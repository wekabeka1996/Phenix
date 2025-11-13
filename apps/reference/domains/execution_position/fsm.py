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
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Optional, Tuple, Set, Coroutine

from vfoundation.core.fsm_emit_compat import Message, emit_compat
from vfoundation.dr import wal
from apps.reference.adapters.binance_adapter import BinanceAdapter, BinanceAPIError
from vfoundation.services.price_service import PriceService, PriceServiceSync

from .fsm_open import OpenFlowFSM
from .fsm_manage import ManageFlowFSM
from .fsm_close import CloseFlowFSM
from .exposure_guard import ExposureGuard
from .watchdog import OrderTimeoutWatchdog
from .utils import (
    quantize_stop_price,
    validate_anti_2021,
    generate_client_order_id,
    calc_tp_sl_from_mark,
    validate_not_immediate,
    opposite_side,
)
from .aurora_log_adapter import AuroraLogAdapter
from .metrics_collector import MetricsCollector
from apps.reference.telemetry.order_logger import order_logger
from .utils import quantize_stop_price, validate_anti_2021, generate_client_order_id
from vfoundation.obs.correlation import CorrelationStore
from .utils_event_bus import LocalBus

# Import OrderGuardian for TP/SL cleanup
from apps.reference.domains.execution_position.order_guardian import OrderGuardian

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

    def __init__(self, config: Dict[str, Any], fsm, shadow_mode: bool = False):
        self.config = config
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

        # EXP-FIX: Initialize exposure guard
        self.exposure_guard = ExposureGuard(self.config, fsm=self.fsm)
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

        # Orphan-monitor configuration (additive, safe defaults)
        try:
            # Try Pydantic access first
            if hasattr(self.config, 'trading') and self.config.trading:
                manage_cfg = self.config.trading.execution.manage if self.config.trading.execution else None
            elif isinstance(self.config, dict):
                manage_cfg = (
                    self.config.get("trading", {})
                    .get("execution", {})
                    .get("manage", {})
                )
            else:
                manage_cfg = None
        except (AttributeError, TypeError):
            manage_cfg = None

        # Get orphan_monitor config
        orphan_cfg = None
        if manage_cfg:
            if hasattr(manage_cfg, 'orphan_monitor'):
                orphan_cfg = manage_cfg.orphan_monitor
            elif isinstance(manage_cfg, dict):
                orphan_cfg = manage_cfg.get("orphan_monitor", {})

        if orphan_cfg is None:
            orphan_cfg = {}

        # Safe extraction of orphan_monitor settings
        def get_orphan_setting(key: str, default):
            if isinstance(orphan_cfg, dict):
                return orphan_cfg.get(key, default)
            elif hasattr(orphan_cfg, key):
                return getattr(orphan_cfg, key, default)
            else:
                return default

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
        self._guardian_unified: bool = bool(
            self._guardian_cfg.get("unified", True))
        self._guardian_emit_tidy_event: bool = bool(
            self._guardian_cfg.get("emit_tidy_event", True))
        self._guardian_poll_interval_ms: int = int(
            self._guardian_cfg.get("poll_interval_ms", 500))
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
        # FIX-TRADEEXEC-1: Single event path for FILL events - listen to TRADE_EXECUTED from FSMCore
        # This ensures ExposureGuard.on_fill is called for all fills (WS + REST polling + AccountObserver)
        self.bus.listen("EVT:TRADE_EXECUTED", self._on_trade_executed)
        # Support both 'ORDER_FILL' and legacy 'FILL' event verbs (legacy path for backward compatibility)
        self.bus.listen("EVT:ORDER_FILL", self._on_order_fill)
        self.bus.listen("EVT:FILL", self._on_order_fill)

        # Async loop used for guardian and adapter operations (set later)
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None

        # Initialize order timeout watchdog
        try:
            # Try Pydantic access first
            if hasattr(self.config, 'execution') and self.config.execution:
                watchdog_config = self.config.execution.watchdog
            elif isinstance(self.config, dict):
                watchdog_config = self.config.get(
                    "execution", {}).get("watchdog", {})
            else:
                watchdog_config = None
        except (AttributeError, TypeError):
            watchdog_config = None

        # Fallback to trading.watchdog if execution.watchdog is not available
        if watchdog_config is None or not watchdog_config:
            try:
                if hasattr(self.config, 'trading') and self.config.trading:
                    watchdog_config = self.config.trading.watchdog
                elif isinstance(self.config, dict):
                    watchdog_config = self.config.get(
                        "trading", {}).get("watchdog", {})
            except (AttributeError, TypeError):
                watchdog_config = {}

        if watchdog_config is None:
            watchdog_config = {}

        # Safe extraction of watchdog settings
        def get_watchdog_setting(key: str, default):
            if isinstance(watchdog_config, dict):
                return watchdog_config.get(key, default)
            elif hasattr(watchdog_config, key):
                return getattr(watchdog_config, key, default)
            else:
                return default

        ack_ttl_ms: int = int(get_watchdog_setting("ack_ttl_ms", 8000))
        fill_ttl_ms: int = int(get_watchdog_setting("fill_ttl_ms", 30000))

        # Log TTL configuration source and values
        ttl_source = "execution.watchdog"
        if watchdog_config is None or not watchdog_config:
            ttl_source = "trading.watchdog"
        elif hasattr(self.config, 'trading') and self.config.trading and hasattr(self.config.trading, 'orders') and self.config.trading.orders:
            # Check if override was applied
            try:
                orders_cfg = None
                if hasattr(self.config, 'trading') and self.config.trading:
                    tr = self.config.trading if isinstance(
                        self.config.trading, dict) else self.config.trading
                    orders_cfg = tr.get("orders") if isinstance(
                        tr, dict) else getattr(tr, "orders", None)
                if orders_cfg:
                    default_ttl_seconds = None
                    if isinstance(orders_cfg, dict):
                        default_ttl_seconds = orders_cfg.get(
                            "default_ttl_seconds")
                    else:
                        default_ttl_seconds = getattr(
                            orders_cfg, "default_ttl_seconds", None)
                    if default_ttl_seconds is not None:
                        ttl_source = "trading.orders.default_ttl_seconds"
            except Exception:
                pass

        LOG.info(
            f"ExecPosFSM TTL config: ack_ttl_ms={ack_ttl_ms}, fill_ttl_ms={fill_ttl_ms}, source={ttl_source}")

        # Optional override from trading.orders.default_ttl_seconds (Balanced profile)
        try:
            orders_cfg = None
            if hasattr(self.config, 'trading') and self.config.trading:
                tr = self.config.trading if isinstance(
                    self.config.trading, dict) else self.config.trading
                orders_cfg = tr.get("orders") if isinstance(
                    tr, dict) else getattr(tr, "orders", None)
            elif isinstance(self.config, dict):
                orders_cfg = self.config.get("orders") or self.config.get(
                    "trading", {}).get("orders")

            if orders_cfg:
                default_ttl_seconds = None
                if isinstance(orders_cfg, dict):
                    default_ttl_seconds = orders_cfg.get("default_ttl_seconds")
                else:
                    default_ttl_seconds = getattr(
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
        self._processed_events: Set[str] = set()

        # Initialize AlertManager for circuit breaker alerts
        self.alert_manager: Optional[AlertManager] = None
        if ALERT_MANAGER_AVAILABLE:
            try:
                self.alert_manager = AlertManager(
                    config=config, logger=getattr(self, 'logger', LOG).getChild("alerts"))
                LOG.info("AlertManager initialized in ExecPosFSM")
            except Exception as e:
                LOG.warning(
                    f"Failed to initialize AlertManager in ExecPosFSM: {e}")

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
                if hasattr(self.config, 'execution') and self.config.execution:
                    exec_cfg = self.config.execution
                    if hasattr(exec_cfg, 'order_guardian') and isinstance(exec_cfg.order_guardian, dict):
                        poll_interval_ms = exec_cfg.order_guardian.get(
                            'poll_interval_ms', 500)
                    elif isinstance(exec_cfg, dict) and 'order_guardian' in exec_cfg:
                        poll_interval_ms = exec_cfg['order_guardian'].get(
                            'poll_interval_ms', 500)
                elif isinstance(self.config, dict):
                    poll_interval_ms = self.config.get('execution', {}).get(
                        'order_guardian', {}).get('poll_interval_ms', 500)

                # If still default, try trading.execution.order_guardian.poll_interval_ms
                if poll_interval_ms == 500:
                    if hasattr(self.config, 'trading') and self.config.trading:
                        exec_cfg = self.config.trading.execution if self.config.trading.execution else {}
                        if isinstance(exec_cfg, dict) and 'order_guardian' in exec_cfg:
                            poll_interval_ms = exec_cfg['order_guardian'].get(
                                'poll_interval_ms', 500)
                    elif isinstance(self.config, dict):
                        poll_interval_ms = self.config.get('trading', {}).get(
                            'execution', {}).get('order_guardian', {}).get('poll_interval_ms', 500)

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
                if hasattr(self.config, 'execution') and self.config.execution:
                    exec_cfg = self.config.execution
                    if hasattr(exec_cfg, 'order_guardian') and isinstance(exec_cfg.order_guardian, dict):
                        poll_interval_ms = exec_cfg.order_guardian.get(
                            'poll_interval_ms', 500)
                    elif isinstance(exec_cfg, dict) and 'order_guardian' in exec_cfg:
                        poll_interval_ms = exec_cfg['order_guardian'].get(
                            'poll_interval_ms', 500)
                elif isinstance(self.config, dict):
                    poll_interval_ms = self.config.get('execution', {}).get(
                        'order_guardian', {}).get('poll_interval_ms', 500)

                # If still default, try trading.execution.order_guardian.poll_interval_ms
                if poll_interval_ms == 500:
                    if hasattr(self.config, 'trading') and self.config.trading:
                        exec_cfg = self.config.trading.execution if self.config.trading.execution else {}
                        if isinstance(exec_cfg, dict) and 'order_guardian' in exec_cfg:
                            poll_interval_ms = exec_cfg['order_guardian'].get(
                                'poll_interval_ms', 500)
                    elif isinstance(self.config, dict):
                        poll_interval_ms = self.config.get('trading', {}).get(
                            'execution', {}).get('order_guardian', {}).get('poll_interval_ms', 500)
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
                    node = getattr(node, key, None)
            except Exception:
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
                    try:
                        value = getattr(source, key, None)
                    except Exception:
                        value = None
                    if value is not None:
                        resolved[key] = value

        _update_from(self._get_config_value(["guardian"], default={}))
        _update_from(self._get_config_value(
            ["execution", "order_guardian"], default={}))
        _update_from(self._get_config_value(
            ["trading", "execution", "order_guardian"], default={}))

        try:
            resolved["poll_interval_ms"] = int(
                resolved.get("poll_interval_ms", 500))
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
            # Fallback to get_event_loop for test environments or thread-based loops
            try:
                return asyncio.get_event_loop()
            except Exception:
                return None

    async def _call_adapter_fn(self, fn_or_callable, *args, **kwargs):
        """Call an adapter function, supporting both sync and async implementations.

        fn_or_callable may be a bound function or a function name on the adapter.
        """
        if not self.adapter:
            return None
        # Resolve attribute if a string passed
        f = fn_or_callable
        if isinstance(fn_or_callable, str):
            f = getattr(self.adapter, fn_or_callable, None)
        if f is None or not callable(f):
            return None
        try:
            if asyncio.iscoroutinefunction(f):
                return await f(*args, **kwargs)
            else:
                result = f(*args, **kwargs)
                # If it returned a coroutine (some wrappers), await it
                if asyncio.iscoroutine(result):
                    return await result
                return result
        except Exception:
            raise

    def _submit_async(
        self,
        maybe_coro_or_fn: Any,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        """Schedule coroutine on a target loop, thread-safe."""
        target_loop = loop or self._get_async_loop()
        if not target_loop:
            LOG.debug("No asyncio loop available to schedule %r",
                      maybe_coro_or_fn)
            # If caller passed a coroutine object, ensure we close it to avoid
            # 'coroutine was never awaited' RuntimeWarning in tests where loop
            # isn't available or scheduling is deferred.
            try:
                if asyncio.iscoroutine(maybe_coro_or_fn):
                    maybe_coro_or_fn.close()
            except Exception:
                pass
            return

        try:
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None

            scheduled = False
            coro_obj = None

            # If we're on the same loop, use create_task
            if running_loop is target_loop:
                coro_obj = maybe_coro_or_fn() if callable(
                    maybe_coro_or_fn) else maybe_coro_or_fn
                try:
                    target_loop.create_task(coro_obj)
                    scheduled = True
                except Exception:
                    try:
                        if asyncio.iscoroutine(coro_obj):
                            coro_obj.close()
                    except Exception:
                        pass
            elif hasattr(target_loop, "create_task") and not hasattr(target_loop, "call_soon_threadsafe"):
                # Lightweight loop with only create_task (dummy loop in tests)
                try:
                    coro_obj = maybe_coro_or_fn() if callable(
                        maybe_coro_or_fn) else maybe_coro_or_fn
                    target_loop.create_task(coro_obj)
                    scheduled = True
                except Exception:
                    try:
                        if asyncio.iscoroutine(coro_obj):
                            coro_obj.close()
                    except Exception:
                        pass
                    LOG.debug(
                        "Dummy loop create_task failed; skipping schedule")
            else:
                # Use thread-safe scheduling for real loops
                try:
                    coro_obj = maybe_coro_or_fn() if callable(
                        maybe_coro_or_fn) else maybe_coro_or_fn
                    asyncio.run_coroutine_threadsafe(coro_obj, target_loop)
                    scheduled = True
                except RuntimeError as e:
                    LOG.debug(
                        "Target loop closed when scheduling coroutine: %s", e)
                    try:
                        running_loop = asyncio.get_running_loop()
                        if hasattr(running_loop, 'create_task'):
                            coro_obj = maybe_coro_or_fn() if callable(
                                maybe_coro_or_fn) else maybe_coro_or_fn
                            running_loop.create_task(coro_obj)
                            scheduled = True
                            return
                    except RuntimeError:
                        pass
                    try:
                        if asyncio.iscoroutine(coro_obj):
                            coro_obj.close()
                    except Exception:
                        pass
                    LOG.debug(
                        "Could not schedule coroutine due to closed loop; skipping: %r", maybe_coro_or_fn)
        finally:
            try:
                if coro_obj is not None and asyncio.iscoroutine(coro_obj) and not scheduled:
                    coro_obj.close()
            except Exception:
                pass

    def _schedule_guardian_start(self) -> None:
        """Ensure guardian poller and startup reconcile are scheduled once."""
        if self._guardian_start_scheduled:
            return
        guardian = getattr(self, "order_guardian", None)
        if not guardian:
            return

        # Do not schedule guardian background tasks in shadow mode; tests expect
        # no background work started when ExecPosFSM is in shadow_mode.
        if getattr(self, 'shadow_mode', False):
            LOG.debug("Shadow mode: skip scheduling guardian start")
            return

        loop = self._get_async_loop()
        if not loop:
            LOG.debug("OrderGuardian start deferred: no event loop active")
            return

        # Schedule guardian.start only if it's a coroutine or returns one.
        start_fn = getattr(guardian, "start", None)
        start_scheduled = False
        if callable(start_fn):
            try:
                if asyncio.iscoroutinefunction(start_fn):
                    self._submit_async(start_fn, loop)
                    start_scheduled = True
                else:
                    maybe_coro = start_fn()
                    if asyncio.iscoroutine(maybe_coro):
                        self._submit_async(start_fn, loop)
                        start_scheduled = True
                    else:
                        LOG.debug(
                            "Guardian.start is not an async coroutine; skipping schedule")
            except Exception:
                LOG.debug("Guardian.start invocation failed; skipping schedule")

        # If guardian.start was not scheduled (non-async or failed), schedule
        # startup reconcile directly. This avoids duplicate reconcile calls when
        # guardian.start() already starts the poll loop and triggers cleanup.
        if not start_scheduled:
            try:
                self._submit_async(
                    self._startup_order_guardian_reconcile, loop)
            except Exception:
                try:
                    self._submit_async(
                        self._startup_order_guardian_reconcile, loop)
                except Exception:
                    LOG.debug("Failed scheduling startup reconcile after retry")
        LOG.info("✅ OrderGuardian background tasks scheduled")
        self._guardian_start_scheduled = True

    def _schedule_fsm_cleanup_loop(self) -> None:
        """Start FSM-side cleanup loop respecting unified guardian config."""
        if self._bg_started:
            return
        if not self._orphan_cfg.get("enabled"):
            return
        if not getattr(self, "order_guardian", None):
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

        self._submit_async(self._cleanup_loop, loop)
        self._bg_started = True

    @staticmethod
    def _is_cancel_success_response(result: Any) -> bool:
        """Treat standard cancel success and -2011 idempotent paths uniformly."""
        if isinstance(result, dict):
            status = str(result.get("status", "")).upper()
            if status == "CANCELED":
                return True
            code = result.get("code")
            if code == -2011:
                return True
            msg = str(result.get("msg", "")).lower()
            if "unknown order" in msg:
                return True
        return False

    @staticmethod
    def _is_unknown_order_error(error: Exception) -> bool:
        """Detect -2011 or equivalent unknown order errors from adapter."""
        if isinstance(error, BinanceAPIError) and getattr(error, "code", None) == -2011:
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
            positions = self._latest_portfolio_state.get("positions", [])
            for pos in positions:
                symbol = pos.get("symbol")
                position_amt = float(pos.get("positionAmt", 0))

                # Check if this position was previously non-zero but is now zero
                prev_amt = getattr(
                    self, '_prev_position_amts', {}).get(symbol, 0.0)
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
                        logger=getattr(self, "logger", None),
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
        if event_key in self._processed_events:
            LOG.debug(
                f"[ACK] Skipping duplicate ACK for {symbol} order {order_id}")
            return
        self._processed_events.add(event_key)

        LOG.debug(
            f"[ACK] Processing ACK for {symbol} order {order_id} (rid={rid})")

        # Release pre-fill hold from exposure guard
        # NOTE: prefill_reservations was a design concept but not implemented in ExposureState
        # Only postfill_reservations exists. This handler just needs to handle the ACK event.
        if hasattr(self, "exposure_guard"):
            LOG.debug(f"[ACK] Order {order_id} acknowledged for {symbol}")

    def _on_trade_executed(self, event: Message) -> None:
        """
        Handle EVT:TRADE_EXECUTED events (unified fill path from FSMCore).

        This is the canonical single path for all fill events:
        - WS events from BinanceAdapter
        - REST-polling fill detections from watchdog
        - AccountObserver's new trade detections

        Calls ExposureGuard.on_fill() and creates post-fill hold.
        """
        payload = event.pld or {}
        symbol = payload.get("symbol")
        side = payload.get("side")
        price = payload.get("price")
        quantity = payload.get("quantity") or payload.get("qty")
        client_order_id = payload.get("clientOrderId") or payload.get("client_order_id")
        idempotent_key = payload.get("idempotent_key") or client_order_id
        rid = payload.get("rid") or event.rid

        if not symbol or quantity is None:
            LOG.warning(f"EVT:TRADE_EXECUTED missing required fields: symbol={symbol}, quantity={quantity}")
            return

        LOG.info(f"EVT:TRADE_EXECUTED received in ExecPosFSM: symbol={symbol} side={side} qty={quantity} key={idempotent_key}")

        # 🔄 IDEMPOTENT: Check if this event was already processed
        event_key = f"trade_executed_{idempotent_key or rid or 'unknown'}_{symbol}"
        if event_key in self._processed_events:
            LOG.debug(f"EVT:TRADE_EXECUTED Skipping duplicate for {symbol} key {idempotent_key}")
            return
        self._processed_events.add(event_key)

        # Calculate notional for exposure guard
        notional_usd = None
        if price is not None:
            try:
                notional_usd = Decimal(str(price)) * Decimal(str(quantity))
            except (ValueError, TypeError, InvalidOperation):
                pass

        # Call ExposureGuard.on_fill (canonical method for all fills)
        if hasattr(self, "exposure_guard") and self.exposure_guard:
            try:
                if idempotent_key and notional_usd is not None:
                    LOG.debug(f"ExposureGuard.on_fill applied (key={idempotent_key} notional={notional_usd})")
                    self.exposure_guard.on_fill(
                        idempotent_key, notional_usd, symbol=symbol, side=side or "SELL"
                    )
                else:
                    LOG.warning(f"Cannot call exposure_guard.on_fill: key={idempotent_key} notional={notional_usd}")
            except Exception as e:
                LOG.error(f"ExposureGuard.on_fill failed: {e}", exc_info=True)

        # Notify OrderGuardian about fill
        if hasattr(self, "order_guardian") and self.order_guardian:
            try:
                self.order_guardian.on_fill(
                    symbol=symbol,
                    parent_order_id=str(client_order_id) if client_order_id else "",
                    filled_qty=float(quantity) if quantity else 0.0
                )
            except Exception as e:
                LOG.debug(f"OrderGuardian.on_fill failed: {e}")

        # Delayed cleanup of orphaned brackets
        loop = self._get_async_loop()
        if loop:
            async def delayed_cleanup():
                await asyncio.sleep(0.5)
                try:
                    await self.order_guardian.reconcile_symbol(symbol)
                except Exception as e:
                    LOG.debug(f"Delayed reconcile_symbol failed: {e}")
            self._submit_async(delayed_cleanup(), loop)

    def _on_order_fill(self, event: Message) -> None:
        """
        Handle EVT:ORDER_FILL events from adapter (legacy path).

        AGENT-PATCH: Process FILL to update order state and create post-fill holds.
        """
        payload = event.pld or {}
        order_id = payload.get("orderId")
        symbol = payload.get("symbol")
        filled_qty = payload.get("quantity") or payload.get(
            "qty") or payload.get("filled_qty")
        # Accept idempotency-fallback key in cases where adapter does not supply orderId
        idempotent_key = payload.get(
            "idempotent_key") or payload.get("idempotencyKey") or None
        rid = payload.get("rid") or event.rid

        # Allow missing orderId if idempotent_key is present (some test harnesses use idempotent_key)
        if not symbol or filled_qty is None:
            LOG.warning(
                f"[FILL] Missing orderId, symbol or quantity in FILL event: {payload}")
            return

        # 🔄 IDEMPOTENT: Check if this event was already processed
        event_key = f"fill_{order_id or idempotent_key or 'unknown'}_{symbol}"
        if event_key in self._processed_events:
            LOG.debug(
                f"[FILL] Skipping duplicate FILL for {symbol} order {order_id}")
            return
        self._processed_events.add(event_key)

        LOG.debug(
            f"[FILL] Processing FILL for {symbol} order {order_id}, qty={filled_qty} (rid={rid})")

        # Create post-fill hold in exposure guard via canonical method
        if hasattr(self, "exposure_guard"):
            # Prefer idempotent key for reservation matching; fallback to generated key
            idempotent_key = payload.get(
                "idempotent_key") or payload.get("idempotencyKey") or None

            # Try to compute notional_usd from price * qty when available
            price_val = payload.get(
                "price") or payload.get("fillPrice") or payload.get("avgPrice") or None
            try:
                notional_usd = Decimal(
                    str(price_val)) * Decimal(str(filled_qty)) if price_val is not None else None
            except Exception:
                notional_usd = None

            if idempotent_key and notional_usd is not None:
                try:
                    LOG.debug(
                        f"[FILL] About to call exposure_guard.on_fill key={idempotent_key} notional={notional_usd}")
                    # Use ExposureGuard.on_fill to atomically move reservation to postfill
                    self.exposure_guard.on_fill(
                        idempotent_key, notional_usd, symbol=symbol, side=payload.get("side", "SELL"))
                    LOG.debug(
                        f"[FILL] Moved reservation {idempotent_key} to postfill via ExposureGuard.on_fill")
                except Exception as e:
                    LOG.debug(
                        f"[FILL] ExposureGuard.on_fill failed for {idempotent_key}: {e}")
                    # Fallback to legacy behavior
                    postfill_key = idempotent_key
                    self.exposure_guard.state.postfill_reservations[postfill_key] = {
                        "symbol": symbol,
                        "qty": filled_qty,
                        "ts_ms": int(__import__('time').time() * 1000),
                        "rid": rid,
                    }
                    LOG.debug(
                        f"[FILL] Created postfill hold for {postfill_key} (fallback)")
            else:
                # No idempotent key or no price info - preserve legacy behavior
                postfill_key = idempotent_key if idempotent_key else f"postfill_{symbol}_{order_id}"
                self.exposure_guard.state.postfill_reservations[postfill_key] = {
                    "symbol": symbol,
                    "qty": filled_qty,
                    "ts_ms": int(__import__('time').time() * 1000),
                    "rid": rid,
                }
                LOG.debug(
                    f"[FILL] Created postfill hold for {postfill_key} (legacy)")

            # Debug: log computed values for diagnostics
            try:
                LOG.debug(
                    f"[FILL_DEBUG] idempotent_key={idempotent_key} filled_qty={filled_qty} price_val={price_val} notional_usd={notional_usd}")
            except Exception:
                pass

        # Notify OrderGuardian about entry fill (per-entry remaining tracking)
        try:
            if hasattr(self, 'order_guardian') and self.order_guardian:
                fq = 0.0
                try:
                    fq = float(filled_qty)
                except Exception:
                    fq = 0.0
                # Best-effort; only updates if this orderId corresponds to a tracked entry
                self.order_guardian.on_fill(
                    symbol=symbol, parent_order_id=str(order_id), filled_qty=fq
                )
        except Exception:
            # Non-fatal
            pass

        # Best-effort cleanup of orphaned brackets in case this fill closed the position
        # Debounce: wait 500ms to allow TP/SL registration before cleanup
        loop = self._get_async_loop()
        if loop:
            async def delayed_cleanup():
                await asyncio.sleep(0.5)
                # ✅ FIX: Call reconcile_symbol for the specific symbol instead of global cleanup_orphans
                # This ensures brackets are cleaned up when position closes, even if other symbols have positions
                await self.order_guardian.reconcile_symbol(symbol)
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
            # Only emit asynchronously when реальний asyncio loop доступний (із call_soon_threadsafe)
            if loop and hasattr(loop, "call_soon_threadsafe"):
                self._submit_async(emit_compat(
                    self.fsm, exposure_msg, logger=LOG), loop)
            else:
                LOG.debug(
                    "Skip async exposure emit on ORDER_FILL (no real loop)")
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
                    if hasattr(self.config, 'trading') and self.config.trading:
                        mode = self.config.trading.mode
                    elif isinstance(self.config, dict):
                        mode = self.config.get("trading_mode", "testnet")
                except (AttributeError, TypeError):
                    mode = "testnet"
        else:
            # Fallback to global mode or domain-specific mode from dict
            try:
                if hasattr(self.config, 'trading') and self.config.trading:
                    mode = self.config.trading.mode
                elif isinstance(self.config, dict):
                    # Check domain-specific mode first
                    domain_mode = self.config.get("domain_configuration", {}).get(
                        "execution_position", {}).get("trading_mode")
                    if domain_mode:
                        mode = domain_mode
                        LOG.info(
                            f"✅ ExecPosFSM using domain-specific mode from dict: {mode}")
                    else:
                        global_mode = self.config.get(
                            "trading_mode", "testnet")
                        # For hybrid modes, execution_position should use testnet
                        if global_mode == "hybrid_live_data_testnet_exec":
                            mode = "testnet"
                            LOG.info(
                                f"✅ ExecPosFSM using testnet for hybrid mode: {global_mode} → {mode}")
                        else:
                            mode = global_mode
                        LOG.info(
                            f"ExecPosFSM using global trading_mode from dict: {mode}")
                else:
                    mode = "testnet"
            except (AttributeError, TypeError):
                mode = "testnet"
            if not isinstance(self.config, dict):
                LOG.info(
                    f"ExecPosFSM using global trading_mode: {mode.upper()}")

        LOG.info(f"🎯 EXECUTION POSITION FSM MODE: {mode.upper()}")

        try:
            if hasattr(self.config, 'binance_api'):
                api_config = self.config.binance_api if self.config.binance_api else {}
            elif isinstance(self.config, dict):
                api_config = self.config.get("binance_api", {})
            else:
                api_config = {}
        except (AttributeError, TypeError):
            api_config = {}

        # Safe extraction of env config
        env_config = {}
        if mode == "live":
            if isinstance(api_config, dict):
                env_config = api_config.get("live", {})
            else:
                env_config = api_config.live if hasattr(
                    api_config, 'live') else {}
            LOG.info("❌ ExecPosFSM adapter is configured for LIVE execution.")
        else:  # 'testnet' or 'hybrid_live_data_testnet_exec'
            if isinstance(api_config, dict):
                env_config = api_config.get("testnet", {})
            else:
                env_config = api_config.testnet if hasattr(
                    api_config, 'testnet') else {}
            LOG.info(
                f"✅ ExecPosFSM adapter is configured for TESTNET execution (mode: {mode})."
            )

        # Extract API credentials safely
        if isinstance(env_config, dict):
            api_key = env_config.get("api_key", "")
            api_secret = env_config.get("api_secret", "")
            rest_url = env_config.get("rest_url", "")
        else:
            api_key = getattr(env_config, "api_key", "")
            api_secret = getattr(env_config, "api_secret", "")
            rest_url = getattr(env_config, "rest_url", "")

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
        # PriceService SSOT - in Wave 0 we initialize without adapter wiring
        # (synchronous PriceService is a low-impact additive step)
        # Initialize an Async PriceService and a sync wrapper for synchronous FSMs
        try:
            async_price_service = PriceService(
                self.adapter, max_cache_size=500)
            self.price_service = PriceServiceSync(
                async_service=async_price_service)
        except Exception:
            self.price_service = None

    def _get_or_create_flows(
        self, symbol: str
    ) -> Tuple[OpenFlowFSM, ManageFlowFSM, CloseFlowFSM]:
        """Get or create the set of FSMs for a given symbol (thread-safe)."""
        with self._flows_lock:
            if symbol not in self.manage_flows:
                LOG.info(f"Creating new set of FSMs for symbol: {symbol}")
                try:
                    if hasattr(self.config, 'trading') and self.config.trading:
                        exec_config = self.config.trading.execution if self.config.trading.execution else None
                    elif isinstance(self.config, dict):
                        exec_config = self.config.get(
                            "trading", {}).get("execution", {})
                    else:
                        exec_config = None
                except (AttributeError, TypeError):
                    exec_config = None

                if exec_config is None:
                    exec_config = {}

                # Safe extraction of execution config settings
                if isinstance(exec_config, dict):
                    cooldown_ms = float(exec_config.get("cooldown_ms", 1000))
                    guard_enabled = exec_config.get("guard_enabled", True)
                else:
                    cooldown_ms = float(
                        getattr(exec_config, "cooldown_ms", 1000))
                    guard_enabled = getattr(exec_config, "guard_enabled", True)
                cooldown_sec = cooldown_ms / 1000.0

                self.open_flows[symbol] = OpenFlowFSM(
                    cooldown_sec=cooldown_sec,
                    guard_enabled=guard_enabled,
                    config=self.config,
                    metrics_collector=self.metrics_collector,
                )
                self.manage_flows[symbol] = ManageFlowFSM(
                    config=self.config, price_service=getattr(self, 'price_service', None))
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

    async def sync_open_orders_and_positions(self) -> None:
        """
        Backward-compatible public API used in tests to trigger order/position sync.

        Delegates to the internal reconcile logic.
        """
        await self._startup_order_guardian_reconcile()

    def handle(self, msg: Message) -> Optional[Message]:
        """Route message to the appropriate flow and handle execution decisions."""
        pld = msg.pld or {}

        # P0.3: WAL logging for msg_in event
        wal.append({
            "event_type": "msg_in",
            "data": msg.model_dump(),
            "timestamp": int(time.time() * 1000)
        })

        # Handle portfolio state updates BEFORE symbol check (they don't need symbol)
        if msg.verb == "PORTFOLIO_STATE_UPDATED":
            # Handle portfolio state updates (trigger post-fill hold release)
            self._on_portfolio_state_updated(msg)
            return None

        # Also handle raw FILL events sent directly to handle() so test harnesses
        # using Message(verb="FILL") are processed the same as adapter callbacks.
        if msg.op == "EVT" and msg.verb in ("FILL", "ORDER_FILL"):
            try:
                self._on_order_fill(msg)
            except Exception:
                pass

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
            if self._check_exposure_fail_closed(msg):
                return None  # Error already emitted
            result = open_flow.handle(msg)
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
            # Route non-CMD events to ManageFlow; also inform CloseFlow of EVT/UPD
            result = manage_flow.handle(msg)
            # Inform CloseFlow of EVT/UPD events so it can update its state
            try:
                if msg.op in ("EVT", "UPD"):
                    close_flow.handle(msg)
            except Exception:
                # Non-fatal - CloseFlow should not break manage flow handling
                pass

        # If a decision was made, log it and execute if not in shadow mode
        if result and result.op == "DEC":
            wal.append({
                "event_type": "msg_out",
                "data": result.model_dump(),
                "timestamp": int(time.time() * 1000)
            })
            # ✅ FIX: Execute CLOSE decisions even in shadow mode to cancel brackets
            if (not self.shadow_mode and self.adapter) or (result.verb == "CLOSE" and self.adapter):
                # Asynchronously execute the trade decision
                loop = self._get_async_loop()
                if loop:
                    self._submit_async(self._execute_decision(result), loop)

        return result

    async def replay_on_startup(self) -> None:
        """
        P0.3: WAL replay for state recovery on startup.

        Replays WAL events to restore FSM state after restart.
        Processes msg_in events to rebuild internal state.
        """
        try:
            LOG.info("🔄 Starting WAL replay for ExecPosFSM...")

            # Get WAL events from vfoundation.dr.wal
            from vfoundation.dr.wal import read_all

            events = read_all()
            replayed_count = 0

            for event in events:
                try:
                    # Only replay msg_in events (decisions are already logged separately)
                    event_type = event.get("event_type", "")
                    if event_type == "msg_in":
                        msg_data = event.get("data", {})
                        # Reconstruct Message from WAL data
                        msg = Message(**msg_data)
                        # Replay by calling handle (but skip WAL logging during replay)
                        # Temporarily disable WAL logging during replay
                        original_wal_append = wal.append
                        wal.append = lambda x: None  # No-op during replay
                        try:
                            self.handle(msg)
                            replayed_count += 1
                        finally:
                            wal.append = original_wal_append  # Restore

                except Exception as e:
                    LOG.warning(
                        f"WAL replay error for event {event.get('id', 'unknown')}: {e}")
                    continue

            LOG.info(
                f"✅ WAL replay completed: {replayed_count} events replayed")

        except Exception as e:
            LOG.error(f"❌ WAL replay failed: {e}", exc_info=True)
            # Don't raise - allow startup to continue even if replay fails

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
            except:
                # Fallback: try trading_mode attribute
                if hasattr(self.config, "trading_mode"):
                    domain_mode = self.config.trading_mode
                elif isinstance(self.config, dict) and "trading_mode" in self.config:
                    domain_mode = self.config.get("trading_mode", "testnet")
        elif isinstance(self.config, dict):
            # Dict-based config
            domain_mode = self.config.get("trading_mode", "testnet")
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
                        cancel_result = await self._call_adapter_fn(self.adapter.cancel_order, symbol, order_id)
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
                # Quick profit instrumentation
                event_why = getattr(decision, 'why', '') or pld.get('why', '')
                if event_why == 'QUICK_PROFIT_HIT':
                    LOG.info(f"💰 Executing QUICK PROFIT close for {symbol}")
                    LOG.info(f"   PnL: ${pld.get('pnl_usd', 'unknown')}")
                    try:
                        if hasattr(self, 'metrics_collector') and self.metrics_collector:
                            pnl_raw = pld.get('pnl_usd', 0)
                            pnl = float(
                                pnl_raw) if pnl_raw is not None else 0.0
                            self.metrics_collector.record_quick_profit_close(
                                symbol, pnl)
                    except Exception:
                        LOG.debug("Failed to record quick profit metric")

                # PHASE A2: Set closing flag to prevent bracket placement race condition
                manage = self.manage_flows.get(symbol)
                if manage:
                    manage._closing_position = True
                    manage._closing_position_ts = time.time()
                    LOG.info(
                        f"🔒 [PHASE A2] Set closing flag for {symbol} to prevent bracket race")

                # Support DEC:CLOSE by entry: if a parent_order_id is provided in
                # the decision payload, call OrderGuardian.close_entry() which
                # cancels only brackets belonging to the parent entry and returns
                # remaining qty & side to close. Skip symbol-wide tracked-bracket
                # cancellation in that case to avoid interfering with other
                # entries on the same symbol.
                pld_parent_id = pld.get("parent_order_id") or pld.get(
                    "parent_entry_id") or pld.get("entry_order_id")
                tasks = []
                bracket_order_ids = []  # Track IDs for logging (if any)

                if pld_parent_id:
                    # Cancel brackets for specific entry via OrderGuardian
                    try:
                        entry_close_res = await self.order_guardian.close_entry(symbol=symbol, parent_order_id=str(pld_parent_id))
                        cancelled_cnt = entry_close_res.get(
                            "cancelled_brackets", 0)
                        remaining_qty = float(entry_close_res.get(
                            "remaining_qty", 0.0) or 0.0)
                        entry_side = entry_close_res.get("side")
                        LOG.info(
                            f"🔒 DEC:CLOSE by-entry executed: parent={pld_parent_id} cancelled={cancelled_cnt} remaining={remaining_qty} side={entry_side}")
                    except Exception as e:
                        LOG.warning(f"🔁 DEC:CLOSE by-entry helper error: {e}")
                        entry_close_res = {
                            "cancelled_brackets": 0, "remaining_qty": 0.0, "side": None}
                        remaining_qty = 0.0

                    # If there is remaining qty for this entry, place a reduce-only market
                    if remaining_qty and remaining_qty > 0:
                        try:
                            # Determine close side from entry side if available
                            if entry_side:
                                close_side = "SELL" if entry_side.upper() == "BUY" else "BUY"
                            else:
                                # Fallback to current positions if we don't have entry side
                                try:
                                    pos = next((p for p in (await self._call_adapter_fn(self.adapter.get_open_positions)) if p.get("symbol") == symbol), None)
                                    pos_amt = float(
                                        pos.get("positionAmt", 0)) if pos else 0
                                    close_side = "SELL" if pos_amt > 0 else "BUY"
                                except Exception:
                                    close_side = "SELL"

                            close_qty = str(abs(Decimal(str(remaining_qty))))
                            close_id = generate_client_order_id(
                                "CLOSE", symbol)
                            await self._call_adapter_fn(self.adapter.place_market_reduce_only, symbol, close_side, close_qty, new_client_order_id=close_id)
                            LOG.info(
                                f"Close executed (by-entry) for {symbol}: parent={pld_parent_id} side={close_side} qty={close_qty}")
                        except Exception as e:
                            LOG.warning(
                                f"Failed placing reduce-only close for entry parent={pld_parent_id}: {e}")

                    # Skip symbol-wide tracked bracket cancellation below when parent_id is present
                    self._symbol_brackets.pop(symbol, None)
                    return
                else:
                    # Cancel tracked brackets (backward compatibility)
                    br = self._symbol_brackets.get(symbol, {})
                    if br.get("sl_order_id"):
                        tasks.append(self._call_adapter_fn(
                            self.adapter.cancel_order, symbol, br["sl_order_id"]))
                        bracket_order_ids.append(("SL", br["sl_order_id"]))
                    if br.get("tp_order_id"):
                        tasks.append(self._call_adapter_fn(
                            self.adapter.cancel_order, symbol, br["tp_order_id"]))
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
                                cancel_status = str(
                                    result.get("status", "")).upper()
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
                    positions = await self._call_adapter_fn(self.adapter.get_open_positions)
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
                        amt = float(pos.get("positionAmt", 0))
                    except Exception:
                        amt = 0.0
                if abs(amt) < 1e-10:
                    LOG.info(f"No open position to close for {symbol}")
                    self._symbol_brackets.pop(symbol, None)
                    return
                close_side = "SELL" if amt > 0 else "BUY"
                close_qty = str(abs(Decimal(str(amt))))
                close_id = generate_client_order_id("CLOSE", symbol)
                await self._call_adapter_fn(self.adapter.place_market_reduce_only, symbol, close_side, close_qty, new_client_order_id=close_id)
                LOG.info(
                    f"Close executed for {symbol}: side={close_side} qty={close_qty}")
                self._symbol_brackets.pop(symbol, None)

                # ✅ PHASE A1: Ensure cleanup after manual CLOSE
                # Wait for position to settle, then cleanup any orphaned brackets
                await asyncio.sleep(2.0)

                # 🔄 Synchronous reconcile (symbol-wide) — ОПЦІЙНО: тільки якщо зберігаємо єдиний набір брекетів
                # multi-entry mode: НЕ чіпати інші брекети за символом, щоб не зламати SL/TP другої позиції
                do_symbol_reconcile = True
                try:
                    if isinstance(self.config, dict):
                        do_symbol_reconcile = bool(
                            self.config.get("trading", {})
                            .get("execution", {})
                            .get("manage", {})
                            .get("brackets", {})
                            .get("keep_single_bracket_set", True)
                        )
                    else:
                        tr = getattr(self.config, 'trading', None)
                        exec_cfg = getattr(
                            tr, 'execution', None) if tr else None
                        manage_cfg = getattr(
                            exec_cfg, 'manage', None) if exec_cfg else None
                        brackets_cfg = getattr(
                            manage_cfg, 'brackets', None) if manage_cfg else None
                        if brackets_cfg and hasattr(brackets_cfg, 'keep_single_bracket_set'):
                            do_symbol_reconcile = bool(
                                getattr(brackets_cfg, 'keep_single_bracket_set'))
                        else:
                            do_symbol_reconcile = True
                except Exception:
                    do_symbol_reconcile = True
                # If we were invoked for DEC:CLOSE by specific entry, skip symbol-wide reconcile
                if pld_parent_id:
                    do_symbol_reconcile = False
                if do_symbol_reconcile:
                    LOG.info(
                        f"🔄 [DEC:CLOSE RECONCILE] Starting sync cleanup for {symbol} (single-set mode)")
                    try:
                        open_orders = await self._call_adapter_fn(self.adapter.get_open_orders, symbol)
                        open_orders_list = [
                            o.to_dict() if hasattr(o, 'to_dict') else (
                                o.__dict__ if not isinstance(o, dict) else o)
                            for o in open_orders
                        ]

                        cancel_tasks = []
                        for o in open_orders_list:
                            otype = (o.get("type") or "").upper()
                            reduce_only = str(
                                o.get("reduceOnly", "")).lower() == "true"
                            close_pos = str(
                                o.get("closePosition", "")).lower() == "true"
                            if otype in ("STOP_MARKET", "TAKE_PROFIT_MARKET", "LIMIT") and (reduce_only or close_pos):
                                oid = o.get("orderId")
                                cancel_tasks.append(
                                    (otype, oid, self.adapter.cancel_order(symbol, oid)))

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
                                        self._orphan_metrics["reconcile_cancelled"] = self._orphan_metrics.get(
                                            "reconcile_cancelled", 0) + 1
                                    else:
                                        status = str(result.get(
                                            "status", "")).upper()
                                        LOG.warning(
                                            f"❌ [DEC:CLOSE RECONCILE] Cancel response unexpected for {otype} {oid} (status={status})")
                                        self._orphan_metrics["errors"] += 1

                            LOG.info(
                                f"✅ [DEC:CLOSE RECONCILE] Completed for {symbol}: cancelled {len(cancel_tasks)} orders")
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
                else:
                    LOG.info(
                        f"🛑 [DEC:CLOSE RECONCILE] Skipped symbol-wide cleanup for {symbol} (multi-entry mode)")

                # Запуск повної чистки орфанів не виконується у multi-entry режимі (щоб не чіпати інші entry)
                if do_symbol_reconcile:
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
                    "orphans_cancelled": self._orphan_metrics.get("reconcile_cancelled", 0)
                })

                return

            symbol = decision.pld["symbol"]
            side = decision.pld["side"].upper()
            qty = decision.pld["qty"]

            # Get mark price and filters
            mark = await self._call_adapter_fn(self.adapter.get_mark_price, symbol)
            exchange_info = await self._call_adapter_fn(self.adapter.get_exchange_info, symbol)
            tick_size = float(
                next(
                    f["tickSize"]
                    for f in exchange_info["symbols"][0]["filters"]
                    if f["filterType"] == "PRICE_FILTER"
                )
            )

            # TP/SL bps from config with backward compatibility
            trading_cfg = self.config.get("trading", {}) if isinstance(
                self.config, dict) else self.config.trading
            exec_cfg = (trading_cfg
                        or {}).get("execution", {})
            brackets_cfg = (trading_cfg.get("execution", {}) if isinstance(trading_cfg, dict) else trading_cfg.execution
                            or {}).get("manage", {}).get("brackets", {})
            # SL
            try:
                sl_dict = trading_cfg.get("execution", {}).get("brackets", {}).get(
                    "sl", {}) if isinstance(trading_cfg, dict) else trading_cfg.execution.brackets.sl or {}
                sl_bps = int(sl_dict.get("fixed_bps",
                                         getattr(sl_dict, 'stop_loss_bps', 50) if not isinstance(sl_dict, dict) else 50))
            except Exception:
                sl_bps = 50
            # TP
            try:
                tp_dict = trading_cfg.get("execution", {}).get("brackets", {}).get(
                    "tp", {}) if isinstance(trading_cfg, dict) else trading_cfg.execution.brackets.tp or {}
                if isinstance(tp_dict, dict) and "fixed_bps" in tp_dict:
                    tp_bps = int(tp_dict.get("fixed_bps", 100))
                else:
                    # derive from ratios if provided
                    ratio = trading_cfg.get("execution", {}).get("brackets", {}).get("take_profit_high_ratio") or trading_cfg.get("execution", {}).get("brackets", {}).get("take_profit_low_ratio") if isinstance(
                        trading_cfg, dict) else (getattr(trading_cfg.execution.brackets, 'take_profit_high_ratio', None) or getattr(trading_cfg.execution.brackets, 'take_profit_low_ratio', None))
                    tp_bps = int(float(ratio) * float(sl_bps)
                                 ) if ratio is not None else 100
            except Exception:
                tp_bps = 100

            tp, sl = calc_tp_sl_from_mark(
                mark, "LONG" if side == "BUY" else "SHORT", tp_bps, sl_bps
            )

            # Quantize
            tp = quantize_stop_price(
                tp, tick_size, side="BUY" if side == "BUY" else "SELL"
            )
            sl = quantize_stop_price(
                sl, tick_size, side="SELL" if side == "BUY" else "BUY"
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
            entry_resp = await self._call_adapter_fn(self.adapter.place_market_entry, symbol, side, qty, entry_id)
            LOG.info(f"✅ MARKET entry placed: {entry_resp}")

            # [GUARD] Register entry order for ownership tracking
            self.order_guardian.register_entry(
                symbol=symbol,
                order_id=str(entry_resp.get("orderId", "")),
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
            entry_order_id = str(entry_resp.get("orderId", ""))
            self.watchdog.track_order_placed(
                order_id=entry_order_id,
                client_order_id=entry_id,
                symbol=symbol,
                corr_id=decision.corr_id,
                rid=decision.rid
            )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": decision.rid,
                "event_type": "ORDER_PLACED",
                "symbol": symbol,
                "side": side,
                "quantity": float(qty),
                "client_order_id": entry_id,
                "order_id": str(entry_resp.get("orderId", "")),
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
            entry_order_id = str(entry_resp.get("orderId", ""))
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
                    return await self._call_adapter_fn(self.adapter.place_stop_market_close_position, symbol, sl_side, str(sl), new_client_order_id=sl_id)

                async def place_tp_async():
                    try:
                        return (
                            await self._call_adapter_fn(self.adapter.place_take_profit_market_close_position, symbol, tp_side, str(tp), new_client_order_id=tp_id)
                        )
                    except BinanceAPIError as e:
                        if e.code == -2021:
                            # PHASE A3: Exponential backoff for -2021 (price too close to mark)
                            LOG.warning(
                                f"⚠️ [PHASE A3] TP -2021 error, attempting backoff for {symbol}")
                            self._orphan_metrics["tp_sl_retry_backoff"] = self._orphan_metrics.get(
                                "tp_sl_retry_backoff", 0) + 1

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
                                return await self._call_adapter_fn(self.adapter.place_take_profit_market_close_position, symbol, tp_side, str(tp_adj), new_client_order_id=tp_id)
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
                                        return await self._call_adapter_fn(self.adapter.place_take_profit_market_close_position, symbol, tp_side, str(tp_adj2), new_client_order_id=tp_id)
                                    except BinanceAPIError:
                                        # Fallback to LIMIT reduceOnly
                                        LOG.warning(
                                            f"⚠️ [PHASE A3] TP -2021 fallback to LIMIT for {symbol}")
                                        self.metrics_collector.record_retry(
                                            "tp_fallback") if self.metrics_collector else None
                                        return await self._call_adapter_fn(self.adapter.place_limit_reduce_only, symbol, tp_side, str(tp_adj2), qty, new_client_order_id=tp_id)
                                else:
                                    raise
                            # Fallback to LIMIT reduceOnly
                            self.metrics_collector.record_retry(
                                "tp_fallback") if self.metrics_collector else None
                            return await self._call_adapter_fn(self.adapter.place_limit_reduce_only, symbol, tp_side, str(tp_adj), qty, new_client_order_id=tp_id)
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
                sl_resp = await self._call_adapter_fn(self.adapter.place_stop_market_close_position, symbol, sl_side, str(sl), new_client_order_id=sl_id)
                try:
                    tp_resp = await self._call_adapter_fn(self.adapter.place_take_profit_market_close_position, symbol, tp_side, str(tp), new_client_order_id=tp_id)
                except BinanceAPIError as e:
                    if e.code == -2021:
                        tp_adj = tp * 1.002
                        tp_adj = quantize_stop_price(
                            tp_adj, tick_size, side="BUY" if side == "BUY" else "SELL"
                        )
                        try:
                            tp_resp = await self._call_adapter_fn(self.adapter.place_take_profit_market_close_position, symbol, tp_side, str(tp_adj), new_client_order_id=tp_id)
                        except BinanceAPIError:
                            tp_resp = await self._call_adapter_fn(self.adapter.place_limit_reduce_only, symbol, tp_side, str(tp_adj), qty, new_client_order_id=tp_id)
                    else:
                        raise

            # Log the results
            sl_order_id = None
            tp_order_id = None

            if sl_resp:
                LOG.info(f"✅ SL placed: {sl_resp}")
                self._orphan_metrics["tp_sl_placed_success"] = self._orphan_metrics.get(
                    "tp_sl_placed_success", 0) + 1
                # Correlation: store SL ACK
                sl_order_id = str(sl_resp["orderId"])
                self.correlation_store.put_sl_tp_ack(
                    sl_order_id, entry_resp["clientOrderId"], decision.corr_id or "", decision.oco_group_id or "", decision.rid or "")
                # Track SL bracket per symbol
                self._symbol_brackets.setdefault(
                    symbol, {})["sl_order_id"] = sl_order_id

            if tp_resp:
                LOG.info(f"✅ TP placed: {tp_resp}")
                self._orphan_metrics["tp_sl_placed_success"] = self._orphan_metrics.get(
                    "tp_sl_placed_success", 0) + 1
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
                    entry_order_id=str(entry_resp.get("orderId", "")),
                    sl_order_id=sl_order_id,
                    tp_order_id=tp_order_id,
                    sl_client_id=sl_id if sl_resp else None,
                    tp_client_id=tp_id if tp_resp else None,
                    corr_id=decision.corr_id,
                    rid=decision.rid
                )

                # Optional single-set bracket policy (default: keep single set)
                # Feature flag: trading.execution.manage.brackets.keep_single_bracket_set (default True)
                keep_single = True
                try:
                    if isinstance(self.config, dict):
                        keep_single = bool(
                            self.config.get("trading", {})
                            .get("execution", {})
                            .get("manage", {})
                            .get("brackets", {})
                            .get("keep_single_bracket_set", True)
                        )
                    else:
                        # Pydantic / object-style (best-effort)
                        tr = getattr(self.config, 'trading', None)
                        exec_cfg = getattr(
                            tr, 'execution', None) if tr else None
                        manage_cfg = getattr(
                            exec_cfg, 'manage', None) if exec_cfg else None
                        brackets_cfg = getattr(
                            manage_cfg, 'brackets', None) if manage_cfg else None
                        if brackets_cfg and hasattr(brackets_cfg, 'keep_single_bracket_set'):
                            keep_single = bool(
                                getattr(brackets_cfg, 'keep_single_bracket_set'))
                except Exception:
                    keep_single = True

                if keep_single:
                    try:
                        await self.order_guardian.cleanup_other_brackets_for_symbol(
                            symbol,
                            keep_parent_order_id=str(
                                entry_resp.get("orderId", "")),
                        )
                    except Exception as _e:
                        LOG.debug(
                            f"OrderGuardian cleanup_other_brackets_for_symbol skipped: {_e}")

            # ✅ NEW: Sync bracket IDs with ManageFlowFSM for OCO emulation
            # Ensures ManageFlowFSM has accurate tracking even if WebSocket events are delayed
            manage_flow = self.manage_flows.get(symbol)
            if manage_flow:
                sl_id = self._symbol_brackets.get(
                    symbol, {}).get("sl_order_id")
                tp_id = self._symbol_brackets.get(
                    symbol, {}).get("tp_order_id")
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
                    symbol = decision.pld.get('symbol', 'unknown')
                    error_key = f"exec_error_{symbol}"
                    if not hasattr(self, '_exec_error_counts'):
                        self._exec_error_counts = {}
                    self._exec_error_counts[error_key] = self._exec_error_counts.get(
                        error_key, 0) + 1

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
            order_logger.write({
                "rid": decision.rid,
                "event_type": "ORDER_REJECTED",
                "symbol": decision.pld.get("symbol", ""),
                "side": decision.pld.get("side", "NONE"),
                "quantity": float(decision.pld.get("qty", 0)),
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
                "enabled": self._orphan_cfg.get("enabled", True),
                "periodic_interval_sec": self._orphan_cfg.get("periodic_interval_sec", 300),
                "min_order_age_sec": self._orphan_cfg.get("min_order_age_sec", 0),
                "batch_cancel_limit": self._orphan_cfg.get("batch_cancel_limit", 50),
                "rate_limit_per_min": self._orphan_cfg.get("rate_limit_per_min", 120),
            },
        }

        # Include gate metrics (SYMBOL_TIDY entry gate)
        try:
            gate_blocked = int(self._gate_metrics.get(
                "gate_entry_blocked_tidy", 0))
            gate_allowed = int(self._gate_metrics.get(
                "gate_entry_allowed_tidy", 0))
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
            guardian = getattr(self, "order_guardian", None)
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
            allow_gate = False
            if hasattr(self.config, 'execution') and self.config.execution:
                allow_gate = bool(
                    getattr(self.config.execution, 'allow_trade_with_guardian_tidy_only', False))
            elif isinstance(self.config, dict):
                allow_gate = bool(self.config.get('execution', {}).get(
                    'allow_trade_with_guardian_tidy_only', False))
        except Exception:
            allow_gate = False

        if not allow_gate:
            return True

        # TTL and cooldown
        ttl_ms = int(self._guardian_cfg.get("cleanup_ttl_ms", 6000))
        cooldown_ms = int(self._guardian_cfg.get("symbol_cooldown_ms", 4000))

        now = time.time()
        last_tidy = self._symbol_last_tidy_ts.get(symbol, 0.0)
        fresh = (now - last_tidy) * 1000.0 <= ttl_ms
        last_block = self._last_entry_block_ts.get(symbol, 0.0)
        cooldown_ok = (now - last_block) * 1000.0 >= cooldown_ms

        if fresh or (last_block > 0 and cooldown_ok):
            self._gate_metrics["gate_entry_allowed_tidy"] = self._gate_metrics.get(
                "gate_entry_allowed_tidy", 0) + 1
            LOG.info(
                f"[GATE] entry_allowed: tidy_recent={fresh} cooldown_ok={cooldown_ok} last_block={last_block} symbol={symbol}")
            return True

        # Block
        self._last_entry_block_ts[symbol] = now
        self._gate_metrics["gate_entry_blocked_tidy"] = self._gate_metrics.get(
            "gate_entry_blocked_tidy", 0) + 1
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
                cancel_result = await self._call_adapter_fn(self.adapter.cancel_order, deadline.symbol, deadline.order_id)

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

                    # ✅ FIX: Update portfolio state after successful timeout cancellation
                    # This ensures decision_making knows the position was never opened
                    await self._update_portfolio_after_timeout_cancellation(deadline.symbol)

                else:
                    status = str(cancel_result.get("status", "")).upper()
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

                    # ✅ FIX: Update portfolio state even for idempotent cancellation
                    await self._update_portfolio_after_timeout_cancellation(deadline.symbol)

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
            self._timeout_counts[timeout_key] = self._timeout_counts.get(
                timeout_key, 0) + 1

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
            await emit_compat(self.fsm, timeout_msg, logger=getattr(self, "logger", None))
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

    def _check_exposure_fail_closed(self, msg: Message) -> bool:
        """
        EXP-FIX: Check exposure limits with fail-closed behavior.

        Returns True if request should be blocked (error already emitted).
        """
        pld = msg.pld or {}
        symbol = pld.get("symbol")
        qty = pld.get("qty")
        price_ref = pld.get("price_ref")

        if not symbol or not qty or not price_ref:
            LOG.warning(
                f"EXPOSURE_CHECK_SKIP: Missing required fields for {symbol}")
            return False

        try:
            # Calculate notional
            notional_usd = Decimal(str(qty)) * Decimal(str(price_ref))

            # Check exposure with fail-closed logic
            exposure_check = self.exposure_guard.can_open(
                symbol, notional_usd, self._latest_portfolio_state
            )

            if not exposure_check["allowed"]:
                reason = exposure_check["reason"]
                stale_sec = exposure_check.get("stale_sec", 0)

                # EXP-FIX: Paranoid fail-closed: reserve exposure even when blocking
                # This protects against edge cases where our stale detection is wrong
                reserve_key = pld.get(
                    "idempotent_key") or msg.rid or f"rid_{msg.rid}"
                self.exposure_guard.reserve(reserve_key, notional_usd)

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
                        "requested_notional": str(notional_usd),
                    },
                    why=f"exposure_fail_closed_{reason.lower()}",
                )

                # EXP-FIX: Record fail-closed metric
                if hasattr(self, "metrics_collector") and self.metrics_collector:
                    self.metrics_collector.record_exposure_fail_closed(reason)

                # Emit error asynchronously
                loop = self._get_async_loop()
                if loop:
                    self._submit_async(self._emit_error_async(error_msg), loop)
                return True

            # EXP-FIX: Periodic shadow notional check (every 10 requests approx)
            self._shadow_check_counter += 1

            if self._shadow_check_counter % 10 == 0 and self.adapter:
                loop = self._get_async_loop()
                if loop:
                    self._submit_async(self._check_shadow_notional(), loop)

            # Reserve exposure for successful check
            reserve_key = pld.get(
                "idempotent_key") or msg.rid or f"rid_{msg.rid}"
            self.exposure_guard.reserve(reserve_key, notional_usd)

            return False

        except Exception as e:
            LOG.error(f"EXPOSURE_CHECK_ERROR: {e}", exc_info=True)
            return False

    async def _emit_error_async(self, msg: Message) -> None:
        """Asynchronously emit an error message."""
        try:
            await emit_compat(self.fsm, msg, logger=getattr(self, "logger", None))
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
        qty = pld.get("qty", 0)
        price = pld.get("price", 0)
        try:
            notional_usd = Decimal(str(qty)) * Decimal(str(price))
            self.exposure_guard.on_fill(reserve_key, notional_usd)

            # EXP-FIX: Record post-fill hold metric
            if hasattr(self, "metrics_collector") and self.metrics_collector:
                self.metrics_collector.record_postfill_hold(
                    len(self.exposure_guard.state.postfill_reservations)
                )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": pld.get("rid", f"fill_{reserve_key}"),
                "event_type": "ORDER_STATE_CHANGED",
                "symbol": pld.get("symbol", ""),
                "side": pld.get("side", "NONE"),
                "quantity": float(qty),
                "price": float(price),
                "client_order_id": pld.get("client_order_id", ""),
                "order_id": pld.get("order_id", ""),
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
            await emit_compat(self.fsm, msg, logger=getattr(self, "logger", None))
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
            shadow_notional = await self._call_adapter_fn(self.adapter.get_positions_notional_usd_shadow)

            # Get portfolio notional
            portfolio_notional = Decimal(
                str(self._latest_portfolio_state.get("open_positions_usd", "0"))
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
        # Read from config when available; fallback to safe defaults
        try:
            if hasattr(self.config, 'execution') and self.config.execution:
                backoff_ms = list(
                    getattr(self.config.execution, 'preflight_backoff_ms', [150, 300, 500]))
            elif hasattr(self.config, 'trading') and self.config.trading:
                backoff_ms = list(getattr(self.config.trading, 'execution', {}).get(
                    'preflight_backoff_ms', [150, 300, 500]))  # type: ignore
            elif isinstance(self.config, dict):
                backoff_ms = (
                    self.config.get('execution', {}).get(
                        'preflight_backoff_ms')
                    or self.config.get('trading', {}).get('execution', {}).get('preflight_backoff_ms')
                    or [150, 300, 500]
                )
            else:
                backoff_ms = [150, 300, 500]
        except Exception:
            backoff_ms = [150, 300, 500]
        tries = 0
        start = time.time()

        while True:
            tries += 1
            try:
                positions = await self._call_adapter_fn(self.adapter.get_open_positions, symbol)
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
                    self._orphan_metrics["tp_sl_skipped_no_position"] = self._orphan_metrics.get(
                        "tp_sl_skipped_no_position", 0) + 1
                    return False

                # Wait before next retry
                await asyncio.sleep(backoff_ms[tries - 1] / 1000.0)

            except Exception as e:
                LOG.warning(
                    f"⚠️ [PHASE A3] PRE-FLIGHT ERROR for {symbol} (try {tries}): {e}")
                if tries > len(backoff_ms):
                    return False
                await asyncio.sleep(backoff_ms[tries - 1] / 1000.0)

    async def _preflight_position_check_nonzero(self, symbol: str) -> bool:
        """Alternative pre-flight: allow any non-zero positionAmt (BOTH/LONG/SHORT)."""
        try:
            positions = await self._call_adapter_fn(self.adapter.get_open_positions, symbol)
            positions_list = [
                p.to_dict() if hasattr(p, 'to_dict') else (
                    p.__dict__ if not isinstance(p, dict) else p)
                for p in positions
            ]

            sym_positions = [
                p for p in positions_list if p.get("symbol") == symbol]
            if not sym_positions:
                LOG.warning(
                    f"dYs� [PHASE A3] PRE-FLIGHT FAILED: No position data for {symbol}")
                return False

            pos_nonzero = None
            for _p in sym_positions:
                try:
                    _amt = float(_p.get("positionAmt", 0))
                    if abs(_amt) >= 1e-8:
                        pos_nonzero = _p
                        break
                except Exception:
                    continue

            if pos_nonzero is None:
                LOG.warning(
                    f"dYs� [PHASE A3] PRE-FLIGHT SKIPPED: Position is 0 for {symbol} (TP_SL_SKIPPED_NO_POSITION)")
                self._orphan_metrics["tp_sl_skipped_no_position"] = self._orphan_metrics.get(
                    "tp_sl_skipped_no_position", 0) + 1
                return False

            position_amt = float(pos_nonzero.get("positionAmt", 0))
            LOG.debug(
                f"�o. [PHASE A3] PRE-FLIGHT OK: Position {position_amt} for {symbol}")
            return True

        except Exception as e:
            LOG.warning(
                f"�s��,? [PHASE A3] PRE-FLIGHT ERROR for {symbol}: {e}")
            return False

    async def _cleanup_loop(self) -> None:
        """Periodic orphaned-order cleanup loop (interval from config)."""
        while True:
            try:
                interval = max(
                    5, int(self._orphan_cfg.get("periodic_interval_sec", 300)))
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
        # Guard against concurrent or duplicate startup reconcile runs
        if getattr(self, "_startup_reconcile_running", False):
            LOG.debug(
                "startup_order_guardian_reconcile: already running; skipping duplicate call")
            return
        self._startup_reconcile_running = True
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

            # Then (later) run cleanup to remove orphans - defer to final sync step
            # Note: A single cleanup sweep is performed at the end of this method
        except Exception as e:
            LOG.error(f"❌ OrderGuardian startup reconciliation failed: {e}")
        finally:
            self._startup_reconcile_running = False
        """
        Synchronize open orders and positions with Binance at startup.

        This ensures the system state matches reality after manual interventions
        or restarts. Cancels orphaned orders and reconciles positions.
        """
        if not self.adapter:
            LOG.warning(
                "Adapter not initialized, skipping order/position sync")
            return

        try:
            # 🧹 STARTUP: Clear stale pending_exposure from previous run
            self.exposure_guard.cleanup_all_pending()

            LOG.info("🔄 Starting synchronization with Binance...")

            # 1. Get all open orders from Binance
            all_open_orders = await self.adapter.get_open_orders()
            LOG.info(f"📋 Found {len(all_open_orders)} open orders on Binance")

            # Group orders by symbol
            orders_by_symbol = {}
            # Convert orders to dict if needed
            orders_list = [
                o.to_dict() if hasattr(o, 'to_dict') else (
                    o.__dict__ if not isinstance(o, dict) else o)
                for o in all_open_orders
            ]

            # 🔍 Diagnostic: Log TP/SL and bracket orders separately
            tp_sl_orders = [o for o in orders_list if o.get(
                "type") in ["TAKE_PROFIT_MARKET", "STOP_MARKET"]]
            entry_orders = [o for o in orders_list if o.get("type") in [
                "MARKET", "LIMIT"]]
            if tp_sl_orders:
                LOG.warning(
                    f"⚠️  ORPHANED_TP_SL_CHECK: {len(tp_sl_orders)} TP/SL orders still open:")
                for o in tp_sl_orders:
                    LOG.warning(f"   📌 {o.get('symbol')} {o.get('clientOrderId')}: "
                                f"{o.get('type')} @{o.get('stopPrice')} "
                                f"(status={o.get('status')}, closePosition={o.get('closePosition')})")
            if entry_orders:
                LOG.info(f"📍 {len(entry_orders)} entry orders (MARKET/LIMIT)")

            for order in orders_list:
                symbol = order.get("symbol")
                if symbol not in orders_by_symbol:
                    orders_by_symbol[symbol] = []
                orders_by_symbol[symbol].append(order)

            # 2. Get all positions from Binance
            positions = await self.adapter.get_open_positions()
            LOG.info(f"📊 Found {len(positions)} positions on Binance")

            # Convert positions to dict if needed
            positions_list = [
                p.to_dict() if hasattr(p, 'to_dict') else (
                    p.__dict__ if not isinstance(p, dict) else p)
                for p in positions
            ]

            # ✅ NEW: Use order_guardian.cleanup_orphans() for centralized cleanup
            # This ensures consistent orphan detection across startup and runtime
            LOG.info("🧹 Running orphan cleanup on startup...")
            await self.order_guardian.cleanup_orphans()  # Scans ALL symbols exactly once
            LOG.info("✅ Startup orphan cleanup completed")

            # 3. For each position, check if we have matching FSM state
            for pos in positions_list:
                symbol = pos.get("symbol")
                position_amt = float(pos.get("positionAmt", 0))

                if abs(position_amt) >= 0.0001:
                    # Position exists - check if we have FSM state
                    LOG.info(
                        f"📈 {symbol}: Position {position_amt}, checking FSM state...")

                    # Ensure we have FSMs created (thread-safe via _get_or_create_flows)
                    _, manage_flow, _ = self._get_or_create_flows(symbol)
                    LOG.info(
                        f"✅ {symbol}: FSMs ready, manage flow initialized")

            LOG.info("✅ Synchronization complete")

        except Exception as e:
            LOG.error(
                f"❌ Error during order/position sync: {e}", exc_info=True)

    async def _update_portfolio_after_timeout_cancellation(self, symbol: str) -> None:
        """
        ✅ FIX: Update portfolio state after successful timeout cancellation.

        This ensures decision_making knows the position was never opened,
        allowing new position attempts for the same symbol.

        Args:
            symbol: Trading pair that had the timed-out order
        """
        try:
            from vfoundation.core.fsm_emit_compat import emit_compat, Message

            # Get current portfolio state and update positions_count to 0 for this symbol
            current_state = self._latest_portfolio_state.copy()
            # Reset to allow new positions
            current_state["positions_count"] = 0
            current_state["open_positions_usd"] = "0"  # No open positions
            current_state["last_updated"] = int(time.time() * 1000)

            # Emit EVT:PORTFOLIO_STATE_UPDATED to notify decision_making
            portfolio_msg = Message(
                op="EVT",
                verb="PORTFOLIO_STATE_UPDATED",
                src="execution_position",
                dst="decision_making",
                rid=f"timeout_cancel_{symbol}_{int(time.time())}",
                pld={
                    "portfolio_state": current_state,
                    "symbol": symbol,
                    "reason": "timeout_cancellation",
                    "timestamp_ms": int(time.time() * 1000)
                },
                why="portfolio_state_reset_after_timeout_cancellation",
            )

            await emit_compat(self.fsm, portfolio_msg, logger=LOG)
            LOG.info(
                f"✅ Portfolio state reset after timeout cancellation for {symbol}")

        except Exception as e:
            LOG.error(
                f"❌ Failed to update portfolio state after timeout cancellation for {symbol}: {e}")
