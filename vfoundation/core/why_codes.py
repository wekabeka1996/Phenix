"""
WHY Codes - Standardized Rejection and Event Reason Codes

This module defines standardized WHY codes used throughout the Aurora trading system
to provide consistent, machine-readable reasons for decisions, rejections, and events.

WHY codes follow the pattern: CATEGORY_SHORT_DESCRIPTION
Categories:
- SPREAD: Market spread related issues
- RISK: Risk management rejections
- LIQ: Liquidity and sizing issues
- MARGIN: Margin and leverage issues
- REGIME: Market regime filtering
- GUARD: System guards and limits
- FSM: FSM state and transition issues
- EXCHANGE: Exchange API rejections
- IDEMPOTENCY: Duplicate operation prevention
- TIMEOUT: Time-based expirations
- CONFIG: Configuration issues
- VALIDATION: Input validation failures
"""

from enum import Enum
from typing import Dict, Any


class WhyCode(Enum):
    """Standardized WHY codes for Aurora trading system."""

    # Market Spread Issues
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    SPREAD_NEGATIVE = "SPREAD_NEGATIVE"
    SPREAD_ZERO = "SPREAD_ZERO"

    # Risk Management Rejections
    RISK_SCORE_HIGH = "RISK_SCORE_HIGH"
    RISK_NOT_ALLOWED = "RISK_NOT_ALLOWED"
    RISK_KELLY_ZERO = "RISK_KELLY_ZERO"
    RISK_CVAR_EXCEEDED = "RISK_CVAR_EXCEEDED"
    RISK_DRAWDOWN_LIMIT = "RISK_DRAWDOWN_LIMIT"

    # Liquidity and Sizing Issues
    LIQ_POSITION_TOO_SMALL = "LIQ_POSITION_TOO_SMALL"
    LIQ_POSITION_TOO_LARGE = "LIQ_POSITION_TOO_LARGE"
    LIQ_INSUFFICIENT_DEPTH = "LIQ_INSUFFICIENT_DEPTH"
    LIQ_PRICE_IMPACT_HIGH = "LIQ_PRICE_IMPACT_HIGH"

    # Margin and Leverage Issues
    MARGIN_INSUFFICIENT = "MARGIN_INSUFFICIENT"
    MARGIN_LEVERAGE_TOO_HIGH = "MARGIN_LEVERAGE_TOO_HIGH"
    MARGIN_MAINTENANCE_LOW = "MARGIN_MAINTENANCE_LOW"

    # Market Regime Filtering
    REGIME_TREND_UP_BLOCK_SELL = "REGIME_TREND_UP_BLOCK_SELL"
    REGIME_TREND_DOWN_BLOCK_BUY = "REGIME_TREND_DOWN_BLOCK_BUY"
    REGIME_UNCERTAIN_SIZE_REDUCED = "REGIME_UNCERTAIN_SIZE_REDUCED"
    REGIME_HIGH_VOL_SIZE_REDUCED = "REGIME_HIGH_VOL_SIZE_REDUCED"
    REGIME_LOW_VOL_SIZE_INCREASED = "REGIME_LOW_VOL_SIZE_INCREASED"
    REGIME_MEAN_REVERSION_SIZE_REDUCED = "REGIME_MEAN_REVERSION_SIZE_REDUCED"

    # System Guards and Limits
    GUARD_LIQ_DIST_TOO_CLOSE = "GUARD_LIQ_DIST_TOO_CLOSE"
    GUARD_POSITION_LIMIT_EXCEEDED = "GUARD_POSITION_LIMIT_EXCEEDED"
    GUARD_RATE_LIMIT_EXCEEDED = "GUARD_RATE_LIMIT_EXCEEDED"
    GUARD_CIRCUIT_BREAKER_OPEN = "GUARD_CIRCUIT_BREAKER_OPEN"

    # FSM State and Transition Issues
    FSM_STATE_INVALID = "FSM_STATE_INVALID"
    FSM_TRANSITION_NOT_ALLOWED = "FSM_TRANSITION_NOT_ALLOWED"
    FSM_TIMEOUT_EXPIRED = "FSM_TIMEOUT_EXPIRED"
    FSM_DUPLICATE_OPERATION = "FSM_DUPLICATE_OPERATION"

    # Exchange API Rejections
    EXCHANGE_ORDER_REJECTED = "EXCHANGE_ORDER_REJECTED"
    EXCHANGE_INSUFFICIENT_BALANCE = "EXCHANGE_INSUFFICIENT_BALANCE"
    EXCHANGE_INVALID_PRICE = "EXCHANGE_INVALID_PRICE"
    EXCHANGE_INVALID_QUANTITY = "EXCHANGE_INVALID_QUANTITY"
    EXCHANGE_MARKET_CLOSED = "EXCHANGE_MARKET_CLOSED"
    EXCHANGE_RATE_LIMIT = "EXCHANGE_RATE_LIMIT"

    # Idempotency Issues
    IDEMPOTENCY_DUPLICATE_KEY = "IDEMPOTENCY_DUPLICATE_KEY"
    IDEMPOTENCY_KEY_EXPIRED = "IDEMPOTENCY_KEY_EXPIRED"
    IDEMPOTENCY_KEY_INVALID = "IDEMPOTENCY_KEY_INVALID"

    # Time-based Issues
    TIMEOUT_ORDER_EXPIRED = "TIMEOUT_ORDER_EXPIRED"
    TIMEOUT_REQUEST_EXPIRED = "TIMEOUT_REQUEST_EXPIRED"
    TIMEOUT_CONNECTION_LOST = "TIMEOUT_CONNECTION_LOST"

    # Configuration Issues
    CONFIG_MISSING_KEY = "CONFIG_MISSING_KEY"
    CONFIG_INVALID_VALUE = "CONFIG_INVALID_VALUE"
    CONFIG_SCHEMA_VIOLATION = "CONFIG_SCHEMA_VIOLATION"

    # Input Validation Failures
    VALIDATION_MISSING_FIELD = "VALIDATION_MISSING_FIELD"
    VALIDATION_INVALID_TYPE = "VALIDATION_INVALID_TYPE"
    VALIDATION_INVALID_FORMAT = "VALIDATION_INVALID_FORMAT"
    VALIDATION_OUT_OF_RANGE = "VALIDATION_OUT_OF_RANGE"

    # Drift Monitor Issues
    DRIFT_DEC_CLOSE_FALSE_POSITIVE = "DRIFT_DEC_CLOSE_FALSE_POSITIVE"
    DRIFT_DEC_CLOSE_MISSING_FILL = "DRIFT_DEC_CLOSE_MISSING_FILL"
    DRIFT_DEC_CLOSE_REDUCE_ONLY_MISMATCH = "DRIFT_DEC_CLOSE_REDUCE_ONLY_MISMATCH"

    # Success/Info Codes
    SUCCESS_ORDER_PLACED = "SUCCESS_ORDER_PLACED"
    SUCCESS_POSITION_OPENED = "SUCCESS_POSITION_OPENED"
    SUCCESS_POSITION_CLOSED = "SUCCESS_POSITION_CLOSED"
    INFO_REGIME_DETECTED = "INFO_REGIME_DETECTED"
    INFO_RISK_RECALCULATED = "INFO_RISK_RECALCULATED"

    # NRR Codes (Normalized Reject Reasons)
    NRR_011_EXPOSURE_LIMIT_EXCEEDED = "NRR-011"
    NRR_012_RATE_LIMIT_EXCEEDED = "NRR-012"
    NRR_013_EXPOSURE_BLOCK_COOLDOWN_ACTIVE = "NRR-013"
    NRR_014_SYMBOL_COOLDOWN_ACTIVE = "NRR-014"
    NRR_015_EXCHANGE_ORDER_REJECTED = "NRR-015"
    NRR_016_ORDER_TIMEOUT_EXPIRED = "NRR-016"
    NRR_017_SYMBOL_COOLDOWN_ACTIVE = "NRR-017"
    NRR_018_EXCHANGE_REJECTED_ORDER = "NRR-018"
    NRR_019_ORDER_TIMEOUT_EXPIRED = "NRR-019"


def get_why_description(code: WhyCode) -> str:
    """Get human-readable description for a WHY code."""
    descriptions = {
        # Market Spread Issues
        WhyCode.SPREAD_TOO_WIDE: "Market spread exceeds maximum allowed threshold",
        WhyCode.SPREAD_NEGATIVE: "Market spread is negative (invalid data)",
        WhyCode.SPREAD_ZERO: "Market spread is zero (no liquidity)",
        # Risk Management Rejections
        WhyCode.RISK_SCORE_HIGH: "Risk score exceeds acceptable threshold",
        WhyCode.RISK_NOT_ALLOWED: "Risk management policy prohibits trading",
        WhyCode.RISK_KELLY_ZERO: "Kelly fraction calculation resulted in zero",
        WhyCode.RISK_CVAR_EXCEEDED: "Conditional Value at Risk exceeds limit",
        WhyCode.RISK_DRAWDOWN_LIMIT: "Portfolio drawdown exceeds maximum limit",
        # Liquidity and Sizing Issues
        WhyCode.LIQ_POSITION_TOO_SMALL: "Calculated position size below minimum threshold",
        WhyCode.LIQ_POSITION_TOO_LARGE: "Calculated position size exceeds maximum limit",
        WhyCode.LIQ_INSUFFICIENT_DEPTH: "Order book depth insufficient for position size",
        WhyCode.LIQ_PRICE_IMPACT_HIGH: "Estimated price impact exceeds tolerance",
        # Margin and Leverage Issues
        WhyCode.MARGIN_INSUFFICIENT: "Available margin insufficient for position",
        WhyCode.MARGIN_LEVERAGE_TOO_HIGH: "Leverage exceeds safe liquidation distance",
        WhyCode.MARGIN_MAINTENANCE_LOW: "Maintenance margin below required level",
        # Market Regime Filtering
        WhyCode.REGIME_TREND_UP_BLOCK_SELL: "Counter-trend sell blocked in TREND_UP regime",
        WhyCode.REGIME_TREND_DOWN_BLOCK_BUY: "Counter-trend buy blocked in TREND_DOWN regime",
        WhyCode.REGIME_UNCERTAIN_SIZE_REDUCED: "Position size reduced in UNCERTAIN regime",
        WhyCode.REGIME_HIGH_VOL_SIZE_REDUCED: "Position size reduced in HIGH_VOLATILITY regime",
        WhyCode.REGIME_LOW_VOL_SIZE_INCREASED: "Position size increased in LOW_VOLATILITY regime",
        WhyCode.REGIME_MEAN_REVERSION_SIZE_REDUCED: "Position size reduced in MEAN_REVERSION regime",
        # System Guards and Limits
        WhyCode.GUARD_LIQ_DIST_TOO_CLOSE: "Liquidation distance too close to entry price",
        WhyCode.GUARD_POSITION_LIMIT_EXCEEDED: "Position limit per symbol exceeded",
        WhyCode.GUARD_RATE_LIMIT_EXCEEDED: "API rate limit exceeded",
        WhyCode.GUARD_CIRCUIT_BREAKER_OPEN: "Circuit breaker is open due to system issues",
        # FSM State and Transition Issues
        WhyCode.FSM_STATE_INVALID: "FSM is in invalid state for this operation",
        WhyCode.FSM_TRANSITION_NOT_ALLOWED: "FSM transition not allowed from current state",
        WhyCode.FSM_TIMEOUT_EXPIRED: "FSM operation timed out",
        WhyCode.FSM_DUPLICATE_OPERATION: "Duplicate operation detected by FSM",
        # Exchange API Rejections
        WhyCode.EXCHANGE_ORDER_REJECTED: "Order rejected by exchange",
        WhyCode.EXCHANGE_INSUFFICIENT_BALANCE: "Exchange reports insufficient balance",
        WhyCode.EXCHANGE_INVALID_PRICE: "Order price rejected by exchange",
        WhyCode.EXCHANGE_INVALID_QUANTITY: "Order quantity rejected by exchange",
        WhyCode.EXCHANGE_MARKET_CLOSED: "Market is closed for trading",
        WhyCode.EXCHANGE_RATE_LIMIT: "Exchange rate limit exceeded",
        # Idempotency Issues
        WhyCode.IDEMPOTENCY_DUPLICATE_KEY: "Duplicate operation detected via idempotency key",
        WhyCode.IDEMPOTENCY_KEY_EXPIRED: "Idempotency key has expired",
        WhyCode.IDEMPOTENCY_KEY_INVALID: "Idempotency key format is invalid",
        # Time-based Issues
        WhyCode.TIMEOUT_ORDER_EXPIRED: "Order expired before execution",
        WhyCode.TIMEOUT_REQUEST_EXPIRED: "Request timed out",
        WhyCode.TIMEOUT_CONNECTION_LOST: "Connection lost during operation",
        # Configuration Issues
        WhyCode.CONFIG_MISSING_KEY: "Required configuration key is missing",
        WhyCode.CONFIG_INVALID_VALUE: "Configuration value is invalid",
        WhyCode.CONFIG_SCHEMA_VIOLATION: "Configuration violates schema requirements",
        # Input Validation Failures
        WhyCode.VALIDATION_MISSING_FIELD: "Required field is missing from input",
        WhyCode.VALIDATION_INVALID_TYPE: "Field has invalid data type",
        WhyCode.VALIDATION_INVALID_FORMAT: "Field format is invalid",
        WhyCode.VALIDATION_OUT_OF_RANGE: "Field value is out of acceptable range",
        # Drift Monitor Issues
        WhyCode.DRIFT_DEC_CLOSE_FALSE_POSITIVE: "DEC:CLOSE matched non-position-closing FILL",
        WhyCode.DRIFT_DEC_CLOSE_MISSING_FILL: "Expected FILL event for DEC:CLOSE not found",
        WhyCode.DRIFT_DEC_CLOSE_REDUCE_ONLY_MISMATCH: "FILL reduceOnly flag doesn't match DEC:CLOSE",
        # Success/Info Codes
        WhyCode.SUCCESS_ORDER_PLACED: "Order successfully placed on exchange",
        WhyCode.SUCCESS_POSITION_OPENED: "Position successfully opened",
        WhyCode.SUCCESS_POSITION_CLOSED: "Position successfully closed",
        WhyCode.INFO_REGIME_DETECTED: "Market regime detected and classified",
        WhyCode.INFO_RISK_RECALCULATED: "Risk parameters recalculated",
        # NRR Codes
        WhyCode.NRR_011_EXPOSURE_LIMIT_EXCEEDED: "Exposure limit exceeded",
        WhyCode.NRR_012_RATE_LIMIT_EXCEEDED: "Rate limit exceeded",
        WhyCode.NRR_013_EXPOSURE_BLOCK_COOLDOWN_ACTIVE: "Exposure block cooldown active",
        WhyCode.NRR_014_SYMBOL_COOLDOWN_ACTIVE: "Symbol cooldown active",
        WhyCode.NRR_015_EXCHANGE_ORDER_REJECTED: "Exchange rejected order",
        WhyCode.NRR_016_ORDER_TIMEOUT_EXPIRED: "Order timeout expired",
        WhyCode.NRR_017_SYMBOL_COOLDOWN_ACTIVE: "Symbol cooldown active",
        WhyCode.NRR_018_EXCHANGE_REJECTED_ORDER: "Exchange rejected order",
        WhyCode.NRR_019_ORDER_TIMEOUT_EXPIRED: "Order timeout expired",
    }

    return descriptions.get(code, f"Unknown WHY code: {code.value}")


def format_why_with_details(code: WhyCode, details: str = None) -> str:
    """Format WHY code with optional details for logging."""
    base = f"{code.value}"
    if details:
        return f"{base}: {details}"
    return base


def create_why_payload(code: WhyCode, details: Dict[str, Any] = None) -> Dict[str, Any]:
    """Create standardized WHY payload for events."""
    payload = {
        "why_code": code.value,
        "why_description": get_why_description(code),
    }

    if details:
        payload["why_details"] = details

    return payload
