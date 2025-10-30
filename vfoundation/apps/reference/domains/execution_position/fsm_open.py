"""
FSMP-P1-T02: Open Flow FSM for execution_position domain.

States: IDLE → CANDIDATE → READY → EMIT_DEC_OPEN → DONE
Guards: min_notional, qty/price steps, cooldown
Output: DEC:OPEN(symbol, side, qty, price?, tif?)

Shadow-mode: no live API calls, all I/O via ACL stub.
"""

from __future__ import annotations

import time
import logging
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Dict, Optional, Any

from vfoundation.core.protocol import Message
from .contracts import (
    MIN_ORDER_QTY,
    MIN_NOTIONAL,
    QTY_STEP,
    PRICE_STEP,
)
from .exposure_guard import ExposureGuard


class OpenState(str, Enum):
    """FSM states for open flow."""

    IDLE = "IDLE"
    CANDIDATE = "CANDIDATE"
    READY = "READY"
    EMIT_DEC_OPEN = "EMIT_DEC_OPEN"
    DONE = "DONE"
    ERROR = "ERROR"


class OpenFlowFSM:
    """
    Open Flow FSM: processes CMD:OPEN and emits DEC:OPEN after guards.

    Shadow-mode: validates contracts, generates DEC, but no live orders.
    Guards (fail-closed): min_notional, qty/price steps, cooldown.
    """

    def __init__(
        self,
        cooldown_sec: float = 1.0,
        guard_enabled: bool = True,
        config: Optional[Dict] = None,
        exposure_guard: Optional[ExposureGuard] = None,
    ):
        self.state = OpenState.IDLE
        self.cooldown_sec = cooldown_sec
        self.guard_enabled = guard_enabled
        self.config = config or {}
        self.exposure_guard = exposure_guard
        self.last_open_ts: float = 0.0
        self.logger = logging.getLogger(__name__)
        self._metrics: Dict[str, int] = {
            "fsm_open_decisions_total": 0,
            "fsm_guard_rejects_total": 0,
            "fsm_errors_total": 0,
        }

    def _get_instrument_specs(self, symbol: str) -> Dict[str, Decimal]:
        """Get instrument specifications from config."""
        instruments = self.config.get("trading", {}).get("instruments", {})
        specs = instruments.get(symbol, {})

        # Convert values to Decimal with proper error handling
        def to_decimal(value: Any, default: Decimal) -> Decimal:
            if isinstance(value, Decimal):
                return value
            try:
                return Decimal(str(value))
            except (ValueError, TypeError, InvalidOperation):
                return default

        return {
            "min_qty": to_decimal(specs.get("min_qty"), MIN_ORDER_QTY),
            "step_size": to_decimal(specs.get("step_size"), QTY_STEP),
            "tick_size": to_decimal(specs.get("tick_size"), PRICE_STEP),
            "min_notional": to_decimal(specs.get("min_notional"), MIN_NOTIONAL),
        }

    def handle(self, msg: Message) -> Optional[Message]:
        """
        Process incoming message and return DEC:OPEN if guards pass.

        Args:
            msg: CMD:OPEN with pld: symbol, side, qty, price?, order_type?, tif?

        Returns:
            DEC:OPEN if guards pass, ERR if guards fail, None if not applicable.
        """
        if msg.op == "CMD" and msg.verb == "OPEN":
            # Extract and validate pld
            try:
                pld = msg.pld or {}
                symbol = pld.get("symbol")
                side = pld.get("side")
                qty = pld.get("qty")
                price = pld.get("price")
                order_type = pld.get("order_type", "MARKET")
                tif = pld.get("tif", "GTC")

                if not symbol or not side:
                    self.logger.error(
                        f"GUARD_REJECT: Missing required fields - symbol={symbol}, side={side}, rid={msg.rid}"
                    )
                    return self._reject(msg, "OPEN_GUARD_FAIL", "missing symbol or side")

                # Get instrument specifications
                specs = self._get_instrument_specs(symbol)
                min_qty = specs["min_qty"]
                step_size = specs["step_size"]
                tick_size = specs["tick_size"]
                min_notional = specs["min_notional"]

                # Convert to Decimal
                qty_dec = Decimal(str(qty)) if qty is not None else None
                price_dec = Decimal(str(price)) if price is not None else None
                price_ref = (
                    Decimal(str(pld.get("price_ref"))) if pld.get("price_ref") is not None else None
                )

                # Guard: qty bounds
                if qty_dec is None or qty_dec < min_qty:
                    self.logger.error(
                        f"GUARD_REJECT: Quantity below minimum - qty={qty_dec}, min={min_qty}, rid={msg.rid}"
                    )
                    return self._reject(msg, "OPEN_GUARD_FAIL", f"qty below minimum {min_qty}")

                # Guard: qty step (round down to step_size)
                qty_rounded = (qty_dec // step_size) * step_size
                if qty_rounded != qty_dec:
                    self.logger.warning(
                        f"GUARD_ADJUST: Quantity rounded down - original={qty_dec}, rounded={qty_rounded}, step={step_size}, rid={msg.rid}"
                    )
                    qty_dec = qty_rounded  # Use rounded quantity for further checks

                # Guard: price bounds (for LIMIT orders)
                if order_type == "LIMIT":
                    if price_dec is None:
                        self.logger.error(
                            f"GUARD_REJECT: LIMIT order missing price - order_type={order_type}, price={price}, rid={msg.rid}"
                        )
                        return self._reject(msg, "OPEN_GUARD_FAIL", "LIMIT order requires price")

                    # Round price to tick_size
                    price_rounded = ((price_dec // tick_size) * tick_size).quantize(tick_size)
                    if price_rounded != price_dec:
                        self.logger.warning(
                            f"GUARD_ADJUST: Price rounded to tick - original={price_dec}, rounded={price_rounded}, tick={tick_size}, rid={msg.rid}"
                        )
                        price_dec = price_rounded

                # Guard: qty step (removed - now auto-rounded above)

                # Guard: price step (removed - now auto-rounded above)

                # Guard: min_notional
                if order_type == "LIMIT" and price_dec is not None:
                    notional = qty_dec * price_dec
                    if notional < min_notional:
                        self.logger.error(
                            f"GUARD_REJECT: Notional below minimum - notional={notional}, min={min_notional}, qty={qty_dec}, price={price_dec}, rid={msg.rid}"
                        )
                        return self._reject(
                            msg, "OPEN_GUARD_FAIL", f"notional {notional} < {min_notional}"
                        )

                # Guard: min_notional for MARKET orders (approximate check using current market price)
                elif order_type == "MARKET" and price_ref is not None:
                    notional = qty_dec * price_ref
                    if notional < min_notional:
                        self.logger.error(
                            f"GUARD_REJECT: Estimated notional below minimum - notional={notional}, min={min_notional}, qty={qty_dec}, price_ref={price_ref}, rid={msg.rid}"
                        )
                        return self._reject(
                            msg,
                            "OPEN_GUARD_FAIL",
                            f"estimated notional {notional} < {min_notional}",
                        )

                # Guard: cooldown
                now = time.time()
                if self.guard_enabled and now - self.last_open_ts < self.cooldown_sec:
                    self.logger.warning(
                        f"GUARD_REJECT: Cooldown active - elapsed={now - self.last_open_ts:.2f}s, required={self.cooldown_sec}s, rid={msg.rid}"
                    )
                    return self._reject(msg, "OPEN_GUARD_FAIL", "cooldown active")

                # Guard: portfolio exposure limit
                if self.exposure_guard:
                    # Calculate notional for exposure check
                    if order_type == "LIMIT" and price_dec is not None:
                        notional_usd = qty_dec * price_dec
                    elif order_type == "MARKET":
                        if price_ref is None:
                            self.logger.error(
                                f"GUARD_REJECT: MARKET order missing price_ref - order_type={order_type}, price_ref={price_ref}, rid={msg.rid}"
                            )
                            return self._reject(
                                msg, "NO_PRICE_REF", "MARKET order requires price_ref"
                            )
                        notional_usd = qty_dec * price_ref
                    else:
                        # For other order types, skip exposure check (fail-closed)
                        notional_usd = Decimal("0")

                    if notional_usd > 0:
                        allowed, exposure_data = self.exposure_guard.can_open(notional_usd)
                        if not allowed:
                            self.logger.warning(
                                f"GUARD_REJECT: Portfolio exposure limit exceeded - "
                                f"equity={exposure_data['equity_usd']}, limit={exposure_data['limit_usd']}, "
                                f"positions={exposure_data['positions_usd']}, pending={exposure_data['pending_usd']}, "
                                f"new={exposure_data['new_usd']}, will_be={exposure_data['exposure_will_be_usd']}, rid={msg.rid}"
                            )
                            return self._reject_exposure(msg, exposure_data)

                        # Reserve exposure for pending order
                        reserve_key = msg.pld.get("idempotent_key") or msg.rid or f"rid_{msg.rid}"
                        reduce_only = pld.get("reduce_only", False) or pld.get(
                            "close_position", False
                        )
                        self.exposure_guard.reserve(reserve_key, notional_usd, reduce_only)

                # All guards passed → generate DEC:OPEN
                dec_pld = {
                    "symbol": symbol,
                    "side": side,
                    "qty": str(qty_dec),
                    "order_type": order_type,
                    "tif": tif,
                }
                if price_dec is not None:
                    dec_pld["price"] = str(price_dec)

                # Pass through idempotent_key from CMD:OPEN payload (AURORA_IDEMPOTENCY_V1)
                if "idempotent_key" in msg.pld:
                    dec_pld["idempotent_key"] = msg.pld["idempotent_key"]
                    self.logger.info(
                        f"IDEMPOTENCY: Passing key {msg.pld['idempotent_key']} to DEC:OPEN"
                    )

                self.logger.info(
                    f"GUARD_PASSED: All guards OK - symbol={symbol}, side={side}, qty={qty_dec}, price={price_dec}, order_type={order_type}, rid={msg.rid}"
                )

                dec = Message(
                    op="DEC",
                    verb="OPEN",
                    src=msg.dst,  # FSM as source
                    dst="execution_position",
                    rid=msg.rid,
                    why="OPEN_OK",
                    pld=dec_pld,
                )

                # Update state and metrics
                self.state = OpenState.DONE
                self.last_open_ts = now
                self._metrics["fsm_open_decisions_total"] += 1

                return dec

            except Exception as e:
                self._metrics["fsm_errors_total"] += 1
                self.state = OpenState.ERROR
                self.logger.exception(
                    f"FSM_EXCEPTION: Unexpected error processing CMD:OPEN - rid={msg.rid}, error={str(e)}"
                )
                return Message(
                    op="ERR",
                    verb="OPEN",
                    src=msg.dst,
                    dst=msg.src,
                    rid=msg.rid,
                    why=f"FSM exception: {str(e)[:60]}",
                    pld={"error": str(e)},
                )

        elif msg.op == "EVT" and msg.verb == "READY" and self.state == OpenState.CANDIDATE:
            self.state = OpenState.READY
            return None

        elif msg.op == "EVT" and msg.verb == "EXECUTE" and self.state == OpenState.READY:
            # Generate DEC:OPEN
            pld = msg.pld or {}
            symbol = pld.get("symbol")
            side = pld.get("side")
            qty = pld.get("qty")
            price = pld.get("price")

            dec_pld = {
                "symbol": symbol,
                "side": side,
                "qty": str(qty),
                "order_type": "LIMIT",
                "tif": "GTC",
            }
            if price is not None:
                dec_pld["price"] = str(price)

            dec = Message(
                op="DEC",
                verb="OPEN",
                src=msg.dst,  # FSM as source
                dst="execution_position",
                rid=msg.rid,
                why="OPEN_OK",
                idempotent_key=msg.idempotent_key,
                pld=dec_pld,
            )

            # Update state and metrics
            self.state = OpenState.DONE
            self.last_open_ts = time.time()
            self._metrics["fsm_open_decisions_total"] += 1

            return dec

        return None

    def _check_qty_step(self, qty: Decimal) -> bool:
        """Check if qty is multiple of QTY_STEP."""
        remainder = qty % QTY_STEP
        return remainder == 0

    def _check_price_step(self, price: Decimal) -> bool:
        """Check if price is multiple of PRICE_STEP."""
        remainder = price % PRICE_STEP
        return remainder == 0

    def _reject(self, msg: Message, why: str, reason: str) -> Message:
        """Generate ERR message for guard failures."""
        self._metrics["fsm_guard_rejects_total"] += 1
        if reason != "cooldown active":
            self.state = OpenState.ERROR
        return Message(
            op="ERR",
            verb="OPEN",
            src=msg.dst,
            dst=msg.src,
            rid=msg.rid,
            why=why[:80],
            pld={"reason": reason},
        )

    def _reject_exposure(self, msg: Message, exposure_data: Dict[str, str]) -> Message:
        """Generate ERR message for portfolio exposure limit violations."""
        self._metrics["fsm_guard_rejects_total"] += 1
        self.state = OpenState.ERROR
        return Message(
            op="ERR",
            verb="OPEN",
            src=msg.dst,
            dst=msg.src,
            rid=msg.rid,
            why="PORTFOLIO_EXPOSURE_LIMIT",
            pld={
                "reason": "PORTFOLIO_EXPOSURE_LIMIT",
                "equity_usd": exposure_data["equity_usd"],
                "limit_usd": exposure_data["limit_usd"],
                "positions_usd": exposure_data["positions_usd"],
                "pending_usd": exposure_data["pending_usd"],
                "new_usd": exposure_data["new_usd"],
                "exposure_will_be_usd": exposure_data["exposure_will_be_usd"],
            },
        )

    def get_metrics(self) -> Dict[str, int]:
        """Return metrics for observability."""
        return self._metrics.copy()

    def reset(self) -> None:
        """Reset FSM state (for testing)."""
        self.state = OpenState.IDLE
        self.last_open_ts = 0.0
