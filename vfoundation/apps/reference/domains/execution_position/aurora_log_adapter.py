#!/usr/bin/env python3
"""
Aurora Log Adapter

Structured logging adapter for Aurora trading system.
Provides enhanced trade logging with all necessary fields for debugging and analysis.
"""

import logging
import time
from typing import Dict, Any, Optional
from pathlib import Path


class AuroraLogAdapter:
    """
    Aurora Log Adapter for structured trade logging.

    Provides enhanced logging for trade intents, decisions, and executions
    with all necessary fields for debugging and analysis.
    """

    def __init__(self, log_file: str = "logs/aurora_trades.log", level: str = "INFO"):
        """
        Initialize Aurora Log Adapter.

        Args:
            log_file: Path to trade log file
            level: Logging level (DEBUG, INFO, WARNING, ERROR)
        """
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Create dedicated logger for trades
        self.logger = logging.getLogger("aurora.trades")
        self.logger.setLevel(getattr(logging, level.upper()))

        # Avoid duplicate handlers
        if not self.logger.handlers:
            # File handler with trade-specific format
            file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
            formatter = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

            # Prevent propagation to root logger
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
        """
        Log trade intent with full context.

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
            "timestamp": time.time(),
        }

        # Add optional fields if provided
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

        # Format as readable string
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
        """
        Log trade decision (accept/reject).

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
            "timestamp": time.time(),
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
        """
        Log trade execution status.

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
            "timestamp": time.time(),
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
        self, rid: str, symbol: str, side: str, guard_type: str, reason: str, **extra_fields
    ) -> None:
        """
        Log guard rejection with details.

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
            "timestamp": time.time(),
        }

        log_data.update(extra_fields)

        message = f"GUARD_REJECT: {guard_type} - {symbol} {side} ({reason})"
        self.logger.warning(message, extra=log_data)
