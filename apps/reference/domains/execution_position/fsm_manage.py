"""
FSMP-P1-T02: Manage Flow FSM for execution_position domain.

States: FLAT|OPENED → TRACKING → EMIT_DEC_ADJUST → TRACKING
Rules (stubs): trail_pct, breakeven, time_stop
Output: DEC:ADJUST(tp?, sl?, move_to_be?)

Shadow-mode: decisions only, no live modifications.
"""
from __future__ import annotations

import time
from decimal import Decimal
from enum import Enum
from typing import Dict, Any, Optional

from vfoundation.core.protocol import Message


class ManageState(str, Enum):
    """FSM states for manage flow."""
    FLAT = "FLAT"
    OPENED = "OPENED"
    TRACKING = "TRACKING"
    BRACKETS_PENDING = "BRACKETS_PENDING"
    BRACKETS_PLACED = "BRACKETS_PLACED"
    EMIT_DEC_ADJUST = "EMIT_DEC_ADJUST"
    ERROR = "ERROR"


class ManageFlowFSM:
    """
    Manage Flow FSM: tracks open positions and manages brackets/trailing stops.
    
    Shadow-mode: stub rules (trail/breakeven/time_stop).
    Rules execute on EVT:PARTIAL_FILL|FILL|UPD:*.
    """

    def __init__(self, trail_pct: float = 0.5, breakeven_after_sec: float = 300.0, config: Optional[Dict[str, Any]] = None):
        self.state = ManageState.FLAT
        self.trail_pct = trail_pct  # stub: trailing stop %
        self.breakeven_after_sec = breakeven_after_sec  # stub: move to BE after X sec
        
        # Position tracking
        self.position_qty: Optional[Decimal] = None
        self.position_entry_price: Optional[Decimal] = None
        self.position_open_ts: float = 0.0
        self.position_side: Optional[str] = None  # 'BUY' or 'SELL'
        
        # Bracket orders tracking
        self.sl_order_id: Optional[str] = None
        self.tp_order_id: Optional[str] = None
        self.sl_price: Optional[Decimal] = None
        self.tp_price: Optional[Decimal] = None
        
        # Trailing stop tracking
        self.trailing_activated: bool = False
        self.last_trailing_ts: float = 0.0
        
        # Configuration
        self.config = config or {}
        
        # Read rules from config
        rules_config = self.config.get('execution_position', {}).get('rules', {})
        self.sl_bps = Decimal(str(rules_config.get('sl_bps', 50)))  # 50 bps default
        self.tp_bps = Decimal(str(rules_config.get('tp_bps', 100)))  # 100 bps default
        self.breakeven_bps = Decimal(str(rules_config.get('breakeven_bps', 20)))  # 20 bps default
        self.trail_start_bps = Decimal(str(rules_config.get('trail_start_bps', 30)))  # 30 bps default
        
        self._metrics: Dict[str, int] = {
            "fsm_adjust_decisions_total": 0,
            "fsm_bracket_orders_placed": 0,
            "fsm_trailing_adjustments": 0,
            "fsm_errors_total": 0,
        }

    def hydrate(self, position_data: Dict[str, Any]):
        """
        Hydrate the FSM state from a position snapshot.
        This is used for disaster recovery to restore FSM behavior for existing positions.
        """
        try:
            self.state = ManageState.TRACKING  # Assume active tracking after hydration
            self.position_qty = Decimal(str(position_data['qty']))
            self.position_entry_price = Decimal(str(position_data['entry_price']))
            self.position_open_ts = float(position_data.get('open_ts', time.time()))
            self.position_side = position_data['side']
            
            # Restore bracket and trailing stop info if available
            self.sl_order_id = position_data.get('sl_order_id')
            self.tp_order_id = position_data.get('tp_order_id')
            self.sl_price = Decimal(str(position_data['sl_price'])) if position_data.get('sl_price') else None
            self.tp_price = Decimal(str(position_data['tp_price'])) if position_data.get('tp_price') else None
            self.trailing_activated = position_data.get('trailing_activated', False)
            
            if self.sl_order_id or self.tp_order_id:
                self.state = ManageState.BRACKETS_PLACED

            print(f"[ManageFlowFSM] Hydrated state for position: qty={self.position_qty}, entry={self.position_entry_price}, side={self.position_side}")

        except KeyError as e:
            self.state = ManageState.ERROR
            self._metrics["fsm_errors_total"] += 1
            print(f"[ManageFlowFSM] HYDRATION_ERROR: Missing key in position_data: {e}")
        except Exception as e:
            self.state = ManageState.ERROR
            self._metrics["fsm_errors_total"] += 1
            print(f"[ManageFlowFSM] HYDRATION_ERROR: Failed to hydrate state: {e}")

    def handle(self, msg: Message) -> Optional[Message]:
        """
        Process incoming events and emit DEC:ADJUST if rules trigger.
        
        Args:
            msg: EVT:PARTIAL_FILL|FILL|UPD:* with payload: symbol, qty, price, etc.
            
        Returns:
            DEC:ADJUST if rules trigger, None otherwise.
        """
        if msg.op not in ("EVT", "UPD"):
            return None

        # State transition: FLAT → OPENED on PARTIAL_FILL or FILL
        if self.state == ManageState.FLAT and msg.verb in ("PARTIAL_FILL", "FILL", "TRADE_EXECUTED"):
            self._on_fill(msg)
            self.state = ManageState.OPENED
            print(f"[ManageFlowFSM] Position opened on {msg.verb}, transitioning to OPENED")
            
            # Immediately check rules based on the fill event data as the first tick
            rule_action = self._check_rules(msg)
            if rule_action:
                return rule_action

            # If no rules trigger, proceed to place brackets
            self.state = ManageState.BRACKETS_PENDING
            print("[ManageFlowFSM] Placing brackets, transitioning to BRACKETS_PENDING")
            return self._place_brackets(msg)

        # Handle bracket order confirmations
        if self.state == ManageState.BRACKETS_PENDING and msg.verb == "ORDER_UPDATED":
            # This message confirms a bracket order was placed.
            # We update our internal state but also check rules, as the market could have moved.
            self._on_bracket_placed(msg)
            return self._check_rules(msg)

        # Check rules in all active states to eliminate blind spots.
        # This covers market data updates while in OPENED, BRACKETS_PENDING, etc.
        if self.state in (ManageState.OPENED, ManageState.TRACKING, ManageState.BRACKETS_PENDING, ManageState.BRACKETS_PLACED):
            return self._check_rules(msg)

        elif msg.op == "UPD" and msg.verb == "TICK" and self.state == ManageState.OPENED:
            # Received new tick, check SL/TP rules
            current_price = Decimal(str(msg.pld.get("price", 0)))
            if not current_price:
                return None
                
            self.last_known_price = current_price
            
            # Call existing rule checking logic
            close_decision = self._check_rules(msg)
            if close_decision:
                self.state = ManageState.CLOSE_COND_MET  # Transition to close state
                return close_decision

        return None

    def _on_fill(self, msg: Message):
        """Update position state on fill event."""
        try:
            pld = msg.pld or {}
            qty = Decimal(str(pld.get("qty", 0)))
            price = Decimal(str(pld.get("price", 0)))
            side = pld.get("side")  # BUY or SELL

            if self.position_qty is None:
                self.position_qty = qty
                self.position_entry_price = price
                self.position_side = side
                self.position_open_ts = time.time()
            else:
                # Average down (stub logic)
                total_qty = self.position_qty + qty
                entry_price = self.position_entry_price if self.position_entry_price is not None else Decimal("0")
                avg_price = (
                    (self.position_qty * entry_price + qty * price) / total_qty
                )
                self.position_qty = total_qty
                self.position_entry_price = avg_price
                # Keep original side for position

        except Exception:
            self._metrics["fsm_errors_total"] += 1

    def _place_brackets(self, msg: Message) -> Optional[Message]:
        """Place SL and TP bracket orders after position opens."""
        if not self._should_place_brackets():
            self.state = ManageState.TRACKING
            return None
            
        try:
            # Calculate bracket prices
            sl_price, tp_price = self._calculate_bracket_prices()
            if sl_price is None or tp_price is None:
                self.state = ManageState.TRACKING
                return None
                
            self.sl_price = sl_price
            self.tp_price = tp_price
            
            # Generate unique client order IDs
            position_id = f"{msg.rid}_{int(self.position_open_ts)}"
            sl_client_id = f"{position_id}_sl"
            tp_client_id = f"{position_id}_tp"
            
            # Emit SL order
            assert self.position_side is not None
            sl_order = self._emit_place_order(
                msg, sl_client_id, "STOP_MARKET", self.position_side, 
                str(self.position_qty), str(sl_price), "SL bracket"
            )
            
            # Emit TP order  
            self._emit_place_order(
                msg, tp_client_id, "LIMIT", self._get_opposite_side(), 
                str(self.position_qty), str(tp_price), "TP bracket"
            )
            
            self._metrics["fsm_bracket_orders_placed"] += 2
            return sl_order  # Return first order, second will be handled separately
            
        except Exception:
            self._metrics["fsm_errors_total"] += 1
            self.state = ManageState.TRACKING
            return None

    def _should_place_brackets(self) -> bool:
        """Check if brackets should be placed based on config."""
        brackets_config = self.config.get("brackets", {})
        return brackets_config.get("enable", False)

    def _calculate_bracket_prices(self) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """Calculate SL and TP prices based on config and position."""
        if self.position_entry_price is None or self.position_side is None:
            return None, None
            
        brackets_config = self.config.get("brackets", {})
        sl_config = brackets_config.get("sl", {})
        tp_config = brackets_config.get("tp", {})
        
        # For now, use fixed BPS mode (ATR mode would need ATR data)
        entry_price = self.position_entry_price
        
        # Calculate SL price
        sl_bps = self.sl_bps
        if self.position_side == "BUY":
            sl_price = entry_price * (1 - Decimal(str(sl_bps)) / 10000)
        else:  # SELL
            sl_price = entry_price * (1 + Decimal(str(sl_bps)) / 10000)
            
        # Calculate TP price
        tp_bps = self.tp_bps
        if self.position_side == "BUY":
            tp_price = entry_price * (1 + Decimal(str(tp_bps)) / 10000)
        else:  # SELL
            tp_price = entry_price * (1 - Decimal(str(tp_bps)) / 10000)
            
        return sl_price, tp_price

    def _get_opposite_side(self) -> str:
        """Get opposite side for closing position."""
        return "SELL" if self.position_side == "BUY" else "BUY"

    def _emit_place_order(self, msg: Message, client_id: str, order_type: str, 
                         side: str, qty: str, price: str, why: str) -> Message:
        """Emit DEC:PLACE_ORDER for bracket."""
        return Message(
            op="DEC",
            verb="PLACE_ORDER",
            src=msg.dst,
            dst="execution_position", 
            rid=msg.rid,
            why=why[:80],
            idempotent_key=client_id,
            pld={
                "symbol": msg.pld.get("symbol", ""),
                "side": side,
                "qty": qty,
                "order_type": order_type,
                "price": price if order_type == "LIMIT" else None,
                "stopPrice": price if "STOP" in order_type else None,
                "reduceOnly": True,
                "newClientOrderId": client_id,
            }
        )

    def _on_bracket_placed(self, msg: Message) -> Optional[Message]:
        """Handle bracket order placement confirmation."""
        pld = msg.pld or {}
        client_order_id = pld.get("clientOrderId")
        order_id = pld.get("orderId")
        
        if client_order_id and order_id:
            if "_sl" in client_order_id:
                self.sl_order_id = order_id
            elif "_tp" in client_order_id:
                self.tp_order_id = order_id
                
            # Check if both brackets are placed
            if self.sl_order_id and self.tp_order_id:
                self.state = ManageState.BRACKETS_PLACED
                print(f"[ManageFlowFSM] Both brackets placed: SL={self.sl_order_id}, TP={self.tp_order_id}")
                
        return None

    def _check_rules(self, msg: Message) -> Optional[Message]:
        """
        Check management rules: brackets, trailing stop, breakeven, time_stop.
        
        Returns:
            DEC:PLACE_ORDER, DEC:CANCEL_ORDER, or DEC:ADJUST if rule triggers, None otherwise.
        """
        if self.position_qty is None or self.position_entry_price is None:
            return None

        try:
            # Handle bracket fills (OCO emulation)
            if msg.verb in ("TRADE_EXECUTED", "ORDER_UPDATED"):
                bracket_action = self._handle_bracket_fill(msg)
                if bracket_action:
                    return bracket_action
            
            # Handle trailing stop
            if msg.op == "UPD" and msg.verb == "MARKET_DATA":
                trailing_action = self._check_trailing_stop(msg)
                if trailing_action:
                    return trailing_action

            now = time.time()
            elapsed = now - self.position_open_ts

            # Rule 1: Trail (stub: check if current price > entry + trail_pct%)
            pld = msg.pld or {}
            current_price = pld.get("price")
            if current_price is not None:
                current_price_dec = Decimal(str(current_price))
                trail_trigger = self.position_entry_price * (1 + Decimal(str(self.trail_pct / 100)))

                if current_price_dec > trail_trigger:
                    return self._emit_adjust(msg, "ADJUST_TRAIL", {"rule": "trail", "trigger_price": str(trail_trigger)})

            # Rule 1.5: SL/TP Check (client-side stops)
            if msg.op == "UPD" and msg.verb == "TICK" and current_price is not None:
                current_price_dec = Decimal(str(current_price))
                
                # Calculate SL and TP prices
                if self.position_side == "BUY":
                    sl_price = self.position_entry_price * (1 - self.sl_bps / Decimal('10000'))
                    tp_price = self.position_entry_price * (1 + self.tp_bps / Decimal('10000'))
                    
                    if current_price_dec <= sl_price:
                        return self._emit_close(msg, "STOP_LOSS_HIT", {"rule": "client_sl", "sl_price": str(sl_price)})
                    elif current_price_dec >= tp_price:
                        return self._emit_close(msg, "TAKE_PROFIT_HIT", {"rule": "client_tp", "tp_price": str(tp_price)})
                        
                elif self.position_side == "SELL":
                    sl_price = self.position_entry_price * (1 + self.sl_bps / Decimal('10000'))
                    tp_price = self.position_entry_price * (1 - self.tp_bps / Decimal('10000'))
                    
                    if current_price_dec >= sl_price:
                        return self._emit_close(msg, "STOP_LOSS_HIT", {"rule": "client_sl", "sl_price": str(sl_price)})
                    elif current_price_dec <= tp_price:
                        return self._emit_close(msg, "TAKE_PROFIT_HIT", {"rule": "client_tp", "tp_price": str(tp_price)})

            # Rule 2: Breakeven (stub: move SL to BE after X seconds)
            if elapsed > self.breakeven_after_sec:
                return self._emit_adjust(msg, "ADJUST_BE", {"rule": "breakeven", "elapsed_sec": elapsed})

            # Rule 3: Time stop (stub: close after 3600 sec)
            if elapsed > 3600:
                return self._emit_adjust(msg, "ADJUST_TIME", {"rule": "time_stop", "elapsed_sec": elapsed})

        except Exception:
            self._metrics["fsm_errors_total"] += 1

        return None

    def _handle_bracket_fill(self, msg: Message) -> Optional[Message]:
        """Handle SL/TP bracket fills and perform OCO emulation."""
        pld = msg.pld or {}
        order_id = pld.get("orderId")
        
        if not order_id:
            return None
            
        # Check if this is a bracket fill
        if order_id == self.sl_order_id:
            # SL filled - cancel TP (OCO emulation)
            if self.tp_order_id and self.config.get("brackets", {}).get("oco_emulation", False):
                print(f"[ManageFlowFSM] SL filled, cancelling TP: {self.tp_order_id}")
                return self._emit_cancel_order(msg, self.tp_order_id, "OCO_SL_filled")
            self.sl_order_id = None
            
        elif order_id == self.tp_order_id:
            # TP filled - cancel SL (OCO emulation)  
            if self.sl_order_id and self.config.get("brackets", {}).get("oco_emulation", False):
                print(f"[ManageFlowFSM] TP filled, cancelling SL: {self.sl_order_id}")
                assert self.sl_order_id is not None
                return self._emit_cancel_order(msg, self.sl_order_id, "OCO_TP_filled")
            self.tp_order_id = None
            
        return None

    def _check_trailing_stop(self, msg: Message) -> Optional[Message]:
        """Check and adjust trailing stop if conditions met."""
        trailing_config = self.config.get("trailing", {})
        if not trailing_config.get("enable", False) or not self.sl_order_id:
            return None
            
        try:
            pld = msg.pld or {}
            current_price = pld.get("mark_price") or pld.get("last_price")
            if not current_price:
                return None
                
            current_price_dec = Decimal(str(current_price))
            now = time.time()
            
            # Check activation condition
            assert self.position_entry_price is not None
            assert self.position_side is not None
            if not self.trailing_activated:
                activation_threshold = self.position_entry_price * (
                    1 + Decimal(str(trailing_config.get("activation_profit_atr_k", 1.0))) * Decimal("0.01")  # Simplified ATR
                )
                if self.position_side == "BUY" and current_price_dec >= activation_threshold:
                    self.trailing_activated = True
                    print(f"[ManageFlowFSM] Trailing stop activated at {current_price}")
                elif self.position_side == "SELL" and current_price_dec <= activation_threshold:
                    self.trailing_activated = True
                    print(f"[ManageFlowFSM] Trailing stop activated at {current_price}")
                else:
                    return None
            
            # Check cooldown
            if now - self.last_trailing_ts < trailing_config.get("cooldown_sec", 30):
                return None
                
            # Calculate new SL price
            assert self.sl_price is not None
            step_bps = trailing_config.get("step_bps", 10)
            if self.position_side == "BUY":
                # For long position, trail up
                new_sl_price = max(self.sl_price, current_price_dec * (1 - Decimal(str(step_bps)) / 10000))
                if new_sl_price > self.sl_price:
                    return self._adjust_trailing_stop(msg, new_sl_price)
            else:
                # For short position, trail down
                new_sl_price = min(self.sl_price, current_price_dec * (1 + Decimal(str(step_bps)) / 10000))
                if new_sl_price < self.sl_price:
                    return self._adjust_trailing_stop(msg, new_sl_price)
                    
        except Exception:
            self._metrics["fsm_errors_total"] += 1
            
        return None

    def _adjust_trailing_stop(self, msg: Message, new_sl_price: Decimal) -> Message:
        """Adjust trailing stop by cancelling old and placing new."""
        assert self.position_side is not None
        assert self.position_qty is not None
        self.last_trailing_ts = time.time()
        self.sl_price = new_sl_price
        self._metrics["fsm_trailing_adjustments"] += 1
        
        # Cancel old SL
        assert self.sl_order_id is not None
        cancel_msg = self._emit_cancel_order(msg, self.sl_order_id, "trailing_adjust")
        
        # Place new SL (will be handled by next message)
        position_id = f"{msg.rid}_{int(self.position_open_ts)}"
        new_client_id = f"{position_id}_sl_trail_{int(time.time())}"
        
        self._emit_place_order(
            msg, new_client_id, "STOP_MARKET", self.position_side,
            str(self.position_qty), str(new_sl_price), "trailing_stop_adjust"
        )
        
        # For simplicity, return cancel first - new order will be placed on next cycle
        return cancel_msg

    def _emit_cancel_order(self, msg: Message, order_id: str, why: str) -> Message:
        """Emit DEC:CANCEL_ORDER."""
        return Message(
            op="DEC",
            verb="CANCEL_ORDER",
            src=msg.dst,
            dst="execution_position",
            rid=msg.rid,
            why=why[:80],
            idempotent_key=f"cancel_{order_id}_{int(time.time())}",
            pld={
                "orderId": order_id,
            }
        )

    def _emit_adjust(self, msg: Message, why: str, details: Dict[str, Any]) -> Message:
        """Generate DEC:ADJUST with stub rules."""
        self.state = ManageState.EMIT_DEC_ADJUST
        self._metrics["fsm_adjust_decisions_total"] += 1

        dec = Message(
            op="DEC",
            verb="ADJUST",
            src=msg.dst,
            dst="execution_position",
            rid=msg.rid,
            why=why[:80],
            idempotent_key=f"{msg.rid}_{why}_{int(time.time())}",
            pld=details,
        )

        # Return to TRACKING
        self.state = ManageState.TRACKING
        return dec

    def _emit_close(self, msg: Message, why: str, details: Dict[str, Any]) -> Message:
        """Generate DEC:CLOSE for SL/TP hits."""
        self.state = ManageState.EMIT_DEC_ADJUST  # Use existing state
        self._metrics["fsm_adjust_decisions_total"] += 1

        dec = Message(
            op="DEC",
            verb="CLOSE",
            src=msg.dst,
            dst="execution_position",
            rid=msg.rid,
            why=why[:80],
            idempotent_key=f"{msg.rid}_{why}_{int(time.time())}",
            pld=details,
        )
        return dec

    def get_metrics(self) -> Dict[str, int]:
        """Return metrics for observability."""
        return self._metrics.copy()

    def reset(self):
        """Reset FSM state (for testing)."""
        self.state = ManageState.FLAT
        self.position_qty = None
        self.position_entry_price = None
        self.position_open_ts = 0.0
        self.position_side = None
        self.sl_order_id = None
        self.tp_order_id = None
        self.sl_price = None
        self.tp_price = None
        self.trailing_activated = False
        self.last_trailing_ts = 0.0
