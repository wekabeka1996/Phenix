"""Small Pydantic payload models shared by DecisionMaking helpers.

These models are intentionally narrow compatibility surfaces. They normalize the
legacy portfolio-position payload shape used by tests and a small set of helper
paths, but they do not own broader portfolio or strategy-resolution logic.
"""

from decimal import Decimal
from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator


class PositionData(BaseModel):
    """Position snapshot in the currently supported DecisionMaking shape.

    The field names intentionally preserve the existing payload contract
    (``positionAmt``, ``entryPrice``, ``unRealizedProfit``) instead of exposing a
    snake_case Python-only facade. Strategy ownership is resolved elsewhere and
    is not part of this schema.
    """

    symbol: str
    positionAmt: Decimal
    entryPrice: Decimal
    unRealizedProfit: Decimal
    leverage: Decimal = Field(default=Decimal("1"))

    @field_validator('positionAmt', 'entryPrice', 'unRealizedProfit', 'leverage', mode='before')
    def parse_decimal(cls, v: Any) -> Any:
        """Accept stringy numeric inputs while rejecting non-decimal values."""
        try:
            if isinstance(v, (str, int, float)):
                return Decimal(str(v))
            return v
        except Exception:
            raise ValueError(f"Invalid decimal value: {v}")


class PortfolioStatePayload(BaseModel):
    """Compatibility payload for portfolio-state snapshots.

    Existing producers may still emit the legacy "positions-only" shape, so the
    aggregate equity fields remain optional and ``positions`` keeps a default
    empty list for permissive backward-compatible parsing.
    """

    schema_version: int = Field(default=1)
    ts_ms: Optional[int] = None
    equity_usdt: Optional[Decimal] = None
    available_usdt: Optional[Decimal] = None

    positions: List[PositionData] = Field(default_factory=list)

    @field_validator('equity_usdt', 'available_usdt', mode='before')
    def parse_optional_decimal(cls, v: Any) -> Any:
        """Normalize optional aggregate money fields into Decimal values."""
        if v is None:
            return None
        try:
            if isinstance(v, (str, int, float)):
                return Decimal(str(v))
            return v
        except Exception:
            raise ValueError(f"Invalid decimal value: {v}")
