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
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple

from vfoundation.core.fsm_emit_compat import Message, emit_compat
from vfoundation.dr import wal
from apps.reference.adapters.binance_adapter import BinanceAdapter, BinanceAPIError

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
            "skipped_age": 0,
            "skipped_rate_limit": 0,
            "errors": 0,
        }
        self._orphan_rate_window_start: float = 0.0
        self._orphan_rate_count: int = 0

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
            self.watchdog.start()  # Start timeout watchdog
            # Start orphaned-order cleanup loop (best-effort)
            try:
                loop = asyncio.get_event_loop()
                if loop and not self._bg_started:
                    # Schedule startup sync if configured
                    if self._orphan_cfg.get("enabled") and self._orphan_cfg.get("run_on_startup"):
                        loop.create_task(self.sync_open_orders_and_positions())
                    # Periodic loop
                    if self._orphan_cfg.get("enabled"):
                        loop.create_task(self._cleanup_loop())
                    self._bg_started = True
            except RuntimeError:
                # No running loop yet
                pass

    def _on_portfolio_state_updated(self, event: Message) -> None:
        """
        Handle EVT:PORTFOLIO_STATE_UPDATED events to update exposure guard state.

        EXP-FIX: Store latest portfolio state for exposure checks.
        EXP-LEVERAGE-001: Update exposure guard with portfolio data.
        """
        self._latest_portfolio_state = event.pld or {}

        # EXP-LEVERAGE-001: Update exposure guard with latest portfolio state
        self.exposure_guard.on_portfolio(self._latest_portfolio_state)

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
            try:
                asyncio.get_running_loop()  # Check for running loop
                asyncio.create_task(
                    emit_compat(self.fsm, expired_msg,
                                logger=getattr(self, "logger", None))
                )
            except RuntimeError:
                # No running loop, skip emission
                pass

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

        LOG.debug(
            f"[ACK] Processing ACK for {symbol} order {order_id} (rid={rid})")

        # Release pre-fill hold from exposure guard
        # NOTE: prefill_reservations was a design concept but not implemented in ExposureState
        # Only postfill_reservations exists. This handler just needs to handle the ACK event.
        if hasattr(self, "exposure_guard"):
            LOG.debug(f"[ACK] Order {order_id} acknowledged for {symbol}")

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

        LOG.debug(
            f"[FILL] Processing FILL for {symbol} order {order_id}, qty={filled_qty} (rid={rid})")

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
        try:
            loop = asyncio.get_event_loop()
            if loop:
                loop.create_task(self.cleanup_orphaned_bracket_orders(symbol))
        except RuntimeError:
            pass

    def shutdown(self):
        """Shutdown the FSM and cleanup resources."""
        if hasattr(self, 'watchdog') and self.watchdog:
            self.watchdog.stop()
        LOG.info("ExecPosFSM shutdown complete")

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
                        mode = self.self.config.trading_mode
                except (AttributeError, TypeError):
                    mode = "testnet"
        else:
            # Fallback to global mode
            try:
                if hasattr(self.config, 'trading') and self.config.trading:
                    mode = self.config.trading.mode
                elif isinstance(self.config, dict):
                    mode = self.self.config.trading_mode
            except (AttributeError, TypeError):
                mode = "testnet"
            LOG.info(f"ExecPosFSM using global trading_mode: {mode}")

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
        LOG.info(
            f"✅ BinanceAdapter initialized for ExecPosFSM with base URL: {self.adapter.base_url}"
        )

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
                f"ExecPosFSM received message without symbol: {msg.verb}")
            return None

        open_flow, manage_flow, close_flow = self._get_or_create_flows(symbol)
        result = None

        # Route to the correct FSM based on the message verb
        if msg.verb == "OPEN":
            # EXP-FIX: Fail-closed exposure check before processing CMD:OPEN
            if self._check_exposure_fail_closed(msg):
                return None  # Error already emitted
            result = open_flow.handle(msg)
        elif msg.verb in ["PARTIAL_FILL", "FILL", "TRADE_EXECUTED", "ORDER_UPDATED"]:
            manage_result = manage_flow.handle(msg)
            close_result = close_flow.handle(msg)
            result = manage_result if manage_result else close_result

            # EXP-FIX: Handle post-fill hold for FILLED orders
            if msg.verb == "FILL" and result:
                self._handle_fill_event(msg)

        elif msg.verb == "CLOSE":
            result = close_flow.handle(msg)
        else:
            result = manage_flow.handle(msg)

        # If a decision was made, log it and execute if not in shadow mode
        if result and result.op == "DEC":
            wal.append(result.model_dump())
            if not self.shadow_mode and self.adapter:
                # Asynchronously execute the trade decision
                loop = asyncio.get_event_loop()
                loop.create_task(self._execute_decision(result))

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
                        await self.adapter.cancel_order(symbol, order_id)
                        LOG.info(f"Cancelled order {order_id} for {symbol}")
                    except Exception as e:
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
                # Cancel tracked brackets
                br = self._symbol_brackets.get(symbol, {})
                tasks = []
                bracket_order_ids = []  # Track IDs for logging
                if br.get("sl_order_id"):
                    tasks.append(self.adapter.cancel_order(
                        symbol, br["sl_order_id"]))
                    bracket_order_ids.append(("SL", br["sl_order_id"]))
                if br.get("tp_order_id"):
                    tasks.append(self.adapter.cancel_order(
                        symbol, br["tp_order_id"]))
                    bracket_order_ids.append(("TP", br["tp_order_id"]))

                if tasks:
                    # ✅ NEW: Collect and verify cancel results
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for (bracket_type, order_id), result in zip(bracket_order_ids, results):
                        if isinstance(result, Exception):
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
                            cancel_status = result.get("status", "").upper()
                            if cancel_status == "CANCELED":
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
                await self.adapter.place_market_reduce_only(symbol, close_side, close_qty, new_client_order_id=close_id)
                LOG.info(
                    f"Close executed for {symbol}: side={close_side} qty={close_qty}")
                self._symbol_brackets.pop(symbol, None)

                # ✅ NEW: Ensure cleanup after manual CLOSE
                # Wait for position to settle, then cleanup any orphaned brackets
                await asyncio.sleep(2.0)
                await self.cleanup_orphaned_bracket_orders(symbol)
                LOG.info(
                    f"✅ Cleanup after manual CLOSE for {symbol} completed")

                return

            symbol = decision.pld["symbol"]
            side = decision.pld["side"].upper()
            qty = decision.pld["qty"]

            # Get mark price and filters
            mark = await self.adapter.get_mark_price(symbol)
            exchange_info = await self.adapter.get_exchange_info(symbol)
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

            # Place MARKET entry
            entry_id = generate_client_order_id("ENTRY", symbol)
            entry_resp = await self.adapter.place_market_entry(
                symbol, side, qty, entry_id
            )
            LOG.info(f"✅ MARKET entry placed: {entry_resp}")

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

            # Check for existing brackets to avoid duplicates
            open_orders = await self.adapter.get_open_orders(symbol)
            # Convert objects to dict if needed
            open_orders_list = [
                o.to_dict() if hasattr(o, 'to_dict') else (
                    o.__dict__ if not isinstance(o, dict) else o)
                for o in open_orders
            ]
            existing_sl = any(
                o.get("type") == "STOP_MARKET" and o.get(
                    "closePosition") == "true"
                for o in open_orders_list
            )
            existing_tp = any(
                (o.get("type") in ["TAKE_PROFIT_MARKET", "LIMIT"]
                 and o.get("closePosition") == "true")
                or o.get("reduceOnly") == "true"
                for o in open_orders_list
            )

            if existing_sl:
                LOG.warning(f"SL already exists for {symbol}, skipping")
            else:
                # Place SL
                sl_side = opposite_side(side)
                sl_id = generate_client_order_id("SL", symbol)

            if existing_tp:
                LOG.warning(f"TP already exists for {symbol}, skipping")
            else:
                # Place TP with retry/fallback
                tp_side = opposite_side(side)
                tp_id = generate_client_order_id("TP", symbol)

            # ✅ Place SL and TP in parallel (not sequentially)
            sl_resp = None
            tp_resp = None
            try:
                async def place_sl_async():
                    if existing_sl:
                        return None
                    return await self.adapter.place_stop_market_close_position(
                        symbol, sl_side, str(sl), new_client_order_id=sl_id
                    )

                async def place_tp_async():
                    if existing_tp:
                        return None
                    try:
                        return (
                            await self.adapter.place_take_profit_market_close_position(
                                symbol, tp_side, str(tp), new_client_order_id=tp_id
                            )
                        )
                    except BinanceAPIError as e:
                        if e.code == -2021:
                            # Retry with widened TP
                            tp_adj = tp * 1.002  # +20 bps approx
                            tp_adj = quantize_stop_price(
                                tp_adj, tick_size, side="BUY" if side == "BUY" else "SELL"
                            )
                            self.metrics_collector.record_retry(
                                "tp_adjust") if self.metrics_collector else None
                            try:
                                return await self.adapter.place_take_profit_market_close_position(
                                    symbol, tp_side, str(tp_adj), new_client_order_id=tp_id
                                )
                            except BinanceAPIError:
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
                if not existing_sl:
                    sl_resp = await self.adapter.place_stop_market_close_position(
                        symbol, sl_side, str(sl), new_client_order_id=sl_id
                    )
                if not existing_tp:
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
            if sl_resp:
                LOG.info(f"✅ SL placed: {sl_resp}")
                # Correlation: store SL ACK
                sl_order_id = str(sl_resp["orderId"])
                self.correlation_store.put_sl_tp_ack(
                    sl_order_id, entry_resp["clientOrderId"], decision.corr_id or "", decision.oco_group_id or "", decision.rid or "")
                # Track SL bracket per symbol
                self._symbol_brackets.setdefault(
                    symbol, {})["sl_order_id"] = sl_order_id

            if tp_resp:
                LOG.info(f"✅ TP placed: {tp_resp}")
                # Correlation: store TP ACK
                tp_order_id = str(tp_resp["orderId"])
                self.correlation_store.put_sl_tp_ack(
                    tp_order_id, entry_resp["clientOrderId"], decision.corr_id or "", decision.oco_group_id or "", decision.rid or "")
                # Track TP bracket per symbol
                self._symbol_brackets.setdefault(
                    symbol, {})["tp_order_id"] = tp_order_id

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
                "enabled": self._self.config.trading.execution.manage.orphan_monitor.enabled,
                "periodic_interval_sec": self._self.config.trading.execution.manage.orphan_monitor.periodic_interval_sec,
                "min_order_age_sec": self._self.config.trading.execution.manage.orphan_monitor.min_order_age_sec,
                "batch_cancel_limit": self._self.config.trading.execution.manage.orphan_monitor.batch_cancel_limit,
                "rate_limit_per_min": self._self.config.trading.execution.manage.orphan_monitor.rate_limit_per_min,
            },
        }

        return all_metrics

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
                cancel_result = await self.adapter.cancel_order(
                    deadline.symbol, deadline.order_id
                )

                # ✅ NEW: Verify cancel status from exchange response
                status = cancel_result.get("status", "").upper()
                if status == "CANCELED":
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
                try:
                    asyncio.get_running_loop()  # Check for running loop
                    asyncio.create_task(self._emit_error_async(error_msg))
                except RuntimeError:
                    # No running loop, emit synchronously if possible
                    try:
                        asyncio.get_running_loop()
                        asyncio.create_task(
                            emit_compat(self.fsm, error_msg,
                                        logger=getattr(self, "logger", None))
                        )
                    except RuntimeError:
                        # Really no loop, skip emission
                        pass
                return True

            # EXP-FIX: Periodic shadow notional check (every 10 requests approx)
            self._shadow_check_counter += 1

            if self._shadow_check_counter % 10 == 0 and self.adapter:
                try:
                    asyncio.get_running_loop()  # Check for running loop
                    asyncio.create_task(self._check_shadow_notional())
                except RuntimeError:
                    # No running loop, skip async check
                    pass

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

        # Notify watchdog of order fill
        order_id = pld.get("order_id")
        if order_id:
            self.watchdog.ensure_started()  # Safe late-start if needed
            self.watchdog.on_order_fill(order_id)

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

    async def cleanup_orphaned_bracket_orders(self, symbol: Optional[str] = None) -> None:
        """Cancel reduceOnly/closePosition bracket orders when no position exists (manual closes).

        Enhanced with optional min-age filter, batch limit, and simple rate limiting
        controlled via config manage.orphan_monitor.
        """
        if not self.adapter:
            return

        cancels_this_run = 0
        try:
            positions = await self.adapter.get_open_positions()
            # Convert positions to dict if they're objects
            positions_list = [
                p.to_dict() if hasattr(p, 'to_dict') else (
                    p.__dict__ if not isinstance(p, dict) else p)
                for p in positions
            ]
            active = {p.get("symbol")
                      for p in positions_list if p.get("symbol")}

            if symbol:
                symbols = [symbol]
                LOG.info(
                    f"🔄 [ORPHAN_CLEANUP] Starting cleanup for specific symbol: {symbol}")
            else:
                try:
                    all_orders = await self.adapter.get_open_orders()
                    # Convert orders to dict if they're objects
                    all_orders_list = [
                        o.to_dict() if hasattr(o, 'to_dict') else (
                            o.__dict__ if not isinstance(o, dict) else o)
                        for o in all_orders
                    ]
                    symbols = sorted({o.get("symbol")
                                     for o in all_orders_list if o.get("symbol")})
                    LOG.info(
                        f"🔄 [ORPHAN_CLEANUP] Starting cleanup scan for {len(symbols)} symbols, {len(active)} have active positions")
                except Exception:
                    symbols = []

            # Controls (from self._orphan_cfg which was initialized safely)
            min_age_sec = max(
                0, int(self._orphan_cfg.get("min_order_age_sec", 0)))
            batch_limit = max(
                0, int(self._orphan_cfg.get("batch_cancel_limit", 50)))
            rate_limit_per_min = max(
                0, int(self._orphan_cfg.get("rate_limit_per_min", 120)))
            now_ms = int(time.time() * 1000)

            def rate_limited(now_ts_ms: int) -> bool:
                # Reset window if older than 60s
                if now_ts_ms - int(self._orphan_rate_window_start * 1000) >= 60_000:
                    self._orphan_rate_window_start = now_ts_ms / 1000.0
                    self._orphan_rate_count = 0
                if rate_limit_per_min <= 0:
                    return False
                return self._orphan_rate_count >= rate_limit_per_min

            for sym in symbols:
                if not sym or sym in active:
                    continue
                try:
                    open_orders = await self.adapter.get_open_orders(sym)
                    # Convert orders to dict if they're objects
                    open_orders_list = [
                        o.to_dict() if hasattr(o, 'to_dict') else (
                            o.__dict__ if not isinstance(o, dict) else o)
                        for o in open_orders
                    ]
                except Exception as e:
                    LOG.warning(
                        f"cleanup: failed to fetch open orders for {sym}: {e}")
                    continue
                for o in open_orders_list:
                    otype = (o.get("type") or "").upper()
                    reduce_only = str(o.get("reduceOnly", "")
                                      ).lower() == "true"
                    close_pos = str(o.get("closePosition", "")
                                    ).lower() == "true"
                    if otype in ("STOP_MARKET", "TAKE_PROFIT_MARKET", "LIMIT") and (reduce_only or close_pos):
                        # Age filter (if timestamp available)
                        if min_age_sec > 0:
                            ts = (
                                o.get("updateTime")
                                or o.get("time")
                                or o.get("transactTime")
                                or o.get("origTime")
                                or o.get("createTime")
                            )
                            try:
                                ts_ms = int(ts)
                            except Exception:
                                ts_ms = None  # unknown age -> don't skip by age
                            if ts_ms is not None and (now_ms - ts_ms) < (min_age_sec * 1000):
                                self._orphan_metrics["skipped_age"] += 1
                                continue

                        # Batch limit
                        if batch_limit and cancels_this_run >= batch_limit:
                            break

                        # Rate limit per minute (shared across symbols)
                        if rate_limited(now_ms):
                            self._orphan_metrics["skipped_rate_limit"] += 1
                            continue

                        oid = o.get("orderId")
                        try:
                            await self.adapter.cancel_order(sym, oid)
                            # 📋 Детальний лог про скасований ордер
                            LOG.info(
                                f"✅ [ORPHAN_CLEANUP] Cancelled orphaned {otype} order {oid} for {sym} "
                                f"(reduceOnly={reduce_only}, closePosition={close_pos})")
                            cancels_this_run += 1
                            self._orphan_metrics["cancels"] += 1
                            self._orphan_rate_count += 1
                        except Exception as e:
                            LOG.warning(
                                f"❌ [ORPHAN_CLEANUP] Failed to cancel {otype} order {oid} for {sym}: {e}")
                            self._orphan_metrics["errors"] += 1
                # If batch limit reached for this run, stop scanning further symbols
                if batch_limit and cancels_this_run >= batch_limit:
                    break
        except Exception as e:
            LOG.debug(f"cleanup_orphaned_bracket_orders error: {e}")
            self._orphan_metrics["errors"] += 1

        # 📊 Логування результату cleanup
        if cancels_this_run > 0:
            LOG.info(f"✅ [ORPHAN_CLEANUP] Completed: cancelled {cancels_this_run} orders "
                     f"(skipped_age={self._orphan_metrics.get('skipped_age', 0)}, "
                     f"skipped_rate_limit={self._orphan_metrics.get('skipped_rate_limit', 0)})")

    async def _cleanup_loop(self) -> None:
        """Periodic orphaned-order cleanup loop (interval from config)."""
        while True:
            try:
                interval = max(
                    5, int(self._orphan_cfg.get("periodic_interval_sec", 300)))
                await asyncio.sleep(interval)
                await self.cleanup_orphaned_bracket_orders()
                self._orphan_metrics["loops"] += 1
            except asyncio.CancelledError:
                raise
            except Exception as e:
                LOG.debug(f"cleanup loop error: {e}")
                self._orphan_metrics["errors"] += 1

    async def sync_open_orders_and_positions(self) -> None:
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

            # ✅ NEW: Use cleanup_orphaned_bracket_orders instead of duplicating logic
            # This ensures consistent orphan detection across startup and runtime
            LOG.info("🧹 Running orphan cleanup on startup...")
            await self.cleanup_orphaned_bracket_orders()  # Scans ALL symbols
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
