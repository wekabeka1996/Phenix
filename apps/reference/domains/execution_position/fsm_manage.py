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


try:
    from apps.reference.telemetry.metrics import inc_manage_skipped
except ImportError:

    def inc_manage_skipped() -> None:
        pass


class ManageState(str, Enum):
    """FSM states for manage flow."""

    FLAT = "FLAT"
    OPENED = "OPENED"
    TRACKING = "TRACKING"
    BRACKETS_PENDING = "BRACKETS_PENDING"
    BRACKETS_PLACED = "BRACKETS_PLACED"
    EMIT_DEC_ADJUST = "EMIT_DEC_ADJUST"
    ERROR = "ERROR"
    EMERGENCY = "EMERGENCY"
    WAIT_MODE = "WAIT_MODE"


class ManageFlowFSM:
    """
    Manage Flow FSM: tracks open positions and manages brackets/trailing stops.

    Shadow-mode: stub rules (trail/breakeven/time_stop).
    Rules execute on EVT:PARTIAL_FILL|FILL|UPD:*.
    """

    def __init__(
        self,
        trail_pct: float = 0.5,
        breakeven_after_sec: float = 300.0,
        config: Optional[Dict[str, Any]] = None,
    ):
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
        # Emergency/WaitMode configuration
        # Using typed attribute access for Pydantic models
        try:
            bar_gate_cfg = self.config.trading.decision.bar_gating if self.config.trading else None
            self._bar_ms = int(bar_gate_cfg.bar_ms) if bar_gate_cfg and hasattr(bar_gate_cfg, 'bar_ms') else 15 * 60 * 1000
        except (AttributeError, TypeError, ValueError):
            self._bar_ms = 15 * 60 * 1000
        
        try:
            em_cfg = self.config.execution.manage.emergency if self.config.execution else None
            self._wait_mode_bars = int(em_cfg.get("wait_mode_bars", 2)) if isinstance(em_cfg, dict) else 2
        except (AttributeError, TypeError, ValueError):
            self._wait_mode_bars = 2
        self._wait_mode_until_ts: int = 0

        # Read auto-manage flag from config
        # Try both paths: trading.execution.manage and execution.manage
        try:
            if hasattr(self.config, 'trading') and self.config.trading:
                cfg_exec = self.config.trading.execution
            elif hasattr(self.config, 'execution') and self.config.execution:
                cfg_exec = self.config.execution
            else:
                cfg_exec = None
            
            manage_cfg = cfg_exec.manage if cfg_exec else None
            self._auto_manage_enabled = bool(manage_cfg.auto if manage_cfg and hasattr(manage_cfg, 'auto') else False)
        except (AttributeError, TypeError):
            self._auto_manage_enabled = False

        # Log configuration status
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"ManageFlowFSM initialized: auto_manage_enabled={self._auto_manage_enabled}")

        self._metrics: Dict[str, int] = {
            "fsm_adjust_decisions_total": 0,
            "fsm_bracket_orders_placed": 0,
            "fsm_trailing_adjustments": 0,
            "fsm_errors_total": 0,
        }

    def set_bracket_ids(self, sl_order_id: Optional[str], tp_order_id: Optional[str]) -> None:
        """
        Directly set bracket IDs from ExecPosFSM after placement.

        This ensures ManageFlowFSM has accurate bracket tracking for OCO emulation,
        even if ORDER_UPDATED WebSocket events are delayed or missed.

        Args:
            sl_order_id: Stop-loss order ID from exchange (string)
            tp_order_id: Take-profit order ID from exchange (string)
        """
        self.sl_order_id = sl_order_id
        self.tp_order_id = tp_order_id
        # Log synchronization for debugging
        import logging
        LOG = logging.getLogger(__name__)
        LOG.debug(f"✅ Synced bracket IDs: SL={sl_order_id}, TP={tp_order_id}")

    def handle(self, msg: Message) -> Optional[Message]:
        """
        Process incoming events and emit DEC:ADJUST if rules trigger.

        Args:
            msg: EVT:PARTIAL_FILL|FILL|UPD:* with payload: symbol, qty, price, etc.

        Returns:
            DEC:ADJUST if rules trigger, None otherwise.
        """
        # Kill-switch: check if auto-manage is disabled
        if not self._auto_manage_enabled:
            inc_manage_skipped()
            # Emit MANAGE_SKIPPED event for observability
            pld_symbol = msg.pld.get("symbol") if isinstance(msg.pld, dict) else None
            return Message(
                op="EVT",
                verb="MANAGE_SKIPPED",
                src="execution_position",
                dst="any",
                rid=getattr(msg, "rid", None) or "",
                why="manage_disabled",
                pld={
                    "symbol": pld_symbol,
                    "reason": "auto_manage_disabled",
                },
                data_ref=msg.data_ref.copy() if msg.data_ref else [],  # Preserve WHY chain
            )

        if msg.op not in ("EVT", "UPD"):
            return None

        # WAIT_MODE handling: skip actions until TTL expires
        try:
            pld = msg.pld or {}
            ts_value = pld.get("ts") if isinstance(pld, dict) else None
            now_ts = int(ts_value) if ts_value else int(time.time() * 1000)
        except Exception:
            now_ts = int(time.time() * 1000)
        
        if self.state == ManageState.WAIT_MODE:
            if now_ts < self._wait_mode_until_ts:
                pld_symbol = msg.pld.get("symbol") if isinstance(msg.pld, dict) else None
                return Message(
                    op="EVT",
                    verb="MANAGE_SKIPPED",
                    src="execution_position",
                    dst="any",
                    rid=getattr(msg, "rid", None) or "",
                    why="wait_mode_active",
                    pld={"symbol": pld_symbol, "reason": "wait_mode"},
                    data_ref=msg.data_ref.copy() if msg.data_ref else [],
                )
            else:
                self.state = ManageState.TRACKING

        # State transition: FLAT → BRACKETS_PENDING on PARTIAL_FILL or FILL
        if self.state == ManageState.FLAT and msg.verb in (
            "PARTIAL_FILL",
            "FILL",
            "TRADE_EXECUTED",
        ):
            self._on_fill(msg)
            self.state = (
                ManageState.BRACKETS_PENDING
            )  # Place brackets after position opens
            print(
                f"[ManageFlowFSM] Position opened, placing brackets on {msg.verb}")
            # Place bracket orders immediately
            return self._place_brackets(msg)

        # Handle bracket order confirmations
        if self.state == ManageState.BRACKETS_PENDING and msg.verb == "ORDER_UPDATED":
            return self._on_bracket_placed(msg)

        # Check rules in TRACKING/BRACKETS_PLACED states
        if self.state in (ManageState.TRACKING, ManageState.BRACKETS_PLACED):
            return self._check_rules(msg)

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
                entry_price = (
                    self.position_entry_price
                    if self.position_entry_price is not None
                    else Decimal("0")
                )
                avg_price = (self.position_qty * entry_price +
                             qty * price) / total_qty
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
            sl_order = self._emit_place_order(
                msg,
                sl_client_id,
                "STOP_MARKET",
                self.position_side or "",
                str(self.position_qty),
                str(sl_price),
                "SL bracket",
            )

            # Emit TP order
            tp_order = self._emit_place_order(
                msg,
                tp_client_id,
                "LIMIT",
                self._get_opposite_side(),
                str(self.position_qty),
                str(tp_price),
                "TP bracket",
            )

            self._metrics["fsm_bracket_orders_placed"] += 2
            return sl_order  # Return first order, second will be handled separately

        except Exception:
            self._metrics["fsm_errors_total"] += 1
            self.state = ManageState.TRACKING
            return None

    def _should_place_brackets(self) -> bool:
        """Check if brackets should be placed based on config."""
        try:
            # Try Pydantic attribute access first
            if hasattr(self.config, 'trading') and self.config.trading:
                brackets_config = self.config.trading.execution.manage.brackets if self.config.trading.execution and self.config.trading.execution.manage else None
            elif isinstance(self.config, dict):
                brackets_config = self.config.get("brackets", {})
            else:
                brackets_config = None
            
            if brackets_config and hasattr(brackets_config, 'enable'):
                return bool(brackets_config.enable)
            elif isinstance(brackets_config, dict):
                return bool(brackets_config.get("enable", False))
            return False
        except (AttributeError, TypeError):
            return False

    def _calculate_bracket_prices(self) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """Calculate SL and TP prices based on config and position."""
        if self.position_entry_price is None or self.position_side is None:
            return None, None

        try:
            # Try Pydantic attribute access first
            if hasattr(self.config, 'trading') and self.config.trading:
                brackets = self.config.trading.execution.manage.brackets if self.config.trading.execution and self.config.trading.execution.manage else None
                sl_config = brackets.sl if brackets else None
                tp_config = brackets.tp if brackets else None
            elif isinstance(self.config, dict):
                brackets_config = self.config.get("brackets", {})
                sl_config = brackets_config.get("sl", {}) if isinstance(brackets_config, dict) else None
                tp_config = brackets_config.get("tp", {}) if isinstance(brackets_config, dict) else None
            else:
                sl_config = None
                tp_config = None

            # For now, use fixed BPS mode (ATR mode would need ATR data)
            entry_price = self.position_entry_price

            # Calculate SL price
            sl_bps = 50
            if sl_config:
                if hasattr(sl_config, 'fixed_bps'):
                    sl_bps = sl_config.fixed_bps
                elif isinstance(sl_config, dict):
                    sl_bps = sl_config.get("fixed_bps", 50)
            
            if self.position_side == "BUY":
                sl_price = entry_price * (1 - Decimal(str(sl_bps)) / 10000)
            else:  # SELL
                sl_price = entry_price * (1 + Decimal(str(sl_bps)) / 10000)

            # Calculate TP price
            tp_bps = 100
            if tp_config:
                if hasattr(tp_config, 'fixed_bps'):
                    tp_bps = tp_config.fixed_bps
                elif isinstance(tp_config, dict):
                    tp_bps = tp_config.get("fixed_bps", 100)
            
            if self.position_side == "BUY":
                tp_price = entry_price * (1 + Decimal(str(tp_bps)) / 10000)
            else:  # SELL
                tp_price = entry_price * (1 - Decimal(str(tp_bps)) / 10000)

            return sl_price, tp_price
        except (AttributeError, TypeError, ValueError):
            return None, None

    def _get_opposite_side(self) -> str:
        """Get opposite side for closing position."""
        return "SELL" if self.position_side == "BUY" else "BUY"

    def _emit_place_order(
        self,
        msg: Message,
        client_id: str,
        order_type: str,
        side: str,
        qty: str,
        price: str,
        why: str,
    ) -> Message:
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
            },
            data_ref=msg.data_ref.copy() if msg.data_ref else [],  # Preserve WHY chain
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
                print(
                    f"[ManageFlowFSM] Both brackets placed: SL={self.sl_order_id}, TP={self.tp_order_id}"
                )

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
            # Emergency protection (optional)
            try:
                if hasattr(self.config, 'execution') and self.config.execution:
                    emergency_cfg = self.config.execution.manage.emergency if self.config.execution.manage else None
                elif isinstance(self.config, dict):
                    emergency_cfg = self.config.get("emergency", {})
                else:
                    emergency_cfg = None
            except (AttributeError, TypeError):
                emergency_cfg = None
            
            emergency_enabled = False
            emergency_sl_bps = 100
            if emergency_cfg:
                if hasattr(emergency_cfg, 'enable'):
                    emergency_enabled = bool(emergency_cfg.enable)
                elif isinstance(emergency_cfg, dict):
                    emergency_enabled = bool(emergency_cfg.get("enable", False))
                
                if hasattr(emergency_cfg, 'emergency_sl_bps'):
                    emergency_sl_bps = emergency_cfg.emergency_sl_bps
                elif isinstance(emergency_cfg, dict):
                    emergency_sl_bps = emergency_cfg.get("emergency_sl_bps", 100)
            
            if emergency_enabled and msg.op == "UPD" and msg.verb == "MARKET_DATA":
                pld = msg.pld or {}
                cur = pld.get("price")
                if cur is not None and self.position_entry_price:
                    current_price_dec = Decimal(str(cur))
                    sl_em_bps = Decimal(str(emergency_sl_bps))
                    adverse = (self.position_entry_price - current_price_dec) if (
                        self.position_side == "BUY") else (current_price_dec - self.position_entry_price)
                    if adverse > 0:
                        adverse_bps = (
                            adverse / self.position_entry_price) * Decimal("10000")
                        if adverse_bps >= sl_em_bps:
                            # Move to WAIT_MODE for configured number of bars
                            try:
                                now_ts = int((msg.pld or {}).get("ts")) if (
                                    msg.pld or {}).get("ts") else int(time.time() * 1000)
                            except Exception:
                                now_ts = int(time.time() * 1000)
                            bar_index = now_ts // getattr(self,
                                                          "_bar_ms", 900000)
                            self._wait_mode_until_ts = (
                                bar_index + getattr(self, "_wait_mode_bars", 2)) * getattr(self, "_bar_ms", 900000)
                            self.state = ManageState.WAIT_MODE
                            new_sl = (self.position_entry_price * (Decimal("1") - sl_em_bps / Decimal("10000"))) if self.position_side == "BUY" else (
                                self.position_entry_price * (Decimal("1") + sl_em_bps / Decimal("10000")))
                            return self._emit_place_order(
                                msg,
                                client_id=f"{getattr(msg,'rid','')}_emergency_sl",
                                order_type="STOP_MARKET",
                                side=self.position_side or "",
                                qty=str(self.position_qty),
                                price=str(new_sl),
                                why="emergency_stop_activate",
                            )
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
                trail_trigger = self.position_entry_price * (
                    1 + Decimal(str(self.trail_pct / 100))
                )

                if current_price_dec > trail_trigger:
                    return self._emit_adjust(
                        msg,
                        "ADJUST_TRAIL",
                        {"rule": "trail", "trigger_price": str(trail_trigger)},
                    )

            # Rule 2: Breakeven (stub: move SL to BE after X seconds)
            if elapsed > self.breakeven_after_sec:
                return self._emit_adjust(
                    msg, "ADJUST_BE", {
                        "rule": "breakeven", "elapsed_sec": elapsed}
                )

            # Rule 3: Time stop (stub: close after 3600 sec)
            if elapsed > 3600:
                return self._emit_adjust(
                    msg, "ADJUST_TIME", {
                        "rule": "time_stop", "elapsed_sec": elapsed}
                )

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
            decision = None
            try:
                oco_enabled = False
                if hasattr(self.config, 'trading') and self.config.trading:
                    brackets = self.config.trading.execution.manage.brackets if self.config.trading.execution and self.config.trading.execution.manage else None
                    if brackets and hasattr(brackets, 'oco_emulation'):
                        oco_enabled = bool(brackets.oco_emulation)
                elif isinstance(self.config, dict):
                    oco_enabled = bool(self.config.get("brackets", {}).get("oco_emulation", False))
            except (AttributeError, TypeError):
                oco_enabled = False
            
            if self.tp_order_id and oco_enabled:
                print(
                    f"[ManageFlowFSM] SL filled, cancelling TP: {self.tp_order_id}")
                decision = self._emit_cancel_order(
                    msg, self.tp_order_id, "OCO_SL_filled")

            # Always clear the filled order from tracking
            self.sl_order_id = None
            return decision

        elif order_id == self.tp_order_id:
            # TP filled - cancel SL (OCO emulation)
            decision = None
            try:
                oco_enabled = False
                if hasattr(self.config, 'trading') and self.config.trading:
                    brackets = self.config.trading.execution.manage.brackets if self.config.trading.execution and self.config.trading.execution.manage else None
                    if brackets and hasattr(brackets, 'oco_emulation'):
                        oco_enabled = bool(brackets.oco_emulation)
                elif isinstance(self.config, dict):
                    oco_enabled = bool(self.config.get("brackets", {}).get("oco_emulation", False))
            except (AttributeError, TypeError):
                oco_enabled = False
            
            if self.sl_order_id and oco_enabled:
                print(
                    f"[ManageFlowFSM] TP filled, cancelling SL: {self.sl_order_id}")
                decision = self._emit_cancel_order(
                    msg, self.sl_order_id, "OCO_TP_filled")

            # Always clear the filled order from tracking
            self.tp_order_id = None
            return decision

        return None

    def _check_trailing_stop(self, msg: Message) -> Optional[Message]:
        """Check and adjust trailing stop if conditions met."""
        try:
            # Try Pydantic attribute access first
            if hasattr(self.config, 'trading') and self.config.trading:
                trailing = self.config.trading.execution.manage.trailing if self.config.trading.execution and self.config.trading.execution.manage else None
            elif isinstance(self.config, dict):
                trailing = self.config.get("trailing", {})
            else:
                trailing = None
        except (AttributeError, TypeError):
            trailing = None
        
        trailing_enabled = False
        if trailing:
            if hasattr(trailing, 'enable'):
                trailing_enabled = bool(trailing.enable)
            elif isinstance(trailing, dict):
                trailing_enabled = bool(trailing.get("enable", False))
        
        if not trailing_enabled or not self.sl_order_id:
            return None

        try:
            pld = msg.pld or {}
            current_price = pld.get("mark_price") or pld.get("last_price")
            if not current_price:
                return None

            current_price_dec = Decimal(str(current_price))
            now = time.time()

            # Check activation condition
            if not self.trailing_activated and self.position_entry_price:
                # Get activation_profit_atr_k
                activation_k = 1.0
                if trailing:
                    if hasattr(trailing, 'activation_profit_atr_k'):
                        activation_k = float(trailing.activation_profit_atr_k)
                    elif isinstance(trailing, dict):
                        activation_k = float(trailing.get("activation_profit_atr_k", 1.0))
                
                activation_threshold = self.position_entry_price * (
                    1
                    + Decimal(str(activation_k))
                    * Decimal("0.01")  # Simplified ATR
                )
                if (
                    self.position_side == "BUY"
                    and current_price_dec >= activation_threshold
                ):
                    self.trailing_activated = True
                    print(
                        f"[ManageFlowFSM] Trailing stop activated at {current_price}")
                elif (
                    self.position_side == "SELL"
                    and current_price_dec <= activation_threshold
                ):
                    self.trailing_activated = True
                    print(
                        f"[ManageFlowFSM] Trailing stop activated at {current_price}")
                else:
                    return None

            # Check cooldown
            if now - self.last_trailing_ts < trailing_config.get("cooldown_sec", 30):
                return None

            # Calculate new SL price
            step_bps = trailing_config.get("step_bps", 10)
            if self.position_side == "BUY" and self.sl_price:
                # For long position, trail up
                new_sl_price = max(
                    self.sl_price,
                    current_price_dec * (1 - Decimal(str(step_bps)) / 10000),
                )
                if new_sl_price > self.sl_price:
                    return self._adjust_trailing_stop(msg, new_sl_price)
            elif self.position_side == "SELL" and self.sl_price:
                # For short position, trail down
                new_sl_price = min(
                    self.sl_price,
                    current_price_dec * (1 + Decimal(str(step_bps)) / 10000),
                )
                if new_sl_price < self.sl_price:
                    return self._adjust_trailing_stop(msg, new_sl_price)

        except Exception:
            self._metrics["fsm_errors_total"] += 1

        return None

    def _adjust_trailing_stop(self, msg: Message, new_sl_price: Decimal) -> Message:
        """Adjust trailing stop by cancelling old and placing new."""
        self.last_trailing_ts = time.time()
        self.sl_price = new_sl_price
        self._metrics["fsm_trailing_adjustments"] += 1

        # Cancel old SL
        cancel_msg = self._emit_cancel_order(
            msg, self.sl_order_id or "", "trailing_adjust")

        # Place new SL (will be handled by next message)
        position_id = f"{msg.rid}_{int(self.position_open_ts)}"
        new_client_id = f"{position_id}_sl_trail_{int(time.time())}"

        new_sl_msg = self._emit_place_order(
            msg,
            new_client_id,
            "STOP_MARKET",
            self.position_side or "",
            str(self.position_qty),
            str(new_sl_price),
            "trailing_stop_adjust",
        )

        # For simplicity, return cancel first - new order will be placed on next cycle
        return cancel_msg

    def _emit_cancel_order(self, msg: Message, order_id: str, why: str) -> Message:
        """Emit DEC:CANCEL_ORDER with symbol included for adapter call."""
        symbol = (msg.pld or {}).get("symbol", "")
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
                "symbol": symbol,
            },
            data_ref=msg.data_ref.copy() if msg.data_ref else [],  # Preserve WHY chain
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
            data_ref=msg.data_ref.copy() if msg.data_ref else [],  # Preserve WHY chain
        )

        # Return to TRACKING
        self.state = ManageState.TRACKING
        return dec

    def get_metrics(self) -> Dict[str, int]:
        """Return metrics for observability."""
        return self._metrics.copy()

    def hydrate(self, state_data: Dict[str, Any]) -> None:
        """
        Restore FSM state from persisted data.

        Args:
            state_data: Dictionary containing position and bracket state
        """
        try:
            # Validate required fields
            if "qty" not in state_data:
                self.state = ManageState.ERROR
                return

            # Restore position data
            self.position_qty = Decimal(
                str(state_data.get("qty", 0))) if state_data.get("qty") else None
            self.position_entry_price = Decimal(str(state_data.get(
                "entry_price", 0))) if state_data.get("entry_price") else None
            self.position_side = state_data.get("side")
            self.position_open_ts = float(state_data.get("open_ts", 0))

            # Restore bracket data
            self.sl_order_id = state_data.get("sl_order_id")
            self.tp_order_id = state_data.get("tp_order_id")

            # Set appropriate state based on what data is available
            if self.position_qty and self.position_qty != 0:
                if self.sl_order_id:
                    self.state = ManageState.BRACKETS_PLACED
                else:
                    self.state = ManageState.TRACKING
            else:
                self.state = ManageState.FLAT

        except (ValueError, TypeError, KeyError) as e:
            print(f"Failed to hydrate ManageFlowFSM: {e}")
            self.state = ManageState.ERROR

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
