"""
LLM Judge Phase 4 — Verdict Synthesizer Tests

Tests synthesize_verdict() deterministic mapping for entry and lifecycle
scopes, dissent detection, confidence discounting, shadow posture.

Authority: docs/LLM_JUDGE/LLM_JUDGE_PHASE4_IMPLEMENTATION_BLUEPRINT.md §14, §16
"""

import pytest

from apps.reference.domains.alpha_search.judge.config_models import (
    ChamberConfig,
    VerdictConfig,
)
from apps.reference.domains.alpha_search.judge.contracts import (
    ChamberAggregate,
    ExpertOutput,
    JudgeEvidenceEnvelope,
    JudgeVerdict,
    PositionContextSnapshot,
)
from apps.reference.domains.alpha_search.judge.envelope import (
    assemble_evidence_envelope,
)
from apps.reference.domains.alpha_search.judge.verdict import synthesize_verdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VERDICT_CFG = VerdictConfig()
_CHAMBER_CFG = ChamberConfig()


def _make_expert_output(
    expert_id: str = "judge.test_v1",
    symbol: str = "BTCUSDT",
    entry_verdict: str = "OPEN_LONG",
    confidence: float = 0.8,
    signal_direction: str = "LONG",
) -> ExpertOutput:
    return ExpertOutput(
        expert_id=expert_id,
        expert_version="1.0.0",
        symbol=symbol,
        tf_sec=300,
        ts_ms=1000000,
        entry_verdict=entry_verdict,
        lifecycle_verdict=None,
        confidence=confidence,
        signal_direction=signal_direction,
        reasoning=["test"],
    )


def _make_entry_envelope(
    admissibility: str = "ADMISSIBLE",
    admissibility_reason: str | None = None,
    consensus_direction: str = "LONG",
    consensus_strength: float = 0.8,
    expert_outputs=None,
    symbol: str = "BTCUSDT",
    ts_ms: int = 1000000,
) -> JudgeEvidenceEnvelope:
    if expert_outputs is None:
        expert_outputs = [_make_expert_output(symbol=symbol)]
    chamber = ChamberAggregate(
        chamber_id=f"entry_{symbol}_{ts_ms}",
        symbol=symbol,
        tf_sec=300,
        ts_ms=ts_ms,
        verdict_scope="ENTRY",
        expert_outputs=expert_outputs,
        expert_count=len(expert_outputs),
        responding_count=len(expert_outputs),
        abstaining_count=0,
        consensus_direction=consensus_direction,
        consensus_strength=consensus_strength,
        admissibility=admissibility,
        admissibility_reason=admissibility_reason,
    )
    return assemble_evidence_envelope(
        chamber,
        verdict_config=_VERDICT_CFG,
        chamber_config=_CHAMBER_CFG,
    )


def _make_lifecycle_envelope(
    admissibility: str = "QUORUM_INSUFFICIENT",
    admissibility_reason: str | None = "responding_below_min_quorum",
    ts_ms: int = 1000000,
) -> JudgeEvidenceEnvelope:
    chamber = ChamberAggregate(
        chamber_id=f"lifecycle_BTCUSDT_{ts_ms}",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=ts_ms,
        verdict_scope="LIFECYCLE",
        expert_outputs=[],
        expert_count=0,
        responding_count=0,
        abstaining_count=0,
        consensus_direction=None,
        consensus_strength=0.0,
        admissibility=admissibility,
        admissibility_reason=admissibility_reason,
    )
    return assemble_evidence_envelope(
        chamber,
        verdict_config=_VERDICT_CFG,
        chamber_config=_CHAMBER_CFG,
    )


# ---------------------------------------------------------------------------
# Entry Verdict Tests
# ---------------------------------------------------------------------------

class TestEntryVerdictMapping:
    def test_admissible_long_open_long(self):
        env = _make_entry_envelope(consensus_direction="LONG")
        v = synthesize_verdict(env, verdict_config=_VERDICT_CFG)
        assert isinstance(v, JudgeVerdict)
        assert v.entry_verdict == "OPEN_LONG"
        assert v.confidence == 0.8
        assert "chamber_consensus:LONG" in v.reasoning

    def test_admissible_short_open_short(self):
        eo = _make_expert_output(
            entry_verdict="OPEN_SHORT",
            signal_direction="SHORT",
            confidence=0.7,
        )
        env = _make_entry_envelope(
            consensus_direction="SHORT",
            consensus_strength=0.7,
            expert_outputs=[eo],
        )
        v = synthesize_verdict(env, verdict_config=_VERDICT_CFG)
        assert v.entry_verdict == "OPEN_SHORT"
        assert v.confidence == 0.7

    def test_admissible_neutral_no_entry(self):
        eo = _make_expert_output(
            entry_verdict="NO_ENTRY",
            signal_direction="NEUTRAL",
            confidence=0.5,
        )
        env = _make_entry_envelope(
            consensus_direction="NEUTRAL",
            consensus_strength=0.5,
            expert_outputs=[eo],
        )
        v = synthesize_verdict(env, verdict_config=_VERDICT_CFG)
        assert v.entry_verdict == "NO_ENTRY"

    def test_admissible_split_no_entry_with_dissent_discount(self):
        eo1 = _make_expert_output(
            expert_id="e1",
            entry_verdict="OPEN_LONG",
            signal_direction="LONG",
            confidence=0.8,
        )
        eo2 = _make_expert_output(
            expert_id="e2",
            entry_verdict="OPEN_SHORT",
            signal_direction="SHORT",
            confidence=0.8,
        )
        env = _make_entry_envelope(
            consensus_direction="SPLIT",
            consensus_strength=0.8,
            expert_outputs=[eo1, eo2],
        )
        v = synthesize_verdict(env, verdict_config=_VERDICT_CFG)
        assert v.entry_verdict == "NO_ENTRY"
        assert v.confidence == 0.8 * 0.5  # default discount
        assert v.dissent_noted is True
        assert "dissent_downweight" in v.reasoning

    def test_split_custom_discount(self):
        eo1 = _make_expert_output(expert_id="e1", signal_direction="LONG")
        eo2 = _make_expert_output(
            expert_id="e2",
            entry_verdict="OPEN_SHORT",
            signal_direction="SHORT",
        )
        env = _make_entry_envelope(
            consensus_direction="SPLIT",
            consensus_strength=1.0,
            expert_outputs=[eo1, eo2],
        )
        cfg = VerdictConfig(split_confidence_discount=0.3)
        v = synthesize_verdict(env, verdict_config=cfg)
        assert v.confidence == pytest.approx(0.3)

    def test_admissible_none_direction_unknown(self):
        env = _make_entry_envelope(
            consensus_direction=None,
            consensus_strength=0.0,
            expert_outputs=[_make_expert_output(
                entry_verdict="UNKNOWN", confidence=0.0, signal_direction=None,
            )],
        )
        v = synthesize_verdict(env, verdict_config=_VERDICT_CFG)
        assert v.entry_verdict == "UNKNOWN"
        assert v.confidence == 0.0
        assert "no_consensus_direction" in v.reasoning

    def test_inadmissible_suppress(self):
        env = _make_entry_envelope(
            admissibility="INADMISSIBLE",
            admissibility_reason="solicited_expert_missing_output",
        )
        v = synthesize_verdict(env, verdict_config=_VERDICT_CFG)
        assert v.entry_verdict == "SUPPRESS"
        assert v.confidence == 0.0
        assert "entry_chamber_inadmissible:solicited_expert_missing_output" in v.reasoning
        assert v.suppression_reason == "entry_chamber_inadmissible:solicited_expert_missing_output"
        assert v.suppression_code == "ENTRY_CHAMBER_MISSING_OUTPUT"

    def test_quorum_insufficient_unknown(self):
        env = _make_entry_envelope(
            admissibility="QUORUM_INSUFFICIENT",
            admissibility_reason="responding_below_min_quorum",
            consensus_direction=None,
            consensus_strength=0.0,
            expert_outputs=[_make_expert_output(
                entry_verdict="UNKNOWN", confidence=0.0, signal_direction=None,
            )],
        )
        v = synthesize_verdict(env, verdict_config=_VERDICT_CFG)
        assert v.entry_verdict == "UNKNOWN"
        assert v.confidence == 0.0
        assert "quorum_insufficient" in v.reasoning
        assert "admissibility_reason:responding_below_min_quorum" in v.reasoning


class TestEntryVerdictMetadata:
    def test_verdict_id_format(self):
        env = _make_entry_envelope(symbol="ETHUSDT", ts_ms=7777777)
        v = synthesize_verdict(env, verdict_config=_VERDICT_CFG)
        assert v.verdict_id == "vrd_entry_ETHUSDT_7777777"
        assert v.cycle_key == "ENTRY:ETHUSDT:300:7777777"

    def test_shadow_applied_false(self):
        env = _make_entry_envelope()
        v = synthesize_verdict(env, verdict_config=_VERDICT_CFG)
        assert v.authority_mode == "shadow"
        assert v.applied is False

    def test_envelope_id_linked(self):
        env = _make_entry_envelope()
        v = synthesize_verdict(env, verdict_config=_VERDICT_CFG)
        assert v.envelope_id == env.envelope_id

    def test_chamber_id_linked(self):
        env = _make_entry_envelope()
        v = synthesize_verdict(env, verdict_config=_VERDICT_CFG)
        assert v.chamber_id == env.chamber_aggregate.chamber_id

    def test_strategy_id_from_config(self):
        env = _make_entry_envelope()
        cfg = VerdictConfig(strategy_id="custom")
        v = synthesize_verdict(env, verdict_config=cfg)
        assert v.strategy_id == "custom"

    def test_suppression_none_for_admissible_entry(self):
        env = _make_entry_envelope()
        v = synthesize_verdict(env, verdict_config=_VERDICT_CFG)
        assert v.suppression_reason is None
        assert v.suppression_code is None

    def test_lifecycle_verdict_none_for_entry(self):
        env = _make_entry_envelope()
        v = synthesize_verdict(env, verdict_config=_VERDICT_CFG)
        assert v.lifecycle_verdict is None


class TestEntryDissentDetection:
    def test_no_dissent_unanimous(self):
        eo1 = _make_expert_output(expert_id="e1", signal_direction="LONG")
        eo2 = _make_expert_output(expert_id="e2", signal_direction="LONG")
        env = _make_entry_envelope(
            consensus_direction="LONG",
            expert_outputs=[eo1, eo2],
        )
        v = synthesize_verdict(env, verdict_config=_VERDICT_CFG)
        assert v.dissent_noted is False

    def test_dissent_when_expert_disagrees(self):
        eo1 = _make_expert_output(
            expert_id="e1",
            entry_verdict="OPEN_LONG",
            signal_direction="LONG",
        )
        eo2 = _make_expert_output(
            expert_id="e2",
            entry_verdict="OPEN_SHORT",
            signal_direction="SHORT",
            confidence=0.3,
        )
        env = _make_entry_envelope(
            consensus_direction="LONG",
            consensus_strength=0.8,
            expert_outputs=[eo1, eo2],
        )
        v = synthesize_verdict(env, verdict_config=_VERDICT_CFG)
        assert v.dissent_noted is True


# ---------------------------------------------------------------------------
# Lifecycle Verdict Tests
# ---------------------------------------------------------------------------

class TestLifecycleVerdict:
    def test_lifecycle_quorum_insufficient_unknown(self):
        env = _make_lifecycle_envelope(admissibility="QUORUM_INSUFFICIENT")
        v = synthesize_verdict(env, verdict_config=_VERDICT_CFG)
        assert v.verdict_scope == "LIFECYCLE"
        assert v.lifecycle_verdict == "UNKNOWN"
        assert v.confidence == 0.0
        assert v.dissent_noted is False
        assert v.authority_mode == "shadow"
        assert v.applied is False
        assert v.entry_verdict is None

    def test_lifecycle_verdict_id_format(self):
        env = _make_lifecycle_envelope(ts_ms=8888888)
        v = synthesize_verdict(env, verdict_config=_VERDICT_CFG)
        assert v.verdict_id == "vrd_lifecycle_BTCUSDT_8888888"
        assert v.cycle_key == "LIFECYCLE:BTCUSDT:300:8888888"
