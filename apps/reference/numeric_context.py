"""
Numeric Context for Financial Calculations

This module establishes the global decimal context for all financial calculations
in the Aurora Core FSM system. All financial operations must use Decimal instead
of float to ensure deterministic and precise calculations.

Source of Truth: shared/numeric/context.py, docs/ADR-T1-S3.2-decimal-math.md
"""

import decimal

# Set global decimal context for the entire application
# Precision: 28 decimal places (sufficient for most financial calculations)
# Rounding: ROUND_HALF_UP (banker's rounding)
decimal.setcontext(decimal.Context(prec=28, rounding=decimal.ROUND_HALF_UP))

# Export commonly used decimal constants
ZERO = decimal.Decimal("0")
ONE = decimal.Decimal("1")
TWO = decimal.Decimal("2")
TEN = decimal.Decimal("10")
HUNDRED = decimal.Decimal("100")


def decimal_from_str(value: str) -> decimal.Decimal:
    """Convert string to Decimal, ensuring no float conversion."""
    return decimal.Decimal(value)


def decimal_from_int(value: int) -> decimal.Decimal:
    """Convert int to Decimal."""
    return decimal.Decimal(value)


def decimal_from_float(value: float) -> decimal.Decimal:
    """Convert float to Decimal (use sparingly, prefer string conversion)."""
    return decimal.Decimal(str(value))
