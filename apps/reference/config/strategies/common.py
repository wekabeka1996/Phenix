from __future__ import annotations
from apps.reference.config.strategies.mean_reversion import (
    MeanReversion1mStrategyConfig,
)
from apps.reference.config.strategies.md_amr import MDAMRStrategyConfig
from apps.reference.config.strategies.llm_microstructure import (
    LLMMicrostructureStrategyConfig,
)
from apps.reference.config.strategies.aurora import AuroraStrategyConfig

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrategiesArbitrationLoggingConfig(BaseModel):
    """Logging configuration for strategy arbitration."""
    model_config = ConfigDict(extra='forbid')

    rejected_why_prefix: str = Field(
        description='Prefix for why-codes when strategy intent is rejected')
    log_level: str = Field(
        description='Log level for arbitration events (INFO/WARNING/ERROR)')


class StrategiesArbitrationConfig(BaseModel):
    """Configuration for strategy conflict arbitration."""
    model_config = ConfigDict(extra='forbid')

    mode: Literal['priority'] = Field(
        description="Arbitration mode: 'priority' (only supported mode, lower number = higher priority)")
    window_ms: int = Field(
        description="Decision window size in ms for multi-strategy arbitration (SSOT; no silent defaults).")
    priority: Dict[str, int] = Field(
        description='Strategy priority ranks (lower = higher priority)')
    logging: StrategiesArbitrationLoggingConfig = Field()


class StrategiesRegistryConfig(BaseModel):
    """
    Strategies Registry SSOT (config/aurora/strategies.yaml).

    Defines:
    1. Which strategies are active per symbol (assignments)
    2. How to arbitrate conflicts between strategies (arbitration)

    CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION: Strict validation (extra='forbid')
    """
    model_config = ConfigDict(extra='forbid')

    version: str = Field(description='Strategies registry config version')
    assignments: Dict[str, List[str]] = Field(
        description='Per-symbol strategy assignments (symbol → list[strategy_id])')
    arbitration: StrategiesArbitrationConfig = Field(
        description='Arbitration policy for strategy conflicts')

    @model_validator(mode='after')
    def validate_priorities_for_hybrid_symbols(self) -> 'StrategiesRegistryConfig':
        """Ensure all strategies in hybrid assignments have priorities defined."""
        if self.arbitration.mode == 'priority':
            priorities = self.arbitration.priority
            for symbol, strategies in self.assignments.items():
                if len(strategies) > 1:
                    for strategy_id in strategies:
                        if strategy_id not in priorities:
                            raise ValueError(
                                f"❌ ARBITRATION:missing_priority for '{strategy_id}' in hybrid "
                                f"symbol {symbol}. All strategies must have priorities defined."
                            )
        return self


class StrategyObjectiveMultiplierConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    m_min: float = Field(ge=0.0, le=1.0)
    m_max: float = Field(ge=1.0)
    lambda_scale: float = Field(ge=0.0)
    penalty_center: float = Field()
    penalty_scale: float = Field(gt=0.0)

    @model_validator(mode="after")
    def _validate_range(self) -> "StrategyObjectiveMultiplierConfig":
        if self.m_min > self.m_max:
            raise ValueError("objective multiplier requires m_min <= m_max")
        return self


class StrategyObjectiveGateConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    min_objective_score: float = Field(ge=0.0, le=1.0)
    enforcement_mode: Literal["OBSERVE", "GATE", "MULTIPLY"] = Field()


class StrategyObjectiveRegimeProfile(BaseModel):
    model_config = ConfigDict(extra='forbid')

    weights: Dict[str, float] = Field()
    multiplier: StrategyObjectiveMultiplierConfig = Field()
    gate: StrategyObjectiveGateConfig = Field()

    @model_validator(mode="after")
    def _validate_weights(self) -> "StrategyObjectiveRegimeProfile":
        if not self.weights:
            raise ValueError(
                "objective regime profile requires non-empty weights")
        if sum(abs(float(v)) for v in self.weights.values()) <= 0.0:
            raise ValueError(
                "objective regime profile requires non-zero weight mass")
        return self


class StrategyObjectiveConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(default=False)
    regimes: Dict[str, StrategyObjectiveRegimeProfile] = Field(
        default_factory=dict)

    @model_validator(mode="after")
    def _validate_enabled_config(self) -> "StrategyObjectiveConfig":
        if self.enabled and not self.regimes:
            raise ValueError(
                "strategy objective requires at least one regime profile when enabled")
        return self


class StrategiesConfig(BaseModel):
    """Canonical strategy policy namespace (CFG-STRATEGY-SSOT-FREEZE-03)."""

    model_config = ConfigDict(extra="forbid")

    aurora: Optional["AuroraStrategyConfig"] = Field(
        default=None,
        description="Aurora strategy config (from strategies/aurora.yaml)",
    )
    mean_reversion: Optional["MeanReversion1mStrategyConfig"] = Field(
        default=None,
        description="Mean Reversion 1m strategy config (from strategies/mean_reversion.yaml)",
    )
    md_amr: Optional["MDAMRStrategyConfig"] = Field(
        default=None,
        description="MD-AMR strategy config (from strategies/md_amr.yaml)",
    )
    llm_microstructure: Optional["LLMMicrostructureStrategyConfig"] = Field(
        default=None,
        description="LLM microstructure strategy config (from strategies/llm_microstructure.yaml)",
    )
