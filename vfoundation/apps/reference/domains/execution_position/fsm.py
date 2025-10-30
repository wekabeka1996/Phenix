"""
FSMP-P1-T02: Orchestration of 3 FSM flows for execution_position domain.

Registry: open_flow, manage_flow, close_flow
Metrics: aggregated from all flows + decision latency
Shadow-mode: all flows use stub logic, no live API calls.
"""

from __future__ import annotations

import time
from decimal import Decimal
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from vfoundation.core.fsm import FSM
from vfoundation.core.protocol import Message
from vfoundation.dr import wal

from .fsm_open import OpenFlowFSM
from .fsm_manage import ManageFlowFSM, ManageState
from .fsm_close import CloseFlowFSM, CloseState
from .execution_adapter import AbstractExecutionAdapter
from .simulated_adapter import SimulatedExecutionAdapter
from .aurora_log_adapter import AuroraLogAdapter
from .metrics_collector import MetricsCollector
from .exposure_guard import ExposureGuard

try:
    from .binance_execution_adapter import BinanceExecutionAdapter
except ImportError:
    BinanceExecutionAdapter = None

from vfoundation.apps.reference.telemetry.metrics import (
    update_exposure,
    inc_exposure_guard_block,
    inc_pending_expired,
    inc_order_state,
)
from .order_index import OrderIndex
from vfoundation.apps.reference.telemetry.audit_logger import audit_logger
from vfoundation.apps.reference.domains.risk_management.daily_gate import DailyRiskState


def _utc_hm() -> tuple[int, int]:
    """Get current UTC hour and minute."""
    now = datetime.now(timezone.utc)
    return now.hour, now.minute


def _in_quiet(quiet: list[str]) -> bool:
    """Check if current UTC time is within any quiet hour window."""
    h, m = _utc_hm()
    cur = h * 60 + m
    for win in quiet or []:
        a, b = win.split("-")
        ah, am = map(int, a.split(":"))
        bh, bm = map(int, b.split(":"))
        start = ah * 60 + am
        end = bh * 60 + bm
        if start <= end:
            # Normal range
            if start <= cur <= end:
                return True
        else:
            # Wraps around midnight
            if cur >= start or cur <= end:
                return True
    return False


class ExecPosFSM:
    """Wrapper FSM class for execution_position domain with shadow mode support."""

    def __init__(
        self,
        config: Any,
        fsm: Any,
        shadow_mode: bool = False,
        adapter: Optional[AbstractExecutionAdapter] = None,
    ):
        self.config = config
        self.fsm = fsm
        self.shadow_mode = shadow_mode
        self.logger = logging.getLogger(__name__)

        # Initialize adapter: use provided, create simulator by default, or None in shadow mode
        if adapter:
            self.adapter: Optional[AbstractExecutionAdapter] = adapter
        elif not self.shadow_mode:
            # Try BinanceExecutionAdapter first, fallback to SimulatedExecutionAdapter
            if BinanceExecutionAdapter is not None:
                try:
                    self.adapter = BinanceExecutionAdapter(shadow_mode=False, fsm_core=self)

                    # Initialize margin settings (leverage and margin type) for all instruments
                    instruments_config = config.trading.get("instruments", {})
                    if instruments_config and hasattr(self.adapter, "initialize_margin_settings"):
                        self.logger.info(
                            "Initializing leverage and margin settings for instruments..."
                        )
                        self.adapter.initialize_margin_settings(instruments_config)

                except Exception as e:
                    self.logger.warning(
                        f"Failed to init BinanceExecutionAdapter: {e}, using SimulatedExecutionAdapter"
                    )
                    self.adapter = SimulatedExecutionAdapter()
            else:
                self.adapter = SimulatedExecutionAdapter()
        else:
            self.adapter = None  # In shadow_mode adapter not needed

        # Read execution config with defaults
        exec_config = config.trading.get("execution", {})

        # Parse cooldown_ms with proper type conversion
        cooldown_ms_raw = exec_config.get("cooldown_ms", 1000)
        try:
            cooldown_ms = float(cooldown_ms_raw)
        except (ValueError, TypeError):
            self.logger.warning(
                f"Invalid cooldown_ms value '{cooldown_ms_raw}', using default 1000ms"
            )
            cooldown_ms = 1000.0

        cooldown_sec = cooldown_ms / 1000.0  # Convert ms to seconds
        guard_enabled = exec_config.get("guard_enabled", True)

        # Initialize Exposure Guard for portfolio risk management
        self.exposure_guard = ExposureGuard(exec_config)

        self.open_flow = OpenFlowFSM(
            cooldown_sec=cooldown_sec,
            guard_enabled=guard_enabled,
            config=config,
            exposure_guard=self.exposure_guard,
        )
        self.manage_flow = ManageFlowFSM(trail_pct=0.5, breakeven_after_sec=300.0)
        self.close_flow = CloseFlowFSM(max_hold_sec=7200.0)

        # Initialize Aurora Log Adapter for enhanced trade logging
        self.log_adapter = AuroraLogAdapter()

        # Initialize Metrics Collector for monitoring trade patterns
        self.metrics_collector = MetricsCollector()

        # Initialize Order Index for lifecycle correlation (AUR-004)
        self.order_index = OrderIndex(ttl_sec=3600)  # 1 hour TTL

        # Initialize Daily Risk Gate (PACK PROD-1)
        self.daily_gate = DailyRiskState(cfg=self.config, logger=self.logger)

        # Exposure fraction for metrics
        ex = exec_config.get("exposure", {})
        self._exposure_fraction = float(ex.get("max_portfolio_fraction", 0.20))

    def handle(self, msg: Message) -> Optional[Message]:
        """Route message to appropriate flow based on verb."""
        if msg.verb == "OPEN":
            # Log trade intent with enhanced details
            pld = msg.pld or {}
            symbol = pld.get("symbol", "")
            side = pld.get("side", "")

            # Extract order details if present (from decision_making these are in nested structure)
            order_details = pld.get("order", {})

            # Convert all numeric values to Decimal if they are strings (for precision preservation)
            # WARN: For logging only, do not use in calculations
            def safe_decimal(val: Any) -> Optional[Decimal]:
                if val is None:
                    return None
                try:
                    return Decimal(str(val)) if isinstance(val, (str, int, float)) else None
                except (ValueError, TypeError):
                    return None

            self.log_adapter.log_trade_intent(
                rid=msg.rid,
                symbol=symbol,
                side=side,
                probability=float(safe_decimal(pld.get("probability")))
                if safe_decimal(pld.get("probability")) is not None
                else None,
                size=float(safe_decimal(pld.get("size")))
                if safe_decimal(pld.get("size")) is not None
                else None,
                price=float(safe_decimal(order_details.get("price") or pld.get("price")))
                if safe_decimal(order_details.get("price") or pld.get("price")) is not None
                else None,
                qty=float(safe_decimal(order_details.get("qty") or pld.get("qty")))
                if safe_decimal(order_details.get("qty") or pld.get("qty")) is not None
                else None,
                risk_score=float(safe_decimal(pld.get("risk_score")))
                if safe_decimal(pld.get("risk_score")) is not None
                else None,
                features=pld.get("features"),
            )

            # Record intent in metrics
            self.metrics_collector.record_trade_intent(
                symbol=symbol,
                side=side,
                rid=msg.rid,
                probability=pld.get("probability"),
                size=pld.get("size"),
            )

            # PACK PROD-2: Check ops guards before any other processing
            ops_cfg = self.config.get("ops") or {}

            # 1) PANIC KILLSWITCH
            if bool(ops_cfg.get("panic_killswitch", False)):
                result = Message(
                    op="ERR",
                    verb="OPEN",
                    intent="REJECTION",
                    src="execution_position",
                    dst=msg.src,
                    rid=msg.rid,
                    pld={"reason": "PANIC_ON"},
                    why="panic_kill",
                )
                # Log rejection
                self.log_adapter.log_guard_rejection(
                    rid=msg.rid, symbol=symbol, side=side, guard_type="PANIC", reason="PANIC_ON"
                )
                # Record rejection in metrics
                self.metrics_collector.record_trade_decision(
                    symbol=symbol, side=side, decision="REJECTED", reason="PANIC_ON", rid=msg.rid
                )
                return result

            # 2) QUIET HOURS
            if _in_quiet(ops_cfg.get("quiet_hours_utc") or []):
                result = Message(
                    op="ERR",
                    verb="OPEN",
                    intent="REJECTION",
                    src="execution_position",
                    dst=msg.src,
                    rid=msg.rid,
                    pld={"reason": "QUIET_HOURS"},
                    why="quiet_window",
                )
                # Log rejection
                self.log_adapter.log_guard_rejection(
                    rid=msg.rid,
                    symbol=symbol,
                    side=side,
                    guard_type="QUIET_HOURS",
                    reason="QUIET_HOURS",
                )
                # Record rejection in metrics
                self.metrics_collector.record_trade_decision(
                    symbol=symbol, side=side, decision="REJECTED", reason="QUIET_HOURS", rid=msg.rid
                )
                return result

            # 3) ALLOWLIST SYMBOLS
            allow = ops_cfg.get("allowlist_symbols") or []
            sym = (msg.pld or {}).get("symbol", "").upper()
            if allow and sym not in set(x.upper() for x in allow):
                result = Message(
                    op="ERR",
                    verb="OPEN",
                    intent="REJECTION",
                    src="execution_position",
                    dst=msg.src,
                    rid=msg.rid,
                    pld={"reason": "SYMBOL_NOT_ALLOWED", "symbol": sym, "allow": allow},
                    why="symbol_not_allowlisted",
                )
                # Log rejection
                self.log_adapter.log_guard_rejection(
                    rid=msg.rid,
                    symbol=symbol,
                    side=side,
                    guard_type="ALLOWLIST",
                    reason="SYMBOL_NOT_ALLOWED",
                )
                # Record rejection in metrics
                self.metrics_collector.record_trade_decision(
                    symbol=symbol,
                    side=side,
                    decision="REJECTED",
                    reason="SYMBOL_NOT_ALLOWED",
                    rid=msg.rid,
                )
                return result

            result = self.open_flow.handle(msg)

            # PACK PROD-1: Check daily risk gate after exposure guard
            if result and result.op == "DEC":
                ok, data = self.daily_gate.can_open()
                if not ok:
                    # Daily gate rejection - emit ERR:OPEN
                    result = Message(
                        op="ERR",
                        verb="OPEN",
                        intent="REJECTION",
                        src="execution_position",
                        dst=msg.src,
                        rid=msg.rid,
                        pld=data,
                        why="daily_gate_block",
                    )
                    # Log rejection
                    self.log_adapter.log_guard_rejection(
                        rid=msg.rid,
                        symbol=symbol,
                        side=side,
                        guard_type="DAILY_RISK",
                        reason=data.get("reason", "DAILY_RISK_LIMIT"),
                    )
                    # Record rejection in metrics
                    self.metrics_collector.record_trade_decision(
                        symbol=symbol,
                        side=side,
                        decision="REJECTED",
                        reason="DAILY_RISK_LIMIT",
                        rid=msg.rid,
                    )

            # Handle exposure guard release on rejection or adapter failure
            if result and result.op == "ERR":
                # Release reserved exposure on guard rejection
                reserve_key = msg.pld.get("idempotent_key") or msg.rid or f"rid_{msg.rid}"
                self.exposure_guard.release(reserve_key)

                # Increment exposure guard reject counter for exposure limit rejections
                if (result.pld or {}).get("reason") == "PORTFOLIO_EXPOSURE_LIMIT":
                    inc_exposure_guard_block()

            # Log decision based on result
            if result and result.op == "ERR":
                # Guard rejection
                reason = result.pld.get("reason", "unknown") if result.pld else "unknown"
                guard_type = (
                    "COOLDOWN"
                    if "cooldown" in reason
                    else "EXPOSURE"
                    if reason == "PORTFOLIO_EXPOSURE_LIMIT"
                    else "DAILY"
                    if reason == "DAILY_RISK_LIMIT"
                    else "PANIC"
                    if reason == "PANIC_ON"
                    else "QUIET_HOURS"
                    if reason == "QUIET_HOURS"
                    else "ALLOWLIST"
                    if reason == "SYMBOL_NOT_ALLOWED"
                    else "OTHER"
                )
                self.log_adapter.log_guard_rejection(
                    rid=msg.rid, symbol=symbol, side=side, guard_type=guard_type, reason=reason
                )

                # Record rejection in metrics
                self.metrics_collector.record_trade_decision(
                    symbol=symbol, side=side, decision="REJECTED", reason=reason, rid=msg.rid
                )

            elif result and result.op == "DEC":
                # Trade accepted
                self.log_adapter.log_trade_decision(
                    rid=msg.rid, symbol=symbol, side=side, decision="ACCEPTED"
                )

                # Record acceptance in metrics
                self.metrics_collector.record_trade_decision(
                    symbol=symbol, side=side, decision="ACCEPTED", rid=msg.rid
                )
        elif msg.verb in ["PARTIAL_FILL", "FILL"]:
            result = self.manage_flow.handle(msg)
        elif msg.verb == "CLOSE":
            result = self.close_flow.handle(msg)
        elif msg.verb == "PORTFOLIO_STATE_UPDATED":
            # Handle portfolio state updates for exposure guard
            self.exposure_guard.on_portfolio_update(msg.pld or {})
            # Handle portfolio state updates for daily gate (PACK PROD-1)
            self.daily_gate.on_portfolio(msg.pld or {})
            expired = self.exposure_guard.expire_stale()
            if expired:
                inc_pending_expired(len(expired))
                result = Message(
                    op="EVT",
                    verb="PENDING_EXPOSURE_EXPIRED",
                    intent="OBSERVATION",
                    src="execution_position",
                    dst="any",
                    rid=msg.rid,
                    pld={"expired_keys": expired, "why": "ttl_expired"},
                    why="expire_pending",
                )
            else:
                # Emit exposure snapshot
                snap = self.exposure_guard.metrics_snapshot()
                result = Message(
                    op="EVT",
                    verb="PORTFOLIO_EXPOSURE_UPDATED",
                    intent="OBSERVATION",
                    src="execution_position",
                    dst="any",
                    rid=msg.rid,
                    pld=snap,
                    why="exposure_snapshot",
                )
            # Update exposure metrics
            update_exposure(
                equity_usd=(msg.pld or {}).get("equity_free_usdt"),
                positions_usd=self.exposure_guard.state.open_positions_usd,
                pending_usd=self.exposure_guard.state.pending_open_usd,
                fraction=self._exposure_fraction,
            )

            # AUR-004: Expire old order references
            expired_orders = self.order_index.expire()
            if expired_orders > 0:
                self.logger.debug(f"Expired {expired_orders} old order references")
        else:
            # For other messages, try manage flow as default
            result = self.manage_flow.handle(msg)

        # Release hooks for pending exposure on terminal events
        if msg.op == "ERR" and msg.verb == "OPEN":
            reserve_key = (msg.pld or {}).get("idempotent_key") or msg.rid
            self.exposure_guard.release(reserve_key)
            # Increment exposure guard reject counter
            if (msg.pld or {}).get("reason") == "PORTFOLIO_EXPOSURE_LIMIT":
                inc_exposure_guard_block()
            result = None  # ERR already handled
        elif msg.op == "EVT" and msg.verb in (
            "ORDER_REJECTED",
            "ORDER_CANCELED",
            "ORDER_FILLED",
            "POSITION_OPENED",
        ):
            reserve_key = (msg.pld or {}).get("idempotent_key") or msg.rid
            self.exposure_guard.release(reserve_key)
            result = None  # Event handled
        elif msg.op == "EVT" and msg.verb == "ORDER_STATE_CHANGED":
            # PACK PROD-1: Accumulate realized PnL for daily gate
            st = (msg.pld or {}).get("status", "").upper()
            if st == "FILLED":
                self.daily_gate.on_order_filled(msg.pld or {})
            result = None  # Event handled

        if result and result.op == "DEC" and not self.shadow_mode:
            wal.append(result.model_dump())
            # Integrate adapter: call place_order for DEC:OPEN
            if result.verb == "OPEN" and self.adapter:
                try:
                    feedback = self.adapter.place_order(result)

                    # AUR-004: Order Lifecycle Correlation
                    # Upsert order reference and emit ORDER_STATE_CHANGED NEW
                    pld = result.pld or {}
                    self.order_index.upsert_from_open(
                        rid=result.rid,
                        idempotent_key=pld.get("idempotent_key"),
                        clientOrderId=feedback.get("clientOrderId"),
                        symbol=pld.get("symbol", ""),
                        side=pld.get("side", ""),
                        order_type=pld.get("order_type", "MARKET"),
                    )

                    # Emit ORDER_STATE_CHANGED event
                    order_state_event = Message(
                        op="EVT",
                        verb="ORDER_STATE_CHANGED",
                        intent="OBSERVATION",
                        src="execution_position",
                        dst="any",
                        rid=result.rid,
                        pld={
                            "symbol": pld.get("symbol", ""),
                            "status": "NEW",
                            "rid": result.rid,
                            "idempotent_key": pld.get("idempotent_key"),
                            "clientOrderId": feedback.get("clientOrderId"),
                            "exchangeOrderId": feedback.get("orderId"),
                            "side": pld.get("side", ""),
                            "order_type": pld.get("order_type", "MARKET"),
                            "qty": pld.get("qty", "0"),
                            "ts_ms": int(time.time() * 1000),
                        },
                        why="order_placed",
                    )

                    # Attach exchange ID if available
                    if feedback.get("orderId"):
                        self.order_index.attach_exchange_id(
                            clientOrderId=feedback.get("clientOrderId"),
                            exchangeOrderId=feedback.get("orderId"),
                        )

                    # Log to audit and increment metrics
                    audit_logger.log_order_state_changed(
                        rid=result.rid,
                        idempotent_key=pld.get("idempotent_key"),
                        clientOrderId=feedback.get("clientOrderId"),
                        exchangeOrderId=feedback.get("orderId"),
                        symbol=pld.get("symbol", ""),
                        status="NEW",
                        qty=pld.get("qty"),
                        why="order_placed",
                        ts_ms=int(time.time() * 1000),
                    )
                    inc_order_state("NEW")

                    self.logger.info(f"Adapter placed order: {feedback}")
                    # Return the order state event instead of None
                    return order_state_event

                except Exception as e:
                    self.logger.error(f"Adapter failed to place order: {e}")
                    # Release reserved exposure on adapter failure
                    reserve_key = (
                        result.pld.get("idempotent_key") or result.rid or f"rid_{result.rid}"
                    )
                    self.exposure_guard.release(reserve_key)

        return result

    def handle_event(self, msg: Message) -> Optional[Message]:
        """
        Compatibility alias for handle() to support vFoundation FSM API.

        This method exists for backward compatibility with code expecting
        the vFoundation FSM interface. It delegates to handle().
        """
        return self.handle(msg)

    def _handle_portfolio_state_recovery(self, msg: Message) -> None:
        """
        Handle portfolio state recovery on system restart.
        Restore FSM states based on current open positions.
        """
        pld = msg.pld or {}
        positions = pld.get("positions", [])

        # Get symbol from config (assuming single symbol per FSM instance)
        symbol = self.config.get("instruments", {}).get("symbol", "BTCUSDT")

        # Find position for this symbol
        position = None
        for pos in positions:
            if pos.get("symbol") == symbol:
                position = pos
                break

        if position:
            position_qty = float(position.get("net_position", 0))
            if abs(position_qty) > 1e-9:  # Position exists
                # Restore ManageFlowFSM state
                if self.manage_flow.state == ManageState.FLAT:
                    # Simulate fill event to restore state
                    fake_fill_msg = Message(
                        op="EVT",
                        verb="FILL",
                        src="position_tracking",
                        dst="execution_position",
                        rid="RECOVERY",
                        pld={
                            "symbol": symbol,
                            "qty": str(position_qty),
                            "price": str(position.get("avg_entry_price", 0)),
                        },
                    )
                    self.manage_flow.handle(fake_fill_msg)
                    print(
                        f"[FSM_RECOVERY] ManageFlowFSM restored to TRACKING for {symbol}, qty={position_qty}"
                    )

                # Restore CloseFlowFSM state
                if self.close_flow.state == CloseState.FLAT:
                    # Simulate fill event to restore state
                    fake_fill_msg = Message(
                        op="EVT",
                        verb="FILL",
                        src="position_tracking",
                        dst="execution_position",
                        rid="RECOVERY",
                        pld={
                            "symbol": symbol,
                            "filled_qty": abs(
                                position_qty
                            ),  # Any positive value to trigger transition
                        },
                    )
                    self.close_flow.handle(fake_fill_msg)
                    print(
                        f"[FSM_RECOVERY] CloseFlowFSM restored to OPENED for {symbol}, qty={position_qty}"
                    )

    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive trading metrics."""
        return {
            "summary": self.metrics_collector.get_summary_metrics(),
            "rejection_patterns": self.metrics_collector.get_rejection_patterns(),
            "open_flow_metrics": self.open_flow.get_metrics(),
            "manage_flow_metrics": self.manage_flow.get_metrics(),
            "close_flow_metrics": self.close_flow.get_metrics(),
        }

    def get_symbol_metrics(self, symbol: str) -> Dict[str, Any]:
        """Get metrics for a specific symbol."""
        return self.metrics_collector.get_symbol_metrics(symbol)


# Global FSM registry
fsm = FSM("execution_position")

# Instantiate 3 flows
open_flow = OpenFlowFSM(cooldown_sec=1.0)
manage_flow = ManageFlowFSM(trail_pct=0.5, breakeven_after_sec=300.0)
close_flow = CloseFlowFSM(max_hold_sec=7200.0)

# Metrics aggregation
_decision_latencies: list[float] = []


@fsm.on("CMD", "OPEN")
def on_cmd_open(msg: Message) -> Optional[Message]:
    """Route CMD:OPEN to open_flow."""
    start = time.perf_counter()
    result = open_flow.handle(msg)
    _record_latency(time.perf_counter() - start)

    if result and result.op == "DEC":
        wal.append(result.model_dump())

    return result


@fsm.on("EVT", "PARTIAL_FILL")
@fsm.on("EVT", "FILL")
@fsm.on("UPD", "*")
def on_events(msg: Message) -> Optional[Message]:
    """Route events to manage_flow and close_flow."""
    start = time.perf_counter()

    # Check manage_flow first
    adjust_dec = manage_flow.handle(msg)
    if adjust_dec:
        wal.append(adjust_dec.model_dump())
        _record_latency(time.perf_counter() - start)
        return adjust_dec

    # Check close_flow
    close_dec = close_flow.handle(msg)
    if close_dec:
        wal.append(close_dec.model_dump())
        _record_latency(time.perf_counter() - start)
        return close_dec

    _record_latency(time.perf_counter() - start)
    return None


@fsm.on("EVT", "REJECTED")
@fsm.on("EVT", "EXPIRED")
def on_error_events(msg: Message) -> Optional[Message]:
    """Route error events to close_flow."""
    start = time.perf_counter()
    result = close_flow.handle(msg)
    _record_latency(time.perf_counter() - start)

    if result:
        wal.append(result.model_dump())

    return result


@fsm.on("TIMER", "*")
def on_timer(msg: Message) -> Optional[Message]:
    """Route timer ticks to close_flow."""
    start = time.perf_counter()
    result = close_flow.handle(msg)
    _record_latency(time.perf_counter() - start)

    if result:
        wal.append(result.model_dump())

    return result


def _record_latency(latency_sec: float) -> None:
    """Record decision latency for p95 calculation."""
    global _decision_latencies
    _decision_latencies.append(latency_sec * 1000)  # Convert to ms

    # Keep only last 1000 measurements
    if len(_decision_latencies) > 1000:
        _decision_latencies = _decision_latencies[-1000:]


def get_metrics() -> Dict[str, Any]:
    """
    Aggregate metrics from all flows + decision latency.

    Returns:
        Dict with: fsm_decision_ms_p95, fsm_open_decisions_total,
                   fsm_adjust_decisions_total, fsm_close_decisions_total,
                   fsm_guard_rejects_total, fsm_errors_total
    """
    metrics = {
        "fsm_decision_ms_p95": _calculate_p95(_decision_latencies),
        "fsm_open_decisions_total": 0,
        "fsm_adjust_decisions_total": 0,
        "fsm_close_decisions_total": 0,
        "fsm_guard_rejects_total": 0,
        "fsm_errors_total": 0,
    }

    # Aggregate from flows
    from typing import cast
    from .fsm_open import OpenFlowFSM
    from .fsm_manage import ManageFlowFSM
    from .fsm_close import CloseFlowFSM

    for flow_obj, prefix in [
        (open_flow, "open"),
        (manage_flow, "adjust"),
        (close_flow, "close"),
    ]:
        flow_typed = cast(OpenFlowFSM | ManageFlowFSM | CloseFlowFSM, flow_obj)
        flow_metrics = flow_typed.get_metrics()
        for key, value in flow_metrics.items():
            if key.startswith("fsm_"):
                metrics[key] = metrics.get(key, 0) + value

    return metrics


def _calculate_p95(latencies: list[float]) -> float:
    """Calculate p95 latency from list."""
    if not latencies:
        return 0.0

    sorted_lat = sorted(latencies)
    idx = int(len(sorted_lat) * 0.95)
    return sorted_lat[min(idx, len(sorted_lat) - 1)]


def reset_all() -> None:
    """Reset all flows (for testing)."""
    open_flow.reset()
    manage_flow.reset()
    close_flow.reset()
    global _decision_latencies
    _decision_latencies = []
