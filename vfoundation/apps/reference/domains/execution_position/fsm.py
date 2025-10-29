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

try:
    from .binance_execution_adapter import BinanceExecutionAdapter
except ImportError:
    BinanceExecutionAdapter = None


class ExecPosFSM:
    """Wrapper FSM class for execution_position domain with shadow mode support."""
    
    def __init__(
        self,
        config,
        fsm,
        shadow_mode: bool = False,
        adapter: Optional[AbstractExecutionAdapter] = None
    ):
        self.config = config
        self.fsm = fsm
        self.shadow_mode = shadow_mode
        self.logger = logging.getLogger(__name__)
        
        # Initialize adapter: use provided, create simulator by default, or None in shadow mode
        if adapter:
            self.adapter = adapter
        elif not self.shadow_mode:
            # Try BinanceExecutionAdapter first, fallback to SimulatedExecutionAdapter
            if BinanceExecutionAdapter:
                try:
                    self.adapter = BinanceExecutionAdapter(shadow_mode=False)
                    
                    # Initialize margin settings (leverage and margin type) for all instruments
                    instruments_config = config.trading.get('instruments', {})
                    if instruments_config and hasattr(self.adapter, 'initialize_margin_settings'):
                        self.logger.info("Initializing leverage and margin settings for instruments...")
                        self.adapter.initialize_margin_settings(instruments_config)
                    
                except Exception as e:
                    self.logger.warning(f"Failed to init BinanceExecutionAdapter: {e}, using SimulatedExecutionAdapter")
                    self.adapter = SimulatedExecutionAdapter()
            else:
                self.adapter = SimulatedExecutionAdapter()
        else:
            self.adapter = None  # In shadow_mode adapter not needed
        
        # Read execution config with defaults
        exec_config = config.trading.get('execution', {})
        
        # Parse cooldown_ms with proper type conversion
        cooldown_ms_raw = exec_config.get('cooldown_ms', 1000)
        try:
            cooldown_ms = float(cooldown_ms_raw)
        except (ValueError, TypeError):
            self.logger.warning(f"Invalid cooldown_ms value '{cooldown_ms_raw}', using default 1000ms")
            cooldown_ms = 1000.0
        
        cooldown_sec = cooldown_ms / 1000.0  # Convert ms to seconds
        guard_enabled = exec_config.get('guard_enabled', True)
        
        self.open_flow = OpenFlowFSM(cooldown_sec=cooldown_sec, guard_enabled=guard_enabled, config=config)
        self.manage_flow = ManageFlowFSM(trail_pct=0.5, breakeven_after_sec=300.0)
        self.close_flow = CloseFlowFSM(max_hold_sec=7200.0)
        
        # Initialize Aurora Log Adapter for enhanced trade logging
        self.log_adapter = AuroraLogAdapter()
        
        # Initialize Metrics Collector for monitoring trade patterns
        self.metrics_collector = MetricsCollector()
    
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
            def safe_decimal(val):
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
                probability=safe_decimal(pld.get("probability")),
                size=safe_decimal(pld.get("size")),
                price=safe_decimal(order_details.get("price") or pld.get("price")),
                qty=safe_decimal(order_details.get("qty") or pld.get("qty")),
                risk_score=safe_decimal(pld.get("risk_score")),
                features=pld.get("features")
            )
            
            # Record intent in metrics
            self.metrics_collector.record_trade_intent(
                symbol=symbol,
                side=side,
                rid=msg.rid,
                probability=pld.get("probability"),
                size=pld.get("size")
            )
            
            result = self.open_flow.handle(msg)
            
            # Log decision based on result
            if result and result.op == "ERR":
                # Guard rejection
                reason = result.pld.get("reason", "unknown") if result.pld else "unknown"
                guard_type = "COOLDOWN" if "cooldown" in reason else "OTHER"
                self.log_adapter.log_guard_rejection(
                    rid=msg.rid,
                    symbol=symbol,
                    side=side,
                    guard_type=guard_type,
                    reason=reason
                )
                
                # Record rejection in metrics
                self.metrics_collector.record_trade_decision(
                    symbol=symbol,
                    side=side,
                    decision="REJECTED",
                    reason=reason,
                    rid=msg.rid
                )
                
            elif result and result.op == "DEC":
                # Trade accepted
                self.log_adapter.log_trade_decision(
                    rid=msg.rid,
                    symbol=symbol,
                    side=side,
                    decision="ACCEPTED"
                )
                
                # Record acceptance in metrics
                self.metrics_collector.record_trade_decision(
                    symbol=symbol,
                    side=side,
                    decision="ACCEPTED",
                    rid=msg.rid
                )
        elif msg.verb in ["PARTIAL_FILL", "FILL"]:
            result = self.manage_flow.handle(msg)
        elif msg.verb == "CLOSE":
            result = self.close_flow.handle(msg)
        elif msg.verb == "PORTFOLIO_STATE_UPDATED":
            # Handle portfolio state recovery for both FSMs
            self._handle_portfolio_state_recovery(msg)
            result = None  # No decision emitted for recovery
        else:
            # For other messages, try manage flow as default
            result = self.manage_flow.handle(msg)
        
        if result and result.op == "DEC" and not self.shadow_mode:
            wal.append(result.model_dump())
            # Integrate adapter: call place_order for DEC:OPEN
            if result.verb == "OPEN" and self.adapter:
                try:
                    feedback = self.adapter.place_order(result)
                    self.logger.info(f"Adapter placed order: {feedback}")
                    # Optionally emit event based on feedback
                except Exception as e:
                    self.logger.error(f"Adapter failed to place order: {e}")
        
        return result

    def handle_event(self, msg: Message) -> Optional[Message]:
        """
        Compatibility alias for handle() to support vFoundation FSM API.
        
        This method exists for backward compatibility with code expecting
        the vFoundation FSM interface. It delegates to handle().
        """
        return self.handle(msg)

    def _handle_portfolio_state_recovery(self, msg: Message):
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
            position_qty = position.get("net_position", 0)
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
                            "price": str(position.get("avg_entry_price", 0))
                        }
                    )
                    self.manage_flow.handle(fake_fill_msg)
                    print(f"[FSM_RECOVERY] ManageFlowFSM restored to TRACKING for {symbol}, qty={position_qty}")
                
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
                            "filled_qty": abs(position_qty)  # Any positive value to trigger transition
                        }
                    )
                    self.close_flow.handle(fake_fill_msg)
                    print(f"[FSM_RECOVERY] CloseFlowFSM restored to OPENED for {symbol}, qty={position_qty}")

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


def _record_latency(latency_sec: float):
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


def reset_all():
    """Reset all flows (for testing)."""
    open_flow.reset()
    manage_flow.reset()
    close_flow.reset()
    global _decision_latencies
    _decision_latencies = []
