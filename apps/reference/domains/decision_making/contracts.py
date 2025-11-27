from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class PortfolioSnapshot(BaseModel):
    equity_total_usdt: Decimal = Field(alias="equity_total")
    equity_free_usdt: Decimal = Field(alias="equity_free")
    equity_locked_usdt: Optional[Decimal] = Field(
        default=None, alias="equity_locked")
    positions_value_usdt: Optional[Decimal] = Field(
        default=None, alias="positions_value")
    timestamp: datetime
    source: Optional[str] = None

    @field_validator("equity_total_usdt", "equity_free_usdt")
    @classmethod
    def _non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("equity values must be non-negative")
        return value

    class Config:
        # Pydantic V2 (was: allow_population_by_field_name)
        populate_by_name = True
        frozen = True
