"""
FSMP-P1-T02: Manage Flow FSM for execution_position domain.

States: FLAT → BRACKETS_PENDING → BRACKETS_PLACED → TRACKING
    ↔ EMIT_DEC_ADJUST ↔ TRACKING, WAIT_MODE (pause)
Rules (stubs): trail_pct, breakeven, time_stop
Output: DEC:ADJUST(tp?, sl?, move_to_be?)

Shadow-mode: decisions only, no live modifications.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Dict, Any, Optional
from vfoundation.services.price_service import PriceService

from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.brackets_config import (
    ResolvedBrackets,
    resolve_brackets_config,
)
from vfoundation.apps.reference.domains.execution_position.bracket_aggregator import (
    AggregatedOcoError,
    AggregatedOcoRiskConfig,
    InstrumentPriceConstraints,
    compute_aggregated_brackets,
)
from apps.reference.domains.execution_position.contracts import TPSLValidationRules
from apps.reference.domains.execution_position.manage_config import (
    ExecutionManageConfig,
    resolve_execution_manage_config,
)


agg_oco_logger = logging.getLogger("agg_oco")


try:
    from apps.reference.telemetry.metrics import inc_manage_skipped
except ImportError:

    def inc_manage_skipped() -> None:
        pass


class ManageState(str, Enum):
    """FSM states for manage flow."""

    FLAT = "FLAT"
    TRACKING = "TRACKING"
    BRACKETS_PENDING = "BRACKETS_PENDING"
    BRACKETS_PLACED = "BRACKETS_PLACED"
    EMIT_DEC_ADJUST = "EMIT_DEC_ADJUST"
    ERROR = "ERROR"
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
        price_service: Optional[PriceService] = None,
        order_guardian: Optional[Any] = None,
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

        # Aggregated OCO bookkeeping
        self._aggregated_last_place_ts: int = 0
        self._agg_side: Optional[str] = None

        # Configuration
        self.config = config or {}
        # Optional price service (SSOT) for mark/last/mid retrieval
        self.price_service: Optional[PriceService] = price_service
        self._order_guardian = order_guardian
        self._current_bracket_set_id: Optional[str] = None
        self._current_bracket_meta: Optional[Any] = None
        self._pending_bracket_log: Optional[Dict[str, Any]] = None
        # Emergency/WaitMode configuration
        # Using typed attribute access for Pydantic models
        try:
            if isinstance(self.config, dict):
                bar_gate_cfg = self.config.get("trading", {}).get(
                    "decision", {}).get("bar_gating", {})
                self._bar_ms = int(bar_gate_cfg.get(
                    "bar_ms", 15 * 60 * 1000)) if isinstance(bar_gate_cfg, dict) else 15 * 60 * 1000
            else:
                bar_gate_cfg = self.config.trading.decision.bar_gating if self.config.trading else None
                self._bar_ms = int(bar_gate_cfg.bar_ms) if bar_gate_cfg and hasattr(
                    bar_gate_cfg, 'bar_ms') else 15 * 60 * 1000
        except (AttributeError, TypeError, ValueError):
            self._bar_ms = 15 * 60 * 1000

        manage_cfg = self._manage_config()
        self._wait_mode_bars = manage_cfg.emergency.wait_mode_bars
        self._wait_mode_until_ts: int = 0

        # Anti-race window (ms) configurable via config; default 800ms
        try:
            if hasattr(self.config, 'execution') and self.config.execution:
                self._anti_race_close_ms = int(
                    getattr(self.config.execution, 'anti_race_close_ms', 800))
            elif hasattr(self.config, 'trading') and self.config.trading:
                exec_cfg = getattr(self.config.trading, 'execution', None)
                self._anti_race_close_ms = int(
                    getattr(exec_cfg, 'anti_race_close_ms', 800)) if exec_cfg else 800
            elif isinstance(self.config, dict):
                self._anti_race_close_ms = int(
                    self.config.get('execution', {}).get('anti_race_close_ms')
                    or self.config.get('trading', {}).get('execution', {}).get('anti_race_close_ms', 800)
                )
            else:
                self._anti_race_close_ms = 800
        except Exception:
            self._anti_race_close_ms = 800

        self._auto_manage_enabled = bool(manage_cfg.auto)

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
        qp_cfg = manage_cfg.quick_profit
        self.quick_profit_enabled = qp_cfg.enabled
        self.quick_profit_mode = qp_cfg.mode
        self.quick_profit_target_usd = qp_cfg.target_usd
        self.quick_profit_priority = qp_cfg.priority

    def _manage_config(self) -> ExecutionManageConfig:
        return resolve_execution_manage_config(self.config)

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
            qty_value = (
                pld.get("qty")
                if pld.get("qty") is not None
                else pld.get("quantity")
            )
            qty = Decimal(str(qty_value or 0))
            price = Decimal(str(pld.get("price", 0)))
            side = pld.get("side")  # BUY or SELL
            # Persist symbol for later lookups (used by _calculate_bracket_prices, _check_quick_profit etc.)
            try:
                self.symbol = pld.get("symbol") or getattr(
                    self, 'symbol', None)
            except Exception:
                # be defensive; symbol is optional
                pass

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

    def _place_brackets(self, msg: Message, reason: str = "entry_fill") -> Optional[Message]:
        if self._is_aggregated_oco_enabled():
            return self._place_brackets_aggregated(msg, reason=reason)
        return self._place_brackets_legacy(msg)

    def _place_brackets_legacy(self, msg: Message) -> Optional[Message]:
        """Place SL and TP bracket orders after position opens."""

        if not self._prepare_for_bracket_placement():
            return None

        try:
            resolved_brackets = resolve_brackets_config(
                self.config, symbol=getattr(self, "symbol", None)
            )

            # Calculate bracket prices
            sl_price, tp_price = self._calculate_bracket_prices(
                resolved_brackets
            )
            if sl_price is None or tp_price is None:
                self.state = ManageState.TRACKING
                print('[DEBUG] _place_brackets: sl_price or tp_price is None')
                return None

            self.sl_price = sl_price
            self.tp_price = tp_price

            # === VALIDATION PHASE: Check SL/TP prices before submission ===
            # Get current mark price (prefer PriceService if available, fallback to entry price)
            current_mark = self.position_entry_price
            try:
                if self.price_service and getattr(self, 'symbol', None):
                    quote = self.price_service.get_current(
                        getattr(self, 'symbol', None))
                    # Quote may be a PriceQuote dataclass; prefer mark then last
                    q_mark = getattr(quote, 'mark', None)
                    q_last = getattr(quote, 'last', None)
                    if q_mark is not None:
                        current_mark = Decimal(str(q_mark))
                    elif q_last is not None:
                        current_mark = Decimal(str(q_last))
            except Exception:
                # Do not block bracket placement on price service errors
                pass
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
                print('[DEBUG] _place_brackets: SL validation failed', sl_reason)
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
                print('[DEBUG] _place_brackets: TP validation failed', tp_reason)
                return None

            # === SAFETY OFFSET PHASE: Apply offset to avoid -2021 errors ===
            offset_bps = resolved_brackets.offset_bps

            # Get tick_size from somewhere (use 0.01 as default for now)
            # TODO: fetch from /exchangeInfo or cache
            tick_size = Decimal("0.01")

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

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._metrics["fsm_errors_total"] += 1
            self.state = ManageState.TRACKING
            return None

    def _prepare_for_bracket_placement(self) -> bool:
        """Common guard rails before emitting new bracket orders."""
        # PHASE A2: Anti-race check - skip if position is closing
        if self._closing_position:
            elapsed_s = time.time() - self._closing_position_ts
            if elapsed_s < (self._anti_race_close_ms / 1000.0):
                import logging
                LOG = logging.getLogger(__name__)
                LOG.info(
                    f"[BRK] skip:closing_flag elapsed={elapsed_s:.3f}s (<{self._anti_race_close_ms/1000.0:.1f}s)")
                self.state = ManageState.TRACKING
                return False
            self._closing_position = False

        import logging
        LOG = logging.getLogger(__name__)

        if self.sl_order_id or self.tp_order_id:
            LOG.info(
                f"[BRK] local bracket IDs present (SL={self.sl_order_id}, TP={self.tp_order_id}) → clearing phantoms")
            self.sl_order_id = None
            self.tp_order_id = None

        if not self._should_place_brackets():
            self.state = ManageState.TRACKING
            print('[DEBUG] _prepare_for_bracket_placement: placing disabled')
            return False

        return True

    def _place_brackets_aggregated(self, msg: Message, reason: str) -> Optional[Message]:
        if not self._prepare_for_bracket_placement():
            return None

        try:
            levels = self._compute_aggregated_bracket_levels(reason=reason)
        except AggregatedOcoError as exc:
            import logging
            LOG = logging.getLogger(__name__)
            LOG.warning(
                "[BRK][agg] failed to compute aggregated brackets: %s", exc)
            self.state = ManageState.TRACKING
            self._metrics["fsm_errors_total"] += 1
            return None

        return self._place_or_update_bracket_set_from_levels(msg, levels, reason)

    def _place_or_update_bracket_set_from_levels(
        self,
        msg: Message,
        levels,
        reason: str,
    ) -> Optional[Message]:
        if self.position_qty is None or self.position_side is None:
            return None

        agg_side = self._convert_position_side()
        self._agg_side = agg_side

        sl_before = self.sl_price
        tp_before = self.tp_price
        qty_before = self.position_qty
        avg_before = self.position_entry_price
        action = self._map_reason_to_action(reason)

        # Ensure we track the new bracket prices
        self.sl_price = levels.sl_price
        self.tp_price = levels.tp_price
        self.state = ManageState.BRACKETS_PENDING

        self._pending_bracket_log = {
            "action": action,
            "position_qty_before": str(qty_before) if qty_before is not None else None,
            "position_qty_after": str(self.position_qty) if self.position_qty is not None else None,
            "avg_price_before": str(avg_before) if avg_before is not None else None,
            "avg_price_after": str(self.position_entry_price) if self.position_entry_price is not None else None,
            "sl_price_before": str(sl_before) if sl_before is not None else None,
            "sl_price_after": str(levels.sl_price) if levels.sl_price is not None else None,
            "tp_price_before": str(tp_before) if tp_before is not None else None,
            "tp_price_after": str(levels.tp_price) if levels.tp_price is not None else None,
            "why": self._clip_why(levels.why),
            "rid": getattr(msg, "rid", None),
        }

        position_id = getattr(msg, "rid", "agg") or "agg"
        timestamp_suffix = str(int(time.time()))
        base_client_id = f"{position_id}_{timestamp_suffix}"

        sl_client_id = f"{base_client_id}_sl"
        tp_client_id = f"{base_client_id}_tp"

        self._current_bracket_set_id = base_client_id

        qty_str = str(self.position_qty)
        opposite_side = self._get_opposite_side()

        sl_order = self._emit_place_order(
            msg,
            sl_client_id,
            "STOP_MARKET",
            opposite_side,
            qty_str,
            str(levels.sl_price),
            levels.why,
        )

        self._emit_place_order(
            msg,
            tp_client_id,
            "LIMIT",
            opposite_side,
            qty_str,
            str(levels.tp_price),
            levels.why,
        )

        self._metrics["fsm_bracket_orders_placed"] += 2
        self._aggregated_last_place_ts = int(time.time() * 1000)
        return sl_order

    def _maybe_register_bracket_set(self) -> None:
        if not (self._order_guardian and self._is_aggregated_oco_enabled()):
            self._pending_bracket_log = None
            return
        if not self.sl_order_id and not self.tp_order_id:
            self._pending_bracket_log = None
            return

        symbol = getattr(self, "symbol", None)
        side = self.position_side
        if not symbol or not side:
            self._pending_bracket_log = None
            return

        agg_side = self._agg_side
        if not agg_side and side:
            try:
                agg_side = self._convert_position_side()
            except AggregatedOcoError:
                agg_side = None
        if not agg_side:
            self._pending_bracket_log = None
            return

        bracket_set_id = self._current_bracket_set_id or self._build_fallback_bracket_set_id()

        try:
            meta = self._order_guardian.register_bracket_set(
                bracket_set_id=bracket_set_id,
                symbol=symbol,
                side=agg_side,
                sl_order_id=self.sl_order_id,
                tp_order_id=self.tp_order_id,
                created_ts=time.time(),
            )
            self._current_bracket_meta = meta
            self._log_bracket_set_event(meta, self._pending_bracket_log)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "[BRK][agg] failed to register bracket set", exc_info=exc
            )
            self._pending_bracket_log = None

    def _build_fallback_bracket_set_id(self) -> str:
        symbol = getattr(self, "symbol", "unknown") or "unknown"
        side = self.position_side or "SIDELESS"
        return f"{symbol}:{side}:{int(time.time() * 1000)}"

    def _clear_guardian_bracket_set(self, symbol: Optional[str], side: Optional[str]) -> None:
        if not (self._order_guardian and self._is_aggregated_oco_enabled()):
            return
        if not symbol or not side:
            return
        # Aggregated OCO side must already be canonical ("LONG"/"SHORT").
        try:
            self._order_guardian.clear_bracket_set_for_position(
                symbol=symbol,
                side=side,
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "[BRK][agg] failed to clear bracket set", exc_info=exc
            )

    @staticmethod
    def _map_reason_to_action(reason: Optional[str]) -> str:
        mapping = {
            "entry_fill": "create",
            "scale_in_fill": "recalc_scale_in",
            "partial_close_fill": "recalc_partial",
            "partial_close_unprotected": "recalc_manual_fix",
        }
        if not reason:
            return "create"
        return mapping.get(reason, reason)

    @staticmethod
    def _clip_why(value: Optional[Any]) -> Optional[str]:
        if value is None:
            return None
        return str(value)[:80]

    def _log_bracket_set_event(self, meta: Any, context: Optional[Dict[str, Any]]) -> None:
        if not meta or context is None:
            self._pending_bracket_log = None
            return

        action = context.get("action") or "create"
        if getattr(meta, "version", 0) == 0 and action not in {"cleanup_full_close", "flip_reset"}:
            action = "create"

        extra = {
            "event_type": "AGG_OCO_BRACKET_SET_CHANGED",
            "symbol": getattr(meta, "symbol", None),
            "side": getattr(meta, "side", None),
            "bracket_set_id": getattr(meta, "bracket_set_id", None),
            "version": getattr(meta, "version", None),
            "action": action,
            "position_qty_before": context.get("position_qty_before"),
            "position_qty_after": context.get("position_qty_after"),
            "avg_price_before": context.get("avg_price_before"),
            "avg_price_after": context.get("avg_price_after"),
            "sl_price_before": context.get("sl_price_before"),
            "sl_price_after": context.get("sl_price_after"),
            "tp_price_before": context.get("tp_price_before"),
            "tp_price_after": context.get("tp_price_after"),
            "why": self._clip_why(context.get("why")),
            "rid": context.get("rid"),
        }

        agg_oco_logger.info("Aggregated OCO bracket set changed", extra=extra)
        self._pending_bracket_log = None

    def _compute_aggregated_bracket_levels(self, *, reason: str):
        if (
            self.position_qty is None
            or self.position_entry_price is None
            or self.position_side is None
        ):
            raise AggregatedOcoError("position snapshot is incomplete")

        resolved = resolve_brackets_config(
            self.config, symbol=getattr(self, "symbol", None)
        )

        sl_bps = Decimal(str(resolved.sl_bps))
        tp_bps = Decimal(str(resolved.tp_bps))
        if sl_bps <= 0:
            raise AggregatedOcoError("sl_bps must be > 0 for aggregated OCO")

        sl_pct = sl_bps / Decimal("10000")
        tp_rr = tp_bps / sl_bps if tp_bps > 0 else Decimal("1")

        risk_cfg = AggregatedOcoRiskConfig(
            sl_pct=sl_pct,
            tp_rr=tp_rr,
        )

        constraints = self._get_instrument_constraints()
        side = self._convert_position_side()

        return compute_aggregated_brackets(
            position_amt=abs(self.position_qty),
            avg_entry_price=self.position_entry_price,
            side=side,
            risk_cfg=risk_cfg,
            constraints=constraints,
            why=reason,
        )

    def _get_instrument_constraints(self) -> InstrumentPriceConstraints:
        tick_size = self._lookup_instrument_value(
            "tick_size") or Decimal("0.01")
        min_price = (
            self._lookup_instrument_value("min_price")
            or tick_size
            or Decimal("0.01")
        )
        return InstrumentPriceConstraints(
            tick_size=tick_size,
            min_price=min_price,
        )

    def _lookup_instrument_value(self, field: str) -> Optional[Decimal]:
        symbol = getattr(self, "symbol", None)
        if not symbol:
            return None

        trading_cfg = getattr(self.config, "trading", None)
        if trading_cfg:
            instruments = getattr(trading_cfg, "instruments", None)
            if hasattr(instruments, "model_dump"):
                instruments = instruments.model_dump()
            value = self._extract_instrument_field(instruments, symbol, field)
            dec_value = self._coerce_decimal_value(value)
            if dec_value is not None:
                return dec_value

        if isinstance(self.config, dict):
            instruments = self.config.get("trading", {}).get("instruments", {})
            value = self._extract_instrument_field(instruments, symbol, field)
            dec_value = self._coerce_decimal_value(value)
            if dec_value is not None:
                return dec_value

        return None

    @staticmethod
    def _extract_instrument_field(source: Any, symbol: str, field: str) -> Any:
        if not source or symbol not in source:
            return None
        sym_cfg = source.get(symbol)
        if isinstance(sym_cfg, dict):
            return sym_cfg.get(field)
        try:
            return getattr(sym_cfg, field)
        except Exception:
            return None

    @staticmethod
    def _coerce_decimal_value(value: Any) -> Optional[Decimal]:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None

    def _convert_position_side(self) -> str:
        if self.position_side == "BUY":
            return "LONG"
        if self.position_side == "SELL":
            return "SHORT"
        raise AggregatedOcoError(
            f"Unsupported position side for aggregated OCO: {self.position_side}"
        )

    def _is_aggregated_oco_enabled(self) -> bool:
        try:
            return bool(self._manage_config().brackets.aggregated_oco.enabled)
        except Exception:
            return False

    def _handle_aggregated_fill_event(self, msg: Message) -> Optional[Message]:
        agg_cfg = self._manage_config().brackets.aggregated_oco
        pld = msg.pld or {}

        qty_value = (
            pld.get("qty")
            if pld.get("qty") is not None
            else pld.get("quantity")
        )
        if qty_value is None:
            return None

        try:
            fill_qty = Decimal(str(qty_value))
        except (InvalidOperation, ValueError, TypeError):
            return None

        if fill_qty <= 0:
            return None

        order_type = str(pld.get("order_type") or pld.get("type") or "")
        close_position = (
            str(pld.get("closePosition") or pld.get("cp") or "")
            .strip()
            .lower()
            == "true"
        )
        reduce_only = (
            str(pld.get("reduceOnly") or "")
            .strip()
            .lower()
            == "true"
        )
        is_exit_fill = order_type in {
            "TAKE_PROFIT_MARKET", "STOP_MARKET"} or close_position or reduce_only

        if is_exit_fill:
            remaining = self._apply_exit_fill(fill_qty)
            if remaining is None:
                return None
            if remaining == 0:
                self._clear_position_state()
                return None
            if agg_cfg.recalc_on_partial_close:
                return self._recalc_aggregated_brackets(msg, reason="partial_close_fill")
            if self._needs_bracket_recalc_after_partial_close(agg_cfg):
                return self._recalc_aggregated_brackets(
                    msg,
                    reason="partial_close_unprotected",
                )
            return None

        was_open = self.position_qty is not None
        self._on_fill(msg)
        if was_open and agg_cfg.recalc_on_scale_in:
            return self._recalc_aggregated_brackets(msg, reason="scale_in_fill")
        return None

    def _needs_bracket_recalc_after_partial_close(self, agg_cfg) -> bool:
        if agg_cfg.allow_unprotected_position:
            return False
        if self.position_qty is None or self.position_qty == 0:
            return False
        # Require both SL and TP ids so Guardian can protect the set.
        return (self.sl_order_id is None) or (self.tp_order_id is None)

    def _apply_exit_fill(self, fill_qty: Decimal) -> Optional[Decimal]:
        if self.position_qty is None:
            return None

        remaining = self.position_qty - abs(fill_qty)
        if remaining <= 0:
            self.position_qty = None
            return Decimal("0")

        self.position_qty = remaining
        return remaining

    def _clear_position_state(self) -> None:
        symbol = getattr(self, "symbol", None)
        prev_side = self.position_side
        agg_side = self._agg_side
        if not agg_side and prev_side:
            if prev_side == "BUY":
                agg_side = "LONG"
            elif prev_side == "SELL":
                agg_side = "SHORT"
        cleanup_context = {
            "action": "cleanup_full_close",
            "position_qty_before": str(self.position_qty) if self.position_qty is not None else None,
            "position_qty_after": "0",
            "avg_price_before": str(self.position_entry_price) if self.position_entry_price is not None else None,
            "avg_price_after": None,
            "sl_price_before": str(self.sl_price) if self.sl_price is not None else None,
            "sl_price_after": None,
            "tp_price_before": str(self.tp_price) if self.tp_price is not None else None,
            "tp_price_after": None,
            "why": self._clip_why("cleanup_full_close"),
            "rid": None,
        }
        self._log_bracket_set_event(
            self._current_bracket_meta, cleanup_context)
        self.position_qty = None
        self.position_entry_price = None
        self.position_side = None
        self.position_open_ts = 0.0
        self.sl_order_id = None
        self.tp_order_id = None
        self.sl_price = None
        self.tp_price = None
        self._current_bracket_set_id = None
        self._current_bracket_meta = None
        self._aggregated_last_place_ts = 0
        self._agg_side = None
        self.state = ManageState.FLAT
        self._clear_guardian_bracket_set(symbol, agg_side)

    def _recalc_aggregated_brackets(self, msg: Message, *, reason: str) -> Optional[Message]:
        agg_cfg = self._manage_config().brackets.aggregated_oco
        now_ms = int(time.time() * 1000)
        ttl_ms = max(int(agg_cfg.ttl_protect_new_bracket_ms or 0), 0)

        if self._aggregated_last_place_ts and ttl_ms > 0:
            elapsed = now_ms - self._aggregated_last_place_ts
            if elapsed < ttl_ms:
                if agg_cfg.allow_unprotected_position or (
                    self.sl_order_id or self.tp_order_id
                ):
                    import logging

                    LOG = logging.getLogger(__name__)
                    LOG.info(
                        "[BRK][agg] skip recalc reason=%s elapsed=%sms ttl=%sms",
                        reason,
                        elapsed,
                        ttl_ms,
                    )
                    return None

        return self._place_brackets_aggregated(msg, reason=reason)

    def _should_place_brackets(self) -> bool:
        """Check if brackets should be placed based on config."""
        brackets_cfg = self._manage_config().brackets
        return bool(brackets_cfg.enable)

    def _calculate_bracket_prices(
        self, resolved: ResolvedBrackets
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """Calculate SL and TP prices based on config and position.

        Supports both NEW and LEGACY config keys:
        - NEW: execution.manage.brackets.sl.fixed_bps, execution.manage.brackets.tp.fixed_bps
        - LEGACY: execution.manage.brackets.stop_loss_bps, take_profit_low_ratio, take_profit_high_ratio

        Fallback chain:
        1. Try new keys (sl.fixed_bps, tp.fixed_bps)
        2. If not found, fallback to legacy keys for backward compatibility
        """
        if self.position_entry_price is None or self.position_side is None:
            return None, None

        try:
            entry_price = self.position_entry_price

            sl_bps = resolved.sl_bps
            tp_bps = resolved.tp_bps

            if self.position_side == "BUY":
                sl_price = entry_price * (1 - Decimal(str(sl_bps)) / 10000)
            else:  # SELL
                sl_price = entry_price * (1 + Decimal(str(sl_bps)) / 10000)

            if self.position_side == "BUY":
                tp_price = entry_price * (1 + Decimal(str(tp_bps)) / 10000)
            else:  # SELL
                tp_price = entry_price * (1 - Decimal(str(tp_bps)) / 10000)

            # ========== Quantize prices to tick_size ==========
            # Read tick_size from config if available
            tick_size = None
            try:
                symbol = getattr(self, 'symbol', None)
                brackets_cfg = getattr(self.config, "trading", None)
                if brackets_cfg:
                    instruments = getattr(brackets_cfg, "instruments", None)
                    if hasattr(instruments, "model_dump"):
                        instruments = instruments.model_dump()
                    if isinstance(instruments, dict):
                        sym_config = instruments.get(
                            symbol, {}) if symbol else {}
                        if isinstance(sym_config, dict):
                            tick_size = sym_config.get("tick_size")
                        elif hasattr(sym_config, "tick_size"):
                            tick_size = getattr(sym_config, "tick_size")
                elif isinstance(self.config, dict):
                    instruments = (
                        self.config.get("trading", {})
                        .get("instruments", {})
                    )
                    sym_config = instruments.get(symbol, {}) if symbol else {}
                    if isinstance(sym_config, dict):
                        tick_size = sym_config.get("tick_size")
            except (AttributeError, TypeError, KeyError):
                tick_size = None

            # Apply tick_size quantization if available
            if tick_size:
                try:
                    tick_size_dec = Decimal(str(tick_size))
                    # Round down to nearest tick (conservative for SL/TP)
                    sl_price = (
                        sl_price / tick_size_dec).quantize(Decimal('1')) * tick_size_dec
                    tp_price = (
                        tp_price / tick_size_dec).quantize(Decimal('1')) * tick_size_dec
                except (ValueError, TypeError, ArithmeticError):
                    # If quantization fails, use original prices
                    pass

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

        # Get workingType and priceProtect from config
        working_type = "MARK_PRICE"  # Default
        price_protect = False  # Default
        brackets_meta = self._manage_config().brackets
        working_type = brackets_meta.working_type_default or "MARK_PRICE"
        price_protect = bool(brackets_meta.price_protect)

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
                self._maybe_register_bracket_set()

        return None

    def _check_quick_profit(self, msg: Message) -> Optional[Message]:
        """PRIORITY CHECK: Close position if quick profit target reached.

        Returns DEC:CLOSE if threshold hit, otherwise None.
        """
        if not self.quick_profit_enabled:
            return None

        if self.position_qty is None or self.position_entry_price is None:
            return None

        try:
            # Prefer PriceService if available
            current_price = None
            try:
                if self.price_service and getattr(self, 'symbol', None):
                    quote = self.price_service.get_current(
                        getattr(self, 'symbol', None))
                    # Prefer mark, then last, then mid
                    current_price = getattr(quote, 'mark', None) or getattr(
                        quote, 'last', None) or getattr(quote, 'mid', None)
            except Exception:
                # On any price service error, fallback to payload
                current_price = None

            if current_price is None:
                pld = msg.pld or {}
                current_price = pld.get('mark_price') or pld.get(
                    'last_price') or pld.get('price')
            if current_price is None:
                return None
            current_price_dec = Decimal(str(current_price))

            if self.position_side == 'BUY':
                pnl_per_unit = current_price_dec - self.position_entry_price
            else:
                pnl_per_unit = self.position_entry_price - current_price_dec

            total_pnl_usd = pnl_per_unit * abs(self.position_qty)
            # If using percentage mode, target may be relative; only fixed_usd supported now
            if total_pnl_usd >= self.quick_profit_target_usd:
                import logging
                LOG = logging.getLogger(__name__)
                LOG.info(
                    f"🎯 QUICK PROFIT HIT: symbol={getattr(self,'symbol', None)} pnl_usd={total_pnl_usd} target={self.quick_profit_target_usd}")
                # Emit close decision - do not cancel brackets here; ExecPosFSM will do cleanup
                details = {
                    'rule': 'quick_profit',
                    'pnl_usd': str(total_pnl_usd),
                    'current_price': str(current_price_dec),
                    'target_usd': str(self.quick_profit_target_usd)
                }
                return self._emit_close(msg, 'QUICK_PROFIT_HIT', details)
        except Exception:
            self._metrics['fsm_errors_total'] = self._metrics.get(
                'fsm_errors_total', 0) + 1
        return None

    def _check_rules(self, msg: Message) -> Optional[Message]:
        """
        Check management rules: brackets, trailing stop, breakeven, time_stop.

        Returns:
            DEC:PLACE_ORDER, DEC:CANCEL_ORDER, or DEC:ADJUST if rule triggers, None otherwise.
        """
        if self.position_qty is None or self.position_entry_price is None:
            return None

        if (
            self._is_aggregated_oco_enabled()
            and msg.op == "EVT"
            and msg.verb in ("PARTIAL_FILL", "FILL", "TRADE_EXECUTED")
        ):
            agg_decision = self._handle_aggregated_fill_event(msg)
            if agg_decision:
                return agg_decision

        # PRIORITY: Quick profit rule (highest priority)
        try:
            if self.quick_profit_enabled and self.quick_profit_priority == 'highest':
                qp = self._check_quick_profit(msg)
                if qp:
                    return qp
        except Exception:
            # Do not block other rules if quick_profit check fails
            self._metrics['fsm_errors_total'] = self._metrics.get(
                'fsm_errors_total', 0) + 1

        try:
            emergency_cfg = self._manage_config().emergency
            emergency_enabled = emergency_cfg.enabled
            emergency_sl_bps = emergency_cfg.sl_bps
        except Exception:
            emergency_enabled = False
            emergency_sl_bps = Decimal("100")

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

        try:
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
                        {"rule": "trail", "trigger_price": str(
                            trail_trigger)},
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
            oco_enabled = bool(self._manage_config().brackets.oco_emulation)

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
            oco_enabled = bool(self._manage_config().brackets.oco_emulation)

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
            trailing_cfg = self._manage_config().trailing
            if not trailing_cfg.enabled or not self.sl_order_id:
                return None

            pld = msg.pld or {}
            current_price = pld.get("mark_price") or pld.get("last_price")
            if not current_price:
                return None

            current_price_dec = Decimal(str(current_price))
            now = time.time()

            # Check activation condition
            if not self.trailing_activated and self.position_entry_price:
                # Get activation_profit_atr_k
                activation_k = float(
                    trailing_cfg.activation_profit_atr_k or 1.0)

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
            if now - self.last_trailing_ts < float(trailing_cfg.cooldown_sec or 0.0):
                return None

            # Calculate new SL price
            step_bps = trailing_cfg.step_bps
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

    def _emit_close(self, msg: Message, why: str, details: Dict[str, Any]) -> Message:
        """Generate DEC:CLOSE with reduce_only=true and include symbol when available.

        This mirrors CloseFlowFSM._emit_close, but is emitted from ManageFlowFSM.
        """
        self.state = ManageState.EMIT_DEC_ADJUST
        self._metrics["fsm_adjust_decisions_total"] = self._metrics.get(
            "fsm_adjust_decisions_total", 0) + 1

        symbol = (msg.pld or {}).get("symbol") or getattr(self, 'symbol', None)

        dec = Message(
            op="DEC",
            verb="CLOSE",
            src=msg.dst,
            dst="execution_position",
            rid=msg.rid,
            why=why[:80],
            idempotent_key=f"{msg.rid}_{why}_{int(time.time())}",
            pld={
                "reduce_only": True,
                **({"symbol": symbol} if symbol else {}),
                **details,
            },
            data_ref=msg.data_ref.copy() if msg.data_ref else [],
        )

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
                str(state_data.get("qty", state_data.get("quantity", 0)))) if state_data.get("qty") or state_data.get("quantity") else None
            self.position_entry_price = Decimal(str(state_data.get(
                "entry_price", 0))) if state_data.get("entry_price") else None
            self.position_side = state_data.get("side")
            self.position_open_ts = float(state_data.get("open_ts", 0))

            # Restore bracket data
            self.sl_order_id = state_data.get("sl_order_id")
            self.tp_order_id = state_data.get("tp_order_id")
            # Restore symbol if present
            try:
                self.symbol = state_data.get(
                    'symbol', getattr(self, 'symbol', None))
            except Exception:
                self.symbol = getattr(self, 'symbol', None)

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
