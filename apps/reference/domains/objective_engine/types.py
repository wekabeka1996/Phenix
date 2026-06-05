from __future__ import annotations

from typing import Dict, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ObjectiveSignalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    symbol: str
    signal_score: float
    signal_direction: Literal[-1, 0, 1]
    regime: str
    regime_age_sec: float
    regime_confidence: float
    readiness_completeness: float

    @field_validator(
        "signal_score",
        "regime_age_sec",
        "regime_confidence",
        "readiness_completeness",
        mode="before",
    )
    @classmethod
    def _validate_finite_float(cls, value: object) -> float:
        if not isinstance(value, (int, float)):
            raise ValueError("objective signal fields must be finite numbers")
        value_f = float(value)
        if value_f != value_f or value_f in (float("inf"), float("-inf")):
            raise ValueError("objective signal fields must be finite numbers")
        return value_f

    @field_validator("strategy_id", "symbol", "regime")
    @classmethod
    def _validate_non_empty_str(cls, value: str) -> str:
        value_s = str(value).strip()
        if not value_s:
            raise ValueError("objective signal string fields must be non-empty")
        return value_s

    @field_validator("regime_age_sec")
    @classmethod
    def _validate_regime_age(cls, value: float) -> float:
        if value < 0.0:
            raise ValueError("regime_age_sec must be >= 0")
        return value

    @field_validator("regime_confidence", "readiness_completeness")
    @classmethod
    def _validate_unit_range(cls, value: float) -> float:
        if not (0.0 <= value <= 1.0):
            raise ValueError("objective confidence/completeness inputs must be in [0, 1]")
        return value


class ObjectiveMarketInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: float
    atr: float
    spread_bps: float
    liquidity_state: float
    volatility_state: float

    @field_validator("price", "atr", "spread_bps", "liquidity_state", "volatility_state", mode="before")
    @classmethod
    def _validate_finite_float(cls, value: object) -> float:
        if not isinstance(value, (int, float)):
            raise ValueError("objective market fields must be finite numbers")
        value_f = float(value)
        if value_f != value_f or value_f in (float("inf"), float("-inf")):
            raise ValueError("objective market fields must be finite numbers")
        return value_f

    @field_validator("price", "atr")
    @classmethod
    def _validate_positive(cls, value: float) -> float:
        if value <= 0.0:
            raise ValueError("price and atr must be > 0")
        return value

    @field_validator("spread_bps", "liquidity_state", "volatility_state")
    @classmethod
    def _validate_non_negative(cls, value: float) -> float:
        if value < 0.0:
            raise ValueError("spread_bps, liquidity_state, volatility_state must be >= 0")
        return value


class ObjectiveStructureInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold_margin: float
    rr_expected: float
    tp_dist_atr: float
    stop_dist_atr: float

    @field_validator("threshold_margin", "rr_expected", "tp_dist_atr", "stop_dist_atr", mode="before")
    @classmethod
    def _validate_finite_float(cls, value: object) -> float:
        if not isinstance(value, (int, float)):
            raise ValueError("objective structure fields must be finite numbers")
        value_f = float(value)
        if value_f != value_f or value_f in (float("inf"), float("-inf")):
            raise ValueError("objective structure fields must be finite numbers")
        return value_f

    @field_validator("threshold_margin", "rr_expected", "tp_dist_atr", "stop_dist_atr")
    @classmethod
    def _validate_non_negative(cls, value: float) -> float:
        if value < 0.0:
            raise ValueError("objective structure fields must be >= 0")
        return value


class ObjectiveExposureInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_exposure_usd: float
    projected_exposure_usd: float
    max_exposure_usd: float

    @field_validator("current_exposure_usd", "projected_exposure_usd", "max_exposure_usd", mode="before")
    @classmethod
    def _validate_finite_float(cls, value: object) -> float:
        if not isinstance(value, (int, float)):
            raise ValueError("objective exposure fields must be finite numbers")
        value_f = float(value)
        if value_f != value_f or value_f in (float("inf"), float("-inf")):
            raise ValueError("objective exposure fields must be finite numbers")
        return value_f

    @field_validator("current_exposure_usd", "projected_exposure_usd", "max_exposure_usd")
    @classmethod
    def _validate_non_negative(cls, value: float) -> float:
        if value < 0.0:
            raise ValueError("objective exposure fields must be >= 0")
        return value

    @model_validator(mode="after")
    def _validate_exposure_ordering(self) -> "ObjectiveExposureInput":
        if self.max_exposure_usd <= 0.0:
            raise ValueError("max_exposure_usd must be > 0")
        if self.projected_exposure_usd < self.current_exposure_usd:
            raise ValueError("projected_exposure_usd must be >= current_exposure_usd")
        return self


class ObjectiveBehaviorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recent_cancel_replace_count: int
    recent_blocked_intent_count: int
    recent_reentry_count: int

    @field_validator(
        "recent_cancel_replace_count",
        "recent_blocked_intent_count",
        "recent_reentry_count",
        mode="before",
    )
    @classmethod
    def _validate_non_negative_int(cls, value: object) -> int:
        try:
            value_i = int(value)
        except Exception as exc:
            raise ValueError("objective behavior fields must be integers") from exc
        if value_i < 0:
            raise ValueError("objective behavior fields must be >= 0")
        return value_i


class ObjectiveExecutionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_fee_bps: float
    expected_slippage_bps: float

    @field_validator("expected_fee_bps", "expected_slippage_bps", mode="before")
    @classmethod
    def _validate_finite_float(cls, value: object) -> float:
        if not isinstance(value, (int, float)):
            raise ValueError("objective execution fields must be finite numbers")
        value_f = float(value)
        if value_f != value_f or value_f in (float("inf"), float("-inf")):
            raise ValueError("objective execution fields must be finite numbers")
        return value_f

    @field_validator("expected_fee_bps", "expected_slippage_bps")
    @classmethod
    def _validate_non_negative(cls, value: float) -> float:
        if value < 0.0:
            raise ValueError("objective execution fields must be >= 0")
        return value


class ObjectiveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal: ObjectiveSignalInput
    market: ObjectiveMarketInput
    structure: ObjectiveStructureInput
    exposure: ObjectiveExposureInput
    behavior: ObjectiveBehaviorInput
    execution: ObjectiveExecutionInput


class ObjectiveTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    multiplier: float
    objective_score: float
    components: Dict[str, float] = Field(default_factory=dict)
    raw_metrics: Dict[str, float] = Field(default_factory=dict)


class ObjectiveScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    original_score: float
    objective_score: float
    multiplier: float
    components: Dict[str, float] = Field(default_factory=dict)
    raw_metrics: Dict[str, float] = Field(default_factory=dict)
    trace_id: str
    is_blocked: bool = False
    block_reason: str | None = None
    trace: ObjectiveTrace
