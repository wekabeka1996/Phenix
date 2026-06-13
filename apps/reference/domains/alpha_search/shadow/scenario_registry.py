"""
Shadow Scenario Registry
=========================

Pydantic-backed schema for the extended 30-scenario shadow registry.
Loaded from config/alpha_search/scenario_registry_v2.yaml.

AUTHORITY BOUNDARY:
  Every scenario in this registry is shadow_only=True.
  Nothing here touches real execution, real order submission,
  real position management, or real risk authority.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ScenarioFamily(str, Enum):
    MEAN_REVERSION = "mean_reversion"
    TREND_CONTINUATION = "trend_continuation"
    VOLATILITY_BREAKOUT = "volatility_breakout"
    MICROSTRUCTURE = "microstructure"
    REGIME_ADAPTIVE = "regime_adaptive"
    COST_EXECUTION = "cost_execution"
    MD_AMR = "md_amr"


class ExitModel(str, Enum):
    HORIZON_1_BAR = "horizon_1_bar"
    HORIZON_3_BAR = "horizon_3_bar"
    HORIZON_6_BAR = "horizon_6_bar"
    FIXED_TP_SL = "fixed_tp_sl"
    TRAILING_GIVEBACK = "trailing_giveback"
    MICROSTRUCTURE_REVERSAL = "microstructure_reversal_exit"


class ConfidenceModel(str, Enum):
    SCORE_MAGNITUDE = "score_magnitude"
    REGIME_WEIGHTED = "regime_weighted"
    FEATURE_COMPLETENESS = "feature_completeness"
    ENSEMBLE_AGREEMENT = "ensemble_agreement"
    MICROSTRUCTURE_ALIGNED = "microstructure_aligned"


class FeeModel(str, Enum):
    TAKER_10BPS = "taker_10bps"
    TAKER_7BPS = "taker_7bps"
    MAKER_5BPS = "maker_5bps"
    ZERO = "zero_fee"


class SlippageModel(str, Enum):
    ZERO = "zero"
    SPREAD_HALF = "spread_half"
    SPREAD_FULL = "spread_full"
    MARKET_IMPACT = "market_impact_05bps"


# ---------------------------------------------------------------------------
# Per-scenario exit/fee config
# ---------------------------------------------------------------------------

class ShadowExitConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: ExitModel = ExitModel.HORIZON_3_BAR
    tp_bps: Optional[float] = None
    sl_bps: Optional[float] = None
    max_hold_bars: int = Field(default=6, ge=1, le=288)
    trail_activation_bps: Optional[float] = None
    trail_distance_bps: Optional[float] = None


# ---------------------------------------------------------------------------
# Core scenario spec
# ---------------------------------------------------------------------------

class ShadowScenarioSpec(BaseModel):
    """
    Full metadata spec for a shadow scenario.

    shadow_only, authority_applied, no_effect are always True / False / True
    by construction — schema enforces it.
    """

    model_config = ConfigDict(extra="forbid")

    # Identity
    scenario_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    family: ScenarioFamily
    version: str = Field(default="1.0.0")
    enabled: bool = True

    # Authority boundary — immutable
    shadow_only: bool = Field(default=True)
    authority_applied: bool = Field(default=False)
    no_effect: bool = Field(default=True)

    # Scope
    allowed_symbols: List[str] = Field(default_factory=list)
    allowed_regimes: List[str] = Field(default_factory=list)
    allowed_sides: List[str] = Field(default=["BUY", "SELL"])

    # Signal configuration
    timeframe_sec: int = Field(default=300, ge=60)
    horizon_sec: int = Field(default=900, ge=60)
    entry_threshold: float = Field(ge=0.0, le=1.0)
    confidence_model: ConfidenceModel = ConfidenceModel.SCORE_MAGNITUDE
    score_provider: str = Field(default="ta_ensemble")

    # Exit / fee / slippage
    exit: ShadowExitConfig = Field(default_factory=ShadowExitConfig)
    fee_model: FeeModel = FeeModel.TAKER_10BPS
    slippage_model: SlippageModel = SlippageModel.SPREAD_HALF

    # Overrides applied on top of base config (dot-path -> value)
    score_overrides: Dict[str, Any] = Field(default_factory=dict)

    # Documentation
    description: str = Field(default="")
    expected_edge_hypothesis: str = Field(default="")

    @field_validator("shadow_only")
    @classmethod
    def must_be_shadow(cls, v: bool) -> bool:
        if not v:
            raise ValueError("shadow_only must be True — shadow scenarios cannot have live authority")
        return v

    @field_validator("authority_applied")
    @classmethod
    def must_not_have_authority(cls, v: bool) -> bool:
        if v:
            raise ValueError("authority_applied must be False — shadow scenarios have zero live authority")
        return v

    @field_validator("no_effect")
    @classmethod
    def must_be_no_effect(cls, v: bool) -> bool:
        if not v:
            raise ValueError("no_effect must be True — shadow scenarios produce no real trading effects")
        return v

    @model_validator(mode="after")
    def validate_sides(self) -> "ShadowScenarioSpec":
        valid = {"BUY", "SELL", "NEUTRAL"}
        bad = set(self.allowed_sides) - valid
        if bad:
            raise ValueError(f"Invalid allowed_sides: {bad}")
        return self


# ---------------------------------------------------------------------------
# Registry root
# ---------------------------------------------------------------------------

class ShadowScenarioRegistry(BaseModel):
    """Root schema for scenario_registry_v2.yaml."""

    model_config = ConfigDict(extra="forbid")

    registry_id: str
    version: int = Field(default=1, ge=1)
    description: str = Field(default="")
    scenarios: List[ShadowScenarioSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "ShadowScenarioRegistry":
        ids = [s.scenario_id for s in self.scenarios]
        dupes = {sid for sid in ids if ids.count(sid) > 1}
        if dupes:
            raise ValueError(f"Duplicate scenario IDs in registry: {dupes}")
        return self

    @model_validator(mode="after")
    def validate_minimum_scenarios(self) -> "ShadowScenarioRegistry":
        enabled = [s for s in self.scenarios if s.enabled]
        if len(enabled) < 25:
            raise ValueError(
                f"Registry must have at least 25 enabled scenarios, got {len(enabled)}"
            )
        return self

    @model_validator(mode="after")
    def validate_all_shadow(self) -> "ShadowScenarioRegistry":
        non_shadow = [s.scenario_id for s in self.scenarios if not s.shadow_only]
        if non_shadow:
            raise ValueError(f"Non-shadow scenarios found: {non_shadow}")
        return self

    def get_enabled(self) -> List[ShadowScenarioSpec]:
        return [s for s in self.scenarios if s.enabled]

    def get_by_family(self, family: ScenarioFamily) -> List[ShadowScenarioSpec]:
        return [s for s in self.scenarios if s.family == family and s.enabled]

    def get_by_id(self, scenario_id: str) -> Optional[ShadowScenarioSpec]:
        for s in self.scenarios:
            if s.scenario_id == scenario_id:
                return s
        return None

    def duplicate_fingerprints(self) -> Dict[str, List[str]]:
        """Return groups of scenarios that share identical (score_provider, entry_threshold, score_overrides) tuples."""
        from collections import defaultdict
        groups: Dict[str, List[str]] = defaultdict(list)
        for s in self.scenarios:
            key = f"{s.score_provider}|{s.entry_threshold}|{sorted(s.score_overrides.items())}"
            groups[key].append(s.scenario_id)
        return {k: v for k, v in groups.items() if len(v) > 1}


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_registry(path: str) -> ShadowScenarioRegistry:
    """Load and validate scenario_registry_v2.yaml."""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return ShadowScenarioRegistry.model_validate(raw)
