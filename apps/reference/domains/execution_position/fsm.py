"""
FSMP-P1-T02: Orchestration of 3 FSM flows for execution_position domain.

This FSM acts as a wrapper, routing commands to the appropriate flow FSM
(Open, Manage, Close) on a per-symbol basis. It integrates directly with
the vFoundation BinanceAdapter to execute trades in the configured environment.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

# T2B-04: Time abstraction for deterministic testing
from apps.reference.core.time import get_clock
from typing import Dict, Any, Optional, Tuple, Set, Coroutine, List, TYPE_CHECKING

from vfoundation.core.fsm_emit_compat import Message, emit_compat
from vfoundation.dr import wal
from apps.reference.adapters.binance_adapter import BinanceAdapter, BinanceAPIError
from apps.reference.config_models import (
    AuroraConfig,
    ExecutionPositionRestoreArtifactConfig,
    ExecutionPositionRestoreArtifactMode,
    ExecutionPositionStartupTruthArtifactConfig,
    PositionPolicySidecarConfig,
)
from apps.reference.utils.accessors import aget, dget

from .fsm_open import OpenFlowFSM
from .fsm_manage import ManageFlowFSM, ManageState
from .fsm_close import CloseFlowFSM, CloseState
from .bracket_math import compute_bracket_targets
from .exposure_guard import ExposureGuard
from .watchdog import OrderTimeoutWatchdog, OrderDeadline
from .utils import (
    quantize_stop_price,
    generate_client_order_id,
    validate_not_immediate,
    opposite_side,
    BoundedEventDeduper,
    coerce_exchange_bool,
)
from .aurora_log_adapter import AuroraLogAdapter
from .terminal_order_contracts import (
    emit_canonical_terminal_order_event,
)
from .trade_executed_contracts import normalize_trade_executed_payload
from .metrics_collector import MetricsCollector
from .intent_boundary_audit import IntentBoundaryAudit
from apps.reference.telemetry.order_logger import order_logger
from apps.reference.telemetry.trade_lifecycle_logger import (
    EXECUTION_BRACKET_OWNERSHIP_RECORD_KIND,
    EXECUTION_FILL_INGRESS_RECORD_KIND,
    POSITION_POLICY_SIDECAR_RECORD_KIND,
    append_trade_lifecycle_record,
)

# FIX-LIFECYCLE-01: Trade lifecycle source-of-truth logger
try:
    from apps.reference.telemetry.trade_lifecycle_logger import trade_lifecycle as _trade_lifecycle
except ImportError:
    _trade_lifecycle = None

from vfoundation.obs.correlation import CorrelationStore
from .utils_event_bus import LocalBus

from .idempotent_cancel import IdempotentCancelHelper, IdempotentCancelResult

# Import OrderGuardian for TP/SL cleanup
from apps.reference.domains.execution_position.order_guardian import OrderGuardian

# EP-01: Import regime mapping for ExposureGuard adaptation
from apps.reference.core.types.regime_types import map_regime_to_bucket

# TASK50: Import qty normalizer for fail-closed quantity validation
from apps.reference.domains.execution_position.qty_normalizer import normalize_qty
from vfoundation.obs.domain_bridge import DomainBridge

# PHASE4: Pending brackets WAL persistence
from apps.reference.domains.execution_position.pending_brackets_wal import (
    write_pending_brackets_stored,
    write_pending_brackets_cleared,
    read_pending_brackets_from_wal,
)

# Phase 14A: Sub-module imports (Strangler Fig decomposition)
from apps.reference.domains.execution_position.leverage_config import LeverageConfigManager
from apps.reference.domains.execution_position.entry_manager import EntryManager
from apps.reference.domains.execution_position.exposure_manager import ExposureManager
from apps.reference.domains.execution_position.lifecycle import LifecycleManager
from apps.reference.domains.execution_position.intent_router import IntentRouter
from apps.reference.domains.execution_position.event_handlers import EPEventHandlers
from apps.reference.domains.execution_position.close_executor import CloseExecutor
from apps.reference.domains.execution_position.open_executor import OpenExecutor, UncertainSubmitRecoveryError
from apps.reference.domains.execution_position.bracket_manager import BracketManager
from apps.reference.domains.execution_position.position_policy_sidecar import (
    ACTION_PACKAGE_VERSION,
    CLOSE_REQUEST_COMMAND_TOPIC,
    PositionPolicyCloseRequest,
    PositionPolicySidecar,
)
from apps.reference.telemetry.shadow_journal import (
    attach_shadow_journal,
    get_shadow_journal,
    snapshot_execpos_state,
)
from apps.reference.domains.execution_position.truth_hardening import (
    attach_execution_truth_hardening,
    build_position_signature,
    get_execution_truth_hardening,
    normalize_close_qty,
)
from apps.reference.domains.execution_position.restore_artifact import (
    BRACKET_STATE_DEFERRED_PENDING_WAL,
    BRACKET_STATE_LINKED_ACTIVE,
    BRACKET_STATE_PARTIAL_LINKAGE,
    BRACKET_STATE_UNKNOWN,
    RESTORE_PHASE_UNKNOWN,
    DeferredBracketRef,
    ExecutionPositionRestoreArtifactDarkReader,
    ExecutionPositionRestoreArtifactWriter,
    ExecutionPositionRestoreAuthoritativeStatus,
    ExecutionPositionRestoreAuthoritativeSymbolStatus,
    ExecutionPositionRestoreDarkReadStatus,
    ExecutionPositionRestoreEnvelope,
    ExecutionPositionRestoreLifecycleRecord,
    ExecutionPositionStartupTruthArtifactWriter,
    ExecutionPositionStartupTruthCacheStatus,
    ExecutionPositionStartupTruthInputSnapshot,
    ExecutionPositionStartupTruthRecord,
    ExecutionPositionStartupTruthRestoreArtifactStatus,
    ExecutionPositionStartupTruthSummary,
    ExecutionPositionStartupTruthUnknownSymbolRecord,
    ExecutionPositionStartupTruthSymbolRecord,
    STARTUP_TRUTH_ARTIFACT_SCHEMA_VERSION,
    STARTUP_TRUTH_ARTIFACT_TYPE,
    STARTUP_TRUTH_ARTIFACT_WRITER_COMPONENT,
    TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN,
    TRUTH_SOURCE_RESTORE_ARTIFACT,
    TRUTH_SOURCE_RESTORED_PENDING_WAL,
    TRUTH_SOURCE_RUNTIME_LOCAL,
    TRUTH_SOURCE_UNKNOWN,
)

# Phase 14.2: Additional Strangler Fig micro-extractions
from apps.reference.domains.execution_position.config_resolver import ConfigResolverMixin
from apps.reference.domains.execution_position.async_scheduling import AsyncSchedulingMixin
from apps.reference.domains.execution_position.adapter_init import AdapterInitMixin
from apps.reference.domains.execution_position.health_metrics import HealthMetricsMixin

# Import AlertManager for circuit breaker alerts
try:
    from apps.reference.telemetry.alerts import AlertManager
    ALERT_MANAGER_AVAILABLE = True
except ImportError:
    ALERT_MANAGER_AVAILABLE = False

    class AlertManager:  # type: ignore[no-redef]
        pass

LOG = logging.getLogger(__name__)

if TYPE_CHECKING:
    from apps.reference.config_models import LeverageConfig


def _build_watchdog_trade_executed_message(
    event_name: str,
    payload: Dict[str, Any],
    why: str,
) -> Message:
    """Build the canonical watchdog TRADE_EXECUTED envelope.

    The top-level RID must mirror the normalized business RID in payload["rid"]
    so WAL, shadow, and lifecycle records can be queried with one key.
    """
    verb = event_name.split(":")[1] if ":" in event_name else event_name
    msg_kwargs = {
        "op": "EVT",
        "verb": verb,
        "src": "execution_position",
        "dst": "execution_position",
        "pld": payload,
        "why": why,
    }

    business_rid = payload.get("rid")
    if business_rid not in (None, ""):
        msg_kwargs["rid"] = str(business_rid)

    return Message(**msg_kwargs)


def _utc_hm() -> Tuple[int, int]:
    """Get current hour and minute in UTC."""
    now = datetime.now(timezone.utc)
    return now.hour, now.minute


def _in_quiet(quiet: list[str]) -> bool:
    """
    Check if current UTC time is within any of the quiet hours windows.

    Args:
        quiet: List of time ranges in format "HH:MM-HH:MM" (e.g., ["22:00-06:00"])
               Range wraps around midnight if start > end

    Returns:
        True if current time is within any quiet window, False otherwise
    """
    h, m = _utc_hm()
    cur = h * 60 + m  # Current time in minutes from midnight

    for win in quiet or []:
        try:
            a, b = win.split("-")
            ah, am = map(int, a.split(":"))
            bh, bm = map(int, b.split(":"))
            start = ah * 60 + am
            end = bh * 60 + bm

            if start <= end:
                # Normal range (doesn't wrap midnight)
                if start <= cur <= end:
                    return True
            else:
                # Range wraps around midnight (e.g., 22:00-06:00)
                if cur >= start or cur <= end:
                    return True
        except (ValueError, AttributeError):
            # Skip malformed ranges
            continue

    return False


@dataclass
class PendingEntryMeta:
    """Metadata for a pending LIMIT entry order used by runtime adapters."""

    symbol: str
    side: str
    limit_price: str
    placed_at_ms: int
    tf_sec: int
    cancelable_regimes: Optional[List[str]] = None


class ExecPosFSM(
    ConfigResolverMixin,
    AsyncSchedulingMixin,
    AdapterInitMixin,
    HealthMetricsMixin,
):
    """
    Wrapper FSM for the execution_position domain. It manages FSM instances
    per symbol and handles trade execution via the BinanceAdapter.

    Phase 14.2: Methods extracted to mixins:
    - ConfigResolverMixin: _get_config_value, _resolve_guardian_config, _collect_guardian_symbols
    - AsyncSchedulingMixin: set_async_loop, _get/submit_async, _schedule_guardian/cleanup
    - AdapterInitMixin: _initialize_adapter
    - HealthMetricsMixin: get_metrics, handle_tick, is_healthy
    """

    def __init__(
        self,
        config: Optional[AuroraConfig],
        fsm,
        shadow_mode: bool = False,
        leverage_service: Optional[Any] = None,
        is_live_execution: bool = False,
    ):
        if isinstance(config, dict):
            raise TypeError("ExecPosFSM requires typed AuroraConfig, got dict")
        if config is None:
            raise ValueError(
                f"CRITICAL: {self.__class__.__name__} requires valid AuroraConfig. "
                "Refusing to start with empty defaults."
            )
        self.config = config

        self.fsm = fsm
        try:
            domains = getattr(self.fsm, "domains", None)
            if isinstance(domains, dict):
                domains["execution_position"] = self
        except Exception:
            pass
        self.shadow_mode = shadow_mode
        # BinanceExecutionAdapter or similar
        self.adapter: Optional[Any] = None

        # TASK47c-P3: LeverageService for OpenFlowFSM
        self.leverage_service = leverage_service
        self.is_live_execution = is_live_execution

        self.open_flows: Dict[str, OpenFlowFSM] = {}
        self.manage_flows: Dict[str, ManageFlowFSM] = {}
        self.close_flows: Dict[str, CloseFlowFSM] = {}
        self._flows_lock = threading.Lock()  # EXP-FIX: Thread-safe flows access

        self.log_adapter = AuroraLogAdapter()

        # TASK-ZOMBIE-FIX: Wire MetricsCollector to config (was hardcoded defaults)
        try:
            mc_cfg = self.config.domains.execution_position.metrics_collector
            if mc_cfg is None:
                raise ValueError("metrics_collector config is required")
            self.metrics_collector = MetricsCollector(
                window_size_minutes=int(mc_cfg.window_size_minutes),
                recent_rejections_minutes=int(
                    mc_cfg.recent_rejections_minutes),
                config=mc_cfg,
            )
        except (AttributeError, TypeError) as e:
            raise ValueError(
                f"Failed to load metrics_collector config from domains.execution_position: {e}. "
                "Check domains.yaml has execution_position.metrics_collector.window_size_minutes"
            ) from e

        # Idempotent cancel helper - SSOT: domains.execution_position.idempotent_cancel (FAIL-CLOSED)
        self._idempotent_cancel_helper: Optional[IdempotentCancelHelper] = None
        self._idempotent_cancel_max_retries: Optional[int] = None
        try:
            idempotent_cfg = self.config.domains.execution_position.idempotent_cancel
            if idempotent_cfg is None or idempotent_cfg.max_retries is None:
                raise ValueError("idempotent_cancel.max_retries is required")
            self._idempotent_cancel_max_retries = int(
                idempotent_cfg.max_retries)
            self._idempotent_cancel_helper = IdempotentCancelHelper(
                logger_inst=LOG)
        except (AttributeError, TypeError) as e:
            raise ValueError(
                f"Failed to load idempotent_cancel config from domains.execution_position: {e}. "
                "Check domains.yaml has execution_position.idempotent_cancel.max_retries"
            ) from e

        # EXP-FIX: Initialize exposure guard
        self.exposure_guard = ExposureGuard(self.fsm, self.config)
        # EXP-FIX: Store latest portfolio state
        self._latest_portfolio_state: Dict[str, Any] = {}
        self._portfolio_event_stage_traces: Dict[str, Dict[str, Any]] = {}
        self._portfolio_event_stage_trace_order: List[str] = []
        self._portfolio_event_stage_trace_limit: int = 256
        # Post-close cooldown support (global + per-symbol)
        self._prev_position_amts: Dict[str, float] = {}
        self._last_position_closed_ts: Dict[str, float] = {}
        self._last_any_position_closed_ts: float = 0.0
        try:
            exec_cfg = self.config.trading.execution
        except Exception as e:
            raise ValueError(
                "Missing required config: trading.execution (needed for cooldown_after_close_ms)."
            ) from e
        if exec_cfg is None:
            raise ValueError(
                "Missing required config: trading.execution (needed for cooldown_after_close_ms)."
            )
        if exec_cfg.cooldown_after_close_ms is None:
            raise ValueError(
                "Missing required config: trading.execution.cooldown_after_close_ms."
            )
        self._cooldown_after_close_sec = float(
            exec_cfg.cooldown_after_close_ms) / 1000.0
        # EXP-FIX: Shadow check counter
        self._shadow_check_counter: int = 0
        # ALERT-FIX: Execution error tracking for circuit breaker
        self._exec_error_counts: Dict[str, int] = {}

        self.correlation_store = CorrelationStore()
        # Track SL/TP bracket orders per symbol for atomic cleanup on close
        self._symbol_brackets: Dict[str, Dict[str, str]] = {}
        self._symbol_bracket_truth_source: Dict[str, str] = {}
        self._symbol_manage_truth_source: Dict[str, str] = {}
        # Background task started flag
        self._bg_started: bool = False
        self._guardian_start_scheduled: bool = False
        self._fsm_cleanup_logged: bool = False

        # GATE: Track last tidy timestamps and last gate-block per symbol
        self._symbol_last_tidy_ts: Dict[str, float] = {}
        self._last_entry_block_ts: Dict[str, float] = {}
        self._gate_metrics: Dict[str, int] = {
            "gate_entry_blocked_tidy": 0,
            "gate_entry_allowed_tidy": 0,
        }

        # TP/SL Intent Data Cache (PHASE A2 fix)
        # Stores intent params from DEC:OPEN to be injected into Manage flow on FILL
        self._pending_intent_data: Dict[str, Dict[str, Any]] = {}

        # LIMIT-ENTRY-DEFERRED-BRACKETS: Pending TP/SL for LIMIT entries (placed on fill)
        # Key = entry_order_id, Value = {"symbol", "side", "sl", "tp", "qty", "rid", "idem_key", "tick_size"}
        self._pending_brackets: Dict[str, Dict[str, Any]] = {}
        # Canonical per-symbol bracket ownership snapshot shared by primary,
        # deferred, and recovery placement paths.
        self._bracket_owner_by_symbol: Dict[str, Dict[str, Any]] = {}

        # REGIME-LOG: Track open-time regime per symbol for close-time forensics
        self._open_regime_by_symbol: Dict[str, Dict[str, Any]] = {}

        # FIX-LIFECYCLE-01: Best-effort symbolrid/last fill price cache
        # Used to flush trade_lifecycle on robust position-close detection (portfolio snapshot).
        self._last_lifecycle_rid_by_symbol: Dict[str, str] = {}
        self._last_lifecycle_fill_price_by_symbol: Dict[str, float] = {}

        # PnL + close_reason cache: populated on ORDER_FILLED, consumed on POSITION_CLOSED.
        self._last_realized_pnl_by_symbol: Dict[str, float] = {}
        self._last_close_reason_by_symbol: Dict[str, str] = {}
        self._proven_terminal_close_by_symbol: Dict[str, Dict[str, Any]] = {}
        self._position_policy_close_requests: Dict[str, Dict[str, Any]] = {}

        # PHASE 1: Stable lifecycle identity per symbol for downstream neocortex correlation.
        # Populated from OrderIndex.ref.idempotent_key at fill time (TASK40 block).
        # Emitted as top-level 'lifecycle_id' in ORDER_FILLED and POSITION_CLOSED.
        # Safety: Binance futures enforces net-position semantics (one positionAmt per symbol).
        # Overwrite is safe because concurrent open positions per symbol are impossible
        # under normal operation. Same safety profile as _last_lifecycle_rid_by_symbol above.
        self._last_lifecycle_ikey_by_symbol: Dict[str, str] = {}

        # PHASE 2: Cache exchange tradeId (updated every fill) and entry side (ENTRY fills only).
        # tradeId is emitted as top-level 'trade_id' in POSITION_CLOSED for neocortex correlation.
        # Entry side is cached only from ENTRY fills to prevent SL/TP fill sides from overwriting
        # the original entry direction. Emitted as 'side' in POSITION_CLOSED (replaces "N/A").
        # Safety: Same per-symbol overwrite profile as _last_lifecycle_ikey_by_symbol above.
        self._last_trade_id_by_symbol: Dict[str, str] = {}
        self._last_entry_side_by_symbol: Dict[str, str] = {}

        # PHASE 3: Accumulated commission fees for current lifecycle per symbol.
        # Updated on every fill (ENTRY, SL, TP, CLOSE). Reset after POSITION_CLOSED write.
        # Emitted as 'fees' in POSITION_CLOSED; combined with realized_pnl to produce
        # 'realized_pnl_net'. Both non-None fields enable reward_complete=True in neocortex.
        # Safety: Same per-symbol overwrite profile as other caches above.
        self._accumulated_fees_by_symbol: Dict[str, float] = {}

        # PHASE4: Rehydrate pending brackets from WAL on startup
        # PHASE4: Rehydrate pending brackets from WAL on startup
        # SKIP IN BACKTEST: Do not restore live state into backtest
        if self.config.trading_mode == "backtest":
            LOG.info("i [PHASE4] WAL hydration skipped (backtest mode)")
        else:
            try:
                restored = read_pending_brackets_from_wal()
                if restored:
                    self._pending_brackets = restored
                    LOG.info(
                        f" [PHASE4] Restored {len(restored)} pending brackets from WAL")
            except Exception as e:
                LOG.warning(
                    f"[PHASE4] Failed to restore pending brackets from WAL: {e}")

        # EP-01.3-SUPERSEDE-ACK: Queued supersede state
        # When supersede cancels old entry, new open is queued until cancel confirmed
        # Key = symbol, Value = {"decision": decision_msg, "cancel_order_id": str, "queued_at": float}
        self._supersede_queue: Dict[str, Dict[str, Any]] = {}
        # Symbols currently waiting for cancel confirmation before executing queued open
        self._supersede_canceling: set = set()
        self._last_features_cache: Dict[str, Dict[str, Any]] = {}
        self._pending_entry_meta: Dict[str, PendingEntryMeta] = {}
        self._open_strategy_by_symbol: Dict[str, str] = {}
        self._last_regime_by_symbol: Dict[str, str] = {}
        self._bracket_health_started: bool = False

        # Orphan-monitor configuration (Strict SSOT)
        # CFG-NO-DEFAULTS: All values must come from config.trading.execution.manage.orphan_monitor
        self._orphan_monitor_cfg = getattr(
            self.config.trading.execution.manage, "orphan_monitor", None)

        # If config is missing entirely, disable functionality (safe fallback for optional section)
        # But if section exists, it MUST have all fields (Pydantic enforced)
        self._orphan_cfg: Dict[str, Any] = {}
        if self._orphan_monitor_cfg:
            self._orphan_cfg = {
                "enabled": self._orphan_monitor_cfg.enabled,
                "run_on_startup": self._orphan_monitor_cfg.run_on_startup,
                "periodic_interval_sec": self._orphan_monitor_cfg.periodic_interval_sec,
                "min_order_age_sec": self._orphan_monitor_cfg.min_order_age_sec,
                "batch_cancel_limit": self._orphan_monitor_cfg.batch_cancel_limit,
                "rate_limit_per_min": self._orphan_monitor_cfg.rate_limit_per_min,
            }
            LOG.info(
                f"OrphanMonitor configured: interval={self._orphan_cfg['periodic_interval_sec']}s")
        else:
            self._orphan_cfg = {"enabled": False}
            LOG.info("OrphanMonitor disabled (no config)")
        # Orphan-monitor runtime counters/metrics
        self._orphan_metrics: Dict[str, int] = {
            "loops": 0,
            "cancels": 0,
            "reconcile_cancelled": 0,
            "skipped_age": 0,
            "skipped_rate_limit": 0,
            "errors": 0,
            "tp_sl_skipped_no_position": 0,
            "tp_sl_placed_success": 0,
            "tp_sl_retry_backoff": 0,
            "clientorderid_reuse_success": 0,
        }
        self._orphan_rate_window_start: float = 0.0
        self._orphan_rate_count: int = 0

        self._guardian_cfg: Dict[str, Any] = self._resolve_guardian_config()
        self._guardian_unified: bool = bool(
            dget(self._guardian_cfg, "unified", True))
        self._guardian_emit_tidy_event: bool = bool(
            dget(self._guardian_cfg, "emit_tidy_event", True))
        self._guardian_poll_interval_ms: int = int(
            dget(self._guardian_cfg, "poll_interval_ms", 500))
        self._fsm_cleanup_enabled: bool = bool(
            self._get_config_value(
                ["execution", "fsm_periodic_cleanup_enabled"], default=True)
        )

        # BUS-FAILCLOSED-01: Fail-closed bus wiring.
        # Silent LocalBus fallback caused production-invisible intent drops
        # (TRADE_INTENT_PROPOSED emitted on FSMCore, ExecPosFSM on LocalBus).
        if self.fsm and hasattr(self.fsm, "listen") and hasattr(self.fsm, "emit"):
            self.bus = self.fsm
            LOG.debug("ExecPosFSM using FSMCore event bus")
        elif self.shadow_mode:
            self.bus = LocalBus()
            LOG.info(
                "ExecPosFSM using LocalBus (shadow_mode=True, test-only)")
        else:
            raise RuntimeError(
                "BUS-FAILCLOSED-01: ExecPosFSM requires a valid FSMCore bus. "
                "Received fsm=%r. Silent LocalBus fallback is prohibited in "
                "production to prevent invisible intent drops." % type(
                    self.fsm)
            )
        self._shadow_journal = attach_shadow_journal(self.fsm, self.config)
        self._execution_truth_hardening = attach_execution_truth_hardening(
            self.fsm,
            self.config,
        )
        self._trade_lifecycle = _trade_lifecycle
        self._restore_artifact_writer = self._create_restore_artifact_writer()
        self._restore_artifact_dark_reader = self._create_restore_artifact_dark_reader()
        self._startup_truth_artifact_writer = self._create_startup_truth_artifact_writer()
        self._restore_artifact_loop_started: bool = False
        self._emit_trade_intent_reject_wal = True
        self.position_policy_close_request_type = PositionPolicyCloseRequest
        self._position_policy_sidecar: Optional[PositionPolicySidecar] = None

        audit_cfg = None
        try:
            audit_cfg = self.config.domains.execution_position.intent_boundary_audit
        except Exception:
            audit_cfg = None
        self._intent_boundary_audit = IntentBoundaryAudit(
            bus=self.bus,
            config=audit_cfg,
            logger=LOG.getChild("IntentBoundaryAudit"),
            lifecycle=self._trade_lifecycle,
            write_wal=self._emit_trade_intent_reject_wal,
        )
        self._intent_boundary_audit.register_bus_listeners()

        # Register event listeners on the bus
        self.bus.listen("EVT:PORTFOLIO_STATE_UPDATED",
                        self._on_portfolio_state_updated)
        self.bus.listen("EVT:ORDER_ACK", self._on_order_ack)
        self.bus.listen("EVT:TRADE_EXECUTED", self._on_trade_executed)
        self.bus.listen("EVT:ORDER_FILL", self._on_order_fill)
        self.bus.listen("EVT:ORDER_STATE_CHANGED",
                        self._on_order_state_changed)
        self.bus.listen("EVT:FEATURES_CALCULATED",
                        self._on_features_calculated)
        # EP-01: Subscribe to regime changes for dynamic risk adaptation
        self.bus.listen("EVT:REGIME_DETECTED", self._on_regime_detected)
        self.bus.listen("EVT:EXECUTION_CLOSE_RECONCILED",
                        self._on_execution_close_reconciled)
        # BUGFIX: Connect DecisionMaking intent to ExecutionPosition logic
        self.bus.listen("EVT:TRADE_INTENT_PROPOSED",
                        self._on_trade_intent_proposed)
        self.bus.listen("EVT:TRADE_INTENT_REJECTED",
                        self._on_trade_intent_rejected)
        # LLM external intent path: wire CMD:EXTERNAL_OPEN_REQUEST_V1
        self.bus.listen("CMD:EXTERNAL_OPEN_REQUEST_V1",
                        self._on_external_open_request)
        self.bus.listen(
            CLOSE_REQUEST_COMMAND_TOPIC,
            self._on_position_policy_close_request,
        )

        # Phase 14D: DomainBridge for orphan domains
        self._domain_bridge = DomainBridge("execution_position", bus=self.bus)
        self._domain_bridge.register_health_fn(self.is_healthy)
        self._last_status_ts = 0.0

        # Async loop used for guardian and adapter operations (set later)
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None

        # Initialize order timeout watchdog
        watchdog_config = self._get_config_value(["execution", "watchdog"])
        if not watchdog_config:
            watchdog_config = self._get_config_value(
                ["trading", "execution", "watchdog"])
        if not watchdog_config:
            watchdog_config = self._get_config_value(["trading", "watchdog"])

        if watchdog_config is None:
            watchdog_config = {}

        # Safe extraction of watchdog settings
        def get_watchdog_setting(key: str, default):
            # Direct access only (fail-closed: missing field  AttributeError)
            if isinstance(watchdog_config, dict):
                # Dict path for legacy compatibility, but NO defaults
                if key not in watchdog_config:
                    raise ValueError(
                        f"CRITICAL: watchdog.{key} missing. FSM cannot start without watchdog config."
                    )
                return watchdog_config[key]
            else:
                # Pydantic model - direct access
                return getattr(watchdog_config, key)

        # Direct access - if missing, raises ValueError (fail-closed)
        ack_ttl_ms: int = int(get_watchdog_setting("ack_ttl_ms", None))
        fill_ttl_ms: int = int(get_watchdog_setting("fill_ttl_ms", None))
        # P1_EXECUTION_TIMEOUT_TRUTH_RESTORATION: wire canonical cadence/throttle fields
        check_interval_ms: int = int(
            get_watchdog_setting("check_interval_ms", None))
        rps_limit: int = int(get_watchdog_setting("rps_limit", None))

        # Log TTL configuration source and values
        ttl_source = "execution.watchdog"
        if watchdog_config is None or not watchdog_config:
            ttl_source = "trading.watchdog"
        # NOTE: shadow alias probe for trading.orders.default_ttl_seconds removed (P1 slice)

        LOG.info(
            f"ExecPosFSM TTL config: ack_ttl_ms={ack_ttl_ms}, fill_ttl_ms={fill_ttl_ms}, "
            f"check_interval_ms={check_interval_ms}, rps_limit={rps_limit}, source={ttl_source}")

        # P1_EXECUTION_TIMEOUT_TRUTH_RESTORATION: Shadow alias reads for
        # trading.orders.default_ttl_seconds and root orders.default_ttl_seconds
        # have been removed. fill_ttl_ms from watchdog config is the sole SSOT.
        # Per-order LIMIT lifetime is owned by valid_for_ms -> fill_ttl_override_ms chain.
        self.watchdog: OrderTimeoutWatchdog = OrderTimeoutWatchdog(
            ack_ttl_ms=ack_ttl_ms,
            fill_ttl_ms=fill_ttl_ms,
            check_interval_ms=check_interval_ms,
            rps_limit=rps_limit,
            on_timeout_callback=self._handle_order_timeout
        )

        # Initialize processed events tracking for idempotent WS/REST handling
        # SSOT: domains.execution_position.event_dedup (fail-closed if missing)
        try:
            event_dedup_cfg = self.config.domains.execution_position.event_dedup
            if event_dedup_cfg is None:
                raise ValueError(
                    "event_dedup config is required in domains.execution_position")
            dedup_max = event_dedup_cfg.max_size
            dedup_ttl = event_dedup_cfg.ttl_ms
        except (AttributeError, TypeError) as e:
            raise ValueError(
                f"Failed to load event_dedup config from domains.execution_position: {e}. "
                "Check domains.yaml has execution_position.event_dedup section."
            ) from e

        self._processed_events = BoundedEventDeduper(
            max_size=dedup_max, ttl_ms=dedup_ttl)

        # Initialize AlertManager for circuit breaker alerts
        self.alert_manager: Optional[AlertManager] = None
        if ALERT_MANAGER_AVAILABLE:
            try:
                self.alert_manager = AlertManager(
                    config=self.config, logger=aget(self, "logger", LOG).getChild("alerts"))
                LOG.info("AlertManager initialized in ExecPosFSM")
            except Exception as e:
                LOG.warning(
                    f"Failed to initialize AlertManager in ExecPosFSM: {e}")

        # Ensure attribute exists even if init fails
        self.order_guardian: Optional[OrderGuardian] = None

        if not self.shadow_mode:
            self._initialize_adapter()
            #  POLLING FIX: Connect Watchdog hooks to adapter functions after initialization
            if hasattr(self.watchdog, 'set_hooks') and self.adapter:
                async def emit_trade_executed(event_name, payload, why="polling_fill"):
                    """Emit TRADE_EXECUTED event via FSM event system."""
                    try:
                        msg = _build_watchdog_trade_executed_message(
                            event_name,
                            payload,
                            why,
                        )
                        await emit_compat(self.fsm, msg, logger=LOG)
                    except Exception as e:
                        LOG.error(f"Failed to emit {event_name}: {e}")

                self.watchdog.set_hooks(
                    get_order_fn=self.adapter.get_order,
                    emit_fn=emit_trade_executed
                )
                LOG.info(
                    " Watchdog REST polling hooks connected to adapter functions")
            # Initialize OrderGuardian for TP/SL cleanup with strict ownership tracking
            # MAGIC-NUM-EXTRACTION: poll_interval_ms from SSOT domains.execution_position.guardian
            poll_interval_ms = self._guardian_poll_interval_ms

            LOG.info(
                f"OrderGuardian poll_interval_ms from config: {poll_interval_ms}")

            try:
                self.order_guardian = OrderGuardian(
                    self.adapter, config=self.config, poll_interval_ms=poll_interval_ms, bus=self.bus)
                LOG.info(" OrderGuardian initialized for ExecPosFSM")

                #  FIX: Defer OrderGuardian startup until after FSM initialization
                # Will be started via start_order_guardian() method when event loop is available
                LOG.info(" OrderGuardian ready for startup")

                #  FIX: Add startup re-linking to detect existing orphaned orders
                # Will be called via start_order_guardian() method when event loop is available
                guardian_symbols = self._collect_guardian_symbols()
                if guardian_symbols:
                    try:
                        self.order_guardian.update_known_symbols(
                            guardian_symbols)
                    except AttributeError:
                        pass

                self._schedule_guardian_start()
                self._schedule_fsm_cleanup_loop()
                self.watchdog.start()  # Start timeout watchdog (always, not just on guardian failure)
            except Exception as e:
                LOG.error(f"Failed to initialize OrderGuardian: {e}")
                self.order_guardian = None
                self.watchdog.start()  # Start timeout watchdog even if guardian fails
                self._schedule_fsm_cleanup_loop()
        else:
            # Initialize OrderGuardian even in shadow mode for cleanup operations
            # MAGIC-NUM-EXTRACTION: poll_interval_ms from SSOT domains.execution_position.guardian
            poll_interval_ms = self._guardian_poll_interval_ms

            self.order_guardian = OrderGuardian(
                None,  # No adapter in shadow mode
                config=self.config,
                poll_interval_ms=poll_interval_ms,
                bus=self.bus,
            )
            LOG.info(" OrderGuardian initialized for ExecPosFSM (shadow mode)")
            guardian_symbols = self._collect_guardian_symbols()
            if guardian_symbols:
                try:
                    self.order_guardian.update_known_symbols(guardian_symbols)
                except AttributeError:
                    pass
            self._schedule_guardian_start()
            self._schedule_fsm_cleanup_loop()
            self.watchdog.start()  # Start timeout watchdog in shadow mode too

        # Subscribe to Guardian TIDY events to update gate state
        try:
            if hasattr(self, 'bus') and self.bus:
                self.bus.listen("EVT:SYMBOL_TIDY", self._on_symbol_tidy_event)
        except Exception:
            pass

        # Phase 14A: Create sub-module instances (Strangler Fig delegation targets)
        self._lev_cfg = LeverageConfigManager(self)
        self._entry_mgr = EntryManager(self)
        self._exposure_mgr = ExposureManager(self)
        self._lifecycle_mgr = LifecycleManager(self)
        self._intent_router = IntentRouter(self)
        self._evt_handlers = EPEventHandlers(self)
        self._close_exec = CloseExecutor(self)
        self._open_exec = OpenExecutor(self)
        self._bracket_mgr = BracketManager(self)
        self.position_policy_close_request_type = PositionPolicyCloseRequest
        self._position_policy_sidecar = self._create_position_policy_sidecar()
        if self._position_policy_sidecar is not None:
            self._position_policy_sidecar.announce_mode_active()

    async def run_leverage_bootstrap(self) -> Set[str]:
        """Phase 14A: Delegated to LeverageConfigManager."""
        return await self._lev_cfg.run_bootstrap()

    def _collect_leverage_configs(self) -> Dict[str, "LeverageConfig"]:
        """Phase 14A: Delegated to LeverageConfigManager."""
        return self._lev_cfg.collect_configs()

    def validate_leverage_ssot_consistency(self) -> List[str]:
        """Phase 14A: Delegated to LeverageConfigManager."""
        return self._lev_cfg.validate_ssot_consistency()

    def _resolve_price(self, pld: Dict[str, Any], key: str) -> Optional[str]:
        """
        Smart extraction to handle flat (DecisionMaking) vs nested (Strategy) payloads.

        Priority:
        1. Root level (normalized by DM)
        2. price_ctx (raw strategy output, e.g., MeanReversion)
        3. order nested object (legacy/alternative structure)

        CFG-SMART-EXTRACT-01: Ensures stop_price/target_price are found regardless
        of where Strategy places them in the payload hierarchy.
        """
        # 1. Root level
        val = pld.get(key)
        if val not in (None, "", "None", "null"):
            return str(val)

        # 2. Nested price_ctx (e.g., from MeanReversion strategy)
        price_ctx = pld.get("price_ctx")
        if isinstance(price_ctx, dict):
            ctx_val = price_ctx.get(key)
            if ctx_val not in (None, "", "None", "null"):
                return str(ctx_val)

        # 3. Nested order object (alternative/legacy structure)
        order = pld.get("order")
        if isinstance(order, dict):
            order_val = order.get(key)
            if order_val not in (None, "", "None", "null"):
                return str(order_val)

        return None

    def _evaluate_supersede_reprice_guard(
        self,
        symbol: str,
        decision: Message,
        pending_order_ids: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Evaluate whether a same-side LIMIT supersede materially improves price."""
        try:
            pe_ttl_cfg = self.config.domains.execution_position.pending_entry_ttl
            guard_cfg = pe_ttl_cfg.supersede_reprice_guard
        except AttributeError:
            return None

        if guard_cfg is None:
            return None
        try:
            if not bool(guard_cfg.enabled):
                return None
        except AttributeError:
            return None

        pld = decision.pld or {}
        if str(pld.get("order_type", "")).upper() != "LIMIT":
            return None

        new_side = str(pld.get("side", "")).upper()
        new_price_raw = pld.get("price")
        if not new_side or new_price_raw in (None, ""):
            return None

        try:
            new_price = Decimal(str(new_price_raw))
        except Exception:
            return None
        if new_price <= 0:
            return None

        features_snap = self._last_features_cache.get(symbol) or {}
        feats = features_snap.get("features", {}) if isinstance(
            features_snap, dict) else {}
        atr_14 = None
        atr_raw = feats.get("atr_14")
        if atr_raw not in (None, ""):
            try:
                atr_14 = Decimal(str(atr_raw))
            except Exception:
                atr_14 = None
        if atr_14 is not None and atr_14 <= 0:
            atr_14 = None

        analyses: List[Dict[str, Any]] = []
        for order_id in pending_order_ids:
            meta = self._pending_entry_meta.get(order_id)
            if meta is None or str(meta.side).upper() != new_side:
                return None
            old_price = Decimal(str(meta.limit_price))
            bps_threshold_px = (
                old_price
                * Decimal(str(getattr(guard_cfg, "min_price_improvement_bps", 0.0)))
                / Decimal("10000")
            )
            atr_threshold_px = Decimal("0")
            atr_mult = Decimal(
                str(getattr(guard_cfg, "min_price_improvement_atr_mult", 0.0)))
            if atr_14 is not None and atr_mult > 0:
                atr_threshold_px = atr_14 * atr_mult
            threshold_px = max(bps_threshold_px, atr_threshold_px)
            improvement_px = new_price - old_price if new_side == "BUY" else old_price - new_price
            analyses.append(
                {
                    "order_id": order_id,
                    "old_price": str(old_price),
                    "new_price": str(new_price),
                    "improvement_px": float(improvement_px),
                    "threshold_px": float(threshold_px),
                    "allow_cancel": improvement_px >= threshold_px,
                }
            )

        if not analyses:
            return None
        decision_summary = {
            "symbol": symbol,
            "side": new_side,
            "analyses": analyses,
            "enforce": bool(getattr(guard_cfg, "enforce", False)),
            "allow_cancel": all(bool(item.get("allow_cancel")) for item in analyses),
        }
        if hasattr(self, "_emit_observability_event"):
            try:
                self._emit_observability_event(
                    "SUPERSEDE_REPRICE_GUARD", decision_summary)
            except Exception:
                pass
        return decision_summary

    def _evaluate_advanced_stale_cancel(self, symbol: str, new_regime: str) -> None:
        """Cancel pending entries only when regime, age, and drift gates all pass."""
        try:
            pe_cfg = self.config.domains.execution_position.pending_entry_ttl
            adv = pe_cfg.advanced_stale_cancel
        except AttributeError:
            return
        if adv is None or not adv.enabled:
            return

        candidates: List[Tuple[str, Any]] = []
        if self.watchdog:
            for oid, dl in list(self.watchdog.pending_orders.items()):
                if dl.symbol == symbol:
                    candidates.append((oid, dl))
            for oid, dl in list(self.watchdog.acked_orders.items()):
                if dl.symbol == symbol:
                    candidates.append((oid, dl))
        if not candidates:
            return

        now_ms = get_clock().now_ms()
        features_snap = self._last_features_cache.get(symbol)
        approved_order_ids: Set[str] = set()

        for order_id, _deadline in candidates:
            meta = self._pending_entry_meta.get(order_id)
            if meta is None:
                continue

            if meta.cancelable_regimes is not None:
                if new_regime not in meta.cancelable_regimes:
                    continue
            else:
                side_may = set(
                    getattr(adv, "may_cancel_regimes", {}).get(meta.side, []))
                never = set(
                    getattr(adv, "never_cancel_regimes", ["UNCERTAIN"]))
                if new_regime not in (side_may - never):
                    continue

            age_ms = now_ms - meta.placed_at_ms
            min_age_ms = adv.min_age_before_cancel_sec * 1000
            if age_ms < min_age_ms:
                continue

            if features_snap is None:
                continue
            feats = features_snap.get("features", {})
            price_raw = feats.get("price")
            atr_raw = feats.get("atr_14")
            if price_raw is None or atr_raw is None:
                continue
            try:
                current_price = Decimal(str(price_raw))
                atr_14 = Decimal(str(atr_raw))
                limit_price = Decimal(str(meta.limit_price))
            except Exception:
                continue
            if atr_14 <= 0:
                continue

            threshold = atr_14 * Decimal(str(adv.drift_away.atr_mult))
            drift = current_price - limit_price if meta.side == "BUY" else limit_price - current_price
            if drift < threshold:
                continue
            approved_order_ids.add(order_id)

        if approved_order_ids:
            self._entry_mgr.cancel_pending_entries_for_symbol(
                symbol=symbol,
                reason="CANCEL_STALE_REGIME_ADVANCED",
                context=f"regime={new_regime} approved={sorted(approved_order_ids)}",
                filter_order_ids=approved_order_ids,
            )

    def _mark_processed_event(self, event_key: str) -> bool:
        """Idempotency helper with bounded memory."""
        if self._processed_events.seen(event_key):
            return False

        now_ms = get_clock().now_ms()
        self._processed_events.add(event_key, now_ms)
        return True

    # Phase 14.2: _get_config_value, _resolve_guardian_config, _collect_guardian_symbols
    #  extracted to ConfigResolverMixin (config_resolver.py)

    # Phase 14.2: set_async_loop, _get_async_loop, _submit_async,
    # _schedule_guardian_start, _schedule_fsm_cleanup_loop
    #  extracted to AsyncSchedulingMixin (async_scheduling.py)

    @staticmethod
    def _is_cancel_success_response(result: Any) -> bool:
        """Treat standard cancel success and -2011 idempotent paths uniformly."""
        if isinstance(result, IdempotentCancelResult):
            return bool(result.success and result.is_idempotent_success)
        if hasattr(result, "status"):
            status = str(getattr(result, "status") or "").upper()
            if status in ("CANCELED", "CANCELLED"):
                return True
        if isinstance(result, dict):
            status = str(result["status"]
                         if "status" in result else "").upper()
            if status == "CANCELED":
                return True
            code = result.get("code")
            if code == -2011:
                return True
            msg = str(result["msg"] if "msg" in result else "").lower()
            if "unknown order" in msg:
                return True
        return False

    @staticmethod
    def _cancel_status_str(result: Any) -> str:
        if isinstance(result, IdempotentCancelResult):
            return str(result.order_status_after or result.order_status_before or "").upper()
        if hasattr(result, "status"):
            return str(getattr(result, "status") or "").upper()
        if isinstance(result, dict):
            return str(result.get("status") or "").upper()
        return ""

    async def _cancel_order(self, symbol: str, order_id: str) -> Any:
        """Unified cancel path with optional idempotent helper."""
        if not self.adapter:
            raise RuntimeError("ExecPosFSM adapter is not initialized")

        helper = self._idempotent_cancel_helper
        max_retries = self._idempotent_cancel_max_retries
        if helper and isinstance(max_retries, int) and max_retries > 0 and hasattr(self.adapter, "get_order"):
            try:
                res = await helper.cancel_order_idempotent(
                    symbol=symbol,
                    order_id=str(order_id),
                    cancel_func=self.adapter.cancel_order,
                    get_order_func=self.adapter.get_order,
                    max_retries=max_retries,
                )
                helper.log_cancel_result(res, str(order_id))
                return res
            except Exception as e:
                LOG.debug(
                    f"IDEMPOTENT_CANCEL: helper failed, fallback to direct cancel: {e}")

        return await self.adapter.cancel_order(symbol, order_id)

    @staticmethod
    def _is_unknown_order_error(error: Exception) -> bool:
        """Detect -2011 or equivalent unknown order errors from adapter."""
        if isinstance(error, BinanceAPIError) and aget(error, "code", None) == -2011:
            return True
        message = str(error).lower()
        return "unknown order" in message

    def _cancel_pending_entries_for_symbol(
        self,
        symbol: str,
        reason: str,
        context: str = "",
    ) -> None:
        """Phase 14A: Delegated to EntryManager."""
        self._entry_mgr.cancel_pending_entries_for_symbol(
            symbol, reason, context)

    def _cancel_all_pending_entries(self, reason: str = "CANCEL_PANIC_KILL") -> None:
        """Phase 14A: Delegated to EntryManager."""
        self._entry_mgr.cancel_all_pending_entries(reason)

    def on_panic_killswitch_activated(self) -> None:
        """Phase 14A: Delegated to EntryManager."""
        self._entry_mgr.on_panic_killswitch_activated()

    def _process_queued_supersede(self, symbol: str) -> None:
        """Phase 14A: Delegated to EntryManager."""
        self._entry_mgr.process_queued_supersede(symbol)

    def _on_regime_detected(self, event: Message) -> None:
        """Phase 14A: Delegated to EPEventHandlers."""
        self._evt_handlers.on_regime_detected(event)
        if self._position_policy_sidecar is not None:
            self._position_policy_sidecar.on_regime_detected(event)

    def _on_trade_intent_proposed(self, msg: Message) -> None:
        """Phase 14A: Delegated to IntentRouter."""
        self._intent_router.on_trade_intent_proposed(msg)

    def _on_trade_intent_rejected(self, msg: Message) -> None:
        """Phase 14A: Delegated to IntentRouter."""
        self._intent_router.on_trade_intent_rejected(msg)

    def _on_external_open_request(self, msg: Message) -> None:
        """Phase 14A: Delegated to IntentRouter (LLM external intent path)."""
        self._intent_router.on_external_open_request(msg)

    def _on_portfolio_state_updated(self, event: Message) -> None:
        """Phase 14A: Delegated to EPEventHandlers."""
        self._evt_handlers.on_portfolio_state_updated(event)
        if self._position_policy_sidecar is not None:
            self._record_portfolio_event_trace_stage(
                event,
                "sidecar_portfolio_refresh_reached",
            )
            self._position_policy_sidecar.on_portfolio_state_updated(event)
            self._record_portfolio_event_trace_stage(
                event,
                "sidecar_portfolio_refresh_completed",
            )

    def _on_order_ack(self, event: Message) -> None:
        """Phase 14A: Delegated to EPEventHandlers."""
        self._evt_handlers.on_order_ack(event)

    @staticmethod
    def _manage_state_value(manage_flow: Optional[ManageFlowFSM]) -> str:
        if manage_flow is None:
            return ""
        state = getattr(manage_flow, "state", None)
        if state is None:
            return ""
        return str(getattr(state, "value", state) or "")

    @staticmethod
    def _close_state_value(close_flow: Optional[CloseFlowFSM]) -> str:
        if close_flow is None:
            return ""
        state = getattr(close_flow, "state", None)
        if state is None:
            return ""
        return str(getattr(state, "value", state) or "")

    def _create_restore_artifact_writer(
        self,
    ) -> Optional[ExecutionPositionRestoreArtifactWriter]:
        try:
            candidate = self.config.domains.execution_position.restore_artifact
        except Exception:
            return None

        if not isinstance(candidate, ExecutionPositionRestoreArtifactConfig):
            return None

        return ExecutionPositionRestoreArtifactWriter(
            candidate,
            observability_hook=self._emit_observability_event,
            logger=LOG,
        )

    def _restore_artifact_mode(self) -> Optional[ExecutionPositionRestoreArtifactMode]:
        try:
            candidate = self.config.domains.execution_position.restore_artifact
        except Exception:
            return None
        if not isinstance(candidate, ExecutionPositionRestoreArtifactConfig):
            return None
        return candidate.mode

    def _authoritative_restore_enabled(self) -> bool:
        return self._restore_artifact_mode() == ExecutionPositionRestoreArtifactMode.AUTHORITATIVE

    def _manage_truth_source_for(self, symbol: str) -> str:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return TRUTH_SOURCE_UNKNOWN
        if symbol_key in self.manage_flows:
            return self._symbol_manage_truth_source.get(
                symbol_key,
                TRUTH_SOURCE_RUNTIME_LOCAL,
            )
        return TRUTH_SOURCE_UNKNOWN

    def _set_manage_truth_source(self, symbol: str, truth_source: str) -> None:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return
        self._symbol_manage_truth_source[symbol_key] = (
            str(truth_source or TRUTH_SOURCE_UNKNOWN).strip().upper()
            or TRUTH_SOURCE_UNKNOWN
        )

    def _clear_manage_truth_source(self, symbol: str) -> None:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return
        self._symbol_manage_truth_source.pop(symbol_key, None)

    def _create_restore_artifact_dark_reader(
        self,
    ) -> Optional[ExecutionPositionRestoreArtifactDarkReader]:
        try:
            candidate = self.config.domains.execution_position.restore_artifact
        except Exception:
            return None

        if not isinstance(candidate, ExecutionPositionRestoreArtifactConfig):
            return None

        return ExecutionPositionRestoreArtifactDarkReader(
            candidate,
            logger=LOG,
        )

    def _create_startup_truth_artifact_writer(
        self,
    ) -> Optional[ExecutionPositionStartupTruthArtifactWriter]:
        try:
            candidate = self.config.domains.execution_position.startup_truth_artifact
        except Exception:
            return None

        if not isinstance(candidate, ExecutionPositionStartupTruthArtifactConfig):
            return None

        return ExecutionPositionStartupTruthArtifactWriter(
            candidate,
            observability_hook=self._emit_observability_event,
            logger=LOG,
        )

    def _restore_artifact_symbol_candidates(self) -> List[str]:
        symbols: Set[str] = set()
        symbols.update(str(sym).upper() for sym in self.manage_flows.keys())
        symbols.update(str(sym).upper() for sym in self.close_flows.keys())
        symbols.update(str(sym).upper()
                       for sym in self._symbol_brackets.keys())
        for pending in dict(self._pending_brackets).values():
            if not isinstance(pending, dict):
                continue
            symbol = str(pending.get("symbol") or "").strip().upper()
            if symbol:
                symbols.add(symbol)
        return sorted(symbols)

    def _set_symbol_bracket_order(
        self,
        symbol: str,
        *,
        order_role: str,
        order_id: str,
        truth_source: str = TRUTH_SOURCE_RUNTIME_LOCAL,
    ) -> None:
        symbol_key = str(symbol or "").strip().upper()
        order_id_str = str(order_id or "").strip()
        role_key = str(order_role or "").strip().upper()
        if not symbol_key or not order_id_str or role_key not in {"SL", "TP"}:
            return
        bracket_key = "sl_order_id" if role_key == "SL" else "tp_order_id"
        self._symbol_brackets.setdefault(symbol_key, {})[
            bracket_key] = order_id_str
        self._symbol_bracket_truth_source[symbol_key] = str(
            truth_source or TRUTH_SOURCE_UNKNOWN
        ).strip().upper() or TRUTH_SOURCE_UNKNOWN

    def _set_symbol_brackets_snapshot(
        self,
        symbol: str,
        *,
        sl_order_id: Optional[str] = None,
        tp_order_id: Optional[str] = None,
        truth_source: str = TRUTH_SOURCE_RUNTIME_LOCAL,
    ) -> None:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return

        brackets: Dict[str, str] = {}
        sl_order_id_str = str(sl_order_id or "").strip()
        tp_order_id_str = str(tp_order_id or "").strip()
        if sl_order_id_str:
            brackets["sl_order_id"] = sl_order_id_str
        if tp_order_id_str:
            brackets["tp_order_id"] = tp_order_id_str

        if not brackets:
            self._clear_symbol_brackets(symbol_key)
            return

        self._symbol_brackets[symbol_key] = brackets
        self._symbol_bracket_truth_source[symbol_key] = str(
            truth_source or TRUTH_SOURCE_UNKNOWN
        ).strip().upper() or TRUTH_SOURCE_UNKNOWN

    def _clear_symbol_brackets(self, symbol: str) -> None:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return
        self._symbol_brackets.pop(symbol_key, None)
        self._symbol_bracket_truth_source.pop(symbol_key, None)

    def _apply_authoritative_local_close_reset(
        self,
        symbol: str,
        *,
        reason: str,
        source: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return False

        anything_reset = False
        manage_flow = self.manage_flows.get(symbol_key)
        if manage_flow is not None:
            try:
                has_active_lifecycle = bool(manage_flow.has_active_lifecycle())
            except Exception:
                has_active_lifecycle = False
            if has_active_lifecycle:
                manage_flow.state = ManageState.FLAT
                manage_flow._clear_lifecycle_tracking(
                    reason=reason,
                    clear_symbol=True,
                )
                anything_reset = True

        close_flow = self.close_flows.get(symbol_key)
        close_state = self._close_state_value(close_flow).upper()
        if close_flow is not None and close_state not in ("", CloseState.FLAT.value):
            close_flow.reset()
            anything_reset = True

        if (
            symbol_key in self._symbol_brackets
            or symbol_key in self._symbol_bracket_truth_source
        ):
            self._clear_symbol_brackets(symbol_key)
            anything_reset = True

        pending_to_clear: List[Tuple[Any, str]] = []
        for entry_order_id, pending in dict(self._pending_brackets).items():
            if not isinstance(pending, dict):
                continue
            pending_symbol = str(pending.get("symbol") or "").strip().upper()
            if pending_symbol == symbol_key:
                pending_to_clear.append((entry_order_id, pending_symbol))

        for entry_order_id, pending_symbol in pending_to_clear:
            self._pending_brackets.pop(entry_order_id, None)
            try:
                write_pending_brackets_cleared(
                    entry_order_id=str(entry_order_id),
                    reason=reason,
                    symbol=pending_symbol or symbol_key,
                )
            except Exception as exc:
                LOG.warning(
                    "Failed to clear pending brackets during authoritative reset "
                    "symbol=%s entry_order_id=%s source=%s reason=%s error=%s",
                    symbol_key,
                    entry_order_id,
                    source,
                    reason,
                    exc,
                )
            anything_reset = True

        if anything_reset:
            LOG.info(
                "[ExecPosFSM] authoritative local close reset applied "
                "symbol=%s source=%s reason=%s payload_keys=%s",
                symbol_key,
                source,
                reason,
                sorted((payload or {}).keys()),
            )
        return anything_reset

    def _symbol_bracket_truth_source_for(self, symbol: str) -> str:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return TRUTH_SOURCE_UNKNOWN
        if symbol_key in self._symbol_brackets:
            return self._symbol_bracket_truth_source.get(
                symbol_key,
                TRUTH_SOURCE_RUNTIME_LOCAL,
            )
        return TRUTH_SOURCE_UNKNOWN

    def _runtime_order_index(self) -> Any:
        direct_index = getattr(self, "order_index", None)
        if direct_index is not None:
            return direct_index
        return getattr(self.fsm, "order_index", None)

    def _resolve_restore_artifact_bracket_snapshot(
        self,
        symbol: str,
    ) -> Dict[str, Any]:
        symbol_key = str(symbol or "").strip().upper()
        pending_order_ids: List[str] = []
        for entry_order_id, pending in dict(self._pending_brackets).items():
            if not isinstance(pending, dict):
                continue
            pending_symbol = str(pending.get("symbol") or "").strip().upper()
            if pending_symbol == symbol_key:
                pending_order_ids.append(str(entry_order_id))

        if len(pending_order_ids) == 1:
            return {
                "bracket_state": BRACKET_STATE_DEFERRED_PENDING_WAL,
                "bracket_truth_source": TRUTH_SOURCE_RESTORED_PENDING_WAL,
                "deferred_entry_order_id": pending_order_ids[0],
                "restore_relevant": True,
            }
        if len(pending_order_ids) > 1:
            return {
                "bracket_state": BRACKET_STATE_UNKNOWN,
                "bracket_truth_source": TRUTH_SOURCE_UNKNOWN,
                "deferred_entry_order_id": None,
                "restore_relevant": True,
            }

        bracket_links = dict(self._symbol_brackets.get(symbol_key) or {})
        has_sl = bool(str(bracket_links.get("sl_order_id") or "").strip())
        has_tp = bool(str(bracket_links.get("tp_order_id") or "").strip())
        if has_sl and has_tp:
            return {
                "bracket_state": BRACKET_STATE_LINKED_ACTIVE,
                "bracket_truth_source": self._symbol_bracket_truth_source_for(
                    symbol_key
                ),
                "deferred_entry_order_id": None,
                "restore_relevant": True,
            }
        if has_sl or has_tp:
            return {
                "bracket_state": BRACKET_STATE_PARTIAL_LINKAGE,
                "bracket_truth_source": self._symbol_bracket_truth_source_for(
                    symbol_key
                ),
                "deferred_entry_order_id": None,
                "restore_relevant": True,
            }
        return {
            "bracket_state": BRACKET_STATE_UNKNOWN,
            "bracket_truth_source": TRUTH_SOURCE_UNKNOWN,
            "deferred_entry_order_id": None,
            "restore_relevant": False,
        }

    def _build_execution_restore_artifact_records(
        self,
    ) -> List[ExecutionPositionRestoreLifecycleRecord]:
        records: List[ExecutionPositionRestoreLifecycleRecord] = []
        for symbol in self._restore_artifact_symbol_candidates():
            record = self._build_execution_restore_artifact_record(symbol)
            if record is not None:
                records.append(record)
        return records

    def _build_execution_restore_artifact_record(
        self,
        symbol: str,
    ) -> Optional[ExecutionPositionRestoreLifecycleRecord]:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return None

        manage_flow = self.manage_flows.get(symbol_key)
        close_flow = self.close_flows.get(symbol_key)
        manage_phase = self._manage_state_value(
            manage_flow) or RESTORE_PHASE_UNKNOWN
        close_phase = self._close_state_value(
            close_flow) or RESTORE_PHASE_UNKNOWN
        bracket_snapshot = self._resolve_restore_artifact_bracket_snapshot(
            symbol_key)

        has_active_manage = self._has_active_lifecycle_for_symbol(symbol_key)
        has_active_close = close_phase not in ("", "FLAT")
        if not (has_active_manage or has_active_close or bracket_snapshot["restore_relevant"]):
            return None

        record_kwargs: Dict[str, Any] = {
            "symbol": symbol_key,
            "manage_phase": manage_phase,
            "manage_truth_source": self._manage_truth_source_for(symbol_key),
            "close_phase": close_phase,
            "bracket_state": bracket_snapshot["bracket_state"],
            "bracket_truth_source": bracket_snapshot["bracket_truth_source"],
            "live_reconcile_required": True,
        }
        if (
            bracket_snapshot["bracket_state"] == BRACKET_STATE_DEFERRED_PENDING_WAL
            and bracket_snapshot["deferred_entry_order_id"]
        ):
            record_kwargs["deferred_bracket_ref"] = DeferredBracketRef(
                entry_order_id=str(
                    bracket_snapshot["deferred_entry_order_id"]),
            )
        return ExecutionPositionRestoreLifecycleRecord(**record_kwargs)

    def _restore_semantics_signature(
        self,
        symbol: str,
    ) -> Tuple[str, str, str, Optional[str], bool]:
        symbol_key = str(symbol or "").strip().upper()
        manage_phase = self._manage_state_value(
            self.manage_flows.get(symbol_key)) or RESTORE_PHASE_UNKNOWN
        close_phase = self._close_state_value(
            self.close_flows.get(symbol_key)) or RESTORE_PHASE_UNKNOWN
        bracket_snapshot = self._resolve_restore_artifact_bracket_snapshot(
            symbol_key)
        has_active_manage = self._has_active_lifecycle_for_symbol(symbol_key)
        has_active_close = close_phase not in ("", "FLAT")
        return (
            manage_phase,
            close_phase,
            str(bracket_snapshot["bracket_state"]),
            (
                str(bracket_snapshot["deferred_entry_order_id"])
                if bracket_snapshot["deferred_entry_order_id"]
                else None
            ),
            bool(
                has_active_manage or has_active_close or bracket_snapshot["restore_relevant"]),
        )

    def _append_restart_truth_record(
        self,
        *,
        event_type: str,
        symbol: str,
        sl_order_id: Optional[str],
        tp_order_id: Optional[str],
        order_index_registrations: int,
        unresolved_reasons: Optional[List[str]] = None,
    ) -> None:
        record = {
            "record_kind": "execution_restart_truth",
            "event_type": event_type,
            "ts_ms": get_clock().now_ms(),
            "symbol": str(symbol or "").strip().upper() or None,
            "sl_order_id": str(sl_order_id or "").strip() or None,
            "tp_order_id": str(tp_order_id or "").strip() or None,
            "bracket_truth_source": self._symbol_bracket_truth_source_for(symbol),
            "manage_truth_source": self._manage_truth_source_for(symbol),
            "order_index_registrations": int(order_index_registrations),
            "unresolved_reasons": list(unresolved_reasons or []) or None,
        }
        filtered = {key: value for key,
                    value in record.items() if value is not None}
        append_trade_lifecycle_record(
            filtered,
            log_file=self._trade_lifecycle_log_path(),
        )
        self._emit_observability_event(event_type, filtered)

    def _startup_reconstruct_runtime_bracket_truth(
        self,
        open_orders: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        order_index = self._runtime_order_index()
        if self.order_guardian is None or order_index is None:
            return {
                "summary": {
                    "symbols_reconstructed": 0,
                    "order_index_registrations": 0,
                    "unresolved_symbols": 0,
                },
                "records": [],
            }

        resolved_orders: Dict[str, Dict[str, str]] = {}
        unresolved_reasons: Dict[str, List[str]] = {}
        duplicate_roles: Dict[str, Set[str]] = {}
        order_index_registrations = 0
        order_index_registrations_by_symbol: Dict[str, int] = {}
        runtime_truth_records: List[Dict[str, Any]] = []

        def _note_unresolved(symbol_key: str, reason: str) -> None:
            unresolved_reasons.setdefault(symbol_key, []).append(reason)

        for raw_order in open_orders:
            order = raw_order if isinstance(raw_order, dict) else {}
            symbol_key = str(order.get("symbol") or "").strip().upper()
            exchange_order_id = str(
                order.get("orderId") or order.get("order_id") or ""
            ).strip()
            client_order_id = str(
                order.get("clientOrderId") or order.get(
                    "client_order_id") or ""
            ).strip()
            if not symbol_key or not exchange_order_id:
                continue

            context = self.order_guardian.resolve_terminal_bracket_context(
                client_order_id=client_order_id or None,
                exchange_order_id=exchange_order_id,
                symbol=symbol_key,
            )
            if context is None:
                continue

            role = str(context.get("bracket_role") or "").strip().upper()
            tracked_order_id = str(
                context.get(
                    "tracked_bracket_order_id") or exchange_order_id or ""
            ).strip()
            tracked_client_order_id = str(
                context.get("tracked_client_order_id") or client_order_id or ""
            ).strip()
            if role not in {"SL", "TP", "TP1", "TP2"}:
                _note_unresolved(
                    symbol_key, f"unsupported_role:{role or 'missing'}")
                continue
            if not tracked_order_id:
                _note_unresolved(
                    symbol_key, f"missing_tracked_order_id:{exchange_order_id}")
                continue
            if not tracked_client_order_id:
                _note_unresolved(
                    symbol_key, f"missing_tracked_client_order_id:{tracked_order_id}")
                continue

            order_kind = "SL" if role == "SL" else "TP"
            resolved_for_symbol = resolved_orders.setdefault(symbol_key, {})
            existing_order_id = resolved_for_symbol.get(order_kind)
            if existing_order_id and existing_order_id != tracked_order_id:
                duplicate_roles.setdefault(symbol_key, set()).add(order_kind)
                _note_unresolved(
                    symbol_key,
                    f"duplicate_{order_kind.lower()}:{existing_order_id},{tracked_order_id}",
                )
            else:
                resolved_for_symbol[order_kind] = tracked_order_id

            if order_index.get(exchangeOrderId=tracked_order_id) is None:
                try:
                    order_index.register_bracket_child(
                        rid=str(context.get("rid") or tracked_order_id),
                        idempotent_key=None,
                        clientOrderId=tracked_client_order_id,
                        exchangeOrderId=tracked_order_id,
                        symbol=symbol_key,
                        side=str(order.get("side") or "").upper(),
                        order_type=str(
                            order.get("type")
                            or order.get("order_type")
                            or context.get("order_type")
                            or ""
                        ),
                        order_kind=order_kind,
                    )
                    order_index_registrations += 1
                    order_index_registrations_by_symbol[symbol_key] = (
                        order_index_registrations_by_symbol.get(
                            symbol_key, 0) + 1
                    )
                except Exception as exc:
                    _note_unresolved(
                        symbol_key,
                        f"order_index_registration_failed:{type(exc).__name__}",
                    )

        symbols_reconstructed = 0
        unresolved_symbols = 0
        for symbol_key in sorted(set(resolved_orders.keys()) | set(unresolved_reasons.keys())):
            duplicate_for_symbol = duplicate_roles.get(symbol_key, set())
            sl_order_id = None
            tp_order_id = None
            manage_truth_source = self._manage_truth_source_for(symbol_key)
            if symbol_key in resolved_orders:
                if "SL" not in duplicate_for_symbol:
                    sl_order_id = resolved_orders[symbol_key].get("SL")
                if "TP" not in duplicate_for_symbol:
                    tp_order_id = resolved_orders[symbol_key].get("TP")

            if sl_order_id or tp_order_id:
                self._set_symbol_brackets_snapshot(
                    symbol_key,
                    sl_order_id=sl_order_id,
                    tp_order_id=tp_order_id,
                    truth_source=TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN,
                )
                manage_flow = self.manage_flows.get(symbol_key)
                if manage_flow is not None and self._manage_state_value(manage_flow) not in {
                    "",
                    "FLAT",
                }:
                    manage_flow.set_bracket_ids(
                        sl_order_id=sl_order_id,
                        tp_order_id=tp_order_id,
                    )
                symbols_reconstructed += 1
                self._append_restart_truth_record(
                    event_type="EXECUTION_RESTART_RUNTIME_TRUTH_RECONSTRUCTED",
                    symbol=symbol_key,
                    sl_order_id=sl_order_id,
                    tp_order_id=tp_order_id,
                    order_index_registrations=order_index_registrations_by_symbol.get(
                        symbol_key,
                        0,
                    ),
                    unresolved_reasons=unresolved_reasons.get(symbol_key),
                )
                runtime_truth_records.append(
                    {
                        "symbol": symbol_key,
                        "status": "reconstructed",
                        "sl_order_id": sl_order_id,
                        "tp_order_id": tp_order_id,
                        "bracket_truth_source": self._symbol_bracket_truth_source_for(symbol_key),
                        "manage_truth_source": manage_truth_source,
                        "order_index_registrations": order_index_registrations_by_symbol.get(
                            symbol_key,
                            0,
                        ),
                        "unresolved_reasons": list(unresolved_reasons.get(symbol_key) or []),
                    }
                )
            elif unresolved_reasons.get(symbol_key):
                self._clear_symbol_brackets(symbol_key)
                self._append_restart_truth_record(
                    event_type="EXECUTION_RESTART_RUNTIME_TRUTH_UNRESOLVED",
                    symbol=symbol_key,
                    sl_order_id=None,
                    tp_order_id=None,
                    order_index_registrations=0,
                    unresolved_reasons=unresolved_reasons.get(symbol_key),
                )
                runtime_truth_records.append(
                    {
                        "symbol": symbol_key,
                        "status": "unresolved",
                        "sl_order_id": None,
                        "tp_order_id": None,
                        "bracket_truth_source": self._symbol_bracket_truth_source_for(symbol_key),
                        "manage_truth_source": manage_truth_source,
                        "order_index_registrations": 0,
                        "unresolved_reasons": list(unresolved_reasons.get(symbol_key) or []),
                    }
                )

            if unresolved_reasons.get(symbol_key):
                unresolved_symbols += 1

        summary = {
            "symbols_reconstructed": symbols_reconstructed,
            "order_index_registrations": order_index_registrations,
            "unresolved_symbols": unresolved_symbols,
        }
        self._emit_observability_event(
            "RESTORE:EXECUTION_POSITION_RUNTIME_TRUTH_RECONCILED",
            summary,
        )
        return {
            "summary": summary,
            "records": runtime_truth_records,
        }

    def _restore_artifact_has_state(self) -> bool:
        return any(self._build_execution_restore_artifact_records())

    def _persist_restore_artifact_snapshot(
        self,
        *,
        trigger: str,
        allow_empty: bool,
    ) -> bool:
        writer = self._restore_artifact_writer
        if writer is None:
            return False
        return writer.persist(self, trigger=trigger, allow_empty=allow_empty)

    def _append_startup_truth_artifact_record(
        self,
        *,
        trigger: str,
        failure_reason: Optional[str],
        input_snapshot: Dict[str, Any],
        symbols_considered: List[str],
        fresh_open_order_count: int,
        runtime_truth: Dict[str, Any],
        restore_artifact_write_attempted: bool,
        restore_artifact_write_succeeded: bool,
        restore_authoritative: Optional[ExecutionPositionRestoreAuthoritativeStatus] = None,
        restore_dark_read: Optional[ExecutionPositionRestoreDarkReadStatus] = None,
        execution_truth_cache: Optional[ExecutionPositionStartupTruthCacheStatus] = None,
    ) -> bool:
        writer = self._startup_truth_artifact_writer
        if writer is None:
            return False

        runtime_summary = runtime_truth.get(
            "summary") if isinstance(runtime_truth, dict) else {}
        runtime_records = runtime_truth.get(
            "records") if isinstance(runtime_truth, dict) else []
        unknown_truth_records = self._build_startup_truth_unknown_records(
            symbols_considered=symbols_considered,
            input_snapshot=input_snapshot,
            runtime_truth_records=runtime_records,
            restore_authoritative=restore_authoritative,
        )
        restore_writer = self._restore_artifact_writer
        restore_artifact_path = restore_writer.storage_path if restore_writer is not None else None

        try:
            record = ExecutionPositionStartupTruthRecord(
                schema_version=STARTUP_TRUTH_ARTIFACT_SCHEMA_VERSION,
                artifact_type=STARTUP_TRUTH_ARTIFACT_TYPE,
                ts_ms=get_clock().now_ms(),
                writer_component=STARTUP_TRUTH_ARTIFACT_WRITER_COMPONENT,
                startup_trigger=trigger,
                failure_reason=str(failure_reason or "").strip() or None,
                reconcile_sequence=[
                    "authoritative_restore_read",
                    "collect_startup_symbols",
                    "guardian_link_existing_from_rest",
                    "guardian_cleanup_orphans",
                    "fetch_post_cleanup_open_orders",
                    "reconstruct_runtime_bracket_truth",
                    "dark_read_compare",
                    "persist_restore_artifact_snapshot",
                ],
                symbols_considered=sorted(
                    {
                        str(symbol).strip().upper()
                        for symbol in symbols_considered
                        if str(symbol).strip()
                    }
                ),
                fresh_open_order_count=int(fresh_open_order_count),
                input_snapshot=ExecutionPositionStartupTruthInputSnapshot(
                    positions_fetch_succeeded=bool(
                        input_snapshot.get("positions_fetch_succeeded", False)
                    ),
                    pre_cleanup_open_orders_fetch_succeeded=bool(
                        input_snapshot.get(
                            "pre_cleanup_open_orders_fetch_succeeded", False)
                    ),
                    post_cleanup_open_orders_fetch_succeeded=bool(
                        input_snapshot.get(
                            "post_cleanup_open_orders_fetch_succeeded", False)
                    ),
                    guardian_link_existing_invoked=bool(
                        input_snapshot.get(
                            "guardian_link_existing_invoked", False)
                    ),
                    guardian_cleanup_invoked=bool(
                        input_snapshot.get("guardian_cleanup_invoked", False)
                    ),
                    position_symbols_observed=sorted(
                        {
                            str(symbol).strip().upper()
                            for symbol in input_snapshot.get("position_symbols_observed", [])
                            if str(symbol).strip()
                        }
                    ),
                    pre_cleanup_order_symbols_observed=sorted(
                        {
                            str(symbol).strip().upper()
                            for symbol in input_snapshot.get(
                                "pre_cleanup_order_symbols_observed",
                                [],
                            )
                            if str(symbol).strip()
                        }
                    ),
                    guardian_symbols_observed=sorted(
                        {
                            str(symbol).strip().upper()
                            for symbol in input_snapshot.get("guardian_symbols_observed", [])
                            if str(symbol).strip()
                        }
                    ),
                    fresh_order_symbols_observed=sorted(
                        {
                            str(symbol).strip().upper()
                            for symbol in input_snapshot.get("fresh_order_symbols_observed", [])
                            if str(symbol).strip()
                        }
                    ),
                ),
                runtime_truth_summary=ExecutionPositionStartupTruthSummary(
                    symbols_reconstructed=int(
                        runtime_summary.get("symbols_reconstructed", 0)
                    ),
                    order_index_registrations=int(
                        runtime_summary.get("order_index_registrations", 0)
                    ),
                    unresolved_symbols=int(
                        runtime_summary.get("unresolved_symbols", 0)
                    ),
                ),
                runtime_truth_records=[
                    ExecutionPositionStartupTruthSymbolRecord(
                        symbol=str(item.get("symbol") or "").strip().upper(),
                        status=(
                            "unresolved"
                            if str(item.get("status") or "").strip().lower()
                            == "unresolved"
                            else "reconstructed"
                        ),
                        sl_order_id=str(item.get("sl_order_id")
                                        or "").strip() or None,
                        tp_order_id=str(item.get("tp_order_id")
                                        or "").strip() or None,
                        bracket_truth_source=str(
                            item.get(
                                "bracket_truth_source") or TRUTH_SOURCE_UNKNOWN
                        ).strip()
                        or TRUTH_SOURCE_UNKNOWN,
                        manage_truth_source=str(
                            item.get(
                                "manage_truth_source") or TRUTH_SOURCE_UNKNOWN
                        ).strip()
                        or TRUTH_SOURCE_UNKNOWN,
                        order_index_registrations=int(
                            item.get("order_index_registrations", 0)
                        ),
                        unresolved_reasons=[
                            str(reason)
                            for reason in item.get("unresolved_reasons", [])
                            if str(reason).strip()
                        ],
                    )
                    for item in runtime_records
                    if str(item.get("symbol") or "").strip()
                ],
                unknown_truth_records=unknown_truth_records,
                restore_artifact=ExecutionPositionStartupTruthRestoreArtifactStatus(
                    path=restore_artifact_path,
                    write_attempted=bool(restore_artifact_write_attempted),
                    write_succeeded=bool(restore_artifact_write_succeeded),
                ),
                restore_authoritative=(
                    restore_authoritative
                    or ExecutionPositionRestoreAuthoritativeStatus()
                ),
                restore_dark_read=restore_dark_read or ExecutionPositionRestoreDarkReadStatus(),
                execution_truth_cache=(
                    execution_truth_cache or self._execution_truth_cache_status()
                ),
            )
        except Exception as exc:
            self._emit_observability_event(
                "RESTORE:EXECUTION_POSITION_STARTUP_TRUTH_BUILD_FAILED",
                {
                    "startup_trigger": trigger,
                    "failure_reason": type(exc).__name__,
                },
            )
            return False

        return writer.append_record(record)

    def _build_startup_truth_unknown_records(
        self,
        *,
        symbols_considered: List[str],
        input_snapshot: Dict[str, Any],
        runtime_truth_records: List[Dict[str, Any]],
        restore_authoritative: Optional[ExecutionPositionRestoreAuthoritativeStatus],
    ) -> List[ExecutionPositionStartupTruthUnknownSymbolRecord]:
        status = restore_authoritative or ExecutionPositionRestoreAuthoritativeStatus()
        if status.artifact_state not in {"missing", "not_readable", "corrupt", "stale"}:
            return []

        artifact_reason = {
            "missing": "authoritative_artifact_missing",
            "not_readable": "authoritative_artifact_not_readable",
            "corrupt": "authoritative_artifact_corrupt",
            "stale": "authoritative_artifact_stale",
        }.get(status.artifact_state)
        if not artifact_reason:
            return []

        observed_input_map: Dict[str, Set[str]] = {}

        def _remember(symbols: List[str], source: str) -> None:
            for raw_symbol in symbols:
                symbol = str(raw_symbol or "").strip().upper()
                if not symbol:
                    continue
                observed_input_map.setdefault(symbol, set()).add(source)

        _remember(symbols_considered, "symbols_considered")
        _remember(
            list(input_snapshot.get("position_symbols_observed", [])),
            "position_symbols_observed",
        )
        _remember(
            list(input_snapshot.get("pre_cleanup_order_symbols_observed", [])),
            "pre_cleanup_order_symbols_observed",
        )
        _remember(
            list(input_snapshot.get("guardian_symbols_observed", [])),
            "guardian_symbols_observed",
        )
        _remember(
            list(input_snapshot.get("fresh_order_symbols_observed", [])),
            "fresh_order_symbols_observed",
        )

        authoritative_symbols = {
            str(item.symbol).strip().upper()
            for item in status.symbol_statuses
            if str(item.symbol).strip()
        }
        reconstructed_symbols = {
            str(item.get("symbol") or "").strip().upper()
            for item in runtime_truth_records
            if str(item.get("status") or "").strip().lower() == "reconstructed"
            and str(item.get("symbol") or "").strip()
        }
        portfolio_symbols = {
            str(symbol).strip().upper()
            for symbol in input_snapshot.get("position_symbols_observed", [])
            if str(symbol).strip()
        }
        positions_fetch_succeeded = bool(
            input_snapshot.get("positions_fetch_succeeded", False))

        unknown_rows: List[ExecutionPositionStartupTruthUnknownSymbolRecord] = []
        for symbol in sorted(observed_input_map):
            if symbol in authoritative_symbols or symbol in reconstructed_symbols:
                continue

            portfolio_presence = "unknown"
            if positions_fetch_succeeded:
                portfolio_presence = "present" if symbol in portfolio_symbols else "absent"

            reason_codes = [artifact_reason]
            if portfolio_presence == "present":
                reason_codes.append(
                    "portfolio_present_without_restored_lifecycle_truth")

            unknown_rows.append(
                ExecutionPositionStartupTruthUnknownSymbolRecord(
                    symbol=symbol,
                    authoritative_artifact_state=status.artifact_state,
                    portfolio_presence=portfolio_presence,
                    reconstructed_exact_truth_present=False,
                    observed_inputs=sorted(
                        observed_input_map.get(symbol) or []),
                    reason_codes=reason_codes,
                )
            )

        return unknown_rows

    def _execution_truth_cache_status(self) -> ExecutionPositionStartupTruthCacheStatus:
        hardening = get_execution_truth_hardening(self)
        if hardening is None:
            return ExecutionPositionStartupTruthCacheStatus()
        try:
            return ExecutionPositionStartupTruthCacheStatus.model_validate(
                hardening.cache_status_snapshot()
            )
        except Exception:
            return ExecutionPositionStartupTruthCacheStatus()

    def _run_restore_artifact_dark_read_comparison(
        self,
        *,
        now_ms: Optional[int] = None,
    ) -> ExecutionPositionRestoreDarkReadStatus:
        reader = self._restore_artifact_dark_reader
        if reader is None:
            return ExecutionPositionRestoreDarkReadStatus()

        heuristic_records = self._build_execution_restore_artifact_records()
        result = reader.compare_against(heuristic_records, now_ms=now_ms)
        if not result.attempted:
            return result

        if result.artifact_state == "missing":
            LOG.info(
                "Execution restore dark-read: artifact missing at startup (%s)",
                result.artifact_path,
            )
        elif result.artifact_state == "corrupt":
            LOG.warning(
                "Execution restore dark-read: artifact corrupt at startup (%s)",
                result.artifact_path,
            )
        elif result.artifact_state == "not_readable":
            LOG.warning(
                "Execution restore dark-read: artifact not readable at startup (%s)",
                result.artifact_path,
            )
        elif result.artifact_state == "stale":
            LOG.warning(
                "Execution restore dark-read: artifact stale at startup (%s, age_ms=%s, stale_after_ms=%s)",
                result.artifact_path,
                result.artifact_age_ms,
                result.stale_after_ms,
            )

        if result.comparison_outcome == "mismatch":
            LOG.warning(
                "Execution restore dark-read mismatch: path=%s artifact_state=%s exact_field_mismatch=%s heuristic_only=%s artifact_only=%s unknown_vs_guessed=%s mixed_certainty=%s",
                result.artifact_path,
                result.artifact_state,
                result.mismatch_counts.exact_field_mismatch,
                result.mismatch_counts.heuristic_only_field,
                result.mismatch_counts.artifact_only_field,
                result.mismatch_counts.unknown_vs_guessed_mismatch,
                result.mixed_certainty,
            )
        elif result.comparison_outcome == "exact_match":
            LOG.info(
                "Execution restore dark-read exact match: path=%s artifact_state=%s record_count=%s",
                result.artifact_path,
                result.artifact_state,
                result.artifact_record_count,
            )
        return result

    def _run_restore_artifact_authoritative_read(
        self,
        *,
        now_ms: Optional[int] = None,
    ) -> ExecutionPositionRestoreAuthoritativeStatus:
        mode = self._restore_artifact_mode()
        status = ExecutionPositionRestoreAuthoritativeStatus(
            mode=mode.value if mode is not None else "off",
            attempted=True,
        )
        if mode != ExecutionPositionRestoreArtifactMode.AUTHORITATIVE:
            status.attempted = False
            return status

        try:
            reader_cfg = self.config.domains.execution_position.restore_artifact
        except Exception:
            reader_cfg = None
        if not isinstance(reader_cfg, ExecutionPositionRestoreArtifactConfig):
            status.artifact_state = "not_attempted"
            status.attempted = False
            return status

        artifact_path = str(reader_cfg.storage_path)
        status.artifact_path = artifact_path
        status.stale_after_ms = reader_cfg.dark_read_max_artifact_age_ms
        path = Path(artifact_path)

        if not path.exists():
            status.artifact_state = "missing"
            LOG.warning(
                "Execution restore authoritative read: artifact missing at startup (%s)",
                artifact_path,
            )
            return status

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            status.artifact_state = "not_readable"
            LOG.warning(
                "Execution restore authoritative read: artifact not readable at startup (%s): %s",
                artifact_path,
                exc,
            )
            return status

        if not raw.strip():
            status.artifact_state = "corrupt"
            LOG.warning(
                "Execution restore authoritative read: artifact empty/corrupt at startup (%s)",
                artifact_path,
            )
            return status

        try:
            payload = json.loads(raw)
            envelope = ExecutionPositionRestoreEnvelope.model_validate(payload)
        except Exception as exc:
            status.artifact_state = "corrupt"
            LOG.warning(
                "Execution restore authoritative read: artifact corrupt at startup (%s): %s",
                artifact_path,
                exc,
            )
            return status

        status.parse_success = True
        status.artifact_generated_at_ms = envelope.generated_at_ms
        status.artifact_record_count = len(envelope.active_lifecycles)
        effective_now_ms = int(
            now_ms if now_ms is not None else get_clock().now_ms())
        if envelope.generated_at_ms <= effective_now_ms:
            status.artifact_age_ms = effective_now_ms - envelope.generated_at_ms
        if (
            status.stale_after_ms is not None
            and status.artifact_age_ms is not None
            and status.artifact_age_ms > status.stale_after_ms
        ):
            status.artifact_state = "stale"
            LOG.warning(
                "Execution restore authoritative read: artifact stale at startup (%s, age_ms=%s, stale_after_ms=%s)",
                artifact_path,
                status.artifact_age_ms,
                status.stale_after_ms,
            )
            return status

        status.artifact_state = "valid"
        status.mixed_certainty_symbols = sorted(
            {
                record.symbol
                for record in envelope.active_lifecycles
                if any(
                    value == RESTORE_PHASE_UNKNOWN
                    for value in (
                        str(record.manage_phase).strip().upper(),
                        str(record.close_phase).strip().upper(),
                        str(record.bracket_state).strip().upper(),
                    )
                )
                and len(
                    {
                        str(record.manage_phase).strip().upper(),
                        str(record.close_phase).strip().upper(),
                        str(record.bracket_state).strip().upper(),
                    }
                    - {RESTORE_PHASE_UNKNOWN}
                )
                > 0
            }
        )
        status.mixed_certainty = bool(status.mixed_certainty_symbols)

        for record in envelope.active_lifecycles:
            symbol_status = self._apply_authoritative_restore_record(record)
            status.symbol_statuses.append(symbol_status)
            status.applied_record_count += 1
            for field_name in (
                "manage_phase_restore_status",
                "close_phase_restore_status",
                "bracket_state_restore_status",
            ):
                if getattr(symbol_status, field_name) == "exact":
                    status.restored_exact_field_count += 1
                else:
                    status.restored_unknown_field_count += 1

        LOG.info(
            "Execution restore authoritative read applied: path=%s records=%s exact_fields=%s unknown_fields=%s mixed_certainty=%s",
            artifact_path,
            status.applied_record_count,
            status.restored_exact_field_count,
            status.restored_unknown_field_count,
            status.mixed_certainty,
        )
        return status

    def _apply_authoritative_restore_record(
        self,
        record: ExecutionPositionRestoreLifecycleRecord,
    ) -> ExecutionPositionRestoreAuthoritativeSymbolStatus:
        symbol_key = str(record.symbol or "").strip().upper()
        symbol_status = ExecutionPositionRestoreAuthoritativeSymbolStatus(
            symbol=symbol_key,
            manage_phase_value=RESTORE_PHASE_UNKNOWN,
            close_phase_value=RESTORE_PHASE_UNKNOWN,
            bracket_state_value=BRACKET_STATE_UNKNOWN,
            live_reconcile_required=bool(record.live_reconcile_required),
            deferred_entry_order_id=(
                str(record.deferred_bracket_ref.entry_order_id).strip()
                if record.deferred_bracket_ref is not None
                else None
            ),
        )

        manage_phase = str(record.manage_phase or "").strip(
        ).upper() or RESTORE_PHASE_UNKNOWN
        if manage_phase == RESTORE_PHASE_UNKNOWN:
            symbol_status.manage_phase_value = RESTORE_PHASE_UNKNOWN
            symbol_status.manage_phase_restore_status = "unknown"
        else:
            try:
                manage_state = ManageState(manage_phase)
            except Exception:
                symbol_status.unresolved_reasons.append(
                    f"unsupported_manage_phase:{manage_phase}"
                )
            else:
                manage_flow = self._get_or_create_manage_flow(symbol_key)
                manage_flow.state = manage_state
                manage_flow.symbol = symbol_key
                self._set_manage_truth_source(
                    symbol_key, TRUTH_SOURCE_RESTORE_ARTIFACT)
                symbol_status.manage_phase_value = manage_state.value
                symbol_status.manage_phase_restore_status = "exact"

        close_phase = str(record.close_phase or "").strip(
        ).upper() or RESTORE_PHASE_UNKNOWN
        if close_phase == RESTORE_PHASE_UNKNOWN:
            symbol_status.close_phase_value = RESTORE_PHASE_UNKNOWN
            symbol_status.close_phase_restore_status = "unknown"
        else:
            try:
                close_state = CloseState(close_phase)
            except Exception:
                symbol_status.unresolved_reasons.append(
                    f"unsupported_close_phase:{close_phase}"
                )
            else:
                close_flow = self._get_or_create_close_flow(symbol_key)
                close_flow.state = close_state
                close_flow.position_active = close_state not in {
                    CloseState.FLAT,
                    CloseState.DONE,
                }
                symbol_status.close_phase_value = close_state.value
                symbol_status.close_phase_restore_status = "exact"

        bracket_state = str(record.bracket_state or "").strip(
        ).upper() or BRACKET_STATE_UNKNOWN
        self._clear_symbol_brackets(symbol_key)
        if bracket_state == BRACKET_STATE_DEFERRED_PENDING_WAL:
            deferred_entry_order_id = (
                str(record.deferred_bracket_ref.entry_order_id).strip()
                if record.deferred_bracket_ref is not None
                else ""
            )
            pending = self._pending_brackets.get(deferred_entry_order_id)
            pending_symbol = (
                str(pending.get("symbol") or "").strip().upper()
                if isinstance(pending, dict)
                else ""
            )
            if deferred_entry_order_id and pending_symbol == symbol_key:
                symbol_status.bracket_state_value = BRACKET_STATE_DEFERRED_PENDING_WAL
                symbol_status.bracket_state_restore_status = "exact"
            else:
                symbol_status.bracket_state_value = BRACKET_STATE_UNKNOWN
                symbol_status.bracket_state_restore_status = "unknown"
                symbol_status.unresolved_reasons.append(
                    "deferred_pending_missing_in_wal"
                )
        elif bracket_state == BRACKET_STATE_UNKNOWN:
            symbol_status.bracket_state_value = BRACKET_STATE_UNKNOWN
            symbol_status.bracket_state_restore_status = "unknown"
        elif bracket_state in {BRACKET_STATE_LINKED_ACTIVE, BRACKET_STATE_PARTIAL_LINKAGE}:
            symbol_status.bracket_state_value = BRACKET_STATE_UNKNOWN
            symbol_status.bracket_state_restore_status = "unknown"
            symbol_status.unresolved_reasons.append(
                "bracket_lineage_not_restorable_from_envelope"
            )
        else:
            symbol_status.bracket_state_value = BRACKET_STATE_UNKNOWN
            symbol_status.bracket_state_restore_status = "unknown"
            symbol_status.unresolved_reasons.append(
                f"unsupported_bracket_state:{bracket_state}"
            )

        return symbol_status

    def _finalize_restore_authoritative_status(
        self,
        status: ExecutionPositionRestoreAuthoritativeStatus,
        *,
        positions_fetch_succeeded: bool,
        position_symbols: Set[str],
    ) -> ExecutionPositionRestoreAuthoritativeStatus:
        if not status.attempted or not status.symbol_statuses:
            return status

        current_records = {
            record.symbol: record
            for record in self._build_execution_restore_artifact_records()
        }
        for symbol_status in status.symbol_statuses:
            symbol_key = str(symbol_status.symbol or "").strip().upper()
            if positions_fetch_succeeded:
                symbol_status.portfolio_presence = (
                    "present" if symbol_key in position_symbols else "absent"
                )
            if (
                symbol_status.portfolio_presence == "absent"
                and (
                    symbol_status.manage_phase_restore_status == "exact"
                    or symbol_status.close_phase_restore_status == "exact"
                    or symbol_status.bracket_state_restore_status == "exact"
                )
            ):
                symbol_status.unresolved_reasons.append(
                    "portfolio_symbol_absent")
            if (
                symbol_status.portfolio_presence == "present"
                and symbol_status.manage_phase_restore_status == "unknown"
                and symbol_status.close_phase_restore_status == "unknown"
                and symbol_status.bracket_state_restore_status == "unknown"
            ):
                symbol_status.unresolved_reasons.append(
                    "portfolio_present_without_restored_lifecycle_truth"
                )

            current_record = current_records.get(symbol_key)
            if current_record is None:
                continue

            if symbol_status.manage_phase_value != str(current_record.manage_phase):
                symbol_status.runtime_override_fields.append("manage_phase")
            if symbol_status.close_phase_value != str(current_record.close_phase):
                symbol_status.runtime_override_fields.append("close_phase")
            if symbol_status.bracket_state_value != str(current_record.bracket_state):
                symbol_status.runtime_override_fields.append("bracket_state")

        return status

    def _trade_lifecycle_log_path(self) -> str:
        try:
            candidate = self.config.domains.execution_position.position_policy_sidecar
        except Exception:
            candidate = None

        if isinstance(candidate, PositionPolicySidecarConfig):
            try:
                if candidate.logging.write_trade_lifecycle_jsonl:
                    return str(candidate.logging.trade_lifecycle_log_path)
            except Exception:
                pass
        return "logs/trade_lifecycle.jsonl"

    def _portfolio_event_trace_id(self, event: Message) -> str:
        payload = getattr(event, "pld", None) or {}
        rid = getattr(event, "rid", None) or payload.get("rid") or "-"
        positions_last_ts_ms = payload.get("positions_last_ts_ms")
        event_ts_ms = None
        for key in ("event_ts_ms", "ts_ms", "timestamp_ms", "timestamp", "ts"):
            value = payload.get(key)
            if value not in (None, "", "None"):
                event_ts_ms = value
                break
        return (
            f"{rid}|"
            f"{positions_last_ts_ms if positions_last_ts_ms not in (None, '', 'None') else '-'}|"
            f"{event_ts_ms if event_ts_ms not in (None, '', 'None') else '-'}"
        )

    def _record_portfolio_event_trace_stage(
        self,
        event: Message,
        stage: str,
        *,
        error: Optional[BaseException] = None,
    ) -> str:
        payload = getattr(event, "pld", None) or {}
        trace_id = self._portfolio_event_trace_id(event)

        symbols: List[str] = []
        positions = payload.get("positions")
        if isinstance(positions, list):
            for position in positions:
                if not isinstance(position, dict):
                    continue
                symbol = str(position.get("symbol") or "").strip().upper()
                if symbol:
                    symbols.append(symbol)
        symbol_summary = ",".join(sorted(set(symbols)))

        if trace_id not in self._portfolio_event_stage_traces:
            self._portfolio_event_stage_traces[trace_id] = {
                "trace_id": trace_id,
                "rid": getattr(event, "rid", None) or payload.get("rid"),
                "positions_last_ts_ms": payload.get("positions_last_ts_ms"),
                "event_ts_ms": payload.get("event_ts_ms")
                or payload.get("ts_ms")
                or payload.get("timestamp_ms")
                or payload.get("timestamp")
                or payload.get("ts"),
                "symbol_summary": symbol_summary,
                "latest_portfolio_state_set": False,
                "expire_stale_entered": False,
                "expire_stale_failed": False,
                "sidecar_portfolio_refresh_reached": False,
                "sidecar_portfolio_refresh_completed": False,
            }
            self._portfolio_event_stage_trace_order.append(trace_id)
            if len(self._portfolio_event_stage_trace_order) > self._portfolio_event_stage_trace_limit:
                evicted_trace_id = self._portfolio_event_stage_trace_order.pop(
                    0)
                self._portfolio_event_stage_traces.pop(evicted_trace_id, None)

        entry = self._portfolio_event_stage_traces[trace_id]
        entry[stage] = True
        entry["last_stage"] = stage
        if error is not None:
            entry["error_type"] = type(error).__name__
            entry["error_message"] = str(error)
        return trace_id

    def _portfolio_event_trace_snapshot(self) -> List[Dict[str, Any]]:
        return [
            dict(self._portfolio_event_stage_traces[trace_id])
            for trace_id in self._portfolio_event_stage_trace_order
            if trace_id in self._portfolio_event_stage_traces
        ]

    def _has_active_lifecycle_for_symbol(self, symbol: str) -> bool:
        manage_flow = self.manage_flows.get(str(symbol or "").upper())
        if manage_flow is None:
            return False
        try:
            return bool(manage_flow.has_active_lifecycle())
        except Exception:
            return False

    def _strategy_assignments_for_symbol(self, symbol: str) -> List[str]:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return []
        try:
            registry = getattr(self.config, "strategies_registry", None)
            assignments = getattr(registry, "assignments", None)
        except Exception:
            return []
        if not isinstance(assignments, dict):
            return []
        raw_assignments = assignments.get(symbol_key) or []
        if not isinstance(raw_assignments, list):
            return []
        result: List[str] = []
        for strategy_id in raw_assignments:
            normalized = str(strategy_id or "").strip()
            if normalized:
                result.append(normalized)
        return result

    def _strategy_profile_has_symbol(self, strategy_id: str, symbol: str) -> bool:
        strategy_key = str(strategy_id or "").strip()
        symbol_key = str(symbol or "").strip().upper()
        if not strategy_key or not symbol_key:
            return False
        try:
            strategies = getattr(self.config, "strategies", None)
            strategy_cfg = getattr(
                strategies, strategy_key, None) if strategies is not None else None
            assets = getattr(strategy_cfg, "assets",
                             None) if strategy_cfg is not None else None
        except Exception:
            return False
        return isinstance(assets, dict) and symbol_key in assets

    def _resolve_bracket_strategy_owner(
        self,
        *,
        symbol: str,
        explicit_strategy_id: Optional[str] = None,
        explicit_source: str = "",
        allow_registry_fallback: bool = True,
    ) -> Dict[str, Any]:
        symbol_key = str(symbol or "").strip().upper()
        assignments = self._strategy_assignments_for_symbol(symbol_key)
        explicit = str(explicit_strategy_id or "").strip()
        if explicit.lower() == "none":
            explicit = ""

        explicit_invalid_detail = ""
        if explicit:
            assigned_ok = (not assignments) or (explicit in assignments)
            profile_ok = self._strategy_profile_has_symbol(
                explicit, symbol_key)
            if assigned_ok and profile_ok:
                return {
                    "strategy_id": explicit,
                    "strategy_source": explicit_source or "explicit",
                    "owner_status": "resolved",
                    "detail": "",
                    "assigned_strategies": assignments,
                }
            if not assigned_ok:
                explicit_invalid_detail = f"explicit_strategy_not_assigned:{explicit}"
            elif not profile_ok:
                explicit_invalid_detail = f"explicit_strategy_profile_missing:{explicit}"
            if not allow_registry_fallback:
                return {
                    "strategy_id": None,
                    "strategy_source": explicit_source or "explicit",
                    "owner_status": "unresolved",
                    "detail": explicit_invalid_detail,
                    "assigned_strategies": assignments,
                }

        if allow_registry_fallback:
            if len(assignments) == 1:
                candidate = assignments[0]
                if self._strategy_profile_has_symbol(candidate, symbol_key):
                    detail = explicit_invalid_detail
                    if detail:
                        detail = f"{detail};fallback_to_registry_assignment:{candidate}"
                    return {
                        "strategy_id": candidate,
                        "strategy_source": "registry_assignment",
                        "owner_status": "resolved",
                        "detail": detail,
                        "assigned_strategies": assignments,
                    }
                detail = f"assigned_strategy_profile_missing:{candidate}"
                if explicit_invalid_detail:
                    detail = f"{explicit_invalid_detail};{detail}"
                return {
                    "strategy_id": None,
                    "strategy_source": "registry_assignment",
                    "owner_status": "profile_missing",
                    "detail": detail,
                    "assigned_strategies": assignments,
                }
            if len(assignments) > 1:
                detail = "multiple_strategy_assignments"
                if explicit_invalid_detail:
                    detail = f"{explicit_invalid_detail};{detail}"
                return {
                    "strategy_id": None,
                    "strategy_source": explicit_source or "registry_assignment",
                    "owner_status": "ambiguous",
                    "detail": detail,
                    "assigned_strategies": assignments,
                }

        detail = explicit_invalid_detail or "strategy_owner_unresolved"
        return {
            "strategy_id": None,
            "strategy_source": explicit_source or "unresolved",
            "owner_status": "missing",
            "detail": detail,
            "assigned_strategies": assignments,
        }

    def _resolve_strategy_owner_from_decision(
        self,
        *,
        symbol: str,
        decision: Message,
    ) -> Dict[str, Any]:
        payload = dict(getattr(decision, "pld", None) or {})
        metadata = payload.get("metadata") if isinstance(
            payload.get("metadata"), dict) else {}
        candidates = (
            (metadata.get("strategy_id"), "decision_metadata"),
            (payload.get("strategy_id"), "decision_strategy_id"),
            (payload.get("strategy"), "decision_strategy"),
        )
        for strategy_id, source in candidates:
            normalized = str(strategy_id or "").strip()
            if normalized and normalized.lower() != "none":
                return self._resolve_bracket_strategy_owner(
                    symbol=symbol,
                    explicit_strategy_id=normalized,
                    explicit_source=source,
                    allow_registry_fallback=True,
                )
        return self._resolve_bracket_strategy_owner(
            symbol=symbol,
            explicit_strategy_id=None,
            explicit_source="",
            allow_registry_fallback=True,
        )

    def _resolve_strategy_owner_for_recovery(self, *, symbol: str) -> Dict[str, Any]:
        symbol_key = str(symbol or "").strip().upper()
        cached_owner = self._resolve_bracket_strategy_owner(
            symbol=symbol_key,
            explicit_strategy_id=self._open_strategy_by_symbol.get(symbol_key),
            explicit_source="runtime_cache",
            allow_registry_fallback=True,
        )
        if cached_owner.get("owner_status") == "resolved":
            return cached_owner

        remembered = dict(self._bracket_owner_by_symbol.get(symbol_key) or {})
        remembered_strategy_id = str(
            remembered.get("strategy_id") or "").strip()
        if remembered_strategy_id:
            remembered_owner = self._resolve_bracket_strategy_owner(
                symbol=symbol_key,
                explicit_strategy_id=remembered_strategy_id,
                explicit_source="bracket_owner_cache",
                allow_registry_fallback=True,
            )
            if remembered_owner.get("owner_status") == "resolved":
                return remembered_owner
            remembered_detail = str(
                remembered_owner.get("detail") or "").strip()
            cached_detail = str(cached_owner.get("detail") or "").strip()
            if cached_detail and remembered_detail:
                cached_owner["detail"] = f"{cached_detail};{remembered_detail}"
            elif remembered_detail:
                cached_owner["detail"] = remembered_detail
        return cached_owner

    def _remember_bracket_owner(
        self,
        *,
        symbol: str,
        strategy_id: Optional[str],
        strategy_source: Optional[str],
        owner_status: str,
        placement_path: str,
        detail: Optional[str] = None,
        assigned_strategies: Optional[List[str]] = None,
        rid: Optional[str] = None,
        corr_id: Optional[str] = None,
        entry_order_id: Optional[str] = None,
        entry_client_order_id: Optional[str] = None,
        lifecycle_active: Optional[bool] = None,
    ) -> Dict[str, Any]:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return {}
        current = dict(self._bracket_owner_by_symbol.get(symbol_key) or {})
        current["symbol"] = symbol_key
        current["updated_ts_ms"] = get_clock().now_ms()
        strategy_value = str(strategy_id or "").strip()
        if strategy_value and strategy_value.lower() != "none":
            current["strategy_id"] = strategy_value
        if strategy_source:
            current["strategy_source"] = str(strategy_source)
        if owner_status:
            current["owner_status"] = str(owner_status)
        if detail:
            current["detail"] = str(detail)
        if assigned_strategies is not None:
            current["assigned_strategies"] = [
                str(item) for item in assigned_strategies if str(item or "").strip()
            ]
        current["placement_path"] = str(placement_path)
        if rid:
            current["rid"] = str(rid)
        if corr_id:
            current["corr_id"] = str(corr_id)
        if entry_order_id:
            current["entry_order_id"] = str(entry_order_id)
        if entry_client_order_id:
            current["entry_client_order_id"] = str(entry_client_order_id)
        if lifecycle_active is not None:
            current["lifecycle_active"] = bool(lifecycle_active)
        self._bracket_owner_by_symbol[symbol_key] = current
        return current

    def _append_bracket_ownership_record(
        self,
        *,
        event_type: str,
        symbol: str,
        placement_path: str,
        strategy_id: Optional[str],
        strategy_source: Optional[str],
        owner_status: str,
        detail: Optional[str] = None,
        assigned_strategies: Optional[List[str]] = None,
        rid: Optional[str] = None,
        corr_id: Optional[str] = None,
        entry_order_id: Optional[str] = None,
        entry_client_order_id: Optional[str] = None,
        sl_order_id: Optional[str] = None,
        tp_order_id: Optional[str] = None,
        lifecycle_active: Optional[bool] = None,
    ) -> None:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return

        fingerprint = (
            str(event_type),
            str(placement_path),
            str(strategy_id or ""),
            str(strategy_source or ""),
            str(owner_status or ""),
            str(detail or ""),
            str(entry_order_id or ""),
            str(entry_client_order_id or ""),
            str(sl_order_id or ""),
            str(tp_order_id or ""),
            lifecycle_active,
        )
        current = dict(self._bracket_owner_by_symbol.get(symbol_key) or {})
        if current.get("last_record_fingerprint") == fingerprint:
            return
        current["last_record_fingerprint"] = fingerprint
        self._bracket_owner_by_symbol[symbol_key] = current

        record = {
            "record_kind": EXECUTION_BRACKET_OWNERSHIP_RECORD_KIND,
            "event_type": event_type,
            "ts_ms": get_clock().now_ms(),
            "symbol": symbol_key,
            "placement_path": placement_path,
            "recovery_only": placement_path == "recovery",
            "strategy_id": strategy_id,
            "strategy_source": strategy_source,
            "owner_status": owner_status,
            "owner_detail": detail,
            "assigned_strategies": assigned_strategies,
            "rid": rid,
            "corr_id": corr_id,
            "entry_order_id": entry_order_id,
            "entry_client_order_id": entry_client_order_id,
            "sl_order_id": sl_order_id,
            "tp_order_id": tp_order_id,
            "lifecycle_active": lifecycle_active,
        }
        filtered = {key: value for key,
                    value in record.items() if value is not None}
        append_trade_lifecycle_record(
            filtered,
            log_file=self._trade_lifecycle_log_path(),
        )
        self._emit_observability_event(event_type, filtered)
        self._persist_restore_artifact_snapshot(
            trigger=f"bracket_record:{event_type.lower()}",
            allow_empty=True,
        )

    def _remember_proven_terminal_close(
        self,
        payload: Dict[str, Any],
        *,
        trigger_event: str,
    ) -> None:
        symbol = str(payload.get("symbol") or "").strip().upper()
        close_reason = str(
            payload.get("close_reason") or payload.get("bracket_role") or ""
        ).strip().upper()
        tracked_bracket_order_id = str(
            payload.get("tracked_bracket_order_id") or ""
        ).strip()
        correlation_source = str(
            payload.get("terminal_correlation_source") or ""
        ).strip()

        if (
            not symbol
            or close_reason not in {"SL", "TP", "TP1", "TP2"}
            or not tracked_bracket_order_id
        ):
            return

        ts_ms_raw = payload.get("ts_ms") or payload.get(
            "event_ts_ms") or get_clock().now_ms()
        try:
            ts_ms = int(ts_ms_raw)
        except (TypeError, ValueError):
            ts_ms = get_clock().now_ms()

        self._proven_terminal_close_by_symbol[symbol] = {
            "symbol": symbol,
            "rid": str(payload.get("rid") or "").strip() or None,
            "close_reason": close_reason,
            "tracked_bracket_order_id": tracked_bracket_order_id,
            "parent_entry_order_id": str(
                payload.get("parent_entry_order_id") or ""
            ).strip() or None,
            "terminal_correlation_source": correlation_source or None,
            "source": "exchange_bracket_websocket",
            "trigger_event": trigger_event,
            "event_order_id": str(payload.get("orderId") or "").strip() or None,
            "client_order_id": str(
                payload.get("clientOrderId") or payload.get(
                    "client_order_id") or ""
            ).strip() or None,
            "ts_ms": ts_ms,
        }

    def get_recent_terminal_close_proof(
        self,
        symbol: str,
        *,
        max_age_ms: int = 300000,
    ) -> Optional[Dict[str, Any]]:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return None

        proof = self._proven_terminal_close_by_symbol.get(symbol_key)
        if not proof:
            return None

        try:
            age_ms = get_clock().now_ms() - int(proof.get("ts_ms") or 0)
        except (TypeError, ValueError):
            age_ms = max_age_ms + 1
        if age_ms > int(max_age_ms):
            self._proven_terminal_close_by_symbol.pop(symbol_key, None)
            return None
        return dict(proof)

    def _latest_portfolio_position_amt(self, symbol: str) -> Optional[str]:
        if not symbol:
            return None
        positions = (self._latest_portfolio_state or {}).get("positions") or []
        for position in positions:
            if str(position.get("symbol") or "").upper() != symbol.upper():
                continue
            value = position.get("net_position")
            if value is None:
                value = position.get("positionAmt")
            return None if value is None else str(value)
        return None

    def _build_canonical_fill_message(
        self,
        event: Message,
        *,
        fill_source: str,
    ) -> Optional[Message]:
        raw_payload = dict(event.pld or {})
        normalized = normalize_trade_executed_payload(
            raw_payload,
            fallback_rid=getattr(event, "rid", None),
            order_index=getattr(self.fsm, "order_index", None),
        )
        symbol = str(
            normalized.get("symbol") or raw_payload.get("symbol") or ""
        ).strip().upper()
        if not symbol:
            LOG.warning(
                "CANONICAL_FILL_INGRESS_SKIPPED: missing symbol for %s payload_keys=%s",
                fill_source,
                sorted(raw_payload.keys()),
            )
            return None

        payload = dict(raw_payload)
        payload.update(normalized)
        payload["symbol"] = symbol

        quantity = payload.get("qty") or payload.get(
            "quantity") or payload.get("last_fill_qty")
        if quantity is not None:
            quantity = str(quantity)
            payload["qty"] = quantity
            payload["quantity"] = quantity

        price = payload.get("price")
        if price is not None:
            payload["price"] = str(price)

        side = payload.get("side")
        if side is not None:
            payload["side"] = str(side).upper()

        order_id = payload.get("orderId") or payload.get("exchangeOrderId")
        if order_id is not None:
            payload["orderId"] = str(order_id)
            payload.setdefault("exchangeOrderId", str(order_id))

        client_order_id = payload.get(
            "clientOrderId") or payload.get("client_order_id")
        if client_order_id is not None:
            payload["clientOrderId"] = str(client_order_id)
            payload["client_order_id"] = str(client_order_id)

        rid = payload.get("rid") or getattr(event, "rid", None) or order_id
        if rid is not None:
            payload["rid"] = str(rid)

        now_ms = get_clock().now_ms()
        payload["fill_source"] = fill_source
        payload["canonical_fill_trace_id"] = (
            f"exec-fill:{symbol}:{fill_source}:{payload.get('rid') or order_id or now_ms}:{now_ms}"
        )
        payload.setdefault("event_ts_ms", payload.get(
            "ts_ms") or payload.get("ts") or now_ms)

        event_data = event.model_dump()
        event_data["op"] = "EVT"
        event_data["verb"] = "TRADE_EXECUTED"
        event_data["pld"] = payload
        if rid is not None:
            event_data["rid"] = str(rid)
        return Message(**event_data)

    @staticmethod
    def _missing_fill_activation_fields(payload: Dict[str, Any]) -> List[str]:
        missing: List[str] = []
        for field in ("symbol", "qty", "price", "side"):
            value = payload.get(field)
            if value in (None, "", "None"):
                missing.append(field)
        return missing

    def _append_execution_fill_ingress_record(
        self,
        *,
        canonical_msg: Message,
        trigger_event: str,
        fill_source: str,
        manage_flow_created: bool,
        manage_state_before: str,
        manage_state_after: str,
        result: Optional[Message],
        activation_skipped_reason: Optional[str] = None,
    ) -> None:
        payload = canonical_msg.pld or {}
        symbol = str(payload.get("symbol") or "")
        record = {
            "record_kind": EXECUTION_FILL_INGRESS_RECORD_KIND,
            "event_type": "EXECUTION_FILL_INGRESS",
            "ts_ms": get_clock().now_ms(),
            "trigger_event": trigger_event,
            "fill_source": fill_source,
            "canonical_fill_trace_id": payload.get("canonical_fill_trace_id"),
            "rid": payload.get("rid") or canonical_msg.rid,
            "symbol": symbol,
            "order_id": payload.get("orderId"),
            "client_order_id": payload.get("clientOrderId") or payload.get("client_order_id"),
            "manage_flow_created": manage_flow_created,
            "manage_state_before": manage_state_before or None,
            "manage_state_after": manage_state_after or None,
            "activation_skipped_reason": activation_skipped_reason,
            "result_op": getattr(result, "op", None),
            "result_verb": getattr(result, "verb", None),
            "portfolio_position_signature": (
                self._get_portfolio_position_signature(
                    symbol) if symbol else None
            ),
            "portfolio_positions_last_ts_ms": (
                (self._latest_portfolio_state or {}).get("positions_last_ts_ms")
            ),
            "portfolio_position_amt": self._latest_portfolio_position_amt(symbol),
        }
        append_trade_lifecycle_record(
            {key: value for key, value in record.items() if value is not None},
            log_file=self._trade_lifecycle_log_path(),
        )

    def _process_flow_result(self, result: Optional[Message]) -> None:
        if not result or result.op != "DEC":
            return

        if result.verb == "BATCH":
            batch_pld = result.pld or {}
            messages = batch_pld["messages"] if "messages" in batch_pld else []
            for msg_data in messages:
                if isinstance(msg_data, dict):
                    try:
                        sub_msg = Message(**msg_data)
                    except Exception as exc:
                        LOG.error(
                            "Failed to reconstruct BATCH message: %s",
                            exc,
                        )
                        continue
                else:
                    sub_msg = msg_data

                wal.append(sub_msg.model_dump())
                if (not self.shadow_mode and self.adapter) or (
                    sub_msg.verb in (
                        "CLOSE", "CLOSE_POSITION") and self.adapter
                ):
                    loop = self._get_async_loop()
                    if loop:
                        self._submit_async(
                            self._execute_decision(sub_msg), loop)
            return

        wal.append(result.model_dump())
        if (not self.shadow_mode and self.adapter) or (
            result.verb in ("CLOSE", "CLOSE_POSITION") and self.adapter
        ):
            loop = self._get_async_loop()
            LOG.info(
                " ExecPosFSM: DEC:%s ready to execute, loop=%s, shadow_mode=%s, adapter=%s",
                result.verb,
                loop is not None,
                self.shadow_mode,
                self.adapter is not None,
            )
            if loop:
                self._submit_async(self._execute_decision(result), loop)
            else:
                LOG.error(
                    " ExecPosFSM: No async loop available for DEC:%s! Order will NOT be executed!",
                    result.verb,
                )
        else:
            LOG.info(
                " ExecPosFSM: Skipping execution for DEC:%s (shadow_mode=%s, adapter=%s)",
                result.verb,
                self.shadow_mode,
                self.adapter is not None,
            )

    def _handle_canonical_fill_ingress(
        self,
        event: Message,
        *,
        fill_source: str,
        process_result: bool,
    ) -> Optional[Message]:
        canonical_msg = self._build_canonical_fill_message(
            event,
            fill_source=fill_source,
        )
        if canonical_msg is None:
            return None

        payload = canonical_msg.pld or {}
        symbol = str(payload.get("symbol") or "")
        missing_fields = self._missing_fill_activation_fields(payload)
        manage_flow: Optional[ManageFlowFSM] = None
        manage_flow_created = False
        manage_state_before = ""

        self._remember_proven_terminal_close(
            payload,
            trigger_event=event.verb,
        )

        if not missing_fields and symbol:
            manage_flow_created = symbol not in self.manage_flows
            _, manage_flow, _ = self._get_or_create_flows(symbol)
            manage_state_before = self._manage_state_value(manage_flow)

        if fill_source == "trade_executed":
            self._evt_handlers.on_trade_executed(canonical_msg)

        bookkeeping_msg = canonical_msg
        if fill_source == "trade_executed":
            bookkeeping_data = canonical_msg.model_dump()
            bookkeeping_payload = dict(payload)
            bookkeeping_payload["_skip_trade_lifecycle_on_fill"] = True
            bookkeeping_data["pld"] = bookkeeping_payload
            bookkeeping_msg = Message(**bookkeeping_data)
        self._evt_handlers.on_order_fill(bookkeeping_msg)

        if missing_fields:
            self._append_execution_fill_ingress_record(
                canonical_msg=canonical_msg,
                trigger_event=event.verb,
                fill_source=fill_source,
                manage_flow_created=False,
                manage_state_before="",
                manage_state_after="",
                result=None,
                activation_skipped_reason="missing_fields:" +
                ",".join(missing_fields),
            )
            return None

        result = manage_flow.handle(
            canonical_msg) if manage_flow is not None else None
        manage_state_after = self._manage_state_value(manage_flow)

        payload["manage_flow_created"] = manage_flow_created
        payload["manage_state_before"] = manage_state_before
        payload["manage_state_after"] = manage_state_after
        payload["portfolio_position_signature"] = self._get_portfolio_position_signature(
            symbol)
        payload["portfolio_positions_last_ts_ms"] = (
            (self._latest_portfolio_state or {}).get("positions_last_ts_ms")
        )
        portfolio_position_amt = self._latest_portfolio_position_amt(symbol)
        if portfolio_position_amt is not None:
            payload["portfolio_position_amt"] = portfolio_position_amt

        self._append_execution_fill_ingress_record(
            canonical_msg=canonical_msg,
            trigger_event=event.verb,
            fill_source=fill_source,
            manage_flow_created=manage_flow_created,
            manage_state_before=manage_state_before,
            manage_state_after=manage_state_after,
            result=result,
        )

        if self._position_policy_sidecar is not None and (
            result is None or getattr(result, "op", None) != "ERR"
        ):
            if fill_source == "trade_executed":
                self._position_policy_sidecar.on_trade_executed(canonical_msg)
            else:
                self._position_policy_sidecar.on_order_fill(canonical_msg)

        if process_result:
            self._process_flow_result(result)
        return result

    def _on_trade_executed(self, event: Message) -> None:
        """Canonical fill ingress for authoritative runtime TRADE_EXECUTED events."""
        self._handle_canonical_fill_ingress(
            event,
            fill_source="trade_executed",
            process_result=True,
        )

    def _on_order_fill(self, event: Message) -> None:
        """Compatibility fill ingress routed into the same canonical local lifecycle path."""
        self._handle_canonical_fill_ingress(
            event,
            fill_source="order_fill",
            process_result=True,
        )

    def _on_features_calculated(self, event: Message) -> None:
        """Phase 14A: Delegated to EPEventHandlers."""
        self._evt_handlers.on_features_calculated(event)
        if self._position_policy_sidecar is not None:
            self._position_policy_sidecar.on_features_calculated(event)

    def _on_order_state_changed(self, event: Message) -> None:
        """Preserve incumbent cancel-state handling, then forward to the sidecar."""
        self._handle_cancel_event(event)
        if self._position_policy_sidecar is not None:
            self._position_policy_sidecar.on_order_state_changed(event)

    def _on_execution_close_reconciled(self, event: Message) -> None:
        """Forward authoritative close reconciliation after incumbent ownership resolves."""
        payload = dict(getattr(event, "pld", None) or {})
        symbol = str(payload.get("symbol") or "").strip().upper()
        request_context = self._position_policy_close_requests.get(symbol)
        if request_context is not None:
            self._emit_position_policy_close_request_state(
                request_context,
                request_state="reconciled",
                why="position_policy_sidecar:close_reconciled",
                extra={
                    "business_close_reconciled": bool(
                        payload.get("business_close_reconciled")
                    ),
                    "reconcile_source": payload.get("source"),
                    "reconcile_rid": payload.get("rid"),
                    "reconcile_why": payload.get("why"),
                },
            )
            self._position_policy_close_requests.pop(symbol, None)
        self._apply_authoritative_local_close_reset(
            symbol,
            reason="execution_close_reconciled",
            source=str(payload.get("source") or "execution_close_reconciled"),
            payload=payload,
        )
        if self._position_policy_sidecar is not None:
            self._position_policy_sidecar.on_execution_close_reconciled(event)

    def _on_position_policy_close_request(self, event: Message) -> None:
        payload = dict(getattr(event, "pld", None) or {})
        request, request_payload, parse_error = self._parse_position_policy_close_request(
            payload
        )
        if request is None:
            self._emit_position_policy_close_request_state(
                request_payload,
                request_state="suppressed",
                why="position_policy_sidecar:close_request_invalid",
                extra={"suppression_reason": parse_error or "invalid_request"},
            )
            return

        symbol = request.symbol
        allowed_scope = self._position_policy_allowed_scope()
        request_payload["allowed_action_scope"] = dict(allowed_scope)

        suppression_reason: Optional[str] = None
        incumbent_owner: Optional[str] = None
        manage_flow = self.manage_flows.get(symbol)
        if request.policy_source != "position_policy_sidecar":
            suppression_reason = "invalid_policy_source"
        elif request.requested_action != "SOFT_CLOSE":
            suppression_reason = "unsupported_requested_action"
        elif request.target_mode != "symbol_current_net_only":
            suppression_reason = "exact_targeting_forbidden"
        elif request.requested_qty not in (None, "", "0", 0):
            suppression_reason = "partial_reduce_forbidden"
        elif not bool(allowed_scope.get("soft_close_symbol_current_net_only")):
            suppression_reason = "soft_close_scope_disabled"
        elif bool(allowed_scope.get("partial_reduce")):
            suppression_reason = "partial_reduce_forbidden"
        elif bool(allowed_scope.get("bracket_mutation")):
            suppression_reason = "bracket_mutation_forbidden"
        elif bool(allowed_scope.get("exact_targeting")):
            suppression_reason = "exact_targeting_forbidden"
        elif manage_flow is None:
            suppression_reason = "no_manage_flow_for_symbol"
        elif hasattr(manage_flow, "has_active_lifecycle") and not manage_flow.has_active_lifecycle():
            suppression_reason = "manage_flow_has_no_active_lifecycle"
        elif bool(getattr(manage_flow, "_closing_position", False)):
            suppression_reason = "manage_flow_close_in_progress"
            incumbent_owner = "ManageFlowFSM"

        portfolio_state = self._get_portfolio_state_for_symbol(symbol)
        position_signature = self._get_portfolio_position_signature(symbol)
        if suppression_reason is None and portfolio_state == "UNKNOWN":
            suppression_reason = "portfolio_state_unknown"
        elif suppression_reason is None and portfolio_state == "FLAT":
            suppression_reason = "portfolio_flat_no_live_net_position"
        elif suppression_reason is None and position_signature == "UNKNOWN":
            suppression_reason = "portfolio_position_signature_unknown"

        hardening = get_execution_truth_hardening(self)
        if suppression_reason is None and hardening is not None:
            close_decision = hardening.evaluate_close_command(
                symbol=symbol,
                requested_qty=request.requested_qty,
                position_signature=position_signature,
                rid=request.request_id,
            )
            if close_decision.suppress:
                suppression_reason = f"close_guard:{close_decision.reason}"
                incumbent_owner = incumbent_owner or "ExecutionTruthHardening"

        if suppression_reason is not None:
            self._emit_position_policy_close_request_state(
                request_payload,
                request_state="suppressed",
                why="position_policy_sidecar:close_request_suppressed",
                extra={
                    "suppression_reason": suppression_reason,
                    "incumbent_owner": incumbent_owner,
                    "portfolio_state": portfolio_state,
                    "portfolio_position_signature": position_signature,
                },
            )
            return

        policy_context = self._position_policy_context_from_request_payload(
            request_payload
        )
        self._position_policy_close_requests[symbol] = dict(policy_context)
        close_msg = Message(
            op="CMD",
            verb="CLOSE",
            src="execution_position.position_policy_sidecar",
            dst="execution_position",
            rid=request.request_id,
            why="position_policy_sidecar_soft_close",
            pld={
                "symbol": symbol,
                "reason": "position_policy_sidecar_soft_close",
                "trigger": CLOSE_REQUEST_COMMAND_TOPIC,
                "trace": request.trace_id,
                "idempotent_key": request.request_id,
                "close_guard_prevalidated": True,
                "policy_context": policy_context,
            },
        )
        result = self.handle(close_msg)
        if result is None or result.op != "DEC" or result.verb not in {"CLOSE", "CLOSE_POSITION"}:
            self._position_policy_close_requests.pop(symbol, None)
            self._emit_position_policy_close_request_state(
                request_payload,
                request_state="suppressed",
                why="position_policy_sidecar:close_command_not_emitted",
                extra={
                    "suppression_reason": "close_command_not_emitted",
                    "portfolio_state": portfolio_state,
                    "portfolio_position_signature": position_signature,
                },
            )
            return

        self._emit_position_policy_close_request_state(
            request_payload,
            request_state="close_command_emitted",
            why="position_policy_sidecar:close_command_emitted",
            extra={
                "close_cmd_rid": request.request_id,
                "execution_shadow_mode": bool(self.shadow_mode),
                "adapter_present": bool(self.adapter),
                "portfolio_state": portfolio_state,
                "portfolio_position_signature": position_signature,
            },
        )

    def _parse_position_policy_close_request(
        self,
        payload: Dict[str, Any],
    ) -> tuple[Optional[PositionPolicyCloseRequest], Dict[str, Any], Optional[str]]:
        normalized = dict(payload)
        symbol = str(normalized.get("symbol") or "").strip().upper()
        normalized["symbol"] = symbol
        normalized.setdefault(
            "event_type", "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED")
        normalized.setdefault("policy_source", "position_policy_sidecar")
        normalized.setdefault(
            "source_event_type", "POSITION_POLICY_SIDECAR_RECOMMENDED"
        )
        normalized.setdefault("requested_action", "SOFT_CLOSE")
        normalized.setdefault("target_mode", "symbol_current_net_only")
        normalized.setdefault("action_package_version", ACTION_PACKAGE_VERSION)
        normalized.setdefault("allowed_action_scope", {})
        normalized.setdefault("reason_codes", [])
        normalized.setdefault("score_snapshot", {})
        normalized.setdefault("position_snapshot", {})
        normalized.setdefault("feature_ref", {})
        normalized.setdefault("regime_ref", {})
        normalized.setdefault("freshness_snapshot", {})
        normalized.setdefault("fill_correlation", {})
        normalized.setdefault("portfolio_correlation", {})
        normalized["request_id"] = str(
            normalized.get("request_id") or "").strip()
        normalized["trace_id"] = str(normalized.get("trace_id") or "").strip()
        normalized["requested_qty"] = normalized.get("requested_qty")
        try:
            normalized["ts_ms"] = int(normalized.get(
                "ts_ms") or get_clock().now_ms())
        except (TypeError, ValueError):
            normalized["ts_ms"] = get_clock().now_ms()

        if not normalized["request_id"]:
            return None, normalized, "missing_request_id"
        if not normalized["trace_id"]:
            return None, normalized, "missing_trace_id"
        if not symbol:
            return None, normalized, "missing_symbol"

        request = self.position_policy_close_request_type(
            ts_ms=normalized["ts_ms"],
            request_id=normalized["request_id"],
            trace_id=normalized["trace_id"],
            symbol=symbol,
            source_event_type=str(normalized.get(
                "source_event_type") or "POSITION_POLICY_SIDECAR_RECOMMENDED"),
            event_type=str(normalized.get("event_type")
                           or "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED"),
            requested_action=str(normalized.get(
                "requested_action") or "SOFT_CLOSE"),
            requested_qty=(
                None
                if normalized.get("requested_qty") in (None, "", "0", 0)
                else str(normalized.get("requested_qty"))
            ),
            target_mode=str(normalized.get("target_mode")
                            or "symbol_current_net_only"),
            policy_source=str(normalized.get("policy_source")
                              or "position_policy_sidecar"),
            action_package_version=str(normalized.get(
                "action_package_version") or ACTION_PACKAGE_VERSION),
            allowed_action_scope=dict(
                normalized.get("allowed_action_scope") or {}),
            reason_codes=tuple(str(code) for code in (
                normalized.get("reason_codes") or [])),
            score_snapshot=dict(normalized.get("score_snapshot") or {}),
            position_snapshot=dict(normalized.get("position_snapshot") or {}),
            feature_ref=dict(normalized.get("feature_ref") or {}),
            regime_ref=dict(normalized.get("regime_ref") or {}),
            freshness_snapshot=dict(
                normalized.get("freshness_snapshot") or {}),
            fill_correlation=dict(normalized.get("fill_correlation") or {}),
            portfolio_correlation=dict(
                normalized.get("portfolio_correlation") or {}),
        )
        request_payload = dict(normalized)
        request_payload.update(request.to_payload())
        return request, request_payload, None

    def _position_policy_allowed_scope(self) -> Dict[str, bool]:
        try:
            candidate = self.config.domains.execution_position.position_policy_sidecar
        except Exception:
            candidate = None
        if not isinstance(candidate, PositionPolicySidecarConfig):
            return {
                "soft_close_symbol_current_net_only": False,
                "partial_reduce": False,
                "bracket_mutation": False,
                "exact_targeting": False,
            }
        return {
            "soft_close_symbol_current_net_only": bool(
                candidate.allowed_actions.soft_close_symbol_current_net_only
            ),
            "partial_reduce": bool(candidate.allowed_actions.partial_reduce),
            "bracket_mutation": bool(candidate.allowed_actions.bracket_mutation),
            "exact_targeting": bool(candidate.allowed_actions.exact_targeting),
        }

    @staticmethod
    def _position_policy_context_from_request_payload(
        request_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "symbol": request_payload.get("symbol"),
            "policy_source": request_payload.get("policy_source"),
            "source_event_type": request_payload.get("source_event_type"),
            "source_trace_id": request_payload.get("trace_id"),
            "request_id": request_payload.get("request_id"),
            "request_event_type": request_payload.get("event_type"),
            "requested_action": request_payload.get("requested_action"),
            "requested_qty": request_payload.get("requested_qty"),
            "target_mode": request_payload.get("target_mode"),
            "allowed_action_scope": dict(
                request_payload.get("allowed_action_scope") or {}
            ),
            "reason_codes": list(request_payload.get("reason_codes") or []),
            "score_snapshot": dict(request_payload.get("score_snapshot") or {}),
            "position_snapshot": dict(request_payload.get("position_snapshot") or {}),
            "feature_ref": dict(request_payload.get("feature_ref") or {}),
            "regime_ref": dict(request_payload.get("regime_ref") or {}),
            "freshness_snapshot": dict(
                request_payload.get("freshness_snapshot") or {}
            ),
            "fill_correlation": dict(request_payload.get("fill_correlation") or {}),
            "portfolio_correlation": dict(
                request_payload.get("portfolio_correlation") or {}
            ),
            "action_package_version": request_payload.get("action_package_version"),
            "request_ts_ms": request_payload.get("ts_ms"),
        }

    def _emit_position_policy_close_request_state(
        self,
        request_context: Dict[str, Any],
        *,
        request_state: str,
        why: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = {
            "ts_ms": int(get_clock().now_sec() * 1000),
            "event_type": "POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE",
            "request_state": request_state,
            "symbol": request_context.get("symbol")
            or (
                request_context.get("position_snapshot") or {}
            ).get("symbol"),
            "request_id": request_context.get("request_id"),
            "trace_id": request_context.get("trace_id")
            or request_context.get("source_trace_id"),
            "policy_source": request_context.get("policy_source")
            or "position_policy_sidecar",
            "policy_context": self._position_policy_context_from_request_payload(
                request_context
            )
            if "trace_id" in request_context
            else dict(request_context),
            "why": why,
        }
        if extra:
            payload.update({k: v for k, v in extra.items() if v is not None})
        self._emit_execution_bus_event(
            "EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE",
            payload,
        )
        append_trade_lifecycle_record(
            {
                "record_kind": POSITION_POLICY_SIDECAR_RECORD_KIND,
                **payload,
            },
            log_file=self._trade_lifecycle_log_path(),
        )

    def _position_policy_known_symbols(self) -> Set[str]:
        symbols: Set[str] = set(self.manage_flows.keys())
        symbols.update(str(sym).upper()
                       for sym in self._last_features_cache.keys())
        symbols.update(str(sym).upper()
                       for sym in self._last_regime_by_symbol.keys())
        return symbols

    def _create_position_policy_sidecar(self) -> Optional[PositionPolicySidecar]:
        try:
            candidate = self.config.domains.execution_position.position_policy_sidecar
        except Exception:
            return None

        if not isinstance(candidate, PositionPolicySidecarConfig):
            return None
        if candidate.mode.value == "disable":
            return None

        return PositionPolicySidecar(
            config=candidate,
            bus=self.bus,
            manage_flow_getter=lambda symbol: self.manage_flows.get(
                str(symbol).upper()),
            known_symbols_getter=self._position_policy_known_symbols,
        )

    def shutdown(self):
        """Shutdown the FSM and cleanup resources."""
        if self._restore_artifact_has_state():
            self._persist_restore_artifact_snapshot(
                trigger="shutdown",
                allow_empty=False,
            )
        if hasattr(self, '_intent_boundary_audit') and self._intent_boundary_audit:
            self._intent_boundary_audit.stop()
        if hasattr(self, 'watchdog') and self.watchdog:
            self.watchdog.stop()
        if hasattr(self, 'order_guardian') and self.order_guardian:
            loop = self._get_async_loop()
            if loop:
                self._submit_async(self.order_guardian.stop(), loop)
        # FILL-PIPELINE-FIX-AUDIT: Stop WS client on shutdown (F-4)
        if hasattr(self, 'ws_client') and self.ws_client is not None:
            try:
                self.ws_client.stop()
            except Exception:
                pass
        LOG.info("ExecPosFSM shutdown complete")

    async def start_order_guardian(self):
        """Start OrderGuardian polling and reconciliation after FSM initialization."""
        try:
            self._schedule_restore_artifact_loop()
        except Exception as e:
            LOG.error(f"Failed to start restore artifact loop: {e}")
        if not self.order_guardian:
            return

        try:
            self._schedule_guardian_start()
            self._schedule_fsm_cleanup_loop()
            self._schedule_bracket_health_check()
        except Exception as e:
            LOG.error(f"Failed to start OrderGuardian: {e}")

    def _schedule_restore_artifact_loop(self) -> None:
        if self._restore_artifact_loop_started:
            return
        if self._restore_artifact_writer is None:
            return
        if not self._restore_artifact_writer.writes_enabled():
            return
        loop = self._get_async_loop()
        if not loop:
            LOG.debug("Restore artifact loop deferred: no event loop active")
            return
        self._submit_async(self._restore_artifact_loop(), loop)
        self._restore_artifact_loop_started = True

    async def _restore_artifact_loop(self) -> None:
        writer = self._restore_artifact_writer
        if writer is None or not writer.writes_enabled():
            return

        while True:
            try:
                await get_clock().sleep_ms(writer.flush_interval_ms)
                self._persist_restore_artifact_snapshot(
                    trigger="periodic",
                    allow_empty=False,
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                LOG.warning("restore artifact loop error: %s", e)

    def _schedule_bracket_health_check(self) -> None:
        """Schedule the bracket health loop once the shared async runtime is ready."""
        if self._bracket_health_started:
            return

        try:
            cfg = self.config.domains.execution_position.bracket_health_check
        except (AttributeError, TypeError):
            cfg = None

        if cfg is None:
            return
        try:
            if not bool(cfg.enabled):
                return
        except AttributeError:
            return

        loop = self._get_async_loop()
        if not loop:
            LOG.debug("[BRACKET-HEALTH] deferred: no event loop active")
            return

        self._submit_async(self._bracket_health_loop(), loop)
        self._bracket_health_started = True
        LOG.info(
            "[BRACKET-HEALTH] scheduled (interval=%ss, grace=%sms)",
            int(cfg.interval_sec),
            int(cfg.grace_period_ms),
        )

    async def _bracket_health_loop(self) -> None:
        """Periodic safety net for missing SL/TP brackets."""
        try:
            cfg = self.config.domains.execution_position.bracket_health_check
        except (AttributeError, TypeError):
            return

        if cfg is None:
            return
        try:
            if not bool(cfg.enabled):
                return
        except AttributeError:
            return

        while True:
            try:
                await get_clock().sleep_sec(float(cfg.interval_sec))
                await self._run_bracket_health_check(cfg)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                LOG.warning(f"[BRACKET-HEALTH] loop error: {e}")

    async def _run_bracket_health_check(self, cfg: Any) -> None:
        """Check live positions and re-arm missing SL/TP brackets when safe."""
        if not self.adapter:
            return

        try:
            positions = await self.adapter.get_open_positions()
        except Exception as e:
            LOG.warning(f"[BRACKET-HEALTH] failed to get positions: {e}")
            return

        if not positions:
            return

        current_time_ms = get_clock().now_ms()
        placements_this_cycle = 0

        for pos in positions:
            if placements_this_cycle >= int(cfg.max_placements_per_cycle):
                break

            if hasattr(pos, "to_dict"):
                pos_dict = pos.to_dict()
            elif isinstance(pos, dict):
                pos_dict = pos
            else:
                pos_dict = pos.__dict__ if hasattr(pos, "__dict__") else {}

            symbol = str(pos_dict.get("symbol") or "")
            if not symbol:
                continue

            try:
                position_amt = float(
                    pos_dict.get("net_position")
                    or pos_dict.get("positionAmt")
                    or pos_dict.get("position_amount")
                    or 0.0
                )
            except Exception:
                position_amt = 0.0
            if abs(position_amt) < 1e-10:
                continue

            entry_price_raw = pos_dict.get(
                "entryPrice") or pos_dict.get("entry_price")
            try:
                entry_price = float(entry_price_raw or 0.0)
            except Exception:
                entry_price = 0.0
            if entry_price <= 0.0:
                continue

            update_time_ms = int(
                pos_dict.get("updateTime") or pos_dict.get(
                    "update_time_ms") or 0
            )
            if update_time_ms > 0 and (current_time_ms - update_time_ms) < int(cfg.grace_period_ms):
                continue

            has_sl, has_tp = await self._check_brackets_on_exchange(symbol)
            if has_sl and has_tp:
                continue

            side = "BUY" if position_amt > 0 else "SELL"
            owner_context = self._resolve_health_check_bracket_context(
                symbol=symbol,
                entry_price=entry_price,
                side=side,
            )
            sl_price = owner_context.get("sl_price")
            tp_price = owner_context.get("tp_price")
            if sl_price is None or tp_price is None:
                self._append_bracket_ownership_record(
                    event_type="EXECUTION_BRACKET_RECOVERY_SKIPPED",
                    symbol=symbol,
                    placement_path="recovery",
                    strategy_id=owner_context.get("strategy_id"),
                    strategy_source=owner_context.get("strategy_source"),
                    owner_status=str(owner_context.get(
                        "owner_status") or "missing"),
                    detail=owner_context.get("detail"),
                    assigned_strategies=owner_context.get(
                        "assigned_strategies"),
                    lifecycle_active=self._has_active_lifecycle_for_symbol(
                        symbol),
                )
                continue

            placed = await self._place_health_check_brackets(
                symbol=symbol,
                side=side,
                sl_price=sl_price,
                tp_price=tp_price,
                need_sl=not has_sl,
                need_tp=not has_tp,
                owner_context=owner_context,
            )
            if placed:
                placements_this_cycle += 1

    async def _check_brackets_on_exchange(self, symbol: str) -> Tuple[bool, bool]:
        """Inspect exchange open orders and detect existing SL/TP brackets."""
        try:
            if hasattr(self.adapter, "_request"):
                raw_orders = await self.adapter._request(
                    "GET", "/fapi/v1/openOrders", {"symbol": symbol}
                )
            else:
                raw_orders = await self.adapter.get_open_orders(symbol)
        except Exception as e:
            LOG.warning(
                f"[BRACKET-HEALTH] failed to inspect open orders for {symbol}: {e}")
            return True, True

        has_sl = False
        has_tp = False
        for order in raw_orders or []:
            if hasattr(order, "to_dict"):
                order_dict = order.to_dict()
            elif isinstance(order, dict):
                order_dict = order
            else:
                order_dict = order.__dict__ if hasattr(
                    order, "__dict__") else {}

            order_type = str(order_dict.get("type") or "").upper()
            reduce_only_raw = order_dict.get("reduceOnly", False)
            close_position_raw = order_dict.get("closePosition", False)
            reduce_only = coerce_exchange_bool(reduce_only_raw)
            close_position = coerce_exchange_bool(close_position_raw)

            if order_type == "STOP_MARKET" and (reduce_only or close_position):
                has_sl = True
            if order_type == "TAKE_PROFIT_MARKET" and (reduce_only or close_position):
                has_tp = True

        return has_sl, has_tp

    def _resolve_health_check_bracket_context(
        self,
        *,
        symbol: str,
        entry_price: float,
        side: str,
    ) -> Dict[str, Any]:
        context = dict(
            self._resolve_strategy_owner_for_recovery(symbol=symbol))
        context.setdefault("assigned_strategies",
                           self._strategy_assignments_for_symbol(symbol))
        context["sl_price"] = None
        context["tp_price"] = None
        strategy_id = str(context.get("strategy_id") or "").strip()
        if context.get("owner_status") != "resolved" or not strategy_id:
            return context

        regime = str(self._last_regime_by_symbol.get(symbol) or "DEFAULT")
        sl_price, tp_price, detail = self._compute_strategy_health_check_brackets(
            symbol=symbol,
            entry_price=entry_price,
            side=side,
            strategy_id=strategy_id,
            regime=regime,
        )
        if sl_price is None or tp_price is None:
            current_detail = str(context.get("detail") or "").strip()
            if detail:
                context["detail"] = f"{current_detail};{detail}" if current_detail else detail
            return context

        context["sl_price"] = sl_price
        context["tp_price"] = tp_price
        return context

    def _compute_strategy_health_check_brackets(
        self,
        *,
        symbol: str,
        entry_price: float,
        side: str,
        strategy_id: str,
        regime: str,
    ) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """Compute recovery brackets from the explicit strategy owner for the symbol."""
        try:
            sl_pct_eff: Optional[float] = None
            tp_rr_eff: Optional[float] = None

            if strategy_id == "md_amr" and getattr(self.config.strategies, "md_amr", None) is not None:
                strategy_cfg = self.config.strategies.md_amr
                asset_cfg = strategy_cfg.assets.get(symbol) if isinstance(
                    strategy_cfg.assets, dict) else None
                exit_cfg = getattr(asset_cfg, "exit",
                                   None) if asset_cfg is not None else None
                if exit_cfg is not None and getattr(exit_cfg, "sl_pct", None) is not None and getattr(exit_cfg, "tp_rr", None) is not None:
                    sl_pct_eff = float(exit_cfg.sl_pct)
                    tp_rr_eff = float(exit_cfg.tp_rr)
                    regime_tpsl = getattr(exit_cfg, "regime_tpsl", None)
                    try:
                        regime_tpsl_enabled = bool(
                            regime_tpsl.enabled) if regime_tpsl is not None else False
                    except AttributeError:
                        regime_tpsl_enabled = False
                    if regime_tpsl_enabled:
                        sl_mult = float((getattr(regime_tpsl, "sl_mult", {}) or {}).get(
                            regime, (getattr(regime_tpsl, "sl_mult", {}) or {}).get("DEFAULT", 1.0)))
                        tp_mult = float((getattr(regime_tpsl, "tp_mult", {}) or {}).get(
                            regime, (getattr(regime_tpsl, "tp_mult", {}) or {}).get("DEFAULT", 1.0)))
                        sl_pct_eff = sl_pct_eff * sl_mult
                        tp_rr_eff = tp_rr_eff * tp_mult
                        if getattr(regime_tpsl, "min_sl_pct", None) is not None:
                            sl_pct_eff = max(
                                float(regime_tpsl.min_sl_pct), sl_pct_eff)
                        if getattr(regime_tpsl, "max_sl_pct", None) is not None:
                            sl_pct_eff = min(
                                float(regime_tpsl.max_sl_pct), sl_pct_eff)
                        if getattr(regime_tpsl, "min_tp_rr", None) is not None:
                            tp_rr_eff = max(
                                float(regime_tpsl.min_tp_rr), tp_rr_eff)
                        if getattr(regime_tpsl, "max_tp_rr", None) is not None:
                            tp_rr_eff = min(
                                float(regime_tpsl.max_tp_rr), tp_rr_eff)
            elif strategy_id == "aurora" and getattr(self.config.strategies, "aurora", None) is not None:
                strategy_cfg = getattr(self.config.strategies, "aurora", None)
                asset_cfg = strategy_cfg.assets.get(
                    symbol) if strategy_cfg is not None else None
                exit_cfg = getattr(asset_cfg, "exit",
                                   None) if asset_cfg is not None else None
                tp_cfg = getattr(asset_cfg, "take_profit",
                                 None) if asset_cfg is not None else None
                if exit_cfg is not None and getattr(exit_cfg, "sl_pct", None) is not None and tp_cfg is not None and getattr(tp_cfg, "tp_low_ratio", None) is not None:
                    sl_pct_eff = float(exit_cfg.sl_pct)
                    tp_rr_eff = float(tp_cfg.tp_low_ratio)
                    regime_tpsl = getattr(exit_cfg, "regime_tpsl", None)
                    try:
                        regime_tpsl_enabled = bool(
                            regime_tpsl.enabled) if regime_tpsl is not None else False
                    except AttributeError:
                        regime_tpsl_enabled = False
                    regime_tpsl_mode = str(
                        getattr(regime_tpsl, "mode", "")) if regime_tpsl is not None else ""
                    if regime_tpsl_enabled and regime_tpsl_mode == "pct_mult":
                        sl_mult = float((getattr(regime_tpsl, "sl_mult", {}) or {}).get(
                            regime, (getattr(regime_tpsl, "sl_mult", {}) or {}).get("DEFAULT", 1.0)))
                        tp_mult = float((getattr(regime_tpsl, "tp_mult", {}) or {}).get(
                            regime, (getattr(regime_tpsl, "tp_mult", {}) or {}).get("DEFAULT", 1.0)))
                        sl_pct_eff = sl_pct_eff * sl_mult
                        tp_rr_eff = tp_rr_eff * tp_mult
                        if getattr(regime_tpsl, "min_sl_pct", None) is not None:
                            sl_pct_eff = max(
                                float(regime_tpsl.min_sl_pct), sl_pct_eff)
                        if getattr(regime_tpsl, "max_sl_pct", None) is not None:
                            sl_pct_eff = min(
                                float(regime_tpsl.max_sl_pct), sl_pct_eff)
                        if getattr(regime_tpsl, "min_tp_rr", None) is not None:
                            tp_rr_eff = max(
                                float(regime_tpsl.min_tp_rr), tp_rr_eff)
                        if getattr(regime_tpsl, "max_tp_rr", None) is not None:
                            tp_rr_eff = min(
                                float(regime_tpsl.max_tp_rr), tp_rr_eff)
            elif strategy_id == "mean_reversion":
                return None, None, "unsupported_recovery_strategy:mean_reversion"
            else:
                return None, None, f"unsupported_recovery_strategy:{strategy_id}"

            if sl_pct_eff is None or tp_rr_eff is None:
                return None, None, f"recovery_exit_profile_missing:{strategy_id}"

            instrument_spec = self.config.instruments.get(symbol)
            tick_size = Decimal(str(instrument_spec.tick_size)
                                ) if instrument_spec is not None else Decimal("0.01")

            recovery_targets = compute_bracket_targets(
                reference_price=entry_price,
                position_side=side,
                sl_pct=sl_pct_eff,
                tp_low_ratio=tp_rr_eff,
            )

            return (
                float(quantize_stop_price(float(recovery_targets.sl_price), float(tick_size),
                      side="SELL" if side == "BUY" else "BUY")),
                float(quantize_stop_price(float(recovery_targets.tp1_price), float(tick_size),
                      side="BUY" if side == "BUY" else "SELL")),
                None,
            )
        except Exception as e:
            LOG.warning(
                f"[BRACKET-HEALTH] failed to compute recovery brackets for {symbol}: {e}")
            return None, None, f"recovery_compute_error:{strategy_id}"

    def _compute_health_check_brackets(
        self,
        *,
        symbol: str,
        entry_price: float,
        side: str,
    ) -> Tuple[Optional[float], Optional[float]]:
        context = self._resolve_health_check_bracket_context(
            symbol=symbol,
            entry_price=entry_price,
            side=side,
        )
        return context.get("sl_price"), context.get("tp_price")

    async def _place_health_check_brackets(
        self,
        *,
        symbol: str,
        side: str,
        sl_price: float,
        tp_price: float,
        need_sl: bool,
        need_tp: bool,
        owner_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Place only the missing recovery brackets and register them with current owners."""
        if not self.adapter or not self.order_guardian:
            return False

        if not await self._preflight_position_check(symbol):
            return False

        bracket_side = opposite_side(side)
        parent_order_id = f"health_check:{symbol}"
        placed = False
        owner_context = dict(owner_context or {})

        if need_sl:
            try:
                sl_client_id = generate_client_order_id("BHSL", symbol)
                sl_resp = await self.adapter.place_stop_market_close_position(
                    symbol,
                    bracket_side,
                    str(sl_price),
                    new_client_order_id=sl_client_id,
                )
                sl_order_id = str(
                    sl_resp.get("orderId", "")
                    if isinstance(sl_resp, dict)
                    else getattr(sl_resp, "order_id", "")
                )
                if sl_order_id:
                    self._set_symbol_bracket_order(
                        symbol,
                        order_role="SL",
                        order_id=sl_order_id,
                    )
                    self.order_guardian.register_bracket(
                        symbol=symbol,
                        parent_order_id=parent_order_id,
                        order_id=sl_order_id,
                        client_order_id=sl_client_id,
                        kind="SL",
                        corr_id="bracket_health",
                        rid="bracket_health",
                    )
                    placed = True
            except Exception as e:
                LOG.warning(
                    f"[BRACKET-HEALTH] SL recovery failed for {symbol}: {e}")

        if need_tp:
            try:
                tp_client_id = generate_client_order_id("BHTP", symbol)
                tp_resp = await self.adapter.place_take_profit_market_close_position(
                    symbol,
                    bracket_side,
                    str(tp_price),
                    new_client_order_id=tp_client_id,
                )
                tp_order_id = str(
                    tp_resp.get("orderId", "")
                    if isinstance(tp_resp, dict)
                    else getattr(tp_resp, "order_id", "")
                )
                if tp_order_id:
                    self._set_symbol_bracket_order(
                        symbol,
                        order_role="TP",
                        order_id=tp_order_id,
                    )
                    self.order_guardian.register_bracket(
                        symbol=symbol,
                        parent_order_id=parent_order_id,
                        order_id=tp_order_id,
                        client_order_id=tp_client_id,
                        kind="TP",
                        corr_id="bracket_health",
                        rid="bracket_health",
                    )
                    placed = True
            except Exception as e:
                LOG.warning(
                    f"[BRACKET-HEALTH] TP recovery failed for {symbol}: {e}")

        if placed:
            lifecycle_active = self._has_active_lifecycle_for_symbol(symbol)
            owner_snapshot = self._remember_bracket_owner(
                symbol=symbol,
                strategy_id=owner_context.get("strategy_id"),
                strategy_source=owner_context.get("strategy_source"),
                owner_status=str(owner_context.get(
                    "owner_status") or "resolved"),
                detail=owner_context.get("detail"),
                assigned_strategies=owner_context.get("assigned_strategies"),
                placement_path="recovery",
                lifecycle_active=lifecycle_active,
            )
            manage_flow = self.manage_flows.get(symbol)
            # GUARD: Only sync bracket IDs into ManageFlowFSM when a real lifecycle
            # is active (state != FLAT). Injecting bracket IDs into a FLAT FSM corrupts
            # has_active_lifecycle() truth, causing a self-reinforcing OPEN_GUARD_FAIL loop.
            # The bracket IDs remain in _symbol_brackets for external observability.
            if manage_flow is not None and manage_flow.state != ManageState.FLAT:
                brackets = self._symbol_brackets.get(symbol, {})
                manage_flow.set_bracket_ids(
                    brackets.get("sl_order_id"),
                    brackets.get("tp_order_id"),
                )
            self._emit_observability_event(
                "BRACKET_HEALTH_REARMED",
                {
                    "symbol": symbol,
                    "need_sl": bool(need_sl),
                    "need_tp": bool(need_tp),
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                },
            )
            self._append_bracket_ownership_record(
                event_type="EXECUTION_BRACKET_RECOVERY_PLACED",
                symbol=symbol,
                placement_path="recovery",
                strategy_id=owner_snapshot.get("strategy_id"),
                strategy_source=owner_snapshot.get("strategy_source"),
                owner_status=str(owner_snapshot.get(
                    "owner_status") or "resolved"),
                detail=owner_snapshot.get("detail"),
                assigned_strategies=owner_snapshot.get("assigned_strategies"),
                lifecycle_active=lifecycle_active,
                sl_order_id=(self._symbol_brackets.get(
                    symbol, {}) or {}).get("sl_order_id"),
                tp_order_id=(self._symbol_brackets.get(
                    symbol, {}) or {}).get("tp_order_id"),
            )

        return placed

    # Phase 14.2: _initialize_adapter
    #  extracted to AdapterInitMixin (adapter_init.py)

    def _create_open_flow(self, symbol: str) -> OpenFlowFSM:
        try:
            exec_config = self.config.trading.execution if self.config.trading else None
        except AttributeError:
            exec_config = None

        cooldown_ms = float(aget(exec_config, "cooldown_ms", 1000))
        guard_enabled = bool(aget(exec_config, "guard_enabled", True))
        cooldown_sec = cooldown_ms / 1000.0
        return OpenFlowFSM(
            cooldown_sec=cooldown_sec,
            guard_enabled=guard_enabled,
            config=self.config,
            metrics_collector=self.metrics_collector,
            leverage_service=self.leverage_service,
            is_live_execution=self.is_live_execution,
        )

    def _wire_manage_flow(self, symbol: str, manage_flow: ManageFlowFSM) -> None:
        self._set_manage_truth_source(
            symbol, self._manage_truth_source_for(symbol))
        if hasattr(manage_flow, "set_observability_hook"):
            manage_flow.set_observability_hook(
                self._emit_execution_bus_event,
            )
        if hasattr(manage_flow, "set_shadow_journal") and self._shadow_journal is not None:
            manage_flow.set_shadow_journal(self._shadow_journal)

    def _wire_close_flow(self, close_flow: CloseFlowFSM) -> None:
        if hasattr(close_flow, "set_shadow_journal") and self._shadow_journal is not None:
            close_flow.set_shadow_journal(self._shadow_journal)

    def _get_or_create_open_flow(self, symbol: str) -> OpenFlowFSM:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            raise ValueError("symbol is required")
        with self._flows_lock:
            if symbol_key not in self.open_flows:
                self.open_flows[symbol_key] = self._create_open_flow(
                    symbol_key)
            return self.open_flows[symbol_key]

    def _get_or_create_manage_flow(self, symbol: str) -> ManageFlowFSM:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            raise ValueError("symbol is required")
        with self._flows_lock:
            if symbol_key not in self.manage_flows:
                LOG.info(f"Creating new manage flow for symbol: {symbol_key}")
                self.manage_flows[symbol_key] = ManageFlowFSM(
                    config=self.config)
                self._set_manage_truth_source(
                    symbol_key, TRUTH_SOURCE_RUNTIME_LOCAL)
            self._wire_manage_flow(symbol_key, self.manage_flows[symbol_key])
            return self.manage_flows[symbol_key]

    def _get_or_create_close_flow(self, symbol: str) -> CloseFlowFSM:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            raise ValueError("symbol is required")
        with self._flows_lock:
            if symbol_key not in self.close_flows:
                LOG.info(f"Creating new close flow for symbol: {symbol_key}")
                self.close_flows[symbol_key] = CloseFlowFSM()
            self._wire_close_flow(self.close_flows[symbol_key])
            return self.close_flows[symbol_key]

    def _get_or_create_flows(
        self, symbol: str
    ) -> Tuple[OpenFlowFSM, ManageFlowFSM, CloseFlowFSM]:
        """Get or create the set of FSMs for a given symbol (thread-safe)."""
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            raise ValueError("symbol is required")
        with self._flows_lock:
            if symbol_key not in self.open_flows:
                self.open_flows[symbol_key] = self._create_open_flow(
                    symbol_key)
            if symbol_key not in self.manage_flows:
                LOG.info(f"Creating new set of FSMs for symbol: {symbol_key}")
                self.manage_flows[symbol_key] = ManageFlowFSM(
                    config=self.config)
                self._set_manage_truth_source(
                    symbol_key, TRUTH_SOURCE_RUNTIME_LOCAL)
            if symbol_key not in self.close_flows:
                self.close_flows[symbol_key] = CloseFlowFSM()

            self._wire_manage_flow(symbol_key, self.manage_flows[symbol_key])
            self._wire_close_flow(self.close_flows[symbol_key])

            return (
                self.open_flows[symbol_key],
                self.manage_flows[symbol_key],
                self.close_flows[symbol_key],
            )

    def hydrate(self, position_data: Dict[str, Any]):
        """Hydrate the FSMs for a given position from a snapshot."""
        symbol = position_data.get("symbol")
        if not symbol:
            LOG.error("HYDRATION_ERROR: position_data is missing 'symbol'")
            return

        journal = get_shadow_journal(self)
        before = snapshot_execpos_state(
            self, symbol) if journal is not None else None
        _, manage_flow, close_flow = self._get_or_create_flows(symbol)

        LOG.info(f"Hydrating FSMs for symbol {symbol} from snapshot.")
        manage_flow.hydrate(position_data)
        close_flow.hydrate(position_data)
        if journal is not None:
            journal.record_transition(
                event_name="RESTORE:EXECUTION_POSITION_HYDRATE",
                source_component="execution_position.fsm",
                source_path="restore:execution_position_hydrate",
                event_origin_type="restore",
                truth_owner="ExecPosFSM",
                payload=position_data,
                rid=str(position_data.get("rid")) if position_data.get(
                    "rid") is not None else None,
                before=before,
                after=snapshot_execpos_state(self, symbol),
                restore_marker=True,
            )

    def restore_startup_from_snapshot_positions(
        self,
        restored_positions: Dict[str, Dict[str, Any]],
    ) -> int:
        if self._authoritative_restore_enabled():
            LOG.info(
                "Skipping heuristic execution hydrate from snapshot positions because restore_artifact.mode=authoritative"
            )
            return 0

        hydrated_count = 0
        for symbol, position_data in restored_positions.items():
            hydrate_data = {
                "symbol": symbol,
                "qty": position_data["quantity"],
                "entry_price": position_data["avg_price"],
                "side": "BUY" if position_data["quantity"] > 0 else "SELL",
            }
            self.hydrate(hydrate_data)
            hydrated_count += 1
        return hydrated_count

    def handle(self, msg: Message) -> Optional[Message]:
        """Route message to the appropriate flow and handle execution decisions."""
        journal = get_shadow_journal(self)
        pld = msg.pld or {}
        symbol_hint = pld.get("symbol")
        before = snapshot_execpos_state(
            self, symbol_hint) if journal is not None else None
        result = None
        try:
            if msg.verb == "PORTFOLIO_STATE_UPDATED":
                self._on_portfolio_state_updated(msg)
                return None

            symbol = pld.get("symbol")
            if not symbol:
                LOG.warning(
                    f"ExecPosFSM received message without symbol: {msg.verb}, pld_keys={list(pld.keys()) if pld else 'EMPTY'}, msg_type={type(msg)}, pld_type={type(pld)}")
                return None

            open_flow, manage_flow, close_flow = self._get_or_create_flows(
                symbol)
            self._set_manage_truth_source(symbol, TRUTH_SOURCE_RUNTIME_LOCAL)
            restore_signature_before = self._restore_semantics_signature(
                symbol)

            if msg.verb == "OPEN":
                now = get_clock().now_sec()
                last_close = float(self._last_any_position_closed_ts or 0.0)
                if last_close > 0 and self._cooldown_after_close_sec > 0 and (now - last_close) < self._cooldown_after_close_sec:
                    remaining = max(
                        0.0, self._cooldown_after_close_sec - (now - last_close))
                    result = Message(
                        op="ERR",
                        verb="OPEN",
                        src=msg.dst,
                        dst=msg.src,
                        rid=msg.rid,
                        why="OPEN_GUARD_FAIL",
                        pld={
                            "reason": "cooldown_after_close active",
                            "cooldown_remaining_sec": round(remaining, 3),
                        },
                    )
                    return result

                local_guard_err = self._local_open_guard(msg, manage_flow)
                if local_guard_err is not None:
                    self._cancel_entry_reservation(str(msg.rid))
                    result = local_guard_err
                    return result

                exposure_err = self._check_exposure_fail_closed(msg)
                if exposure_err is not None:
                    self._cancel_entry_reservation(str(msg.rid))
                    result = exposure_err
                    return result
                result = open_flow.handle(msg)

                if result is not None and getattr(result, "op", None) == "ERR":
                    self._cancel_entry_reservation(str(msg.rid))

                if result and result.op == "DEC" and result.verb == "OPEN":
                    try:
                        pld = result.pld or {}

                        def _is_real_value(v) -> bool:
                            return v is not None and str(v).strip().lower() != "none"

                        raw_stop = pld.get("stop_price")
                        raw_target = pld.get("target_price")
                        raw_sl_pct = pld.get("sl_pct")

                        if _is_real_value(raw_stop) or _is_real_value(raw_target) or _is_real_value(raw_sl_pct):
                            intent_data = {
                                "stop_price": raw_stop if _is_real_value(raw_stop) else None,
                                "target_price": raw_target if _is_real_value(raw_target) else None,
                                "sl_pct": raw_sl_pct if _is_real_value(raw_sl_pct) else None,
                                "timestamp": get_clock().now_sec()
                            }
                            self._pending_intent_data[result.rid] = intent_data
                            LOG.info(
                                f"CAPTURED_INTENT_DATA for {result.rid}: {intent_data}")
                        else:
                            LOG.debug(
                                f"SKIP_INTENT_CACHE for {result.rid}: all values are None")
                    except Exception as e:
                        LOG.error(f"Failed to capture intent data: {e}")
            elif msg.verb == "TRADE_EXECUTED":
                result = self._handle_canonical_fill_ingress(
                    msg,
                    fill_source=str((msg.pld or {}).get(
                        "fill_source") or "trade_executed"),
                    process_result=False,
                )
            elif msg.verb == "ORDER_FILL":
                result = self._handle_canonical_fill_ingress(
                    msg,
                    fill_source=str((msg.pld or {}).get(
                        "fill_source") or "order_fill"),
                    process_result=False,
                )
            elif msg.verb == "ORDER_STATE_CHANGED":
                self._on_order_state_changed(msg)
            elif msg.verb == "EXECUTION_CLOSE_RECONCILED":
                self._on_execution_close_reconciled(msg)
            elif msg.verb == "ORDER_CANCELLED":
                self._handle_cancel_event(msg)
            elif msg.verb == "CLOSE":
                symbol = msg.pld.get("symbol") if msg.pld else None
                hardening = get_execution_truth_hardening(self)
                skip_close_guard = bool(
                    (msg.pld or {}).get("close_guard_prevalidated"))
                if symbol and hardening is not None and not skip_close_guard:
                    close_decision = hardening.evaluate_close_command(
                        symbol=symbol,
                        requested_qty=(msg.pld or {}).get("qty"),
                        position_signature=self._get_portfolio_position_signature(
                            symbol),
                        rid=getattr(msg, "rid", None),
                    )
                    if close_decision.suppress:
                        LOG.warning(
                            "[CMD:CLOSE] Suppressed duplicate close propagation for %s: %s (%s)",
                            symbol,
                            close_decision.reason,
                            close_decision.key,
                        )
                        if journal is not None:
                            journal.record_transition(
                                event_name="HARDENING:CMD_CLOSE_SUPPRESSED",
                                source_component="execution_position.fsm",
                                source_path="execution:close_source_guard",
                                event_origin_type="execution",
                                truth_owner="ExecPosFSM",
                                payload=msg.pld or {},
                                rid=getattr(msg, "rid", None),
                                before=before,
                                after=snapshot_execpos_state(self, symbol),
                                notes=[
                                    close_decision.reason,
                                    f"guard_key={close_decision.key}",
                                    f"requested_qty={normalize_close_qty((msg.pld or {}).get('qty'))}",
                                ],
                            )
                        return None
                if symbol:
                    manage = self.manage_flows.get(symbol)
                    if manage:
                        manage._closing_position = True
                        manage._closing_position_ts = get_clock().now_sec()
                        print(
                            f" [CMD:CLOSE] Set closing flag for {symbol} to prevent bracket race")
                result = close_flow.handle(msg)
            else:
                result = manage_flow.handle(msg)

            self._process_flow_result(result)
            restore_signature_after = self._restore_semantics_signature(symbol)
            if restore_signature_after != restore_signature_before:
                self._persist_restore_artifact_snapshot(
                    trigger=f"transition:{str(msg.verb).lower()}",
                    allow_empty=True,
                )

            return result
        finally:
            if journal is not None:
                notes = []
                if result is not None:
                    notes.append(f"result={result.op}:{result.verb}")
                journal.record_transition(
                    event_name=f"{msg.op}:{msg.verb}",
                    source_component="execution_position.fsm",
                    source_path="execution:execpos_handle",
                    event_origin_type="execution",
                    truth_owner="ExecPosFSM",
                    payload=msg.pld or {},
                    rid=getattr(msg, "rid", None),
                    before=before,
                    after=snapshot_execpos_state(
                        self, (msg.pld or {}).get("symbol")),
                    notes=notes,
                )

    async def _execute_decision(self, decision: Message):
        """Phase 14A: Thin dispatcher  delegates to sub-module executors."""
        if not self.adapter:
            return

        # --- CRITICAL SAFETY GUARDRAIL ---
        domain_mode = "testnet"
        if hasattr(self.config, "get_domain_mode"):
            try:
                domain_mode = self.config.get_domain_mode("execution_position")
            except Exception:
                if hasattr(self.config, "trading_mode"):
                    domain_mode = self.config.trading_mode
        elif hasattr(self.config, "trading_mode"):
            domain_mode = self.config.trading_mode

        if domain_mode == "testnet":
            if "testnet" not in self.adapter.base_url:
                LOG.critical(
                    " GUARDRAIL TRIGGERED: Domain mode is TESTNET, but adapter is configured for LIVE API! Order BLOCKED.")
                fatal_msg = Message(
                    op="ERR", verb="FATAL_CONFIG_MISMATCH", src="execution_position",
                    dst="monitoring", rid="config_check",
                    pld={"reason": "Testnet mode with live execution URL"},
                    why="Testnet mode with live execution URL")
                await emit_compat(self.fsm, fatal_msg, logger=LOG)
                return
        elif domain_mode == "live":
            LOG.warning(
                " LIVE execution mode - ensure you know what you're doing!")

        # --- END GUARDRAIL ---

        try:
            # Phase 14A: Dispatch to sub-module executors
            if decision.verb == "CANCEL_ORDER":
                await self._close_exec.execute_cancel_order(decision)
                return

            if decision.verb in ("CLOSE", "CLOSE_POSITION"):
                decision_pld = decision.pld or {}
                symbol = decision_pld.get("symbol")
                trigger = str(decision_pld.get("trigger") or "")
                hardening = get_execution_truth_hardening(self)
                if (
                    symbol
                    and hardening is not None
                    and trigger != "CMD:CLOSE"
                ):
                    close_decision = hardening.evaluate_non_cmd_close_decision(
                        symbol=symbol,
                        requested_qty=decision_pld.get("qty"),
                        position_signature=self._get_portfolio_position_signature(
                            symbol),
                        rid=getattr(decision, "rid", None),
                    )
                    if close_decision.suppress:
                        LOG.warning(
                            "[DEC:CLOSE] Suppressed non-CMD duplicate close execution for %s: %s (%s)",
                            symbol,
                            close_decision.reason,
                            close_decision.key,
                        )
                        journal = get_shadow_journal(self)
                        if journal is not None:
                            journal.record_transition(
                                event_name="HARDENING:NON_CMD_DEC_CLOSE_SUPPRESSED",
                                source_component="execution_position.fsm",
                                source_path="execution:non_cmd_close_guard",
                                event_origin_type="execution",
                                truth_owner="ExecPosFSM",
                                payload=decision_pld,
                                rid=getattr(decision, "rid", None),
                                before=snapshot_execpos_state(self, symbol),
                                after=snapshot_execpos_state(self, symbol),
                                notes=[
                                    close_decision.reason,
                                    f"guard_key={close_decision.key}",
                                    f"decision_why={decision.why}",
                                    f"requested_qty={normalize_close_qty(decision_pld.get('qty'))}",
                                ],
                            )
                        return
                await self._close_exec.execute_close(decision)
                return

            if decision.verb == "PLACE_ORDER":
                await self._close_exec.execute_place_order(decision)
                return

            # Default: OPEN verb
            await self._open_exec.execute_open(decision)

        except Exception as e:
            LOG.error(
                f" Adapter failed to execute decision {decision.verb} for "
                f"{decision.pld.get('symbol') if decision.pld else 'unknown'}: {e}",
                exc_info=True)

            if self.alert_manager:
                try:
                    symbol = decision.pld["symbol"] if decision.pld and "symbol" in decision.pld else "unknown"
                    error_key = f"exec_error_{symbol}"
                    if not hasattr(self, '_exec_error_counts'):
                        self._exec_error_counts = {}
                    self._exec_error_counts[error_key] = (
                        self._exec_error_counts.get(error_key, 0) + 1)
                    if self._exec_error_counts[error_key] >= 2:
                        self.alert_manager.check_circuit_breaker(True, 600)
                except Exception as alert_e:
                    LOG.error(
                        f"Error triggering execution error alert: {alert_e}")

            decision_pld = decision.pld or {}
            reason_code = "ADAPTER_ERROR"
            reason_text = str(e)[:200]
            order_reject_metadata = {
                "error": str(e),
                "decision_verb": decision.verb,
            }
            terminal_payload_extra: dict[str, Any] = {}
            if isinstance(e, UncertainSubmitRecoveryError):
                reason_code = "UNCERTAIN_SUBMIT_UNRECOVERED"
                reason_text = (
                    "Submit status unknown and recovery by clientOrderId failed: "
                    f"{e.original_error}"
                )[:200]
                order_reject_metadata.update({
                    "uncertain_submit": True,
                    "client_order_id": e.entry_id,
                    "binance_code": e.binance_code,
                    "recovery_attempts": e.attempts,
                    "original_exception_class": type(e.original_error).__name__,
                })
                terminal_payload_extra = {
                    "uncertain_submit": True,
                    "client_order_id": e.entry_id,
                    "binance_code": e.binance_code,
                    "recovery_attempts": e.attempts,
                    "original_exception_class": type(e.original_error).__name__,
                }

            order_logger.write({
                "rid": decision.rid,
                "event_type": "ORDER_REJECTED",
                "symbol": decision_pld.get("symbol", ""),
                "side": decision_pld.get("side", "NONE"),
                "quantity": float(decision_pld.get("qty", 0)),
                "nrr_code": "NRR-015",
                "why": f"Adapter execution failed: {reason_text}",
                "source_fsm": "ExecPosFSM",
                "origin_class": "execution_adapter",
                "metadata": order_reject_metadata,
            })

            try:
                await emit_canonical_terminal_order_event(
                    fsm=self.fsm,
                    event_name="EVT:ORDER_REJECTED",
                    payload={
                        "symbol": decision_pld.get("symbol", ""),
                        "side": decision_pld.get("side", "NONE"),
                        "reason_code": reason_code,
                        "reason_text": reason_text,
                        "exception_class": type(e).__name__,
                        "origin_class": "execution_adapter",
                        "ts_ms": get_clock().now_ms(),
                        **terminal_payload_extra,
                    },
                    rid=decision.rid,
                    src="execution_position",
                    dst="observability",
                    why="adapter_execution_failed",
                    logger=LOG,
                    write_wal=True,
                    fallback_ts_ms=get_clock().now_ms(),
                )
            except Exception as emit_e:
                LOG.warning(
                    "Failed to emit EVT:ORDER_REJECTED canonical seam: %s", emit_e)

            exec_failed_msg = Message(
                op="ERR", verb="EXECUTION_FAILED", src="execution_position",
                dst="monitoring", rid=decision.rid,
                pld={"error": str(
                    e), "original_decision": decision.model_dump()},
                why="Execution failed due to adapter error")
            await emit_compat(self.fsm, exec_failed_msg, logger=LOG)

    # Phase 14.2: get_metrics
    #  extracted to HealthMetricsMixin (health_metrics.py)

    # ---- GATE: SYMBOL_TIDY entry gating ----
    def _on_symbol_tidy_event(self, payload: Dict[str, Any]) -> None:
        """Phase 14A: Delegated to EPEventHandlers."""
        self._evt_handlers.on_symbol_tidy_event(payload)

    def _entry_tidy_gate_allow(self, symbol: str) -> bool:
        """Phase 14A: Delegated to EPEventHandlers."""
        return self._evt_handlers.entry_tidy_gate_allow(symbol)

    async def _handle_order_timeout(self, deadline):
        """Phase 14A: Delegated to EntryManager."""
        await self._entry_mgr.handle_order_timeout(deadline)

    def open_flow(self, symbol: str) -> OpenFlowFSM:
        """Get or create OpenFlowFSM for the given symbol."""
        open_f, _, _ = self._get_or_create_flows(symbol)
        return open_f

    def manage_flow(self, symbol: str) -> ManageFlowFSM:
        """Get or create ManageFlowFSM for the given symbol."""
        _, manage_f, _ = self._get_or_create_flows(symbol)
        return manage_f

    def close_flow(self, symbol: str) -> CloseFlowFSM:
        """Get or create CloseFlowFSM for the given symbol."""
        _, _, close_f = self._get_or_create_flows(symbol)
        return close_f

    def _cancel_entry_reservation(self, rid: str) -> None:
        """Clear OrderIndex reservation when an OPEN path is blocked fail-closed."""
        try:
            # type: ignore[attr-defined]
            if hasattr(self.fsm, "order_index") and self.fsm.order_index:
                self.fsm.order_index.cancel_reservation(
                    str(rid))  # type: ignore[attr-defined]
        except Exception:
            pass

    @staticmethod
    def _read_position_amt(pos: Dict[str, Any]) -> Any:
        """Read position amount from either canonical or legacy field name.

        The position_tracking domain emits ``net_position`` (the canonical
        field per ``portfolio_state_v1.json``).  Some external/Binance-direct
        payloads may still carry ``positionAmt``.  We check both, preferring
        ``net_position``.
        """
        val = pos.get("net_position")
        if val is not None:
            return val
        return pos.get("positionAmt")

    def _get_portfolio_state_for_symbol(self, symbol: str) -> str:
        """Best-effort portfolio snapshot for split-brain guard telemetry."""
        portfolio = self._latest_portfolio_state or {}
        if not portfolio:
            return "UNKNOWN"

        positions = portfolio.get("positions")
        if not isinstance(positions, list):
            return "UNKNOWN"

        for pos in positions:
            if not isinstance(pos, dict):
                continue
            if str(pos.get("symbol") or "").upper() != symbol.upper():
                continue
            qty_raw = self._read_position_amt(pos)
            if qty_raw is None:
                qty_raw = "0"
            try:
                qty = Decimal(str(qty_raw))
            except Exception:
                return "UNKNOWN"
            if abs(qty) <= Decimal("1e-9"):
                return "FLAT"
            return "LONG" if qty > 0 else "SHORT"

        return "FLAT"

    def _get_portfolio_position_signature(self, symbol: str) -> str:
        """Close-guard state basis derived from current portfolio truth."""
        signature = build_position_signature(
            self._latest_portfolio_state or {}, symbol)
        return str(signature or "UNKNOWN")

    def _emit_execution_bus_event(self, topic: str, payload: Dict[str, Any]) -> None:
        why = str(payload.get("why") or "execution:observability")
        event_payload = dict(payload)
        event_payload.setdefault("ts_ms", int(get_clock().now_sec() * 1000))
        event_payload.setdefault("why", why)
        try:
            self.bus.emit(
                topic,
                event_payload,
                why=why,
            )
        except Exception:
            pass
        try:
            self._emit_observability_event(
                topic.replace("EVT:", ""),
                event_payload,
            )
        except Exception:
            pass

    def _local_open_guard(self, msg: Message, manage_flow: ManageFlowFSM) -> Optional[Message]:
        """Fail closed when local execution state still owns an unresolved lifecycle."""
        has_active_lifecycle = (
            manage_flow.has_active_lifecycle()
            if hasattr(manage_flow, "has_active_lifecycle")
            else str(getattr(getattr(manage_flow, "state", None), "value", manage_flow.state)) != "FLAT"
        )
        if not has_active_lifecycle:
            return None

        symbol = (msg.pld or {}).get("symbol", "")
        local_state = str(
            getattr(getattr(manage_flow, "state", None), "value", "UNKNOWN"))
        portfolio_state = self._get_portfolio_state_for_symbol(symbol)
        divergence_detected = portfolio_state == "FLAT" and local_state != "FLAT"
        tracked_rid = self._last_lifecycle_rid_by_symbol.get(symbol)
        lifecycle_id = self._last_lifecycle_ikey_by_symbol.get(symbol)
        why = "execution:local_manage_state_conflict"
        payload = {
            "ts_ms": int(get_clock().now_sec() * 1000),
            "symbol": symbol,
            "rid": msg.rid,
            "lifecycle_id": lifecycle_id,
            "tracked_rid": tracked_rid,
            "block_reason": "local_manage_state_conflict",
            "reason": "local_manage_state_conflict",
            "current_local_state": local_state,
            "local_manage_state": local_state,
            "portfolio_truth_state": portfolio_state,
            "portfolio_state": portfolio_state,
            "divergence_detected": divergence_detected,
            "has_active_lifecycle": has_active_lifecycle,
            "closing_position": bool(getattr(manage_flow, "_closing_position", False)),
            "position_qty": (
                str(getattr(manage_flow, "position_qty", None))
                if getattr(manage_flow, "position_qty", None) is not None
                else None
            ),
            "entry_order_id": getattr(manage_flow, "entry_order_id", None),
            "entry_client_order_id": getattr(manage_flow, "entry_client_order_id", None),
            "sl_order_id": getattr(manage_flow, "sl_order_id", None),
            "tp_order_id": getattr(manage_flow, "tp_order_id", None),
            "tp1_order_id": getattr(manage_flow, "tp1_order_id", None),
            "tp2_order_id": getattr(manage_flow, "tp2_order_id", None),
            "why": why,
        }

        self._emit_execution_bus_event("EVT:EXECUTION_GUARD_BLOCKED", payload)
        if divergence_detected:
            self._emit_execution_bus_event(
                "EVT:EXECUTION_DIVERGENCE_DETECTED",
                {
                    "ts_ms": payload["ts_ms"],
                    "symbol": symbol,
                    "current_rid": msg.rid,
                    "tracked_rid": tracked_rid,
                    "lifecycle_id": lifecycle_id,
                    "local_manage_state": local_state,
                    "portfolio_state": portfolio_state,
                    "divergence_type": "portfolio_flat_vs_local_nonflat",
                    "why": "execution:divergence_detected",
                },
            )

        return Message(
            op="ERR",
            verb="OPEN",
            src=msg.dst,
            dst=msg.src,
            rid=msg.rid,
            why="OPEN_GUARD_FAIL",
            pld=payload,
        )

    def _check_exposure_fail_closed(self, msg: Message) -> Optional[Message]:
        """Phase 14A: Delegated to ExposureManager."""
        return self._exposure_mgr.check_exposure_fail_closed(msg)

    async def _emit_error_async(self, msg: Message) -> None:
        """Asynchronously emit an error message."""
        try:
            await emit_compat(self.fsm, msg, logger=aget(self, "logger", None))
        except Exception as e:
            LOG.exception(
                "Failed to emit error message via emit_compat: %r", e)

    def _handle_fill_event(self, msg: Message) -> None:
        """Phase 14A: Delegated to ExposureManager."""
        self._exposure_mgr.handle_fill_event(msg)

    def _handle_cancel_event(self, msg: Message) -> None:
        """Phase 14A: Delegated to ExposureManager."""
        self._exposure_mgr.handle_cancel_event(msg)

    async def _emit_exposure_update_async(self, msg: Message) -> None:
        """Phase 14A: Delegated to ExposureManager."""
        await self._exposure_mgr.emit_exposure_update_async(msg)

    async def _check_shadow_notional(self) -> None:
        """Phase 14A: Delegated to ExposureManager."""
        await self._exposure_mgr.check_shadow_notional()

    def _emit_observability_event(self, event_type: str, data: dict) -> None:
        """
        PHASE C: Emit structured observability events.

        Events are logged as JSON for dashboards and alerting.

        Args:
            event_type: Event identifier (e.g., 'TP_SL_RETRY_ATTEMPT', 'RECONCILE_CANCELLED')
            data: Event data dict (symbol, count, reason, etc.)
        """
        event = {
            "timestamp_utc": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "rid": (
                data.get("rid")
                or (
                    self.current_decision.rid
                    if hasattr(self, 'current_decision') and self.current_decision
                    else "N/A"
                )
            ),
            **data
        }
        LOG.info(f" [EVENT] {event_type}: {event}", extra={"event": event})

    async def _preflight_position_check(self, symbol: str) -> bool:
        """Phase 14A: Delegated to BracketManager."""
        return await self._bracket_mgr.preflight_position_check(symbol)

    async def _place_deferred_brackets(
        self, entry_order_id: str, bracket_data: Dict[str, Any]
    ) -> None:
        """Phase 14A: Delegated to BracketManager."""
        await self._bracket_mgr.place_deferred_brackets(entry_order_id, bracket_data)

    async def _cleanup_loop(self) -> None:
        """Periodic orphaned-order cleanup loop (interval from config)."""
        while True:
            try:
                # STRICT SSOT: interval validated by schema (ge=5)
                interval = int(self._orphan_cfg["periodic_interval_sec"])
                # DET-BT-13: Use clock.sleep_sec for deterministic backtest
                await get_clock().sleep_sec(interval)
                await self.order_guardian.cleanup_orphans()
                self._orphan_metrics["loops"] += 1
            except asyncio.CancelledError:
                self._orphan_metrics["errors"] += 1
            except Exception as e:
                LOG.debug(f"cleanup loop error: {e}")
                self._orphan_metrics["errors"] += 1

    async def _startup_order_guardian_reconcile(self) -> None:
        """
        Startup reconciliation: Link existing orders and positions for OrderGuardian.

        This ensures OrderGuardian has accurate tracking of existing orders/positions
        after restart, enabling proper orphan detection and cleanup.
        """
        fresh_orders: List[Dict[str, Any]] = []
        position_symbols: Set[str] = set()
        pre_cleanup_order_symbols: Set[str] = set()
        fresh_order_symbols: Set[str] = set()
        guardian_symbols: Set[str] = set()
        positions_fetch_succeeded = False
        pre_cleanup_open_orders_fetch_succeeded = False
        post_cleanup_open_orders_fetch_succeeded = False
        guardian_link_existing_invoked = False
        guardian_cleanup_invoked = False
        runtime_truth: Dict[str, Any] = {
            "summary": {
                "symbols_reconstructed": 0,
                "order_index_registrations": 0,
                "unresolved_symbols": 0,
            },
            "records": [],
        }
        restore_authoritative = ExecutionPositionRestoreAuthoritativeStatus()
        restore_dark_read = ExecutionPositionRestoreDarkReadStatus()
        execution_truth_cache = self._execution_truth_cache_status()
        restore_artifact_write_attempted = False
        restore_artifact_write_succeeded = False
        failure_reason: Optional[str] = None
        try:
            LOG.info(" Starting OrderGuardian startup reconciliation...")
            fresh_orders: List[Dict[str, Any]] = []
            restore_authoritative = self._run_restore_artifact_authoritative_read()
            authoritative_symbols = {
                str(item.symbol).strip().upper()
                for item in restore_authoritative.symbol_statuses
                if str(item.symbol).strip()
            }

            #  FIX: First link existing orders from REST API for all symbols with positions
            if self.adapter:
                try:
                    positions = await self.adapter.get_open_positions()
                    positions_fetch_succeeded = True
                    symbols_with_positions = set()

                    # Convert positions to dict if needed and collect symbols
                    positions_list = [
                        p.to_dict() if hasattr(p, 'to_dict') else (
                            p.__dict__ if not isinstance(p, dict) else p)
                        for p in positions
                    ]

                    for pos in positions_list:
                        symbol = pos.get("symbol")
                        if symbol:
                            position_symbols.add(str(symbol).strip().upper())
                            symbols_with_positions.add(symbol)

                    # Also check for symbols with open orders
                    all_orders = await self.adapter.get_open_orders()
                    pre_cleanup_open_orders_fetch_succeeded = True
                    orders_list = [
                        o.to_dict() if hasattr(o, 'to_dict') else (
                            o.__dict__ if not isinstance(o, dict) else o)
                        for o in all_orders
                    ]

                    for order in orders_list:
                        symbol = order.get("symbol")
                        if symbol:
                            pre_cleanup_order_symbols.add(
                                str(symbol).strip().upper())
                            symbols_with_positions.add(symbol)

                    guardian_symbols.update(self._collect_guardian_symbols())
                    symbols_with_positions.update(guardian_symbols)
                    symbols_with_positions.update(authoritative_symbols)

                    # Link existing orders for each symbol
                    guardian_link_existing_invoked = bool(
                        symbols_with_positions)
                    for symbol in symbols_with_positions:
                        await self.order_guardian.link_existing_from_rest(symbol)
                        LOG.debug(f" Linked existing orders for {symbol}")

                    LOG.info(
                        f" Linked existing orders for {len(symbols_with_positions)} symbols")

                except Exception as e:
                    LOG.warning(
                        f"Failed to link existing orders during startup: {e}")

            # Then run cleanup to remove orphans
            guardian_cleanup_invoked = True
            await self.order_guardian.cleanup_orphans()
            if self.adapter:
                try:
                    fresh_open_orders = await self.adapter.get_open_orders()
                    post_cleanup_open_orders_fetch_succeeded = True
                    fresh_orders = [
                        o.to_dict() if hasattr(o, 'to_dict') else (
                            o.__dict__ if not isinstance(o, dict) else o)
                        for o in fresh_open_orders
                    ]
                    for order in fresh_orders:
                        symbol = str(order.get("symbol") or "").strip().upper()
                        if symbol:
                            fresh_order_symbols.add(symbol)
                except Exception as e:
                    LOG.warning(
                        f"Failed to fetch fresh open orders after startup reconcile: {e}")
            runtime_truth = self._startup_reconstruct_runtime_bracket_truth(
                fresh_orders)
            restore_authoritative = self._finalize_restore_authoritative_status(
                restore_authoritative,
                positions_fetch_succeeded=positions_fetch_succeeded,
                position_symbols=position_symbols,
            )
            restore_dark_read = self._run_restore_artifact_dark_read_comparison()
            restore_artifact_write_attempted = True
            restore_artifact_write_succeeded = self._persist_restore_artifact_snapshot(
                trigger="startup_order_guardian_reconcile",
                allow_empty=True,
            )
            LOG.info(" OrderGuardian startup reconciliation completed")
        except Exception as e:
            failure_reason = type(e).__name__
            LOG.error(f" OrderGuardian startup reconciliation failed: {e}")
        finally:
            self._append_startup_truth_artifact_record(
                trigger="startup_order_guardian_reconcile",
                failure_reason=failure_reason,
                input_snapshot={
                    "positions_fetch_succeeded": positions_fetch_succeeded,
                    "pre_cleanup_open_orders_fetch_succeeded": pre_cleanup_open_orders_fetch_succeeded,
                    "post_cleanup_open_orders_fetch_succeeded": post_cleanup_open_orders_fetch_succeeded,
                    "guardian_link_existing_invoked": guardian_link_existing_invoked,
                    "guardian_cleanup_invoked": guardian_cleanup_invoked,
                    "position_symbols_observed": sorted(position_symbols),
                    "pre_cleanup_order_symbols_observed": sorted(pre_cleanup_order_symbols),
                    "guardian_symbols_observed": sorted(guardian_symbols),
                    "fresh_order_symbols_observed": sorted(fresh_order_symbols),
                },
                symbols_considered=sorted(
                    position_symbols
                    | pre_cleanup_order_symbols
                    | guardian_symbols
                    | fresh_order_symbols
                    | {
                        str(item.symbol).strip().upper()
                        for item in restore_authoritative.symbol_statuses
                        if str(item.symbol).strip()
                    }
                ),
                fresh_open_order_count=len(fresh_orders),
                runtime_truth=runtime_truth,
                restore_artifact_write_attempted=restore_artifact_write_attempted,
                restore_artifact_write_succeeded=restore_artifact_write_succeeded,
                restore_authoritative=restore_authoritative,
                restore_dark_read=restore_dark_read,
                execution_truth_cache=execution_truth_cache,
            )
    # Phase 14.2: handle_tick_async, handle_tick, is_healthy
    #  extracted to HealthMetricsMixin (health_metrics.py)
