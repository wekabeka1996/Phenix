#!/usr/bin/env python3
"""Lightweight trade-event logger for execution_position flows.

The adapter writes human-readable trade lifecycle lines to a dedicated file
logger and attaches event metadata via ``extra`` for handlers that consume it.
It is not a generic logging framework and intentionally keeps formatting local.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

# T2B-04: Time abstraction for deterministic testing
from apps.reference.core.time import get_clock
from apps.reference.utils.accessors import aget


class AuroraLogAdapter:
    """Trade-log adapter backed by the shared ``aurora.trades`` logger."""

    def __init__(self, log_file: str = "logs/aurora_trades.log", level: str = "INFO"):
        """Initialize the trade logger and ensure its file handler exists.

        Args:
            log_file: Path to trade log file
            level: Logging level (DEBUG, INFO, WARNING, ERROR)
        """
        self.log_file = Path(log_file).resolve()
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # ExecPosFSM instances share one named logger, so handler deduplication
        # must be path-aware to avoid duplicate writes on repeated init.
        self.logger = logging.getLogger("aurora.trades")
        self.logger.setLevel(getattr(logging, level.upper()))

        already = any(
            isinstance(h, logging.FileHandler)
            and aget(h, "baseFilename", "")
            and Path(str(aget(h, "baseFilename", ""))).resolve() == self.log_file
            for h in self.logger.handlers
        )
        if not already:
            # The line format stays intentionally compact because most tests and
            # operator forensics read the file as plain text, not structured JSON.
            file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
            formatter = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

        # Keep trade logs out of the root logger to avoid duplicate console/file
        # emission when the application config wires parent handlers.
        self.logger.propagate = False

    def log_trade_intent(
        self,
        rid: str,
        symbol: str,
        side: str,
        probability: Optional[float] = None,
        size: Optional[float] = None,
        price: Optional[float] = None,
        qty: Optional[float] = None,
        risk_score: Optional[float] = None,
        features: Optional[Dict[str, Any]] = None,
        **extra_fields,
    ) -> None:
        """Log a proposed trade intent with optional sizing/risk context.

        Args:
            rid: Request ID
            symbol: Trading symbol (e.g., 'ETHUSDT')
            side: Trade side ('buy' or 'sell')
            probability: Win probability (0.0-1.0)
            size: Position size in USD
            price: Target price
            qty: Quantity to trade
            risk_score: Risk assessment score
            features: Trading features used in decision
            **extra_fields: Additional fields to log
        """
        log_data = {
            "event": "TRADE_INTENT_PROPOSED",
            "rid": rid,
            "symbol": symbol,
            "side": side,
            "timestamp": get_clock().now_sec(),
        }

        # Keep ``extra`` sparse so unrelated handlers do not receive a large
        # payload when optional trading context is absent.
        if probability is not None:
            log_data["probability"] = probability
        if size is not None:
            log_data["size_usd"] = size
        if price is not None:
            log_data["price"] = price
        if qty is not None:
            log_data["quantity"] = qty
        if risk_score is not None:
            log_data["risk_score"] = risk_score
        if features is not None:
            log_data["features"] = features

        # Add any extra fields
        log_data.update(extra_fields)

        # The message is optimized for grep-friendly plain-text incident review.
        message = f"EVENT_TRADE_INTENT_PROPOSED - {symbol} {side}"
        if probability is not None:
            message += f" (prob={float(probability):.3f})"
        if size is not None:
            message += f" (size=${float(size):.2f})"
        if price is not None:
            message += f" (price={float(price):.4f})"
        if qty is not None:
            message += f" (qty={float(qty):.6f})"
        if risk_score is not None:
            message += f" (risk={float(risk_score):.3f})"

        self.logger.info(message, extra=log_data)

    def log_trade_decision(
        self,
        rid: str,
        symbol: str,
        side: str,
        decision: str,
        reason: Optional[str] = None,
        **extra_fields,
    ) -> None:
        """Log an accept/reject decision for a proposed trade.

        Args:
            rid: Request ID
            symbol: Trading symbol
            side: Trade side
            decision: Decision ('ACCEPTED' or 'REJECTED')
            reason: Reason for rejection (if applicable)
            **extra_fields: Additional fields to log
        """
        log_data = {
            "event": "TRADE_DECISION",
            "rid": rid,
            "symbol": symbol,
            "side": side,
            "decision": decision,
            "timestamp": get_clock().now_sec(),
        }

        if reason:
            log_data["reason"] = reason

        log_data.update(extra_fields)

        level = logging.INFO if decision == "ACCEPTED" else logging.WARNING
        message = f"EVENT_TRADE_DECISION - {symbol} {side} {decision}"
        if reason:
            message += f" ({reason})"

        self.logger.log(level, message, extra=log_data)

    def log_trade_execution(
        self,
        rid: str,
        symbol: str,
        side: str,
        order_id: Optional[str] = None,
        status: str = "PLACED",
        executed_qty: Optional[float] = None,
        executed_price: Optional[float] = None,
        **extra_fields,
    ) -> None:
        """Log an execution-state update for an order/trade.

        Args:
            rid: Request ID
            symbol: Trading symbol
            side: Trade side
            order_id: Exchange order ID
            status: Execution status ('PLACED', 'FILLED', 'CANCELLED', 'REJECTED')
            executed_qty: Actually executed quantity
            executed_price: Actually executed price
            **extra_fields: Additional fields to log
        """
        log_data = {
            "event": "TRADE_EXECUTION",
            "rid": rid,
            "symbol": symbol,
            "side": side,
            "status": status,
            "timestamp": get_clock().now_sec(),
        }

        if order_id:
            log_data["order_id"] = order_id
        if executed_qty is not None:
            log_data["executed_qty"] = executed_qty
        if executed_price is not None:
            log_data["executed_price"] = executed_price

        log_data.update(extra_fields)

        message = f"EVENT_TRADE_EXECUTION - {symbol} {side} {status}"
        if order_id:
            message += f" (order_id={order_id})"
        if executed_qty is not None:
            message += f" (qty={float(executed_qty):.6f})"
        if executed_price is not None:
            message += f" (price={float(executed_price):.4f})"

        self.logger.info(message, extra=log_data)

    def log_guard_rejection(
        self,
        rid: str,
        symbol: str,
        side: str,
        guard_type: str,
        reason: str,
        **extra_fields,
    ) -> None:
        """Log a guard-layer rejection with its guard type and reason.

        Args:
            rid: Request ID
            symbol: Trading symbol
            side: Trade side
            guard_type: Type of guard that rejected ('COOLDOWN', 'NOTIONAL', etc.)
            reason: Detailed rejection reason
            **extra_fields: Additional fields to log
        """
        log_data = {
            "event": "GUARD_REJECTION",
            "rid": rid,
            "symbol": symbol,
            "side": side,
            "guard_type": guard_type,
            "reason": reason,
            "timestamp": get_clock().now_sec(),
        }

        log_data.update(extra_fields)

        message = f"GUARD_REJECT: {guard_type} - {symbol} {side} ({reason})"
        self.logger.warning(message, extra=log_data)
