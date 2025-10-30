"""
Normalized Reject Reasons (NRR) module.

Provides standardized error codes and normalization logic for consistent
error handling across the trading system.
"""

import re
from typing import Dict, Optional


class NormalizedRejectReasons:
    """
    Maps raw error messages to standardized NRR codes for analytics and debugging.
    """

    # NRR Code definitions
    INSUFFICIENT_BALANCE = "NRR-001"
    INVALID_ORDER_PARAMS = "NRR-002"
    MARKET_CLOSED = "NRR-003"
    SYMBOL_NOT_TRADING = "NRR-004"
    PRICE_OUT_OF_RANGE = "NRR-005"
    QUANTITY_TOO_SMALL = "NRR-006"
    QUANTITY_TOO_LARGE = "NRR-007"
    ORDER_WOULD_TRIGGER_LIQ = "NRR-008"
    REDUCE_ONLY_VIOLATION = "NRR-009"
    POSITION_SIZE_EXCEEDED = "NRR-010"
    EXPOSURE_LIMIT_EXCEEDED = "NRR-011"
    RATE_LIMIT_EXCEEDED = "NRR-012"
    NETWORK_ERROR = "NRR-013"
    TIMEOUT_ERROR = "NRR-014"
    UNKNOWN_ERROR = "NRR-999"

    # Regex patterns for normalization
    PATTERNS = {
        INSUFFICIENT_BALANCE: [
            r"insufficient.*balance",
            r"account.*insufficient",
            r"not enough.*funds",
            r"balance.*not.*sufficient",
        ],
        INVALID_ORDER_PARAMS: [
            r"invalid.*order.*param",
            r"order.*param.*invalid",
            r"bad.*request.*order",
        ],
        MARKET_CLOSED: [r"market.*closed", r"trading.*suspended", r"market.*not.*open"],
        SYMBOL_NOT_TRADING: [
            r"symbol.*not.*trading",
            r"instrument.*not.*available",
            r"symbol.*suspended",
        ],
        PRICE_OUT_OF_RANGE: [
            r"price.*out.*range",
            r"price.*too.*high",
            r"price.*too.*low",
            r"invalid.*price",
        ],
        QUANTITY_TOO_SMALL: [
            r"quantity.*too.*small",
            r"lot.*size.*minimum",
            r"min.*quantity",
        ],
        QUANTITY_TOO_LARGE: [
            r"quantity.*too.*large",
            r"max.*quantity",
            r"lot.*size.*maximum",
        ],
        ORDER_WOULD_TRIGGER_LIQ: [
            r"would.*trigger.*liquidation",
            r"liquidation.*risk",
            r"margin.*insufficient",
        ],
        REDUCE_ONLY_VIOLATION: [r"reduce.*only", r"position.*cannot.*increase"],
        POSITION_SIZE_EXCEEDED: [
            r"position.*size.*exceeded",
            r"max.*position",
            r"position.*limit",
        ],
        EXPOSURE_LIMIT_EXCEEDED: [
            r"exposure.*limit",
            r"risk.*limit.*exceeded",
            r"exposure.*exceeded",
        ],
        RATE_LIMIT_EXCEEDED: [
            r"rate.*limit",
            r"too.*many.*requests",
            r"request.*rate.*exceeded",
        ],
        NETWORK_ERROR: [r"network.*error", r"connection.*failed", r"timeout.*network"],
        TIMEOUT_ERROR: [r"timeout", r"request.*timed.*out", r"operation.*timeout"],
    }

    @classmethod
    def normalize(cls, raw_reason: str) -> str:
        """
        Normalize a raw reject reason to a standardized NRR code.

        Args:
            raw_reason: The raw error message from API or system

        Returns:
            Standardized NRR code
        """
        if not raw_reason:
            return cls.UNKNOWN_ERROR

        raw_lower = raw_reason.lower().strip()

        for nrr_code, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, raw_lower, re.IGNORECASE):
                    return nrr_code

        return cls.UNKNOWN_ERROR

    @classmethod
    def get_description(cls, nrr_code: str) -> Optional[str]:
        """
        Get human-readable description for an NRR code.

        Args:
            nrr_code: The NRR code

        Returns:
            Description string or None if code not found
        """
        descriptions = {
            cls.INSUFFICIENT_BALANCE: "Account has insufficient balance for the operation",
            cls.INVALID_ORDER_PARAMS: "Order parameters are invalid or malformed",
            cls.MARKET_CLOSED: "Market is currently closed or trading suspended",
            cls.SYMBOL_NOT_TRADING: "Symbol is not currently available for trading",
            cls.PRICE_OUT_OF_RANGE: "Order price is outside acceptable range",
            cls.QUANTITY_TOO_SMALL: "Order quantity is below minimum allowed",
            cls.QUANTITY_TOO_LARGE: "Order quantity exceeds maximum allowed",
            cls.ORDER_WOULD_TRIGGER_LIQ: "Order would trigger account liquidation",
            cls.REDUCE_ONLY_VIOLATION: "Order violates reduce-only position rules",
            cls.POSITION_SIZE_EXCEEDED: "Position size would exceed limits",
            cls.EXPOSURE_LIMIT_EXCEEDED: "Operation would exceed exposure limits",
            cls.RATE_LIMIT_EXCEEDED: "Request rate limit has been exceeded",
            cls.NETWORK_ERROR: "Network connectivity or communication error",
            cls.TIMEOUT_ERROR: "Operation timed out",
            cls.UNKNOWN_ERROR: "Unknown or unmapped error condition",
        }

        return descriptions.get(nrr_code)
