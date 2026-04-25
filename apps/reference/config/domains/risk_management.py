from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RiskScoreWeightsConfig(BaseModel):
    """Risk score weights configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    delta_price_pct: float = Field(...)
    obi: float = Field(...)
    tfi: float = Field(...)
    absorption_inverse: float = Field(...)
    # PKG-ABSORPTION-RISK-FULL: weight for emitted absorption feature value.
    # Default 0.0 → identical to old behavior when omitted from YAML.
    absorption_feature: float = Field(
        ..., ge=0.0,
        description="Weight for emitted absorption feature in risk score (source='feature'|'both'). "
                    "Default 0.0 → no effect.",
    )


class TradingAllowedThresholdsConfig(BaseModel):
    """Trading allowed thresholds configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    # IMPORTANT: Default exists for test compatibility, but production MUST override
    max_risk_score: float = Field(
        ..., description='Max risk score. PRODUCTION MUST OVERRIDE in domains.yaml!')


class RiskValidationConfig(BaseModel):
    """Risk validation configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    total_weight_min: float = Field(...)
    total_weight_max: float = Field(...)


class RiskManagementDomainConfig(BaseModel):
    """Complete risk management domain configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    risk_score_weights: RiskScoreWeightsConfig = Field(...)
    trading_allowed_thresholds: TradingAllowedThresholdsConfig = Field(...)
    validation: RiskValidationConfig = Field(...)

    # D5: Absorption deprecation flag
    # When False, absorption term is excluded from risk score calculation
    # NOTE: Other weights are NOT rescaled when absorption is disabled (per Plan v1)
    use_absorption_penalty: bool = Field(
        ..., description='Whether to include absorption toxicity penalty in risk score. '
                    'Set to False to disable (default). Requires absorption_dp_cap_pct when True.'
    )

    # P3-SSOT: Cap for |delta_price_pct| in toxicity formula.
    # Required when use_absorption_penalty=True — fail-closed, no hardcoded fallback.
    absorption_dp_cap_pct: Optional[float] = Field(
        ..., gt=0.0, le=1.0,
        description=(
            'Cap for delta_price_pct normalisation in absorption toxicity penalty (0..1). '
            'Required when use_absorption_penalty=True. '
            'No hardcoded fallback — must be set in domains.yaml under risk_management.'
        )
    )

    # PKG-ABSORPTION-RISK-FULL: source-routing for absorption term in risk score.
    # "proxy"   → toxicity = |tfi| * clip(|dp_pct|/dp_cap, 0, 1)  (P3 default, backward compat)
    # "feature" → feature_term = clip(|absorption|, clip_min, clip_max) * absorption_feature_w
    # "both"    → both terms applied
    absorption_penalty_source: Literal["proxy", "feature", "both"] = Field(
        ..., description='Source for absorption penalty term: proxy (default), feature, or both. '
                    'Default "proxy" → identical to P3 behavior.',
    )
    absorption_feature_clip_min: float = Field(
        ..., ge=0.0, le=1.0,
        description="Clip min for |absorption| before applying absorption_feature weight. Default 0.0.",
    )
    absorption_feature_clip_max: float = Field(
        ..., ge=0.0, le=1.0,
        description="Clip max for |absorption| before applying absorption_feature weight. Default 1.0.",
    )

    @model_validator(mode='after')
    def _require_dp_cap_when_penalty_enabled(self) -> 'RiskManagementDomainConfig':
        """P3-SSOT: Fail-closed — absorption_dp_cap_pct required when penalty is on."""
        if bool(getattr(self, "use_absorption_penalty", False)) and getattr(self, "absorption_dp_cap_pct", None) is None:
            raise ValueError(
                "risk_management.absorption_dp_cap_pct is required when use_absorption_penalty=True. "
                "Add 'absorption_dp_cap_pct: 0.02' to domains.yaml under risk_management:. "
                "No hardcoded fallback — explicit YAML SSOT only."
            )
        return self
