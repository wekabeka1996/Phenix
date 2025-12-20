"""
FSMP-P1-T02: Manage Flow FSM for execution_position domain.

States: FLAT|OPENED → TRACKING → EMIT_DEC_ADJUST → TRACKING
Rules: per-instrument trailing_stop, max_hold_time, TP1/TP2 partial exit
Output: DEC:ADJUST(tp?, sl?, move_to_be?)

Shadow-mode: decisions only, no live modifications.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal, ROUND_DOWN
from enum import Enum
from typing import Dict, Any, Optional

from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.contracts import TPSLValidationRules
from apps.reference.config_models import AuroraConfig, AuroraInstrumentConfig
from apps.reference.utils.accessors import aget, dget

LOG = logging.getLogger(__name__)


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

    Per-instrument config with fallback: aurora_instruments.<SYM> → global → default.
    Rules execute on EVT:PARTIAL_FILL|FILL|UPD:*.
    """

    def __init__(
        self,
        config: Optional[AuroraConfig] = None,
    ):
        self.state = ManageState.FLAT

        # Position tracking
        self.symbol: Optional[str] = None  # Phase 0: track symbol for per-instrument config
        self.position_qty: Optional[Decimal] = None
        self.position_entry_price: Optional[Decimal] = None
        self.position_open_ts: float = 0.0
        self.position_side: Optional[str] = None  # 'BUY' or 'SELL'

        # Bracket orders tracking
        self.sl_order_id: Optional[str] = None
        self.tp_order_id: Optional[str] = None
        self.tp1_order_id: Optional[str] = None
        self.tp2_order_id: Optional[str] = None

        # Intent data (injected via set_intent_prices)
        self._intent_sl_price: Optional[Decimal] = None
        self._intent_tp_price: Optional[Decimal] = None

        self.sl_price: Optional[Decimal] = None
        self.tp_price: Optional[Decimal] = None  # TP1 price (primary)
        
        # Phase A2: TP1/TP2 partial exit support
        self.tp2_order_id: Optional[str] = None
        self.tp1_price: Optional[Decimal] = None
        self.tp2_price: Optional[Decimal] = None
        self.partial_exit_pct: Optional[float] = None  # e.g., 0.7 = 70% at TP1

        # Phase A3: Trailing stop tracking
        self.trailing_activated: bool = False
        self.last_trailing_ts: float = 0.0
        self.peak_price: Optional[Decimal] = None  # High-water mark for trailing

        # PHASE A2: Anti-race flag - prevents bracket placement during CLOSE
        self._closing_position: bool = False
        self._closing_position_ts: float = 0.0

        if isinstance(config, dict):
            raise TypeError("ManageFlowFSM requires typed AuroraConfig, got dict")
        self.config = AuroraConfig() if config is None else config

        # Extract commonly used configs for easier access
        self._manage_cfg = self.config.trading.execution.manage if self.config.trading.execution else None
        
        # Emergency/WaitMode configuration
        self._bar_ms = 15 * 60 * 1000
        if self.config.trading.decision.bar_gating:
             self._bar_ms = self.config.trading.decision.bar_gating.bar_ms

        self._wait_mode_bars = 2
        if self._manage_cfg and self._manage_cfg.emergency:
            emergency_cfg = self._manage_cfg.emergency
            if isinstance(emergency_cfg, dict):
                self._wait_mode_bars = int(emergency_cfg["wait_mode_bars"] if "wait_mode_bars" in emergency_cfg else 2)
            else:
                self._wait_mode_bars = int(aget(emergency_cfg, "wait_mode_bars", 2))
        
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
            "fsm_max_hold_timeouts": 0,
            "fsm_partial_exits_total": 0,
            "fsm_errors_total": 0,
        }

    # =========================================================================
    # Phase 0: Per-Instrument Aurora Configuration Helpers
    # =========================================================================

    def _get_aurora_instr_cfg(self, symbol: Optional[str] = None) -> Optional[AuroraInstrumentConfig]:
        """
        Get per-instrument Aurora configuration for current or specified symbol.

        Fallback chain:
        1. self.symbol (from position tracking)
        2. Passed symbol argument
        3. Return None if no symbol available

        Supports both Pydantic config and legacy dict format for consistency
        with DecisionMaking._get_aurora_instrument_cfg().

        Args:
            symbol: Trading pair symbol (optional, uses self.symbol if not provided)

        Returns:
            AuroraInstrumentConfig or None if not configured
        """
        target_symbol = symbol or self.symbol
        if not target_symbol:
            return None

        # CFG-AURORA-INSTRUMENTS-SSOT-01-FIXPACK: Direct Pydantic access
        if not self.config or not hasattr(self.config, 'aurora_instruments'):
            return None

        aurora_instruments = self.config.aurora_instruments
        if not isinstance(aurora_instruments, dict):
            return None

        return aurora_instruments.get(target_symbol)  # Already Pydantic-typed

    def _get_exit_param(self, param: str, default: Any, symbol: Optional[str] = None) -> Any:
        """
        Get exit parameter with per-instrument override support.

        Fallback chain:
        1. config.aurora_instruments[SYMBOL].exit.<param> (CANONICAL SSOT)
        2. trading.execution.manage.brackets.sl/tp.* (global, param name mapped)
        3. default value

        Param mapping for global fallback:
        - sl_pct → brackets.sl.fixed_bps (converted: bps/10000)
        - max_hold_sec → None (no global equivalent)

        Args:
            param: Parameter name (e.g., 'sl_pct', 'max_hold_sec')
            default: Default value if not found
            symbol: Optional symbol override

        Returns:
            Parameter value from per-instrument or global config
        """
        # 1. Try per-instrument config
        instr_cfg = self._get_aurora_instr_cfg(symbol)
        if instr_cfg is not None and instr_cfg.exit is not None:
            # Direct access (no getattr fallback)
            # If field missing → AttributeError → caller handles (fail-closed)
            try:
                value = getattr(instr_cfg.exit, param)
                if value is not None:
                    return value
            except AttributeError:
                # Exit param not configured → return None (fail-closed: block action)
                pass

        # 2. Fallback to global via _manage_cfg (with param name mapping)
        if self._manage_cfg and self._manage_cfg.brackets:
            brackets = self._manage_cfg.brackets
            
            # Map param names to global config structure
            if param == "sl_pct" and brackets.sl and brackets.sl.fixed_bps:
                # Convert bps to percentage (50 bps → 0.005)
                return brackets.sl.fixed_bps / 10000.0
            
            # max_hold_sec has no global equivalent - return None (fail-closed)
        
        # 3. Return default
        return default

    def _get_take_profit_params(
        self, symbol: Optional[str] = None
    ) -> tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Get TP1/TP2 parameters from per-instrument config.

        Returns (tp_low_ratio, tp_high_ratio, partial_exit_pct) for symbol.

        Args:
            symbol: Trading pair symbol (optional, uses self.symbol if not provided)

        Returns:
            Tuple of (tp_low_ratio, tp_high_ratio, partial_exit_pct).
            Any value may be None if not configured.
        """
        instr_cfg = self._get_aurora_instr_cfg(symbol)
        tp = aget(instr_cfg, "take_profit", None) if instr_cfg is not None else None
        if tp is not None:
            return (
                aget(tp, "tp_low_ratio", None),
                aget(tp, "tp_high_ratio", None),
                aget(tp, "partial_exit_pct", None),
            )
        return None, None, None

    def set_intent_prices(self, sl_price: Union[str, float, Decimal], tp_price: Optional[Union[str, float, Decimal]] = None) -> None:
        """
        Inject specific TP/SL prices from TradeIntent (Strategy calculation).
        Called by ExecPosFSM before bracket placement.
        """
        try:
            if sl_price:
                self._intent_sl_price = Decimal(str(sl_price))
            if tp_price:
                self._intent_tp_price = Decimal(str(tp_price))
            LOG.info(f"SET_INTENT_PRICES: SL={self._intent_sl_price}, TP={self._intent_tp_price}")
        except Exception as e:
            LOG.error(f"Failed to set intent prices: {e}")


    def _get_trailing_stop_params(
        self, symbol: Optional[str] = None
    ) -> tuple[bool, Optional[float], Optional[float], int]:
        """
        Get trailing stop parameters from per-instrument config.

        Phase A3: Per-instrument trailing with global fallback.

        Args:
            symbol: Trading pair symbol (optional, uses self.symbol if not provided)

        Returns:
            Tuple of (enabled, activation_pct, trail_pct, min_update_interval_sec).
        """
        # 1. Try per-instrument config
        instr_cfg = self._get_aurora_instr_cfg(symbol)
        ts = aget(instr_cfg, "trailing_stop", None) if instr_cfg is not None else None
        if ts is not None:
            return (
                bool(ts.enabled),
                aget(ts, "activation_pct", None),
                aget(ts, "trail_pct", None),
                int(aget(ts, "min_update_interval_sec", 5) or 5),
            )

        # 2. Fallback to global trailing dict
        trailing = aget(self.config, "trailing", None) or {}
        if isinstance(trailing, dict):
            return (
                bool(dget(trailing, "enable", False)),
                trailing.get("activation_profit_atr_k"),  # Legacy name
                trailing.get("step_bps"),  # Legacy: bps not pct
                int(dget(trailing, "cooldown_sec", 5)),
            )

        return False, None, None, 5

    def _get_max_hold_sec(self, symbol: Optional[str] = None) -> Optional[int]:
        """
        Get max hold time from per-instrument exit config.

        Phase A4: Returns max_hold_sec for forced position exit.

        Args:
            symbol: Trading pair symbol (optional, uses self.symbol if not provided)

        Returns:
            max_hold_sec or None if not configured.
        """
        instr_cfg = self._get_aurora_instr_cfg(symbol)
        exit_cfg = aget(instr_cfg, "exit", None) if instr_cfg is not None else None
        if exit_cfg is not None:
            return aget(exit_cfg, "max_hold_sec", None)
        return None

    def _check_max_hold_time(self, msg: Message, elapsed_sec: float) -> Optional[Message]:
        """
        Check if position exceeded max hold time and should be closed.

        Phase A4: Per-instrument max_hold_sec watchdog.
        Forces market close when position held too long.

        Args:
            msg: Current message for context
            elapsed_sec: Seconds since position open

        Returns:
            DEC:CLOSE_POSITION message if timeout, None otherwise.
        """
        max_hold_sec = self._get_max_hold_sec(self.symbol)
        if max_hold_sec is None:
            return None

        if elapsed_sec >= max_hold_sec:
            self._metrics["fsm_max_hold_timeouts"] = int(self._metrics["fsm_max_hold_timeouts"]) + 1
            msg_pld = msg.pld or {}

            # Emit close position message
            return Message(
                op="DEC",
                verb="CLOSE_POSITION",
                src="execution_position",
                dst="execution_position",
                rid=msg.rid,
                why=f"max_hold_timeout_{int(elapsed_sec)}s_reduce_only",
                pld={
                    "symbol": self.symbol or (msg_pld["symbol"] if "symbol" in msg_pld else ""),
                    "side": self._get_opposite_side(),
                    "qty": str(self.position_qty),
                    "reduce_only": True,
                    "reason": "MAX_HOLD_TIME_EXCEEDED",
                    "elapsed_sec": elapsed_sec,
                    "max_hold_sec": max_hold_sec,
                },
                data_ref=msg.data_ref.copy() if msg.data_ref else [],
            )

        return None

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
                rid=aget(msg, "rid", None) or "",
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
        except (ValueError, TypeError, AttributeError) as e:
            LOG.debug(f"Failed to parse timestamp from message: {e}")
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
                    rid=aget(msg, "rid", None) or "",
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
            order_type = pld.get("order_type") or (pld["type"] if "type" in pld else "")
            close_position = (
                str(pld["closePosition"] if "closePosition" in pld else "").lower() == "true"
                or str(pld["cp"] if "cp" in pld else "").lower() == "true"
            )
            is_reduce_only = str(pld["reduceOnly"] if "reduceOnly" in pld else "").lower() == "true"

            # 🔍 DIAGNOSTIC: Log all FILL events in FLAT state
            LOG.debug(f"FILL event in FLAT: verb={msg.verb}, "
                      f"type={order_type}, closePos={close_position}, reduceOnly={is_reduce_only}, "
                      f"pld_keys={list(pld.keys())}")

            # EXIT orders: TAKE_PROFIT_MARKET, STOP_MARKET, or LIMIT with closePosition=true
            is_exit_order = (order_type in ["TAKE_PROFIT_MARKET", "STOP_MARKET"]) or \
                (close_position or is_reduce_only)

            if is_exit_order:
                # ⚠️ Position is CLOSING via TP/SL - do NOT create new TP/SL!
                LOG.info(
                    f"EXIT fill detected ({order_type}), position closing, NOT placing brackets")
                self.position_qty = None
                self.position_entry_price = None
                self.position_side = None
                self.symbol = None  # Phase 0: clear symbol on position close
                self.sl_price = None
                self.tp_price = None
                # Stay in FLAT, return without placing new brackets
                return None
            else:
                # ENTRY fill - position is opening
                # HOTFIX: Auto-clear closing flag on ENTRY (we're opening, not closing)
                if self._closing_position:
                    self._closing_position = False
                    LOG.info("[BRK] ENTRY detected → closing_flag=False")

                LOG.info(
                    f"ENTRY fill - creating position from {msg.verb}")
                self._on_fill(msg)
                self.state = (
                    ManageState.BRACKETS_PENDING
                )  # Place brackets after position opens
                LOG.info(
                    f"Position opened, placing brackets on {msg.verb}")
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
            qty = Decimal(str(pld["qty"] if "qty" in pld else 0))
            price = Decimal(str(pld["price"] if "price" in pld else 0))
            side = pld.get("side")  # BUY or SELL
            symbol = pld.get("symbol")  # Phase 0: extract symbol from fill event

            if self.position_qty is None:
                self.position_qty = qty
                self.position_entry_price = price
                self.position_side = side
                self.symbol = symbol  # Phase 0: track symbol for per-instrument config
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

        except (ValueError, TypeError, KeyError) as e:
            LOG.warning(f"Failed to process fill event: {e}")
            self._metrics["fsm_errors_total"] += 1

    def _place_brackets(self, msg: Message) -> Optional[Message]:
        """Place SL and TP bracket orders after position opens."""

        # PHASE A2: Anti-race check - skip if position is closing
        if self._closing_position:
            elapsed_s = time.time() - self._closing_position_ts
            if elapsed_s < (self._anti_race_close_ms / 1000.0):  # configurable anti-race window
                # Position close still in progress, skip bracket placement
                LOG.info(
                    f"[BRK] skip:closing_flag elapsed={elapsed_s:.3f}s (<{self._anti_race_close_ms/1000.0:.1f}s)")
                self.state = ManageState.TRACKING
                return None
            else:
                # Timeout: assume close finished, clear flag
                self._closing_position = False
                LOG.info(
                    f"[BRK] clearing closing_flag after {elapsed_s:.3f}s")

        # HOTFIX: PHASE A1 - Dedup check + clear phantom IDs
        # Note: Full REST dedup (openOrders check) should be done at async level (fsm.py)
        # Here we do local dedup: if IDs are set but we're in FLAT->ENTRY transition,
        # clear them (they're phantoms from previous trade)
        # DO THIS BEFORE _should_place_brackets() check so IDs are always cleared

        if self.sl_order_id or self.tp_order_id or self.tp1_order_id or self.tp2_order_id:
            # Local IDs present - likely phantoms if we're placing new brackets
            LOG.info(
                f"[BRK] local bracket IDs present (SL={self.sl_order_id}, TP={self.tp_order_id}, "
                f"TP1={self.tp1_order_id}, TP2={self.tp2_order_id}) → clearing phantoms")
            self.sl_order_id = None
            self.tp_order_id = None
            self.tp1_order_id = None
            self.tp2_order_id = None

        if not self._should_place_brackets():
            self.state = ManageState.TRACKING
            return None

        try:
            # Calculate bracket prices (Phase A2: returns sl, tp1, tp2)
            sl_price, tp1_price, tp2_price = self._calculate_bracket_prices()
            if sl_price is None or tp1_price is None:
                self.state = ManageState.TRACKING
                return None

            self.sl_price = sl_price
            self.tp1_price = tp1_price
            self.tp2_price = tp2_price
            self.tp_price = tp1_price  # Backward compat: legacy single TP = TP1

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
                cur = self._metrics["fsm_bracket_validation_failed"] if "fsm_bracket_validation_failed" in self._metrics else 0
                self._metrics["fsm_bracket_validation_failed"] = cur + 1
                self.state = ManageState.TRACKING
                return None

            # Validate TP1 price
            is_tp1_valid, tp1_reason = TPSLValidationRules.validate_stop_price_for_side(
                position_side=validation_side,
                current_mark=current_mark,
                stop_price=tp1_price,
                is_take_profit=True,
            )
            if not is_tp1_valid:
                cur = self._metrics["fsm_bracket_validation_failed"] if "fsm_bracket_validation_failed" in self._metrics else 0
                self._metrics["fsm_bracket_validation_failed"] = cur + 1
                self.state = ManageState.TRACKING
                return None

            # Validate TP2 price if present
            if tp2_price is not None:
                is_tp2_valid, tp2_reason = TPSLValidationRules.validate_stop_price_for_side(
                    position_side=validation_side,
                    current_mark=current_mark,
                    stop_price=tp2_price,
                    is_take_profit=True,
                )
                if not is_tp2_valid:
                    cur = self._metrics["fsm_bracket_validation_failed"] if "fsm_bracket_validation_failed" in self._metrics else 0
                    self._metrics["fsm_bracket_validation_failed"] = cur + 1
                    self.state = ManageState.TRACKING
                    return None

            # === SAFETY OFFSET PHASE: Apply offset to avoid -2021 errors ===
            # Read offset_bps from config (default 5)
            offset_bps = 5
            if self._manage_cfg and self._manage_cfg.brackets:
                 offset_bps = self._manage_cfg.brackets.offset_bps

            # CFG-INSTRUMENTS-STEP-03-EXECUTION-PRECISION:
            # Get tick_size from canonical config.instruments
            tick_size = Decimal("0.01")
            symbol = msg.pld.get("symbol")
            if symbol and self.config.instruments:
                 inst = self.config.instruments.get(symbol)
                 if inst and hasattr(inst, 'tick_size') and inst.tick_size is not None:
                     tick_size = Decimal(str(inst.tick_size))

            # Apply offset to SL (move it AWAY from entry to be safer)
            sl_offset = TPSLValidationRules.add_safety_offset(
                sl_price, tick_size, offset_bps)
            if self.position_side == "BUY":
                sl_price = sl_price - sl_offset
            else:
                sl_price = sl_price + sl_offset

            # Apply offset to TP1 (move it AWAY from entry to be safer)
            tp1_offset = TPSLValidationRules.add_safety_offset(
                tp1_price, tick_size, offset_bps)
            if self.position_side == "BUY":
                tp1_price = tp1_price + tp1_offset
            else:
                tp1_price = tp1_price - tp1_offset

            # Apply offset to TP2 if present
            if tp2_price is not None:
                tp2_offset = TPSLValidationRules.add_safety_offset(
                    tp2_price, tick_size, offset_bps)
                if self.position_side == "BUY":
                    tp2_price = tp2_price + tp2_offset
                else:
                    tp2_price = tp2_price - tp2_offset

            # Update stored prices
            self.sl_price = sl_price
            self.tp1_price = tp1_price
            self.tp2_price = tp2_price
            self.tp_price = tp1_price  # Backward compat
            cur = self._metrics["fsm_bracket_offset_applied"] if "fsm_bracket_offset_applied" in self._metrics else 0
            self._metrics["fsm_bracket_offset_applied"] = cur + 1

            # === QUANTITY CALCULATION: TP1 partial, TP2 remainder ===
            total_qty = self.position_qty
            if tp2_price is not None and self.partial_exit_pct is not None:
                # Phase A2: Split qty between TP1 (partial) and TP2 (remainder)
                partial_pct = Decimal(str(self.partial_exit_pct))
                tp1_qty = (total_qty * partial_pct).quantize(Decimal("0.001"), rounding=ROUND_DOWN)
                tp2_qty = total_qty - tp1_qty
            else:
                # Single TP mode: all qty on TP1
                tp1_qty = total_qty
                tp2_qty = Decimal("0")

            # Generate unique client order IDs
            position_id = f"{msg.rid}_{int(self.position_open_ts)}"
            sl_client_id = f"{position_id}_sl"
            tp1_client_id = f"{position_id}_tp1"
            tp2_client_id = f"{position_id}_tp2"

            # === EMISSION PHASE: Place validated bracket orders ===
            orders = []

            # Emit SL order (full qty)
            sl_order = self._emit_place_order(
                msg,
                sl_client_id,
                "STOP_MARKET",
                self._get_opposite_side(),
                str(total_qty),
                str(sl_price),
                "SL bracket",
            )
            orders.append(sl_order.model_dump())

            # Emit TP1 order
            tp1_order = self._emit_place_order(
                msg,
                tp1_client_id,
                "TAKE_PROFIT_MARKET",
                self._get_opposite_side(),
                str(tp1_qty),
                str(tp1_price),
                "TP1 bracket (partial)" if tp2_price else "TP bracket",
            )
            orders.append(tp1_order.model_dump())
            self.tp1_order_id = tp1_client_id

            # Emit TP2 order if configured
            if tp2_price is not None and tp2_qty > Decimal("0"):
                tp2_order = self._emit_place_order(
                    msg,
                    tp2_client_id,
                    "TAKE_PROFIT_MARKET",
                    self._get_opposite_side(),
                    str(tp2_qty),
                    str(tp2_price),
                    "TP2 bracket (remainder)",
                )
                orders.append(tp2_order.model_dump())
                self.tp2_order_id = tp2_client_id
                self._metrics["fsm_bracket_orders_placed"] += 3
            else:
                self._metrics["fsm_bracket_orders_placed"] += 2

            # Backward compat: set legacy tp_order_id to TP1
            self.tp_order_id = tp1_client_id
            
            # Return BATCH message with all orders
            return Message(
                op="DEC",
                verb="BATCH",
                src="execution_position",
                dst="execution_position",
                rid=msg.rid,
                why="place_brackets_batch",
                pld={
                    "messages": orders
                },
                data_ref=msg.data_ref.copy() if msg.data_ref else []
            )

        except (ValueError, TypeError, KeyError) as e:
            LOG.warning(f"Failed to place brackets: {e}")
            self._metrics["fsm_errors_total"] += 1
            self.state = ManageState.TRACKING
            return None

    def _should_place_brackets(self) -> bool:
        """Check if brackets should be placed based on config."""
        if self._manage_cfg and self._manage_cfg.brackets:
             return self._manage_cfg.brackets.enable
        return False

    def _calculate_bracket_prices(
        self
    ) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """
        Calculate SL, TP1, TP2 prices for current position.
        
        Phase A2: Uses per-instrument config with global fallback.
        Returns (sl_price, tp1_price, tp2_price).
        TP2 may be None if not configured (single TP mode).
        
        Fallback chain:
        - Intent Injection: self._intent_sl_price (from Strategy)
        - Config Lookup: aurora_instruments.<SYMBOL>.exit.sl_pct → brackets.sl.fixed_bps
        - TP: self._intent_tp_price (from Strategy) -> ...
        """
        if self.position_entry_price is None or self.position_side is None:
            return None, None, None

        # PHASE A2 FIX: Prioritize injected intent prices (Strategy calculation)
        if self._intent_sl_price:
             LOG.info(f"USING_INTENT_SL for calculation: {self._intent_sl_price}")
             sl_price = self._intent_sl_price
             # Consume it
             self._intent_sl_price = None
             
             # If we have SL, check for TP
             tp1_price = None
             if self._intent_tp_price:
                 LOG.info(f"USING_INTENT_TP for calculation: {self._intent_tp_price}")
                 tp1_price = self._intent_tp_price
                 self._intent_tp_price = None
             
             # Return early with strategy values (quantized)
             return self._quantize_prices(self.symbol, sl_price, tp1_price, None)
             
        entry_price = self.position_entry_price
        symbol = self.symbol  # Phase 0: use tracked symbol

        # ========== Get per-instrument config ==========
        sl_pct: Optional[float] = None
        tp_low_ratio: Optional[float] = None
        tp_high_ratio: Optional[float] = None
        partial_exit_pct: Optional[float] = None

        instr_cfg = self._get_aurora_instr_cfg(symbol)
        if instr_cfg is not None:
            # Get exit config (SL)
            exit_cfg = aget(instr_cfg, "exit", None)
            if exit_cfg is not None:
                sl_pct = aget(exit_cfg, "sl_pct", None)
            # Get take_profit config (TP1/TP2)
            tp_low_ratio, tp_high_ratio, partial_exit_pct = self._get_take_profit_params(symbol)

        # Store partial_exit_pct for bracket placement
        self.partial_exit_pct = partial_exit_pct

        # ========== Calculate SL price ==========
        if sl_pct is not None:
            sl_price = self._calculate_sl_from_pct(entry_price, sl_pct)
        else:
            sl_price = self._calculate_sl_from_bps(entry_price)

        # ========== Calculate TP1/TP2 prices ==========
        tp1_price: Optional[Decimal] = None
        tp2_price: Optional[Decimal] = None

        if sl_pct is not None and tp_low_ratio is not None:
            # Phase A2: Risk-ratio based TP1/TP2
            risk_pct = Decimal(str(sl_pct))  # SL distance as risk unit
            tp1_off = risk_pct * Decimal(str(tp_low_ratio))

            if self.position_side == "BUY":
                tp1_price = entry_price * (Decimal("1") + tp1_off)
            else:
                tp1_price = entry_price * (Decimal("1") - tp1_off)

            # TP2 is optional (further target)
            if tp_high_ratio is not None:
                tp2_off = risk_pct * Decimal(str(tp_high_ratio))
                if self.position_side == "BUY":
                    tp2_price = entry_price * (Decimal("1") + tp2_off)
                else:
                    tp2_price = entry_price * (Decimal("1") - tp2_off)
        else:
            # Fallback: single TP from bps
            tp1_price = self._calculate_tp_from_bps(entry_price)

        # ========== Quantize prices to tick_size ==========
        sl_price, tp1_price, tp2_price = self._quantize_prices(symbol, sl_price, tp1_price, tp2_price)

        return sl_price, tp1_price, tp2_price

    def _calculate_sl_from_pct(self, entry_price: Decimal, sl_pct: float) -> Decimal:
        """Calculate SL price from percentage."""
        sl_pct_dec = Decimal(str(sl_pct))
        if self.position_side == "BUY":
            return entry_price * (Decimal("1") - sl_pct_dec)
        else:
            return entry_price * (Decimal("1") + sl_pct_dec)

    def _calculate_sl_from_bps(self, entry_price: Decimal) -> Decimal:
        """
        Fallback: calculate SL using existing bps config.
        Reads from: trading.execution.manage.brackets.sl.fixed_bps
        """
        sl_bps = 50  # default
        if self._manage_cfg and self._manage_cfg.brackets:
            brackets = self._manage_cfg.brackets
            if brackets.sl and brackets.sl.fixed_bps:
                sl_bps = brackets.sl.fixed_bps
            elif brackets.stop_loss_bps:  # Legacy fallback
                sl_bps = brackets.stop_loss_bps

        if self.position_side == "BUY":
            return entry_price * (1 - Decimal(str(sl_bps)) / 10000)
        else:
            return entry_price * (1 + Decimal(str(sl_bps)) / 10000)

    def _calculate_tp_from_bps(self, entry_price: Decimal) -> Optional[Decimal]:
        """
        Fallback: calculate TP using existing bps config.
        Reads from: trading.execution.manage.brackets.tp.fixed_bps
        """
        tp_bps = 100  # default
        if self._manage_cfg and self._manage_cfg.brackets:
            brackets = self._manage_cfg.brackets
            if brackets.tp and brackets.tp.fixed_bps:
                tp_bps = brackets.tp.fixed_bps

        if self.position_side == "BUY":
            return entry_price * (1 + Decimal(str(tp_bps)) / 10000)
        else:
            return entry_price * (1 - Decimal(str(tp_bps)) / 10000)

    def _quantize_prices(
        self,
        symbol: Optional[str],
        sl_price: Optional[Decimal],
        tp1_price: Optional[Decimal],
        tp2_price: Optional[Decimal],
    ) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """Quantize prices to tick_size from instruments config."""
        tick_size = None
        if symbol and self.config and hasattr(self.config, 'trading'):
            instruments = aget(self.config.trading, "instruments", None)
            if instruments:
                inst = instruments.get(symbol)
                if inst:
                    tick_size = aget(inst, "tick_size", None)

        if tick_size:
            try:
                tick_size_dec = Decimal(str(tick_size))
                if sl_price is not None:
                    sl_price = (sl_price / tick_size_dec).quantize(Decimal('1')) * tick_size_dec
                if tp1_price is not None:
                    tp1_price = (tp1_price / tick_size_dec).quantize(Decimal('1')) * tick_size_dec
                if tp2_price is not None:
                    tp2_price = (tp2_price / tick_size_dec).quantize(Decimal('1')) * tick_size_dec
            except (ValueError, TypeError, ArithmeticError):
                pass

        return sl_price, tp1_price, tp2_price

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
        msg_pld = msg.pld or {}
        payload = {
            "symbol": msg_pld["symbol"] if "symbol" in msg_pld else "",
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
        if "STOP" in order_type and order_type != "STOP_LOSS" and bool(aget(self, "closePosition", False)):
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
                LOG.info(
                    f"Both brackets placed: SL={self.sl_order_id}, TP={self.tp_order_id}"
                )

        return None

    def _check_rules(self, msg: Message) -> Optional[Message]:
        """
        Check management rules: brackets, trailing stop, max hold time.

        Uses per-instrument config with fallback to global defaults.

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
                 if isinstance(em_cfg, dict):
                     emergency_enabled = bool(dget(em_cfg, "enable", False))
                     emergency_sl_bps = int(dget(em_cfg, "emergency_sl_bps", 100))
                 else:
                     emergency_enabled = bool(aget(em_cfg, "enable", False))
                     emergency_sl_bps = int(aget(em_cfg, "emergency_sl_bps", 100))

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
                            # Direct access (fail-closed: missing emergency config → crash)
                            if not hasattr(self, "_bar_ms") or not hasattr(self, "_wait_mode_bars"):
                                raise ValueError(
                                    "CRITICAL: Emergency mode activated but _bar_ms/_wait_mode_bars not configured. "
                                    "Cannot determine wait period (fail-closed)."
                                )
                            bar_index = now_ts // self._bar_ms
                            self._wait_mode_until_ts = (
                                bar_index + self._wait_mode_bars) * self._bar_ms
                            self.state = ManageState.WAIT_MODE
                            new_sl = (self.position_entry_price * (Decimal("1") - sl_em_bps / Decimal("10000"))) if self.position_side == "BUY" else (
                                self.position_entry_price * (Decimal("1") + sl_em_bps / Decimal("10000")))
                            return self._emit_place_order(
                                msg,
                                client_id=f"{aget(msg, 'rid', '')}_emergency_sl",
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

            # Handle trailing stop (per-instrument config)
            if msg.op == "UPD" and msg.verb == "MARKET_DATA":
                trailing_action = self._check_trailing_stop(msg)
                if trailing_action:
                    return trailing_action

            now = time.time()
            elapsed = now - self.position_open_ts

            # Phase A4: Max hold time watchdog (per-instrument config)
            max_hold_action = self._check_max_hold_time(msg, elapsed)
            if max_hold_action:
                return max_hold_action

        except (ValueError, TypeError, KeyError, ArithmeticError) as e:
            LOG.warning(f"Error in _check_rules: {e}")
            self._metrics["fsm_errors_total"] += 1

        return None

    def _handle_bracket_fill(self, msg: Message) -> Optional[Message]:
        """
        Handle SL/TP bracket fills and perform OCO emulation.
        
        Phase A2: Supports TP1/TP2 partial exit:
        - TP1 fill: reduces position_qty by partial_exit_pct, keeps TP2 and adjusts SL
        - TP2 fill: closes remaining position, cancels SL
        - SL fill: cancels all remaining TP orders
        """
        pld = msg.pld or {}
        order_id = pld.get("orderId")
        client_order_id = pld["clientOrderId"] if "clientOrderId" in pld else ""

        if not order_id:
            return None

        oco_enabled = False
        if self._manage_cfg and self._manage_cfg.brackets:
            oco_enabled = self._manage_cfg.brackets.oco_emulation

        # === SL FILLED ===
        if order_id == self.sl_order_id or "_sl" in client_order_id:
            LOG.info(f"[ManageFlowFSM] SL filled: {order_id}")
            decisions = []
            
            # Cancel all TP orders (OCO emulation)
            if oco_enabled:
                if self.tp1_order_id:
                    decisions.append(self._emit_cancel_order(msg, self.tp1_order_id, "OCO_SL_filled_tp1"))
                if self.tp2_order_id:
                    decisions.append(self._emit_cancel_order(msg, self.tp2_order_id, "OCO_SL_filled_tp2"))
                # Legacy fallback
                elif self.tp_order_id and self.tp_order_id != self.tp1_order_id:
                    decisions.append(self._emit_cancel_order(msg, self.tp_order_id, "OCO_SL_filled"))

            # Clear all bracket tracking
            self.sl_order_id = None
            self.tp_order_id = None
            self.tp1_order_id = None
            self.tp2_order_id = None
            
            # Return first cancel decision (others handled in next cycle)
            return decisions[0] if decisions else None

        # === TP1 FILLED (partial exit) ===
        if order_id == self.tp1_order_id or "_tp1" in client_order_id:
            LOG.info(f"[ManageFlowFSM] TP1 filled (partial exit): {order_id}")
            
            # Update position qty (reduce by partial_exit_pct)
            if self.position_qty and self.partial_exit_pct:
                filled_pct = Decimal(str(self.partial_exit_pct))
                filled_qty = self.position_qty * filled_pct
                self.position_qty = self.position_qty - filled_qty
                LOG.info(f"[ManageFlowFSM] Position reduced: filled={filled_qty}, remaining={self.position_qty}")
                self._metrics["fsm_partial_exits_total"] = int(self._metrics["fsm_partial_exits_total"]) + 1

            # Clear TP1, keep TP2 as "runner"
            self.tp1_order_id = None
            
            # If no TP2 configured, this was single-TP mode - cancel SL
            if not self.tp2_order_id and oco_enabled and self.sl_order_id:
                LOG.info(f"[ManageFlowFSM] Single TP mode, cancelling SL: {self.sl_order_id}")
                decision = self._emit_cancel_order(msg, self.sl_order_id, "OCO_TP1_filled_no_tp2")
                self.sl_order_id = None
                self.tp_order_id = None
                return decision
            
            # TODO: Consider adjusting SL to breakeven after TP1 (optional feature)
            return None

        # === TP2 FILLED (remainder/runner) ===
        if order_id == self.tp2_order_id or "_tp2" in client_order_id:
            LOG.info(f"[ManageFlowFSM] TP2 filled (runner closed): {order_id}")
            decision = None
            
            # Cancel SL (OCO emulation) - position fully closed
            if oco_enabled and self.sl_order_id:
                LOG.info(f"[ManageFlowFSM] TP2 filled, cancelling SL: {self.sl_order_id}")
                decision = self._emit_cancel_order(msg, self.sl_order_id, "OCO_TP2_filled")

            # Clear all bracket tracking
            self.sl_order_id = None
            self.tp_order_id = None
            self.tp1_order_id = None
            self.tp2_order_id = None
            self.position_qty = Decimal("0")
            
            return decision

        # === Legacy TP (backward compat) ===
        if order_id == self.tp_order_id:
            LOG.info(f"[ManageFlowFSM] Legacy TP filled: {order_id}")
            decision = None
            
            if oco_enabled and self.sl_order_id:
                decision = self._emit_cancel_order(msg, self.sl_order_id, "OCO_TP_filled")

            self.tp_order_id = None
            self.sl_order_id = None
            return decision

        return None

    def _check_trailing_stop(self, msg: Message) -> Optional[Message]:
        """
        Check and adjust trailing stop if conditions met.

        Phase A3: Uses per-instrument trailing_stop config with global fallback.
        Implements high-water mark trailing with CANCEL+NEW flow.
        """
        # Get trailing params from per-instrument or global config
        enabled, activation_pct, trail_pct, min_update_sec = self._get_trailing_stop_params(self.symbol)

        if not enabled or not self.sl_order_id:
            return None

        try:
            pld = msg.pld or {}
            current_price = pld.get("mark_price") or pld.get("last_price")
            if not current_price:
                return None

            current_price_dec = Decimal(str(current_price))
            now = time.time()

            # Update peak price (high-water mark)
            if self.peak_price is None:
                self.peak_price = current_price_dec
            elif self.position_side == "BUY" and current_price_dec > self.peak_price:
                self.peak_price = current_price_dec
            elif self.position_side == "SELL" and current_price_dec < self.peak_price:
                self.peak_price = current_price_dec

            # Check activation condition
            if not self.trailing_activated and self.position_entry_price:
                if activation_pct is None:
                    activation_pct = 0.003  # Default 0.3%

                if self.position_side == "BUY":
                    activation_threshold = self.position_entry_price * (
                        Decimal("1") + Decimal(str(activation_pct))
                    )
                    if current_price_dec >= activation_threshold:
                        self.trailing_activated = True
                        self.peak_price = current_price_dec
                    else:
                        return None
                elif self.position_side == "SELL":
                    activation_threshold = self.position_entry_price * (
                        Decimal("1") - Decimal(str(activation_pct))
                    )
                    if current_price_dec <= activation_threshold:
                        self.trailing_activated = True
                        self.peak_price = current_price_dec
                    else:
                        return None

            # Rate limit: minimum interval between updates
            if now - self.last_trailing_ts < min_update_sec:
                return None

            # Calculate new SL price based on trail_pct from peak
            if trail_pct is None:
                trail_pct = 0.006  # Default 0.6%

            trail_pct_dec = Decimal(str(trail_pct))

            if self.position_side == "BUY" and self.sl_price and self.peak_price:
                # BUY: SL trails below peak
                new_sl_price = self.peak_price * (Decimal("1") - trail_pct_dec)
                # Only update if new SL is higher (tighter)
                if new_sl_price > self.sl_price:
                    return self._adjust_trailing_stop(msg, new_sl_price)

            elif self.position_side == "SELL" and self.sl_price and self.peak_price:
                # SELL: SL trails above peak (peak is low point)
                new_sl_price = self.peak_price * (Decimal("1") + trail_pct_dec)
                # Only update if new SL is lower (tighter)
                if new_sl_price < self.sl_price:
                    return self._adjust_trailing_stop(msg, new_sl_price)

        except (ValueError, TypeError, KeyError, ArithmeticError) as e:
            LOG.warning(f"Trailing stop check failed: {e}")
            self._metrics["fsm_errors_total"] += 1

        return None

    def _adjust_trailing_stop(self, msg: Message, new_sl_price: Decimal) -> Message:
        """
        Adjust trailing stop by cancelling old and placing new.

        Phase A3: CANCEL+NEW flow for trailing stop modification.
        """
        self.last_trailing_ts = time.time()
        self.sl_price = new_sl_price
        self._metrics["fsm_trailing_adjustments"] += 1

        # Cancel old SL
        cancel_msg = self._emit_cancel_order(
            msg, self.sl_order_id or "", "trailing_adjust")

        # Place new SL (will be handled by next message)
        position_id = f"{msg.rid}_{int(self.position_open_ts)}"
        new_client_id = f"{position_id}_sl_trail_{int(time.time())}"

        # Use opposite side for SL order (to close position)
        new_sl_msg = self._emit_place_order(
            msg,
            new_client_id,
            "STOP_MARKET",
            self._get_opposite_side(),
            str(self.position_qty),
            str(new_sl_price),
            "trailing_stop_adjust",
        )

        # Update SL order ID to new one
        self.sl_order_id = new_client_id

        # Return cancel first - new order will be placed on next cycle
        return cancel_msg

    def _emit_cancel_order(self, msg: Message, order_id: str, why: str) -> Message:
        """Emit DEC:CANCEL_ORDER with symbol included for adapter call."""
        msg_pld = msg.pld or {}
        symbol = msg_pld["symbol"] if "symbol" in msg_pld else ""
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
            qty_value = state_data.get("qty")
            entry_price_value = state_data.get("entry_price")
            self.position_qty = Decimal(str(qty_value)) if qty_value else None
            self.position_entry_price = Decimal(str(entry_price_value)) if entry_price_value else None
            self.position_side = state_data.get("side")
            self.position_open_ts = float(state_data["open_ts"] if "open_ts" in state_data else 0)

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
            LOG.error(f"Failed to hydrate ManageFlowFSM: {e}")
            self.state = ManageState.ERROR

    def reset(self):
        """Reset FSM state (for testing)."""
        self.state = ManageState.FLAT
        self.symbol = None  # Phase 0: clear symbol on reset
        self.position_qty = None
        self.position_entry_price = None
        self.position_open_ts = 0.0
        self.position_side = None
        # Bracket orders (legacy)
        self.sl_order_id = None
        self.tp_order_id = None
        self.sl_price = None
        self.tp_price = None
        # Phase A2: TP1/TP2
        self.tp1_order_id = None
        self.tp2_order_id = None
        self.tp1_price = None
        self.tp2_price = None
        self.partial_exit_pct = None
        # Phase A3: Trailing stop
        self.trailing_activated = False
        self.last_trailing_ts = 0.0
        self.peak_price = None
