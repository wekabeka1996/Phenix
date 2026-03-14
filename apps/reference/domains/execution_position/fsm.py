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
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

# T2B-04: Time abstraction for deterministic testing
from apps.reference.core.time import get_clock
from typing import Dict, Any, Optional, Tuple, Set, Coroutine, List, TYPE_CHECKING

from vfoundation.core.fsm_emit_compat import Message, emit_compat
from vfoundation.dr import wal
from apps.reference.adapters.binance_adapter import BinanceAdapter, BinanceAPIError
from apps.reference.config_models import AuroraConfig
from apps.reference.utils.accessors import aget, dget

from .fsm_open import OpenFlowFSM
from .fsm_manage import ManageFlowFSM
from .fsm_close import CloseFlowFSM
from .exposure_guard import ExposureGuard
from .watchdog import OrderTimeoutWatchdog, OrderDeadline
from .utils import (
    quantize_stop_price,
    generate_client_order_id,
    validate_not_immediate,
    opposite_side,
    BoundedEventDeduper,
)
from .aurora_log_adapter import AuroraLogAdapter
from .metrics_collector import MetricsCollector
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
from apps.reference.domains.execution_position.open_executor import OpenExecutor
from apps.reference.domains.execution_position.bracket_manager import BracketManager

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

        # REGIME-LOG: Track open-time regime per symbol for close-time forensics
        self._open_regime_by_symbol: Dict[str, Dict[str, Any]] = {}

        # FIX-LIFECYCLE-01: Best-effort symbolrid/last fill price cache
        # Used to flush trade_lifecycle on robust position-close detection (portfolio snapshot).
        self._last_lifecycle_rid_by_symbol: Dict[str, str] = {}
        self._last_lifecycle_fill_price_by_symbol: Dict[str, float] = {}

        # PnL + close_reason cache: populated on ORDER_FILLED, consumed on POSITION_CLOSED.
        self._last_realized_pnl_by_symbol: Dict[str, float] = {}
        self._last_close_reason_by_symbol: Dict[str, str] = {}

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

        # AGENT-PATCH: Safe event bus setup with LocalBus fallback
        if self.fsm and hasattr(self.fsm, "listen") and hasattr(self.fsm, "emit"):
            self.bus = self.fsm
            LOG.debug("ExecPosFSM using FSMCore event bus")
        else:
            self.bus = LocalBus()
            LOG.debug(
                "ExecPosFSM using LocalBus fallback (FSMCore not available)")

        # Register event listeners on the bus
        self.bus.listen("EVT:PORTFOLIO_STATE_UPDATED",
                        self._on_portfolio_state_updated)
        self.bus.listen("EVT:ORDER_ACK", self._on_order_ack)
        self.bus.listen("EVT:ORDER_FILL", self._on_order_fill)
        self.bus.listen("EVT:FEATURES_CALCULATED",
                        self._on_features_calculated)
        # EP-01: Subscribe to regime changes for dynamic risk adaptation
        self.bus.listen("EVT:REGIME_DETECTED", self._on_regime_detected)
        # BUGFIX: Connect DecisionMaking intent to ExecutionPosition logic
        self.bus.listen("EVT:TRADE_INTENT_PROPOSED",
                        self._on_trade_intent_proposed)
        self.bus.listen("EVT:TRADE_INTENT_REJECTED",
                        self._on_trade_intent_rejected)

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

        # Log TTL configuration source and values
        ttl_source = "execution.watchdog"
        if watchdog_config is None or not watchdog_config:
            ttl_source = "trading.watchdog"
        elif hasattr(self.config, 'trading') and self.config.trading and hasattr(self.config.trading, 'orders') and self.config.trading.orders:
            # Check if override was applied
            try:
                orders_cfg = self.config.trading.orders if self.config.trading else None
                default_ttl_seconds = aget(
                    orders_cfg, "default_ttl_seconds", None) if orders_cfg else None
                if default_ttl_seconds is not None:
                    ttl_source = "trading.orders.default_ttl_seconds"
            except Exception:
                pass

        LOG.info(
            f"ExecPosFSM TTL config: ack_ttl_ms={ack_ttl_ms}, fill_ttl_ms={fill_ttl_ms}, source={ttl_source}")

        # Optional override from trading.orders.default_ttl_seconds (Balanced profile)
        try:
            orders_cfg = self._get_config_value(["trading", "orders"])
            if not orders_cfg:
                orders_cfg = self._get_config_value(["orders"])

            if orders_cfg:
                default_ttl_seconds = None
                if isinstance(orders_cfg, dict):
                    default_ttl_seconds = orders_cfg.get("default_ttl_seconds")
                else:
                    default_ttl_seconds = aget(
                        orders_cfg, "default_ttl_seconds", None)

                if default_ttl_seconds is not None:
                    ttl_ms = int(default_ttl_seconds) * 1000
                    fill_ttl_ms = ttl_ms
                    LOG.info(
                        f"ExecPosFSM: applying default_ttl_seconds override -> fill_ttl_ms={fill_ttl_ms}")
        except Exception as e:
            LOG.warning(f"ExecPosFSM: failed to read default_ttl_seconds: {e}")
        self.watchdog: OrderTimeoutWatchdog = OrderTimeoutWatchdog(
            ack_ttl_ms=ack_ttl_ms,
            fill_ttl_ms=fill_ttl_ms,
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
                        verb = event_name.split(
                            ":")[1] if ":" in event_name else event_name

                        # Build kwargs for Message, only include rid if present
                        msg_kwargs = {
                            "op": "EVT",
                            "verb": verb,
                            "src": "execution_position",
                            "dst": "execution_position",
                            "pld": payload,
                            "why": why
                        }

                        # Only add rid if it's present and not None
                        if payload.get("rid") is not None:
                            msg_kwargs["rid"] = payload["rid"]

                        msg = Message(**msg_kwargs)
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

    def _on_trade_intent_proposed(self, msg: Message) -> None:
        """Phase 14A: Delegated to IntentRouter."""
        self._intent_router.on_trade_intent_proposed(msg)

    def _on_trade_intent_rejected(self, msg: Message) -> None:
        """Phase 14A: Delegated to IntentRouter."""
        self._intent_router.on_trade_intent_rejected(msg)

    def _on_portfolio_state_updated(self, event: Message) -> None:
        """Phase 14A: Delegated to EPEventHandlers."""
        self._evt_handlers.on_portfolio_state_updated(event)

    def _on_order_ack(self, event: Message) -> None:
        """Phase 14A: Delegated to EPEventHandlers."""
        self._evt_handlers.on_order_ack(event)

    def _on_order_fill(self, event: Message) -> None:
        """Phase 14A: Delegated to EPEventHandlers."""
        self._evt_handlers.on_order_fill(event)

    def _on_features_calculated(self, event: Message) -> None:
        """Phase 14A: Delegated to EPEventHandlers."""
        self._evt_handlers.on_features_calculated(event)

    def shutdown(self):
        """Shutdown the FSM and cleanup resources."""
        if hasattr(self, 'watchdog') and self.watchdog:
            self.watchdog.stop()
        if hasattr(self, 'order_guardian') and self.order_guardian:
            loop = self._get_async_loop()
            if loop:
                self._submit_async(self.order_guardian.stop(), loop)
        LOG.info("ExecPosFSM shutdown complete")

    async def start_order_guardian(self):
        """Start OrderGuardian polling and reconciliation after FSM initialization."""
        if not self.order_guardian:
            return

        try:
            self._schedule_guardian_start()
            self._schedule_fsm_cleanup_loop()
            self._schedule_bracket_health_check()
        except Exception as e:
            LOG.error(f"Failed to start OrderGuardian: {e}")

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
                    pos_dict.get("positionAmt")
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
            sl_price, tp_price = self._compute_health_check_brackets(
                symbol=symbol,
                entry_price=entry_price,
                side=side,
            )
            if sl_price is None or tp_price is None:
                continue

            placed = await self._place_health_check_brackets(
                symbol=symbol,
                side=side,
                sl_price=sl_price,
                tp_price=tp_price,
                need_sl=not has_sl,
                need_tp=not has_tp,
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
            reduce_only = (
                str(reduce_only_raw).lower() == "true"
                if isinstance(reduce_only_raw, str)
                else bool(reduce_only_raw)
            )
            close_position = (
                str(close_position_raw).lower() == "true"
                if isinstance(close_position_raw, str)
                else bool(close_position_raw)
            )

            if order_type == "STOP_MARKET" and (reduce_only or close_position):
                has_sl = True
            if order_type == "TAKE_PROFIT_MARKET" and (reduce_only or close_position):
                has_tp = True

        return has_sl, has_tp

    def _compute_health_check_brackets(
        self,
        *,
        symbol: str,
        entry_price: float,
        side: str,
    ) -> Tuple[Optional[float], Optional[float]]:
        """Compute recovery brackets from the active strategy SSOT for the symbol."""
        try:
            strategy_id = str(
                self._open_strategy_by_symbol.get(symbol) or "aurora")
            regime = str(self._last_regime_by_symbol.get(symbol) or "DEFAULT")

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
            else:
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

            if sl_pct_eff is None or tp_rr_eff is None:
                return None, None

            tp_pct_eff = sl_pct_eff * tp_rr_eff
            instrument_spec = self.config.instruments.get(symbol)
            tick_size = Decimal(str(instrument_spec.tick_size)
                                ) if instrument_spec is not None else Decimal("0.01")

            if side == "BUY":
                sl_price = entry_price * (1.0 - sl_pct_eff)
                tp_price = entry_price * (1.0 + tp_pct_eff)
            else:
                sl_price = entry_price * (1.0 + sl_pct_eff)
                tp_price = entry_price * (1.0 - tp_pct_eff)

            return (
                float(quantize_stop_price(sl_price, float(tick_size),
                      side="SELL" if side == "BUY" else "BUY")),
                float(quantize_stop_price(tp_price, float(tick_size),
                      side="BUY" if side == "BUY" else "SELL")),
            )
        except Exception as e:
            LOG.warning(
                f"[BRACKET-HEALTH] failed to compute recovery brackets for {symbol}: {e}")
            return None, None

    async def _place_health_check_brackets(
        self,
        *,
        symbol: str,
        side: str,
        sl_price: float,
        tp_price: float,
        need_sl: bool,
        need_tp: bool,
    ) -> bool:
        """Place only the missing recovery brackets and register them with current owners."""
        if not self.adapter or not self.order_guardian:
            return False

        if not await self._preflight_position_check(symbol):
            return False

        bracket_side = opposite_side(side)
        parent_order_id = f"health_check:{symbol}"
        placed = False

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
                    self._symbol_brackets.setdefault(
                        symbol, {})["sl_order_id"] = sl_order_id
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
                    self._symbol_brackets.setdefault(
                        symbol, {})["tp_order_id"] = tp_order_id
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
            manage_flow = self.manage_flows.get(symbol)
            if manage_flow is not None:
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

        return placed

    # Phase 14.2: _initialize_adapter
    #  extracted to AdapterInitMixin (adapter_init.py)

    def _get_or_create_flows(
        self, symbol: str
    ) -> Tuple[OpenFlowFSM, ManageFlowFSM, CloseFlowFSM]:
        """Get or create the set of FSMs for a given symbol (thread-safe)."""
        with self._flows_lock:
            if symbol not in self.manage_flows:
                LOG.info(f"Creating new set of FSMs for symbol: {symbol}")
                try:
                    exec_config = self.config.trading.execution if self.config.trading else None
                except AttributeError:
                    exec_config = None

                # Safe extraction of execution config settings
                cooldown_ms = float(aget(exec_config, "cooldown_ms", 1000))
                guard_enabled = bool(aget(exec_config, "guard_enabled", True))
                cooldown_sec = cooldown_ms / 1000.0

                self.open_flows[symbol] = OpenFlowFSM(
                    cooldown_sec=cooldown_sec,
                    guard_enabled=guard_enabled,
                    config=self.config,
                    metrics_collector=self.metrics_collector,
                    leverage_service=self.leverage_service,
                    is_live_execution=self.is_live_execution,
                )
                self.manage_flows[symbol] = ManageFlowFSM(config=self.config)
                if hasattr(self.manage_flows[symbol], "set_observability_hook"):
                    self.manage_flows[symbol].set_observability_hook(
                        self._emit_execution_bus_event,
                    )
                self.close_flows[symbol] = CloseFlowFSM()
            elif hasattr(self.manage_flows[symbol], "set_observability_hook"):
                self.manage_flows[symbol].set_observability_hook(
                    self._emit_execution_bus_event,
                )

            return (
                self.open_flows[symbol],
                self.manage_flows[symbol],
                self.close_flows[symbol],
            )

    def hydrate(self, position_data: Dict[str, Any]):
        """Hydrate the FSMs for a given position from a snapshot."""
        symbol = position_data.get("symbol")
        if not symbol:
            LOG.error("HYDRATION_ERROR: position_data is missing 'symbol'")
            return

        _, manage_flow, close_flow = self._get_or_create_flows(symbol)

        LOG.info(f"Hydrating FSMs for symbol {symbol} from snapshot.")
        manage_flow.hydrate(position_data)
        close_flow.hydrate(position_data)

    def handle(self, msg: Message) -> Optional[Message]:
        """Route message to the appropriate flow and handle execution decisions."""
        pld = msg.pld or {}

        # Handle portfolio state updates BEFORE symbol check (they don't need symbol)
        if msg.verb == "PORTFOLIO_STATE_UPDATED":
            # Handle portfolio state updates (trigger post-fill hold release)
            self._on_portfolio_state_updated(msg)
            return None

        symbol = pld.get("symbol")
        if not symbol:
            LOG.warning(
                f"ExecPosFSM received message without symbol: {msg.verb}, pld_keys={list(pld.keys()) if pld else 'EMPTY'}, msg_type={type(msg)}, pld_type={type(pld)}")
            return None

        open_flow, manage_flow, close_flow = self._get_or_create_flows(symbol)
        result = None

        # Route to the correct FSM based on the message verb
        if msg.verb == "OPEN":
            # Post-close cooldown: prevent immediate re-entry after any position closes (global).
            now = get_clock().now_sec()
            last_close = float(self._last_any_position_closed_ts or 0.0)
            if last_close > 0 and self._cooldown_after_close_sec > 0 and (now - last_close) < self._cooldown_after_close_sec:
                remaining = max(
                    0.0, self._cooldown_after_close_sec - (now - last_close))
                return Message(
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

            local_guard_err = self._local_open_guard(msg, manage_flow)
            if local_guard_err is not None:
                self._cancel_entry_reservation(str(msg.rid))
                return local_guard_err

            # EXP-FIX: Fail-closed exposure check before processing CMD:OPEN
            exposure_err = self._check_exposure_fail_closed(msg)
            if exposure_err is not None:
                # TASK49/TASK40: If DecisionMaking reserved ENTRY_INTENT in OrderIndex,
                # ensure we clear it when OPEN is blocked fail-closed (no order will be placed).
                self._cancel_entry_reservation(str(msg.rid))
                return exposure_err
            result = open_flow.handle(msg)

            # If guards rejected CMD:OPEN, clear ENTRY_INTENT reservation so DM doesn't get stuck
            # deferring with NRR-ORDER-IN-FLIGHT.
            if result is not None and getattr(result, "op", None) == "ERR":
                self._cancel_entry_reservation(str(msg.rid))

            # PHASE A2 FIX: Capture TP/SL intent data if present
            if result and result.op == "DEC" and result.verb == "OPEN":
                try:
                    pld = result.pld or {}
                    # Helper to check for real values (not None, not "None" string)

                    def _is_real_value(v) -> bool:
                        return v is not None and str(v).strip().lower() != "none"

                    # Extract values
                    raw_stop = pld.get("stop_price")
                    raw_target = pld.get("target_price")
                    raw_sl_pct = pld.get("sl_pct")

                    # Only cache if at least one value is real (not None/"None")
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
            #  POLLING FIX: Watchdog emits EVT:TRADE_EXECUTED on REST-detected fills.
            # Treat it as a fill for OrderIndex terminalization to unblock the one-open-order guard.
            self._on_order_fill(msg)
            result = manage_flow.handle(msg)
        elif msg.verb == "ORDER_STATE_CHANGED":
            # Handle cancel/expire from Watchdog REST polling
            self._handle_cancel_event(msg)

        elif msg.verb == "ORDER_CANCELLED":
            # EXP-FIX: Handle order cancellation for exposure summary update
            self._handle_cancel_event(msg)

        elif msg.verb == "CLOSE":
            #  FIX: Set closing flag immediately on CMD:CLOSE to prevent bracket race
            symbol = msg.pld.get("symbol") if msg.pld else None
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

        # If a decision was made, log it and execute if not in shadow mode
        if result and result.op == "DEC":
            if result.verb == "BATCH":
                # Handle batch decisions (e.g. OCO brackets)
                batch_pld = result.pld or {}
                messages = batch_pld["messages"] if "messages" in batch_pld else [
                ]
                for msg_data in messages:
                    if isinstance(msg_data, dict):
                        # Reconstruct Message from dict
                        try:
                            sub_msg = Message(**msg_data)
                        except Exception as e:
                            LOG.error(
                                f"Failed to reconstruct BATCH message: {e}")
                            continue
                    else:
                        sub_msg = msg_data

                    wal.append(sub_msg.model_dump())
                    if (not self.shadow_mode and self.adapter) or (sub_msg.verb in ("CLOSE", "CLOSE_POSITION") and self.adapter):
                        loop = self._get_async_loop()
                        if loop:
                            self._submit_async(
                                self._execute_decision(sub_msg), loop)
            else:
                wal.append(result.model_dump())
                #  FIX: Execute CLOSE decisions even in shadow mode to cancel brackets
                if (not self.shadow_mode and self.adapter) or (result.verb in ("CLOSE", "CLOSE_POSITION") and self.adapter):
                    # Asynchronously execute the trade decision
                    loop = self._get_async_loop()
                    LOG.info(
                        f" ExecPosFSM: DEC:{result.verb} ready to execute, loop={loop is not None}, shadow_mode={self.shadow_mode}, adapter={self.adapter is not None}")
                    if loop:
                        self._submit_async(
                            self._execute_decision(result), loop)
                    else:
                        LOG.error(
                            f" ExecPosFSM: No async loop available for DEC:{result.verb}! Order will NOT be executed!")
                else:
                    LOG.info(
                        f" ExecPosFSM: Skipping execution for DEC:{result.verb} (shadow_mode={self.shadow_mode}, adapter={self.adapter is not None})")

        return result

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
            order_logger.write({
                "rid": decision.rid,
                "event_type": "ORDER_REJECTED",
                "symbol": decision_pld.get("symbol", ""),
                "side": decision_pld.get("side", "NONE"),
                "quantity": float(decision_pld.get("qty", 0)),
                "nrr_code": "NRR-015",
                "why": f"Adapter execution failed: {str(e)}",
                "source_fsm": "ExecPosFSM",
                "metadata": {"error": str(e), "decision_verb": decision.verb}
            })

            try:
                order_rejected_msg = Message(
                    op="EVT", verb="ORDER_REJECTED", src="execution_position",
                    dst="observability", rid=decision.rid,
                    pld={"symbol": decision_pld.get("symbol", ""),
                         "side": decision_pld.get("side", "NONE"),
                         "reason_code": "ADAPTER_ERROR",
                         "reason_text": str(e)[:200],
                         "exception_class": type(e).__name__,
                         "ts_ms": get_clock().now_ms()},
                    why="adapter_execution_failed")
                wal.append(order_rejected_msg.model_dump())
            except Exception as wal_e:
                LOG.warning(
                    f"Failed to write EVT:ORDER_REJECTED to WAL: {wal_e}")

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
                self.fsm.order_index.cancel_reservation(str(rid))  # type: ignore[attr-defined]
        except Exception:
            pass

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
            qty_raw = pos.get("positionAmt", "0")
            try:
                qty = Decimal(str(qty_raw))
            except Exception:
                return "UNKNOWN"
            if abs(qty) <= Decimal("1e-9"):
                return "FLAT"
            return "LONG" if qty > 0 else "SHORT"

        return "FLAT"

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
        local_state = str(getattr(getattr(manage_flow, "state", None), "value", "UNKNOWN"))
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
        try:
            LOG.info(" Starting OrderGuardian startup reconciliation...")

            #  FIX: First link existing orders from REST API for all symbols with positions
            if self.adapter:
                try:
                    positions = await self.adapter.get_open_positions()
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
                            symbols_with_positions.add(symbol)

                    # Also check for symbols with open orders
                    all_orders = await self.adapter.get_open_orders()
                    orders_list = [
                        o.to_dict() if hasattr(o, 'to_dict') else (
                            o.__dict__ if not isinstance(o, dict) else o)
                        for o in all_orders
                    ]

                    for order in orders_list:
                        symbol = order.get("symbol")
                        if symbol:
                            symbols_with_positions.add(symbol)

                    symbols_with_positions.update(
                        self._collect_guardian_symbols())

                    # Link existing orders for each symbol
                    for symbol in symbols_with_positions:
                        await self.order_guardian.link_existing_from_rest(symbol)
                        LOG.debug(f" Linked existing orders for {symbol}")

                    LOG.info(
                        f" Linked existing orders for {len(symbols_with_positions)} symbols")

                except Exception as e:
                    LOG.warning(
                        f"Failed to link existing orders during startup: {e}")

            # Then run cleanup to remove orphans
            await self.order_guardian.cleanup_orphans()
            LOG.info(" OrderGuardian startup reconciliation completed")
        except Exception as e:
            LOG.error(f" OrderGuardian startup reconciliation failed: {e}")
    # Phase 14.2: handle_tick_async, handle_tick, is_healthy
    #  extracted to HealthMetricsMixin (health_metrics.py)
