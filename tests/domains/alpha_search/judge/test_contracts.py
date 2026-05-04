"""
LLM Judge Phase 1 — Contract Validation Tests

Tests Pydantic contract models for ExpertOutput, ChamberAggregate,
JudgeEvidenceEnvelope, JudgeVerdict, and supporting sub-models.
"""

import pytest

from apps.reference.domains.alpha_search.judge.contracts import (
    ChamberAggregate,
    EnvelopeProvenance,
    ExpertOutput,
    JudgeEvidenceEnvelope,
    JudgeVerdict,
    PositionContextSnapshot,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_expert_output(**overrides):
    defaults = dict(
        expert_id="ta_expert_v1",
        expert_version="1.0.0",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=1712000000000,
        entry_verdict="OPEN_LONG",
        lifecycle_verdict=None,
        confidence=0.85,
        signal_direction="LONG",
        reasoning=["Strong OBI signal", "Positive regime"],
        schema_version="1",
    )
    defaults.update(overrides)
    return ExpertOutput(**defaults)


def _make_chamber_aggregate(**overrides):
    defaults = dict(
        chamber_id="ch-001",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=1712000000100,
        verdict_scope="ENTRY",
        expert_outputs=[_make_expert_output()],
        expert_count=3,
        responding_count=1,
        abstaining_count=2,
        consensus_direction="LONG",
        consensus_strength=0.7,
        admissibility="ADMISSIBLE",
        schema_version="1",
    )
    defaults.update(overrides)
    if (
        defaults["admissibility"] != "ADMISSIBLE"
        and defaults.get("admissibility_reason") is None
    ):
        defaults["admissibility_reason"] = "test_reason"
    return ChamberAggregate(**defaults)


def _make_provenance(**overrides):
    defaults = dict(
        cortex_version="0.1.0",
        assembly_source="alpha_search.judge.assembler",
    )
    defaults.update(overrides)
    return EnvelopeProvenance(**defaults)


def _make_evidence_envelope(**overrides):
    defaults = dict(
        envelope_id="env-001",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=1712000000200,
        verdict_scope="ENTRY",
        chamber_aggregate=_make_chamber_aggregate(),
        strategy_id="aurora",
        regime="TREND_UP",
        regime_confidence=0.9,
        features_ref="rid:abc123",
        position_context=None,
        freshness_deadline_ms=30000,
        provenance=_make_provenance(),
        schema_version="1",
    )
    defaults.update(overrides)
    return JudgeEvidenceEnvelope(**defaults)


def _make_judge_verdict(**overrides):
    defaults = dict(
        verdict_id="v-001",
        envelope_id="env-001",
        chamber_id="ch-001",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=1712000000300,
        verdict_scope="ENTRY",
        entry_verdict="OPEN_LONG",
        lifecycle_verdict=None,
        suppression_reason=None,
        suppression_code=None,
        confidence=0.85,
        reasoning=["Strong consensus"],
        dissent_noted=False,
        authority_mode="off",
        applied=False,
        strategy_id="aurora",
        schema_version="1",
    )
    defaults.update(overrides)
    return JudgeVerdict(**defaults)


# ---------------------------------------------------------------------------
# A. Valid construction
# ---------------------------------------------------------------------------

class TestExpertOutputValid:
    def test_valid_entry_expert(self):
        eo = _make_expert_output()
        assert eo.entry_verdict == "OPEN_LONG"
        assert eo.lifecycle_verdict is None
        assert eo.cycle_key == "ENTRY:BTCUSDT:300:1712000000000"

    def test_valid_lifecycle_expert(self):
        eo = _make_expert_output(
            entry_verdict=None, lifecycle_verdict="HOLD"
        )
        assert eo.lifecycle_verdict == "HOLD"
        assert eo.entry_verdict is None

    def test_all_entry_verdicts(self):
        for v in ["OPEN_LONG", "OPEN_SHORT", "NO_ENTRY", "SUPPRESS", "UNKNOWN"]:
            eo = _make_expert_output(
                entry_verdict=v,
                reasoning=["suppress reason"] if v == "SUPPRESS" else ["ok"],
            )
            assert eo.entry_verdict == v

    def test_all_lifecycle_verdicts(self):
        for v in ["HOLD", "PROTECT", "EXIT", "SUPPRESS", "UNKNOWN"]:
            eo = _make_expert_output(
                entry_verdict=None,
                lifecycle_verdict=v,
                reasoning=["suppress reason"] if v == "SUPPRESS" else ["ok"],
            )
            assert eo.lifecycle_verdict == v

    def test_frozen_immutability(self):
        eo = _make_expert_output()
        with pytest.raises(Exception):
            eo.confidence = 0.5


class TestChamberAggregateValid:
    def test_valid_entry_chamber(self):
        ca = _make_chamber_aggregate()
        assert ca.verdict_scope == "ENTRY"
        assert ca.admissibility == "ADMISSIBLE"
        assert ca.cycle_key == "ENTRY:BTCUSDT:300:1712000000100"

    def test_empty_expert_outputs(self):
        ca = _make_chamber_aggregate(
            expert_outputs=[],
            responding_count=0,
            admissibility="QUORUM_INSUFFICIENT",
        )
        assert len(ca.expert_outputs) == 0

    def test_all_admissibility_values(self):
        for adm in ["ADMISSIBLE", "INADMISSIBLE", "QUORUM_INSUFFICIENT"]:
            ca = _make_chamber_aggregate(admissibility=adm)
            assert ca.admissibility == adm

    def test_non_admissible_requires_reason(self):
        with pytest.raises(ValueError, match="admissibility_reason"):
            ChamberAggregate(
                chamber_id="ch-001",
                symbol="BTCUSDT",
                tf_sec=300,
                ts_ms=1712000000100,
                verdict_scope="ENTRY",
                expert_outputs=[_make_expert_output()],
                expert_count=1,
                responding_count=1,
                abstaining_count=0,
                consensus_direction="LONG",
                consensus_strength=0.7,
                admissibility="INADMISSIBLE",
                admissibility_reason=None,
                schema_version="1",
            )


class TestEvidenceEnvelopeValid:
    def test_valid_entry_envelope(self):
        env = _make_evidence_envelope()
        assert env.verdict_scope == "ENTRY"
        assert env.position_context is None
        assert env.cycle_key == "ENTRY:BTCUSDT:300:1712000000200"

    def test_valid_lifecycle_envelope(self):
        lifecycle_expert = _make_expert_output(
            entry_verdict=None, lifecycle_verdict="HOLD"
        )
        lifecycle_chamber = _make_chamber_aggregate(
            verdict_scope="LIFECYCLE",
            expert_outputs=[lifecycle_expert],
        )
        env = _make_evidence_envelope(
            verdict_scope="LIFECYCLE",
            chamber_aggregate=lifecycle_chamber,
            position_context=PositionContextSnapshot(
                has_position=True, side="LONG",
                unrealized_pnl_pct=0.5, hold_duration_sec=120,
                bracket_state="ACTIVE",
            ),
        )
        assert env.verdict_scope == "LIFECYCLE"
        assert env.position_context.has_position is True


class TestJudgeVerdictValid:
    def test_valid_entry_verdict(self):
        v = _make_judge_verdict()
        assert v.entry_verdict == "OPEN_LONG"
        assert v.lifecycle_verdict is None
        assert v.applied is False
        assert v.cycle_key == "ENTRY:BTCUSDT:300:1712000000300"

    def test_valid_lifecycle_verdict(self):
        v = _make_judge_verdict(
            verdict_scope="LIFECYCLE",
            entry_verdict=None,
            lifecycle_verdict="EXIT",
        )
        assert v.lifecycle_verdict == "EXIT"

    def test_suppress_with_reason(self):
        v = _make_judge_verdict(
            entry_verdict="SUPPRESS",
            suppression_reason="High volatility regime",
            suppression_code="HV_001",
        )
        assert v.suppression_reason == "High volatility regime"


class TestPositionContextSnapshotValid:
    def test_valid_snapshot(self):
        pc = PositionContextSnapshot(
            has_position=True, side="LONG",
            unrealized_pnl_pct=-0.5, hold_duration_sec=600,
            bracket_state="ACTIVE",
        )
        assert pc.has_position is True
        assert pc.side == "LONG"

    def test_no_position(self):
        pc = PositionContextSnapshot(has_position=False)
        assert pc.side is None


class TestEnvelopeProvenanceValid:
    def test_valid_provenance(self):
        p = _make_provenance()
        assert p.cortex_version == "0.1.0"
        assert p.prompt_template_id is None
        assert p.model_version is None


# ---------------------------------------------------------------------------
# B. XOR invariants
# ---------------------------------------------------------------------------

class TestExpertOutputXOR:
    def test_both_verdicts_set_fails(self):
        with pytest.raises(ValueError, match="XOR"):
            _make_expert_output(
                entry_verdict="OPEN_LONG",
                lifecycle_verdict="HOLD",
            )

    def test_neither_verdict_set_fails(self):
        with pytest.raises(ValueError, match="XOR"):
            _make_expert_output(
                entry_verdict=None,
                lifecycle_verdict=None,
            )


class TestJudgeVerdictXOR:
    def test_entry_scope_missing_entry_verdict(self):
        with pytest.raises(ValueError, match="entry_verdict"):
            _make_judge_verdict(
                verdict_scope="ENTRY",
                entry_verdict=None,
                lifecycle_verdict=None,
            )

    def test_entry_scope_with_lifecycle_verdict(self):
        with pytest.raises(ValueError, match="lifecycle_verdict"):
            _make_judge_verdict(
                verdict_scope="ENTRY",
                entry_verdict="OPEN_LONG",
                lifecycle_verdict="HOLD",
            )

    def test_lifecycle_scope_missing_lifecycle_verdict(self):
        with pytest.raises(ValueError, match="lifecycle_verdict"):
            _make_judge_verdict(
                verdict_scope="LIFECYCLE",
                entry_verdict=None,
                lifecycle_verdict=None,
            )

    def test_lifecycle_scope_with_entry_verdict(self):
        with pytest.raises(ValueError, match="entry_verdict"):
            _make_judge_verdict(
                verdict_scope="LIFECYCLE",
                entry_verdict="OPEN_LONG",
                lifecycle_verdict="EXIT",
            )


# ---------------------------------------------------------------------------
# C. Confidence range
# ---------------------------------------------------------------------------

class TestConfidenceRange:
    def test_negative_confidence_fails(self):
        with pytest.raises(Exception):
            _make_expert_output(confidence=-0.1)

    def test_over_1_confidence_fails(self):
        with pytest.raises(Exception):
            _make_expert_output(confidence=1.1)

    def test_boundary_0(self):
        eo = _make_expert_output(confidence=0.0)
        assert eo.confidence == 0.0

    def test_boundary_1(self):
        eo = _make_expert_output(confidence=1.0)
        assert eo.confidence == 1.0


# ---------------------------------------------------------------------------
# D. Suppression requires reason
# ---------------------------------------------------------------------------

class TestSuppressionReason:
    def test_verdict_suppress_without_reason_fails(self):
        with pytest.raises(ValueError, match="suppression_reason"):
            _make_judge_verdict(
                entry_verdict="SUPPRESS",
                suppression_reason=None,
            )

    def test_verdict_suppress_empty_reason_fails(self):
        with pytest.raises(ValueError, match="suppression_reason"):
            _make_judge_verdict(
                entry_verdict="SUPPRESS",
                suppression_reason="",
            )


# ---------------------------------------------------------------------------
# E. Count consistency on ChamberAggregate
# ---------------------------------------------------------------------------

class TestChamberCounts:
    def test_responding_plus_abstaining_exceeds_expert_count(self):
        with pytest.raises(ValueError, match="expert_count"):
            _make_chamber_aggregate(
                expert_count=3,
                responding_count=2,
                abstaining_count=2,
            )

    def test_counts_at_boundary(self):
        ca = _make_chamber_aggregate(
            expert_count=5,
            responding_count=3,
            abstaining_count=2,
        )
        assert ca.responding_count + ca.abstaining_count == ca.expert_count


# ---------------------------------------------------------------------------
# F. Verdict scope matching
# ---------------------------------------------------------------------------

class TestVerdictScopeMatching:
    def test_entry_chamber_with_lifecycle_expert_fails(self):
        lifecycle_expert = _make_expert_output(
            entry_verdict=None, lifecycle_verdict="HOLD"
        )
        with pytest.raises(ValueError, match="ENTRY chamber"):
            _make_chamber_aggregate(
                verdict_scope="ENTRY",
                expert_outputs=[lifecycle_expert],
            )

    def test_lifecycle_chamber_with_entry_expert_fails(self):
        entry_expert = _make_expert_output(
            entry_verdict="OPEN_LONG", lifecycle_verdict=None
        )
        with pytest.raises(ValueError, match="LIFECYCLE chamber"):
            _make_chamber_aggregate(
                verdict_scope="LIFECYCLE",
                expert_outputs=[entry_expert],
            )

    def test_envelope_scope_mismatch_fails(self):
        entry_chamber = _make_chamber_aggregate(verdict_scope="ENTRY")
        with pytest.raises(ValueError, match="verdict_scope"):
            _make_evidence_envelope(
                verdict_scope="LIFECYCLE",
                chamber_aggregate=entry_chamber,
                position_context=PositionContextSnapshot(
                    has_position=True, side="LONG"),
            )


# ---------------------------------------------------------------------------
# G. Lifecycle requires position context
# ---------------------------------------------------------------------------

class TestLifecycleRequiresPosition:
    def test_lifecycle_without_position_fails(self):
        lifecycle_expert = _make_expert_output(
            entry_verdict=None, lifecycle_verdict="HOLD"
        )
        lifecycle_chamber = _make_chamber_aggregate(
            verdict_scope="LIFECYCLE",
            expert_outputs=[lifecycle_expert],
        )
        with pytest.raises(ValueError, match="position_context"):
            _make_evidence_envelope(
                verdict_scope="LIFECYCLE",
                chamber_aggregate=lifecycle_chamber,
                position_context=None,
            )


# ---------------------------------------------------------------------------
# H. Applied/mode consistency
# ---------------------------------------------------------------------------

class TestAppliedModeConsistency:
    def test_off_mode_applied_true_fails(self):
        with pytest.raises(ValueError, match="applied=False"):
            _make_judge_verdict(authority_mode="off", applied=True)

    def test_shadow_mode_applied_true_fails(self):
        with pytest.raises(ValueError, match="applied=False"):
            _make_judge_verdict(authority_mode="shadow", applied=True)

    def test_off_mode_applied_false_ok(self):
        v = _make_judge_verdict(authority_mode="off", applied=False)
        assert v.applied is False


# ---------------------------------------------------------------------------
# I. Extra fields rejected
# ---------------------------------------------------------------------------

class TestExtraFieldsRejected:
    def test_expert_output_extra_field(self):
        with pytest.raises(Exception):
            _make_expert_output(unknown_field="bad")

    def test_chamber_aggregate_extra_field(self):
        with pytest.raises(Exception):
            _make_chamber_aggregate(unknown_field="bad")

    def test_judge_verdict_extra_field(self):
        with pytest.raises(Exception):
            _make_judge_verdict(unknown_field="bad")


# ---------------------------------------------------------------------------
# J. Required fields
# ---------------------------------------------------------------------------

class TestRequiredFields:
    def test_expert_missing_expert_id(self):
        with pytest.raises(Exception):
            ExpertOutput(
                expert_version="1.0.0", symbol="BTCUSDT", tf_sec=300,
                ts_ms=1712000000000, entry_verdict="NO_ENTRY",
                confidence=0.5, reasoning=["ok"], schema_version="1",
            )

    def test_expert_empty_reasoning(self):
        with pytest.raises(Exception):
            _make_expert_output(reasoning=[])

    def test_verdict_missing_reasoning(self):
        with pytest.raises(Exception):
            JudgeVerdict(
                verdict_id="v-001", envelope_id="env-001",
                chamber_id="ch-001", symbol="BTCUSDT", tf_sec=300,
                ts_ms=1712000000300, verdict_scope="ENTRY",
                entry_verdict="OPEN_LONG", confidence=0.85,
                reasoning=[], dissent_noted=False,
                authority_mode="off", applied=False,
                strategy_id="aurora", schema_version="1",
            )


class TestCycleKeyValidation:
    def test_expert_cycle_key_mismatch_fails(self):
        with pytest.raises(ValueError, match="cycle_key"):
            _make_expert_output(cycle_key="ENTRY:BTCUSDT:300:999")

    def test_chamber_cycle_key_mismatch_fails(self):
        with pytest.raises(ValueError, match="cycle_key"):
            _make_chamber_aggregate(cycle_key="ENTRY:BTCUSDT:300:999")

    def test_envelope_cycle_key_mismatch_fails(self):
        with pytest.raises(ValueError, match="cycle_key"):
            _make_evidence_envelope(cycle_key="ENTRY:BTCUSDT:300:999")

    def test_verdict_cycle_key_mismatch_fails(self):
        with pytest.raises(ValueError, match="cycle_key"):
            _make_judge_verdict(cycle_key="ENTRY:BTCUSDT:300:999")


# ---------------------------------------------------------------------------
# K. Invalid enum values
# ---------------------------------------------------------------------------

class TestInvalidEnums:
    def test_invalid_entry_verdict(self):
        with pytest.raises(Exception):
            _make_expert_output(entry_verdict="INVALID")

    def test_invalid_lifecycle_verdict(self):
        with pytest.raises(Exception):
            _make_expert_output(
                entry_verdict=None, lifecycle_verdict="INVALID"
            )

    def test_invalid_verdict_scope(self):
        with pytest.raises(Exception):
            _make_chamber_aggregate(verdict_scope="INVALID")

    def test_invalid_schema_version(self):
        with pytest.raises(Exception):
            _make_expert_output(schema_version="2")

    def test_invalid_admissibility(self):
        with pytest.raises(Exception):
            _make_chamber_aggregate(admissibility="INVALID")
