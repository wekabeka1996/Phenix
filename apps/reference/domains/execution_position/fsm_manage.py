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
from typing import Dict, Any, Optional, Union

from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.contracts import TPSLValidationRules
from apps.reference.config_models import AuroraConfig, create_aurora_config


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
        config: Optional[Union[Dict[str, Any], AuroraConfig]] = None,
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

        # PHASE A2: Anti-race flag - prevents bracket placement during CLOSE
        self._closing_position: bool = False
        self._closing_position_ts: float = 0.0

        # Configuration: Unify to AuroraConfig
        if config is None:
            self.config = AuroraConfig()
        elif isinstance(config, dict):
            try:
                self.config = create_aurora_config(config)
            except Exception as e:
                # Fallback for partial dicts in tests
                import logging
                logging.getLogger(__name__).warning(f"Config validation failed, using default: {e}")
                self.config = AuroraConfig()
        else:
            self.config = config

        # Extract commonly used configs for easier access
        self._manage_cfg = self.config.trading.execution.manage if self.config.trading.execution else None
        
        # Emergency/WaitMode configuration
        self._bar_ms = 15 * 60 * 1000
        if self.config.trading.decision.bar_gating:
             self._bar_ms = self.config.trading.decision.bar_gating.bar_ms

        self._wait_mode_bars = 2
        if self._manage_cfg and self._manage_cfg.emergency:
             self._wait_mode_bars = int(self._manage_cfg.emergency.get("wait_mode_bars", 2))
        
        self._wait_mode_until_ts: int = 0

        # Anti-race window (ms)
        self._anti_race_close_ms = 800
        # Note: anti_race_close_ms is not yet in Pydantic model, using default

        # Auto-manage flag
        self._auto_manage_enabled = False
        if self._manage_cfg:
            self._auto_manage_enabled = self._manage_cfg.auto

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
            pld_symbol = msg.pld.get("symbol") if isinstance(
                msg.pld, dict) else None
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
                pld_symbol = msg.pld.get("symbol") if isinstance(
                    msg.pld, dict) else None
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
            # 🔍 CRITICAL FIX: Distinguish between ENTRY and EXIT fills
            # If this is an EXIT order (TP/SL), position is CLOSING, not opening!
            pld = msg.pld or {}
            order_type = pld.get("order_type") or pld.get("type", "")
            close_position = str(pld.get("closePosition", "")).lower() == "true" or \
                str(pld.get("cp", "")).lower() == "true"
            is_reduce_only = str(pld.get("reduceOnly", "")).lower() == "true"

            # 🔍 DIAGNOSTIC: Log all FILL events in FLAT state
            print(f"[ManageFlowFSM] 📋 FILL event in FLAT: verb={msg.verb}, "
                  f"type={order_type}, closePos={close_position}, reduceOnly={is_reduce_only}, "
                  f"pld_keys={list(pld.keys())}")

            # EXIT orders: TAKE_PROFIT_MARKET, STOP_MARKET, or LIMIT with closePosition=true
            is_exit_order = (order_type in ["TAKE_PROFIT_MARKET", "STOP_MARKET"]) or \
                (close_position or is_reduce_only)

            if is_exit_order:
                # ⚠️ Position is CLOSING via TP/SL - do NOT create new TP/SL!
                print(
                    f"[ManageFlowFSM] ⚠️ EXIT fill detected ({order_type}), position closing, NOT placing brackets")
                self.position_qty = None
                self.position_entry_price = None
                self.position_side = None
                self.sl_price = None
                self.tp_price = None
                # Stay in FLAT, return without placing new brackets
                return None
            else:
                # ENTRY fill - position is opening
                # HOTFIX: Auto-clear closing flag on ENTRY (we're opening, not closing)
                if self._closing_position:
                    self._closing_position = False
                    import logging
                    LOG = logging.getLogger(__name__)
                    LOG.info("[BRK] ENTRY detected → closing_flag=False")

                print(
                    f"[ManageFlowFSM] 📈 ENTRY fill - creating position from {msg.verb}")
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

        # PHASE A2: Anti-race check - skip if position is closing
        if self._closing_position:
            elapsed_s = time.time() - self._closing_position_ts
            if elapsed_s < (self._anti_race_close_ms / 1000.0):  # configurable anti-race window
                # Position close still in progress, skip bracket placement
                import logging
                LOG = logging.getLogger(__name__)
                LOG.info(
                    f"[BRK] skip:closing_flag elapsed={elapsed_s:.3f}s (<{self._anti_race_close_ms/1000.0:.1f}s)")
                self.state = ManageState.TRACKING
                return None
            else:
                # Timeout: assume close finished, clear flag
                self._closing_position = False
                import logging
                LOG = logging.getLogger(__name__)
                LOG.info(
                    f"[BRK] clearing closing_flag after {elapsed_s:.3f}s")

        # HOTFIX: PHASE A1 - Dedup check + clear phantom IDs
        # Note: Full REST dedup (openOrders check) should be done at async level (fsm.py)
        # Here we do local dedup: if IDs are set but we're in FLAT->ENTRY transition,
        # clear them (they're phantoms from previous trade)
        # DO THIS BEFORE _should_place_brackets() check so IDs are always cleared
        import logging
        LOG = logging.getLogger(__name__)

        if self.sl_order_id or self.tp_order_id:
            # Local IDs present - likely phantoms if we're placing new brackets
            LOG.info(
                f"[BRK] local bracket IDs present (SL={self.sl_order_id}, TP={self.tp_order_id}) → clearing phantoms")
            self.sl_order_id = None
            self.tp_order_id = None

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

            # === VALIDATION PHASE: Check SL/TP prices before submission ===
            # Get current mark price (use entry price as proxy if not available)
            current_mark = self.position_entry_price
            if current_mark is None:
                self.state = ManageState.TRACKING
                return None

            # Convert BUY/SELL to LONG/SHORT for validation
            validation_side = "LONG" if self.position_side == "BUY" else "SHORT" if self.position_side == "SELL" else self.position_side or "LONG"

            # Validate SL price
            is_sl_valid, sl_reason = TPSLValidationRules.validate_stop_price_for_side(
                position_side=validation_side,
                current_mark=current_mark,
                stop_price=sl_price,
                is_take_profit=False,
            )
            if not is_sl_valid:
                self._metrics["fsm_bracket_validation_failed"] = self._metrics.get(
                    "fsm_bracket_validation_failed", 0) + 1
                self.state = ManageState.TRACKING
                return None

            # Validate TP price
            is_tp_valid, tp_reason = TPSLValidationRules.validate_stop_price_for_side(
                position_side=validation_side,
                current_mark=current_mark,
                stop_price=tp_price,
                is_take_profit=True,
            )
            if not is_tp_valid:
                self._metrics["fsm_bracket_validation_failed"] = self._metrics.get(
                    "fsm_bracket_validation_failed", 0) + 1
                self.state = ManageState.TRACKING
                return None

            # === SAFETY OFFSET PHASE: Apply offset to avoid -2021 errors ===
            # Read offset_bps from config (default 5)
            offset_bps = 5
            if self._manage_cfg and self._manage_cfg.brackets:
                 offset_bps = self._manage_cfg.brackets.offset_bps

            # Get tick_size from config or default
            tick_size = Decimal("0.01")
            symbol = msg.pld.get("symbol")
            if symbol and self.config.trading.instruments:
                 inst = self.config.trading.instruments.get(symbol)
                 if inst:
                     tick_size = Decimal(str(inst.tick_size))

            # Apply offset to SL (move it AWAY from entry to be safer)
            sl_offset = TPSLValidationRules.add_safety_offset(
                sl_price, tick_size, offset_bps)
            if self.position_side == "BUY":
                # SL is below entry, move it further down (subtract offset)
                sl_price = sl_price - sl_offset
            else:
                # SL is above entry, move it further up (add offset)
                sl_price = sl_price + sl_offset

            # Apply offset to TP (move it AWAY from entry to be safer)
            tp_offset = TPSLValidationRules.add_safety_offset(
                tp_price, tick_size, offset_bps)
            if self.position_side == "BUY":
                # TP is above entry, move it further up (add offset)
                tp_price = tp_price + tp_offset
            else:
                # TP is below entry, move it further down (subtract offset)
                tp_price = tp_price - tp_offset

            # Update stored prices
            self.sl_price = sl_price
            self.tp_price = tp_price
            self._metrics["fsm_bracket_offset_applied"] = self._metrics.get(
                "fsm_bracket_offset_applied", 0) + 1

            # Generate unique client order IDs
            position_id = f"{msg.rid}_{int(self.position_open_ts)}"
            sl_client_id = f"{position_id}_sl"
            tp_client_id = f"{position_id}_tp"

            # === EMISSION PHASE: Place validated bracket orders ===
            # Emit SL order
            sl_order = self._emit_place_order(
                msg,
                sl_client_id,
                "STOP_MARKET",
                self._get_opposite_side(),
                str(self.position_qty),
                str(sl_price),
                "SL bracket",
            )

            # Emit TP order
            tp_order = self._emit_place_order(
                msg,
                tp_client_id,
                "TAKE_PROFIT_MARKET",
                self._get_opposite_side(),
                str(self.position_qty),
                str(tp_price),
                "TP bracket",
            )

            self._metrics["fsm_bracket_orders_placed"] += 2
            
            # Return BATCH message with both orders
            return Message(
                op="DEC",
                verb="BATCH",
                src="execution_position",
                dst="execution_position",
                rid=msg.rid,
                why="place_brackets_batch",
                pld={
                    "messages": [sl_order.model_dump(), tp_order.model_dump()]
                },
                data_ref=msg.data_ref.copy() if msg.data_ref else []
            )

        except Exception:
            self._metrics["fsm_errors_total"] += 1
            self.state = ManageState.TRACKING
            return None

    def _should_place_brackets(self) -> bool:
        """Check if brackets should be placed based on config."""
        if self._manage_cfg and self._manage_cfg.brackets:
             return self._manage_cfg.brackets.enable
        return False

    def _calculate_bracket_prices(self) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """Calculate SL and TP prices based on config and position."""
        if self.position_entry_price is None or self.position_side is None:
            return None, None

        if not self._manage_cfg or not self._manage_cfg.brackets:
            return None, None
            
        brackets = self._manage_cfg.brackets
        entry_price = self.position_entry_price

        # ========== Calculate SL price ==========
        sl_bps = 50
        if brackets.sl and brackets.sl.fixed_bps:
            sl_bps = brackets.sl.fixed_bps
        elif brackets.stop_loss_bps: # Legacy fallback
             sl_bps = brackets.stop_loss_bps

        if self.position_side == "BUY":
            sl_price = entry_price * (1 - Decimal(str(sl_bps)) / 10000)
        else:  # SELL
            sl_price = entry_price * (1 + Decimal(str(sl_bps)) / 10000)

        # ========== Calculate TP price ==========
        tp_bps = 100
        if brackets.tp and brackets.tp.fixed_bps:
            tp_bps = brackets.tp.fixed_bps
        # Legacy fallback logic removed for clarity, assuming new config structure is primary
        # If needed, we can re-add legacy ratio logic here, but it's better to migrate configs.

        if self.position_side == "BUY":
            tp_price = entry_price * (1 + Decimal(str(tp_bps)) / 10000)
        else:  # SELL
            tp_price = entry_price * (1 - Decimal(str(tp_bps)) / 10000)

        # ========== Quantize prices to tick_size ==========
        tick_size = None
        symbol = getattr(self, 'symbol', None) # Symbol might not be set on FSM instance directly
        # Ideally symbol should be passed or stored. Assuming it might be available or we skip quantization.
        # For now, let's try to get it from config if possible, but FSM is per-symbol usually.
        # If we can't find tick_size easily without symbol, we skip quantization here or rely on adapter.
        
        # Simplified quantization if tick_size is available in config instruments
        if symbol and self.config.trading.instruments:
             inst = self.config.trading.instruments.get(symbol)
             if inst:
                 tick_size = inst.tick_size

        if tick_size:
            try:
                tick_size_dec = Decimal(str(tick_size))
                sl_price = (sl_price / tick_size_dec).quantize(Decimal('1')) * tick_size_dec
                tp_price = (tp_price / tick_size_dec).quantize(Decimal('1')) * tick_size_dec
            except (ValueError, TypeError, ArithmeticError):
                pass

        return sl_price, tp_price

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

        # Get workingType and priceProtect from config
        working_type = "MARK_PRICE"  # Default
        price_protect = False  # Default

        if self._manage_cfg and self._manage_cfg.brackets:
             brackets = self._manage_cfg.brackets
             if hasattr(brackets, 'working_type_default'):
                 working_type = brackets.working_type_default
             if hasattr(brackets, 'price_protect'):
                 price_protect = brackets.price_protect

        # Build payload
        payload = {
            "symbol": msg.pld.get("symbol", ""),
            "side": side,
            "qty": qty,
            "order_type": order_type,
            "price": price if order_type == "LIMIT" else None,
            "stopPrice": price if "STOP" in order_type else None,
            "reduceOnly": True,
            "newClientOrderId": client_id,
            "workingType": working_type,
            "priceProtect": price_protect,
        }

        # For STOP_MARKET/TAKE_PROFIT_MARKET with closePosition=true, don't send qty
        if "STOP" in order_type and order_type != "STOP_LOSS" and getattr(self, 'closePosition', False):
            # Remove qty for close-position orders (Binance manages qty automatically)
            payload.pop("qty", None)

        return Message(
            op="DEC",
            verb="PLACE_ORDER",
            src=msg.dst,
            dst="execution_position",
            rid=msg.rid,
            why=why[:80],
            idempotent_key=client_id,
            pld=payload,
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
            emergency_enabled = False
            emergency_sl_bps = 100
            
            if self._manage_cfg and self._manage_cfg.emergency:
                 # Assuming emergency is a dict in Pydantic model for now based on config_models.py
                 # emergency: Dict[str, Any] = Field(default_factory=dict)
                 em_cfg = self._manage_cfg.emergency
                 emergency_enabled = bool(em_cfg.get("enable", False))
                 emergency_sl_bps = int(em_cfg.get("emergency_sl_bps", 100))

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
            oco_enabled = False
            if self._manage_cfg and self._manage_cfg.brackets:
                 oco_enabled = self._manage_cfg.brackets.oco_emulation

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
            oco_enabled = False
            if self._manage_cfg and self._manage_cfg.brackets:
                 oco_enabled = self._manage_cfg.brackets.oco_emulation

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
        # Trailing config is currently a Dict in AuroraConfig (trailing: Dict[str, Any])
        # We should probably type it properly later, but for now access as dict
        trailing = self.config.trailing
        
        trailing_enabled = False
        if trailing:
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
            cooldown_sec = int(trailing.get("cooldown_sec", 30))
            if now - self.last_trailing_ts < cooldown_sec:
                return None

            # Calculate new SL price
            step_bps = int(trailing.get("step_bps", 10))
            
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
