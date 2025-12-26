"""
FSMP-P1-T02: Orchestration of 3 FSM flows for execution_position domain.

This FSM acts as a wrapper, routing commands to the appropriate flow FSM
(Open, Manage, Close) on a per-symbol basis. It integrates directly with
the vFoundation BinanceAdapter to execute trades in the configured environment.
"""

from __future__ import annotations

import asyncio
from collections import deque
import logging
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple, Set, Coroutine
from pydantic import BaseModel

from vfoundation.core.fsm_emit_compat import Message, emit_compat
from vfoundation.dr import wal
from apps.reference.adapters.binance_adapter import BinanceAdapter, BinanceAPIError
from apps.reference.config_models import AuroraConfig
from apps.reference.utils.accessors import aget, dget

from .fsm_open import OpenFlowFSM
from .fsm_manage import ManageFlowFSM
from .fsm_close import CloseFlowFSM
from .exposure_guard import ExposureGuard
from .watchdog import OrderTimeoutWatchdog
from .utils_event_bus import LocalBus
from .utils import (
    quantize_stop_price,
    validate_anti_2021,
    generate_client_order_id,
    calc_tp_sl_from_mark,
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

# TASK50: Import qty normalizer for fail-closed quantity validation
from apps.reference.domains.execution_position.qty_normalizer import (
    normalize_qty,
    verify_ack_qty,
    NRR_QTY_ROUNDED_TO_ZERO,
    NRR_QTY_BELOW_MIN_QTY,
    NRR_NOTIONAL_BELOW_MIN,
)

# Import AlertManager for circuit breaker alerts
try:
    from apps.reference.telemetry.alerts import AlertManager
    ALERT_MANAGER_AVAILABLE = True
except ImportError:
    ALERT_MANAGER_AVAILABLE = False
    AlertManager = None  # type: ignore

LOG = logging.getLogger(__name__)


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

    def __init__(self, config: Optional[AuroraConfig], fsm, shadow_mode: bool = False):
        if isinstance(config, dict):
            raise TypeError("ExecPosFSM requires typed AuroraConfig, got dict")
        self.config = AuroraConfig() if config is None else config

        self.fsm = fsm
        self.shadow_mode = shadow_mode
        # BinanceExecutionAdapter or similar
        self.adapter: Optional[Any] = None

        self.open_flows: Dict[str, OpenFlowFSM] = {}
        self.manage_flows: Dict[str, ManageFlowFSM] = {}
        self.close_flows: Dict[str, CloseFlowFSM] = {}
        self._flows_lock = threading.Lock()  # EXP-FIX: Thread-safe flows access

        self.log_adapter = AuroraLogAdapter()
        self.metrics_collector = MetricsCollector()

        # Idempotent cancel helper - SSOT: domains.execution_position.idempotent_cancel (FAIL-CLOSED)
        self._idempotent_cancel_helper: Optional[IdempotentCancelHelper] = None
        self._idempotent_cancel_max_retries: Optional[int] = None
        try:
            idempotent_cfg = self.config.domains.execution_position.idempotent_cancel
            if idempotent_cfg is None or idempotent_cfg.max_retries is None:
                raise ValueError("idempotent_cancel.max_retries is required")
            self._idempotent_cancel_max_retries = int(idempotent_cfg.max_retries)
            self._idempotent_cancel_helper = IdempotentCancelHelper(logger_inst=LOG)
        except (AttributeError, TypeError) as e:
            raise ValueError(
                f"Failed to load idempotent_cancel config from domains.execution_position: {e}. "
                "Check domains.yaml has execution_position.idempotent_cancel.max_retries"
            ) from e

        # EXP-FIX: Initialize exposure guard
        self.exposure_guard = ExposureGuard(self.fsm, self.config)
        # EXP-FIX: Store latest portfolio state
        self._latest_portfolio_state: Dict[str, Any] = {}
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

        # Orphan-monitor configuration (additive, safe defaults)
        orphan_cfg = {}
        try:
            if self.config.trading and self.config.trading.execution and self.config.trading.execution.manage:
                orphan_cfg = self.config.trading.execution.manage.orphan_monitor or {}
        except Exception:
            orphan_cfg = {}

        if not isinstance(orphan_cfg, dict):
            orphan_cfg = {}

        # Safe extraction of orphan_monitor settings
        def get_orphan_setting(key: str, default):
            return orphan_cfg[key] if key in orphan_cfg else default

        self._orphan_cfg: Dict[str, Any] = {
            "enabled": bool(get_orphan_setting("enabled", True)),
            "run_on_startup": bool(get_orphan_setting("run_on_startup", True)),
            "periodic_interval_sec": int(get_orphan_setting("periodic_interval_sec", 300)),
            "min_order_age_sec": int(get_orphan_setting("min_order_age_sec", 0)),
            "batch_cancel_limit": int(get_orphan_setting("batch_cancel_limit", 50)),
            "rate_limit_per_min": int(get_orphan_setting("rate_limit_per_min", 120)),
        }
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
        self._guardian_unified: bool = bool(dget(self._guardian_cfg, "unified", True))
        self._guardian_emit_tidy_event: bool = bool(dget(self._guardian_cfg, "emit_tidy_event", True))
        self._guardian_poll_interval_ms: int = int(dget(self._guardian_cfg, "poll_interval_ms", 500))
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

        # Async loop used for guardian and adapter operations (set later)
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None

        # Initialize order timeout watchdog
        watchdog_config = self._get_config_value(["execution", "watchdog"])
        if not watchdog_config:
            watchdog_config = self._get_config_value(["trading", "execution", "watchdog"])
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
                default_ttl_seconds = aget(orders_cfg, "default_ttl_seconds", None) if orders_cfg else None
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
                raise ValueError("event_dedup config is required in domains.execution_position")
            dedup_max = event_dedup_cfg.max_size
            dedup_ttl = event_dedup_cfg.ttl_ms
        except (AttributeError, TypeError) as e:
            raise ValueError(
                f"Failed to load event_dedup config from domains.execution_position: {e}. "
                "Check domains.yaml has execution_position.event_dedup section."
            ) from e

        self._processed_events = BoundedEventDeduper(max_size=dedup_max, ttl_ms=dedup_ttl)

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
                    "✅ Watchdog REST polling hooks connected to adapter functions")
            # Initialize OrderGuardian for TP/SL cleanup with strict ownership tracking
            # Get poll_interval_ms from config
            poll_interval_ms = self._guardian_poll_interval_ms or 500
            try:
                # Try reading from execution.order_guardian.poll_interval_ms first
                og_cfg = self._get_config_value(["execution", "order_guardian"])
                if not og_cfg:
                    og_cfg = self._get_config_value(["trading", "execution", "order_guardian"])

                if og_cfg:
                    if isinstance(og_cfg, dict):
                        poll_interval_ms = int(dget(og_cfg, "poll_interval_ms", 500))
                    else:
                        poll_interval_ms = int(aget(og_cfg, "poll_interval_ms", 500))

                LOG.info(
                    f"OrderGuardian poll_interval_ms from config: {poll_interval_ms}")

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
            except Exception as e:
                LOG.error(f"Failed to initialize OrderGuardian: {e}")
                self.order_guardian = None
                self.watchdog.start()  # Start timeout watchdog
                self._schedule_fsm_cleanup_loop()
        else:
            # Initialize OrderGuardian even in shadow mode for cleanup operations
            # Default to 500ms polling even in shadow mode
            poll_interval_ms = self._guardian_poll_interval_ms or 500
            try:
                # Try reading from execution.order_guardian.poll_interval_ms first
                og_cfg = self._get_config_value(["execution", "order_guardian"])
                if not og_cfg:
                    og_cfg = self._get_config_value(["trading", "execution", "order_guardian"])

                if og_cfg:
                    if isinstance(og_cfg, dict):
                        poll_interval_ms = int(dget(og_cfg, "poll_interval_ms", 500))
                    else:
                        poll_interval_ms = int(aget(og_cfg, "poll_interval_ms", 500))
            except Exception:
                poll_interval_ms = 500

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

        # Subscribe to Guardian TIDY events to update gate state
        try:
            if hasattr(self, 'bus') and self.bus:
                self.bus.listen("EVT:SYMBOL_TIDY", self._on_symbol_tidy_event)
        except Exception:
            pass

    def _mark_processed_event(self, event_key: str) -> bool:
        """Idempotency helper with bounded memory."""
        if self._processed_events.seen(event_key):
            return False
        
        now_ms = int(time.time() * 1000)
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
        """Aggregate guardian config from active runtime sources."""
        resolved: Dict[str, Any] = {
            "unified": True,
            "emit_tidy_event": True,
            "poll_interval_ms": 500,
            "cleanup_ttl_ms": 6000,
            "symbol_cooldown_ms": 4000,
        }

        def _update_from(source: Any) -> None:
            if not source:
                return
            keys = ("unified", "emit_tidy_event", "poll_interval_ms",
                    "cleanup_ttl_ms", "symbol_cooldown_ms")
            if isinstance(source, dict):
                for key in keys:
                    if key in source and source[key] is not None:
                        resolved[key] = source[key]
            else:
                for key in keys:
                    value = aget(source, key, None)
                    if value is not None:
                        resolved[key] = value

        _update_from(self._get_config_value(["guardian"], default={}))
        _update_from(self._get_config_value(
            ["execution", "order_guardian"], default={}))
        _update_from(self._get_config_value(
            ["trading", "execution", "order_guardian"], default={}))

        try:
            resolved["poll_interval_ms"] = int(
                dget(resolved, "poll_interval_ms", 500))
        except Exception:
            resolved["poll_interval_ms"] = 500

        return resolved

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
        if isinstance(result, dict):
            status = str(result["status"] if "status" in result else "").upper()
            if status == "CANCELED":
                return True
            code = result.get("code")
            if code == -2011:
                return True
            msg = str(result["msg"] if "msg" in result else "").lower()
            if "unknown order" in msg:
                return True
        return False

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
                LOG.debug(f"IDEMPOTENT_CANCEL: helper failed, fallback to direct cancel: {e}")

        return await self.adapter.cancel_order(symbol, order_id)

    @staticmethod
    def _is_unknown_order_error(error: Exception) -> bool:
        """Detect -2011 or equivalent unknown order errors from adapter."""
        if isinstance(error, BinanceAPIError) and aget(error, "code", None) == -2011:
            return True
        message = str(error).lower()
        return "unknown order" in message

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
            if hasattr(self.fsm, "order_index") and self.fsm.order_index:  # type: ignore[attr-defined]
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
                    "timestamp_ms": int(time.time() * 1000)
                },
                why="exposure_summary_updated_after_portfolio_change",
            )
            loop = self._get_async_loop()
            if loop:
                self._submit_async(
                    emit_compat(self.fsm, exposure_msg, logger=LOG), loop
                )
        except Exception as e:
            LOG.debug(f"Failed to emit exposure summary update: {e}")

        # ✅ FIX: Check for position closures and trigger orphan cleanup
        # When position becomes 0, TP/SL orders become orphaned and need cleanup
        try:
            positions = self._latest_portfolio_state["positions"] if "positions" in self._latest_portfolio_state else []
            for pos in positions:
                symbol = pos.get("symbol")
                position_amt = float(pos["positionAmt"] if "positionAmt" in pos else 0)

                # Check if this position was previously non-zero but is now zero
                prev_position_amts = aget(self, "_prev_position_amts", {})
                prev_amt = prev_position_amts[symbol] if symbol in prev_position_amts else 0.0
                if abs(prev_amt) >= 1e-10 and abs(position_amt) < 1e-10:
                    LOG.info(
                        f"🔄 [POSITION_CLOSED] {symbol}: position closed (was {prev_amt}, now {position_amt}) - triggering orphan cleanup")
                    # Position closed - trigger immediate orphan cleanup for this symbol
                    if hasattr(self, 'order_guardian') and self.order_guardian:
                        loop = self._get_async_loop()
                        if loop:
                            self._submit_async(
                                self.order_guardian.reconcile_symbol(
                                    symbol, "portfolio_update"
                                ),
                                loop,
                            )

                # Update previous amounts for next comparison
                if not hasattr(self, '_prev_position_amts'):
                    self._prev_position_amts = {}
                self._prev_position_amts[symbol] = position_amt

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

        # TASK40: Mark entry order terminal in OrderIndex (unblocks one-open-order guard).
        try:
            if hasattr(self.fsm, "order_index") and self.fsm.order_index:  # type: ignore[attr-defined]
                ref = self.fsm.order_index.get(exchangeOrderId=str(order_id))  # type: ignore[attr-defined]
                if ref is not None:
                    self.fsm.order_index.mark_terminal(ref)  # type: ignore[attr-defined]
        except Exception:
            pass

        # PHASE A2 FIX: Inject cached intent data into ManageFlowFSM
        if rid in self._pending_intent_data:
            intent_data = self._pending_intent_data[rid]
            manage_flow = self.manage_flows.get(symbol)
            if manage_flow:
                LOG.info(f"INJECTING_INTENT_DATA for {symbol} (rid={rid}): {intent_data}")
                sl_price = intent_data.get("stop_price")
                tp_price = intent_data.get("target_price")
                # BUG FIX: Check for real value, not just truthy ("None" string is truthy!)
                sl_is_real = sl_price is not None and str(sl_price).strip().lower() != "none"
                tp_is_real = tp_price is not None and str(tp_price).strip().lower() != "none"
                if sl_is_real:
                    manage_flow.set_intent_prices(sl_price=sl_price, tp_price=tp_price if tp_is_real else None)
                    LOG.info(f"INTENT_PRICES_INJECTED for {symbol}: SL={sl_price}, TP={tp_price if tp_is_real else 'None'}")
                else:
                    LOG.debug(f"SKIP_INTENT_INJECTION for {symbol}: sl_price is None/invalid")
                
                # Cleanup cache after injection
                self._pending_intent_data.pop(rid, None)
            else:
                LOG.warning(f"Could not inject intent data: ManageFlow not found for {symbol}")

        # Create post-fill hold in exposure guard
        if hasattr(self, "exposure_guard"):
            postfill_key = f"postfill_{symbol}_{order_id}"
            self.exposure_guard.state.postfill_reservations[postfill_key] = {
                "symbol": symbol,
                "qty": filled_qty,
                "ts_ms": int(__import__('time').time() * 1000),
                "rid": rid,
            }
            LOG.debug(f"[FILL] Created postfill hold for {postfill_key}")

        # Best-effort cleanup of orphaned brackets in case this fill closed the position
        # Debounce: wait 500ms to allow TP/SL registration before cleanup
        loop = self._get_async_loop()
        if loop:
            async def delayed_cleanup():
                await asyncio.sleep(0.5)
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
                    "timestamp_ms": int(time.time() * 1000)
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
            # EXP-FIX: Fail-closed exposure check before processing CMD:OPEN
            exposure_err = self._check_exposure_fail_closed(msg)
            if exposure_err is not None:
                return exposure_err
            result = open_flow.handle(msg)
            
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
                            "timestamp": time.time()
                        }
                        self._pending_intent_data[result.rid] = intent_data
                        LOG.info(f"CAPTURED_INTENT_DATA for {result.rid}: {intent_data}")
                    else:
                        LOG.debug(f"SKIP_INTENT_CACHE for {result.rid}: all values are None")
                except Exception as e:
                    LOG.error(f"Failed to capture intent data: {e}")
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
                    manage._closing_position_ts = time.time()
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
                messages = batch_pld["messages"] if "messages" in batch_pld else []
                for msg_data in messages:
                    if isinstance(msg_data, dict):
                        # Reconstruct Message from dict
                        try:
                            sub_msg = Message(**msg_data)
                        except Exception as e:
                            LOG.error(f"Failed to reconstruct BATCH message: {e}")
                            continue
                    else:
                        sub_msg = msg_data
                    
                    wal.append(sub_msg.model_dump())
                    if (not self.shadow_mode and self.adapter) or (sub_msg.verb == "CLOSE" and self.adapter):
                        loop = self._get_async_loop()
                        if loop:
                            self._submit_async(self._execute_decision(sub_msg), loop)
            else:
                wal.append(result.model_dump())
                # ✅ FIX: Execute CLOSE decisions even in shadow mode to cancel brackets
                if (not self.shadow_mode and self.adapter) or (result.verb == "CLOSE" and self.adapter):
                    # Asynchronously execute the trade decision
                    loop = self._get_async_loop()
                    LOG.info(f"🔄 ExecPosFSM: DEC:{result.verb} ready to execute, loop={loop is not None}, shadow_mode={self.shadow_mode}, adapter={self.adapter is not None}")
                    if loop:
                        self._submit_async(self._execute_decision(result), loop)
                    else:
                        LOG.error(f"❌ ExecPosFSM: No async loop available for DEC:{result.verb}! Order will NOT be executed!")
                else:
                    LOG.info(f"⏭️ ExecPosFSM: Skipping execution for DEC:{result.verb} (shadow_mode={self.shadow_mode}, adapter={self.adapter is not None})")

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
            if decision.verb == "CLOSE":
                pld = decision.pld or {}
                symbol = pld.get("symbol")
                if not symbol:
                    LOG.error("DEC:CLOSE missing symbol; cannot execute")
                    return

                # PHASE A2: Set closing flag to prevent bracket placement race condition
                manage = self.manage_flows.get(symbol)
                if manage:
                    manage._closing_position = True
                    manage._closing_position_ts = time.time()
                    LOG.info(
                        f"🔒 [PHASE A2] Set closing flag for {symbol} to prevent bracket race")

                # Cancel tracked brackets
                br = self._symbol_brackets[symbol] if symbol in self._symbol_brackets else {}
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
                                    "timestamp": int(time.time() * 1000)
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
                                    "timestamp": int(time.time() * 1000)
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
                                    "timestamp": int(time.time() * 1000)
                                })
                            else:
                                cancel_status = str(result["status"] if "status" in result else "").upper()
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
                                    "timestamp": int(time.time() * 1000)
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
                        amt = float(pos["positionAmt"] if "positionAmt" in pos else 0)
                    except Exception:
                        amt = 0.0
                if abs(amt) < 1e-10:
                    LOG.info(f"No open position to close for {symbol}")
                    self._symbol_brackets.pop(symbol, None)
                    return
                close_side = "SELL" if amt > 0 else "BUY"
                close_qty = str(abs(Decimal(str(amt))))
                close_id = generate_client_order_id("CLOSE", symbol)
                await self.adapter.place_market_reduce_only(symbol, close_side, close_qty, new_client_order_id=close_id)
                LOG.info(
                    f"Close executed for {symbol}: side={close_side} qty={close_qty}")
                self._symbol_brackets.pop(symbol, None)

                # ✅ PHASE A1: Ensure cleanup after manual CLOSE
                # Wait for position to settle, then cleanup any orphaned brackets
                await asyncio.sleep(2.0)

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
                                    status = str(result["status"] if "status" in result else "").upper()
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
                close_elapsed_ms = int((datetime.utcnow(
                ) - decision.timestamp_utc).total_seconds() * 1000) if decision.timestamp_utc else 0
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
                
                LOG.info(f"Executing PLACE_ORDER: {symbol} {side} {order_type} {qty} @ {price}/{stop_price}")
                
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
                             LOG.error(f"Unsupported order type for PLACE_ORDER: {order_type}")
                             return

                    LOG.info(f"✅ PLACE_ORDER success: {resp}")

                    # ORDER_INDEX: correlate bracket/aux orders for WS updates
                    try:
                        if (
                            client_id
                            and resp
                            and hasattr(self.fsm, "order_index")
                            and self.fsm.order_index  # type: ignore[attr-defined]
                        ):
                            idem_key = (
                                (decision.pld or {}).get("idempotent_key")
                                or getattr(decision, "idempotent_key", None)
                                or decision.rid
                                or rid
                                or client_id
                            )
                            ex_order_id = str(resp.get("orderId"))
                            self.fsm.order_index.upsert_from_open(  # type: ignore[attr-defined]
                                rid=rid or decision.rid or ex_order_id,
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
                            self._symbol_brackets.setdefault(symbol, {})["sl_order_id"] = order_id
                        elif "_tp" in client_id:
                            self._symbol_brackets.setdefault(symbol, {})["tp_order_id"] = order_id
                        
                        # 🔥 CRITICAL: Sync with ManageFlowFSM
                        manage_flow = self.manage_flows.get(symbol)
                        if manage_flow:
                            brackets = self._symbol_brackets[symbol] if symbol in self._symbol_brackets else {}
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

            # TP/SL extraction (FAIL-CLOSED: per-symbol sl_pct from aurora.yaml)
            # SSOT: strategies.aurora.assets.<SYMBOL>.exit.sl_pct (NOT brackets.fixed_bps!)
            sl_pct: Optional[float] = None
            tp_low_ratio: Optional[float] = None
            tp_high_ratio: Optional[float] = None
            
            try:
                aurora = getattr(self.config.strategies, "aurora", None)
                if aurora is None:
                    raise ValueError(f"strategies.aurora not configured")
                
                instr_cfg = aurora.assets.get(symbol)
                if instr_cfg is None:
                    raise ValueError(f"strategies.aurora.assets.{symbol} not configured")
                
                # Extract exit config (FAIL-CLOSED: must exist)
                exit_cfg = getattr(instr_cfg, "exit", None)
                if exit_cfg is None or exit_cfg.sl_pct is None:
                    raise ValueError(
                        f"strategies.aurora.assets.{symbol}.exit.sl_pct is required"
                    )
                sl_pct = exit_cfg.sl_pct
                
                # Extract take_profit config (FAIL-CLOSED: must exist)
                tp_cfg = getattr(instr_cfg, "take_profit", None)
                if tp_cfg is None or tp_cfg.tp_low_ratio is None:
                    raise ValueError(
                        f"strategies.aurora.assets.{symbol}.take_profit.tp_low_ratio is required"
                    )
                tp_low_ratio = tp_cfg.tp_low_ratio
                tp_high_ratio = getattr(tp_cfg, "tp_high_ratio", None)
                
                LOG.debug(
                    f"[{symbol}] PER_SYMBOL_CONFIG_LOADED: sl_pct={sl_pct}, "
                    f"tp_low_ratio={tp_low_ratio}, tp_high_ratio={tp_high_ratio} "
                    f"(source=strategies.aurora.assets.{symbol})"
                )
            except (ValueError, AttributeError) as cfg_err:
                # FAIL-CLOSED: Missing per-symbol config = reject order
                LOG.error(
                    f"❌ [{symbol}] PER_SYMBOL_CONFIG_MISSING: {cfg_err}. "
                    "Order rejected - cannot calculate TP/SL without per-symbol config."
                )
                order_logger.write({
                    "rid": decision.rid,
                    "event_type": "ORDER_REJECTED",
                    "symbol": symbol,
                    "side": side,
                    "quantity": str(raw_qty),
                    "nrr_code": "NRR-BRACKETS-CONFIG-MISSING",
                    "why": str(cfg_err),
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
                        "raw_qty": str(raw_qty),
                        "reason": "NRR-BRACKETS-CONFIG-MISSING",
                        "details": str(cfg_err),
                    },
                    why="NRR-BRACKETS-CONFIG-MISSING",
                )
                await emit_compat(self.fsm, reject_msg, logger=LOG)
                return

            # Calculate SL/TP from per-symbol sl_pct (NOT global bps!)
            # sl_pct is percentage (0.019 = 1.9%), tp_low_ratio is multiplier on SL distance
            mark_dec = Decimal(str(mark))
            sl_pct_dec = Decimal(str(sl_pct))
            tp_low_ratio_dec = Decimal(str(tp_low_ratio))
            
            if side == "BUY":
                # LONG: SL below entry, TP above
                sl = mark_dec * (Decimal("1") - sl_pct_dec)
                tp = mark_dec * (Decimal("1") + sl_pct_dec * tp_low_ratio_dec)
            else:
                # SHORT: SL above entry, TP below
                sl = mark_dec * (Decimal("1") + sl_pct_dec)
                tp = mark_dec * (Decimal("1") - sl_pct_dec * tp_low_ratio_dec)
            
            LOG.info(
                f"[{symbol}] TP/SL_CALCULATED: mark={mark}, sl_pct={sl_pct}, "
                f"tp_low_ratio={tp_low_ratio} → SL={sl}, TP={tp}"
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

            # Place MARKET entry
            entry_id = generate_client_order_id("ENTRY", symbol)
            entry_resp = await self.adapter.place_market_entry(
                symbol, side, qty, entry_id
            )
            LOG.info(f"✅ MARKET entry placed: {entry_resp}")

            # ORDER_INDEX: correlate entry order for WS updates
            try:
                if hasattr(self.fsm, "order_index") and self.fsm.order_index:  # type: ignore[attr-defined]
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
            self.watchdog.track_order_placed(
                order_id=entry_order_id,
                client_order_id=entry_id,
                symbol=symbol,
                corr_id=decision.corr_id,
                rid=decision.rid
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

            # ✅ PHASE A3: Pre-flight check before placing TP/SL (with retry for REST lag)
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
            sl_id = generate_client_order_id("SL", symbol)
            tp_side = opposite_side(side)
            tp_id = generate_client_order_id("TP", symbol)

            # ✅ Place SL and TP in parallel (not sequentially)
            sl_resp = None
            tp_resp = None
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

                            # Retry with widened TP
                            tp_adj = tp * 1.002  # +20 bps approx
                            tp_adj = quantize_stop_price(
                                tp_adj, tick_size, side="BUY" if side == "BUY" else "SELL"
                            )
                            self.metrics_collector.record_retry(
                                "tp_adjust") if self.metrics_collector else None

                            # Exponential backoff: 200ms first retry
                            await asyncio.sleep(0.2)

                            try:
                                return await self.adapter.place_take_profit_market_close_position(
                                    symbol, tp_side, str(tp_adj), new_client_order_id=tp_id
                                )
                            except BinanceAPIError as e2:
                                if e2.code == -2021:
                                    # Second retry: 400ms backoff
                                    LOG.warning(
                                        f"⚠️ [PHASE A3] TP -2021 retry 2, backoff 400ms for {symbol}")
                                    await asyncio.sleep(0.4)

                                    tp_adj2 = tp * 1.005  # +50 bps
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
                        tp_adj = tp * 1.002
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
                brackets = self._symbol_brackets[symbol] if symbol in self._symbol_brackets else {}
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
            }
            # Flat fields for quick access in /metrics JSON
            all_metrics["gate_entry_blocked_tidy"] = gate_blocked
            all_metrics["gate_entry_allowed_tidy"] = gate_allowed
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
            }
            all_metrics["gate_entry_blocked_tidy"] = 0
            all_metrics["gate_entry_allowed_tidy"] = 0
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
                self._symbol_last_tidy_ts[symbol] = time.time()
                LOG.info(f"[GATE] tidy_event: symbol={symbol}")
        except Exception:
            pass

    def _entry_tidy_gate_allow(self, symbol: str) -> bool:
        """Return True if new ENTRY is allowed under SYMBOL_TIDY gate."""
        # Read flag
        try:
            allow_gate = bool(
                aget(self.config.execution, "allow_trade_with_guardian_tidy_only", False)
            ) if self.config.execution else False
        except Exception:
            allow_gate = False

        if not allow_gate:
            return True

        # TTL and cooldown
        ttl_ms = int(dget(self._guardian_cfg, "cleanup_ttl_ms", 6000))
        cooldown_ms = int(dget(self._guardian_cfg, "symbol_cooldown_ms", 4000))

        now = time.time()
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
                        "timestamp": int(time.time() * 1000)
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
                        "timestamp": int(time.time() * 1000)
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
                        "timestamp": int(time.time() * 1000)
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
                        "timestamp": int(time.time() * 1000)
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

        side_raw = pld.get("side")
        side = str(side_raw).upper() if side_raw is not None else "BUY"
        if side not in {"BUY", "SELL", "LONG", "SHORT"}:
            side = "BUY"

        if not symbol or not qty or not price_ref:
            LOG.warning(
                f"EXPOSURE_CHECK_SKIP: Missing required fields for {symbol}")
            return None

        try:
            # Calculate notional
            notional_abs = Decimal(str(qty)) * Decimal(str(price_ref))
            notional_signed = -notional_abs if side in {"SELL", "SHORT"} else notional_abs

            reduce_only = bool(pld.get("reduce_only", False))
            reserve_key = pld.get("idempotent_key") or msg.rid or f"rid_{msg.rid}"

            # Check exposure with fail-closed logic
            exposure_check = self.exposure_guard.can_open(
                symbol, notional_signed, self._latest_portfolio_state
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

            # EXP-FIX: Periodic shadow notional check (every 10 requests approx)
            self._shadow_check_counter += 1

            if self._shadow_check_counter % 10 == 0 and self.adapter:
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
                LOG.warning(f"Failed to write ERR:OPEN(EXPOSURE_CHECK_ERROR) to WAL: {wal_e}")

            return error_msg

    async def _emit_error_async(self, msg: Message) -> None:
        """Asynchronously emit an error message."""
        try:
            await emit_compat(self.fsm, msg, logger=aget(self, "logger", None))
        except Exception as e:
            # Не даємо Task впасти "unretrieved" — лог і поглинання
            LOG.exception(
                "Failed to emit error message via emit_compat: %r", e)

    def _handle_fill_event(self, msg: Message) -> None:
        """
        EXP-FIX: Handle order fill events for post-fill hold mechanism.

        Moves reservation from pending to post-fill hold to prevent race conditions.
        """
        pld = msg.pld or {}
        reserve_key = pld.get("idempotent_key") or pld.get(
            "client_order_id") or msg.rid

        if not reserve_key:
            LOG.warning("FILL_EVENT_SKIP: No reserve_key found in fill event")
            return

        # Calculate filled notional (approximate)
        qty = pld["qty"] if "qty" in pld else 0
        price = pld["price"] if "price" in pld else 0
        try:
            notional_usd = Decimal(str(qty)) * Decimal(str(price))
            fill_symbol = pld.get("symbol")
            if not fill_symbol:
                fill_symbol = (
                    self.exposure_guard.state.pending_exposure.get(reserve_key, {}).get("symbol")
                    if hasattr(self.exposure_guard, "state") and hasattr(self.exposure_guard.state, "pending_exposure")
                    else None
                )
            fill_symbol = str(fill_symbol or "UNKNOWN")

            fill_side_raw = pld.get("side")
            fill_side = str(fill_side_raw).upper() if fill_side_raw is not None else "UNKNOWN"
            if fill_side == "UNKNOWN":
                fill_side = (
                    str(self.exposure_guard.state.pending_exposure.get(reserve_key, {}).get("side") or "UNKNOWN").upper()
                    if hasattr(self.exposure_guard, "state") and hasattr(self.exposure_guard.state, "pending_exposure")
                    else "UNKNOWN"
                )

            self.exposure_guard.on_fill(reserve_key, notional_usd, symbol=fill_symbol, side=fill_side)

            # EXP-FIX: Record post-fill hold metric
            if hasattr(self, "metrics_collector") and self.metrics_collector:
                self.metrics_collector.record_postfill_hold(
                    len(self.exposure_guard.state.postfill_reservations)
                )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": pld["rid"] if "rid" in pld else f"fill_{reserve_key}",
                "event_type": "ORDER_STATE_CHANGED",
                "symbol": fill_symbol,
                "side": fill_side,
                "quantity": float(qty),
                "price": float(price),
                "client_order_id": pld["client_order_id"] if "client_order_id" in pld else "",
                "order_id": pld["order_id"] if "order_id" in pld else "",
                "source_fsm": "ExecPosFSM",
                "reservation_id": reserve_key,
                "metadata": {"fill_status": "FILLED", "notional_usd": float(notional_usd)}
            })

            LOG.debug(
                f"FILL_HANDLED: key={reserve_key}, notional={notional_usd}")
        except Exception as e:
            LOG.error(f"FILL_HANDLE_ERROR: {e}", exc_info=True)

        # ✅ EVT:EXPOSURE_SUMMARY_UPDATED: Emit exposure summary after fill
        try:
            exposure_summary = self.exposure_guard.get_exposure_summary()
            exposure_msg = Message(
                op="EVT",
                verb="EXPOSURE_SUMMARY_UPDATED",
                src="execution_position",
                dst="decision_making",
                rid=pld.get("rid") or msg.rid or f"fill_{reserve_key}",
                pld={
                    "exposure_summary": exposure_summary,
                    "fill_order_id": pld.get("order_id"),
                    "fill_symbol": pld.get("symbol"),
                    "fill_quantity": qty,
                    "timestamp_ms": int(time.time() * 1000)
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

        # Notify watchdog of order fill
        order_id = pld.get("order_id")
        if order_id:
            self.watchdog.ensure_started()  # Safe late-start if needed
            self.watchdog.on_order_fill(order_id)

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

        # TASK40: Mark order terminal in OrderIndex (unblocks one-open-order guard).
        try:
            if hasattr(self.fsm, "order_index") and self.fsm.order_index:  # type: ignore[attr-defined]
                ref = None
                if order_id:
                    ref = self.fsm.order_index.get(exchangeOrderId=str(order_id))  # type: ignore[attr-defined]
                if ref is None and client_order_id:
                    ref = self.fsm.order_index.get(clientOrderId=str(client_order_id))  # type: ignore[attr-defined]
                if ref is not None:
                    self.fsm.order_index.mark_terminal(ref)  # type: ignore[attr-defined]
        except Exception:
            pass

        # Emit exposure summary update after cancellation
        try:
            from vfoundation import emit_compat
            from vfoundation.message import Message

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
                    "timestamp": int(time.time() * 1000)
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

            # Get shadow notional from exchange
            shadow_notional = await self.adapter.get_positions_notional_usd_shadow()

            # Get portfolio notional
            portfolio_notional = Decimal(
                str(self._latest_portfolio_state["open_positions_usd"] if "open_positions_usd" in self._latest_portfolio_state else "0")
            )

            # Compare with tolerance (allow 1% difference)
            tolerance = 0.01
            diff_pct = (
                abs(shadow_notional - float(portfolio_notional))
                / max(shadow_notional, float(portfolio_notional), 1)
                * 100
            )

            if diff_pct > tolerance:
                LOG.warning(
                    f"EXPOSURE_MISMATCH: portfolio={portfolio_notional}, shadow={shadow_notional}, diff={diff_pct:.2f}%"
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
        exec_cfg = getattr(exec_cfg, "execution", None) if exec_cfg is not None else None
        backoff_ms = getattr(exec_cfg, "preflight_backoff_ms", None) if exec_cfg is not None else None
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
        start = time.time()

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

                elapsed_ms = int((time.time() - start) * 1000)
                LOG.info(
                    f"[BRK] preflight positionRisk posAmt={position_amt} try={tries} elapsed={elapsed_ms}ms")

                # Position found!
                if abs(position_amt) >= 1e-10:
                    LOG.info(f"[BRK] preflight DECISION=allow (pos!=0)")
                    return True

                # Exhausted retries
                if tries > len(backoff_ms):
                    LOG.warning(
                        f"🚫 [PHASE A3] PRE-FLIGHT SKIPPED: Position is 0 for {symbol} after {tries} tries (TP_SL_SKIPPED_NO_POSITION)")
                    self._orphan_metrics["tp_sl_skipped_no_position"] += 1
                    return False

                # Wait before next retry
                await asyncio.sleep(backoff_ms[tries - 1] / 1000.0)

            except Exception as e:
                LOG.warning(
                    f"⚠️ [PHASE A3] PRE-FLIGHT ERROR for {symbol} (try {tries}): {e}")
                if tries > len(backoff_ms):
                    return False
                await asyncio.sleep(backoff_ms[tries - 1] / 1000.0)

    async def _cleanup_loop(self) -> None:
        """Periodic orphaned-order cleanup loop (interval from config)."""
        while True:
            try:
                interval = max(
                    5, int(self._orphan_cfg["periodic_interval_sec"]))
                await asyncio.sleep(interval)
                await self.order_guardian.cleanup_orphans()
                self._orphan_metrics["loops"] += 1
            except asyncio.CancelledError:
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
