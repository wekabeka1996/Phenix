"""
Normalized Reject Reasons (NRR) module.

Provides standardized error codes and normalization logic for consistent
error handling across the trading system.
"""

import re
from typing import Optional


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
    # Per-side limit exceeded (EXP-DIRECTION)
    SIDE_EXPOSURE_EXCEEDED = "NRR-012"
    # Directional imbalance limit exceeded (EXP-DIRECTION)
    DIRECTIONAL_RATIO_EXCEEDED = "NRR-013"
    RATE_LIMIT_EXCEEDED = "NRR-014"
    NETWORK_ERROR = "NRR-015"
    TIMEOUT_ERROR = "NRR-016"
    SYMBOL_COOLDOWN_ACTIVE = "NRR-017"
    EXCHANGE_REJECTED_ORDER = "NRR-018"
    ORDER_TIMEOUT_EXPIRED = "NRR-019"
    # TASK47c-B: Leverage/Margin verification codes
    LEVERAGE_MISMATCH = "NRR-020"
    MARGIN_MODE_MISMATCH = "NRR-021"
    LEVERAGE_SET_FAILED = "NRR-022"
    MARGIN_MODE_SET_FAILED = "NRR-023"
    LEVERAGE_VERIFY_FAILED = "NRR-024"
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
            r"trading.*not.*allowed.*risk.*manager",
            r"risk.*score.*too.*high",
        ],
        SIDE_EXPOSURE_EXCEEDED: [
            r"side.*exposure.*exceeded",
            r"long.*limit.*exceeded",
            r"short.*limit.*exceeded",
        ],
        DIRECTIONAL_RATIO_EXCEEDED: [
            r"directional.*ratio.*exceeded",
            r"ratio.*limit.*exceeded",
            r"imbalance.*limit",
        ],
        RATE_LIMIT_EXCEEDED: [
            r"rate.*limit",
            r"too.*many.*requests",
            r"request.*rate.*exceeded",
        ],
        NETWORK_ERROR: [r"network.*error", r"connection.*failed", r"timeout.*network"],
        TIMEOUT_ERROR: [r"timeout", r"request.*timed.*out", r"operation.*timeout"],
        SYMBOL_COOLDOWN_ACTIVE: [r"symbol.*cooldown.*active", r"cooldown.*remaining"],
        EXCHANGE_REJECTED_ORDER: [r"exchange.*reject", r"order.*reject.*exchange", r"-1013", r"-1021", r"-2010"],
        ORDER_TIMEOUT_EXPIRED: [r"order.*timeout.*expired", r"ack.*timeout", r"fill.*timeout"],
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
            cls.EXPOSURE_LIMIT_EXCEEDED: "Operation would exceed total exposure limits",
            cls.SIDE_EXPOSURE_EXCEEDED: "Operation would exceed per-side exposure limits",
            cls.DIRECTIONAL_RATIO_EXCEEDED: "Operation would exceed directional imbalance limits",
            cls.RATE_LIMIT_EXCEEDED: "Request rate limit has been exceeded",
            cls.NETWORK_ERROR: "Network connectivity or communication error",
            cls.TIMEOUT_ERROR: "Operation timed out",
            cls.SYMBOL_COOLDOWN_ACTIVE: "Symbol cooldown period is active",
            cls.EXCHANGE_REJECTED_ORDER: "Exchange rejected the order",
            cls.ORDER_TIMEOUT_EXPIRED: "Order timeout expired",
            # TASK47c-B: Leverage/Margin verification descriptions
            cls.LEVERAGE_MISMATCH: "Exchange leverage does not match expected value",
            cls.MARGIN_MODE_MISMATCH: "Exchange margin mode does not match expected value",
            cls.LEVERAGE_SET_FAILED: "Failed to set leverage on exchange",
            cls.MARGIN_MODE_SET_FAILED: "Failed to set margin mode on exchange",
            cls.LEVERAGE_VERIFY_FAILED: "Failed to verify leverage settings (API error)",
            cls.UNKNOWN_ERROR: "Unknown or unmapped error condition",
        }

        return descriptions.get(nrr_code)
