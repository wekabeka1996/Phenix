"""
FSMP-P1-T02: Open Flow FSM for execution_position domain.

Minimal state machine: IDLE → PROCESSING → DONE|ERROR.
Guards: min_notional, qty/price steps, cooldown.
Output: DEC:OPEN(symbol, side, qty, price?, tif?).

Shadow-mode: no live API calls, all I/O via ACL stub.
"""

from __future__ import annotations

import time
import logging
import uuid
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Dict, Optional

from vfoundation.core.protocol import Message
from .contracts import (
    MIN_ORDER_QTY,
    MIN_NOTIONAL,
    QTY_STEP,
    PRICE_STEP,
)
from .metrics_collector import MetricsCollector


class OpenState(str, Enum):
    """FSM states for open flow."""

    IDLE = "IDLE"
    PROCESSING = "PROCESSING"
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
        metrics_collector: Optional[MetricsCollector] = None,
    ):
        self.state = OpenState.IDLE
        self.cooldown_sec = cooldown_sec
        self.guard_enabled = guard_enabled
        self.config = config or {}
        self.last_open_ts: float = 0.0
        self.logger = logging.getLogger(__name__)
        self.metrics_collector = metrics_collector
        self._metrics: Dict[str, int] = {
            "fsm_open_decisions_total": 0,
            "fsm_guard_rejects_total": 0,
            "fsm_errors_total": 0,
        }
        self.idempotency_store: Dict[str, float] = {}
        try:
            if hasattr(self.config, 'idempotency_window_sec'):
                self.idempotency_window_sec = self.config.idempotency_window_sec
            elif isinstance(self.config, dict):
                self.idempotency_window_sec = self.config.get(
                    "idempotency_window_sec", 60)
            else:
                self.idempotency_window_sec = 60
        except (AttributeError, TypeError):
            self.idempotency_window_sec = 60

    def _get_instrument_specs(self, symbol: str) -> Dict[str, Decimal]:
        """Get instrument specifications from config."""
        try:
            if hasattr(self.config, 'trading') and self.config.trading:
                instruments = self.config.trading.instruments if hasattr(
                    self.config.trading, 'instruments') else {}
            elif isinstance(self.config, dict):
                instruments = self.config.get(
                    "trading", {}).get("instruments", {})
            else:
                instruments = {}
        except (AttributeError, TypeError):
            instruments = {}

        specs = instruments.get(symbol, {}) if isinstance(
            instruments, dict) else {}

        # Convert values to Decimal with proper error handling
        def to_decimal(value, default):
            if isinstance(value, Decimal):
                return value
            try:
                return Decimal(str(value))
            except (ValueError, TypeError, InvalidOperation):
                return default

        return {
            "min_qty": to_decimal(specs.get("min_qty") if isinstance(specs, dict) else specs, MIN_ORDER_QTY),
            "step_size": to_decimal(specs.get("step_size") if isinstance(specs, dict) else specs, QTY_STEP),
            "tick_size": to_decimal(specs.get("tick_size") if isinstance(specs, dict) else specs, PRICE_STEP),
            "min_notional": to_decimal(specs.get("min_notional") if isinstance(specs, dict) else specs, MIN_NOTIONAL),
        }

    def _cleanup_idempotency_store(self):
        """Remove expired keys from the idempotency store."""
        now = time.time()
        expired_keys = [
            key
            for key, timestamp in self.idempotency_store.items()
            if now - timestamp > self.idempotency_window_sec
        ]
        for key in expired_keys:
            del self.idempotency_store[key]
        if expired_keys:
            self.logger.info(
                f"IDEMPOTENCY: Cleaned up {len(expired_keys)} expired keys."
            )

    def handle(self, msg: Message) -> Optional[Message]:
        """
        Process incoming message and return DEC:OPEN if guards pass.

        Args:
            msg: CMD:OPEN with pld: symbol, side, qty, price?, order_type?, tif?

        Returns:
            DEC:OPEN if guards pass, ERR if guards fail, None if not applicable.
        """
        if msg.op == "CMD" and msg.verb == "OPEN":
            # Record CMD:OPEN
            if self.metrics_collector:
                self.metrics_collector.record_cmd_open()
            timestamp_cmd = time.time()

            self.state = OpenState.PROCESSING

            # 0. Idempotency Check
            self._cleanup_idempotency_store()
            idempotent_key = msg.pld.get("idempotent_key")
            if idempotent_key:
                if idempotent_key in self.idempotency_store:
                    self.logger.warning(
                        f"IDEMPOTENCY_REJECT: Duplicate CMD:OPEN received with key {idempotent_key}, rid={msg.rid}"
                    )
                    return self._reject(msg, "IDEMPOTENCY_FAIL", "duplicate command")

                self.idempotency_store[idempotent_key] = time.time()

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
                    return self._reject(
                        msg, "OPEN_GUARD_FAIL", "missing symbol or side"
                    )

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
                    Decimal(str(pld.get("price_ref")))
                    if pld.get("price_ref") is not None
                    else None
                )

                # Guard: qty bounds
                if qty_dec is None or qty_dec < min_qty:
                    self.logger.error(
                        f"GUARD_REJECT: Quantity below minimum - qty={qty_dec}, min={min_qty}, rid={msg.rid}"
                    )
                    return self._reject(
                        msg, "OPEN_GUARD_FAIL", f"qty below minimum {min_qty}"
                    )

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
                        return self._reject(
                            msg, "OPEN_GUARD_FAIL", "LIMIT order requires price"
                        )

                    # Round price to tick_size
                    price_rounded = ((price_dec // tick_size) * tick_size).quantize(
                        tick_size
                    )
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
                            msg,
                            "OPEN_GUARD_FAIL",
                            f"notional {notional} < {min_notional}",
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
                    if self.metrics_collector:
                        self.metrics_collector.record_qos_cooldown_hit()
                    return self._reject(msg, "OPEN_GUARD_FAIL", "cooldown active")

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
                    corr_id=str(uuid.uuid4()),
                    oco_group_id=str(uuid.uuid4()),
                    data_ref=msg.data_ref.copy() if msg.data_ref else [],  # Preserve WHY chain
                )

                # Record metrics
                if self.metrics_collector:
                    ms = (time.time() - timestamp_cmd) * 1000
                    self.metrics_collector.record_time_to_open(ms)
                    self.metrics_collector.record_open_success()

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
        if reason == "cooldown active":
            self.state = OpenState.IDLE
        else:
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

    def get_metrics(self) -> Dict[str, int]:
        """Return metrics for observability."""
        return self._metrics.copy()

    def reset(self):
        """Reset FSM state (for testing)."""
        self.state = OpenState.IDLE
        self.last_open_ts = 0.0
