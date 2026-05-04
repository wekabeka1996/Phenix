"""
LLM Judge — Config Models (Phase 1 + Phase 2 + Phase 3 + Phase 4)

Pydantic strict config models for Judge cortex operational mode, expert
configuration, chamber aggregation configuration, and verdict assembly
configuration.

Authority: docs/LLM_JUDGE/LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md
           docs/LLM_JUDGE/LLM_JUDGE_PHASE2_IMPLEMENTATION_BLUEPRINT.md
           docs/LLM_JUDGE/LLM_JUDGE_PHASE3_IMPLEMENTATION_BLUEPRINT.md
           docs/LLM_JUDGE/LLM_JUDGE_PHASE4_IMPLEMENTATION_BLUEPRINT.md

Phase 1 runtime admission: only 'off' is admitted.
Phase 2 runtime admission: 'off' and 'shadow' are admitted.
Phase 3 addition: ChamberConfig for chamber aggregation parameters.
Phase 4 addition: VerdictConfig for verdict assembly parameters.
The full CortexMode type surface is preserved for forward compatibility.
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .contracts import CortexMode

NormalizeMode = Literal["off", "signed_v2"]
IntrabarAmbiguityPolicy = Literal["mark_ambiguous", "prioritize_sl", "prioritize_tp"]


class ShadowSimulatorConfig(BaseModel):
    """Config for Shadow Plan Fill Simulator (J6-S4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    max_bars_after_signal: int = 12
    intrabar_ambiguity_policy: IntrabarAmbiguityPolicy = "mark_ambiguous"
    fees_bps: float = 2.0
    slippage_bps: float = 1.0



class SignalWeightsExpertConfig(BaseModel):
    """Config for the flat weighted-centering expert (signal_weights_expert).

    Implements the legacy SignalScoreV2.calculate_score() formula:
        score = SUM(w * (x - neutral)) / SUM(|w|)
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    expert_id: str = "judge.signal_weights_v1"
    expert_version: str = "1.0.0"
    symbols: Optional[List[str]] = None
    signal_threshold: float = 0.162
    normalize_mode: NormalizeMode = "off"
    essential_features: List[str] = []
    min_active_features: int = 1
    signal_weights: Dict[str, float] = {}
    feature_neutrals: Dict[str, float] = {}

    @field_validator("signal_threshold")
    @classmethod
    def signal_threshold_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("signal_threshold must be > 0")
        return v

    @field_validator("min_active_features")
    @classmethod
    def min_active_features_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("min_active_features must be > 0")
        return v

    @model_validator(mode="after")
    def validate_weights_neutrals(self) -> "SignalWeightsExpertConfig":
        if self.enabled:
            if not self.signal_weights:
                raise ValueError(
                    "signal_weights must be non-empty when expert is enabled"
                )
            if not self.feature_neutrals:
                raise ValueError(
                    "feature_neutrals must be non-empty when expert is enabled"
                )
            for feat, w in self.signal_weights.items():
                if w != 0 and feat not in self.feature_neutrals:
                    raise ValueError(
                        f"Weighted feature '{feat}' (w={w}) has no "
                        f"corresponding neutral entry"
                    )
            for feat in self.essential_features:
                if feat not in self.signal_weights:
                    raise ValueError(
                        f"Essential feature '{feat}' not present in "
                        f"signal_weights"
                    )
            active_features = sum(
                1 for weight in self.signal_weights.values() if weight != 0
            )
            if active_features > 0 and self.min_active_features > active_features:
                raise ValueError(
                    "min_active_features must be <= count of non-zero "
                    "weighted features when expert is enabled"
                )
        return self


class FeatureNeutralsExpertConfig(BaseModel):
    """Config for the direction-strength composite expert (feature_neutrals_expert).

    Implements the legacy direction-strength formula:
        dir = SUM(w_dir * (x - neutral)) / SUM(|w_dir|)
        str = SUM(w_str * (x - neutral)) / SUM(|w_str|)
        final = dir * (1 + strength_alpha * clamp(str, 0, strength_cap))
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    expert_id: str = "judge.feature_neutrals_v1"
    expert_version: str = "1.0.0"
    symbols: Optional[List[str]] = None
    signal_threshold: float = 0.162
    normalize_mode: NormalizeMode = "off"
    essential_features: List[str] = []
    directional_features: List[str] = []
    min_active_directional_features: int = 1
    strength_features: List[str] = []
    strength_alpha: float = 0.5
    strength_cap: float = 1.0
    signal_weights: Dict[str, float] = {}
    feature_neutrals: Dict[str, float] = {}

    @field_validator("signal_threshold")
    @classmethod
    def signal_threshold_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("signal_threshold must be > 0")
        return v

    @field_validator("min_active_directional_features")
    @classmethod
    def min_active_directional_features_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("min_active_directional_features must be > 0")
        return v

    @field_validator("strength_alpha")
    @classmethod
    def strength_alpha_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("strength_alpha must be >= 0")
        return v

    @field_validator("strength_cap")
    @classmethod
    def strength_cap_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("strength_cap must be >= 0")
        return v

    @model_validator(mode="after")
    def validate_weights_neutrals(self) -> "FeatureNeutralsExpertConfig":
        if self.enabled:
            if not self.signal_weights:
                raise ValueError(
                    "signal_weights must be non-empty when expert is enabled"
                )
            if not self.feature_neutrals:
                raise ValueError(
                    "feature_neutrals must be non-empty when expert is enabled"
                )
            for feat, w in self.signal_weights.items():
                if w != 0 and feat not in self.feature_neutrals:
                    raise ValueError(
                        f"Weighted feature '{feat}' (w={w}) has no "
                        f"corresponding neutral entry"
                    )
            for feat in self.essential_features:
                if feat not in self.signal_weights:
                    raise ValueError(
                        f"Essential feature '{feat}' not present in "
                        f"signal_weights"
                    )
            if not self.directional_features:
                raise ValueError(
                    "directional_features must be non-empty when expert "
                    "is enabled"
                )
            overlap = set(self.directional_features) & set(
                self.strength_features
            )
            if overlap:
                raise ValueError(
                    f"directional_features and strength_features must not "
                    f"overlap, found: {overlap}"
                )
            active_directional = sum(
                1
                for feature in self.directional_features
                if self.signal_weights.get(feature, 0.0) != 0
            )
            if (
                active_directional > 0
                and self.min_active_directional_features > active_directional
            ):
                raise ValueError(
                    "min_active_directional_features must be <= count of "
                    "non-zero directional features when expert is enabled"
                )
        return self


class JudgeExpertsConfig(BaseModel):
    """Container for all judge expert configs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_weights: SignalWeightsExpertConfig = SignalWeightsExpertConfig()
    feature_neutrals: FeatureNeutralsExpertConfig = FeatureNeutralsExpertConfig()


class JudgeShadowLogConfig(BaseModel):
    """Config for shadow-mode JSONL logging of expert outputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = True
    log_dir: str = "logs/judge_experts"
    max_file_size_mb: int = 50
    rotation: Literal["daily"] = "daily"


class ChamberConfig(BaseModel):
    """Config for chamber aggregation (Phase 3).

    Controls admissibility rules (quorum, freshness) and which chambers
    are enabled. The lifecycle chamber is disabled by default because
    no lifecycle experts exist in Phase 3.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    min_quorum: int = 1
    max_staleness_ms: int = 30000
    entry_enabled: bool = True
    lifecycle_enabled: bool = False

    @field_validator("min_quorum")
    @classmethod
    def min_quorum_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("min_quorum must be >= 0")
        return v

    @field_validator("max_staleness_ms")
    @classmethod
    def max_staleness_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("max_staleness_ms must be > 0")
        return v


class ConfidenceLadderTier(BaseModel):
    """One tier in the shadow entry plan confidence ladder."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., min_length=1)
    min_confidence: float = Field(..., ge=0.0, le=1.0)
    limit_offset_bps: int = Field(..., ge=0)
    tp_offset_pct: float = Field(..., gt=0.0)
    sl_offset_pct: float = Field(..., gt=0.0)


class ShadowPlanConfig(BaseModel):
    """Config for shadow LIMIT plan telemetry (J6-S3)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    order_type: Literal["HYPOTHETICAL_LIMIT"] = "HYPOTHETICAL_LIMIT"
    emit_all_tiers: bool = True
    actionable_tiers: List[str] = Field(default_factory=list)
    price_ref_source: Literal["verdict_context"] = "verdict_context"
    confidence_ladder: List[ConfidenceLadderTier] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_confidence_ladder(self) -> "ShadowPlanConfig":
        names: set[str] = set()
        min_confidences = [
            tier.min_confidence for tier in self.confidence_ladder]

        if min_confidences != sorted(min_confidences):
            raise ValueError(
                "confidence_ladder must be sorted ascending by min_confidence"
            )

        for tier in self.confidence_ladder:
            if tier.name in names:
                raise ValueError("confidence_ladder tier names must be unique")
            names.add(tier.name)

        if self.enabled and not self.confidence_ladder:
            raise ValueError(
                "shadow_plan.enabled=true requires non-empty confidence_ladder"
            )

        if self.actionable_tiers:
            invalid_tiers = [t for t in self.actionable_tiers if t not in names]
            if invalid_tiers:
                raise ValueError(
                    f"actionable_tiers {invalid_tiers} not found in confidence_ladder"
                )

        return self


class VerdictConfig(BaseModel):
    """Config for verdict assembly (Phase 4).

    Controls which verdict paths are enabled and provides static context
    for envelope provenance. split_confidence_discount controls how much
    SPLIT consensus degrades verdict confidence.

    Authority: docs/LLM_JUDGE/LLM_JUDGE_PHASE4_IMPLEMENTATION_BLUEPRINT.md §15.2
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_enabled: bool = True
    lifecycle_enabled: bool = False
    strategy_id: str = "aurora"
    cortex_version: str = "phase4_shadow_v1"
    split_confidence_discount: float = 0.5
    shadow_plan: Optional[ShadowPlanConfig] = None

    @field_validator("split_confidence_discount")
    @classmethod
    def split_confidence_in_range(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError(
                "split_confidence_discount must be in [0.0, 1.0]"
            )
        return v


class JudgeCortexConfig(BaseModel):
    """Judge operational mode configuration.

    Phase 1 admits only mode='off'.
    Phase 2 admits 'off' and 'shadow'.
    Phase 3 adds chamber aggregation config.
    Phase 4 adds verdict assembly config with cross-config invariant.
    Any other mode is rejected at validation time with a clear error message.
    The full CortexMode Literal type is preserved so that schemas and
    documentation reflect the complete vocabulary.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    mode: CortexMode = "off"
    experts: Optional[JudgeExpertsConfig] = None
    shadow_log: Optional[JudgeShadowLogConfig] = None
    chamber: Optional[ChamberConfig] = None
    verdict: Optional[VerdictConfig] = None
    simulator: Optional[ShadowSimulatorConfig] = None

    @model_validator(mode="after")
    def validate_phase2_mode_admission(self) -> "JudgeCortexConfig":
        """Phase 2 admits 'off' and 'shadow'. Later phases widen admission."""
        admitted = {"off", "shadow"}
        if self.mode not in admitted:
            raise ValueError(
                f"Judge mode '{self.mode}' is not admitted in the current "
                f"phase. Only {sorted(admitted)} are allowed."
            )
        return self

    @model_validator(mode="after")
    def validate_verdict_subset_of_chamber(self) -> "JudgeCortexConfig":
        """Verdict path must not be wider than chamber path.

        verdict.entry_enabled requires chamber.entry_enabled.
        verdict.lifecycle_enabled requires chamber.lifecycle_enabled.
        Violation is a config load error (fail-closed), not a runtime no-op.

        Authority: docs/LLM_JUDGE/LLM_JUDGE_PHASE4_IMPLEMENTATION_BLUEPRINT.md §15.5
        """
        if self.verdict is not None and self.chamber is None:
            raise ValueError(
                "verdict config requires chamber config to be present"
            )
        if self.verdict is not None and self.chamber is not None:
            if self.verdict.entry_enabled and not self.chamber.entry_enabled:
                raise ValueError(
                    "verdict.entry_enabled=true requires "
                    "chamber.entry_enabled=true"
                )
            if self.verdict.lifecycle_enabled and not self.chamber.lifecycle_enabled:
                raise ValueError(
                    "verdict.lifecycle_enabled=true requires "
                    "chamber.lifecycle_enabled=true"
                )
        return self
