"""
LLM Judge Phase 3 — Chamber Aggregator Tests

Tests ChamberAggregator.aggregate() for:
- Entry chamber with various expert combinations
- Lifecycle chamber stub
- Roster-truth accounting
- Consensus direction and strength
- Duplicate expert_id rejection
"""

import pytest

from apps.reference.domains.alpha_search.judge.config_models import ChamberConfig
from apps.reference.domains.alpha_search.judge.contracts import (
    ChamberAggregate,
    ExpertOutput,
)
from apps.reference.domains.alpha_search.judge.chamber.chamber_aggregator import (
    ChamberAggregator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = ChamberConfig(
    min_quorum=1,
    max_staleness_ms=30000,
    entry_enabled=True,
    lifecycle_enabled=False,
)

TS = 1700000000000


def _make_entry_expert(
    expert_id: str = "judge.signal_weights_v1",
    entry_verdict: str = "OPEN_LONG",
    confidence: float = 0.85,
    signal_direction: str = "LONG",
    ts_ms: int = TS,
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


# ---------------------------------------------------------------------------
# Entry Chamber — basic
# ---------------------------------------------------------------------------

class TestEntryChamberBasic:
    def test_two_long_consensus(self):
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        eo1 = _make_entry_expert(expert_id="e1", entry_verdict="OPEN_LONG",
                                 signal_direction="LONG", confidence=0.8)
        eo2 = _make_entry_expert(expert_id="e2", entry_verdict="OPEN_LONG",
                                 signal_direction="LONG", confidence=0.6)
        result = agg.aggregate(
            [eo1, eo2],
            expected_expert_ids=["e1", "e2"],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert isinstance(result, ChamberAggregate)
        assert result.consensus_direction == "LONG"
        assert result.expert_count == 2
        assert result.responding_count == 2
        assert result.abstaining_count == 0
        assert result.admissibility == "ADMISSIBLE"
        assert abs(result.consensus_strength - 0.7) < 0.001

    def test_two_short_consensus(self):
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        eo1 = _make_entry_expert(expert_id="e1", entry_verdict="OPEN_SHORT",
                                 signal_direction="SHORT", confidence=0.9)
        eo2 = _make_entry_expert(expert_id="e2", entry_verdict="OPEN_SHORT",
                                 signal_direction="SHORT", confidence=0.7)
        result = agg.aggregate(
            [eo1, eo2],
            expected_expert_ids=["e1", "e2"],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert result.consensus_direction == "SHORT"
        assert result.admissibility == "ADMISSIBLE"

    def test_mixed_long_short_split(self):
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        eo1 = _make_entry_expert(expert_id="e1", entry_verdict="OPEN_LONG",
                                 signal_direction="LONG", confidence=0.8)
        eo2 = _make_entry_expert(expert_id="e2", entry_verdict="OPEN_SHORT",
                                 signal_direction="SHORT", confidence=0.8)
        result = agg.aggregate(
            [eo1, eo2],
            expected_expert_ids=["e1", "e2"],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert result.consensus_direction == "SPLIT"
        assert result.responding_count == 2

    def test_single_expert(self):
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        eo = _make_entry_expert(expert_id="e1", confidence=0.75)
        result = agg.aggregate(
            [eo],
            expected_expert_ids=["e1"],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert result.consensus_direction == "LONG"
        assert result.expert_count == 1
        assert result.responding_count == 1
        assert result.consensus_strength == 0.75

    def test_no_entry_neutral(self):
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        eo1 = _make_entry_expert(expert_id="e1", entry_verdict="NO_ENTRY",
                                 signal_direction="NEUTRAL", confidence=0.6)
        eo2 = _make_entry_expert(expert_id="e2", entry_verdict="NO_ENTRY",
                                 signal_direction="NEUTRAL", confidence=0.5)
        result = agg.aggregate(
            [eo1, eo2],
            expected_expert_ids=["e1", "e2"],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert result.consensus_direction == "NEUTRAL"


# ---------------------------------------------------------------------------
# UNKNOWN handling
# ---------------------------------------------------------------------------

class TestEntryChamberUnknown:
    def test_unknown_counted_as_abstaining(self):
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        eo1 = _make_entry_expert(expert_id="e1", confidence=0.8)
        eo2 = _make_entry_expert(expert_id="e2", entry_verdict="UNKNOWN",
                                 signal_direction="NEUTRAL", confidence=0.0)
        result = agg.aggregate(
            [eo1, eo2],
            expected_expert_ids=["e1", "e2"],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert result.responding_count == 1
        assert result.abstaining_count == 1
        assert result.consensus_direction == "LONG"

    def test_both_unknown_quorum_insufficient(self):
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        eo1 = _make_entry_expert(expert_id="e1", entry_verdict="UNKNOWN",
                                 signal_direction="NEUTRAL", confidence=0.0)
        eo2 = _make_entry_expert(expert_id="e2", entry_verdict="UNKNOWN",
                                 signal_direction="NEUTRAL", confidence=0.0)
        result = agg.aggregate(
            [eo1, eo2],
            expected_expert_ids=["e1", "e2"],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert result.responding_count == 0
        assert result.admissibility == "QUORUM_INSUFFICIENT"
        assert result.admissibility_reason == "responding_below_min_quorum"
        assert result.consensus_direction is None

    def test_suppress_counted_as_abstaining(self):
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        eo1 = _make_entry_expert(expert_id="e1", entry_verdict="OPEN_LONG",
                                 signal_direction="LONG", confidence=0.8)
        eo2 = _make_entry_expert(expert_id="e2", entry_verdict="SUPPRESS",
                                 signal_direction="NEUTRAL", confidence=0.9)
        result = agg.aggregate(
            [eo1, eo2],
            expected_expert_ids=["e1", "e2"],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert result.responding_count == 1
        assert result.abstaining_count == 1


# ---------------------------------------------------------------------------
# Roster-truth accounting
# ---------------------------------------------------------------------------

class TestRosterTruth:
    def test_solicited_but_missing_expert(self):
        """Two experts solicited, one crashed (no output). Chamber sees gap."""
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        eo = _make_entry_expert(expert_id="e1", confidence=0.8)
        result = agg.aggregate(
            [eo],
            expected_expert_ids=["e1", "e2"],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert result.expert_count == 2
        assert result.responding_count == 1
        assert result.abstaining_count == 1
        assert result.admissibility == "INADMISSIBLE"
        assert result.admissibility_reason == "solicited_expert_missing_output"

    def test_all_solicited_present(self):
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        eo1 = _make_entry_expert(expert_id="e1", confidence=0.8)
        eo2 = _make_entry_expert(expert_id="e2", confidence=0.7)
        result = agg.aggregate(
            [eo1, eo2],
            expected_expert_ids=["e1", "e2"],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert result.expert_count == 2
        assert result.admissibility == "ADMISSIBLE"

    def test_empty_roster_empty_outputs(self):
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        result = agg.aggregate(
            [],
            expected_expert_ids=[],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert result.expert_count == 0
        assert result.responding_count == 0
        assert result.admissibility == "QUORUM_INSUFFICIENT"
        assert result.admissibility_reason == "responding_below_min_quorum"

    def test_invariant_responding_plus_abstaining_equals_expert_count(self):
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        eo = _make_entry_expert(expert_id="e1", confidence=0.8)
        result = agg.aggregate(
            [eo],
            expected_expert_ids=["e1", "e2", "e3"],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert result.responding_count + result.abstaining_count == result.expert_count


# ---------------------------------------------------------------------------
# Duplicate expert_id
# ---------------------------------------------------------------------------

class TestDuplicateExpertId:
    def test_duplicate_expert_id_inadmissible(self):
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        eo1 = _make_entry_expert(expert_id="e1", confidence=0.8)
        eo2 = _make_entry_expert(expert_id="e1", confidence=0.7)
        result = agg.aggregate(
            [eo1, eo2],
            expected_expert_ids=["e1", "e1"],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert result.admissibility == "INADMISSIBLE"
        assert result.admissibility_reason == "duplicate_expert_id"


# ---------------------------------------------------------------------------
# Lifecycle chamber stub
# ---------------------------------------------------------------------------

class TestLifecycleChamberStub:
    def test_lifecycle_empty_quorum_insufficient(self):
        agg = ChamberAggregator("LIFECYCLE", DEFAULT_CONFIG)
        result = agg.aggregate(
            [],
            expected_expert_ids=[],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert result.verdict_scope == "LIFECYCLE"
        assert result.expert_count == 0
        assert result.responding_count == 0
        assert result.abstaining_count == 0
        assert result.admissibility == "QUORUM_INSUFFICIENT"
        assert result.admissibility_reason == "responding_below_min_quorum"
        assert result.consensus_direction is None
        assert result.consensus_strength == 0.0

    def test_lifecycle_filters_out_entry_outputs(self):
        """Entry-scoped experts should be filtered out by lifecycle chamber."""
        agg = ChamberAggregator("LIFECYCLE", DEFAULT_CONFIG)
        entry_eo = _make_entry_expert(expert_id="e1")
        result = agg.aggregate(
            [entry_eo],
            expected_expert_ids=["e1"],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        # expert_count=1 from roster, but 0 scope-filtered outputs
        assert result.expert_count == 1
        assert result.responding_count == 0
        assert result.abstaining_count == 1


# ---------------------------------------------------------------------------
# Consensus strength
# ---------------------------------------------------------------------------

class TestConsensusStrength:
    def test_mean_of_two_confidences(self):
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        eo1 = _make_entry_expert(expert_id="e1", confidence=0.8)
        eo2 = _make_entry_expert(expert_id="e2", confidence=0.6)
        result = agg.aggregate(
            [eo1, eo2],
            expected_expert_ids=["e1", "e2"],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert abs(result.consensus_strength - 0.7) < 0.001

    def test_zero_responding_zero_strength(self):
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        result = agg.aggregate(
            [],
            expected_expert_ids=[],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert result.consensus_strength == 0.0


# ---------------------------------------------------------------------------
# Chamber ID format
# ---------------------------------------------------------------------------

class TestChamberId:
    def test_entry_chamber_id_format(self):
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        result = agg.aggregate(
            [],
            expected_expert_ids=[],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert result.chamber_id == f"entry_BTCUSDT_{TS}"
        assert result.cycle_key == f"ENTRY:BTCUSDT:300:{TS}"

    def test_lifecycle_chamber_id_format(self):
        agg = ChamberAggregator("LIFECYCLE", DEFAULT_CONFIG)
        result = agg.aggregate(
            [],
            expected_expert_ids=[],
            symbol="ETHUSDT", tf_sec=60, ts_ms=TS,
        )
        assert result.chamber_id == f"lifecycle_ETHUSDT_{TS}"
        assert result.cycle_key == f"LIFECYCLE:ETHUSDT:60:{TS}"


# ---------------------------------------------------------------------------
# Output validates against frozen contract
# ---------------------------------------------------------------------------

class TestContractCompliance:
    def test_output_is_chamber_aggregate(self):
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        eo = _make_entry_expert(expert_id="e1")
        result = agg.aggregate(
            [eo],
            expected_expert_ids=["e1"],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        assert isinstance(result, ChamberAggregate)

    def test_round_trip_serialization(self):
        agg = ChamberAggregator("ENTRY", DEFAULT_CONFIG)
        eo = _make_entry_expert(expert_id="e1")
        result = agg.aggregate(
            [eo],
            expected_expert_ids=["e1"],
            symbol="BTCUSDT", tf_sec=300, ts_ms=TS,
        )
        dumped = result.model_dump()
        restored = ChamberAggregate.model_validate(dumped)
        assert restored.chamber_id == result.chamber_id
        assert restored.consensus_direction == result.consensus_direction
