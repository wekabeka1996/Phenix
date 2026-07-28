from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .decimal_utils import _coerce_positive_decimal

if TYPE_CHECKING:
    from apps.reference.config_models import FlipOrchestrationConfig


class InstrumentSpec(BaseModel):
    """Specification for a trading instrument (e.g., BTCUSDT)."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(...)
    step_size: Decimal = Field(..., description="Quantity precision")
    tick_size: Decimal = Field(..., description="Price precision")
    min_qty: Decimal = Field(...)
    min_notional: Decimal = Field(..., description="Minimum notional value in USDT")
    quote: str = Field(...)

    @field_validator("step_size", "tick_size", "min_qty", "min_notional", mode="before")
    @classmethod
    def _parse_precision_decimals(cls, value: Any) -> Decimal:
        return _coerce_positive_decimal(value)


class LeverageConfig(BaseModel):
    """Leverage configuration for strategy per-asset settings."""

    model_config = ConfigDict(extra="forbid")

    target: int = Field(
        ..., ge=1,
        le=125,
        description="Target leverage (1-125). Binance Futures max is 125x.",
    )
    mode: Literal["ISOLATED", "CROSSED"] = Field(
        ..., description="Margin mode. ISOLATED recommended for position-level risk control.",
    )
    max_notional_value: Optional[Decimal] = Field(
        ..., description="Optional: Max notional value cap for this leverage. From leverageBracket API.",
    )


class InstrumentExecutionConfig(BaseModel):
    """Per-instrument execution settings for leverage and margin control."""

    model_config = ConfigDict(extra="forbid")

    margin_mode: Literal["isolated", "cross"] = Field(
        ..., description="Binance margin mode. ISOLATED = per-position margin, CROSS = shared wallet margin."
    )
    target_leverage: int = Field(
        ..., ge=1,
        le=125,
        description="Target leverage for this instrument (1-125). Must match or be set on exchange.",
    )
    leverage_policy: Literal["verify_only", "set_and_verify"] = Field(
        ..., description="verify_only = reject if mismatch. set_and_verify = set margin+leverage then verify."
    )
    max_notional_utilization: float = Field(
        ..., ge=0.0,
        le=1.0,
        description="Max notional as fraction of available capacity (0.0-1.0). Used for L1 capacity gate.",
    )


class InstrumentSizingConfig(BaseModel):
    """Per-instrument sizing SSOT (margin-first)."""

    model_config = ConfigDict(extra="forbid")

    margin_pct: float = Field(
        ..., gt=0.0,
        le=1.0,
        description="Fraction of wallet equity allocated as isolated margin for this symbol (0..1].",
    )
    fee_buffer_fraction: Decimal = Field(
        ...,
        ge=Decimal("0"),
        lt=Decimal("1"),
        description="Fraction of equity reserved before margin-first sizing.",
    )


class InstrumentPrecisionSpec(BaseModel):
    """Canonical Aurora instrument spec (SSOT from instruments.yaml)."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., description="Symbol name (e.g., BTCUSDT)")
    tick_size: Decimal = Field(..., description="Price precision")
    step_size: Decimal = Field(
        ..., description="Quantity precision (LOT_SIZE stepSize)")
    min_qty: Decimal = Field(..., description="Minimum quantity (LOT_SIZE minQty)")
    min_notional: Decimal = Field(
        ..., description="Minimum notional value (MIN_NOTIONAL)")
    execution: InstrumentExecutionConfig = Field(
        ..., description="Per-symbol execution SSOT (isolated/cross + target leverage policy)"
    )
    sizing: InstrumentSizingConfig = Field(
        ..., description="Per-symbol sizing SSOT (margin-first: margin_pct)"
    )
    flip: "FlipOrchestrationConfig" = Field(
        ...,
        description="Per-symbol flip config (enabled + hysteresis_mult). REQUIRED for all active symbols.",
    )

    @field_validator("step_size", "tick_size", "min_qty", "min_notional", mode="before")
    @classmethod
    def _parse_precision_decimals(cls, value: Any) -> Decimal:
        return _coerce_positive_decimal(value)


__all__ = [
    "InstrumentExecutionConfig",
    "InstrumentPrecisionSpec",
    "InstrumentSizingConfig",
    "InstrumentSpec",
    "LeverageConfig",
]
