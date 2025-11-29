from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

class PositionData(BaseModel):
    symbol: str
    positionAmt: Decimal
    entryPrice: Decimal
    unRealizedProfit: Decimal
    leverage: Decimal = Field(default=Decimal("1"))

    @field_validator('positionAmt', 'entryPrice', 'unRealizedProfit', 'leverage', mode='before')
    def parse_decimal(cls, v):
        try:
            if isinstance(v, (str, int, float)):
                return Decimal(str(v))
            return v
        except Exception:
            raise ValueError(f"Invalid decimal value: {v}")

class PortfolioStatePayload(BaseModel):
    positions: List[PositionData] = Field(default_factory=list)
