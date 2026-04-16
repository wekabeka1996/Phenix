"""
LLM Judge Phase 3 — Admissibility Filter Tests

Tests for evaluate_admissibility() rules:
  R1: Quorum, R2: Silent failure, R2.5: Duplicate, R3: Freshness,
  R4: Scope mismatch, R5: Default ADMISSIBLE.
"""

import pytest

from apps.reference.domains.alpha_search.judge.contracts import ExpertOutput
from apps.reference.domains.alpha_search.judge.chamber.admissibility import (
    evaluate_admissibility,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry_expert(
    expert_id: str = "judge.signal_weights_v1",
    ts_ms: int = 1700000000000,
    confidence: float = 0.85,
    entry_verdict: str = "OPEN_LONG",
    signal_direction: str = "LONG",
) -> ExpertOutput:
    return ExpertOutput(
        expert_id=expert_id,
        expert_version="1.0.0",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=ts_ms,
        entry_verdict=entry_verdict,
        lifecycle_verdict=None,
        confidence=confidence,
        signal_direction=signal_direction,
        reasoning=["test"],
        schema_version="1",
    )


CYCLE_TS = 1700000000000


# ---------------------------------------------------------------------------
# R1: Quorum
# ---------------------------------------------------------------------------

class TestAdmissibilityQuorum:
    def test_quorum_met(self):
        eo = _make_entry_expert()
        result = evaluate_admissibility(
            expert_outputs=[eo],
            responding_count=1,
            expected_expert_count=1,
            min_quorum=1,
            max_staleness_ms=30000,
            cycle_ts_ms=CYCLE_TS,
            verdict_scope="ENTRY",
        )
        assert result == "ADMISSIBLE"

    def test_quorum_insufficient_zero_responding(self):
        result = evaluate_admissibility(
            expert_outputs=[],
            responding_count=0,
            expected_expert_count=0,
            min_quorum=1,
            max_staleness_ms=30000,
            cycle_ts_ms=CYCLE_TS,
            verdict_scope="ENTRY",
        )
        assert result == "QUORUM_INSUFFICIENT"

    def test_quorum_zero_allows_everything(self):
        """min_quorum=0 means quorum is never insufficient from this rule."""
        result = evaluate_admissibility(
            expert_outputs=[],
            responding_count=0,
            expected_expert_count=0,
            min_quorum=0,
            max_staleness_ms=30000,
            cycle_ts_ms=CYCLE_TS,
            verdict_scope="ENTRY",
        )
        assert result == "ADMISSIBLE"

    def test_quorum_two_required_one_responding(self):
        eo = _make_entry_expert()
        result = evaluate_admissibility(
            expert_outputs=[eo],
            responding_count=1,
            expected_expert_count=1,
            min_quorum=2,
            max_staleness_ms=30000,
            cycle_ts_ms=CYCLE_TS,
            verdict_scope="ENTRY",
        )
        assert result == "QUORUM_INSUFFICIENT"


# ---------------------------------------------------------------------------
# R2: Silent failure
# ---------------------------------------------------------------------------

class TestAdmissibilitySilentFailure:
    def test_one_solicited_none_returned(self):
        """Expert solicited but crashed — no ExpertOutput produced."""
        result = evaluate_admissibility(
            expert_outputs=[],
            responding_count=0,
            expected_expert_count=1,
            min_quorum=0,  # skip quorum check
            max_staleness_ms=30000,
            cycle_ts_ms=CYCLE_TS,
            verdict_scope="ENTRY",
        )
        assert result == "INADMISSIBLE"

    def test_two_solicited_one_returned(self):
        """One expert returned, one silently failed."""
        eo = _make_entry_expert()
        result = evaluate_admissibility(
            expert_outputs=[eo],
            responding_count=1,
            expected_expert_count=2,
            min_quorum=1,
            max_staleness_ms=30000,
            cycle_ts_ms=CYCLE_TS,
            verdict_scope="ENTRY",
        )
        assert result == "INADMISSIBLE"

    def test_all_solicited_returned(self):
        eo1 = _make_entry_expert(expert_id="judge.signal_weights_v1")
        eo2 = _make_entry_expert(expert_id="judge.feature_neutrals_v1")
        result = evaluate_admissibility(
            expert_outputs=[eo1, eo2],
            responding_count=2,
            expected_expert_count=2,
            min_quorum=1,
            max_staleness_ms=30000,
            cycle_ts_ms=CYCLE_TS,
            verdict_scope="ENTRY",
        )
        assert result == "ADMISSIBLE"


# ---------------------------------------------------------------------------
# R2.5: Duplicate expert_id
# ---------------------------------------------------------------------------

class TestAdmissibilityDuplicate:
    def test_duplicate_expert_id_inadmissible(self):
        eo1 = _make_entry_expert(expert_id="judge.signal_weights_v1")
        eo2 = _make_entry_expert(expert_id="judge.signal_weights_v1")
        result = evaluate_admissibility(
            expert_outputs=[eo1, eo2],
            responding_count=2,
            expected_expert_count=2,
            min_quorum=1,
            max_staleness_ms=30000,
            cycle_ts_ms=CYCLE_TS,
            verdict_scope="ENTRY",
        )
        assert result == "INADMISSIBLE"

    def test_distinct_expert_ids_admissible(self):
        eo1 = _make_entry_expert(expert_id="judge.signal_weights_v1")
        eo2 = _make_entry_expert(expert_id="judge.feature_neutrals_v1")
        result = evaluate_admissibility(
            expert_outputs=[eo1, eo2],
            responding_count=2,
            expected_expert_count=2,
            min_quorum=1,
            max_staleness_ms=30000,
            cycle_ts_ms=CYCLE_TS,
            verdict_scope="ENTRY",
        )
        assert result == "ADMISSIBLE"


# ---------------------------------------------------------------------------
# R3: Freshness
# ---------------------------------------------------------------------------

class TestAdmissibilityFreshness:
    def test_stale_output_inadmissible(self):
        stale_eo = _make_entry_expert(ts_ms=CYCLE_TS - 60000)
        result = evaluate_admissibility(
            expert_outputs=[stale_eo],
            responding_count=1,
            expected_expert_count=1,
            min_quorum=1,
            max_staleness_ms=30000,
            cycle_ts_ms=CYCLE_TS,
            verdict_scope="ENTRY",
        )
        assert result == "INADMISSIBLE"

    def test_fresh_output_admissible(self):
        fresh_eo = _make_entry_expert(ts_ms=CYCLE_TS - 10000)
        result = evaluate_admissibility(
            expert_outputs=[fresh_eo],
            responding_count=1,
            expected_expert_count=1,
            min_quorum=1,
            max_staleness_ms=30000,
            cycle_ts_ms=CYCLE_TS,
            verdict_scope="ENTRY",
        )
        assert result == "ADMISSIBLE"

    def test_exact_staleness_boundary_admissible(self):
        """Output at exact boundary (cycle_ts - max_staleness) is NOT stale."""
        boundary_eo = _make_entry_expert(ts_ms=CYCLE_TS - 30000)
        result = evaluate_admissibility(
            expert_outputs=[boundary_eo],
            responding_count=1,
            expected_expert_count=1,
            min_quorum=1,
            max_staleness_ms=30000,
            cycle_ts_ms=CYCLE_TS,
            verdict_scope="ENTRY",
        )
        assert result == "ADMISSIBLE"


# ---------------------------------------------------------------------------
# R4: Scope mismatch
# ---------------------------------------------------------------------------

class TestAdmissibilityScopeMismatch:
    def test_lifecycle_scope_rejects_entry_output(self):
        """Entry-only ExpertOutput in LIFECYCLE chamber → INADMISSIBLE."""
        entry_eo = _make_entry_expert()
        result = evaluate_admissibility(
            expert_outputs=[entry_eo],
            responding_count=1,
            expected_expert_count=1,
            min_quorum=1,
            max_staleness_ms=30000,
            cycle_ts_ms=CYCLE_TS,
            verdict_scope="LIFECYCLE",
        )
        assert result == "INADMISSIBLE"


# ---------------------------------------------------------------------------
# R5: Default
# ---------------------------------------------------------------------------

class TestAdmissibilityDefault:
    def test_two_experts_all_checks_pass(self):
        eo1 = _make_entry_expert(expert_id="judge.signal_weights_v1")
        eo2 = _make_entry_expert(expert_id="judge.feature_neutrals_v1")
        result = evaluate_admissibility(
            expert_outputs=[eo1, eo2],
            responding_count=2,
            expected_expert_count=2,
            min_quorum=1,
            max_staleness_ms=30000,
            cycle_ts_ms=CYCLE_TS,
            verdict_scope="ENTRY",
        )
        assert result == "ADMISSIBLE"
