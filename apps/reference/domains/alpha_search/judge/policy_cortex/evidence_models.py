"""
J6-S16 — Surface Evidence Registry: Pydantic Models

Typed models for surface evidence records and the policy classifier output.

Authority: J6-S16 task specification.
SSOT: Pydantic-first; JSON schema in schemas/ kept in sync.

Shadow-only. No advisory, action, or production authority.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ──────────────────────────────────────────────────────────────
# Surface label vocabulary (derived from J6-S15 report §12)
# ──────────────────────────────────────────────────────────────

SurfaceLabel = Literal[
    "REJECTED",
    "FRAGILE",
    "PROMISING_BUT_CONCENTRATED",
    "INSUFFICIENT_SAMPLE",
    "UNKNOWN",
]

# ──────────────────────────────────────────────────────────────
# Policy classifier output vocabulary
# ──────────────────────────────────────────────────────────────

PolicyClassifierOutput = Literal[
    "ALLOW_SHADOW",
    "TRACK_ONLY",
    "REJECT_SURFACE",
    "SUPPRESS",
    "UNKNOWN",
    "NEEDS_MORE_EVIDENCE",
]


# ──────────────────────────────────────────────────────────────
# Surface Evidence Record
# ──────────────────────────────────────────────────────────────

class SurfaceEvidenceRecord(BaseModel):
    """Typed evidence summary for one analytically identified surface.

    Populated from J6-S15 held-out validation artifacts.
    Fields absent in original evidence are explicitly marked None.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Identifying key
    surface_key: str = Field(..., min_length=1)

    # Stability label (from J6-S15 §12)
    label: SurfaceLabel

    # Sample metrics
    sample_size: int = Field(..., ge=0)
    filled_count: int = Field(..., ge=0)
    avg_net_pnl: Optional[float] = None          # base avg net pnl %
    median_net_pnl: Optional[float] = None
    ci_low: Optional[float] = None               # 95% bootstrap CI lower bound
    ci_high: Optional[float] = None              # 95% bootstrap CI upper bound

    # Chronological split evidence
    early_avg_net_pnl: Optional[float] = None    # early_70 avg
    late_avg_net_pnl: Optional[float] = None     # late_30 avg

    # Concentration flags
    one_symbol_share_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    one_tf_share_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    one_side_share_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    one_day_share_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)

    # Regime / structure completeness
    regime_completeness: Optional[str] = None    # "complete" or "incomplete" or None

    # Surface composition fields (may be None if not available in evidence)
    regime: Optional[str] = None
    side: Optional[str] = None
    symbol_group: Optional[str] = None          # e.g. "ETH/PEPE", "all_symbols"
    tier_family: Optional[str] = None           # e.g. "high_only", "medium_high"

    # Edge sensitivity
    edge_sensitivity: Optional[str] = None      # "LOW_EDGE_SENSITIVITY" | "MATERIAL_EDGE_SENSITIVITY"

    # Provenance
    source_artifact: str = Field(..., min_length=1)
    evidence_version: str = Field(..., min_length=1)
    generated_at: Optional[str] = None          # ISO timestamp of artifact generation
    loaded_at: Optional[str] = None             # ISO timestamp of registry load

    # Limitations / caveats
    limitations: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_filled_le_sample(self) -> "SurfaceEvidenceRecord":
        """filled_count must not exceed sample_size."""
        if self.filled_count > self.sample_size:
            raise ValueError(
                f"filled_count ({self.filled_count}) must be <= "
                f"sample_size ({self.sample_size})"
            )
        return self


# ──────────────────────────────────────────────────────────────
# Policy Classifier Result
# ──────────────────────────────────────────────────────────────

class PolicyClassifierResult(BaseModel):
    """Output of the deterministic shadow policy classifier.

    Shadow-only. authority_mode is always 'shadow'.
    applied=False and advisory=False are invariants.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    classifier_output: PolicyClassifierOutput
    reason_codes: List[str] = Field(..., min_length=1)
    matched_surface_key: Optional[str] = None
    matched_surface_label: Optional[SurfaceLabel] = None
    evidence_version: Optional[str] = None
    source_artifact: Optional[str] = None
    limitations: List[str] = Field(default_factory=list)

    # Safety invariants — always shadow
    authority_mode: Literal["shadow"] = "shadow"
    applied: Literal[False] = False
    advisory: Literal[False] = False
    production_authority: Literal[False] = False


# ──────────────────────────────────────────────────────────────
# Policy Cortex Annotation (attached to verdict telemetry)
# ──────────────────────────────────────────────────────────────

class PolicyCortexAnnotation(BaseModel):
    """Shadow policy cortex annotation attached to a Judge verdict.

    This is the structured payload carried by
    EVT:JUDGE_POLICY_CORTEX_EVALUATED_V1 and also inline in
    JudgeVerdict extensions.

    Shadow-only. Must not change execution behaviour.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Cycle identity (matches JudgeVerdict.cycle_key)
    cycle_key: Optional[str] = None
    symbol: str = Field(..., min_length=1)
    side: Optional[str] = None
    regime: Optional[str] = None
    tf_sec: int = Field(..., gt=0)
    tier: Optional[str] = None
    strategy_id: Optional[str] = None

    # Surface evidence lookup
    surface_key: str = Field(..., min_length=1)
    matched_surface_label: Optional[SurfaceLabel] = None

    # Classifier decision
    classifier_output: PolicyClassifierOutput
    reason_codes: List[str] = Field(..., min_length=1)
    final_shadow_policy: PolicyClassifierOutput

    # Concentration flags from matched evidence
    concentration_flags: List[str] = Field(default_factory=list)

    # Sample context
    sample_size: Optional[int] = None
    avg_net_pnl: Optional[float] = None
    late_avg_net_pnl: Optional[float] = None
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None

    # Evidence provenance
    evidence_registry_version: Optional[str] = None
    source_artifact: Optional[str] = None

    # Safety invariants
    authority_mode: Literal["shadow"] = "shadow"
    applied: Literal[False] = False
    advisory: Literal[False] = False
    production_authority: Literal[False] = False

    schema_version: Literal["1"] = "1"
