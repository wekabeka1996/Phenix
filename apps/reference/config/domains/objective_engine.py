from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ObjectiveNormalizationConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = Field(...)
    method: str = Field(...)
    window_size: int = Field(..., ge=10)
    min_samples: int = Field(..., ge=2)
    target_range: Tuple[float, float] = Field(...)
    epsilon: float = Field(...)
    smoothing_factor: float = Field(...)
    outlier_threshold: float = Field(...)


class ObjectiveComponentConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = Field(...)
    normalization: Optional[ObjectiveNormalizationConfig] = Field(...)
    parameters: Dict[str, Any] = Field(...)

    @model_validator(mode="after")
    def _validate_enabled_component(self) -> "ObjectiveComponentConfig":
        if self.enabled and not self.parameters:
            raise ValueError(
                "objective component parameters are required when component is enabled")
        return self


class ObjectiveDataRequirementsConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    require_arce: bool = Field(...)
    require_portfolio: bool = Field(...)
    require_execution: bool = Field(...)
    strict_fail_closed: bool = Field(...)


class ObjectiveExplainabilityConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = Field(...)
    emit_subcomponents: bool = Field(...)
    emit_normalization_stats: bool = Field(...)


class ObjectiveEngineDomainConfig(BaseModel):
    """Domain config for Objective Engine."""
    model_config = ConfigDict(extra='forbid')
    enabled: bool = Field(...)
    data_requirements: ObjectiveDataRequirementsConfig = Field(
        ...)
    explainability: ObjectiveExplainabilityConfig = Field(
        ...)
    components: Dict[str, ObjectiveComponentConfig] = Field(
        ...)

    @model_validator(mode="after")
    def _validate_enabled_domain(self) -> "ObjectiveEngineDomainConfig":
        if not self.enabled:
            return self
        allowed = {"cost", "risk", "edge",
                   "execution", "information", "behavior"}
        unknown = sorted(set(self.components.keys()) - allowed)
        if unknown:
            raise ValueError(
                f"objective_engine.components has unsupported keys: {','.join(unknown)}")
        enabled_components = [name for name,
                              cfg in self.components.items() if cfg.enabled]
        if not enabled_components:
            raise ValueError(
                "objective_engine.components must contain at least one enabled component when objective_engine.enabled=true")
        required_params = {
            "cost": {"alpha_fee", "alpha_slippage", "alpha_spread", "base_fee_bps", "slippage_from_spread_ratio"},
            "risk": {"phi_inventory", "phi_overflow", "phi_volatility"},
            "edge": {"omega_rr", "omega_threshold_margin", "phi_stop_distance", "phi_rr_consistency"},
            "execution": {"omega_liquidity", "phi_spread_drag", "phi_notional_pressure"},
            "information": {"phi_staleness", "omega_regime_confidence", "omega_readiness"},
            "behavior": {"phi_cancel_replace", "phi_blocked_intents", "phi_reentry", "window_sec"},
        }
        for name in enabled_components:
            cfg = self.components[name]
            missing_params = sorted(
                required_params[name] - set(cfg.parameters.keys()))
            if missing_params:
                raise ValueError(
                    f"objective_engine.components.{name}.parameters missing required keys: {','.join(missing_params)}")
        return self
