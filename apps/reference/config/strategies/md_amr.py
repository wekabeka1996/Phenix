from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.reference.config.domains.decision_making import SafetyGatesConfig


class MDAMRWeightsConfig(BaseModel):
    """Raw directional weights for MD-AMR multi-timeframe compass."""
    model_config = ConfigDict(extra='forbid')

    d1: float = Field(..., ge=0.0)
    h1: float = Field(..., ge=0.0)
    m30: float = Field(..., ge=0.0)
    m15: float = Field(..., ge=0.0)

    @model_validator(mode='after')
    def _validate_positive_weight_budget(self) -> 'MDAMRWeightsConfig':
        total_weight = (
            float(self.d1)
            + float(self.h1)
            + float(self.m30)
            + float(self.m15)
        )
        if total_weight <= 0.0:
            raise ValueError(
                "MDAMR weights must sum to > 0.0; runtime equal-weight fallback is forbidden"
            )
        return self


class MDAMRLLMGateConfig(BaseModel):
    """LLM macro shock binary block gate."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    sentiment_block_threshold: float = Field(..., ge=-1.0, le=1.0)
    block_ttl_sec: int = Field(..., ge=60)


_MD_AMR_ALLOWED_REGIME_ALIASES: Dict[str, str] = {
    "LOW_FLAT": "FLAT_LOW",
    "HIGH_FLAT": "FLAT_HIGH",
    "HIGHT_FLAT": "FLAT_HIGH",
    "NORMAL_FLAT": "FLAT_NORMAL",
    "HIGH_VOLATILYTY": "HIGH_VOLATILITY",
    "LOW_VOLATILYTY": "LOW_VOLATILITY",
    "HIGHT_VOLATILITY": "HIGH_VOLATILITY",
}

_MD_AMR_ALLOWED_REGIMES: frozenset[str] = frozenset({
    "TREND_UP",
    "TREND_DOWN",
    "MEAN_REVERSION",
    "HIGH_VOLATILITY",
    "LOW_VOLATILITY",
    "UNCERTAIN",
    "FLAT_LOW",
    "FLAT_NORMAL",
    "FLAT_HIGH",
})


class MDAMRAssetConfig(BaseModel):
    """Per-asset enablement/config for md_amr."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    cooldown_sec: int = Field(..., ge=0)
    position_mode: Literal["STRICT", "DYNAMIC"] = Field(...)
    allowed_regimes: Optional[List[str]] = Field(
        ..., description="Explicit regime allowlist for md_amr. Assigned live symbols must set a non-empty list.",
    )
    exit: Optional["MDAMRExitConfig"] = Field(
        ..., description="MD-AMR TP/SL config. None = no brackets emitted.",
    )

    @field_validator('allowed_regimes', mode='before')
    @classmethod
    def _normalize_allowed_regimes(cls, value: Any) -> Any:
        if value is None or not isinstance(value, list):
            return value
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_regime in value:
            regime = str(raw_regime or '').strip().upper()
            if not regime:
                continue
            regime = _MD_AMR_ALLOWED_REGIME_ALIASES.get(regime, regime)
            if regime not in _MD_AMR_ALLOWED_REGIMES:
                raise ValueError(
                    f"Unknown md_amr allowed_regimes value '{raw_regime}'. "
                    f"Valid values: {sorted(_MD_AMR_ALLOWED_REGIMES)}"
                )
            if regime not in seen:
                seen.add(regime)
                normalized.append(regime)
        return normalized


class MDAMRReconciliationConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    interval_sec: int = Field(..., ge=10, le=3600)
    drift_tolerance: float = Field(..., ge=0.0)


class MDAMRConcentrationGuardConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    max_simultaneous_entries_per_bar: int = Field(..., ge=1, le=20)


class MDAMROptunaConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    oos_split_ratio: float = Field(..., ge=0.0, le=0.5)
    min_oos_calmar_ratio: float = Field(..., ge=0.0)


class MDAMRProgressTrackingConfig(BaseModel):
    """Package C.1 progress-state thresholds."""
    model_config = ConfigDict(extra='forbid')

    early_progress_max_pct: float = Field(
        ..., ge=0.0,
        le=1.0,
        description="Upper bound for EARLY_PROGRESS classification.",
    )
    partial_progress_max_pct: float = Field(
        ..., ge=0.0,
        le=1.0,
        description="Upper bound for PARTIAL_PROGRESS classification.",
    )
    near_completion_max_pct: float = Field(
        ..., ge=0.0,
        le=1.0,
        description=(
            "Upper bound for NEAR_COMPLETION classification. Values at or above "
            "this threshold are COMPLETE."
        ),
    )

    @model_validator(mode='after')
    def _validate_progress_threshold_order(self) -> 'MDAMRProgressTrackingConfig':
        if float(self.early_progress_max_pct) >= float(self.partial_progress_max_pct):
            raise ValueError(
                "MDAMR progress_tracking requires early_progress_max_pct < partial_progress_max_pct"
            )
        if float(self.partial_progress_max_pct) >= float(self.near_completion_max_pct):
            raise ValueError(
                "MDAMR progress_tracking requires partial_progress_max_pct < near_completion_max_pct"
            )
        return self


class MDAMRSetupQualityConfig(BaseModel):
    """Package C.2 setup-quality thresholds."""
    model_config = ConfigDict(extra='forbid')

    penetration_depth_full_scale: float = Field(
        ..., gt=0.0,
        le=10.0,
        description=(
            "Penetration depth at which the penetration setup-quality sub-score "
            "saturates at 1.0."
        ),
    )
    channel_width_pct_full_scale: float = Field(
        ..., gt=0.0,
        le=100.0,
        description=(
            "Channel width percentage at which the channel-quality sub-score "
            "saturates at 1.0."
        ),
    )
    volatility_z_full_penalty: float = Field(
        ..., gt=0.0,
        le=100.0,
        description=(
            "ATR z-score at which the setup-quality volatility sub-score reaches 0.0."
        ),
    )


class MDAMRHoldQualityConfig(BaseModel):
    """Package C.3 hold-quality / soft-decay overlay configuration."""
    model_config = ConfigDict(extra='forbid')

    expected_progress_grace_frac: float = Field(
        ..., ge=0.0,
        lt=1.0,
        description=(
            "Initial fraction of max_hold_bars during which anchored progress is "
            "not yet expected. After the grace window, expected progress ramps "
            "linearly to 1.0 by timeout."
        ),
    )
    time_decay_weight: float = Field(
        ..., ge=0.0,
        le=1.0,
        description="Penalty weight applied to time_decay when deriving hold_quality.",
    )
    progress_deficit_weight: float = Field(
        ..., ge=0.0,
        le=1.0,
        description=(
            "Penalty weight applied to progress_deficit when deriving hold_quality."
        ),
    )

    @model_validator(mode='after')
    def _validate_penalty_budget(self) -> 'MDAMRHoldQualityConfig':
        penalty_budget = float(self.time_decay_weight) + \
            float(self.progress_deficit_weight)
        if penalty_budget > 1.0:
            raise ValueError(
                "MDAMR hold_quality penalty weights must sum to <= 1.0"
            )
        return self


class MDAMRContextValidityConfig(BaseModel):
    """Package C.4 lightweight context-validity overlay configuration."""
    model_config = ConfigDict(extra='forbid')

    regime_confidence_floor: float = Field(
        ..., ge=0.0,
        le=1.0,
        description=(
            "Confidence at or below this level contributes zero regime-validity "
            "score even when the current regime remains allowlisted."
        ),
    )
    regime_confidence_valid: float = Field(
        ..., ge=0.0,
        le=1.0,
        description=(
            "Confidence at or above this level contributes full regime-validity "
            "score when the current regime remains allowlisted."
        ),
    )
    volatility_z_weakening: float = Field(
        ..., ge=0.0,
        le=100.0,
        description=(
            "ATR z-score where elevated local volatility starts weakening "
            "context validity."
        ),
    )
    volatility_z_invalid: float = Field(
        ..., ge=0.0,
        le=100.0,
        description="ATR z-score where volatility-validity reaches zero.",
    )
    channel_width_pct_floor: float = Field(
        ..., ge=0.0,
        le=100.0,
        description=(
            "Channel width percentage at or below which local channel context "
            "is treated as structurally invalid for mean reversion."
        ),
    )
    channel_width_pct_valid: float = Field(
        ..., ge=0.0,
        le=100.0,
        description=(
            "Channel width percentage at or above which channel sanity "
            "contributes fully to context validity."
        ),
    )
    regime_weight: float = Field(
        ..., ge=0.0,
        le=1.0,
        description="Weight of the regime-validity component.",
    )
    volatility_weight: float = Field(
        ..., ge=0.0,
        le=1.0,
        description="Weight of the local volatility-validity component.",
    )
    structure_weight: float = Field(
        ..., ge=0.0,
        le=1.0,
        description="Weight of the local structure-validity component.",
    )
    progress_alignment_weight: float = Field(
        ..., ge=0.0,
        le=1.0,
        description=(
            "Weight of the thesis-progress alignment component derived from "
            "existing C.3 overlays."
        ),
    )
    valid_score_min: float = Field(
        ..., ge=0.0,
        le=1.0,
        description="Minimum context_validity score required to classify the context as VALID.",
    )
    invalid_score_max: float = Field(
        ..., ge=0.0,
        le=1.0,
        description=(
            "Maximum context_validity score still classified as INVALID. Scores "
            "between invalid_score_max and valid_score_min are WEAKENING."
        ),
    )

    @model_validator(mode='after')
    def _validate_context_validity_contract(self) -> 'MDAMRContextValidityConfig':
        if float(self.regime_confidence_valid) <= float(self.regime_confidence_floor):
            raise ValueError(
                "MDAMR context_validity requires regime_confidence_valid > regime_confidence_floor"
            )
        if float(self.volatility_z_invalid) <= float(self.volatility_z_weakening):
            raise ValueError(
                "MDAMR context_validity requires volatility_z_invalid > volatility_z_weakening"
            )
        if float(self.channel_width_pct_valid) <= float(self.channel_width_pct_floor):
            raise ValueError(
                "MDAMR context_validity requires channel_width_pct_valid > channel_width_pct_floor"
            )
        total_weight = (
            float(self.regime_weight)
            + float(self.volatility_weight)
            + float(self.structure_weight)
            + float(self.progress_alignment_weight)
        )
        if abs(total_weight - 1.0) > 1e-9:
            raise ValueError(
                "MDAMR context_validity weights must sum exactly to 1.0"
            )
        if float(self.valid_score_min) <= float(self.invalid_score_max):
            raise ValueError(
                "MDAMR context_validity requires valid_score_min > invalid_score_max"
            )
        return self


class MDAMREntryAnchorPersistenceConfig(BaseModel):
    """Package D.2-PRE restart artifact for md_amr strategy-local anchors."""
    model_config = ConfigDict(extra='forbid')

    storage_path: str = Field(
        ..., min_length=1,
        description=(
            "Path to the md_amr strategy-local entry-anchor restart artifact. "
            "Stores only strategy-local anchor state; execution entry price is "
            "recovered from runtime execution truth."
        ),
    )


class MDAMRExitConfig(BaseModel):
    """Per-symbol exit/TP/SL config for md_amr strategy."""
    model_config = ConfigDict(extra='forbid')

    sl_pct: float = Field(..., gt=0.0, lt=0.5)
    tp_rr: float = Field(..., gt=0.0, lt=20.0)
    regime_tpsl: Optional["RegimeTpSlConfig"] = Field(...)


class MDAMRStrategyConfig(BaseModel):
    """Full configuration for MD-AMR strategy."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(..., description='Enable md_amr strategy')
    type: str = Field(..., description='Strategy type identifier')
    description: str = Field(..., description='Human-readable profile description')
    timeframe_sec: int = Field(..., ge=60, le=86400)
    defer_ttl_sec: int = Field(..., ge=1, le=300)
    channel_window_bars: int = Field(..., ge=3, le=256)
    channel_robust_pct: float = Field(..., ge=0.0, le=0.25)
    atr_window: int = Field(..., ge=2, le=256)
    atr_stats_window: int = Field(..., ge=8, le=512)
    hysteresis_mult: float = Field(..., ge=1.0, le=3.0)
    threshold_z: float = Field(..., ge=0.1, le=10.0)
    volatility_dampening_factor: float = Field(..., ge=0.0, le=1.0)
    thr_base: float = Field(..., ge=0.05, le=0.99)
    thr_floor: float = Field(..., ge=0.01, le=0.50)
    alpha: float = Field(..., ge=0.0, le=1.0)
    conf_min: float = Field(
        ..., ge=0.0,
        le=1.0,
        description=(
            "DEPRECATED in exit path (Package A): conf_min no longer triggers "
            "EDGE_GONE_KILLSWITCH. Retained for config backward-compatibility and "
            "potential Package B semantic cleanup. Runtime kill threshold is now "
            "hold_edge_min. See MD_AMR_PACKAGE_A_REPORT.md."
        ),
    )
    hold_edge_min: float = Field(
        ..., ge=-1.0,
        lt=0.0,
        description=(
            "Package A (Exit Semantics Repair): minimum hold_edge before EDGE_GONE_KILLSWITCH. "
            "hold_edge = dir_score (LONG) or -dir_score (SHORT). "
            "Values <= hold_edge_min trigger FULL_CLOSE. "
            "Default -0.5 requires significant directional inversion. Range (-1.0, 0.0)."
        ),
    )
    target_approach_pct: float = Field(
        ..., ge=0.0,
        lt=0.05,
        description=(
            "Package B (Hold Calibration): tolerance for FEE_AWARE_SCALEOUT target zone. "
            "reached_target = close_now >= avg_close * (1 - target_approach_pct). "
            "Default 0.002 (0.2%) allows scaleout when price is within 0.2%% of avg_close. "
            "Set to 0.0 for strict exact-target semantics (Package A baseline behavior)."
        ),
    )
    max_hold_bars: int = Field(..., ge=1, le=10000)
    atr_zscore_clamp: float = Field(..., ge=1.0, le=100.0)
    atr_std_floor_pct: float = Field(..., ge=0.0, le=1.0)
    fee_bps: float = Field(..., ge=0.0)
    slippage_buffer_bps: float = Field(..., ge=0.0)
    scaleout_fraction: float = Field(..., ge=0.01, le=1.0)
    scaleout_cost_model: Literal["one_way", "round_trip"] = Field(...)
    weights: MDAMRWeightsConfig = Field(...)
    execution: "StrategyExecutionConfig" = Field(
        ..., description="Execution policy (SSOT)")
    safety_gates: SafetyGatesConfig = Field(..., description="Safety gates control")
    llm_gate: MDAMRLLMGateConfig = Field(...)
    reconciliation: MDAMRReconciliationConfig = Field(
        ...)
    concentration_guard: MDAMRConcentrationGuardConfig = Field(
        ...)
    progress_tracking: MDAMRProgressTrackingConfig = Field(
        ..., description="Package C.1 progress-state thresholds")
    setup_quality: MDAMRSetupQualityConfig = Field(
        ..., description="Package C.2 setup-quality thresholds")
    hold_quality: MDAMRHoldQualityConfig = Field(
        ..., description="Package C.3 hold-quality / soft-decay overlay")
    context_validity: MDAMRContextValidityConfig = Field(
        ..., description="Package C.4 lightweight context-validity overlay")
    entry_anchor_persistence: MDAMREntryAnchorPersistenceConfig = Field(
        ..., description="Package D.2-PRE strategy-local entry-anchor restart artifact")
    optuna: MDAMROptunaConfig = Field(...)
    assets: Dict[str, MDAMRAssetConfig] = Field(...)
    objective: Optional["StrategyObjectiveConfig"] = Field(
        ..., description="Strategy objective configuration"
    )

    @model_validator(mode='after')
    def _validate_md_amr_runtime_weight_contract(self) -> 'MDAMRStrategyConfig':
        dampened_total = (
            float(self.weights.m30)
            + float(self.weights.m15)
            + float(self.volatility_dampening_factor)
            * (float(self.weights.d1) + float(self.weights.h1))
        )
        if dampened_total <= 0.0:
            raise ValueError(
                "MDAMR weights and volatility_dampening_factor produce zero post-dampening budget; runtime fallback is forbidden"
            )
        return self
