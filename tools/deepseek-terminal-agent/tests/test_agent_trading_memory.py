"""Tests for agent_trading_memory — P38D Agent Trading Session Memory.

Proves:
1. Append-only: duplicate reflection_id raises, no silent overwrite.
2. Identity enforcement: wrong session_id or agent_id raises.
3. compact_summary: correct counts and feature trust aggregation.
4. next_session_carryover_md: returns valid markdown with all sections.
5. Missing identity fields raise on model construction.
6. Token budget metadata tracking (not real tokenizer).
7. Event/trade/context ref deduplication.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from deepseek_terminal_agent.sessions.agent_trading_memory import (
    AgentTradingSessionMemory,
    FeatureTrustNote,
    ReflectionEntry,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def make_session(**kwargs) -> AgentTradingSessionMemory:
    defaults = dict(
        session_id="session-p38d-001",
        agent_id="agent-5-secondary",
        agent_number=5,
        instruction_manifest_version="p38d-v1",
    )
    defaults.update(kwargs)
    return AgentTradingSessionMemory(**defaults)


def make_reflection(
    reflection_id: str = "ref-001",
    session_id: str = "session-p38d-001",
    agent_id: str = "agent-5-secondary",
    kind: str = "opening_assumptions",
    content: str = "Assuming mean reversion holds in current regime.",
    **kwargs,
) -> ReflectionEntry:
    return ReflectionEntry(
        reflection_id=reflection_id,
        session_id=session_id,
        agent_id=agent_id,
        kind=kind,
        content=content,
        **kwargs,
    )


# ── Test: append-only — no silent overwrite ────────────────────────────────────


def test_append_reflection_is_append_only():
    mem = make_session()
    r1 = make_reflection(reflection_id="ref-001")
    mem.append_reflection(r1)
    assert len(mem.reflections) == 1
    assert "ref-001" in mem.reflection_refs

    # Appending again with same reflection_id MUST raise
    r1_dup = make_reflection(reflection_id="ref-001", content="Duplicate attempt.")
    with pytest.raises(ValueError, match="Duplicate reflection_id"):
        mem.append_reflection(r1_dup)

    # Reflections list remains unchanged
    assert len(mem.reflections) == 1


def test_append_multiple_reflections_sequentially():
    mem = make_session()
    for i in range(5):
        mem.append_reflection(make_reflection(reflection_id=f"ref-{i:03d}", content=f"Reflection {i}"))
    assert len(mem.reflections) == 5
    assert len(mem.reflection_refs) == 5
    assert mem.reflection_refs == [f"ref-{i:03d}" for i in range(5)]


# ── Test: identity enforcement ────────────────────────────────────────────────


def test_append_reflection_wrong_session_id_raises():
    mem = make_session()
    bad_ref = make_reflection(session_id="WRONG-SESSION")
    with pytest.raises(ValueError, match="session_id"):
        mem.append_reflection(bad_ref)


def test_append_reflection_wrong_agent_id_raises():
    mem = make_session()
    bad_ref = make_reflection(agent_id="WRONG-AGENT")
    with pytest.raises(ValueError, match="agent_id"):
        mem.append_reflection(bad_ref)


def test_session_missing_required_fields_raises():
    with pytest.raises(ValidationError):
        AgentTradingSessionMemory(
            agent_id="agent-5",
            agent_number=5,
            instruction_manifest_version="v1",
            # missing session_id
        )
    with pytest.raises(ValidationError):
        AgentTradingSessionMemory(
            session_id="s1",
            agent_number=5,
            instruction_manifest_version="v1",
            # missing agent_id
        )


# ── Test: token budget metadata tracking ─────────────────────────────────────


def test_token_budget_defaults():
    mem = make_session()
    assert mem.context_budget_target_tokens == 1_000_000
    assert mem.reflection_budget_target_tokens == 300_000
    assert mem.tokens_consumed_estimate == 0


def test_token_estimate_increments_on_append():
    mem = make_session()
    mem.append_reflection(make_reflection(reflection_id="ref-001"), token_estimate=5000)
    mem.append_reflection(make_reflection(reflection_id="ref-002"), token_estimate=3000)
    assert mem.tokens_consumed_estimate == 8000


def test_token_estimate_zero_does_not_increment():
    mem = make_session()
    mem.append_reflection(make_reflection(reflection_id="ref-001"), token_estimate=0)
    assert mem.tokens_consumed_estimate == 0


# ── Test: event/trade/context ref deduplication ──────────────────────────────


def test_event_ref_deduplication():
    mem = make_session()
    mem.append_event_ref("evt-001")
    mem.append_event_ref("evt-001")  # duplicate
    mem.append_event_ref("evt-002")
    assert mem.event_refs == ["evt-001", "evt-002"]


def test_trade_ref_deduplication():
    mem = make_session()
    mem.append_trade_ref("trade-A")
    mem.append_trade_ref("trade-A")
    mem.append_trade_ref("trade-B")
    assert mem.trade_refs == ["trade-A", "trade-B"]


def test_context_ref_deduplication():
    mem = make_session()
    mem.append_context_ref("ctx-snapshot-1")
    mem.append_context_ref("ctx-snapshot-1")
    assert mem.active_context_refs == ["ctx-snapshot-1"]


# ── Test: compact_summary ────────────────────────────────────────────────────


def test_compact_summary_empty_session():
    mem = make_session()
    s = mem.compact_summary()
    assert s["session_id"] == "session-p38d-001"
    assert s["agent_id"] == "agent-5-secondary"
    assert s["agent_number"] == 5
    assert s["total_reflections"] == 0
    assert s["reflection_kind_counts"] == {}
    assert s["total_event_refs"] == 0
    assert s["total_trade_refs"] == 0
    assert s["total_context_refs"] == 0
    assert s["cumulative_feature_trust_deltas"] == {}


def test_compact_summary_counts_reflections_by_kind():
    mem = make_session()
    mem.append_reflection(make_reflection(reflection_id="r1", kind="opening_assumptions"))
    mem.append_reflection(make_reflection(reflection_id="r2", kind="decision_review"))
    mem.append_reflection(make_reflection(reflection_id="r3", kind="decision_review"))
    mem.append_event_ref("evt-001")
    mem.append_trade_ref("trade-001")

    s = mem.compact_summary()
    assert s["total_reflections"] == 3
    assert s["reflection_kind_counts"]["opening_assumptions"] == 1
    assert s["reflection_kind_counts"]["decision_review"] == 2
    assert s["total_event_refs"] == 1
    assert s["total_trade_refs"] == 1


def test_compact_summary_aggregates_feature_trust():
    mem = make_session()
    note1 = FeatureTrustNote(
        feature_name="rsi_14",
        trust_delta=0.3,
        reason="Accurately predicted reversal",
        observed_effect="Price reversed after RSI divergence.",
    )
    note2 = FeatureTrustNote(
        feature_name="rsi_14",
        trust_delta=-0.1,
        reason="False signal during flat regime",
        observed_effect="No reversal despite RSI divergence.",
    )
    note3 = FeatureTrustNote(
        feature_name="volume_spike",
        trust_delta=0.5,
        reason="Confirmed breakout",
        observed_effect="Volume spike preceded 2% move.",
    )
    r1 = make_reflection(
        reflection_id="r1",
        kind="feature_trust_update",
        feature_influence_notes=[note1],
    )
    r2 = make_reflection(
        reflection_id="r2",
        kind="feature_trust_update",
        feature_influence_notes=[note2, note3],
    )
    mem.append_reflection(r1)
    mem.append_reflection(r2)

    s = mem.compact_summary()
    trust = s["cumulative_feature_trust_deltas"]
    assert abs(trust["rsi_14"] - 0.2) < 1e-9
    assert abs(trust["volume_spike"] - 0.5) < 1e-9


# ── Test: next_session_carryover_md ──────────────────────────────────────────


def test_carryover_md_is_valid_markdown():
    mem = make_session()
    mem.append_reflection(make_reflection(
        reflection_id="r1",
        kind="opening_assumptions",
        content="Mean reversion assumed valid for current regime.",
        confidence_before=0.6,
        confidence_after=0.7,
    ))
    mem.append_reflection(make_reflection(
        reflection_id="r2",
        kind="decision_review",
        content="Entry at BTCUSDT 65k was correct; exited at 66k.",
    ))
    mem.append_event_ref("evt-100")
    mem.append_trade_ref("trade-X1")

    md = mem.next_session_carryover_md()

    # Must contain identity section
    assert "session-p38d-001" in md
    assert "agent-5-secondary" in md
    assert "Agent #5" in md
    # Must contain token budget section
    assert "1,000,000" in md
    assert "300,000" in md
    # Must contain reflection breakdown
    assert "opening_assumptions" in md
    assert "decision_review" in md
    # Must contain recent reflection content
    assert "Mean reversion assumed valid" in md
    # Must contain carryover footer
    assert "Carryover generated by AgentTradingSessionMemory" in md


def test_carryover_md_shows_confidence():
    mem = make_session()
    r = make_reflection(
        reflection_id="r1",
        kind="session_self_audit",
        content="Auditing session performance.",
        confidence_before=0.4,
        confidence_after=0.75,
    )
    mem.append_reflection(r)
    md = mem.next_session_carryover_md()
    assert "0.40" in md
    assert "0.75" in md


def test_carryover_md_empty_session():
    mem = make_session()
    md = mem.next_session_carryover_md()
    assert "session-p38d-001" in md
    assert "Total reflections: 0" in md


# ── Test: FeatureTrustNote bounds ────────────────────────────────────────────


def test_feature_trust_note_bounds():
    # Valid bounds
    FeatureTrustNote(
        feature_name="rsi_14", trust_delta=1.0, reason="Max trust", observed_effect="x"
    )
    FeatureTrustNote(
        feature_name="rsi_14", trust_delta=-1.0, reason="Zero trust", observed_effect="x"
    )
    # Out of bounds
    with pytest.raises(ValidationError):
        FeatureTrustNote(
            feature_name="rsi_14", trust_delta=1.1, reason="Over max", observed_effect="x"
        )
    with pytest.raises(ValidationError):
        FeatureTrustNote(
            feature_name="rsi_14", trust_delta=-1.1, reason="Under min", observed_effect="x"
        )


# ── Test: reflection_refs_consistent model_validator ─────────────────────────


def test_model_validator_rejects_orphan_reflection_ref():
    """reflection_refs must not contain IDs absent from reflections list."""
    with pytest.raises(ValidationError, match="not found in reflections list"):
        AgentTradingSessionMemory(
            session_id="s1",
            agent_id="a1",
            agent_number=1,
            instruction_manifest_version="v1",
            reflection_refs=["orphan-id"],  # not in reflections
            reflections=[],
        )
