"""
Exchange Filters Contracts.

TASK51-A: Type-safe contracts for exchange filters validation.
Ensures step_size, min_qty, min_notional are properly validated.
"""

from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class ExchangeFilters:
    """
    Filters retrieved from exchange API (Binance exchangeInfo).
    
    All values are normalized to Decimal for precise comparison.
    """
    symbol: str
    step_size: Decimal  # LOT_SIZE.stepSize
    min_qty: Decimal    # LOT_SIZE.minQty
    min_notional: Decimal  # MIN_NOTIONAL.notional
    tick_size: Optional[Decimal] = None  # PRICE_FILTER.tickSize

    def __post_init__(self):
        if self.step_size <= 0:
            raise ValueError(f"step_size must be positive: {self.step_size}")
        if self.min_qty <= 0:
            raise ValueError(f"min_qty must be positive: {self.min_qty}")
        if self.min_notional < 0:
            raise ValueError(f"min_notional cannot be negative: {self.min_notional}")


@dataclass(frozen=True)
class SSOTFilters:
    """
    Filters from SSOT (instruments.yaml).
    
    These MUST match exchange reality for correct qty normalization.
    """
    symbol: str
    step_size: Decimal
    min_qty: Decimal
    min_notional: Decimal
    tick_size: Optional[Decimal] = None

    @classmethod
    def from_yaml_dict(cls, symbol: str, data: dict) -> SSOTFilters:
        """
        Parse SSOT filters from YAML dict.
        
        Args:
            symbol: Trading symbol
            data: Dict with step_size, min_qty, min_notional keys
            
        Returns:
            SSOTFilters instance
        """
        return cls(
            symbol=symbol,
            step_size=Decimal(str(data.get("step_size", "0.001"))),
            min_qty=Decimal(str(data.get("min_qty", "0.001"))),
            min_notional=Decimal(str(data.get("min_notional", "5"))),
            tick_size=Decimal(str(data["tick_size"])) if data.get("tick_size") else None,
        )


@dataclass
class FilterMismatch:
    """
    Represents a mismatch between SSOT and exchange filters.
    """
    symbol: str
    field: str
    ssot_value: Decimal
    exchange_value: Decimal
    
    @property
    def severity(self) -> str:
        """
        Calculate mismatch severity.
        
        Critical if SSOT is MORE permissive than exchange (would cause rejects).
        Warning if SSOT is stricter (overly conservative but safe).
        """
        if self.field == "step_size":
            # SSOT step_size < exchange = CRITICAL (qty may be rejected)
            if self.ssot_value < self.exchange_value:
                return "CRITICAL"
            return "WARNING"
        elif self.field == "min_qty":
            # SSOT min_qty < exchange = CRITICAL
            if self.ssot_value < self.exchange_value:
                return "CRITICAL"
            return "WARNING"
        elif self.field == "min_notional":
            # SSOT min_notional < exchange = CRITICAL
            if self.ssot_value < self.exchange_value:
                return "CRITICAL"
            return "WARNING"
        return "INFO"
    
    def __str__(self) -> str:
        return (
            f"[{self.severity}] {self.symbol}.{self.field}: "
            f"SSOT={self.ssot_value} vs Exchange={self.exchange_value}"
        )
