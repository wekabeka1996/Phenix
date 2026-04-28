"""
LLM Judge Phase 1 — Typed Contracts

Canonical contract models for the LLM Judge bicameral policy cortex.
Authority: docs/LLM_JUDGE/LLM_Judge_Bicameral_Policy_Cortex_Concept_v1.md

Phase 1 scope: type surface only. No runtime evaluation. No event emission.

SSOT: Pydantic-first. JSON schemas kept in sync manually
      (cross-validated by test_serialization.py).
"""

from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.reference.domains.alpha_search.judge.identity import (
    build_cycle_key,
    build_expert_cycle_key,
)


def _maybe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _expected_expert_cycle_key(values: dict[str, Any]) -> Optional[str]:
    symbol = values.get("symbol")
    tf_sec = _maybe_int(values.get("tf_sec"))
    ts_ms = _maybe_int(values.get("ts_ms"))
    if symbol is None or tf_sec is None or ts_ms is None:
        return None
    entry_verdict = values.get("entry_verdict")
    lifecycle_verdict = values.get("lifecycle_verdict")
    if entry_verdict is None and lifecycle_verdict is None:
        return None
    return build_expert_cycle_key(
        entry_verdict=entry_verdict,
        lifecycle_verdict=lifecycle_verdict,
        symbol=str(symbol),
        tf_sec=tf_sec,
        ts_ms=ts_ms,
    )


def _expected_scope_cycle_key(values: dict[str, Any]) -> Optional[str]:
    verdict_scope = values.get("verdict_scope")
    symbol = values.get("symbol")
    tf_sec = _maybe_int(values.get("tf_sec"))
    ts_ms = _maybe_int(values.get("ts_ms"))
    if verdict_scope is None or symbol is None or tf_sec is None or ts_ms is None:
        return None
    return build_cycle_key(
        str(verdict_scope),
        str(symbol),
        tf_sec,
        ts_ms,
    )


def _expected_shadow_entry_plan_cycle_key(
    values: dict[str, Any],
) -> Optional[str]:
    symbol = values.get("symbol")
    tf_sec = _maybe_int(values.get("tf_sec"))
    ts_ms = _maybe_int(values.get("ts_ms"))
    if symbol is None or tf_sec is None or ts_ms is None:
        return None
    return build_cycle_key("ENTRY", str(symbol), tf_sec, ts_ms)


def _ensure_cycle_key(
    values: Any,
    *,
    expected: Optional[str],
    model_name: str,
) -> Any:
    if not isinstance(values, dict) or expected is None:
        return values

    cycle_key = values.get("cycle_key")
    if cycle_key is None:
        updated = dict(values)
        updated["cycle_key"] = expected
        return updated

    if str(cycle_key) != expected:
        raise ValueError(
            f"{model_name}.cycle_key must equal canonical cycle identity "
            f"'{expected}'"
        )
    return values


# ---------------------------------------------------------------------------
# Canonical vocabulary types (frozen by concept authority)
# ---------------------------------------------------------------------------

EntryVerdict = Literal["OPEN_LONG", "OPEN_SHORT",
                       "NO_ENTRY", "SUPPRESS", "UNKNOWN"]

LifecycleVerdict = Literal["HOLD", "PROTECT", "EXIT", "SUPPRESS", "UNKNOWN"]

CortexMode = Literal[
    "off",
    "shadow",
    "hybrid_advisory",
    "guarded_entry_authority",
    "guarded_lifecycle_authority",
]


# ---------------------------------------------------------------------------
# Supporting sub-models
# ---------------------------------------------------------------------------

class PositionContextSnapshot(BaseModel):
    """Current position state for lifecycle evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    has_position: bool
    side: Optional[Literal["LONG", "SHORT"]] = None
    unrealized_pnl_pct: Optional[float] = None
    hold_duration_sec: Optional[int] = Field(default=None, ge=0)
    bracket_state: Optional[Literal["ACTIVE", "PENDING", "NONE"]] = None


class EnvelopeProvenance(BaseModel):
    """Traceability metadata for evidence assembly."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cortex_version: str = Field(..., min_length=1)
    prompt_template_id: Optional[str] = None  # Phase 2+
    model_version: Optional[str] = None  # Phase 2+
    assembly_source: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# ExpertOutput
# ---------------------------------------------------------------------------

class ExpertOutput(BaseModel):
    """Typed output from one expert perspective on a trading decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expert_id: str = Field(..., min_length=1)
    expert_version: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    tf_sec: int = Field(..., gt=0)
    ts_ms: int = Field(..., gt=0)
    cycle_key: Optional[str] = Field(default=None, min_length=1)
    entry_verdict: Optional[EntryVerdict] = None
    lifecycle_verdict: Optional[LifecycleVerdict] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    signal_direction: Optional[Literal["LONG", "SHORT", "NEUTRAL"]] = None
    reasoning: List[str] = Field(..., min_length=1)
    schema_version: Literal["1"] = "1"

    @model_validator(mode="before")
    @classmethod
    def populate_cycle_key(cls, values: Any) -> Any:
        return _ensure_cycle_key(
            values,
            expected=_expected_expert_cycle_key(values)
            if isinstance(values, dict)
            else None,
            model_name="ExpertOutput",
        )

    @model_validator(mode="after")
    def validate_verdict_xor(self) -> ExpertOutput:
        """Exactly one of entry_verdict or lifecycle_verdict must be set."""
        has_entry = self.entry_verdict is not None
        has_lifecycle = self.lifecycle_verdict is not None
        if has_entry == has_lifecycle:
            raise ValueError(
                "ExpertOutput requires exactly one of entry_verdict or "
                "lifecycle_verdict to be set (XOR)"
            )
        return self

    @model_validator(mode="after")
    def validate_suppress_reason(self) -> ExpertOutput:
        """SUPPRESS verdict requires reasoning (already enforced by min_length=1,
        but this makes the semantic intent explicit)."""
        verdict = self.entry_verdict or self.lifecycle_verdict
        if verdict == "SUPPRESS" and len(self.reasoning) < 1:
            raise ValueError(
                "SUPPRESS verdict requires at least one reasoning item"
            )
        return self


# ---------------------------------------------------------------------------
# ChamberAggregate
# ---------------------------------------------------------------------------

class ChamberAggregate(BaseModel):
    """Aggregation of all expert outputs for one evaluation cycle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chamber_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    tf_sec: int = Field(..., gt=0)
    ts_ms: int = Field(..., gt=0)
    cycle_key: Optional[str] = Field(default=None, min_length=1)
    verdict_scope: Literal["ENTRY", "LIFECYCLE"]
    expert_outputs: List[ExpertOutput] = Field(default_factory=list)
    expert_count: int = Field(..., ge=0)
    responding_count: int = Field(..., ge=0)
    abstaining_count: int = Field(..., ge=0)
    consensus_direction: Optional[Literal["LONG",
                                          "SHORT", "NEUTRAL", "SPLIT"]] = None
    consensus_strength: float = Field(..., ge=0.0, le=1.0)
    admissibility: Literal["ADMISSIBLE", "INADMISSIBLE", "QUORUM_INSUFFICIENT"]
    admissibility_reason: Optional[str] = None
    schema_version: Literal["1"] = "1"

    @model_validator(mode="before")
    @classmethod
    def populate_cycle_key(cls, values: Any) -> Any:
        return _ensure_cycle_key(
            values,
            expected=_expected_scope_cycle_key(values)
            if isinstance(values, dict)
            else None,
            model_name="ChamberAggregate",
        )

    @model_validator(mode="after")
    def validate_counts(self) -> ChamberAggregate:
        """responding_count + abstaining_count <= expert_count."""
        if self.responding_count + self.abstaining_count > self.expert_count:
            raise ValueError(
                f"responding_count ({self.responding_count}) + "
                f"abstaining_count ({self.abstaining_count}) must be <= "
                f"expert_count ({self.expert_count})"
            )
        return self

    @model_validator(mode="after")
    def validate_expert_output_scope(self) -> ChamberAggregate:
        """All expert_outputs must match the chamber's verdict_scope."""
        for eo in self.expert_outputs:
            if self.verdict_scope == "ENTRY" and eo.entry_verdict is None:
                raise ValueError(
                    f"ENTRY chamber contains expert output from "
                    f"'{eo.expert_id}' without entry_verdict"
                )
            if self.verdict_scope == "LIFECYCLE" and eo.lifecycle_verdict is None:
                raise ValueError(
                    f"LIFECYCLE chamber contains expert output from "
                    f"'{eo.expert_id}' without lifecycle_verdict"
                )
        return self

    @model_validator(mode="after")
    def validate_admissibility_reason(self) -> ChamberAggregate:
        """Fail-closed chamber states must carry an explicit reason."""
        if self.admissibility != "ADMISSIBLE" and not self.admissibility_reason:
            raise ValueError(
                "Non-ADMISSIBLE chamber states require admissibility_reason"
            )
        return self


# ---------------------------------------------------------------------------
# JudgeEvidenceEnvelope
# ---------------------------------------------------------------------------

class JudgeEvidenceEnvelope(BaseModel):
    """Typed, bounded, timestamped evidence package for judge evaluation.

    Design note: Does NOT duplicate transport-envelope metadata (rid, span_id,
    ts, why, idempotent_key, mode) already carried by vfoundation Message.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    envelope_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    tf_sec: int = Field(..., gt=0)
    ts_ms: int = Field(..., gt=0)
    cycle_key: Optional[str] = Field(default=None, min_length=1)
    verdict_scope: Literal["ENTRY", "LIFECYCLE"]
    chamber_aggregate: ChamberAggregate
    strategy_id: str = Field(..., min_length=1)
    regime: Optional[str] = None
    regime_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    features_ref: Optional[str] = None
    position_context: Optional[PositionContextSnapshot] = None
    freshness_deadline_ms: int = Field(..., gt=0)
    provenance: EnvelopeProvenance
    schema_version: Literal["1"] = "1"

    @model_validator(mode="before")
    @classmethod
    def populate_cycle_key(cls, values: Any) -> Any:
        return _ensure_cycle_key(
            values,
            expected=_expected_scope_cycle_key(values)
            if isinstance(values, dict)
            else None,
            model_name="JudgeEvidenceEnvelope",
        )

    @model_validator(mode="after")
    def validate_lifecycle_requires_position(self) -> JudgeEvidenceEnvelope:
        """LIFECYCLE scope requires position_context."""
        if self.verdict_scope == "LIFECYCLE" and self.position_context is None:
            raise ValueError(
                "verdict_scope='LIFECYCLE' requires position_context to be set"
            )
        return self

    @model_validator(mode="after")
    def validate_scope_consistency(self) -> JudgeEvidenceEnvelope:
        """chamber_aggregate.verdict_scope must match envelope verdict_scope."""
        if self.chamber_aggregate.verdict_scope != self.verdict_scope:
            raise ValueError(
                f"Envelope verdict_scope '{self.verdict_scope}' does not match "
                f"chamber_aggregate verdict_scope "
                f"'{self.chamber_aggregate.verdict_scope}'"
            )
        return self


# ---------------------------------------------------------------------------
# JudgeVerdict
# ---------------------------------------------------------------------------

class JudgeVerdict(BaseModel):
    """Final judge policy verdict for a specific evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict_id: str = Field(..., min_length=1)
    envelope_id: str = Field(..., min_length=1)
    chamber_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    tf_sec: int = Field(..., gt=0)
    ts_ms: int = Field(..., gt=0)
    cycle_key: Optional[str] = Field(default=None, min_length=1)
    verdict_scope: Literal["ENTRY", "LIFECYCLE"]
    entry_verdict: Optional[EntryVerdict] = None
    lifecycle_verdict: Optional[LifecycleVerdict] = None
    suppression_reason: Optional[str] = None
    suppression_code: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: List[str] = Field(..., min_length=1)
    dissent_noted: bool
    authority_mode: CortexMode
    applied: bool
    strategy_id: str = Field(..., min_length=1)
    schema_version: Literal["1"] = "1"

    @model_validator(mode="before")
    @classmethod
    def populate_cycle_key(cls, values: Any) -> Any:
        return _ensure_cycle_key(
            values,
            expected=_expected_scope_cycle_key(values)
            if isinstance(values, dict)
            else None,
            model_name="JudgeVerdict",
        )

    @model_validator(mode="after")
    def validate_verdict_scope_xor(self) -> JudgeVerdict:
        """Verdict-scope-consistent XOR: ENTRY requires entry_verdict,
        LIFECYCLE requires lifecycle_verdict."""
        if self.verdict_scope == "ENTRY":
            if self.entry_verdict is None:
                raise ValueError(
                    "verdict_scope='ENTRY' requires entry_verdict to be set"
                )
            if self.lifecycle_verdict is not None:
                raise ValueError(
                    "verdict_scope='ENTRY' requires lifecycle_verdict to be None"
                )
        elif self.verdict_scope == "LIFECYCLE":
            if self.lifecycle_verdict is None:
                raise ValueError(
                    "verdict_scope='LIFECYCLE' requires lifecycle_verdict to be set"
                )
            if self.entry_verdict is not None:
                raise ValueError(
                    "verdict_scope='LIFECYCLE' requires entry_verdict to be None"
                )
        return self

    @model_validator(mode="after")
    def validate_suppress_requires_reason(self) -> JudgeVerdict:
        """SUPPRESS verdict requires suppression_reason."""
        verdict = self.entry_verdict or self.lifecycle_verdict
        if verdict == "SUPPRESS":
            if not self.suppression_reason:
                raise ValueError(
                    "SUPPRESS verdict requires non-empty suppression_reason"
                )
        return self

    @model_validator(mode="after")
    def validate_applied_mode_consistency(self) -> JudgeVerdict:
        """off/shadow modes require applied=False."""
        if self.authority_mode in ("off", "shadow") and self.applied:
            raise ValueError(
                f"authority_mode='{self.authority_mode}' requires applied=False"
            )
        return self


class ShadowEntryPlan(BaseModel):
    """Shadow-only LIMIT plan telemetry derived from an entry verdict."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str = Field(..., min_length=1)
    source_verdict_id: str = Field(..., min_length=1)
    source_envelope_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    tf_sec: int = Field(..., gt=0)
    ts_ms: int = Field(..., gt=0)
    cycle_key: Optional[str] = Field(default=None, min_length=1)
    authority_mode: CortexMode
    applied: bool
    shadow_only: bool
    final_entry_verdict: EntryVerdict
    suppressed: bool
    suppression_reason: Optional[str] = None
    entry_side: Optional[Literal["BUY", "SELL"]] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_tier: str = Field(..., min_length=1)
    tier_min_confidence: float = Field(..., ge=0.0, le=1.0)
    actionable: bool
    entry_price_ref: Optional[float] = Field(default=None, gt=0.0)
    limit_offset_bps: Optional[int] = Field(default=None, ge=0)
    limit_price: Optional[float] = Field(default=None, gt=0.0)
    tp_price: Optional[float] = Field(default=None, gt=0.0)
    sl_price: Optional[float] = Field(default=None, gt=0.0)
    tp_offset_pct: Optional[float] = Field(default=None, gt=0.0)
    sl_offset_pct: Optional[float] = Field(default=None, gt=0.0)
    risk_reward: Optional[float] = Field(default=None, gt=0.0)
    entry_order_type: Literal["HYPOTHETICAL_LIMIT"] = "HYPOTHETICAL_LIMIT"
    plan_reason_codes: List[str] = Field(..., min_length=1)
    strategy_id: str = Field(..., min_length=1)
    schema_version: Literal["1"] = "1"

    @model_validator(mode="before")
    @classmethod
    def populate_cycle_key(cls, values: Any) -> Any:
        return _ensure_cycle_key(
            values,
            expected=_expected_shadow_entry_plan_cycle_key(values)
            if isinstance(values, dict)
            else None,
            model_name="ShadowEntryPlan",
        )

    @model_validator(mode="after")
    def validate_shadow_posture(self) -> ShadowEntryPlan:
        if self.authority_mode != "shadow":
            raise ValueError("ShadowEntryPlan.authority_mode must be 'shadow'")
        if self.applied:
            raise ValueError("ShadowEntryPlan.applied must be False")
        if not self.shadow_only:
            raise ValueError("ShadowEntryPlan.shadow_only must be True")
        return self

    @model_validator(mode="after")
    def validate_verdict_semantics(self) -> ShadowEntryPlan:
        non_directional = {"NO_ENTRY", "SUPPRESS", "UNKNOWN"}
        expected_side = {
            "OPEN_LONG": "BUY",
            "OPEN_SHORT": "SELL",
        }.get(self.final_entry_verdict)

        if self.final_entry_verdict in non_directional:
            if not self.suppressed:
                raise ValueError(
                    "Non-directional final_entry_verdict requires suppressed=True"
                )
            if self.entry_side is not None:
                raise ValueError(
                    "Suppressed/non-directional ShadowEntryPlan requires entry_side=None"
                )
        else:
            if self.suppressed:
                raise ValueError(
                    "Directional final_entry_verdict must not be marked suppressed"
                )
            if self.entry_side != expected_side:
                raise ValueError(
                    "Directional final_entry_verdict requires matching entry_side"
                )
        return self

    @model_validator(mode="after")
    def validate_price_constraints(self) -> ShadowEntryPlan:
        derived_prices = (self.limit_price, self.tp_price, self.sl_price)
        if self.suppressed:
            if self.entry_price_ref is not None or any(
                value is not None for value in derived_prices
            ):
                raise ValueError(
                    "Suppressed ShadowEntryPlan requires entry_price_ref/price fields to be null"
                )
            return self

        if self.entry_price_ref is None and any(
            value is not None for value in derived_prices
        ):
            raise ValueError(
                "Derived prices require entry_price_ref to be set"
            )

        if self.actionable and self.entry_price_ref is None:
            raise ValueError(
                "Actionable ShadowEntryPlan requires entry_price_ref to be set"
            )

        return self
