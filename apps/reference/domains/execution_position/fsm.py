"""
FSMP-P1-T02: Orchestration of 3 FSM flows for execution_position domain.

This FSM acts as a wrapper, routing commands to the appropriate flow FSM
(Open, Manage, Close) on a per-symbol basis. It integrates directly with
the vFoundation BinanceAdapter to execute trades in the configured environment.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

# T2B-04: Time abstraction for deterministic testing
from apps.reference.core.time import get_clock
from typing import Dict, Any, Optional, Tuple, Set, List, TYPE_CHECKING

from vfoundation.core.fsm_emit_compat import Message, emit_compat
from vfoundation.dr import wal
from apps.reference.adapters.binance_adapter import BinanceAPIError
from apps.reference.config_models import (
    AuroraConfig,
    PositionPolicySidecarConfig,
)
from apps.reference.utils.accessors import aget, dget

from .fsm_open import OpenFlowFSM
from .fsm_manage import ManageFlowFSM, ManageState
from .fsm_close import CloseFlowFSM, CloseState
from .exposure_guard import ExposureGuard
from .watchdog import OrderTimeoutWatchdog
from .utils import (
    BoundedEventDeduper,
)
from .aurora_log_adapter import AuroraLogAdapter
from .terminal_order_contracts import (
    emit_canonical_terminal_order_event,
)
from .metrics_collector import MetricsCollector
from .intent_boundary_audit import IntentBoundaryAudit
from apps.reference.telemetry.order_logger import order_logger

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

# TASK50: Import qty normalizer for fail-closed quantity validation
from vfoundation.obs.domain_bridge import DomainBridge

# PHASE4: Pending brackets WAL persistence
from apps.reference.domains.execution_position.pending_brackets_wal import (
    CriticalStartupError,
    write_pending_brackets_cleared,
    read_pending_brackets_from_wal,
)

# Phase 14A: Sub-module imports (Strangler Fig decomposition)
from apps.reference.domains.execution_position.leverage_config import LeverageConfigManager
from apps.reference.domains.execution_position.entry_manager import EntryManager
from apps.reference.domains.execution_position.exposure_manager import ExposureManager
from apps.reference.domains.execution_position.intent_router import IntentRouter
from apps.reference.domains.execution_position.event_handlers import EPEventHandlers
from apps.reference.domains.execution_position.close_executor import CloseExecutor
from apps.reference.domains.execution_position.open_executor import OpenExecutor, UncertainSubmitRecoveryError
from apps.reference.domains.execution_position.bracket_manager import BracketManager
from apps.reference.domains.execution_position.bracket_ownership import BracketOwnership
from apps.reference.domains.execution_position.fill_ingress_coordinator import FillIngressCoordinator
from apps.reference.domains.execution_position.bracket_health import BracketHealth
from apps.reference.domains.execution_position.startup_truth_orchestrator import StartupTruthOrchestrator
from apps.reference.domains.execution_position.authoritative_restore_apply import AuthoritativeRestoreApply
from apps.reference.domains.execution_position.startup_reconstruction import StartupReconstruction
from apps.reference.domains.execution_position.position_policy_sidecar import (
    CLOSE_REQUEST_COMMAND_TOPIC,
    PositionPolicyCloseRequest,
    PositionPolicySidecar,
)
from apps.reference.domains.execution_position.position_policy_mediator import PositionPolicyMediator
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
    ExecutionPositionRestoreAuthoritativeStatus,
    ExecutionPositionRestoreAuthoritativeSymbolStatus,
    ExecutionPositionRestoreDarkReadStatus,
    ExecutionPositionRestoreLifecycleRecord,
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
        no_order_observation_mode: bool = False,
    ):
        if isinstance(config, dict):
            raise TypeError("ExecPosFSM requires typed AuroraConfig, got dict")
        if config is None:
            raise ValueError(
                f"CRITICAL: {self.__class__.__name__} requires valid AuroraConfig. "
                "Refusing to start with empty defaults."
            )
        if no_order_observation_mode and not shadow_mode:
            raise ValueError(
                "agent_bridge_observation_only requires shadow_mode=True; "
                "refusing an execution-capable composition"
            )
        self.config = config
        self.no_order_observation_mode = bool(no_order_observation_mode)
        self.runtime_mode = (
            "agent_bridge_observation_only"
            if self.no_order_observation_mode
            else "normal"
        )
        self.mode = self.runtime_mode
        self.no_order_blocked_action_count = 0

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
        self._open_guard_bypass_lock = threading.Lock()
        self._prevalidated_open_rids: Set[str] = set()

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

        self._bracket_ownership = BracketOwnership(self)
        self._bracket_health = BracketHealth(self)
        self._startup_truth_orchestrator = StartupTruthOrchestrator(self)
        self._fill_ingress_coordinator = FillIngressCoordinator(self)
        self._authoritative_restore_apply = AuthoritativeRestoreApply(
            self)  # Package 6B
        self._startup_reconstruction = StartupReconstruction(
            self)  # Package 6C

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
        self._close_accounting_truth_by_symbol: Dict[str, Dict[str, Any]] = {}
        self._close_fill_trade_ids_by_symbol_order: Dict[str, set[str]] = {}

        self._position_policy_mediator = PositionPolicyMediator(self)

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
            except CriticalStartupError:
                raise
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
        self._open_attribution_by_symbol: Dict[str, Dict[str, Any]] = {}
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
        self._guardian_emit_tidy_monitoring_event: bool = bool(
            self._guardian_cfg["emit_tidy_monitoring_event"])
        self._guardian_emit_tidy_event: bool = bool(
            self._guardian_cfg["emit_tidy_event"])
        self._guardian_poll_interval_ms: int = int(
            dget(self._guardian_cfg, "poll_interval_ms", 500))
        self._fsm_cleanup_enabled: bool = self._resolve_fsm_periodic_cleanup_enabled()

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
        if not self.no_order_observation_mode:
            self.bus.listen("EVT:TRADE_INTENT_PROPOSED",
                            self._on_trade_intent_proposed)
        self.bus.listen("EVT:TRADE_INTENT_REJECTED",
                        self._on_trade_intent_rejected)
        # LLM external intent path: wire CMD:EXTERNAL_OPEN_REQUEST_V1
        if not self.no_order_observation_mode:
            self.bus.listen("CMD:EXTERNAL_OPEN_REQUEST_V1",
                            self._on_external_open_request)
            self.bus.listen("CMD:EXTERNAL_POSITION_CLOSE_REQUEST_V1",
                            self._on_external_position_close_request)
            self.bus.listen("CMD:EXTERNAL_BRACKET_AMEND_REQUEST_V1",
                            self._on_external_bracket_amend_request)
            self.bus.listen(
                CLOSE_REQUEST_COMMAND_TOPIC,
                self._position_policy_mediator.on_position_policy_close_request,
            )
        else:
            LOG.warning(
                "NO_ORDER_OBSERVATION_MODE_ACTIVE: consequential execution "
                "listeners are not registered; adapter=%s",
                self.adapter,
            )

        # Phase 14D: DomainBridge for orphan domains
        self._domain_bridge = DomainBridge("execution_position", bus=self.bus)
        self._domain_bridge.register_health_fn(self.is_healthy)
        self._last_status_ts = 0.0

        # Async loop used for guardian and adapter operations (set later)
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None

        # Initialize order timeout watchdog
        # T5A.1-SSOT: canonical path is trading.execution.watchdog (trading.yaml only).
        # system.yaml execution.watchdog block removed 2026-05-07 — do not add it back.
        watchdog_config = self._get_config_value(
            ["trading", "execution", "watchdog"])

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
        # T5A.1-SSOT: sole canonical source is trading.execution.watchdog
        ttl_source = "trading.execution.watchdog"
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
                    self.adapter,
                    config=self.config,
                    poll_interval_ms=poll_interval_ms,
                    bus=self.bus,
                    emit_tidy_monitoring_event=self._guardian_emit_tidy_monitoring_event,
                )
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
                emit_tidy_monitoring_event=self._guardian_emit_tidy_monitoring_event,
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

    # === PACKAGE 0: PENDING-ENTRY CONTOUR SANCTIONED TRUTH BOUNDARY ===

    def get_pending_entry_metadata(self, order_id: str):
        return self._pending_entry_meta.get(str(order_id))

    def remove_pending_entry_metadata(self, order_id: str):
        return self._pending_entry_meta.pop(str(order_id), None)

    def enqueue_supersede(self, symbol: str, queued_data: dict) -> None:
        self._supersede_queue[symbol] = queued_data

    def dequeue_supersede(self, symbol: str) -> dict:
        return self._supersede_queue.pop(symbol, None)

    def is_supersede_canceling(self, symbol: str) -> bool:
        return symbol in self._supersede_canceling

    def mark_supersede_canceling(self, symbol: str) -> None:
        self._supersede_canceling.add(symbol)

    def clear_supersede_canceling(self, symbol: str) -> None:
        self._supersede_canceling.discard(symbol)
    # ====================================================================

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
        if self._block_no_order_action("cancel_order"):
            return {"status": "BLOCKED", "reason": "no_order_observation_mode"}
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
        if self._block_no_order_action("trade_intent_proposed"):
            return
        self._intent_router.on_trade_intent_proposed(msg)

    def _on_trade_intent_rejected(self, msg: Message) -> None:
        """Phase 14A: Delegated to IntentRouter."""
        self._intent_router.on_trade_intent_rejected(msg)

    def _on_external_open_request(self, msg: Message) -> None:
        """Phase 14A: Delegated to IntentRouter (LLM external intent path)."""
        if self._block_no_order_action("external_open_request"):
            return
        self._intent_router.on_external_open_request(msg)

    def _on_external_position_close_request(self, msg: Message) -> None:
        """Phase 14A: Delegated to IntentRouter (LLM external close path)."""
        if self._block_no_order_action("external_close_request"):
            return
        self._intent_router.on_external_position_close_request(msg)

    def _on_external_bracket_amend_request(self, msg: Message) -> None:
        """Phase 14A: Delegated to IntentRouter (LLM external bracket amend path)."""
        if self._block_no_order_action("external_bracket_amend_request"):
            return
        self._intent_router.on_external_bracket_amend_request(msg)

    def _block_no_order_action(self, action: str) -> bool:
        """Return true and record telemetry when an execution action is blocked."""
        if not bool(getattr(self, "no_order_observation_mode", False)):
            return False
        self.no_order_blocked_action_count = int(
            getattr(self, "no_order_blocked_action_count", 0)
        ) + 1
        LOG.warning(
            "NO_ORDER_ACTION_BLOCKED action=%s runtime_mode=%s",
            action,
            getattr(self, "runtime_mode", "unknown"),
        )
        return True

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

    # [6B] _restore_artifact_mode was a dead duplicate of startup_truth_orchestrator._restore_artifact_mode
    # (zero callers in ExecPosFSM). Removed in Package 6B. The live copy is in StartupTruthOrchestrator.

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

    def _clear_pending_brackets(
        self,
        entry_order_id: str,
        *,
        reason: str,
        symbol: Optional[str] = None,
        persist_snapshot: bool = False,
    ) -> bool:
        """Sanctioned mutator for pending deferred bracket state."""
        entry_order_id_str = str(entry_order_id or "").strip()
        if not entry_order_id_str:
            return False

        bracket_data = self._pending_brackets.pop(entry_order_id_str, None)
        if not isinstance(bracket_data, dict):
            return False

        symbol_value = str(symbol or bracket_data.get(
            "symbol") or "").strip().upper()
        try:
            write_pending_brackets_cleared(
                entry_order_id=entry_order_id_str,
                reason=reason,
                symbol=symbol_value,
            )
        except Exception as exc:
            LOG.warning(
                "Failed to clear pending brackets entry_order_id=%s reason=%s error=%s",
                entry_order_id_str,
                reason,
                exc,
            )

        if persist_snapshot:
            self._persist_restore_artifact_snapshot(
                trigger=f"bracket_deferred_cleared:{reason}",
                allow_empty=True,
            )

        return True

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
        elif close_flow is not None:
            if getattr(close_flow, "close_submission_restore_truth", None) is not None:
                close_flow.close_submission_restore_truth = None
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
        manage_flow = self.manage_flows.get(symbol_key)
        entry_order_id = str(
            getattr(manage_flow, "entry_order_id", None) or ""
        ).strip() or None
        entry_client_order_id = str(
            getattr(manage_flow, "entry_client_order_id", None) or ""
        ).strip() or None
        sl_client_order_id = str(
            getattr(manage_flow, "sl_algo_client_id", None) or ""
        ).strip() or None
        tp_client_order_id = str(
            getattr(manage_flow, "tp_algo_client_id", None) or ""
        ).strip() or None
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
                "entry_order_id": entry_order_id,
                "entry_client_order_id": entry_client_order_id,
                "sl_order_id": None,
                "tp_order_id": None,
                "sl_client_order_id": sl_client_order_id,
                "tp_client_order_id": tp_client_order_id,
                "restore_relevant": True,
            }
        if len(pending_order_ids) > 1:
            return {
                "bracket_state": BRACKET_STATE_UNKNOWN,
                "bracket_truth_source": TRUTH_SOURCE_UNKNOWN,
                "deferred_entry_order_id": None,
                "entry_order_id": entry_order_id,
                "entry_client_order_id": entry_client_order_id,
                "sl_order_id": None,
                "tp_order_id": None,
                "sl_client_order_id": sl_client_order_id,
                "tp_client_order_id": tp_client_order_id,
                "restore_relevant": True,
            }

        bracket_links = dict(self._symbol_brackets.get(symbol_key) or {})
        sl_order_id = str(bracket_links.get(
            "sl_order_id") or "").strip() or None
        tp_order_id = str(bracket_links.get(
            "tp_order_id") or "").strip() or None
        has_sl = bool(sl_order_id)
        has_tp = bool(tp_order_id)
        if has_sl and has_tp:
            return {
                "bracket_state": BRACKET_STATE_LINKED_ACTIVE,
                "bracket_truth_source": self._symbol_bracket_truth_source_for(
                    symbol_key
                ),
                "deferred_entry_order_id": None,
                "entry_order_id": entry_order_id,
                "entry_client_order_id": entry_client_order_id,
                "sl_order_id": sl_order_id,
                "tp_order_id": tp_order_id,
                "sl_client_order_id": sl_client_order_id,
                "tp_client_order_id": tp_client_order_id,
                "restore_relevant": True,
            }
        if has_sl or has_tp:
            return {
                "bracket_state": BRACKET_STATE_PARTIAL_LINKAGE,
                "bracket_truth_source": self._symbol_bracket_truth_source_for(
                    symbol_key
                ),
                "deferred_entry_order_id": None,
                "entry_order_id": entry_order_id,
                "entry_client_order_id": entry_client_order_id,
                "sl_order_id": sl_order_id,
                "tp_order_id": tp_order_id,
                "sl_client_order_id": sl_client_order_id,
                "tp_client_order_id": tp_client_order_id,
                "restore_relevant": True,
            }
        return {
            "bracket_state": BRACKET_STATE_UNKNOWN,
            "bracket_truth_source": TRUTH_SOURCE_UNKNOWN,
            "deferred_entry_order_id": None,
            "entry_order_id": entry_order_id,
            "entry_client_order_id": entry_client_order_id,
            "sl_order_id": None,
            "tp_order_id": None,
            "sl_client_order_id": sl_client_order_id,
            "tp_client_order_id": tp_client_order_id,
            "restore_relevant": False,
        }

    # --- 0R: Sanctioned FSM-level delegator for 6C (startup_reconstruction.py) ---

    def _startup_reconstruct_runtime_bracket_truth(
        self,
        open_orders: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Thin delegator — routes to StartupReconstruction (Package 6C owner)."""
        return self._startup_reconstruction.reconstruct(open_orders)

    def _apply_authoritative_restore_record(
        self,
        record: ExecutionPositionRestoreLifecycleRecord,
    ) -> ExecutionPositionRestoreAuthoritativeSymbolStatus:
        """Thin delegator — routes to AuthoritativeRestoreApply (Package 6B owner).

        The 6A seam (startup_truth_orchestrator._run_restore_artifact_authoritative_read)
        calls this method. It is kept here as a delegator to preserve the 6A seam without
        forcing a 6A rewrite. Package 6C will drive the apply call directly after 6B
        extraction is complete and 6C is implemented.
        """
        return self._authoritative_restore_apply.apply_record(record)

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

    def _has_active_lifecycle_for_symbol(self, symbol: str) -> bool:
        manage_flow = self.manage_flows.get(str(symbol or "").upper())
        if manage_flow is None:
            return False
        try:
            return bool(manage_flow.has_active_lifecycle())
        except Exception:
            return False

    def _resolve_bracket_strategy_owner(
        self,
        *,
        symbol: str,
        explicit_strategy_id: Optional[str] = None,
        explicit_source: str = "",
        allow_registry_fallback: bool = True,
    ) -> Dict[str, Any]:
        """Phase 14A: Delegated to BracketOwnership."""
        return self._bracket_ownership.resolve_bracket_strategy_owner(
            symbol=symbol,
            explicit_strategy_id=explicit_strategy_id,
            explicit_source=explicit_source,
            allow_registry_fallback=allow_registry_fallback,
        )

    def _resolve_strategy_owner_from_decision(
        self,
        *,
        symbol: str,
        decision: Message,
    ) -> Dict[str, Any]:
        """Phase 14A: Delegated to BracketOwnership."""
        return self._bracket_ownership.resolve_strategy_owner_from_decision(
            symbol=symbol,
            decision=decision,
        )

    def _resolve_strategy_owner_for_recovery(self, *, symbol: str) -> Dict[str, Any]:
        """Phase 14A: Delegated to BracketOwnership."""
        return self._bracket_ownership.resolve_strategy_owner_for_recovery(symbol=symbol)

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
        """Phase 14A: Delegated to BracketOwnership."""
        return self._bracket_ownership.remember_bracket_owner(
            symbol=symbol,
            strategy_id=strategy_id,
            strategy_source=strategy_source,
            owner_status=owner_status,
            placement_path=placement_path,
            detail=detail,
            assigned_strategies=assigned_strategies,
            rid=rid,
            corr_id=corr_id,
            entry_order_id=entry_order_id,
            entry_client_order_id=entry_client_order_id,
            lifecycle_active=lifecycle_active,
        )

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
        """Phase 14A: Delegated to BracketOwnership."""
        self._bracket_ownership.append_bracket_ownership_record(
            event_type=event_type,
            symbol=symbol,
            placement_path=placement_path,
            strategy_id=strategy_id,
            strategy_source=strategy_source,
            owner_status=owner_status,
            detail=detail,
            assigned_strategies=assigned_strategies,
            rid=rid,
            corr_id=corr_id,
            entry_order_id=entry_order_id,
            entry_client_order_id=entry_client_order_id,
            sl_order_id=sl_order_id,
            tp_order_id=tp_order_id,
            lifecycle_active=lifecycle_active,
        )

    def _clear_bracket_owner(self, symbol: str) -> None:
        """Phase 14A: Delegated to BracketOwnership."""
        self._bracket_ownership.clear_bracket_owner(symbol)

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
                # DEF-E11: No async loop means the WAL has committed a DEC record
                # but no exchange action will be scheduled. This is a split-brain:
                # the system BELIEVES an action was taken but no order was sent.
                # Emit a critical observability event so operators can detect and
                # manually intervene (do NOT silently discard the decision).
                rid = getattr(result, "rid", None) or getattr(
                    result, "pld", {}).get("rid")
                symbol = getattr(result, "pld", {}).get(
                    "symbol") if hasattr(result, "pld") else None
                LOG.error(
                    "DEF-E11: No async loop available for DEC:%s rid=%s symbol=%s — "
                    "WAL has DEC truth but NO exchange action was scheduled. "
                    "This is a split-brain state. Manual intervention required.",
                    result.verb, rid, symbol,
                )
                self._emit_observability_event("DEC_NO_LOOP_TERMINAL_FAILURE", {
                    "verb": result.verb,
                    "rid": rid,
                    "symbol": symbol,
                    "why": "DEF-E11:no_async_loop_decision_unscheduled",
                })
        else:
            LOG.info(
                " ExecPosFSM: Skipping execution for DEC:%s (shadow_mode=%s, adapter=%s)",
                result.verb,
                self.shadow_mode,
                self.adapter is not None,
            )

    def _on_trade_executed(self, event: Message) -> None:
        """Canonical fill ingress for authoritative runtime TRADE_EXECUTED events."""
        self._fill_ingress_coordinator.handle_canonical_fill_ingress(
            event, fill_source="trade_executed", process_result=True)

    def _on_order_fill(self, event: Message) -> None:
        """Compatibility fill ingress routed into the same canonical local lifecycle path."""
        self._fill_ingress_coordinator.handle_canonical_fill_ingress(
            event, fill_source="order_fill", process_result=True)

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

        self._position_policy_mediator.on_execution_close_reconciled(event)

        if symbol and self._evt_handlers is not None:
            try:
                close_ts_ms = int(payload.get("ts_ms") or get_clock().now_ms())
            except (TypeError, ValueError):
                close_ts_ms = get_clock().now_ms()
            self._evt_handlers.emit_position_closed_observability(
                symbol,
                close_ts_ms=close_ts_ms,
                open_regime=getattr(
                    self, "_open_regime_by_symbol", {}).get(symbol),
                bus_why="execution_close_reconciled",
                require_close_truth=True,
            )

        self._apply_authoritative_local_close_reset(
            symbol,
            reason="execution_close_reconciled",
            source=str(payload.get("source") or "execution_close_reconciled"),
            payload=payload,
        )
        if self._position_policy_sidecar is not None:
            self._position_policy_sidecar.on_execution_close_reconciled(event)

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
            lifecycle_fee_getter=lambda symbol: self._accumulated_fees_by_symbol.get(
                str(symbol).upper()
            ),
        )

    def shutdown(self, *, async_timeout: float = 5.0):
        """Shutdown the FSM and cleanup resources."""
        if self._startup_truth_orchestrator._restore_artifact_has_state():
            self._startup_truth_orchestrator._persist_restore_artifact_snapshot(
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
                stop_handle = self._submit_async(
                    self.order_guardian.stop(), loop)
                if isinstance(stop_handle, Future):
                    try:
                        stop_handle.result(timeout=async_timeout)
                    except FutureTimeoutError:
                        LOG.error(
                            "OrderGuardian shutdown timed out after %.3fs",
                            async_timeout,
                        )
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
            self._startup_truth_orchestrator._schedule_restore_artifact_loop()
        except Exception as e:
            LOG.error(f"Failed to start restore artifact loop: {e}")
        if not self.order_guardian:
            return

        try:
            self._schedule_guardian_start()
            self._schedule_fsm_cleanup_loop()
            self._bracket_health.schedule_bracket_health_check()
        except Exception as e:
            LOG.error(f"Failed to start OrderGuardian: {e}")

    # --- 0R: Sanctioned FSM-level delegator for 6A (startup_truth_orchestrator) ---
    # Peer modules (e.g. bracket_ownership) MUST call this FSM-level surface,
    # NOT access self._fsm._startup_truth_orchestrator.* directly.

    def _persist_restore_artifact_snapshot(
        self,
        *,
        trigger: str,
        allow_empty: bool,
    ) -> bool:
        """Thin delegator — routes to StartupTruthOrchestrator (Package 6A owner).
        Peer modules must use this surface, not cross into the orchestrator directly.
        """
        return self._startup_truth_orchestrator._persist_restore_artifact_snapshot(
            trigger=trigger,
            allow_empty=allow_empty,
        )

    def _emit_position_policy_close_request_state(
        self,
        request_context: Dict[str, Any],
        *,
        request_state: str,
        why: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Thin delegator for sidecar close-state emission via PositionPolicyMediator."""
        self._position_policy_mediator._emit_position_policy_close_request_state(
            request_context,
            request_state=request_state,
            why=why,
            extra=extra,
        )
    # --- end 0R delegators ---

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
            pre_open_guard=self._run_injected_open_guard,
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

    def _handle_cmd_close_producer_ingress(
        self,
        msg: Message,
        *,
        journal: Any,
        before: Any,
        close_flow: CloseFlowFSM,
    ) -> Optional[Message]:
        """Bounded producer ingress for CMD:CLOSE before CloseFlow delegation."""
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
                    f" [CMD:CLOSE] Set closing flag for {symbol} to prevent bracket race"
                )

        return close_flow.handle(msg)

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
        if self._startup_truth_orchestrator._authoritative_restore_enabled():
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
            restore_signature_before = self._startup_truth_orchestrator._restore_semantics_signature(
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

                local_guard_err = self._pre_open_guard(msg, manage_flow)
                if local_guard_err is not None:
                    self._cancel_entry_reservation(str(msg.rid))
                    result = local_guard_err
                    return result

                exposure_err = self._check_exposure_fail_closed(msg)
                if exposure_err is not None:
                    self._cancel_entry_reservation(str(msg.rid))
                    result = exposure_err
                    return result
                guard_bypass_rid = self._mark_open_guard_prevalidated(msg.rid)
                try:
                    result = open_flow.handle(msg)
                finally:
                    self._clear_open_guard_prevalidated(guard_bypass_rid)

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
                result = self._fill_ingress_coordinator.handle_canonical_fill_ingress(
                    msg,
                    fill_source=str((msg.pld or {}).get(
                        "fill_source") or "trade_executed"),
                    process_result=False,
                )
            elif msg.verb == "ORDER_FILL":
                result = self._fill_ingress_coordinator.handle_canonical_fill_ingress(
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
                result = self._handle_cmd_close_producer_ingress(
                    msg,
                    journal=journal,
                    before=before,
                    close_flow=close_flow,
                )
            else:
                result = manage_flow.handle(msg)

            self._process_flow_result(result)
            restore_signature_after = self._startup_truth_orchestrator._restore_semantics_signature(
                symbol)
            if restore_signature_after != restore_signature_before:
                self._startup_truth_orchestrator._persist_restore_artifact_snapshot(
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
        if self._block_no_order_action(
            f"execute_decision:{getattr(decision, 'verb', 'unknown')}"
        ):
            return
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
            await self._emit_outer_execution_failure(
                decision,
                e,
                propagation_source="_execute_decision",
            )

    async def _emit_outer_execution_failure(
        self,
        decision: Message,
        error: Exception,
        *,
        propagation_source: str,
    ) -> None:
        """Emit the generic outer failure sink for escaped execution exceptions."""
        decision_pld = decision.pld or {}
        decision_symbol = decision_pld.get("symbol", "")
        decision_verb = str(getattr(decision, "verb", "") or "")
        is_close_path = decision_verb in {"CLOSE", "CLOSE_POSITION"}

        LOG.error(
            " Adapter failed to execute decision %s for %s: %s",
            decision_verb,
            decision_symbol or "unknown",
            error,
            exc_info=True,
        )

        if self.alert_manager:
            try:
                symbol = decision_symbol or "unknown"
                error_key = f"exec_error_{symbol}"
                if not hasattr(self, "_exec_error_counts"):
                    self._exec_error_counts = {}
                self._exec_error_counts[error_key] = (
                    self._exec_error_counts.get(error_key, 0) + 1)
                if self._exec_error_counts[error_key] >= 2:
                    self.alert_manager.check_circuit_breaker(True, 600)
            except Exception as alert_e:
                LOG.error("Error triggering execution error alert: %s", alert_e)

        reason_code = "ADAPTER_ERROR"
        reason_text = str(error)[:200]

        side_value = decision_pld.get("side")
        if side_value in (None, ""):
            side_value = "UNKNOWN_CLOSE_SIDE" if is_close_path else "NONE"

        qty_value = decision_pld.get("qty")
        quantity_value = 0.0
        quantity_from_payload = False
        if qty_value not in (None, ""):
            try:
                quantity_value = float(qty_value)
                quantity_from_payload = True
            except (TypeError, ValueError):
                quantity_value = 0.0

        close_client_order_id = ""
        if is_close_path:
            close_client_order_id = str(
                decision_pld.get("client_order_id")
                or decision_pld.get("clientOrderId")
                or decision_pld.get("execution_client_order_id")
                or ""
            ).strip()

        correlation_basis = "rid+symbol+source_fsm+reject_stage"
        if is_close_path:
            correlation_basis = "rid+symbol+reject_stage"
            if close_client_order_id:
                correlation_basis = "rid+symbol+client_order_id+reject_stage"

        order_reject_metadata: dict[str, Any] = {
            "error": str(error),
            "decision_verb": decision_verb,
            "reject_stage": "outer_propagation",
            "correlation_basis": correlation_basis,
            "propagation_source": propagation_source,
        }
        terminal_payload_extra: dict[str, Any] = {
            "reject_stage": "outer_propagation",
            "correlation_basis": correlation_basis,
            "propagation_source": propagation_source,
        }
        if is_close_path:
            order_reject_metadata.update({
                "link_to_inner_reject": True,
                "inner_reject_owner": "CloseExecutor",
                "identity_scope": "rid_symbol_only",
                "quantity_from_payload": quantity_from_payload,
            })
            terminal_payload_extra.update({
                "link_to_inner_reject": True,
                "identity_scope": "rid_symbol_only",
            })
            if close_client_order_id:
                order_reject_metadata["client_order_id"] = close_client_order_id
                order_reject_metadata["identity_scope"] = "rid_symbol_client_order_id"
                terminal_payload_extra["client_order_id"] = close_client_order_id
                terminal_payload_extra["identity_scope"] = "rid_symbol_client_order_id"

        if isinstance(error, UncertainSubmitRecoveryError):
            reason_code = "UNCERTAIN_SUBMIT_UNRECOVERED"
            reason_text = (
                "Submit status unknown and recovery by clientOrderId failed: "
                f"{error.original_error}"
            )[:200]
            order_reject_metadata.update({
                "uncertain_submit": True,
                "client_order_id": error.entry_id,
                "binance_code": error.binance_code,
                "recovery_attempts": error.attempts,
                "original_exception_class": type(error.original_error).__name__,
            })
            terminal_payload_extra.update({
                "uncertain_submit": True,
                "client_order_id": error.entry_id,
                "binance_code": error.binance_code,
                "recovery_attempts": error.attempts,
                "original_exception_class": type(error.original_error).__name__,
            })

        order_reject_payload = {
            "rid": decision.rid,
            "event_type": "ORDER_REJECTED",
            "symbol": decision_symbol,
            "side": side_value,
            "quantity": quantity_value,
            "nrr_code": "NRR-015",
            "why": f"Adapter execution failed: {reason_text}",
            "source_fsm": "ExecPosFSM",
            "origin_class": "execution_adapter",
            "metadata": order_reject_metadata,
        }
        if close_client_order_id:
            order_reject_payload["client_order_id"] = close_client_order_id

        order_logger.write(order_reject_payload)

        try:
            await emit_canonical_terminal_order_event(
                fsm=self.fsm,
                event_name="EVT:ORDER_REJECTED",
                payload={
                    "symbol": decision_symbol,
                    "side": side_value,
                    "reason_code": reason_code,
                    "reason_text": reason_text,
                    "exception_class": type(error).__name__,
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
            pld={
                "error": str(error),
                "original_decision": decision.model_dump(),
                "reject_stage": "outer_propagation",
                "correlation_basis": correlation_basis,
                "propagation_source": propagation_source,
            },
            why="Execution failed due to adapter error",
        )
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

    def _mark_open_guard_prevalidated(self, rid: Any) -> Optional[str]:
        rid_key = str(rid or "").strip()
        if not rid_key:
            return None
        with self._open_guard_bypass_lock:
            self._prevalidated_open_rids.add(rid_key)
        return rid_key

    def _clear_open_guard_prevalidated(self, rid: Optional[str]) -> None:
        rid_key = str(rid or "").strip()
        if not rid_key:
            return
        with self._open_guard_bypass_lock:
            self._prevalidated_open_rids.discard(rid_key)

    def _run_injected_open_guard(self, msg: Message) -> Optional[Message]:
        rid_key = str(getattr(msg, "rid", "") or "").strip()
        if rid_key:
            with self._open_guard_bypass_lock:
                if rid_key in self._prevalidated_open_rids:
                    return None
        symbol = (msg.pld or {}).get("symbol")
        if not symbol:
            return None
        manage_flow = self.manage_flow(symbol)
        return self._pre_open_guard(msg, manage_flow)

    def _cancel_entry_reservation(self, rid: str) -> None:
        """Clear OrderIndex reservation when an OPEN path is blocked fail-closed."""
        try:
            order_index = self._runtime_order_index()
            if order_index is not None:
                order_index.cancel_reservation(str(rid))
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

    async def _handle_bracket_protection_missing(
        self,
        *,
        symbol: str,
        source_path: str,
        failure_class: str,
        reason: str,
        why_code: str,
        rid: Optional[str] = None,
        side: Optional[Any] = None,
        qty: Optional[Any] = None,
        entry_order_id: Optional[Any] = None,
        entry_client_order_id: Optional[Any] = None,
        strategy_id: Optional[Any] = None,
        details: Optional[Any] = None,
        live_position_proven: bool = False,
        remediation_action_override: Optional[str] = None,
    ) -> str:
        """Emit explicit protection-missing telemetry and optionally force-close.

        Callers must pass ``live_position_proven=True`` only after a bounded
        exchange/read-path check has confirmed a non-zero position. Without
        that proof this helper records the unsafe state but does not blind-close.
        """
        symbol_key = str(symbol or "").strip().upper()
        remediation_action = remediation_action_override or (
            "force_reduce_only_close"
            if live_position_proven
            else "position_not_proven_no_close"
        )
        manage_flow = self.manage_flows.get(symbol_key)
        bracket_state = self._symbol_brackets.get(symbol_key, {}) or {}
        payload: Dict[str, Any] = {
            "ts_ms": int(get_clock().now_sec() * 1000),
            "symbol": symbol_key or str(symbol or ""),
            "rid": str(rid) if rid not in (None, "") else None,
            "lifecycle_id": self._last_lifecycle_ikey_by_symbol.get(symbol_key),
            "strategy_id": str(strategy_id) if strategy_id not in (None, "") else self._open_strategy_by_symbol.get(symbol_key),
            "side": str(side) if side not in (None, "") else None,
            "qty": str(qty) if qty not in (None, "") else None,
            "entry_order_id": str(entry_order_id) if entry_order_id not in (None, "") else getattr(manage_flow, "entry_order_id", None),
            "entry_client_order_id": str(entry_client_order_id) if entry_client_order_id not in (None, "") else getattr(manage_flow, "entry_client_order_id", None),
            "sl_order_id": bracket_state.get("sl_order_id") or getattr(manage_flow, "sl_order_id", None),
            "tp_order_id": bracket_state.get("tp_order_id") or getattr(manage_flow, "tp_order_id", None),
            "source_path": source_path,
            "failure_class": failure_class,
            "reason": str(reason or why_code),
            "why_code": why_code,
            "remediation_action": remediation_action,
            "why": "execution:bracket_placement_failed",
        }
        if details is not None:
            payload["details"] = details

        self._emit_execution_bus_event("EVT:BRACKET_PLACEMENT_FAILED", payload)

        if not live_position_proven:
            return remediation_action

        close_msg = Message(
            op="DEC",
            verb="CLOSE",
            src="execution_position",
            dst="execution_position",
            rid=str(rid) if rid not in (
                None, "") else f"bracket_protection_missing:{symbol_key}",
            pld={
                "symbol": symbol_key,
                "trigger": "BRACKET_PROTECTION_MISSING",
                "reason": why_code,
                "close_guard_prevalidated": True,
            },
            why="BRACKET_PROTECTION_MISSING",
        )
        try:
            await self._close_exec.execute_close(close_msg)
        except Exception as close_exc:
            await self._emit_outer_execution_failure(
                close_msg,
                close_exc,
                propagation_source="_handle_bracket_protection_missing",
            )
        return remediation_action

    def _entry_order_in_flight_guard(
        self,
        msg: Message,
        manage_flow: ManageFlowFSM,
    ) -> Optional[Message]:
        """Fail closed when OrderIndex still owns another in-flight entry."""
        order_index = self._runtime_order_index()
        if order_index is None or not hasattr(order_index, "get_in_flight_entry"):
            return None

        symbol = str((msg.pld or {}).get("symbol") or "").strip()
        if not symbol:
            return None

        in_flight_ref = order_index.get_in_flight_entry(
            symbol,
            exclude_rid=str(getattr(msg, "rid", "") or ""),
        )
        if in_flight_ref is None:
            return None

        local_state = str(
            getattr(getattr(manage_flow, "state", None), "value", "UNKNOWN"))
        portfolio_state = self._get_portfolio_state_for_symbol(symbol)
        why = "execution:entry_order_in_flight"
        payload = {
            "ts_ms": int(get_clock().now_sec() * 1000),
            "symbol": symbol,
            "rid": msg.rid,
            "lifecycle_id": getattr(in_flight_ref, "idempotent_key", None),
            "tracked_rid": getattr(in_flight_ref, "rid", None),
            "block_reason": "entry_order_in_flight",
            "reason": "entry_order_in_flight",
            "current_local_state": local_state,
            "local_manage_state": local_state,
            "portfolio_truth_state": portfolio_state,
            "portfolio_state": portfolio_state,
            "divergence_detected": False,
            "has_active_lifecycle": False,
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
            "in_flight_entry_rid": getattr(in_flight_ref, "rid", None),
            "in_flight_entry_client_order_id": getattr(in_flight_ref, "clientOrderId", None),
            "in_flight_entry_order_id": getattr(in_flight_ref, "exchangeOrderId", None),
            "in_flight_entry_order_type": getattr(in_flight_ref, "order_type", None),
            "why": why,
        }
        self._emit_execution_bus_event("EVT:EXECUTION_GUARD_BLOCKED", payload)
        return Message(
            op="ERR",
            verb="OPEN",
            src=msg.dst,
            dst=msg.src,
            rid=msg.rid,
            why="OPEN_GUARD_FAIL",
            pld=payload,
        )

    @staticmethod
    def _is_opposite_entry_against_portfolio(
        *,
        portfolio_state: str,
        intent_side: str,
    ) -> bool:
        side = str(intent_side or "").strip().upper()
        if portfolio_state == "LONG" and side == "SELL":
            return True
        if portfolio_state == "SHORT" and side == "BUY":
            return True
        return False

    def _opposite_entry_contract_guard(
        self,
        msg: Message,
        manage_flow: ManageFlowFSM,
    ) -> Optional[Message]:
        symbol = str((msg.pld or {}).get("symbol") or "").strip()
        if not symbol:
            return None

        intent_side = str((msg.pld or {}).get("side") or "").strip().upper()
        if intent_side not in {"BUY", "SELL"}:
            return None

        portfolio_state = self._get_portfolio_state_for_symbol(symbol)
        if portfolio_state not in {"LONG", "SHORT"}:
            return None

        if not self._is_opposite_entry_against_portfolio(
            portfolio_state=portfolio_state,
            intent_side=intent_side,
        ):
            return None

        local_state = str(
            getattr(getattr(manage_flow, "state", None), "value", "UNKNOWN"))
        has_active_lifecycle = (
            manage_flow.has_active_lifecycle()
            if hasattr(manage_flow, "has_active_lifecycle")
            else local_state != "FLAT"
        )
        tracked_rid = self._last_lifecycle_rid_by_symbol.get(symbol)
        lifecycle_id = self._last_lifecycle_ikey_by_symbol.get(symbol)
        reason = "opposite_entry_requires_explicit_flip_contract"
        why = f"execution:{reason}"
        payload = {
            "ts_ms": int(get_clock().now_sec() * 1000),
            "symbol": symbol,
            "rid": msg.rid,
            "lifecycle_id": lifecycle_id,
            "tracked_rid": tracked_rid,
            "block_reason": reason,
            "reason": reason,
            "current_local_state": local_state,
            "local_manage_state": local_state,
            "portfolio_truth_state": portfolio_state,
            "portfolio_state": portfolio_state,
            "divergence_detected": (not has_active_lifecycle),
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
        return Message(
            op="ERR",
            verb="OPEN",
            src=msg.dst,
            dst=msg.src,
            rid=msg.rid,
            why="OPEN_GUARD_FAIL",
            pld=payload,
        )

    def _local_open_guard(self, msg: Message, manage_flow: ManageFlowFSM) -> Optional[Message]:
        """Fail closed when local execution state still owns an unresolved lifecycle."""
        has_active_lifecycle = (
            manage_flow.has_active_lifecycle()
            if hasattr(manage_flow, "has_active_lifecycle")
            else str(getattr(getattr(manage_flow, "state", None), "value", manage_flow.state)) != "FLAT"
        )
        if not has_active_lifecycle:
            return self._entry_order_in_flight_guard(msg, manage_flow)

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

    def _pre_open_guard(self, msg: Message, manage_flow: ManageFlowFSM) -> Optional[Message]:
        local_guard_err = self._local_open_guard(msg, manage_flow)
        if local_guard_err is not None:
            return local_guard_err
        return self._opposite_entry_contract_guard(msg, manage_flow)

    def _check_exposure_fail_closed(self, msg: Message) -> Optional[Message]:
        """Phase 14A: Delegated to ExposureManager."""
        return self._exposure_mgr.check_exposure_fail_closed(msg)

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

        Events are logged as structured logger records for dashboards and alerting.
        This helper does not emit onto the FSM bus and does not write to the
        shadow critical journal; callers must promote data onto those surfaces
        explicitly when the name is part of the canonical runtime event contract.

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
    ) -> bool:
        """Phase 14A: Delegated to BracketManager."""
        return await self._bracket_mgr.place_deferred_brackets(entry_order_id, bracket_data)

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
                # DEF-E12: CancelledError MUST be re-raised. Swallowing it prevents
                # the task from being cancelled (e.g., on shutdown), causing immortal
                # cleanup loops that block graceful process exit.
                LOG.debug("cleanup_orphans loop cancelled — exiting")
                raise
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
        guardian_seed_symbols: Set[str] = set()
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
        execution_truth_cache = self._startup_truth_orchestrator._execution_truth_cache_status()
        restore_artifact_write_attempted = False
        restore_artifact_write_succeeded = False
        failure_reason: Optional[str] = None
        try:
            LOG.info(" Starting OrderGuardian startup reconciliation...")
            fresh_orders = []
            restore_authoritative = self._startup_truth_orchestrator._run_restore_artifact_authoritative_read()
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

                    guardian_seed_symbols.update(
                        self._collect_guardian_symbols())
                    symbols_with_positions.update(guardian_seed_symbols)
                    symbols_with_positions.update(authoritative_symbols)

                    # Link existing orders for each symbol
                    guardian_link_existing_invoked = bool(
                        symbols_with_positions)
                    if symbols_with_positions:
                        guardian = self.order_guardian
                        if guardian is None:
                            raise AttributeError(
                                "'NoneType' object has no attribute 'link_existing_from_rest'"
                            )
                        for symbol in symbols_with_positions:
                            await guardian.link_existing_from_rest(symbol)
                            LOG.debug(f" Linked existing orders for {symbol}")

                    LOG.info(
                        f" Linked existing orders for {len(symbols_with_positions)} symbols")

                except Exception as e:
                    LOG.warning(
                        f"Failed to link existing orders during startup: {e}")

            # Then run cleanup to remove orphans
            guardian_cleanup_invoked = True
            guardian = self.order_guardian
            if guardian is None:
                raise AttributeError(
                    "'NoneType' object has no attribute 'cleanup_orphans'"
                )
            await guardian.cleanup_orphans()
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
            restore_authoritative = self._startup_truth_orchestrator._finalize_restore_authoritative_status(
                restore_authoritative,
                positions_fetch_succeeded=positions_fetch_succeeded,
                position_symbols=position_symbols,
            )
            restore_dark_read = self._startup_truth_orchestrator._run_restore_artifact_dark_read_comparison()
            restore_artifact_write_attempted = True
            restore_artifact_write_succeeded = self._startup_truth_orchestrator._persist_restore_artifact_snapshot(
                trigger="startup_order_guardian_reconcile",
                allow_empty=True,
            )
            LOG.info(" OrderGuardian startup reconciliation completed")
        except Exception as e:
            failure_reason = type(e).__name__
            LOG.error(f" OrderGuardian startup reconciliation failed: {e}")
        finally:
            self._startup_truth_orchestrator._append_startup_truth_artifact_record(
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
                    "guardian_symbols_observed": [],
                    "fresh_order_symbols_observed": sorted(fresh_order_symbols),
                },
                symbols_considered=sorted(
                    position_symbols
                    | pre_cleanup_order_symbols
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
