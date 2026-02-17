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
from vfoundation.obs.correlation import CorrelationStore
from .utils_event_bus import LocalBus

from .idempotent_cancel import IdempotentCancelHelper, IdempotentCancelResult

# Import OrderGuardian for TP/SL cleanup
from apps.reference.domains.execution_position.order_guardian import OrderGuardian

# EP-01: Import regime mapping for ExposureGuard adaptation
from apps.reference.core.types.regime_types import map_regime_to_bucket

# TASK50: Import qty normalizer for fail-closed quantity validation
from apps.reference.domains.execution_position.qty_normalizer import normalize_qty

# PHASE4: Pending brackets WAL persistence
from apps.reference.domains.execution_position.pending_brackets_wal import (
    write_pending_brackets_stored,
    write_pending_brackets_cleared,
    read_pending_brackets_from_wal,
)

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


class ExecPosFSM:
    """
    Wrapper FSM for the execution_position domain. It manages FSM instances
    per symbol and handles trade execution via the BinanceAdapter.
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
            "gate_entry_blocked_quiet_hours": 0,
            "gate_entry_allowed_quiet_hours": 0,
        }

        # QUIET-HOURS: Load quiet hours gate config
        _qh_cfg = self._get_config_value(
            ["domains", "execution_position", "quiet_hours"])
        self._quiet_hours_enabled: bool = bool(
            getattr(_qh_cfg, "enabled", False)) if _qh_cfg else False
        self._quiet_hours_windows: list = list(
            getattr(_qh_cfg, "windows", [])) if _qh_cfg else []

        # TP/SL Intent Data Cache (PHASE A2 fix)
        # Stores intent params from DEC:OPEN to be injected into Manage flow on FILL
        self._pending_intent_data: Dict[str, Dict[str, Any]] = {}

        # LIMIT-ENTRY-DEFERRED-BRACKETS: Pending TP/SL for LIMIT entries (placed on fill)
        # Key = entry_order_id, Value = {"symbol", "side", "sl", "tp", "qty", "rid", "idem_key", "tick_size"}
        self._pending_brackets: Dict[str, Dict[str, Any]] = {}

        # BRACKET-HEALTH: Track last known regime per symbol for TPSL computation
        self._last_regime_by_symbol: Dict[str, str] = {}
        self._bracket_health_started: bool = False

        # PHASE4: Rehydrate pending brackets from WAL on startup
        try:
            restored = read_pending_brackets_from_wal()
            if restored:
                self._pending_brackets = restored
                LOG.info(
                    f"📌 [PHASE4] Restored {len(restored)} pending brackets from WAL")
        except Exception as e:
            LOG.warning(
                f"[PHASE4] Failed to restore pending brackets from WAL: {e}")

        # EP-01.3-SUPERSEDE-ACK: Queued supersede state
        # When supersede cancels old entry, new open is queued until cancel confirmed
        # Key = symbol, Value = {"decision": decision_msg, "cancel_order_id": str, "queued_at": float}
        self._supersede_queue: Dict[str, Dict[str, Any]] = {}
        # Symbols currently waiting for cancel confirmation before executing queued open
        self._supersede_canceling: set = set()

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
        # EP-01: Subscribe to regime changes for dynamic risk adaptation
        self.bus.listen("EVT:REGIME_DETECTED", self._on_regime_detected)
        # BUGFIX: Connect DecisionMaking intent to ExecutionPosition logic
        self.bus.listen("EVT:TRADE_INTENT_PROPOSED",
                        self._on_trade_intent_proposed)
        self.bus.listen("EVT:TRADE_INTENT_REJECTED",
                        self._on_trade_intent_rejected)

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
            # Direct access only (fail-closed: missing field → AttributeError)
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
                alert_mgr_config = self.config.model_dump()
                self.alert_manager = AlertManager(
                    config=alert_mgr_config, logger=aget(self, "logger", LOG).getChild("alerts"))
                LOG.info("AlertManager initialized in ExecPosFSM")
            except Exception as e:
                LOG.warning(
                    f"Failed to initialize AlertManager in ExecPosFSM: {e}")

        # Ensure attribute exists even if init fails
        self.order_guardian: Optional[OrderGuardian] = None

        if not self.shadow_mode:
            self._initialize_adapter()
            # 🔧 POLLING FIX: Connect Watchdog hooks to adapter functions after initialization
            if hasattr(self.watchdog, 'set_hooks') and self.adapter:
                async def emit_watchdog_event(event_name, payload, why="polling"):
                    """
                    Deliver Watchdog REST-detected events into ExecPosFSM state machine.

                    Why this exists:
                    - Watchdog polling runs inside execution_position domain (timeouts + REST fill detection).
                    - For LIMIT entries we defer TP/SL placement until we see the fill.
                    - REST polling may detect fills even when WebSocket events are missing.
                    - Those fills MUST reach ExecPosFSM._on_order_fill to trigger deferred bracket placement.

                    NOTE:
                    - We intentionally do NOT broadcast Watchdog's EVT:TRADE_EXECUTED payload to the global
                      FSMCore bus because other domains (e.g. position_tracking) treat EVT:TRADE_EXECUTED
                      as a strict schema event (symbol/side/price/quantity/ts/venue). Watchdog's payload
                      is order-centric (orderId/clientOrderId/avgPrice/executedQty).
                    """
                    try:
                        verb = event_name.split(
                            ":")[1] if ":" in event_name else event_name
                        pld = dict(payload or {})

                        # Best-effort correlation recovery: enrich payload with original rid/corr_id
                        try:
                            order_id = pld.get(
                                "orderId") or pld.get("order_id")
                            if order_id is not None:
                                corr = self.correlation_store.get_by_order_id(
                                    str(order_id))
                                if isinstance(corr, dict):
                                    for k in ("rid", "corr_id", "oco_group_id", "parent_client_order_id"):
                                        if pld.get(k) in (None, "", "None", "null"):
                                            v = corr.get(k)
                                            if v not in (None, "", "None", "null"):
                                                pld[k] = v
                        except Exception:
                            pass

                        # Normalize clientOrderId casing for downstream code
                        if pld.get("clientOrderId") in (None, "", "None", "null") and pld.get("client_order_id") not in (None, "", "None", "null"):
                            pld["clientOrderId"] = pld.get("client_order_id")

                        msg_kwargs = {
                            "op": "EVT",
                            "verb": verb,
                            "src": "execution_position",
                            "dst": "execution_position",
                            "pld": pld,
                            "why": why,
                        }

                        # Prefer original RID if available, else let Message default to a UUID.
                        if pld.get("rid") not in (None, "", "None", "null"):
                            msg_kwargs["rid"] = str(pld.get("rid"))

                        msg = Message(**msg_kwargs)

                        # Direct delivery (do not rely on FSMCore event listeners).
                        self.handle(msg)
                    except Exception as e:
                        LOG.error(
                            f"Failed to deliver Watchdog event {event_name}: {e}", exc_info=True)

                self.watchdog.set_hooks(
                    get_order_fn=self.adapter.get_order,
                    emit_fn=emit_watchdog_event
                )
                LOG.info(
                    "✅ Watchdog REST polling hooks connected to adapter functions")
            # Initialize OrderGuardian for TP/SL cleanup with strict ownership tracking
            # MAGIC-NUM-EXTRACTION: poll_interval_ms from SSOT domains.execution_position.guardian
            poll_interval_ms = self._guardian_poll_interval_ms

            LOG.info(
                f"OrderGuardian poll_interval_ms from config: {poll_interval_ms}")

            try:
                self.order_guardian = OrderGuardian(
                    self.adapter, config=self.config, poll_interval_ms=poll_interval_ms, bus=self.bus)
                LOG.info("✅ OrderGuardian initialized for ExecPosFSM")

                # ✅ FIX: Defer OrderGuardian startup until after FSM initialization
                # Will be started via start_order_guardian() method when event loop is available
                LOG.info("✅ OrderGuardian ready for startup")

                # ✅ FIX: Add startup re-linking to detect existing orphaned orders
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
                self._schedule_bracket_health_loop()
                self.watchdog.start()  # Start timeout watchdog (always, not just on guardian failure)
            except Exception as e:
                LOG.error(f"Failed to initialize OrderGuardian: {e}")
                self.order_guardian = None
                self.watchdog.start()  # Start timeout watchdog even if guardian fails
                self._schedule_fsm_cleanup_loop()
                self._schedule_bracket_health_loop()
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
            LOG.info("✅ OrderGuardian initialized for ExecPosFSM (shadow mode)")
            guardian_symbols = self._collect_guardian_symbols()
            if guardian_symbols:
                try:
                    self.order_guardian.update_known_symbols(guardian_symbols)
                except AttributeError:
                    pass
            self._schedule_guardian_start()
            self._schedule_fsm_cleanup_loop()
            self._schedule_bracket_health_loop()
            self.watchdog.start()  # Start timeout watchdog in shadow mode too

        # Subscribe to Guardian TIDY events to update gate state
        try:
            if hasattr(self, 'bus') and self.bus:
                self.bus.listen("EVT:SYMBOL_TIDY", self._on_symbol_tidy_event)
        except Exception:
            pass

    async def run_leverage_bootstrap(self) -> Set[str]:
        """Run leverage bootstrap to sync margin mode and leverage with exchange.

        P3: Active Leverage Management — Runtime Integration

        This method:
        1. Collects LeverageConfig from all active strategy configs
        2. Runs LeverageBootstrapper to sync each symbol
        3. Returns set of symbols that failed (blocked from trading)

        MUST be called AFTER _initialize_adapter() and BEFORE trading starts.

        Returns:
            Set of symbols that failed to sync (should be blocked from trading)
        """
        if self.shadow_mode or self.adapter is None:
            LOG.info(
                "TASK47c-P3: Leverage bootstrap skipped (shadow mode or no adapter)")
            return set()

        # LEVERAGE-SSOT-FIX-01: Validate consistency and log warnings
        ssot_warnings = self.validate_leverage_ssot_consistency()
        if ssot_warnings:
            LOG.warning(
                f"LEVERAGE-SSOT-FIX-01: Found {len(ssot_warnings)} legacy leverage values in strategy configs. "
                "These are IGNORED. SSOT is instruments.yaml."
            )

        # Import here to avoid circular imports
        from apps.reference.domains.execution_position.bootstrapping.leverage_bootstrapper import (
            LeverageBootstrapper,
        )

        # Collect leverage configs from strategies
        leverage_configs = self._collect_leverage_configs()

        if not leverage_configs:
            LOG.warning(
                "TASK47c-P3: No leverage configs found, bootstrap skipped")
            return set()

        LOG.info(
            f"TASK47c-P3: Running leverage bootstrap for {len(leverage_configs)} symbols")

        bootstrapper = LeverageBootstrapper(adapter=self.adapter, logger=LOG)
        results = await bootstrapper.run(leverage_configs)

        if results.has_failures:
            LOG.error(
                f"TASK47c-P3: Leverage bootstrap FAILED for {len(results.failed)} symbols: {results.failed}"
            )
            for sym in results.failed:
                fail_result = results.failures.get(sym)
                if fail_result:
                    LOG.error(
                        f"  {sym}: code={fail_result.error_code}, msg={fail_result.error_msg}")
        else:
            LOG.info(
                f"TASK47c-P3: Leverage bootstrap SUCCESS for all {len(leverage_configs)} symbols")

        return set(results.failed)

    def _collect_leverage_configs(self) -> Dict[str, "LeverageConfig"]:
        """Collect LeverageConfig from instruments.yaml SSOT.

        LEVERAGE-SSOT-FIX-01: Read from instruments.<SYM>.execution.target_leverage
        instead of strategies.*.assets.<SYM>.leverage to avoid SSOT conflict.

        The instruments.yaml is the SSOT for:
        - Sizing calculations (DecisionMaking._calculate_position_size)
        - Exposure guard (ExposureGuard.resolve_symbol_leverage)
        - Bootstrap (this method → LeverageBootstrapper)

        Returns:
            Dict mapping symbol → LeverageConfig (only active symbols with execution config)
        """
        from apps.reference.config_models import LeverageConfig

        result: Dict[str, LeverageConfig] = {}

        # Get active symbols from strategies_registry assignments
        try:
            registry = self.config.strategies_registry
            if registry is None or not hasattr(registry, 'assignments'):
                LOG.warning(
                    "LEVERAGE-SSOT-FIX-01: No strategies_registry.assignments found")
                return result
            assignments = registry.assignments or {}
        except AttributeError:
            LOG.warning(
                "LEVERAGE-SSOT-FIX-01: Failed to read strategies_registry.assignments")
            return result

        # Get instruments dict
        instruments = getattr(self.config, 'instruments', None)
        if not isinstance(instruments, dict):
            LOG.warning(
                "LEVERAGE-SSOT-FIX-01: No instruments dict found in config")
            return result

        for symbol in assignments.keys():
            spec = instruments.get(symbol)
            if spec is None:
                LOG.warning(
                    f"LEVERAGE-SSOT-FIX-01: Symbol {symbol} in assignments but not in instruments")
                continue

            exec_cfg = getattr(spec, 'execution', None)
            if exec_cfg is None:
                LOG.warning(
                    f"LEVERAGE-SSOT-FIX-01: Symbol {symbol} has no execution config")
                continue

            target_leverage = getattr(exec_cfg, 'target_leverage', None)
            margin_mode = getattr(exec_cfg, 'margin_mode', 'isolated')

            if target_leverage is None:
                LOG.warning(
                    f"LEVERAGE-SSOT-FIX-01: Symbol {symbol} has no target_leverage")
                continue

            # Convert margin_mode to LeverageConfig format
            # instruments.yaml uses "isolated"/"cross", LeverageConfig uses "ISOLATED"/"CROSSED"
            mode_map = {"isolated": "ISOLATED", "cross": "CROSSED"}
            mode_normalized = mode_map.get(
                margin_mode.lower() if isinstance(margin_mode, str) else "isolated",
                "ISOLATED"
            )

            # Create LeverageConfig from instruments SSOT
            result[symbol] = LeverageConfig(
                target=int(target_leverage),
                mode=mode_normalized,
            )

        LOG.info(
            f"LEVERAGE-SSOT-FIX-01: Collected leverage from instruments.yaml for {len(result)} symbols: "
            f"{[(s, c.target) for s, c in result.items()]}"
        )
        return result

    def validate_leverage_ssot_consistency(self) -> List[str]:
        """Validate that strategy leverage configs match instruments SSOT.

        LEVERAGE-SSOT-FIX-01: Startup guard to detect legacy/stale strategy leverage.

        Checks:
        - strategies.aurora.assets.<SYM>.leverage.target vs instruments.<SYM>.execution.target_leverage
        - strategies.mean_reversion.assets.<SYM>.leverage.target vs instruments.<SYM>.execution.target_leverage

        Returns:
            List of warning messages for mismatches (empty if consistent)
        """
        warnings: List[str] = []

        instruments = getattr(self.config, 'instruments', None)
        if not isinstance(instruments, dict):
            return warnings

        # Check Aurora strategy assets
        try:
            aurora = self.config.strategies.aurora
            if aurora and aurora.assets:
                for symbol, asset_cfg in aurora.assets.items():
                    if asset_cfg and asset_cfg.leverage:
                        strategy_lev = asset_cfg.leverage.target
                        spec = instruments.get(symbol)
                        if spec and spec.execution:
                            inst_lev = spec.execution.target_leverage
                            if strategy_lev != inst_lev:
                                warnings.append(
                                    f"LEVERAGE_SSOT_MISMATCH: {symbol} aurora.leverage.target={strategy_lev} "
                                    f"!= instruments.execution.target_leverage={inst_lev} "
                                    f"(SSOT is instruments.yaml, strategy value is IGNORED)"
                                )
        except AttributeError:
            pass

        # Check MeanReversion strategy assets
        try:
            mr = self.config.strategies.mean_reversion
            if mr and mr.assets:
                for symbol, asset_cfg in mr.assets.items():
                    if asset_cfg and asset_cfg.leverage:
                        strategy_lev = asset_cfg.leverage.target
                        spec = instruments.get(symbol)
                        if spec and spec.execution:
                            inst_lev = spec.execution.target_leverage
                            if strategy_lev != inst_lev:
                                warnings.append(
                                    f"LEVERAGE_SSOT_MISMATCH: {symbol} mean_reversion.leverage.target={strategy_lev} "
                                    f"!= instruments.execution.target_leverage={inst_lev} "
                                    f"(SSOT is instruments.yaml, strategy value is IGNORED)"
                                )
        except AttributeError:
            pass

        for warn in warnings:
            LOG.warning(warn)

        return warnings

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

    def _mark_processed_event(self, event_key: str) -> bool:
        """Idempotency helper with bounded memory."""
        if self._processed_events.seen(event_key):
            return False

        now_ms = get_clock().now_ms()
        self._processed_events.add(event_key, now_ms)
        return True

    def _get_config_value(self, path: list[str], default: Any = None) -> Any:
        """Safely traverse mixed dict/object configurations."""
        node: Any = self.config
        for key in path:
            if node is None:
                return default
            try:
                if isinstance(node, dict):
                    node = node.get(key)
                else:
                    node = getattr(node, key)
            except (AttributeError, KeyError, TypeError):
                return default
        return node if node is not None else default

    def _resolve_guardian_config(self) -> Dict[str, Any]:
        """Aggregate guardian config from SSOT: domains.execution_position.guardian.

        MAGIC-NUM-EXTRACTION: All guardian config now from domains.yaml, no hardcoded defaults.
        """
        # SSOT: domains.execution_position.guardian (fail-closed if missing)
        try:
            guardian_cfg = self.config.domains.execution_position.guardian
            if guardian_cfg is None:
                raise ValueError(
                    "guardian config is required in domains.execution_position")

            return {
                "unified": bool(guardian_cfg.unified),
                "emit_tidy_event": bool(guardian_cfg.emit_tidy_event),
                "poll_interval_ms": int(guardian_cfg.poll_interval_ms),
                "cleanup_ttl_ms": int(guardian_cfg.cleanup_ttl_ms),
                "symbol_cooldown_ms": int(guardian_cfg.symbol_cooldown_ms),
            }
        except (AttributeError, TypeError) as e:
            raise ValueError(
                f"Failed to load guardian config from domains.execution_position: {e}. "
                "Check domains.yaml has execution_position.guardian section."
            ) from e

    def _collect_guardian_symbols(self) -> Set[str]:
        """Gather configured trading symbols for guardian ownership tracking."""
        symbols: Set[str] = set()
        instruments = self._get_config_value(
            ["trading", "instruments"], default={})
        if isinstance(instruments, dict):
            for sym in instruments.keys():
                if sym:
                    symbols.add(str(sym).upper())
        return symbols

    def set_async_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Register the shared asyncio loop for guardian/adapter tasks."""
        self._async_loop = loop

    def _get_async_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """Resolve the active asyncio loop for scheduling background work."""
        loop = self._async_loop
        if loop and not loop.is_closed():
            return loop
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    def _submit_async(
        self,
        coro: Coroutine[Any, Any, Any],
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        """Schedule coroutine on a target loop, thread-safe."""
        target_loop = loop or self._get_async_loop()
        if not target_loop:
            LOG.debug("No asyncio loop available to schedule %r", coro)
            return

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is target_loop:
            target_loop.create_task(coro)
        else:
            asyncio.run_coroutine_threadsafe(coro, target_loop)

    def _schedule_guardian_start(self) -> None:
        """Ensure guardian poller and startup reconcile are scheduled once."""
        if self._guardian_start_scheduled:
            return
        guardian = aget(self, "order_guardian", None)
        if not guardian:
            return

        loop = self._get_async_loop()
        if not loop:
            LOG.debug("OrderGuardian start deferred: no event loop active")
            return

        self._submit_async(guardian.start(), loop)
        self._submit_async(self._startup_order_guardian_reconcile(), loop)
        LOG.info("✅ OrderGuardian background tasks scheduled")
        self._guardian_start_scheduled = True

    def _schedule_fsm_cleanup_loop(self) -> None:
        """Start FSM-side cleanup loop respecting unified guardian config."""
        if self._bg_started:
            return
        if not self._orphan_cfg.get("enabled"):
            return
        if not aget(self, "order_guardian", None):
            return
        if self._guardian_unified and not self._fsm_cleanup_enabled:
            if not self._fsm_cleanup_logged:
                LOG.info("[FSM-CLEANUP] disabled_by_config (unified=true)")
                self._fsm_cleanup_logged = True
            return

        loop = self._get_async_loop()
        if not loop:
            LOG.debug("FSM cleanup start deferred: no event loop active")
            return

        self._submit_async(self._cleanup_loop(), loop)
        self._bg_started = True

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
        """
        EP-01.3-INT: Cancel pending entry orders for a symbol.

        Iterates through watchdog tracked orders (pending_orders + acked_orders)
        and cancels those matching the symbol.

        Args:
            symbol: Symbol to cancel pending entries for
            reason: Cancel reason code (e.g., CANCEL_STALE_REGIME, CANCEL_SUPERSEDED)
            context: Additional context for logging
        """
        if not self.watchdog:
            return

        orders_to_cancel = []

        # Check pending_orders (not yet ACKed)
        for order_id, deadline in list(self.watchdog.pending_orders.items()):
            if deadline.symbol == symbol:
                orders_to_cancel.append((order_id, deadline))

        # Check acked_orders (ACKed but not yet filled)
        for order_id, deadline in list(self.watchdog.acked_orders.items()):
            if deadline.symbol == symbol:
                orders_to_cancel.append((order_id, deadline))

        if not orders_to_cancel:
            LOG.debug(
                f"EP-01.3: No pending entries to cancel for {symbol} ({reason})")
            return

        LOG.info(
            f"EP-01.3: Cancelling {len(orders_to_cancel)} pending entries for {symbol} "
            f"(reason={reason}, context={context})"
        )

        for order_id, deadline in orders_to_cancel:
            # Schedule async cancel
            loop = self._get_async_loop()
            if loop and self.adapter and not self.shadow_mode:
                async def _do_cancel(oid: str, sym: str, dl: 'OrderDeadline'):
                    try:
                        await self._cancel_order(sym, oid)
                        LOG.info(
                            f"✅ EP-01.3: Cancelled pending entry {oid} ({reason})")
                        # Remove from watchdog tracking
                        self.watchdog.on_order_cancel(oid)
                        # Log cancellation
                        order_logger.write({
                            "rid": dl.rid,
                            "event_type": "ORDER_CANCELLED",
                            "symbol": sym,
                            "order_id": oid,
                            "reason": reason,
                            "context": context,
                            "timestamp": get_clock().now_ms()
                        })
                    except Exception as e:
                        if self._is_unknown_order_error(e):
                            LOG.info(
                                f"✅ EP-01.3: Pending entry {oid} already absent (-2011)")
                            self.watchdog.on_order_cancel(oid)
                        else:
                            LOG.warning(
                                f"EP-01.3: Failed to cancel pending entry {oid}: {e}")

                self._submit_async(_do_cancel(
                    order_id, symbol, deadline), loop)
            else:
                # Just remove from tracking (shadow mode or no adapter)
                self.watchdog.on_order_cancel(order_id)

    def _cancel_all_pending_entries(self, reason: str = "CANCEL_PANIC_KILL") -> None:
        """
        PANIC-INT: Cancel ALL pending entry orders across all symbols.

        Called when panic_killswitch is activated. Iterates through all tracked
        orders in watchdog and cancels them immediately.

        Args:
            reason: Cancel reason code (default: CANCEL_PANIC_KILL)
        """
        if not self.watchdog:
            return

        # Collect all symbols with pending entries
        symbols_with_pending = set()
        for deadline in self.watchdog.pending_orders.values():
            symbols_with_pending.add(deadline.symbol)
        for deadline in self.watchdog.acked_orders.values():
            symbols_with_pending.add(deadline.symbol)

        if not symbols_with_pending:
            LOG.debug(f"PANIC-INT: No pending entries to cancel ({reason})")
            return

        LOG.warning(
            f"PANIC-INT: Cancelling ALL pending entries for {len(symbols_with_pending)} symbols ({reason})"
        )

        for symbol in symbols_with_pending:
            self._cancel_pending_entries_for_symbol(
                symbol=symbol,
                reason=reason,
                context="panic_killswitch_activated"
            )

    def on_panic_killswitch_activated(self) -> None:
        """
        PANIC-INT: Handle panic killswitch activation.

        External code (e.g., config watcher, API endpoint) should call this
        when panic_killswitch transitions from False to True.
        """
        LOG.error(
            "PANIC-INT: panic_killswitch ACTIVATED - cancelling all pending entries")

        # Check config flag
        try:
            pe_ttl_cfg = self.config.domains.execution_position.pending_entry_ttl
            if not pe_ttl_cfg.enabled or not pe_ttl_cfg.cancel_on_panic:
                LOG.info("PANIC-INT: cancel_on_panic disabled, skipping")
                return
        except AttributeError:
            LOG.warning(
                "PANIC-INT: pending_entry_ttl config not loaded, cancelling anyway")

        self._cancel_all_pending_entries("CANCEL_PANIC_KILL")

    def _process_queued_supersede(self, symbol: str) -> None:
        """
        EP-01.3-SUPERSEDE-ACK: Process queued DEC:OPEN after cancel is confirmed.

        Called when:
        1. WS/REST confirms pending entry is CANCELED
        2. Timeout expires (5s) and we proceed anyway

        Args:
            symbol: Symbol to process queued open for
        """
        # Remove from canceling set
        self._supersede_canceling.discard(symbol)

        # Get queued decision
        queued_data = self._supersede_queue.pop(symbol, None)
        if not queued_data:
            LOG.debug(f"EP-01.3: No queued supersede for {symbol}")
            return

        decision = queued_data.get("decision")
        queued_at = queued_data.get("queued_at", 0)
        age_sec = get_clock().now_sec() - queued_at

        if not decision:
            LOG.warning(
                f"EP-01.3: Queued supersede for {symbol} has no decision")
            return

        LOG.info(
            f"EP-01.3: Executing queued supersede DEC:OPEN for {symbol} (waited {age_sec:.2f}s)"
        )

        # Re-submit the decision for processing
        # This will go through normal flow since cancel is now confirmed
        loop = self._get_async_loop()
        if loop:
            self._submit_async(self._async_execute_decision(decision), loop)
        else:
            LOG.error(f"EP-01.3: No event loop for queued supersede {symbol}")

    def _on_regime_detected(self, event: Message) -> None:
        """
        EP-01: Handle EVT:REGIME_DETECTED to update ExposureGuard risk limits.
        EP-01.3-INT: Cancel pending entry orders on regime change.

        This wires RegimeDetector output to ExposureGuard policy adaptation.
        The mapping from RegimeLabel → ExecutionRegimeBucket happens here.
        """
        pld = event.pld or {}
        regime_str = pld.get("regime")
        symbol = pld.get("symbol")
        if not regime_str:
            LOG.warning(
                "EP-01: EVT:REGIME_DETECTED missing 'regime' field, skipping")
            return

        # Map detector label to policy bucket
        bucket = map_regime_to_bucket(regime_str)

        # Delegate to ExposureGuard
        self.exposure_guard.on_regime_changed(bucket)

        # BRACKET-HEALTH: Track last regime per symbol for TPSL computation
        if symbol:
            self._last_regime_by_symbol[symbol] = regime_str

        LOG.info(
            f"EP-01: Regime adaptation triggered: label={regime_str} → bucket={bucket.value}, "
            f"new_ratio={float(self.exposure_guard.max_directional_ratio):.2f}"
        )

        # EP-01.3-INT: Cancel pending entry orders on regime change
        try:
            pe_ttl_cfg = self.config.domains.execution_position.pending_entry_ttl
            if pe_ttl_cfg.enabled and pe_ttl_cfg.cancel_on_regime_change and symbol:
                self._cancel_pending_entries_for_symbol(
                    symbol=symbol,
                    reason="CANCEL_STALE_REGIME",
                    context=f"regime_changed_to_{regime_str}"
                )
        except AttributeError:
            pass  # Config not loaded

    def _on_trade_intent_proposed(self, msg: Message) -> None:
        """
        Handle TRADE_INTENT_PROPOSED event from DecisionMaking directly (SSOT).

        This handler replaces the legacy AuroraBridge. It routes:
        - Normal Intents -> CMD:OPEN
        - Reduce-Only Intents -> CMD:CLOSE
        - Failures -> EVT:TRADE_INTENT_REJECTED
        """
        try:
            pld = msg.pld or {}
            # DecisionMaking uses "instrument" for symbol in trade_intent_v1 schema
            symbol = pld.get("instrument") or pld.get("symbol")
            if not symbol:
                LOG.error(
                    f"TRADE_INTENT_PROPOSED missing symbol/instrument: keys={list(pld.keys())}")
                return
            strategy_id = pld.get("strategy") or pld.get("strategy_id")
            # WHY-CHAIN/TRACE: Treat payload rid as canonical trace_id.
            # FSMCore emits Message.rid independently; upstream rid lives in payload.
            intent_rid = str(pld.get("rid") or msg.rid or "unknown")

            # Log intent via authorized adapter
            self.log_adapter.log_trade_intent(
                rid=intent_rid,
                symbol=symbol,
                side=pld.get("side", ""),
                qty=pld.get("order", {}).get("qty"),
                price=pld.get("order", {}).get("price"),
                features=pld.get("features"),
                risk_score=pld.get("risk_budget", {}).get(
                    "trade_cvar95_max_bps")  # Approx mapping
            )

            order_info = pld.get("order", {})
            reduce_only = (
                pld.get("reduce_only")
                or order_info.get("reduce_only")
                or order_info.get("reduceOnly")
            )

            result: Optional[Message] = None

            if reduce_only:
                # Route to CLOSE flow
                cmd_close = Message(
                    op="CMD",
                    verb="CLOSE",
                    src="execution_position",
                    dst="execution_position",
                    rid=intent_rid,
                    pld={
                        "symbol": symbol,
                        "reason": pld.get("reason") or "intent_reduce_only",
                        "idempotent_key": pld.get("idempotent_key"),
                        "retry_key": pld.get("retry_key"),
                    },
                    why=f"intent_reduce_only:{intent_rid}",
                    data_ref=msg.data_ref
                )
                LOG.info(
                    f"[{symbol}] Processing TRADE_INTENT (reduce_only) -> CMD:CLOSE")
                result = self.handle(cmd_close)

            else:
                # QUIET-HOURS GATE: Block new entries during quiet hours
                if not self._quiet_hours_gate_allow():
                    LOG.warning(
                        f"[{symbol}] TRADE_INTENT BLOCKED by quiet hours gate"
                    )
                    if hasattr(self, "bus"):
                        self.bus.emit(
                            "EVT:TRADE_INTENT_REJECTED",
                            {
                                "symbol": symbol,
                                "reason": "QUIET_HOURS_BLOCKED",
                                "rid": intent_rid,
                            },
                            "quiet_hours_gate",
                            msg.data_ref,
                        )
                    return

                # Route to OPEN flow - STRICT FAIL-CLOSED VALIDATION (EXEC-FAILCLOSED-ORDERFIELDS-01)

                # CFG-SMART-EXTRACT-02: Extract and log TCA & Risk Context for forensics
                tca_budget = pld.get("tca_budget") or {}
                risk_ctx = pld.get("risk_context") or {}

                # Extract key TCA parameters
                slippage_limit = tca_budget.get("max_slippage_bps")
                latency_limit = tca_budget.get("max_latency_ms")
                maker_pref = tca_budget.get("maker_preference")

                # Extract key Risk parameters
                risk_score = risk_ctx.get("risk_score")
                cvar_budget = risk_ctx.get("trade_cvar95_bps")

                # Enhanced metadata logging for debugging strategy→execution contract
                LOG.info(
                    f"[{symbol}] Intent Metadata: Strategy={strategy_id} "
                    f"TCA={{slippage={slippage_limit}bps, latency={latency_limit}ms, maker={maker_pref}}} "
                    f"Risk={{score={risk_score}, cvar={cvar_budget}bps}}"
                )

                # 1. Check strict existence of order_type (No defaults to MARKET)
                order_type = order_info.get("order_type")
                if not order_type:
                    raise ValueError(
                        "NRR-INTENT-MISSING-ORDER_TYPE: Strategy must provide explicit order_type (LIMIT/MARKET)")

                # 2. Validate Constraints
                price = str(order_info.get("price")) if order_info.get(
                    "price") else None
                tif = order_info.get("tif")

                if order_type == "LIMIT":
                    if not price:
                        raise ValueError(
                            "NRR-INTENT-MISSING-PRICE: LIMIT order requires price")
                    if not tif:
                        raise ValueError(
                            "NRR-INTENT-MISSING-TIF: LIMIT order requires tif (GTC/GTX/IOC/FOK)")

                elif order_type == "MARKET":
                    if tif:
                        # User requested strict cleanliness. "MARKET with tif present -> reject"
                        raise ValueError(
                            f"NRR-INTENT-INVALID-TIF: MARKET order must not have tif (got {tif})")

                # SSOT-BRIDGE-SUNSET-01: Extract stop/target prices with price_ctx fallback
                stop_price_raw = self._resolve_price(pld, "stop_price")
                target_price_raw = self._resolve_price(pld, "target_price")

                cmd_payload = {
                    "symbol": symbol,
                    "side": pld.get("side"),
                    "qty": str(order_info.get("qty")),
                    "order_type": order_type,
                    "price": price,
                    "tif": tif,
                    "stop_price": stop_price_raw,
                    "target_price": target_price_raw,
                    "rid": intent_rid,
                    "valid_for_ms": pld.get("valid_for_ms"),
                    "idempotent_key": pld.get("idempotent_key"),
                    "price_ref": str(order_info.get("price_ref")) if order_info.get("price_ref") else None,
                    "strategy": strategy_id,
                }

                cmd_metadata: Dict[str, Any] = {}
                if strategy_id:
                    cmd_metadata["strategy_id"] = str(strategy_id)
                if isinstance(tca_budget, dict) and tca_budget:
                    cmd_metadata["tca_budget"] = dict(tca_budget)
                if isinstance(risk_ctx, dict) and risk_ctx:
                    cmd_metadata["risk_context"] = dict(risk_ctx)
                if cmd_metadata:
                    cmd_payload["metadata"] = cmd_metadata

                cmd_open = Message(
                    op="CMD",
                    verb="OPEN",
                    src="execution_position",
                    dst="execution_position",
                    rid=intent_rid,
                    pld=cmd_payload,
                    why=f"intent_execution:{intent_rid}",
                    data_ref=msg.data_ref
                )

                LOG.info(
                    f"[{symbol}] Processing TRADE_INTENT -> CMD:OPEN (qty={cmd_payload['qty']} side={cmd_payload.get('side')} type={order_type})")
                result = self.handle(cmd_open)

            # Handle Result
            if result:
                LOG.info(
                    f"[{symbol}] TRADE_INTENT processed: {result.op}:{result.verb}")

                # Emit the decision event (DEC:OPEN, DEC:CLOSE, etc.) to the bus
                # so that listeners (Adapters, Loggers, Tests) can react.
                if hasattr(self, "bus"):
                    out_pld = dict(result.pld or {})
                    out_pld.setdefault("rid", result.rid)
                    self.bus.emit(
                        f"{result.op}:{result.verb}",
                        out_pld,
                        result.why,
                        result.data_ref
                    )

                if result.op == "ERR":
                    # Emit REJECT event for feedback loop
                    LOG.warning(f"[{symbol}] Execution Rejected: {result.why}")
                    reject_evt = Message(
                        op="EVT",
                        verb="TRADE_INTENT_REJECTED",
                        src="execution_position",
                        dst="*",
                        rid=intent_rid,
                        pld={
                           "symbol": symbol,
                           "reason": result.why,
                           "original_verification_key": pld.get("idempotent_key"),
                           "rid": intent_rid,
                        },
                        why="execution_rejected",
                        # Preserve upstream WHY chain even if ERR message drops it.
                        data_ref=msg.data_ref,
                    )
                    if hasattr(self, "bus"):
                        self.bus.emit(
                            "EVT:TRADE_INTENT_REJECTED",
                            reject_evt.pld,
                            reject_evt.why,
                            reject_evt.data_ref
                        )
            else:
                # Silent failure (should not happen if handle works properly)
                LOG.warning(
                    f"[{symbol}] TRADE_INTENT processed but no result returned from handle()")
                # Emit generic reject? Safe to do so.
                if hasattr(self, "bus"):
                    self.bus.emit(
                        "EVT:TRADE_INTENT_REJECTED",
                        {"symbol": symbol, "reason": "internal_error_no_result",
                            "rid": intent_rid},
                        "execution_no_result",
                        msg.data_ref,
                    )

        except Exception as e:
            LOG.error(
                f"Failed to process TRADE_INTENT_PROPOSED: {e}", exc_info=True)
            # Emit REJECT for fail-closed feedback
            if hasattr(self, "bus"):
                try:
                    pld = msg.pld or {}
                    symbol = pld.get("instrument") or pld.get(
                        "symbol") or "unknown"
                    self.bus.emit(
                        "EVT:TRADE_INTENT_REJECTED",
                        {
                            "symbol": symbol,
                            "reason": f"EXCEPTION: {str(e)}",
                            "error_type": type(e).__name__,
                            "rid": str(pld.get("rid") or msg.rid or "unknown"),
                        },
                        "execution_exception",
                        msg.data_ref,
                    )
                except Exception as emit_e:
                    LOG.error(f"Failed to emit exception rejection: {emit_e}")

    def _on_trade_intent_rejected(self, msg: Message) -> None:
        """
        Handle TRADE_INTENT_REJECTED event from DecisionMaking.

        Logs the rejection to aurora_trades.log for comprehensive audit trail.
        """
        try:
            pld = msg.pld or {}
            symbol = pld.get("instrument") or pld.get("symbol")
            if not symbol:
                return

            self.log_adapter.log_guard_rejection(
                rid=msg.rid or "unknown",
                symbol=symbol,
                side=pld.get("side", "unknown"),
                guard_type=pld.get("reason", "DECISION_REJECT"),
                reason=pld.get("context") or pld.get(
                    "details", "") or "Strategy rejection",
                strategy_id=pld.get("strategy_id")
            )
        except Exception as e:
            LOG.error(f"Failed to process TRADE_INTENT_REJECTED: {e}")

    def _on_portfolio_state_updated(self, event: Message) -> None:
        """
        Handle EVT:PORTFOLIO_STATE_UPDATED events to update exposure guard state.

        EXP-FIX: Store latest portfolio state for exposure checks.
        EXP-LEVERAGE-001: Update exposure guard with portfolio data.
        """
        self._latest_portfolio_state = event.pld or {}

        # EXP-LEVERAGE-001: Update exposure guard with latest portfolio state
        self.exposure_guard.on_portfolio(self._latest_portfolio_state)

        # ORDER_INDEX: Best-effort TTL cleanup (WS correlation index lives on FSMCore)
        try:
            # type: ignore[attr-defined]
            if hasattr(self.fsm, "order_index") and self.fsm.order_index:
                self.fsm.order_index.expire()  # type: ignore[attr-defined]
        except Exception:
            # Fail-open: correlation is an auxiliary feature
            pass

        # ✅ EVT:EXPOSURE_SUMMARY_UPDATED: Emit exposure summary after portfolio update
        try:
            exposure_summary = self.exposure_guard.get_exposure_summary()
            exposure_msg = Message(
                op="EVT",
                verb="EXPOSURE_SUMMARY_UPDATED",
                src="execution_position",
                dst="decision_making",
                rid="portfolio_update",
                pld={
                    "exposure_summary": exposure_summary,
                    "portfolio_state": self._latest_portfolio_state,
                    "timestamp_ms": get_clock().now_ms()
                },
                why="exposure_summary_updated_after_portfolio_change",
            )
            # FIX-EMIT-COMPAT: FSMCore.emit signature is (event, pld, why, ref), but emit_compat calls (op, verb, pld, why).
            # This argument shift causes the event to be emitted as "EVT" with verb as payload.
            # We explicitly handle the emission here.

            async def _do_emit_exposure():
                try:
                    # Try FSMCore signature first (event_name, payload, why)
                    self.fsm.emit(
                        "EVT:EXPOSURE_SUMMARY_UPDATED",
                        {
                            "exposure_summary": exposure_summary,
                            "portfolio_state": self._latest_portfolio_state,
                            "timestamp_ms": get_clock().now_ms()
                        },
                        "exposure_summary_updated_after_portfolio_change"
                    )
                except TypeError:
                    # Fallback for Actor/AsyncFSM (accepts Message)
                    await emit_compat(self.fsm, exposure_msg, logger=LOG)
                except Exception as ex:
                    LOG.error(f"Failed to emit exposure summary: {ex}")

            loop = self._get_async_loop()
            if loop:
                self._submit_async(_do_emit_exposure(), loop)
        except Exception as e:
            LOG.debug(f"Failed to prepare exposure summary update: {e}")

        # ✅ FIX: Detect position closures robustly (including symbols disappearing from snapshot).
        # When position becomes 0, TP/SL orders become orphaned and need cleanup.
        try:
            positions = self._latest_portfolio_state.get("positions") or []
            current_amts: Dict[str, float] = {}
            for pos in positions:
                sym = pos.get("symbol")
                if not sym:
                    continue
                try:
                    current_amts[sym] = float(pos.get("positionAmt") or 0.0)
                except Exception:
                    current_amts[sym] = 0.0

            epsilon = 1e-10
            all_syms = set(self._prev_position_amts.keys()
                           ) | set(current_amts.keys())
            for sym in all_syms:
                prev_amt = float(self._prev_position_amts.get(sym, 0.0))
                now_amt = float(current_amts.get(sym, 0.0))
                if abs(prev_amt) >= epsilon and abs(now_amt) < epsilon:
                    closed_at = get_clock().now_sec()
                    self._last_position_closed_ts[sym] = closed_at
                    self._last_any_position_closed_ts = closed_at

                    LOG.info(
                        f"[POSITION_CLOSED] {sym}: position closed (was {prev_amt}, now {now_amt})"
                    )

                    # Position closed - trigger immediate orphan cleanup for this symbol
                    if hasattr(self, "order_guardian") and self.order_guardian:
                        loop = self._get_async_loop()
                        if loop:
                            self._submit_async(
                                self.order_guardian.reconcile_symbol(
                                    sym, "portfolio_update"),
                                loop,
                            )

            self._prev_position_amts = current_amts
        except Exception as e:
            LOG.debug(f"Error checking position closures: {e}")

        # Clean up stale reservations on portfolio updates
        expired = self.exposure_guard.expire_stale()

        # EXP-FIX: Release post-fill holds since portfolio is now updated
        released_postfill = list(
            self.exposure_guard.state.postfill_reservations.keys()
        )
        for key in released_postfill:
            self.exposure_guard.state.postfill_reservations.pop(key, None)

        if released_postfill:
            LOG.debug(
                f"RELEASED_POSTFILL_HOLDS: {len(released_postfill)} keys")

        if expired:
            # EXP-FIX: Record expired post-fill holds
            if hasattr(self, "metrics_collector") and self.metrics_collector:
                for _ in expired:
                    if _ in self.exposure_guard.state.postfill_reservations:
                        self.metrics_collector.record_postfill_expired()

            # Emit event for expired reservations
            expired_msg = Message(
                op="EVT",
                verb="PENDING_EXPOSURE_EXPIRED",
                src="execution_position",
                dst="monitoring",
                rid="exposure_cleanup",
                pld={"expired_keys": expired, "why": "ttl_expired"},
                why="exposure_cleanup",
            )
            loop = self._get_async_loop()
            if loop:
                self._submit_async(
                    emit_compat(
                        self.fsm,
                        expired_msg,
                        logger=aget(self, "logger", None),
                    ),
                    loop,
                )

    def _on_order_ack(self, event: Message) -> None:
        """
        Handle EVT:ORDER_ACK events from adapter.

        AGENT-PATCH: Process ACK to update order state and release pre-fill holds.
        """
        payload = event.pld or {}
        order_id = payload.get("orderId")
        symbol = payload.get("symbol")
        rid = payload.get("rid") or event.rid

        if not order_id or not symbol:
            LOG.warning(
                f"[ACK] Missing orderId or symbol in ACK event: {payload}")
            return

        # 🔄 IDEMPOTENT: Check if this event was already processed
        event_key = f"ack_{order_id}_{symbol}"
        if not self._mark_processed_event(event_key):
            LOG.debug(
                f"[ACK] Skipping duplicate ACK for {symbol} order {order_id}")
            return

        LOG.debug(
            f"[ACK] Processing ACK for {symbol} order {order_id} (rid={rid})")

        # Release pre-fill hold from exposure guard
        # NOTE: prefill_reservations was a design concept but not implemented in ExposureState
        # Only postfill_reservations exists. This handler just needs to handle the ACK event.
        if hasattr(self, "exposure_guard"):
            LOG.debug(f"[ACK] Order {order_id} acknowledged for {symbol}")

        # Notify watchdog (used by routing/recovery tests)
        try:
            if hasattr(self, "watchdog") and self.watchdog is not None:
                # FIX: Pass order_id (str) not Message event
                self.watchdog.on_order_ack(order_id)
        except Exception as e:
            LOG.warning(f"[ACK] Failed to notify watchdog for {order_id}: {e}")

    def _on_order_fill(self, event: Message) -> None:
        """
        Handle EVT:ORDER_FILL events from adapter.

        AGENT-PATCH: Process FILL to update order state and create post-fill holds.
        """
        payload = event.pld or {}
        order_id = payload.get("orderId")
        symbol = payload.get("symbol")
        filled_qty = payload.get("quantity")
        rid = payload.get("rid") or event.rid
        client_order_id = payload.get(
            "clientOrderId") or payload.get("client_order_id")

        if not order_id or not symbol or filled_qty is None:
            LOG.warning(
                f"[FILL] Missing orderId, symbol or quantity in FILL event: {payload}")
            return

        # 🔄 IDEMPOTENT: Check if this event was already processed
        event_key = f"fill_{order_id}_{symbol}"
        if not self._mark_processed_event(event_key):
            LOG.debug(
                f"[FILL] Skipping duplicate FILL for {symbol} order {order_id}")
            return

        LOG.debug(
            f"[FILL] Processing FILL for {symbol} order {order_id}, qty={filled_qty} (rid={rid})")

        # FIX: Notify watchdog that order is filled (stop timeout tracking)
        try:
            if hasattr(self, "watchdog") and self.watchdog is not None:
                self.watchdog.on_order_fill(order_id)
        except Exception as e:
            LOG.warning(
                f"[FILL] Failed to notify watchdog for {order_id}: {e}")

        # TASK40: Mark entry order terminal in OrderIndex (unblocks one-open-order guard).
        try:
            # type: ignore[attr-defined]
            if hasattr(self.fsm, "order_index") and self.fsm.order_index:
                ref = None
                ref = self.fsm.order_index.get(exchangeOrderId=str(
                    order_id))  # type: ignore[attr-defined]
                if ref is None and client_order_id:
                    ref = self.fsm.order_index.get(clientOrderId=str(
                        client_order_id))  # type: ignore[attr-defined]
                if ref is None and rid:
                    # type: ignore[attr-defined]
                    ref = self.fsm.order_index.get(rid=str(rid))
                if ref is not None:
                    self.fsm.order_index.mark_terminal(
                        ref)  # type: ignore[attr-defined]
        except Exception:
            pass

        # PHASE A2 FIX: Inject cached intent data into ManageFlowFSM
        if rid in self._pending_intent_data:
            intent_data = self._pending_intent_data[rid]
            manage_flow = self.manage_flows.get(symbol)
            if manage_flow:
                LOG.info(
                    f"INJECTING_INTENT_DATA for {symbol} (rid={rid}): {intent_data}")
                sl_price = intent_data.get("stop_price")
                tp_price = intent_data.get("target_price")
                # BUG FIX: Check for real value, not just truthy ("None" string is truthy!)
                sl_is_real = sl_price is not None and str(
                    sl_price).strip().lower() != "none"
                tp_is_real = tp_price is not None and str(
                    tp_price).strip().lower() != "none"
                if sl_is_real:
                    manage_flow.set_intent_prices(
                        sl_price=sl_price, tp_price=tp_price if tp_is_real else None)
                    LOG.info(
                        f"INTENT_PRICES_INJECTED for {symbol}: SL={sl_price}, TP={tp_price if tp_is_real else 'None'}")
                else:
                    LOG.debug(
                        f"SKIP_INTENT_INJECTION for {symbol}: sl_price is None/invalid")

                # Cleanup cache after injection
                self._pending_intent_data.pop(rid, None)
            else:
                LOG.warning(
                    f"Could not inject intent data: ManageFlow not found for {symbol}")

        # Create post-fill hold in exposure guard
        if hasattr(self, "exposure_guard"):
            postfill_key = f"postfill_{symbol}_{order_id}"
            now_sec = get_clock().now_sec()
            self.exposure_guard.state.postfill_reservations[postfill_key] = {
                "symbol": symbol,
                "qty": filled_qty,
                "ts_ms": int(now_sec * 1000),
                "rid": rid,
                "exp_ts": now_sec + self.exposure_guard.post_fill_hold_ttl_sec,
            }
            LOG.debug(f"[FILL] Created postfill hold for {postfill_key}")

        # LIMIT-ENTRY-DEFERRED-BRACKETS: Check if this is a LIMIT entry fill with pending brackets
        if order_id in self._pending_brackets:
            bracket_data = self._pending_brackets.pop(order_id)

            # PHASE4: Mark as cleared in WAL
            try:
                write_pending_brackets_cleared(
                    entry_order_id=order_id,
                    reason="filled",
                    symbol=bracket_data.get("symbol", ""),
                )
            except Exception as e:
                LOG.warning(f"Failed to clear pending brackets from WAL: {e}")

            LOG.info(
                f"📌 [LIMIT-DEFERRED] Fill received for {symbol} entry {order_id}, "
                f"placing deferred TP/SL brackets"
            )
            # Schedule async bracket placement
            loop = self._get_async_loop()
            if loop:
                self._submit_async(
                    self._place_deferred_brackets(order_id, bracket_data),
                    loop
                )

        # Best-effort cleanup of orphaned brackets in case this fill closed the position
        # Debounce: wait for fill settlement before cleanup (config-based)
        loop = self._get_async_loop()
        if loop:
            lifecycle_cfg = self.config.domains.execution_position.order_lifecycle

            async def delayed_cleanup():
                # DET-BT-13: Use clock.sleep_ms for deterministic backtest
                await get_clock().sleep_ms(lifecycle_cfg.fill_settlement_delay_ms)
                await self.order_guardian.cleanup_orphans()
            self._submit_async(delayed_cleanup(), loop)

        # ✅ EVT:EXPOSURE_SUMMARY_UPDATED: Emit exposure summary after fill
        try:
            exposure_summary = self.exposure_guard.get_exposure_summary()
            exposure_msg = Message(
                op="EVT",
                verb="EXPOSURE_SUMMARY_UPDATED",
                src="execution_position",
                dst="decision_making",
                rid=rid or f"fill_{order_id}",
                pld={
                    "exposure_summary": exposure_summary,
                    "fill_order_id": order_id,
                    "fill_symbol": symbol,
                    "fill_quantity": filled_qty,
                    "timestamp_ms": get_clock().now_ms()
                },
                why="exposure_summary_updated_after_fill",
            )
            loop = self._get_async_loop()
            if loop:
                self._submit_async(
                    emit_compat(self.fsm, exposure_msg, logger=LOG), loop
                )
        except Exception as e:
            LOG.debug(
                f"Failed to emit exposure summary update after fill: {e}")

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
        except Exception as e:
            LOG.error(f"Failed to start OrderGuardian: {e}")

    def _initialize_adapter(self):
        """Initializes the BinanceAdapter based on the domain-level trading_mode."""
        # Check if config_loader has get_domain_mode method (new approach)
        mode = "testnet"  # Default fallback

        # Try to get domain-specific mode first
        if hasattr(self.config, "get_domain_mode"):
            try:
                mode = self.config.get_domain_mode("execution_position")
                LOG.info(f"✅ ExecPosFSM using domain-specific mode: {mode}")
            except Exception as e:
                LOG.warning(f"Could not get domain mode, using fallback: {e}")
                try:
                    if self.config.trading:
                        mode = self.config.trading.mode
                except AttributeError:
                    mode = "testnet"
        else:
            # Fallback to global mode
            try:
                if self.config.trading:
                    mode = self.config.trading.mode
            except AttributeError:
                mode = "testnet"
            LOG.info(f"ExecPosFSM using global trading_mode: {mode}")

        LOG.info(f"🎯 EXECUTION POSITION FSM MODE: {mode.upper()}")

        api_config = self.config.binance_api

        # Safe extraction of env config
        if mode == "live":
            env_config = api_config.live
            LOG.info("❌ ExecPosFSM adapter is configured for LIVE execution.")
        else:  # 'testnet' or 'hybrid_live_data_testnet_exec'
            env_config = api_config.testnet
            LOG.info(
                f"✅ ExecPosFSM adapter is configured for TESTNET execution (mode: {mode})."
            )

        # Extract API credentials (fail-closed: no default fallbacks on critical fields)
        try:
            api_key = env_config.api_key
            api_secret = env_config.api_secret
            rest_url = env_config.rest_url
        except Exception:  # pragma: no cover - defensive
            api_key = None
            api_secret = None
            rest_url = None

        if not all([api_key, api_secret, rest_url]):
            LOG.error(
                f"API configuration for execution in '{mode}' mode is incomplete. Execution will be simulated."
            )
            LOG.debug(f"  - API Key present: {bool(api_key)}")
            LOG.debug(f"  - API Secret present: {bool(api_secret)}")
            LOG.debug(f"  - REST URL: {rest_url}")
            self.shadow_mode = True  # Fallback to shadow mode if config is missing
            return

        self.adapter = BinanceAdapter(
            api_key=api_key,
            api_secret=api_secret,
            rest_url=rest_url,
        )
        # PHASE B1: Pass metrics reference to adapter for -4116 tracking
        self.adapter._orphan_metrics_ref = self._orphan_metrics
        LOG.info(
            f"✅ BinanceAdapter initialized for ExecPosFSM with base URL: {self.adapter.base_url}"
        )

        # 🔧 POLLING FIX: Connect adapter to THIS ExecPosFSM instance (not FSMCore event bus)
        # Adapter needs direct access to ExecPosFSM.handle() to deliver TRADE_EXECUTED events
        self.adapter.exec_fsm = self  # Direct reference to ExecPosFSM for handle() calls
        # Keep for backwards compatibility (event bus)
        self.adapter.fsm_core = self.fsm

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
                self.close_flows[symbol] = CloseFlowFSM()

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

            # EXP-FIX: Fail-closed exposure check before processing CMD:OPEN
            exposure_err = self._check_exposure_fail_closed(msg)
            if exposure_err is not None:
                # TASK49/TASK40: If DecisionMaking reserved ENTRY_INTENT in OrderIndex,
                # ensure we clear it when OPEN is blocked fail-closed (no order will be placed).
                try:
                    # type: ignore[attr-defined]
                    if hasattr(self.fsm, "order_index") and self.fsm.order_index:
                        self.fsm.order_index.cancel_reservation(
                            str(msg.rid))  # type: ignore[attr-defined]
                except Exception:
                    pass
                return exposure_err
            result = open_flow.handle(msg)

            # If guards rejected CMD:OPEN, clear ENTRY_INTENT reservation so DM doesn't get stuck
            # deferring with NRR-ORDER-IN-FLIGHT.
            if result is not None and getattr(result, "op", None) == "ERR":
                try:
                    # type: ignore[attr-defined]
                    if hasattr(self.fsm, "order_index") and self.fsm.order_index:
                        self.fsm.order_index.cancel_reservation(
                            str(msg.rid))  # type: ignore[attr-defined]
                except Exception:
                    pass

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
            # 🔧 POLLING FIX: Watchdog emits EVT:TRADE_EXECUTED on REST-detected fills.
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
            # ✅ FIX: Set closing flag immediately on CMD:CLOSE to prevent bracket race
            symbol = msg.pld.get("symbol") if msg.pld else None
            if symbol:
                manage = self.manage_flows.get(symbol)
                if manage:
                    manage._closing_position = True
                    manage._closing_position_ts = get_clock().now_sec()
                    print(
                        f"🔒 [CMD:CLOSE] Set closing flag for {symbol} to prevent bracket race")
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
                # ✅ FIX: Execute CLOSE decisions even in shadow mode to cancel brackets
                if (not self.shadow_mode and self.adapter) or (result.verb in ("CLOSE", "CLOSE_POSITION") and self.adapter):
                    # Asynchronously execute the trade decision
                    loop = self._get_async_loop()
                    LOG.info(
                        f"🔄 ExecPosFSM: DEC:{result.verb} ready to execute, loop={loop is not None}, shadow_mode={self.shadow_mode}, adapter={self.adapter is not None}")
                    if loop:
                        self._submit_async(
                            self._execute_decision(result), loop)
                    else:
                        LOG.error(
                            f"❌ ExecPosFSM: No async loop available for DEC:{result.verb}! Order will NOT be executed!")
                else:
                    LOG.info(
                        f"⏭️ ExecPosFSM: Skipping execution for DEC:{result.verb} (shadow_mode={self.shadow_mode}, adapter={self.adapter is not None})")

        return result

    async def _execute_decision(self, decision: Message):
        """Asynchronously execute a trading decision using the adapter."""
        if not self.adapter:
            return

        # --- CRITICAL SAFETY GUARDRAIL ---
        # Get domain-specific mode (execution_position should be testnet)
        domain_mode = "testnet"
        if hasattr(self.config, "get_domain_mode"):
            try:
                domain_mode = self.config.get_domain_mode("execution_position")
            except Exception:
                if hasattr(self.config, "trading_mode"):
                    domain_mode = self.config.trading_mode
        elif hasattr(self.config, "trading_mode"):
            domain_mode = self.config.trading_mode

        LOG.info(f"🎯 Executing with domain_mode={domain_mode}")

        if domain_mode == "testnet":
            if "testnet" not in self.adapter.base_url:
                LOG.critical(
                    "🚨 GUARDRAIL TRIGGERED: Domain mode is TESTNET, but adapter is configured for LIVE API! Order BLOCKED."
                )
                # Optionally emit a critical error event
                fatal_msg = Message(
                    op="ERR",
                    verb="FATAL_CONFIG_MISMATCH",
                    src="execution_position",
                    dst="monitoring",
                    rid="config_check",
                    pld={"reason": "Testnet mode with live execution URL"},
                    why="Testnet mode with live execution URL",
                )
                await emit_compat(self.fsm, fatal_msg, logger=LOG)
                return
            else:
                LOG.info(
                    "✅ Testnet mode confirmed: adapter URL contains 'testnet'")
        elif domain_mode == "live":
            LOG.warning(
                "⚠️ LIVE execution mode - ensure you know what you're doing!")

        # --- END GUARDRAIL ---

        try:
            # Handle adapter-level cancellations
            if decision.verb == "CANCEL_ORDER":
                pld = decision.pld or {}
                order_id = pld.get("orderId")
                symbol = pld.get("symbol")
                if order_id and symbol:
                    try:
                        cancel_result = await self._cancel_order(symbol, order_id)
                        if self._is_cancel_success_response(cancel_result):
                            LOG.info(
                                f"Cancelled order {order_id} for {symbol} (idempotent_ok)")
                        else:
                            LOG.warning(
                                f"Cancel response for {order_id} returned unexpected payload: {cancel_result}")
                    except Exception as e:
                        if self._is_unknown_order_error(e):
                            LOG.info(
                                f"Cancel request for {order_id} treated as success (-2011 Unknown order)")
                        else:
                            LOG.warning(
                                f"Failed to cancel order {order_id} for {symbol}: {e}")
                return

            # Execute close intent: cancel brackets then place reduce-only MARKET
            if decision.verb in ("CLOSE", "CLOSE_POSITION"):
                pld = decision.pld or {}
                symbol = pld.get("symbol")
                if not symbol:
                    LOG.error("DEC:CLOSE missing symbol; cannot execute")
                    return

                # PHASE A2: Set closing flag to prevent bracket placement race condition
                manage = self.manage_flows.get(symbol)
                if manage:
                    manage._closing_position = True
                    manage._closing_position_ts = get_clock().now_sec()
                    LOG.info(
                        f"🔒 [PHASE A2] Set closing flag for {symbol} to prevent bracket race")

                # Cancel tracked brackets
                br = self._symbol_brackets[symbol] if symbol in self._symbol_brackets else {
                }
                tasks = []
                bracket_order_ids = []  # Track IDs for logging
                if br.get("sl_order_id"):
                    tasks.append(self._cancel_order(symbol, br["sl_order_id"]))
                    bracket_order_ids.append(("SL", br["sl_order_id"]))
                if br.get("tp_order_id"):
                    tasks.append(self._cancel_order(symbol, br["tp_order_id"]))
                    bracket_order_ids.append(("TP", br["tp_order_id"]))

                if tasks:
                    # ✅ NEW: Collect and verify cancel results
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for (bracket_type, order_id), result in zip(bracket_order_ids, results):
                        if isinstance(result, Exception):
                            if self._is_unknown_order_error(result):
                                LOG.info(
                                    f"ℹ️ {bracket_type} bracket {order_id} already absent (-2011) for {symbol}")
                                order_logger.write({
                                    "rid": decision.rid or "manual-close",
                                    "event_type": "ORDER_CANCELLED",
                                    "symbol": symbol,
                                    "order_id": order_id,
                                    "bracket_type": bracket_type,
                                    "reason": "close_cancel_idempotent",
                                    "timestamp": get_clock().now_ms()
                                })
                            else:
                                LOG.warning(
                                    f"❌ Failed to cancel {bracket_type} bracket {order_id} for {symbol}: {result}")
                                order_logger.write({
                                    "rid": decision.rid or "manual-close",
                                    "event_type": "ORDER_CANCELLATION_FAILED",
                                    "symbol": symbol,
                                    "order_id": order_id,
                                    "bracket_type": bracket_type,
                                    "reason": "close_cancel_exception",
                                    "error": str(result),
                                    "timestamp": get_clock().now_ms()
                                })
                        else:
                            if self._is_cancel_success_response(result):
                                LOG.info(
                                    f"✅ Cancelled {bracket_type} bracket {order_id} for {symbol}")
                                order_logger.write({
                                    "rid": decision.rid or "manual-close",
                                    "event_type": "ORDER_CANCELLED",
                                    "symbol": symbol,
                                    "order_id": order_id,
                                    "bracket_type": bracket_type,
                                    "reason": "manual_close",
                                    "adapter_response": result,
                                    "timestamp": get_clock().now_ms()
                                })
                            else:
                                cancel_status = self._cancel_status_str(result)
                                LOG.warning(
                                    f"❌ Cancel rejected for {bracket_type} bracket {order_id}: status={cancel_status}")
                                order_logger.write({
                                    "rid": decision.rid or "manual-close",
                                    "event_type": "ORDER_CANCELLATION_FAILED",
                                    "symbol": symbol,
                                    "order_id": order_id,
                                    "bracket_type": bracket_type,
                                    "reason": f"close_cancel_rejected_status_{cancel_status}",
                                    "adapter_response": result,
                                    "timestamp": get_clock().now_ms()
                                })

                # Determine side/qty from current positions
                try:
                    positions = await self.adapter.get_open_positions()
                    # Convert positions to dict if they're objects
                    positions_list = [
                        p.to_dict() if hasattr(p, 'to_dict') else (
                            p.__dict__ if not isinstance(p, dict) else p)
                        for p in positions
                    ]
                    pos = next(
                        (p for p in positions_list if p.get("symbol") == symbol), None)
                except Exception:
                    pos = None
                amt = 0.0
                if pos is not None:
                    try:
                        amt = float(pos["positionAmt"]
                                    if "positionAmt" in pos else 0)
                    except Exception:
                        amt = 0.0
                if abs(amt) < 1e-10:
                    LOG.info(f"No open position to close for {symbol}")
                    self._symbol_brackets.pop(symbol, None)
                    return
                close_side = "SELL" if amt > 0 else "BUY"
                close_qty = str(abs(Decimal(str(amt))))
                close_id = generate_client_order_id(
                    "CLOSE",
                    symbol,
                    idempotent_key=str((decision.pld or {}).get(
                        "idempotent_key") or decision.rid or "manual-close"),
                )
                await self.adapter.place_market_reduce_only(symbol, close_side, close_qty, new_client_order_id=close_id)
                LOG.info(
                    f"Close executed for {symbol}: side={close_side} qty={close_qty}")
                self._symbol_brackets.pop(symbol, None)

                # ✅ PHASE A1: Ensure cleanup after manual CLOSE
                # Wait for position to settle, then cleanup any orphaned brackets (config-based)
                lifecycle_cfg = self.config.domains.execution_position.order_lifecycle
                # DET-BT-13: Use clock.sleep_ms for deterministic backtest
                await get_clock().sleep_ms(lifecycle_cfg.position_close_cleanup_delay_ms)

                # 🔄 Synchronous reconcile: fetch open orders ONLY for this symbol
                # and cancel any STOP/TP with reduceOnly=true or closePosition=true
                LOG.info(
                    f"🔄 [DEC:CLOSE RECONCILE] Starting sync cleanup for {symbol}")
                try:
                    open_orders = await self.adapter.get_open_orders(symbol)
                    # Convert orders to dict if they're objects
                    open_orders_list = [
                        o.to_dict() if hasattr(o, 'to_dict') else (
                            o.__dict__ if not isinstance(o, dict) else o)
                        for o in open_orders
                    ]

                    cancel_tasks = []
                    for o in open_orders_list:
                        otype = (o.get("type") or "").upper()
                        reduce_only = str(
                            o["reduceOnly"] if "reduceOnly" in o else "").lower() == "true"
                        close_pos = str(
                            o["closePosition"] if "closePosition" in o else "").lower() == "true"

                        # Cancel STOP/TP/LIMIT with reduceOnly or closePosition
                        if otype in ("STOP_MARKET", "TAKE_PROFIT_MARKET", "LIMIT") and (reduce_only or close_pos):
                            oid = o.get("orderId")
                            cancel_tasks.append(
                                (otype, oid, self._cancel_order(symbol, oid)))

                    # Execute all cancellations
                    if cancel_tasks:
                        results = await asyncio.gather(*[task[2] for task in cancel_tasks], return_exceptions=True)
                        for (otype, oid, _), result in zip(cancel_tasks, results):
                            if isinstance(result, Exception):
                                if self._is_unknown_order_error(result):
                                    LOG.info(
                                        f"ℹ️ [DEC:CLOSE RECONCILE] {otype} {oid} already gone for {symbol} (-2011)")
                                else:
                                    LOG.warning(
                                        f"❌ [DEC:CLOSE RECONCILE] Failed to cancel {otype} {oid} for {symbol}: {result}")
                                    self._orphan_metrics["errors"] += 1
                            else:
                                if self._is_cancel_success_response(result):
                                    LOG.info(
                                        f"✅ [DEC:CLOSE RECONCILE] Cancelled {otype} {oid} for {symbol}")
                                    self._orphan_metrics["reconcile_cancelled"] += 1
                                else:
                                    status = self._cancel_status_str(result)
                                    LOG.warning(
                                        f"❌ [DEC:CLOSE RECONCILE] Cancel response unexpected for {otype} {oid} (status={status})")
                                    self._orphan_metrics["errors"] += 1

                        LOG.info(
                            f"✅ [DEC:CLOSE RECONCILE] Completed for {symbol}: cancelled {len(cancel_tasks)} orders")

                        # PHASE C: Emit observability event for reconcile completion
                        self._emit_observability_event("RECONCILE_CANCELLED", {
                            "symbol": symbol,
                            "order_count": len(cancel_tasks),
                            "metric": self._orphan_metrics["reconcile_cancelled"]
                        })
                    else:
                        LOG.info(
                            f"✅ [DEC:CLOSE RECONCILE] No orphaned brackets found for {symbol}")

                except Exception as e:
                    LOG.warning(
                        f"⚠️ [DEC:CLOSE RECONCILE] Error during cleanup for {symbol}: {e}")
                    self._orphan_metrics["errors"] += 1

                # Also run full cleanup to catch any cross-symbol orphans
                await self.order_guardian.cleanup_orphans()
                LOG.info(
                    f"✅ Cleanup after manual CLOSE for {symbol} completed")

                # [GUARD] Reconcile orphaned brackets for closed position
                await self.order_guardian.reconcile_symbol(symbol, decision.rid)

                # PHASE A2: Clear closing flag - position close complete
                manage = self.manage_flows.get(symbol)
                if manage:
                    manage._closing_position = False
                    LOG.info(
                        f"🔓 [PHASE A2] Cleared closing flag for {symbol} - CLOSE complete")

                # PHASE C: Emit observability event for DEC:CLOSE completion
                # Message.ts is in milliseconds since epoch
                close_elapsed_ms = int(get_clock().now_sec(
                ) * 1000 - decision.ts) if decision.ts else 0
                self._emit_observability_event("DEC_CLOSE_COMPLETED", {
                    "symbol": symbol,
                    "elapsed_ms": close_elapsed_ms,
                    "orphans_cancelled": self._orphan_metrics["reconcile_cancelled"]
                })

                return

            # ✅ NEW: Handle generic PLACE_ORDER (e.g. from ManageFlowFSM for brackets)
            if decision.verb == "PLACE_ORDER":
                pld = decision.pld or {}
                symbol = pld.get("symbol")
                side = pld.get("side")
                qty = pld.get("qty")
                order_type = pld["order_type"] if "order_type" in pld else "LIMIT"
                price = pld.get("price")
                stop_price = pld.get("stopPrice")
                client_id = pld.get("newClientOrderId")
                reduce_only = pld["reduceOnly"] if "reduceOnly" in pld else False

                LOG.info(
                    f"Executing PLACE_ORDER: {symbol} {side} {order_type} {qty} @ {price}/{stop_price}")

                try:
                    resp = None
                    if order_type == "STOP_MARKET" and hasattr(self.adapter, "place_stop_market_close_position"):
                        resp = await self.adapter.place_stop_market_close_position(
                            symbol, side, str(stop_price), new_client_order_id=client_id
                        )
                    elif order_type == "TAKE_PROFIT_MARKET" and hasattr(self.adapter, "place_take_profit_market_close_position"):
                        resp = await self.adapter.place_take_profit_market_close_position(
                            symbol, side, str(stop_price), new_client_order_id=client_id
                        )
                    elif order_type == "LIMIT" and reduce_only and hasattr(self.adapter, "place_limit_reduce_only"):
                        resp = await self.adapter.place_limit_reduce_only(
                            symbol, side, str(price), qty, new_client_order_id=client_id
                        )
                    else:
                        # Fallback to generic place_order if available, or log error
                        if hasattr(self.adapter, "place_order"):
                            # Construct message for adapter (legacy interface)
                            resp = await self.adapter.place_order(decision)
                        else:
                            LOG.error(
                                f"Unsupported order type for PLACE_ORDER: {order_type}")
                            return

                    LOG.info(f"✅ PLACE_ORDER success: {resp}")

                    # ORDER_INDEX: correlate bracket/aux orders for WS updates
                    try:
                        if (
                            client_id
                            and resp
                            and hasattr(self.fsm, "order_index")
                            # type: ignore[attr-defined]
                            and self.fsm.order_index
                        ):
                            ex_order_id = str(resp.get("orderId"))

                            rid_for_index = str(
                                getattr(decision, "rid", "") or "") or ex_order_id
                            idem_key = (
                                (decision.pld or {}).get("idempotent_key")
                                or getattr(decision, "idempotent_key", None)
                                or rid_for_index
                                or client_id
                            )
                            self.fsm.order_index.upsert_from_open(  # type: ignore[attr-defined]
                                rid=rid_for_index,
                                idempotent_key=str(idem_key),
                                clientOrderId=client_id,
                                symbol=symbol,
                                side=str(side).upper() if side else "",
                                order_type=str(order_type),
                            )
                            self.fsm.order_index.attach_exchange_id(  # type: ignore[attr-defined]
                                clientOrderId=client_id,
                                exchangeOrderId=ex_order_id,
                            )
                    except Exception:
                        pass

                    # Register brackets if applicable
                    if client_id and resp:
                        order_id = str(resp.get("orderId"))
                        if "_sl" in client_id:
                            self._symbol_brackets.setdefault(
                                symbol, {})["sl_order_id"] = order_id
                        elif "_tp" in client_id:
                            self._symbol_brackets.setdefault(
                                symbol, {})["tp_order_id"] = order_id

                        # 🔥 CRITICAL: Sync with ManageFlowFSM
                        manage_flow = self.manage_flows.get(symbol)
                        if manage_flow:
                            brackets = self._symbol_brackets[symbol] if symbol in self._symbol_brackets else {
                            }
                            current_sl = brackets.get("sl_order_id")
                            current_tp = brackets.get("tp_order_id")
                            manage_flow.set_bracket_ids(current_sl, current_tp)

                except Exception as e:
                    LOG.error(f"❌ PLACE_ORDER failed: {e}")
                    # Emit error event?

                return

            symbol = decision.pld["symbol"]
            side = decision.pld["side"].upper()
            raw_qty = decision.pld["qty"]

            # EP-01.3-SUPERSEDE-ACK: Check if already waiting for cancel confirmation
            if symbol in self._supersede_canceling:
                LOG.info(
                    f"EP-01.3: {symbol} already canceling pending entry, queueing new DEC:OPEN (supersede)"
                )
                # Update queued decision (newer takes priority)
                self._supersede_queue[symbol] = {
                    "decision": decision,
                    "queued_at": get_clock().now_sec(),
                }
                return  # Early return - will be processed when cancel confirmed

            # EP-01.3-SUPERSEDE-ACK: Check if pending entries exist
            has_pending = False
            pending_order_ids = []
            if self.watchdog:
                for order_id, deadline in list(self.watchdog.pending_orders.items()):
                    if deadline.symbol == symbol:
                        has_pending = True
                        pending_order_ids.append(order_id)
                for order_id, deadline in list(self.watchdog.acked_orders.items()):
                    if deadline.symbol == symbol:
                        has_pending = True
                        pending_order_ids.append(order_id)

            # EP-01.3-SUPERSEDE-ACK: If pending exists, cancel and queue
            if has_pending:
                try:
                    pe_ttl_cfg = self.config.domains.execution_position.pending_entry_ttl
                    if pe_ttl_cfg.enabled and pe_ttl_cfg.cancel_on_supersede:
                        LOG.info(
                            f"EP-01.3: {symbol} has {len(pending_order_ids)} pending entries, "
                            f"queueing new DEC:OPEN until cancel confirmed"
                        )
                        # Mark symbol as canceling
                        self._supersede_canceling.add(symbol)
                        # Store queued decision
                        self._supersede_queue[symbol] = {
                            "decision": decision,
                            "cancel_order_ids": pending_order_ids,
                            "queued_at": get_clock().now_sec(),
                        }
                        # Initiate cancel
                        self._cancel_pending_entries_for_symbol(
                            symbol=symbol,
                            reason="CANCEL_SUPERSEDED",
                            context=f"new_open_side={side}"
                        )
                        # Schedule timeout check (if cancel never confirmed, proceed anyway after timeout)
                        loop = self._get_async_loop()
                        if loop:
                            async def _supersede_timeout():
                                # DET-BT-13: Use clock.sleep_sec for deterministic backtest
                                # STRICT SSOT: Timeout from config (fail-closed)
                                timeout_sec = float(
                                    pe_ttl_cfg.supersede_cancel_timeout_sec)
                                await get_clock().sleep_sec(timeout_sec)
                                if symbol in self._supersede_canceling:
                                    LOG.warning(
                                        f"EP-01.3: {symbol} supersede cancel timeout, proceeding with queued open"
                                    )
                                    self._process_queued_supersede(symbol)
                            self._submit_async(_supersede_timeout(), loop)
                        return  # Early return - wait for cancel confirmation
                except AttributeError:
                    pass  # Config not loaded, proceed with normal flow

            # Get mark price and filters
            mark = await self.adapter.get_mark_price(symbol)

            # TASK50: Get instrument filters from config (SSOT)
            # and normalize qty with fail-closed semantics
            instrument_spec = None
            if hasattr(self.config, "instruments") and self.config.instruments:
                instrument_spec = self.config.instruments.get(symbol)

            # FAIL-CLOSED: TP/SL + qty normalization MUST use YAML SSOT (config/aurora/instruments.yaml).
            # No fallback to exchangeInfo is allowed here.
            if not instrument_spec:
                err = f"instruments.{symbol} is missing (required SSOT for tick_size/step_size/min_qty/min_notional)"
                LOG.error(f"❌ [{symbol}] INSTRUMENT_CONFIG_MISSING: {err}")
                order_logger.write(
                    {
                        "rid": decision.rid,
                        "event_type": "ORDER_REJECTED",
                        "symbol": symbol,
                        "side": side,
                        "quantity": str(raw_qty),
                        "nrr_code": "NRR-INSTRUMENT-CONFIG-MISSING",
                        "why": err,
                    }
                )
                reject_msg = Message(
                    op="EVT",
                    verb="ORDER_REJECTED",
                    src="execution_position",
                    dst="decision_making",
                    rid=decision.rid,
                    pld={
                        "symbol": symbol,
                        "side": side,
                        "raw_qty": str(raw_qty),
                        "reason": "NRR-INSTRUMENT-CONFIG-MISSING",
                        "details": err,
                    },
                    why="NRR-INSTRUMENT-CONFIG-MISSING",
                )
                await emit_compat(self.fsm, reject_msg, logger=LOG)
                return

            tick_size = float(instrument_spec.tick_size)
            step_size = instrument_spec.step_size
            min_qty = instrument_spec.min_qty
            min_notional = instrument_spec.min_notional

            # TASK50: Normalize qty - fail-closed, no silent bump-ups
            norm_result = normalize_qty(
                raw_qty=raw_qty,
                price=mark,
                step_size=step_size,
                min_qty=min_qty,
                min_notional=min_notional,
            )

            if not norm_result.ok:
                LOG.warning(
                    f"❌ [{symbol}] QTY_NORMALIZE_REJECTED: {norm_result.why} "
                    f"(raw_qty={norm_result.raw_qty}, rounded={norm_result.rounded_qty}, "
                    f"min_qty={norm_result.min_qty}, min_notional={norm_result.min_notional})"
                )
                # Log to order_log for forensics
                order_logger.write(
                    {
                        "rid": decision.rid,
                        "event_type": "QTY_NORMALIZE_REJECTED",
                        "symbol": symbol,
                        "side": side,
                        "quantity": str(raw_qty),
                        "nrr_code": norm_result.why,
                        "adapter_response": norm_result.to_dict(),
                        "why": norm_result.why,
                    }
                )
                # Emit rejection event
                reject_msg = Message(
                    op="EVT",
                    verb="ORDER_REJECTED",
                    src="execution_position",
                    dst="decision_making",
                    rid=decision.rid,
                    pld={
                        "symbol": symbol,
                        "side": side,
                        "raw_qty": str(raw_qty),
                        "reason": norm_result.why,
                        "norm_result": norm_result.to_dict(),
                    },
                    why=norm_result.why,
                )
                await emit_compat(self.fsm, reject_msg, logger=LOG)
                return

            # Use normalized qty
            qty = str(norm_result.qty)
            LOG.info(
                f"✅ [{symbol}] QTY_NORMALIZED: raw={raw_qty} → normalized={qty} "
                f"(step={step_size}, min_qty={min_qty})"
            )

            # === STRATEGY PRIMACY FOR SL/TP (FIX: Silent Fallback Elimination) ===
            # STEP 1: Check for explicit Strategy-provided prices in DEC:OPEN payload
            explicit_sl_raw = decision.pld.get(
                "stop_price") if decision.pld else None
            explicit_tp_raw = decision.pld.get(
                "target_price") if decision.pld else None

            # Normalize to Decimal (handle string/Decimal/float/None)
            explicit_sl: Optional[Decimal] = None
            explicit_tp: Optional[Decimal] = None

            if explicit_sl_raw not in (None, "", "None", "null"):
                try:
                    explicit_sl = Decimal(str(explicit_sl_raw))
                    LOG.info(
                        f"✅ [{symbol}] STRATEGY_PRIMACY: Using Strategy-provided SL={explicit_sl}")
                except Exception as e:
                    LOG.warning(
                        f"[{symbol}] Invalid explicit stop_price '{explicit_sl_raw}': {e}")

            if explicit_tp_raw not in (None, "", "None", "null"):
                try:
                    explicit_tp = Decimal(str(explicit_tp_raw))
                    LOG.info(
                        f"✅ [{symbol}] STRATEGY_PRIMACY: Using Strategy-provided TP={explicit_tp}")
                except Exception as e:
                    LOG.warning(
                        f"[{symbol}] Invalid explicit target_price '{explicit_tp_raw}': {e}")

            # STEP 2: Config-based fallback (ONLY if Strategy did not provide prices)
            # TP/SL extraction (FAIL-CLOSED: per-symbol sl_pct from aurora.yaml)
            # SSOT: strategies.aurora.assets.<SYMBOL>.exit.sl_pct (fallback only)
            sl_pct: Optional[float] = None
            tp_low_ratio: Optional[float] = None
            tp_high_ratio: Optional[float] = None
            config_loaded = False

            # Only load config if we need fallback values
            if explicit_sl is None or explicit_tp is None:
                try:
                    aurora = getattr(self.config.strategies, "aurora", None)
                    if aurora is None:
                        raise ValueError("strategies.aurora not configured")

                    instr_cfg = aurora.assets.get(symbol)
                    if instr_cfg is None:
                        raise ValueError(
                            f"strategies.aurora.assets.{symbol} not configured")

                    # Extract exit config (FAIL-CLOSED: must exist if fallback needed)
                    exit_cfg = getattr(instr_cfg, "exit", None)
                    if exit_cfg is None or exit_cfg.sl_pct is None:
                        raise ValueError(
                            f"strategies.aurora.assets.{symbol}.exit.sl_pct is required"
                        )
                    sl_pct = exit_cfg.sl_pct

                    # Extract take_profit config (FAIL-CLOSED: must exist if fallback needed)
                    tp_cfg = getattr(instr_cfg, "take_profit", None)
                    if tp_cfg is None or tp_cfg.tp_low_ratio is None:
                        raise ValueError(
                            f"strategies.aurora.assets.{symbol}.take_profit.tp_low_ratio is required"
                        )
                    tp_low_ratio = tp_cfg.tp_low_ratio
                    tp_high_ratio = getattr(tp_cfg, "tp_high_ratio", None)
                    config_loaded = True

                    LOG.debug(
                        f"[{symbol}] CONFIG_FALLBACK_LOADED: sl_pct={sl_pct}, "
                        f"tp_low_ratio={tp_low_ratio}, tp_high_ratio={tp_high_ratio} "
                        f"(source=strategies.aurora.assets.{symbol})"
                    )
                except (ValueError, AttributeError) as cfg_err:
                    # FAIL-CLOSED: If Strategy didn't provide prices AND config missing → reject
                    if explicit_sl is None or explicit_tp is None:
                        LOG.error(
                            f"❌ [{symbol}] FAIL-CLOSED: Strategy did not provide SL/TP and config fallback missing: {cfg_err}"
                        )
                        order_logger.write({
                            "rid": decision.rid,
                            "event_type": "ORDER_REJECTED",
                            "symbol": symbol,
                            "side": side,
                            "quantity": str(raw_qty),
                            "nrr_code": "NRR-BRACKETS-CONFIG-MISSING",
                            "why": str(cfg_err),
                            "explicit_sl_provided": explicit_sl is not None,
                            "explicit_tp_provided": explicit_tp is not None,
                        })
                        reject_msg = Message(
                            op="EVT",
                            verb="ORDER_REJECTED",
                            src="execution_position",
                            dst="decision_making",
                            rid=decision.rid,
                            pld={
                                "symbol": symbol,
                                "side": side,
                                "raw_qty": str(raw_qty),
                                "reason": "NRR-BRACKETS-CONFIG-MISSING",
                                "details": str(cfg_err),
                            },
                            why="NRR-BRACKETS-CONFIG-MISSING",
                        )
                        await emit_compat(self.fsm, reject_msg, logger=LOG)
                        return

            # STEP 3: Calculate final SL/TP with Strategy Primacy
            mark_dec = Decimal(str(mark))

            # SL: Strategy value takes priority, else calculate from config
            if explicit_sl is not None:
                sl = explicit_sl
                sl_source = "STRATEGY"
            elif config_loaded and sl_pct is not None:
                sl_pct_dec = Decimal(str(sl_pct))
                if side == "BUY":
                    sl = mark_dec * (Decimal("1") - sl_pct_dec)
                else:
                    sl = mark_dec * (Decimal("1") + sl_pct_dec)
                sl_source = "CONFIG_FALLBACK"
                LOG.warning(
                    f"⚠️ [{symbol}] Using CONFIG FALLBACK for SL (Strategy did not provide): sl_pct={sl_pct}")
            else:
                # This shouldn't happen due to fail-closed above, but safety net
                LOG.error(f"❌ [{symbol}] FAIL-CLOSED: No SL source available")
                return

            # TP: Strategy value takes priority, else calculate from config
            if explicit_tp is not None:
                tp = explicit_tp
                tp_source = "STRATEGY"
            elif config_loaded and sl_pct is not None and tp_low_ratio is not None:
                sl_pct_dec = Decimal(str(sl_pct))
                tp_low_ratio_dec = Decimal(str(tp_low_ratio))
                if side == "BUY":
                    tp = mark_dec * \
                        (Decimal("1") + sl_pct_dec * tp_low_ratio_dec)
                else:
                    tp = mark_dec * \
                        (Decimal("1") - sl_pct_dec * tp_low_ratio_dec)
                tp_source = "CONFIG_FALLBACK"
                LOG.warning(
                    f"⚠️ [{symbol}] Using CONFIG FALLBACK for TP (Strategy did not provide): tp_low_ratio={tp_low_ratio}")
            else:
                LOG.error(f"❌ [{symbol}] FAIL-CLOSED: No TP source available")
                return

            LOG.info(
                f"[{symbol}] TP/SL_RESOLVED: mark={mark}, SL={sl} (source={sl_source}), "
                f"TP={tp} (source={tp_source})"
            )

            # Quantize (convert Decimal to float for utility function)
            tp = quantize_stop_price(
                float(tp), tick_size, side="BUY" if side == "BUY" else "SELL"
            )
            sl = quantize_stop_price(
                float(sl), tick_size, side="SELL" if side == "BUY" else "BUY"
            )

            # Validate
            validate_not_immediate(
                "LONG" if side == "BUY" else "SHORT", tp, sl, mark)

            # GATE: Check SYMBOL_TIDY before placing MARKET entry (if enabled)
            if decision.verb == "OPEN":
                sym_for_gate = decision.pld.get(
                    "symbol") if decision.pld else None
                if sym_for_gate and not self._entry_tidy_gate_allow(sym_for_gate):
                    return

            # EP-01.4-INT-B: Entry placement (MARKET or LIMIT based on order_type)
            # Fail-closed: no silent defaults for order_type/tif/price.
            order_type = decision.pld.get("order_type")
            tif = decision.pld.get("tif")
            price = decision.pld.get("price")  # For LIMIT orders

            if not order_type:
                order_logger.write({
                    "rid": decision.rid,
                    "event_type": "ORDER_REJECTED",
                    "symbol": symbol,
                    "side": side,
                    "quantity": float(qty),
                    "nrr_code": "NRR-047",
                    "why": "ORDER-POLICY-01: missing order_type (fail-closed)"[:80],
                    "source_fsm": "ExecPosFSM",
                })
                reject_msg = Message(
                    op="EVT",
                    verb="ORDER_REJECTED",
                    src="execution_position",
                    dst="decision_making",
                    rid=decision.rid,
                    pld={
                        "symbol": symbol,
                        "side": side,
                        "reason": "NRR-047",
                        "details": "missing order_type",
                    },
                    why="NRR-047",
                )
                await emit_compat(self.fsm, reject_msg, logger=LOG)
                return

            order_type = str(order_type).upper()
            if order_type == "MARKET":
                # Contract: MARKET must not carry tif (fail-closed).
                if tif is not None:
                    order_logger.write({
                        "rid": decision.rid,
                        "event_type": "ORDER_REJECTED",
                        "symbol": symbol,
                        "side": side,
                        "quantity": float(qty),
                        "nrr_code": "NRR-049",
                        "why": "ORDER-POLICY-01: MARKET must have tif=null"[:80],
                        "source_fsm": "ExecPosFSM",
                        "metadata": {"tif": str(tif)},
                    })
                    reject_msg = Message(
                        op="EVT",
                        verb="ORDER_REJECTED",
                        src="execution_position",
                        dst="decision_making",
                        rid=decision.rid,
                        pld={
                            "symbol": symbol,
                            "side": side,
                            "reason": "NRR-049",
                            "details": "MARKET must have tif=null",
                        },
                        why="NRR-049",
                    )
                    await emit_compat(self.fsm, reject_msg, logger=LOG)
                    return
            elif order_type == "LIMIT":
                if not price:
                    order_logger.write({
                        "rid": decision.rid,
                        "event_type": "ORDER_REJECTED",
                        "symbol": symbol,
                        "side": side,
                        "quantity": float(qty),
                        "nrr_code": "NRR-050",
                        "why": "ORDER-POLICY-01: LIMIT requires price"[:80],
                        "source_fsm": "ExecPosFSM",
                    })
                    reject_msg = Message(
                        op="EVT",
                        verb="ORDER_REJECTED",
                        src="execution_position",
                        dst="decision_making",
                        rid=decision.rid,
                        pld={
                            "symbol": symbol,
                            "side": side,
                            "reason": "NRR-050",
                            "details": "LIMIT requires price",
                        },
                        why="NRR-050",
                    )
                    await emit_compat(self.fsm, reject_msg, logger=LOG)
                    return
                if tif is None:
                    order_logger.write({
                        "rid": decision.rid,
                        "event_type": "ORDER_REJECTED",
                        "symbol": symbol,
                        "side": side,
                        "quantity": float(qty),
                        "nrr_code": "NRR-052",
                        "why": "ORDER-POLICY-01: LIMIT requires tif (no default)"[:80],
                        "source_fsm": "ExecPosFSM",
                    })
                    reject_msg = Message(
                        op="EVT",
                        verb="ORDER_REJECTED",
                        src="execution_position",
                        dst="decision_making",
                        rid=decision.rid,
                        pld={
                            "symbol": symbol,
                            "side": side,
                            "reason": "NRR-052",
                            "details": "LIMIT requires tif",
                        },
                        why="NRR-052",
                    )
                    await emit_compat(self.fsm, reject_msg, logger=LOG)
                    return
                tif = str(tif).upper()
                # EP-01.3-INT: LIMIT requires explicit per-order TTL (fail-closed).
                if decision.pld.get("valid_for_ms") is None:
                    order_logger.write({
                        "rid": decision.rid,
                        "event_type": "ORDER_REJECTED",
                        "symbol": symbol,
                        "side": side,
                        "quantity": float(qty),
                        "nrr_code": "NRR-025",
                        "why": "EP-01.3-INT: LIMIT requires valid_for_ms"[:80],
                        "source_fsm": "ExecPosFSM",
                    })
                    reject_msg = Message(
                        op="EVT",
                        verb="ORDER_REJECTED",
                        src="execution_position",
                        dst="decision_making",
                        rid=decision.rid,
                        pld={
                            "symbol": symbol,
                            "side": side,
                            "reason": "NRR-025",
                            "details": "LIMIT requires valid_for_ms",
                        },
                        why="NRR-025",
                    )
                    await emit_compat(self.fsm, reject_msg, logger=LOG)
                    return
            else:
                order_logger.write({
                    "rid": decision.rid,
                    "event_type": "ORDER_REJECTED",
                    "symbol": symbol,
                    "side": side,
                    "quantity": float(qty),
                    "nrr_code": "NRR-048",
                    "why": f"ORDER-POLICY-01: unsupported order_type={order_type}"[:80],
                    "source_fsm": "ExecPosFSM",
                })
                reject_msg = Message(
                    op="EVT",
                    verb="ORDER_REJECTED",
                    src="execution_position",
                    dst="decision_making",
                    rid=decision.rid,
                    pld={
                        "symbol": symbol,
                        "side": side,
                        "reason": "NRR-048",
                        "details": f"unsupported order_type={order_type}",
                    },
                    why="NRR-048",
                )
                await emit_compat(self.fsm, reject_msg, logger=LOG)
                return

            idem_key = (
                (decision.pld or {}).get("idempotent_key")
                or getattr(decision, "idempotent_key", None)
                or decision.rid
            )
            entry_id = generate_client_order_id(
                "ENTRY",
                symbol,
                idempotent_key=str(idem_key) if idem_key else None,
            )
            entry_resp = None

            if order_type == "LIMIT" and price:
                # EP-01.4-INT-B: LIMIT entry with configurable tif (supports GTX)
                LOG.info(
                    f"Placing LIMIT entry: {symbol} {side} {qty} @ {price}, tif={tif}")
                try:
                    entry_resp = await self.adapter.place_limit_entry(
                        symbol, side, price, qty, time_in_force=tif, new_client_order_id=entry_id
                    )
                    LOG.info(f"✅ LIMIT entry placed: {entry_resp}")
                except Exception as e:
                    # EP-01.4-INT-B: Check for post-only (GTX) rejection
                    from .reasons import MAKER_ONLY_REJECT, is_maker_only_reject_error
                    err_code = getattr(e, 'code', None)
                    err_msg = str(e)

                    if err_code and is_maker_only_reject_error(err_code):
                        LOG.warning(
                            f"MAKER_ONLY_REJECT: GTX order rejected (code={err_code}), "
                            f"symbol={symbol}, side={side}, NO FALLBACK"
                        )
                        order_logger.write({
                            "rid": decision.rid,
                            "event_type": "ORDER_REJECTED",
                            "symbol": symbol,
                            "side": side,
                            "quantity": float(qty),
                            "price": float(price) if price is not None else 0.0,
                            "nrr_code": "NRR-018",
                            "why": MAKER_ONLY_REJECT,
                            "source_fsm": "ExecPosFSM",
                            "metadata": {
                                "reason_code": MAKER_ONLY_REJECT,
                                "tif": tif,
                                "error_code": err_code,
                                "error_msg": err_msg[:200],
                                "fallback": "NONE",
                            },
                        })
                        # Emit rejection event
                        reject_msg = Message(
                            op="EVT",
                            verb="ORDER_REJECTED",
                            src="execution_position",
                            dst="decision_making",
                            rid=decision.rid,
                            pld={
                                "symbol": symbol,
                                "side": side,
                                "reason": MAKER_ONLY_REJECT,
                                "error_code": err_code,
                            },
                            why=MAKER_ONLY_REJECT,
                        )
                        # B2: WAL persistence for LIMIT ORDER_REJECTED
                        try:
                            wal.append(reject_msg.model_dump())
                        except Exception as wal_e:
                            LOG.warning(
                                f"Failed to write EVT:ORDER_REJECTED (LIMIT) to WAL: {wal_e}")
                        await emit_compat(self.fsm, reject_msg, logger=LOG)
                        return  # NO FALLBACK - abort entry
                    else:
                        # Other error - re-raise
                        LOG.error(f"LIMIT entry failed: {e}")
                        raise
            else:
                # Place MARKET entry (default behavior)
                entry_resp = await self.adapter.place_market_entry(
                    symbol, side, qty, entry_id
                )
                LOG.info(f"✅ MARKET entry placed: {entry_resp}")

            # ORDER_INDEX: correlate entry order for WS updates
            try:
                # type: ignore[attr-defined]
                if hasattr(self.fsm, "order_index") and self.fsm.order_index:
                    idem_key = (
                        (decision.pld or {}).get("idempotent_key")
                        or getattr(decision, "idempotent_key", None)
                        or decision.rid
                        or entry_id
                    )
                    entry_order_id = str(entry_resp.get("orderId"))
                    self.fsm.order_index.upsert_from_open(  # type: ignore[attr-defined]
                        rid=decision.rid or entry_order_id,
                        idempotent_key=str(idem_key),
                        clientOrderId=entry_id,
                        symbol=symbol,
                        side=str(side).upper(),
                        order_type="MARKET",
                    )
                    self.fsm.order_index.attach_exchange_id(  # type: ignore[attr-defined]
                        clientOrderId=entry_id,
                        exchangeOrderId=entry_order_id,
                    )
            except Exception:
                pass

            # [GUARD] Register entry order for ownership tracking
            self.order_guardian.register_entry(
                symbol=symbol,
                order_id=str(entry_resp["orderId"]),
                client_order_id=entry_id,
                side=side,
                qty=qty,
                corr_id=decision.corr_id,
                rid=decision.rid
            )

            # POLLING FIX: Track entry order for fill detection (WebSocket substitute)
            if hasattr(self.adapter, 'track_order'):
                self.adapter.track_order(entry_resp)
                LOG.info(
                    f"[POLLING] Tracking entry order {entry_resp.get('orderId')} for fill detection")

            # Track order for timeout monitoring
            self.watchdog.ensure_started()  # Safe late-start if needed
            entry_order_id = str(entry_resp["orderId"])
            # EP-01.3-INT: Extract valid_for_ms from decision payload for per-order TTL
            valid_for_ms = None
            if decision.pld and "valid_for_ms" in decision.pld:
                try:
                    valid_for_ms = int(
                        decision.pld["valid_for_ms"]) if decision.pld["valid_for_ms"] is not None else None
                except (ValueError, TypeError):
                    valid_for_ms = None
            self.watchdog.track_order_placed(
                order_id=entry_order_id,
                client_order_id=entry_id,
                symbol=symbol,
                corr_id=decision.corr_id,
                rid=decision.rid,
                fill_ttl_override_ms=valid_for_ms,  # EP-01.3-INT
            )

            # Log to OrderLoggerV1
            # TASK50: Added qty normalization context for forensics
            order_logger.write({
                "rid": decision.rid,
                "event_type": "ORDER_PLACED",
                "symbol": symbol,
                "side": side,
                "quantity": float(qty),
                "qty_raw": float(raw_qty) if raw_qty else None,
                "qty_normalized": float(qty),
                "step_size": str(step_size),
                "min_qty": str(min_qty),
                "min_notional": str(min_notional) if min_notional else None,
                "qty_notional_usd": float(norm_result.notional) if norm_result.notional else None,
                "client_order_id": entry_id,
                "order_id": str(entry_resp["orderId"]),
                "source_fsm": "ExecPosFSM",
                "reservation_id": decision.corr_id,
                "adapter_response": entry_resp,
                "metadata": {"order_type": "MARKET_ENTRY", "corr_id": decision.corr_id}
            })

            # B1: WAL persistence for ORDER_PLACED (INTENT-TO-ORDER-TRACE-SSOT-01)
            # Ensures WAL contains full intent→order chain for replay and forensics
            try:
                order_placed_msg = Message(
                    op="EVT",
                    verb="ORDER_PLACED",
                    src="execution_position",
                    dst="observability",
                    rid=decision.rid,
                    pld={
                        "symbol": symbol,
                        "side": side,
                        "qty": str(qty),
                        "order_type": order_type,
                        "client_order_id": entry_id,
                        "exchange_order_id": str(entry_resp.get("orderId")),
                        "ts_ms": get_clock().now_ms(),
                        "corr_id": decision.corr_id,
                    },
                    why="order_placed",
                )
                wal.append(order_placed_msg.model_dump())
            except Exception as wal_e:
                LOG.warning(
                    f"Failed to write EVT:ORDER_PLACED to WAL: {wal_e}")

            # Correlation: store entry ACK
            entry_order_id = str(entry_resp["orderId"])
            decision.link_ack_id = entry_order_id
            self.correlation_store.put_entry_ack(entry_order_id, {
                'corr_id': decision.corr_id,
                'oco_group_id': decision.oco_group_id,
                'rid': decision.rid,
                'parent_client_order_id': None
            })
            self.log_adapter.log_trade_execution(
                rid=decision.rid,
                symbol=symbol,
                side=side,
                order_id=entry_order_id,
                status="ACK",
                corr_id=decision.corr_id
            )

            # Notify watchdog of order ACK
            self.watchdog.ensure_started()  # Safe late-start if needed
            self.watchdog.on_order_ack(entry_order_id)

            # LIMIT-ENTRY-DEFERRED-BRACKETS: For LIMIT entries, defer TP/SL until fill
            # MARKET orders fill immediately, LIMIT orders need to wait for fill event
            if order_type == "LIMIT":
                # Store pending bracket data for placement on fill
                self._pending_brackets[entry_order_id] = {
                    "symbol": symbol,
                    "side": side,
                    "sl": sl,
                    "tp": tp,
                    "qty": qty,
                    "rid": decision.rid,
                    "idem_key": idem_key,
                    "tick_size": tick_size,
                    "corr_id": decision.corr_id,
                    "oco_group_id": decision.oco_group_id,
                    "entry_client_order_id": entry_id,
                    "created_at": get_clock().now_sec(),
                }

                # PHASE4: Persist to WAL for restart safety
                try:
                    write_pending_brackets_stored(
                        entry_order_id=entry_order_id,
                        symbol=symbol,
                        side=side,
                        sl=sl,
                        tp=tp,
                        qty=qty,
                        rid=decision.rid,
                        idem_key=idem_key,
                        tick_size=tick_size,
                        corr_id=decision.corr_id,
                        oco_group_id=decision.oco_group_id,
                        entry_client_order_id=entry_id,
                    )
                except Exception as e:
                    LOG.warning(
                        f"Failed to persist pending brackets to WAL: {e}")

                LOG.info(
                    f"📌 [LIMIT-DEFERRED] Stored pending brackets for {symbol} entry {entry_order_id}, "
                    f"SL={sl}, TP={tp} - will place on fill"
                )
                return None  # TP/SL will be placed when fill arrives

            # ✅ PHASE A3: Pre-flight check before placing TP/SL (with retry for REST lag)
            # Only for MARKET entries - LIMIT entries are handled on fill
            if not await self._preflight_position_check(symbol):
                LOG.warning(
                    f"🚫 [PHASE A3] Skipping TP/SL placement - position check failed for {symbol}")
                return None

            # ✅ Check with OrderGuardian if brackets should be placed
            entry_order_id = str(entry_resp["orderId"])
            if not await self.order_guardian.should_place_brackets(symbol, entry_order_id):
                LOG.warning(
                    f"🚫 OrderGuardian blocked bracket placement for {symbol}")
                return None

            # Generate bracket IDs
            sl_side = opposite_side(side)
            sl_id = generate_client_order_id(
                "SL",
                symbol,
                idempotent_key=str(idem_key) if idem_key else None,
            )
            tp_side = opposite_side(side)
            tp_id = generate_client_order_id(
                "TP",
                symbol,
                idempotent_key=str(idem_key) if idem_key else None,
            )

            # ✅ Place SL and TP in parallel (not sequentially)
            sl_resp = None
            tp_resp = None

            # MAGIC-NUM-EXTRACTION: Read bracket placement config from SSOT
            bracket_cfg = self.config.domains.execution_position.bracket_placement
            tp_widen_first = Decimal(
                "1") + Decimal(str(bracket_cfg.tp_widen_first_bps)) / Decimal("10000")
            tp_widen_second = Decimal(
                "1") + Decimal(str(bracket_cfg.tp_widen_second_bps)) / Decimal("10000")
            retry_backoff_ms = bracket_cfg.retry_backoff_ms

            try:
                async def place_sl_async():
                    return await self.adapter.place_stop_market_close_position(
                        symbol, sl_side, str(sl), new_client_order_id=sl_id
                    )

                async def place_tp_async():
                    try:
                        return (
                            await self.adapter.place_take_profit_market_close_position(
                                symbol, tp_side, str(tp), new_client_order_id=tp_id
                            )
                        )
                    except BinanceAPIError as e:
                        if e.code == -2021:
                            # PHASE A3: Exponential backoff for -2021 (price too close to mark)
                            LOG.warning(
                                f"⚠️ [PHASE A3] TP -2021 error, attempting backoff for {symbol}")
                            self._orphan_metrics["tp_sl_retry_backoff"] += 1

                            # Retry with widened TP (from config)
                            tp_adj = tp * tp_widen_first
                            tp_adj = quantize_stop_price(
                                tp_adj, tick_size, side="BUY" if side == "BUY" else "SELL"
                            )
                            self.metrics_collector.record_retry(
                                "tp_adjust") if self.metrics_collector else None

                            # Exponential backoff from config
                            # DET-BT-13: Use clock.sleep_ms for deterministic backtest
                            await get_clock().sleep_ms(retry_backoff_ms[0])

                            try:
                                return await self.adapter.place_take_profit_market_close_position(
                                    symbol, tp_side, str(tp_adj), new_client_order_id=tp_id
                                )
                            except BinanceAPIError as e2:
                                if e2.code == -2021 and len(retry_backoff_ms) > 1:
                                    # Second retry with second backoff
                                    LOG.warning(
                                        f"⚠️ [PHASE A3] TP -2021 retry 2, backoff {retry_backoff_ms[1]}ms for {symbol}")
                                    # DET-BT-13: Use clock.sleep_ms for deterministic backtest
                                    await get_clock().sleep_ms(retry_backoff_ms[1])

                                    tp_adj2 = tp * tp_widen_second
                                    tp_adj2 = quantize_stop_price(
                                        tp_adj2, tick_size, side="BUY" if side == "BUY" else "SELL"
                                    )

                                    try:
                                        return await self.adapter.place_take_profit_market_close_position(
                                            symbol, tp_side, str(tp_adj2), new_client_order_id=tp_id
                                        )
                                    except BinanceAPIError:
                                        # Fallback to LIMIT reduceOnly
                                        LOG.warning(
                                            f"⚠️ [PHASE A3] TP -2021 fallback to LIMIT for {symbol}")
                                        self.metrics_collector.record_retry(
                                            "tp_fallback") if self.metrics_collector else None
                                        return await self.adapter.place_limit_reduce_only(
                                            symbol,
                                            tp_side,
                                            str(tp_adj2),
                                            qty,
                                            new_client_order_id=tp_id,
                                        )
                                else:
                                    raise
                            # Fallback to LIMIT reduceOnly
                            self.metrics_collector.record_retry(
                                "tp_fallback") if self.metrics_collector else None
                            return await self.adapter.place_limit_reduce_only(
                                symbol,
                                tp_side,
                                str(tp_adj),
                                qty,
                                new_client_order_id=tp_id,
                            )
                        else:
                            raise

                # Run both in parallel
                sl_resp, tp_resp = await asyncio.gather(
                    place_sl_async(),
                    place_tp_async(),
                    return_exceptions=False
                )
            except Exception as e:
                LOG.error(f"Error placing brackets in parallel: {e}")
                # Fallback: place them sequentially
                sl_resp = await self.adapter.place_stop_market_close_position(
                    symbol, sl_side, str(sl), new_client_order_id=sl_id
                )
                try:
                    tp_resp = await self.adapter.place_take_profit_market_close_position(
                        symbol, tp_side, str(tp), new_client_order_id=tp_id
                    )
                except BinanceAPIError as e:
                    if e.code == -2021:
                        # Use config values (already loaded above in bracket_cfg)
                        tp_adj = tp * tp_widen_first
                        tp_adj = quantize_stop_price(
                            tp_adj, tick_size, side="BUY" if side == "BUY" else "SELL"
                        )
                        try:
                            tp_resp = await self.adapter.place_take_profit_market_close_position(
                                symbol, tp_side, str(tp_adj), new_client_order_id=tp_id
                            )
                        except BinanceAPIError:
                            tp_resp = await self.adapter.place_limit_reduce_only(
                                symbol,
                                tp_side,
                                str(tp_adj),
                                qty,
                                new_client_order_id=tp_id,
                            )
                    else:
                        raise

            # Log the results
            sl_order_id = None
            tp_order_id = None

            if sl_resp:
                LOG.info(f"✅ SL placed: {sl_resp}")
                self._orphan_metrics["tp_sl_placed_success"] += 1
                # Correlation: store SL ACK
                sl_order_id = str(sl_resp["orderId"])
                self.correlation_store.put_sl_tp_ack(
                    sl_order_id, entry_resp["clientOrderId"], decision.corr_id or "", decision.oco_group_id or "", decision.rid or "")
                # Track SL bracket per symbol
                self._symbol_brackets.setdefault(
                    symbol, {})["sl_order_id"] = sl_order_id

            if tp_resp:
                LOG.info(f"✅ TP placed: {tp_resp}")
                self._orphan_metrics["tp_sl_placed_success"] += 1
                # Correlation: store TP ACK
                tp_order_id = str(tp_resp["orderId"])
                self.correlation_store.put_sl_tp_ack(
                    tp_order_id, entry_resp["clientOrderId"], decision.corr_id or "", decision.oco_group_id or "", decision.rid or "")
                # Track TP bracket per symbol
                self._symbol_brackets.setdefault(
                    symbol, {})["tp_order_id"] = tp_order_id

            # [GUARD] Register brackets for ownership tracking (if any were placed)
            if sl_order_id or tp_order_id:
                self.order_guardian.register_brackets(
                    symbol=symbol,
                    entry_order_id=str(entry_resp["orderId"]),
                    sl_order_id=sl_order_id,
                    tp_order_id=tp_order_id,
                    sl_client_id=sl_id if sl_resp else None,
                    tp_client_id=tp_id if tp_resp else None,
                    corr_id=decision.corr_id,
                    rid=decision.rid
                )

                # After registering new brackets, proactively cancel any older
                # brackets tied to previous entries for this symbol. This
                # prevents accumulation of hanging reduceOnly/closePosition orders
                # when multiple entries occur sequentially.
                try:
                    await self.order_guardian.cleanup_other_brackets_for_symbol(
                        symbol,
                        keep_parent_order_id=str(entry_resp["orderId"]),
                    )
                except Exception as _e:
                    LOG.debug(
                        f"OrderGuardian cleanup_other_brackets_for_symbol skipped: {_e}")

            # ✅ NEW: Sync bracket IDs with ManageFlowFSM for OCO emulation
            # Ensures ManageFlowFSM has accurate tracking even if WebSocket events are delayed
            manage_flow = self.manage_flows.get(symbol)
            if manage_flow:
                brackets = self._symbol_brackets[symbol] if symbol in self._symbol_brackets else {
                }
                sl_id = brackets.get("sl_order_id")
                tp_id = brackets.get("tp_order_id")
                manage_flow.set_bracket_ids(
                    sl_order_id=sl_id, tp_order_id=tp_id)

        except Exception as e:
            LOG.error(
                f"❌ Adapter failed to execute decision {decision.verb} for {decision.pld.get('symbol')}: {e}",
                exc_info=True,
            )

            # Alert on execution failures (circuit breaker trigger)
            if self.alert_manager:
                try:
                    symbol = decision.pld["symbol"] if "symbol" in decision.pld else "unknown"
                    error_key = f"exec_error_{symbol}"
                    if not hasattr(self, '_exec_error_counts'):
                        self._exec_error_counts = {}
                    self._exec_error_counts[error_key] = (
                        self._exec_error_counts[error_key] if error_key in self._exec_error_counts else 0
                    ) + 1

                    # Alert if 2+ execution errors in last 10 minutes for same symbol
                    if self._exec_error_counts[error_key] >= 2:
                        self.alert_manager.check_circuit_breaker(
                            True, 600)  # 10 minutes active
                        LOG.warning(
                            f"Circuit breaker alert triggered for {symbol} due to repeated execution errors")
                except Exception as alert_e:
                    LOG.error(
                        f"Error triggering execution error alert: {alert_e}")

            # Log to OrderLoggerV1
            decision_pld = decision.pld or {}
            order_logger.write({
                "rid": decision.rid,
                "event_type": "ORDER_REJECTED",
                "symbol": decision_pld["symbol"] if "symbol" in decision_pld else "",
                "side": decision_pld["side"] if "side" in decision_pld else "NONE",
                "quantity": float(decision_pld["qty"] if "qty" in decision_pld else 0),
                "nrr_code": "NRR-015",  # Exchange rejected
                "why": f"Adapter execution failed: {str(e)}",
                "source_fsm": "ExecPosFSM",
                "metadata": {"error": str(e), "decision_verb": decision.verb}
            })

            # B2: WAL persistence for ORDER_REJECTED (INTENT-TO-ORDER-TRACE-SSOT-01)
            # Ensures adapter failures are visible in WAL for full trace
            try:
                order_rejected_msg = Message(
                    op="EVT",
                    verb="ORDER_REJECTED",
                    src="execution_position",
                    dst="observability",
                    rid=decision.rid,
                    pld={
                        "symbol": decision_pld.get("symbol", ""),
                        "side": decision_pld.get("side", "NONE"),
                        "reason_code": "ADAPTER_ERROR",
                        "reason_text": str(e)[:200],
                        "exception_class": type(e).__name__,
                        "ts_ms": get_clock().now_ms(),
                    },
                    why="adapter_execution_failed",
                )
                wal.append(order_rejected_msg.model_dump())
            except Exception as wal_e:
                LOG.warning(
                    f"Failed to write EVT:ORDER_REJECTED to WAL: {wal_e}")

            # Emit an error event
            exec_failed_msg = Message(
                op="ERR",
                verb="EXECUTION_FAILED",
                src="execution_position",
                dst="monitoring",
                rid=decision.rid,
                pld={"error": str(
                    e), "original_decision": decision.model_dump()},
                why="Execution failed due to adapter error",
            )
            await emit_compat(self.fsm, exec_failed_msg, logger=LOG)

    def get_metrics(self) -> Dict[str, Any]:
        """Aggregate metrics from all managed FSMs."""
        all_metrics = {}
        with self._flows_lock:
            for symbol, open_fsm in self.open_flows.items():
                all_metrics[f"{symbol}_open"] = open_fsm.get_metrics()
            for symbol, manage_fsm in self.manage_flows.items():
                all_metrics[f"{symbol}_manage"] = manage_fsm.get_metrics()
            for symbol, close_fsm in self.close_flows.items():
                all_metrics[f"{symbol}_close"] = close_fsm.get_metrics()

        # Include watchdog metrics
        if hasattr(self, 'watchdog'):
            all_metrics["order_timeout_watchdog"] = self.watchdog.get_metrics()

        # Include orphan-monitor metrics
        all_metrics["orphan_monitor"] = {
            **self._orphan_metrics,
            "cfg": {
                "enabled": self._orphan_cfg["enabled"],
                "periodic_interval_sec": self._orphan_cfg["periodic_interval_sec"],
                "min_order_age_sec": self._orphan_cfg["min_order_age_sec"],
                "batch_cancel_limit": self._orphan_cfg["batch_cancel_limit"],
                "rate_limit_per_min": self._orphan_cfg["rate_limit_per_min"],
            },
        }

        # Include gate metrics (SYMBOL_TIDY entry gate)
        try:
            gate_blocked = int(self._gate_metrics["gate_entry_blocked_tidy"])
            gate_allowed = int(self._gate_metrics["gate_entry_allowed_tidy"])
            all_metrics["gate"] = {
                "entry_blocked_tidy": gate_blocked,
                "entry_allowed_tidy": gate_allowed,
                "quiet_hours_enabled": self._quiet_hours_enabled,
                "quiet_hours_windows": self._quiet_hours_windows,
            }
            # Flat fields for quick access in /metrics JSON
            all_metrics["gate_entry_blocked_tidy"] = gate_blocked
            all_metrics["gate_entry_allowed_tidy"] = gate_allowed
            all_metrics["gate_entry_blocked_quiet_hours"] = int(
                self._gate_metrics.get("gate_entry_blocked_quiet_hours", 0))
            all_metrics["gate_entry_allowed_quiet_hours"] = int(
                self._gate_metrics.get("gate_entry_allowed_quiet_hours", 0))
            # Per-symbol stamps
            all_metrics["symbol_last_tidy_ts"] = dict(
                self._symbol_last_tidy_ts)
            all_metrics["last_entry_block_ts"] = dict(
                self._last_entry_block_ts)
        except Exception:
            # Be robust if attributes missing
            all_metrics["gate"] = {
                "entry_blocked_tidy": 0,
                "entry_allowed_tidy": 0,
                "quiet_hours_enabled": getattr(self, "_quiet_hours_enabled", False),
                "quiet_hours_windows": getattr(self, "_quiet_hours_windows", []),
            }
            all_metrics["gate_entry_blocked_tidy"] = 0
            all_metrics["gate_entry_allowed_tidy"] = 0
            all_metrics["gate_entry_blocked_quiet_hours"] = 0
            all_metrics["gate_entry_allowed_quiet_hours"] = 0
            all_metrics["symbol_last_tidy_ts"] = {}
            all_metrics["last_entry_block_ts"] = {}

        try:
            guardian = aget(self, "order_guardian", None)
            if guardian:
                guardian_metrics = guardian.get_metrics()
                all_metrics["order_guardian"] = guardian_metrics
                all_metrics["guardian_unified"] = self._guardian_unified
                all_metrics["guardian_emit_tidy_event"] = self._guardian_emit_tidy_event
        except Exception:
            pass

        return all_metrics

    # ---- GATE: SYMBOL_TIDY entry gating ----
    def _on_symbol_tidy_event(self, payload: Dict[str, Any]) -> None:
        try:
            symbol = payload.get("symbol") if isinstance(
                payload, dict) else None
            if symbol:
                self._symbol_last_tidy_ts[symbol] = get_clock().now_sec()
                LOG.info(f"[GATE] tidy_event: symbol={symbol}")
        except Exception:
            pass

    def _quiet_hours_gate_allow(self) -> bool:
        """Return True if new ENTRY is allowed (not in quiet hours)."""
        if not self._quiet_hours_enabled:
            return True

        if not self._quiet_hours_windows:
            return True

        if _in_quiet(self._quiet_hours_windows):
            self._gate_metrics["gate_entry_blocked_quiet_hours"] += 1
            LOG.info(
                f"[GATE] entry_blocked: quiet_hours "
                f"(windows={self._quiet_hours_windows})"
            )
            return False

        self._gate_metrics["gate_entry_allowed_quiet_hours"] += 1
        return True

    def _entry_tidy_gate_allow(self, symbol: str) -> bool:
        """Return True if new ENTRY is allowed under SYMBOL_TIDY gate."""
        # Read flag
        try:
            allow_gate = bool(
                aget(self.config.execution,
                     "allow_trade_with_guardian_tidy_only", False)
            ) if self.config.execution else False
        except Exception:
            allow_gate = False

        if not allow_gate:
            return True

        # TTL and cooldown
        ttl_ms = int(dget(self._guardian_cfg, "cleanup_ttl_ms", 6000))
        cooldown_ms = int(dget(self._guardian_cfg, "symbol_cooldown_ms", 4000))

        now = get_clock().now_sec()
        last_tidy = self._symbol_last_tidy_ts[symbol] if symbol in self._symbol_last_tidy_ts else 0.0
        fresh = (now - last_tidy) * 1000.0 <= ttl_ms
        last_block = self._last_entry_block_ts[symbol] if symbol in self._last_entry_block_ts else 0.0
        cooldown_ok = (now - last_block) * 1000.0 >= cooldown_ms

        if fresh or (last_block > 0 and cooldown_ok):
            self._gate_metrics["gate_entry_allowed_tidy"] += 1
            LOG.info(
                f"[GATE] entry_allowed: tidy_recent={fresh} cooldown_ok={cooldown_ok} last_block={last_block} symbol={symbol}")
            return True

        # Block
        self._last_entry_block_ts[symbol] = now
        self._gate_metrics["gate_entry_blocked_tidy"] += 1
        age_ms = int((now - last_tidy) * 1000.0)
        LOG.info(
            f"[GATE] entry_blocked: no_tidy_recent symbol={symbol} age_ms={age_ms} ttl_ms={ttl_ms} cooldown_ms={cooldown_ms}")
        return False

    async def _handle_order_timeout(self, deadline):
        """Handle a timed-out order with NRR-019 logging and idempotent cancellation."""
        from apps.reference.telemetry.order_logger import order_logger

        LOG.warning(
            f"Order timeout: {deadline.order_id} ({deadline.symbol}) - {deadline.timeout_type.value}, "
            f"nrr_code=NRR-019, corr_id={deadline.corr_id}, rid={deadline.rid}"
        )

        # Log to OrderLoggerV1
        order_logger.write({
            "rid": deadline.rid or f"timeout_{deadline.order_id}",
            "event_type": "ORDER_TIMEOUT",
            "symbol": deadline.symbol,
            "client_order_id": deadline.client_order_id,
            "order_id": deadline.order_id,
            "nrr_code": "NRR-019",
            "why": f"Order timeout: {deadline.timeout_type.value}",
            "source_fsm": "ExecPosFSM",
            "metadata": {
                "timeout_type": deadline.timeout_type.value,
                "corr_id": deadline.corr_id
            }
        })

        # Attempt idempotent cancellation if adapter is available
        if self.adapter and not self.shadow_mode:
            try:
                self.watchdog.cancel_attempt_count += 1
                cancel_result = await self._cancel_order(deadline.symbol, deadline.order_id)

                # ✅ NEW: Verify cancel status from exchange response
                if self._is_cancel_success_response(cancel_result):
                    # Detect whether the order was FILLED (not actually cancelled)
                    _is_terminal_filled = (
                        isinstance(cancel_result, IdempotentCancelResult)
                        and cancel_result.reason == "PRE_CHECK_TERMINAL_FILLED"
                    )
                    # Also treat PARTIALLY_FILLED -> CANCELED as fill-discovered path:
                    # exchange confirms non-zero execution before cancel.
                    _is_partial_fill_cancel = (
                        isinstance(cancel_result, IdempotentCancelResult)
                        and str(cancel_result.order_status_before or "").upper() == "PARTIALLY_FILLED"
                        and str(cancel_result.order_status_after or "").upper() in ("CANCELED", "CANCELLED")
                    )
                    _is_fill_discovered = _is_terminal_filled or _is_partial_fill_cancel

                    if _is_fill_discovered:
                        # --- FILLED path: order filled during timeout window ---
                        if _is_terminal_filled:
                            LOG.info(
                                f"[TIMEOUT-FILL] Timed-out order {deadline.order_id} "
                                f"({deadline.symbol}) was already FILLED "
                                f"(discovered via idempotent cancel pre-check)"
                            )
                            _fill_reason = "timeout_fill_discovered"
                        else:
                            LOG.info(
                                f"[TIMEOUT-FILL] Timed-out order {deadline.order_id} "
                                f"({deadline.symbol}) was PARTIALLY_FILLED before cancel "
                                f"(treating as fill-discovered for bracket recovery)"
                            )
                            _fill_reason = "timeout_partial_fill_discovered"
                        order_logger.write({
                            "rid": deadline.rid,
                            "event_type": "ORDER_FILL_DISCOVERED",
                            "symbol": deadline.symbol,
                            "order_id": deadline.order_id,
                            "reason": _fill_reason,
                            "timeout_type": deadline.timeout_type.value,
                            "timestamp": get_clock().now_ms()
                        })

                        # Place deferred brackets if pending
                        # (idempotent: no-op if already popped by _on_order_fill)
                        if deadline.order_id in self._pending_brackets:
                            bracket_data = self._pending_brackets.pop(
                                deadline.order_id)
                            try:
                                write_pending_brackets_cleared(
                                    entry_order_id=deadline.order_id,
                                    reason="timeout_fill_discovered",
                                    symbol=bracket_data.get(
                                        "symbol", deadline.symbol),
                                )
                            except Exception as wal_err:
                                LOG.warning(
                                    f"Failed to clear pending brackets from WAL: {wal_err}")

                            LOG.info(
                                f"[TIMEOUT-FILL] Placing deferred TP/SL brackets for "
                                f"{deadline.symbol} entry {deadline.order_id}"
                            )
                            loop = self._get_async_loop()
                            if loop:
                                self._submit_async(
                                    self._place_deferred_brackets(
                                        deadline.order_id, bracket_data),
                                    loop
                                )

                        # Emit TRADE_EXECUTED to update ManageFlowFSM and position tracking
                        order_data = (
                            cancel_result.order_data
                            if isinstance(cancel_result, IdempotentCancelResult)
                            else None
                        ) or {}
                        if float(dget(order_data, "executedQty", 0) or 0) <= 0:
                            try:
                                if self.adapter and hasattr(self.adapter, "get_order"):
                                    fetched_order = await self.adapter.get_order(
                                        deadline.symbol, deadline.order_id
                                    )
                                    if isinstance(fetched_order, dict):
                                        order_data = fetched_order
                            except Exception as fetch_err:
                                LOG.debug(
                                    f"[TIMEOUT-FILL] get_order fallback failed for {deadline.order_id}: {fetch_err}"
                                )

                        exec_qty = float(
                            dget(order_data, "executedQty", 0) or 0)
                        if exec_qty <= 0:
                            LOG.warning(
                                f"[TIMEOUT-FILL] executedQty unavailable for {deadline.order_id}; "
                                f"emitting TRADE_EXECUTED with qty=0"
                            )

                        fill_msg = Message(
                            op="EVT",
                            verb="TRADE_EXECUTED",
                            src="execution_position",
                            dst="execution_position",
                            rid=deadline.rid or f"timeout_fill_{deadline.order_id}",
                            why=_fill_reason,
                            pld={
                                "orderId": deadline.order_id,
                                "symbol": deadline.symbol,
                                "quantity": exec_qty,
                                "qty": exec_qty,
                                "price": float(dget(order_data, "avgPrice", 0)),
                                "side": str(dget(order_data, "side", "")),
                                "client_order_id": dget(order_data, "clientOrderId", ""),
                                "clientOrderId": dget(order_data, "clientOrderId", ""),
                                "rid": deadline.rid,
                            },
                        )
                        try:
                            self.handle(fill_msg)
                        except Exception as emit_err:
                            LOG.error(
                                f"Failed to deliver TRADE_EXECUTED for timeout fill: {emit_err}")

                    else:
                        # --- Genuine cancel path (existing behavior) ---
                        self.watchdog.cancel_success_count += 1
                        LOG.info(
                            f"✅ Cancelled timed-out order {deadline.order_id}: {cancel_result}")

                        # Log successful cancellation to order_log (use global order_logger, not self.order_logger)
                        order_logger.write({
                            "rid": deadline.rid,
                            "event_type": "ORDER_CANCELLED",
                            "symbol": deadline.symbol,
                            "order_id": deadline.order_id,
                            "reason": "timeout_cancellation",
                            "timeout_type": deadline.timeout_type.value,
                            "adapter_response": cancel_result,
                            "timestamp": get_clock().now_ms()
                        })
                else:
                    status = str(
                        cancel_result["status"]
                        if isinstance(cancel_result, dict) and "status" in cancel_result
                        else ""
                    ).upper()
                    # Cancel rejected or order in non-cancelable state (e.g., already FILLED)
                    LOG.error(
                        f"❌ Cancel rejected for timed-out order {deadline.order_id}: "
                        f"status={status}, result={cancel_result}"
                    )
                    order_logger.write({
                        "rid": deadline.rid,
                        "event_type": "ORDER_CANCELLATION_FAILED",
                        "symbol": deadline.symbol,
                        "order_id": deadline.order_id,
                        "reason": f"timeout_cancel_rejected_status_{status}",
                        "timeout_type": deadline.timeout_type.value,
                        "adapter_response": cancel_result,
                        "timestamp": get_clock().now_ms()
                    })

            except Exception as e:
                if self._is_unknown_order_error(e):
                    self.watchdog.cancel_success_count += 1
                    LOG.info(
                        f"✅ Timed-out order {deadline.order_id} already absent (-2011)")
                    order_logger.write({
                        "rid": deadline.rid,
                        "event_type": "ORDER_CANCELLED",
                        "symbol": deadline.symbol,
                        "order_id": deadline.order_id,
                        "reason": "timeout_cancel_idempotent",
                        "timeout_type": deadline.timeout_type.value,
                        "timestamp": get_clock().now_ms()
                    })
                else:
                    LOG.warning(
                        f"Failed to cancel timed-out order {deadline.order_id}: {e}")

                    # Log exception-based cancellation failure (use global order_logger)
                    order_logger.write({
                        "rid": deadline.rid,
                        "event_type": "ORDER_CANCELLATION_FAILED",
                        "symbol": deadline.symbol,
                        "order_id": deadline.order_id,
                        "reason": "timeout_cancel_exception",
                        "timeout_type": deadline.timeout_type.value,
                        "error": str(e),
                        "timestamp": get_clock().now_ms()
                    })

        # Record timeout metric
        if self.metrics_collector:
            self.metrics_collector.record_order_timeout()

        # Alert on circuit breaker conditions (multiple timeouts)
        if self.alert_manager:
            # Track timeout count per symbol for circuit breaker
            timeout_key = f"timeout_{deadline.symbol}"
            if not hasattr(self, '_timeout_counts'):
                self._timeout_counts = {}
            cur = self._timeout_counts[timeout_key] if timeout_key in self._timeout_counts else 0
            self._timeout_counts[timeout_key] = cur + 1

            # Alert if 3+ timeouts in last 5 minutes for same symbol
            if self._timeout_counts[timeout_key] >= 3:
                try:
                    self.alert_manager.check_circuit_breaker(
                        True, 300)  # 5 minutes active
                    LOG.warning(
                        f"Circuit breaker alert triggered for {deadline.symbol} due to repeated timeouts")
                except Exception as e:
                    LOG.error(f"Error triggering circuit breaker alert: {e}")

        # Emit event for monitoring
        timeout_msg = Message(
            op="EVT",
            verb="ORDER_TIMEOUT",
            intent="OBSERVATION",
            src="execution_position",
            dst="monitoring",
            rid=deadline.rid or f"timeout_{deadline.order_id}",
            pld={
                "order_id": deadline.order_id,
                "client_order_id": deadline.client_order_id,
                "symbol": deadline.symbol,
                "timeout_type": deadline.timeout_type.value,
                "corr_id": deadline.corr_id,
                "nrr_code": "NRR-019"
            },
            why="order_timeout_expired",
        )

        try:
            await emit_compat(self.fsm, timeout_msg, logger=aget(self, "logger", None))
        except Exception as e:
            LOG.error(f"Failed to emit timeout event: {e}")

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

    def _check_exposure_fail_closed(self, msg: Message) -> Optional[Message]:
        """
        EXP-FIX: Check exposure limits with fail-closed behavior.

        Returns error Message if request should be blocked, else None.
        """
        pld = msg.pld or {}
        symbol = pld.get("symbol")
        qty = pld.get("qty")
        price_ref = pld.get("price_ref")

        if not symbol or not qty or not price_ref:
            LOG.warning(
                f"EXPOSURE_CHECK_SKIP: Missing required fields for {symbol}")
            return None

        side_raw = pld.get("side")
        side_str = getattr(side_raw, "value", side_raw)
        side = str(side_str).strip().upper() if side_str is not None else ""
        if not side:
            raise ValueError(
                "Order side is missing in payload. Cannot default to BUY."
            )
        if side not in {"BUY", "SELL", "LONG", "SHORT"}:
            raise ValueError(f"Order side is invalid: {side_raw!r}")

        try:
            # Calculate notional
            notional_abs = Decimal(str(qty)) * Decimal(str(price_ref))
            notional_signed = - \
                notional_abs if side in {"SELL", "SHORT"} else notional_abs

            reduce_only = bool(pld.get("reduce_only", False))
            reserve_key = pld.get(
                "idempotent_key") or msg.rid or f"rid_{msg.rid}"

            # Check exposure with fail-closed logic
            # EXP-FIX: Detect FLIP/Reduce (Opposite side order) to prevent double-counting exposure
            is_flip = False
            positions = self._latest_portfolio_state.get("positions") or []
            for p in positions:
                if isinstance(p, dict) and str(p.get("symbol", "")).strip() == symbol:
                    curr_qty_str = str(p.get("net_position", "0"))
                    # simple check: if qty != 0 and sign mismatch with intent side
                    try:
                        curr_qty = Decimal(curr_qty_str)
                        if curr_qty != 0:
                            curr_side_is_buy = curr_qty > 0
                            intent_side_is_buy = (side in {"BUY", "LONG"})
                            if curr_side_is_buy != intent_side_is_buy:
                                is_flip = True
                    except Exception:
                        pass
                    break

            exposure_check = self.exposure_guard.can_open(
                symbol, notional_signed, self._latest_portfolio_state, is_flip=is_flip
            )

            if not exposure_check["allowed"]:
                reason = exposure_check["reason"]
                stale_sec = exposure_check["stale_sec"] if "stale_sec" in exposure_check else 0

                # Emit ERR:OPEN with fail-closed reason
                error_msg = Message(
                    op="ERR",
                    verb="OPEN",
                    src="execution_position",
                    dst=msg.src,
                    rid=msg.rid,
                    pld={
                        "reason": reason,
                        "stale_sec": stale_sec,
                        "symbol": symbol,
                        "side": side,
                        "idempotent_key": str(pld.get("idempotent_key") or ""),
                        "requested_notional": str(notional_signed),
                    },
                    why=f"exposure_fail_closed_{reason.lower()}",
                )

                # WAL: persist failure synchronously so CMD:OPEN never "vanishes".
                try:
                    wal.append(error_msg.model_dump())
                except Exception as wal_e:
                    LOG.warning(f"Failed to write ERR:OPEN to WAL: {wal_e}")

                LOG.error(
                    f"EXPOSURE_FAIL_CLOSED_OPEN_BLOCKED: rid={msg.rid} symbol={symbol} side={side} reason={reason} stale_sec={stale_sec}"
                )

                # EXP-FIX: Record fail-closed metric
                if hasattr(self, "metrics_collector") and self.metrics_collector:
                    self.metrics_collector.record_exposure_fail_closed(reason)

                return error_msg

            # Soft-limit clipping: if ExposureGuard clipped requested notional, scale qty down.
            try:
                clipped_abs = exposure_check.get("clipped_notional_abs") if isinstance(
                    exposure_check, dict) else None
                if clipped_abs is not None:
                    clipped_abs_dec = Decimal(str(clipped_abs))
                    if clipped_abs_dec > Decimal("0") and clipped_abs_dec < abs(notional_signed):
                        price_dec = Decimal(str(price_ref))
                        if price_dec > Decimal("0"):
                            new_qty = clipped_abs_dec / price_dec
                            # Mutate payload so downstream uses clipped qty (will still be normalized later).
                            pld["qty"] = str(new_qty)
                            pld["exposure_clip"] = {
                                "requested_notional_abs": str(abs(notional_signed)),
                                "clipped_notional_abs": str(clipped_abs_dec),
                                "clip_reasons": exposure_check.get("clip_reasons", []),
                            }
                            notional_abs = clipped_abs_dec
                            notional_signed = - \
                                clipped_abs_dec if side in {
                                    "SELL", "SHORT"} else clipped_abs_dec
            except Exception:
                # Clipping is best-effort; do not block execution if clip metadata is malformed.
                pass

            # EXP-FIX: Periodic shadow notional check (config-based sampling rate)
            shadow_cfg = self.config.domains.execution_position.shadow_check
            self._shadow_check_counter += 1

            if shadow_cfg.enabled and self._shadow_check_counter % shadow_cfg.check_every_n_requests == 0 and self.adapter:
                loop = self._get_async_loop()
                if loop:
                    self._submit_async(self._check_shadow_notional(), loop)

            # Reserve exposure for successful check
            self.exposure_guard.reserve(
                reserve_key,
                notional_abs,
                reduce_only=reduce_only,
                symbol=str(symbol),
                side=side,
            )

            return None

        except Exception as e:
            LOG.error(f"EXPOSURE_CHECK_ERROR: {e}", exc_info=True)

            # Fail-closed on any exposure-check error.
            reason = "EXPOSURE_CHECK_ERROR"
            error_msg = Message(
                op="ERR",
                verb="OPEN",
                src="execution_position",
                dst=msg.src,
                rid=msg.rid,
                pld={
                    "reason": reason,
                    "symbol": symbol,
                    "side": side,
                    "idempotent_key": str(pld.get("idempotent_key") or ""),
                },
                why="exposure_fail_closed_exception",
            )

            try:
                wal.append(error_msg.model_dump())
            except Exception as wal_e:
                LOG.warning(
                    f"Failed to write ERR:OPEN(EXPOSURE_CHECK_ERROR) to WAL: {wal_e}")

            return error_msg

    def _handle_cancel_event(self, msg: Message) -> None:
        """
        EXP-FIX: Handle order cancellation events for exposure summary update.

        Emits EVT:EXPOSURE_SUMMARY_UPDATED after order cancellation to ensure
        exposure monitoring stays current.
        """
        pld = msg.pld or {}
        symbol = pld.get("symbol")
        order_id = pld.get("order_id") or pld.get("orderId")
        client_order_id = pld.get("client_order_id")

        LOG.info(
            f"CANCEL_EVENT: Processing cancellation for {symbol} order {order_id}")

        # LIMIT-ENTRY-DEFERRED-BRACKETS: Cleanup pending brackets if entry was cancelled
        if order_id and order_id in self._pending_brackets:
            bracket_data = self._pending_brackets.pop(order_id, None)

            # PHASE4: Mark as cleared in WAL
            try:
                write_pending_brackets_cleared(
                    entry_order_id=order_id,
                    reason="cancelled",
                    symbol=bracket_data.get(
                        "symbol", "") if bracket_data else "",
                )
            except Exception as e:
                LOG.warning(f"Failed to clear pending brackets from WAL: {e}")

            LOG.info(
                f"📌 [LIMIT-DEFERRED] Cleaned up pending brackets for cancelled entry {order_id}"
            )

        # TASK40: Mark order terminal in OrderIndex (unblocks one-open-order guard).
        try:
            # type: ignore[attr-defined]
            if hasattr(self.fsm, "order_index") and self.fsm.order_index:
                ref = None
                if order_id:
                    ref = self.fsm.order_index.get(exchangeOrderId=str(
                        order_id))  # type: ignore[attr-defined]
                if ref is None and client_order_id:
                    ref = self.fsm.order_index.get(clientOrderId=str(
                        client_order_id))  # type: ignore[attr-defined]
                if ref is not None:
                    self.fsm.order_index.mark_terminal(
                        ref)  # type: ignore[attr-defined]
        except Exception:
            pass

        # Emit exposure summary update after cancellation
        try:
            exposure_msg = Message(
                op="EVT",
                verb="EXPOSURE_SUMMARY_UPDATED",
                src="execution_position",
                dst="monitoring",
                rid=pld.get("rid") or msg.rid or f"cancel_{order_id}",
                pld={
                    "symbol": symbol,
                    "order_id": order_id,
                    "client_order_id": client_order_id,
                    "reason": "order_cancelled",
                    "timestamp": get_clock().now_ms()
                },
                why="order_cancelled_exposure_update",
            )

            # Emit asynchronously
            loop = self._get_async_loop()
            if loop:
                self._submit_async(
                    self._emit_exposure_update_async(exposure_msg), loop)
            else:
                LOG.warning(
                    "No event loop available for cancel exposure update")

        except Exception as e:
            LOG.error(
                f"CANCEL_EVENT_ERROR: Failed to emit exposure update for {order_id}: {e}")

        # EP-01.3-SUPERSEDE-ACK: Check if this cancel allows queued supersede to proceed
        if symbol and symbol in self._supersede_canceling:
            # Check if pending entries for this symbol are now clear
            has_more_pending = False
            if self.watchdog:
                for deadline in self.watchdog.pending_orders.values():
                    if deadline.symbol == symbol:
                        has_more_pending = True
                        break
                if not has_more_pending:
                    for deadline in self.watchdog.acked_orders.values():
                        if deadline.symbol == symbol:
                            has_more_pending = True
                            break

            if not has_more_pending:
                LOG.info(
                    f"EP-01.3: {symbol} cancel confirmed, processing queued supersede")
                self._process_queued_supersede(symbol)

    async def _emit_exposure_update_async(self, msg: Message) -> None:
        """Asynchronously emit exposure update event."""
        try:
            from vfoundation import emit_compat
            await emit_compat(self.fsm, msg, logger=aget(self, "logger", None))
        except Exception as e:
            LOG.exception(f"Failed to emit exposure update event: {e}")

    async def _check_shadow_notional(self) -> None:
        """
        EXP-FIX: Periodic shadow notional check for safety auditing.

        Compares portfolio positions with exchange data and emits warnings on mismatch.
        """
        try:
            if not hasattr(self, "adapter") or not self.adapter:
                return

            # BACKTEST-GUARD: MockBroker doesn't have this method
            if not hasattr(self.adapter, "get_positions_notional_usd_shadow"):
                return

            # Get shadow notional from exchange
            shadow_notional = await self.adapter.get_positions_notional_usd_shadow()

            # Get portfolio notional
            portfolio_notional = Decimal(
                str(self._latest_portfolio_state["open_positions_usd"]
                    if "open_positions_usd" in self._latest_portfolio_state else "0")
            )

            # MAGIC-NUM-EXTRACTION: Compare with tolerance from config
            shadow_cfg = self.config.domains.execution_position.shadow_check
            max_notional = max(shadow_notional, float(portfolio_notional), 1)
            diff_abs = abs(shadow_notional - float(portfolio_notional))
            diff_pct = (diff_abs / max_notional) * 100

            # Determine which threshold to use based on portfolio size
            use_absolute = (
                shadow_cfg.use_absolute_for_large_portfolios
                and max_notional >= shadow_cfg.large_portfolio_threshold_usd
            )

            if use_absolute:
                is_mismatch = diff_abs > shadow_cfg.absolute_threshold_usd
                threshold_desc = f">${shadow_cfg.absolute_threshold_usd:.0f}"
            else:
                is_mismatch = diff_pct > shadow_cfg.tolerance_pct
                threshold_desc = f">{shadow_cfg.tolerance_pct}%"

            if is_mismatch:
                LOG.warning(
                    f"EXPOSURE_MISMATCH: portfolio={portfolio_notional}, shadow={shadow_notional}, "
                    f"diff={diff_pct:.2f}%, threshold={threshold_desc}"
                )
                self.exposure_guard._increment_metric(
                    "exposure_mismatch_total", "shadow_check"
                )

                # EXP-FIX: Record mismatch metric
                # NOTE: record_exposure_mismatch not yet implemented in MetricsCollector

                # Emit event for monitoring
                mismatch_msg = Message(
                    op="EVT",
                    verb="EXPOSURE_MISMATCH",
                    src="execution_position",
                    dst="monitoring",
                    rid="shadow_check",
                    pld={
                        "portfolio_notional": str(portfolio_notional),
                        "shadow_notional": shadow_notional,
                        "diff_pct": diff_pct,
                        "threshold": threshold_desc,
                    },
                    why="shadow_notional_mismatch",
                )
                await emit_compat(self.fsm, mismatch_msg, logger=LOG)
            else:
                LOG.debug(
                    f"SHADOW_CHECK_OK: portfolio={portfolio_notional}, shadow={shadow_notional}"
                )

        except Exception as e:
            LOG.error(f"SHADOW_CHECK_ERROR: {e}", exc_info=True)

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
            "rid": self.current_decision.rid if hasattr(self, 'current_decision') and self.current_decision else "N/A",
            **data
        }
        LOG.info(f"📊 [EVENT] {event_type}: {event}", extra={"event": event})

    async def _preflight_position_check(self, symbol: str) -> bool:
        """
        PHASE A3: Pre-flight check before placing TP/SL orders.

        Checks if position exists (positionAmt != 0) via /fapi/v2/positionRisk.
        Uses wait-until loop with exponential backoff to handle REST lag after MARKET entry fill.
        For polling mode (no WebSocket), REST lag can be 500-1500ms.

        Args:
            symbol: Trading pair

        Returns:
            True if position exists and valid, False if position is 0 or missing
        """
        # POLLING-FIX: Exponential backoff for REST-only mode
        # FAIL-CLOSED: must be provided by YAML (trading.execution.preflight_backoff_ms)
        exec_cfg = getattr(self.config, "trading", None)
        exec_cfg = getattr(exec_cfg, "execution",
                           None) if exec_cfg is not None else None
        backoff_ms = getattr(exec_cfg, "preflight_backoff_ms",
                             None) if exec_cfg is not None else None
        if not backoff_ms:
            raise ValueError(
                "trading.execution.preflight_backoff_ms is required for TP/SL preflight; no fallback/default is allowed."
            )
        backoff_ms = [int(x) for x in backoff_ms]
        if any(x <= 0 for x in backoff_ms):
            raise ValueError(
                f"trading.execution.preflight_backoff_ms must be positive ints, got: {backoff_ms}"
            )
        tries = 0
        start = get_clock().now_sec()

        while True:
            tries += 1
            try:
                positions = await self.adapter.get_open_positions(symbol)
                # Convert to dict if needed
                positions_list = [
                    p.to_dict() if hasattr(p, 'to_dict') else (
                        p.__dict__ if not isinstance(p, dict) else p)
                    for p in positions
                ]

                pos = next(
                    (p for p in positions_list if p.get("symbol") == symbol), None)

                if pos is None:
                    position_amt = 0.0
                    LOG.warning(
                        f"[BRK] preflight: position NOT FOUND for {symbol}, available: {[p.get('symbol') for p in positions_list]}")
                else:
                    # Support both 'positionAmt' (old) and 'position_amount' (new ExchangePosition)
                    position_amt = float(
                        pos.get("position_amount") or pos.get("positionAmt") or 0)
                    LOG.info(
                        f"[BRK] preflight: found position for {symbol}, position_amount={position_amt}")

                elapsed_ms = int((get_clock().now_sec() - start) * 1000)
                LOG.info(
                    f"[BRK] preflight positionRisk posAmt={position_amt} try={tries} elapsed={elapsed_ms}ms")

                # Position found!
                if abs(position_amt) >= 1e-10:
                    LOG.info("[BRK] preflight DECISION=allow (pos!=0)")
                    return True

                # Exhausted retries
                if tries > len(backoff_ms):
                    LOG.warning(
                        f"🚫 [PHASE A3] PRE-FLIGHT SKIPPED: Position is 0 for {symbol} after {tries} tries (TP_SL_SKIPPED_NO_POSITION)")
                    self._orphan_metrics["tp_sl_skipped_no_position"] += 1
                    return False

                # Wait before next retry
                # DET-BT-13: Use clock.sleep_ms for deterministic backtest
                await get_clock().sleep_ms(backoff_ms[tries - 1])

            except Exception as e:
                LOG.warning(
                    f"⚠️ [PHASE A3] PRE-FLIGHT ERROR for {symbol} (try {tries}): {e}")
                if tries > len(backoff_ms):
                    return False
                # DET-BT-13: Use clock.sleep_ms for deterministic backtest
                await get_clock().sleep_ms(backoff_ms[tries - 1])

    async def _place_deferred_brackets(
        self, entry_order_id: str, bracket_data: Dict[str, Any]
    ) -> None:
        """
        LIMIT-ENTRY-DEFERRED-BRACKETS: Place TP/SL brackets after LIMIT entry fill.

        Called from _on_order_fill when a LIMIT entry order is filled.
        Uses cached bracket data to place SL and TP orders.
        """
        symbol = bracket_data["symbol"]
        side = bracket_data["side"]
        sl = bracket_data["sl"]
        tp = bracket_data["tp"]
        _qty = bracket_data["qty"]  # Extracted but unused: closePosition=True
        rid = bracket_data.get("rid")
        idem_key = bracket_data.get("idem_key")
        tick_size = bracket_data.get("tick_size", Decimal("0.1"))
        corr_id = bracket_data.get("corr_id")
        oco_group_id = bracket_data.get("oco_group_id")
        entry_client_order_id = bracket_data.get("entry_client_order_id")

        LOG.info(
            f"📌 [LIMIT-DEFERRED] Placing brackets for {symbol}: SL={sl}, TP={tp}"
        )

        # Pre-flight check: verify position exists (should be there after fill)
        if not await self._preflight_position_check(symbol):
            LOG.warning(
                f"🚫 [LIMIT-DEFERRED] Position check failed for {symbol}, skipping brackets"
            )
            return

        # Check with OrderGuardian
        if not await self.order_guardian.should_place_brackets(symbol, entry_order_id):
            LOG.warning(
                f"🚫 [LIMIT-DEFERRED] OrderGuardian blocked brackets for {symbol}"
            )
            return

        # Generate bracket IDs
        sl_side = opposite_side(side)
        sl_id = generate_client_order_id(
            "SL", symbol, idempotent_key=str(idem_key) if idem_key else None
        )
        tp_side = opposite_side(side)
        tp_id = generate_client_order_id(
            "TP", symbol, idempotent_key=str(idem_key) if idem_key else None
        )

        # MAGIC-NUM-EXTRACTION: Read bracket placement config from SSOT
        bracket_cfg = self.config.domains.execution_position.bracket_placement
        tp_widen_first = Decimal(
            "1") + Decimal(str(bracket_cfg.tp_widen_first_bps)) / Decimal("10000")

        # Place SL and TP
        sl_resp = None
        tp_resp = None
        try:
            sl_resp = await self.adapter.place_stop_market_close_position(
                symbol, sl_side, str(sl), new_client_order_id=sl_id
            )
            LOG.info(f"✅ [LIMIT-DEFERRED] SL placed: {sl_resp}")
            self._orphan_metrics["tp_sl_placed_success"] += 1

            # Correlation store
            sl_order_id = str(sl_resp["orderId"])
            self.correlation_store.put_sl_tp_ack(
                sl_order_id, entry_client_order_id or "", corr_id or "",
                oco_group_id or "", rid or ""
            )
            self._symbol_brackets.setdefault(
                symbol, {})["sl_order_id"] = sl_order_id

        except Exception as e:
            LOG.error(
                f"❌ [LIMIT-DEFERRED] Failed to place SL for {symbol}: {e}")

        try:
            tp_resp = await self.adapter.place_take_profit_market_close_position(
                symbol, tp_side, str(tp), new_client_order_id=tp_id
            )
            LOG.info(f"✅ [LIMIT-DEFERRED] TP placed: {tp_resp}")
            self._orphan_metrics["tp_sl_placed_success"] += 1

            # Correlation store
            tp_order_id = str(tp_resp["orderId"])
            self.correlation_store.put_sl_tp_ack(
                tp_order_id, entry_client_order_id or "", corr_id or "",
                oco_group_id or "", rid or ""
            )
            self._symbol_brackets.setdefault(
                symbol, {})["tp_order_id"] = tp_order_id

        except BinanceAPIError as e:
            if e.code == -2021:
                # TP too close to mark price - widen and retry (config-based)
                LOG.warning(
                    f"⚠️ [LIMIT-DEFERRED] TP -2021 for {symbol}, widening")
                tp_adj = tp * tp_widen_first
                tp_adj = quantize_stop_price(
                    tp_adj, tick_size, side="BUY" if side == "BUY" else "SELL"
                )
                try:
                    tp_resp = await self.adapter.place_take_profit_market_close_position(
                        symbol, tp_side, str(tp_adj), new_client_order_id=tp_id
                    )
                    LOG.info(
                        f"✅ [LIMIT-DEFERRED] TP placed (widened): {tp_resp}")
                    tp_order_id = str(tp_resp["orderId"])
                    self.correlation_store.put_sl_tp_ack(
                        tp_order_id, entry_client_order_id or "", corr_id or "",
                        oco_group_id or "", rid or ""
                    )
                    self._symbol_brackets.setdefault(
                        symbol, {})["tp_order_id"] = tp_order_id
                except Exception as e2:
                    LOG.error(
                        f"❌ [LIMIT-DEFERRED] TP retry failed for {symbol}: {e2}")
            else:
                LOG.error(
                    f"❌ [LIMIT-DEFERRED] Failed to place TP for {symbol}: {e}")
        except Exception as e:
            LOG.error(
                f"❌ [LIMIT-DEFERRED] Failed to place TP for {symbol}: {e}")

        # Register brackets with OrderGuardian
        if sl_resp:
            self.order_guardian.register_bracket(
                symbol=symbol,
                parent_order_id=entry_order_id,
                order_id=str(sl_resp["orderId"]),
                client_order_id=sl_id,
                kind="SL",
                corr_id=corr_id,
                rid=rid
            )
        if tp_resp:
            self.order_guardian.register_bracket(
                symbol=symbol,
                parent_order_id=entry_order_id,
                order_id=str(tp_resp["orderId"]),
                client_order_id=tp_id,
                kind="TP",
                corr_id=corr_id,
                rid=rid
            )

        LOG.info(
            f"✅ [LIMIT-DEFERRED] Brackets placed for {symbol}: "
            f"SL={'OK' if sl_resp else 'FAILED'}, TP={'OK' if tp_resp else 'FAILED'}"
        )

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
                raise
            except Exception as e:
                LOG.debug(f"cleanup loop error: {e}")
                self._orphan_metrics["errors"] += 1

    # ═══════════════════════════════════════════════════════════════════════════════
    # BRACKET-HEALTH: Periodic Bracket Health Check (Safety Net)
    # ═══════════════════════════════════════════════════════════════════════════════

    def _schedule_bracket_health_loop(self) -> None:
        """Schedule the bracket health check background loop."""
        if self._bracket_health_started:
            return
        try:
            cfg = self.config.domains.execution_position.bracket_health_check
            if not cfg or not cfg.enabled:
                LOG.info("[BRACKET-HEALTH] disabled by config")
                return
        except (AttributeError, TypeError):
            LOG.info("[BRACKET-HEALTH] no config found, skipping")
            return

        loop = self._get_async_loop()
        if not loop:
            LOG.debug("[BRACKET-HEALTH] deferred: no event loop active")
            return

        self._submit_async(self._bracket_health_loop(), loop)
        self._bracket_health_started = True
        LOG.info(
            f"[BRACKET-HEALTH] scheduled (interval={cfg.interval_sec}s, grace={cfg.grace_period_ms}ms)")

    async def _bracket_health_loop(self) -> None:
        """BRACKET-HEALTH: Periodic safety net loop for missing SL/TP."""
        try:
            cfg = self.config.domains.execution_position.bracket_health_check
            if not cfg or not cfg.enabled:
                return
        except (AttributeError, TypeError):
            return

        while True:
            try:
                await get_clock().sleep_sec(cfg.interval_sec)
                await self._run_bracket_health_check(cfg)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                LOG.warning(f"[BRACKET-HEALTH] loop error: {e}")

    async def _run_bracket_health_check(self, cfg) -> None:
        """Run one cycle of bracket health checking."""
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
            # Rate limit placements per cycle
            if placements_this_cycle >= cfg.max_placements_per_cycle:
                LOG.debug(
                    f"[BRACKET-HEALTH] rate limit reached ({cfg.max_placements_per_cycle}/cycle)")
                break

            # Extract position data
            if hasattr(pos, 'to_dict'):
                pos_dict = pos.to_dict()
            elif isinstance(pos, dict):
                pos_dict = pos
            else:
                pos_dict = pos.__dict__ if hasattr(pos, '__dict__') else {}

            symbol = pos_dict.get("symbol")
            position_amt_str = pos_dict.get(
                "positionAmt") or pos_dict.get("position_amount", "0")
            try:
                position_amt = float(position_amt_str)
            except (TypeError, ValueError):
                position_amt = 0.0

            if not symbol or position_amt == 0.0:
                continue

            # Determine side from position amount
            side = "BUY" if position_amt > 0 else "SELL"

            entry_price_str = pos_dict.get(
                "entryPrice") or pos_dict.get("entry_price", "0")
            try:
                entry_price = float(entry_price_str)
            except (TypeError, ValueError):
                entry_price = 0.0

            if entry_price <= 0.0:
                continue

            # Grace period: skip positions opened too recently
            update_time_ms = int(pos_dict.get("updateTime")
                                 or pos_dict.get("update_time_ms", 0) or 0)
            if update_time_ms > 0 and (current_time_ms - update_time_ms) < cfg.grace_period_ms:
                LOG.debug(
                    f"[BRACKET-HEALTH] {symbol} within grace period, skipping")
                continue

            # Check if brackets exist on exchange
            has_sl, has_tp = await self._check_brackets_on_exchange(symbol)

            if has_sl and has_tp:
                continue  # All good

            missing = []
            if not has_sl:
                missing.append("SL")
            if not has_tp:
                missing.append("TP")
            LOG.warning(
                f"[BRACKET-HEALTH] {symbol} MISSING {'+'.join(missing)} "
                f"(side={side}, entry={entry_price}, regime={self._last_regime_by_symbol.get(symbol, 'UNKNOWN')})"
            )

            # Compute and place missing brackets
            try:
                sl_price, tp_price = self._compute_health_check_brackets(
                    symbol, entry_price, side)
                if sl_price is None or tp_price is None:
                    LOG.warning(
                        f"[BRACKET-HEALTH] {symbol} failed to compute TP/SL from config")
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
            except Exception as e:
                LOG.error(
                    f"[BRACKET-HEALTH] {symbol} bracket placement failed: {e}")

    async def _check_brackets_on_exchange(self, symbol: str) -> Tuple[bool, bool]:
        """
        Check if SL and TP orders exist on exchange for a symbol.

        Uses raw Binance API because ExchangeOrderResponse doesn't include order type.
        Fail-closed: if check fails, assume brackets exist (don't risk duplicates).

        Returns:
            (has_sl, has_tp) tuple
        """
        try:
            # Use raw API request to get order type field
            raw_orders = await self.adapter._request(
                "GET", "/fapi/v1/openOrders", {"symbol": symbol}
            )

            has_sl = False
            has_tp = False

            for order in (raw_orders or []):
                order_type = str(order.get("type", "")).upper()
                reduce_only = order.get("reduceOnly", False)
                close_position = order.get("closePosition", False)

                # SL: STOP_MARKET with reduceOnly or closePosition
                if order_type == "STOP_MARKET" and (reduce_only or close_position):
                    has_sl = True

                # TP: TAKE_PROFIT_MARKET with reduceOnly or closePosition
                if order_type == "TAKE_PROFIT_MARKET" and (reduce_only or close_position):
                    has_tp = True

            return has_sl, has_tp

        except Exception as e:
            LOG.warning(
                f"[BRACKET-HEALTH] failed to check orders for {symbol}: {e}")
            return True, True  # Fail-closed: assume brackets exist

    def _compute_health_check_brackets(
        self, symbol: str, entry_price: float, side: str
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Compute SL/TP prices from SSOT config for bracket health check.

        Uses strategies.aurora.assets[symbol].exit + take_profit + regime_tpsl.
        Falls back to DEFAULT regime multipliers if current regime unknown.

        Returns:
            (sl_price, tp_price) or (None, None) if config missing
        """
        try:
            aurora_cfg = self.config.strategies.aurora
            if aurora_cfg is None:
                return None, None

            asset_cfg = aurora_cfg.assets.get(symbol)
            if asset_cfg is None:
                LOG.warning(
                    f"[BRACKET-HEALTH] no aurora asset config for {symbol}")
                return None, None

            # Get base SL/TP parameters
            exit_cfg = asset_cfg.exit
            tp_cfg = asset_cfg.take_profit
            if exit_cfg is None or exit_cfg.sl_pct is None:
                LOG.warning(f"[BRACKET-HEALTH] {symbol} missing exit.sl_pct")
                return None, None
            if tp_cfg is None or tp_cfg.tp_low_ratio is None:
                LOG.warning(
                    f"[BRACKET-HEALTH] {symbol} missing take_profit.tp_low_ratio")
                return None, None

            sl_pct = float(exit_cfg.sl_pct)
            tp_low_ratio = float(tp_cfg.tp_low_ratio)

            # Apply regime multipliers if regime_tpsl is enabled
            sl_mult = 1.0
            tp_mult = 1.0

            regime_tpsl = getattr(exit_cfg, "regime_tpsl", None)
            if regime_tpsl and regime_tpsl.enabled:
                regime = self._last_regime_by_symbol.get(symbol, "DEFAULT")
                if regime_tpsl.mode == "pct_mult":
                    sl_mult = regime_tpsl.sl_mult.get(
                        regime, regime_tpsl.sl_mult.get("DEFAULT", 1.0))
                    tp_mult = regime_tpsl.tp_mult.get(
                        regime, regime_tpsl.tp_mult.get("DEFAULT", 1.0))

                    # Apply guardrails
                    sl_pct_eff = sl_pct * sl_mult
                    sl_pct_eff = max(regime_tpsl.min_sl_pct, min(
                        regime_tpsl.max_sl_pct, sl_pct_eff))

                    tp_ratio_eff = tp_low_ratio * tp_mult
                    tp_ratio_eff = max(regime_tpsl.min_tp_rr, min(
                        regime_tpsl.max_tp_rr, tp_ratio_eff))
                else:
                    sl_pct_eff = sl_pct
                    tp_ratio_eff = tp_low_ratio
            else:
                sl_pct_eff = sl_pct
                tp_ratio_eff = tp_low_ratio

            # Compute final TP as sl_pct_eff * tp_ratio_eff (risk-reward model)
            tp_pct_eff = sl_pct_eff * tp_ratio_eff

            # Get tick_size for quantization
            instrument_spec = self.config.instruments.get(symbol)
            tick_size = Decimal(
                instrument_spec.tick_size) if instrument_spec else Decimal("0.01")

            # Calculate prices based on side
            if side == "BUY":
                sl_price = entry_price * (1.0 - sl_pct_eff)
                tp_price = entry_price * (1.0 + tp_pct_eff)
            else:  # SELL
                sl_price = entry_price * (1.0 + sl_pct_eff)
                tp_price = entry_price * (1.0 - tp_pct_eff)

            # Quantize to tick_size
            sl_price = float(quantize_stop_price(
                Decimal(str(sl_price)), tick_size))
            tp_price = float(quantize_stop_price(
                Decimal(str(tp_price)), tick_size))

            LOG.info(
                f"[BRACKET-HEALTH] {symbol} computed: SL={sl_price}, TP={tp_price} "
                f"(sl_pct_eff={sl_pct_eff:.4f}, tp_pct_eff={tp_pct_eff:.4f}, "
                f"regime={self._last_regime_by_symbol.get(symbol, 'DEFAULT')})"
            )

            return sl_price, tp_price

        except Exception as e:
            LOG.error(f"[BRACKET-HEALTH] {symbol} compute error: {e}")
            return None, None

    async def _place_health_check_brackets(
        self,
        symbol: str,
        side: str,
        sl_price: float,
        tp_price: float,
        need_sl: bool,
        need_tp: bool,
    ) -> bool:
        """
        Place missing SL/TP brackets detected by health check.

        Uses adapter.place_stop_market_close_position and place_take_profit_market_close_position.
        Registers placed brackets with OrderGuardian.

        Returns:
            True if at least one bracket was placed
        """
        if not self.adapter:
            return False

        # Preflight: verify position still exists
        if not await self._preflight_position_check(symbol):
            LOG.warning(
                f"[BRACKET-HEALTH] {symbol} position check failed, skipping")
            return False

        bracket_side = opposite_side(side)
        placed = False

        # Place SL if missing
        if need_sl:
            try:
                sl_id = generate_client_order_id("BHSL", symbol)
                sl_resp = await self.adapter.place_stop_market_close_position(
                    symbol, bracket_side, str(sl_price), new_client_order_id=sl_id
                )
                sl_order_id = str(sl_resp.get("orderId", "") if isinstance(
                    sl_resp, dict) else getattr(sl_resp, "order_id", ""))
                LOG.info(
                    f"[BRACKET-HEALTH] {symbol} SL placed: price={sl_price}, orderId={sl_order_id}")

                # Register with OrderGuardian
                if self.order_guardian and sl_order_id:
                    self.order_guardian.register_bracket(
                        symbol=symbol,
                        parent_order_id="health_check",
                        order_id=sl_order_id,
                        client_order_id=sl_id,
                        kind="SL",
                        corr_id="bracket_health",
                        rid="bracket_health",
                    )
                self._symbol_brackets.setdefault(
                    symbol, {})["sl_order_id"] = sl_order_id
                placed = True
            except Exception as e:
                LOG.error(
                    f"[BRACKET-HEALTH] {symbol} SL placement failed: {e}")

        # Place TP if missing
        if need_tp:
            try:
                tp_id = generate_client_order_id("BHTP", symbol)
                tp_resp = await self.adapter.place_take_profit_market_close_position(
                    symbol, bracket_side, str(tp_price), new_client_order_id=tp_id
                )
                tp_order_id = str(tp_resp.get("orderId", "") if isinstance(
                    tp_resp, dict) else getattr(tp_resp, "order_id", ""))
                LOG.info(
                    f"[BRACKET-HEALTH] {symbol} TP placed: price={tp_price}, orderId={tp_order_id}")

                # Register with OrderGuardian
                if self.order_guardian and tp_order_id:
                    self.order_guardian.register_bracket(
                        symbol=symbol,
                        parent_order_id="health_check",
                        order_id=tp_order_id,
                        client_order_id=tp_id,
                        kind="TP",
                        corr_id="bracket_health",
                        rid="bracket_health",
                    )
                self._symbol_brackets.setdefault(
                    symbol, {})["tp_order_id"] = tp_order_id
                placed = True
            except Exception as e:
                LOG.error(
                    f"[BRACKET-HEALTH] {symbol} TP placement failed: {e}")

        return placed

    async def _startup_order_guardian_reconcile(self) -> None:
        """
        Startup reconciliation: Link existing orders and positions for OrderGuardian.

        This ensures OrderGuardian has accurate tracking of existing orders/positions
        after restart, enabling proper orphan detection and cleanup.
        """
        try:
            LOG.info("🔄 Starting OrderGuardian startup reconciliation...")

            # ✅ FIX: First link existing orders from REST API for all symbols with positions
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
                        LOG.debug(f"✅ Linked existing orders for {symbol}")

                    LOG.info(
                        f"✅ Linked existing orders for {len(symbols_with_positions)} symbols")

                except Exception as e:
                    LOG.warning(
                        f"Failed to link existing orders during startup: {e}")

            # Then run cleanup to remove orphans
            await self.order_guardian.cleanup_orphans()
            LOG.info("✅ OrderGuardian startup reconciliation completed")
        except Exception as e:
            LOG.error(f"❌ OrderGuardian startup reconciliation failed: {e}")
