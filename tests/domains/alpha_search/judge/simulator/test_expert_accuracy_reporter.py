from apps.reference.domains.alpha_search.judge.contracts import ExpertOutput
from apps.reference.domains.alpha_search.judge.simulator.expert_accuracy_reporter import (
    aggregate_expert_accuracy,
    compute_expert_accuracy_for_cycle,
)


def _make_expert_output(
    *,
    expert_id: str,
    entry_verdict: str,
    confidence: float = 0.8,
) -> ExpertOutput:
    signal_direction = "NEUTRAL"
    if entry_verdict == "OPEN_LONG":
        signal_direction = "LONG"
    elif entry_verdict == "OPEN_SHORT":
        signal_direction = "SHORT"

    return ExpertOutput(
        expert_id=expert_id,
        expert_version="1.0.0",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=1712000000000,
        entry_verdict=entry_verdict,
        lifecycle_verdict=None,
        confidence=confidence,
        signal_direction=signal_direction,
        reasoning=["test"],
    )


class TestComputeExpertAccuracyForCycle:
    def test_per_cycle_expert_accuracy_computed_correctly(self):
        records = compute_expert_accuracy_for_cycle(
            strategy_id="aurora",
            symbol="BTCUSDT",
            tf_sec=300,
            bar_close_ts=1712000000000,
            expert_outputs=[
                _make_expert_output(expert_id="exp-long",
                                    entry_verdict="OPEN_LONG"),
                _make_expert_output(expert_id="exp-short",
                                    entry_verdict="OPEN_SHORT"),
                _make_expert_output(expert_id="exp-no-entry",
                                    entry_verdict="NO_ENTRY"),
            ],
            optimal_action="OPEN_LONG",
        )

        assert len(records) == 3
        assert records[0]["is_correct"] is True
        assert records[1]["is_correct"] is False
        assert records[2]["is_correct"] is False

    def test_missing_expert_outputs_handled_explicitly(self):
        records = compute_expert_accuracy_for_cycle(
            strategy_id="aurora",
            symbol="BTCUSDT",
            tf_sec=300,
            bar_close_ts=1712000000000,
            expert_outputs=None,
            optimal_action="OPEN_LONG",
        )

        assert records == []

    def test_duplicate_expert_ids_handled_deterministically(self):
        records = compute_expert_accuracy_for_cycle(
            strategy_id="aurora",
            symbol="BTCUSDT",
            tf_sec=300,
            bar_close_ts=1712000000000,
            expert_outputs=[
                _make_expert_output(expert_id="dup-exp",
                                    entry_verdict="OPEN_LONG"),
                _make_expert_output(expert_id="dup-exp",
                                    entry_verdict="OPEN_SHORT"),
            ],
            optimal_action="OPEN_LONG",
        )

        assert len(records) == 1
        assert records[0]["expert_id"] == "dup-exp"
        assert records[0]["is_correct"] is True

    def test_no_fabricated_expert_correctness_when_data_absent(self):
        records = compute_expert_accuracy_for_cycle(
            strategy_id="aurora",
            symbol="BTCUSDT",
            tf_sec=300,
            bar_close_ts=1712000000000,
            expert_outputs=[
                _make_expert_output(expert_id="exp-unknown",
                                    entry_verdict="UNKNOWN"),
                _make_expert_output(expert_id="exp-suppress",
                                    entry_verdict="SUPPRESS"),
            ],
            optimal_action="NO_ENTRY",
        )

        assert len(records) == 2
        assert records[0]["evaluated"] is False
        assert records[0]["is_correct"] is None
        assert records[0]["skip_reason"] == "non_actionable_verdict"
        assert records[1]["evaluated"] is False
        assert records[1]["is_correct"] is None


class TestAggregateExpertAccuracy:
    def test_aggregation_total_correct_accuracy_rate_correct(self):
        records = compute_expert_accuracy_for_cycle(
            strategy_id="aurora",
            symbol="BTCUSDT",
            tf_sec=300,
            bar_close_ts=1712000000000,
            expert_outputs=[
                _make_expert_output(expert_id="exp-long",
                                    entry_verdict="OPEN_LONG"),
                _make_expert_output(expert_id="exp-short",
                                    entry_verdict="OPEN_SHORT"),
                _make_expert_output(expert_id="exp-unknown",
                                    entry_verdict="UNKNOWN"),
            ],
            optimal_action="OPEN_LONG",
        )

        summary = aggregate_expert_accuracy(records)

        assert summary["total_count"] == 2
        assert summary["correct_count"] == 1
        assert summary["skipped_count"] == 1
        assert summary["accuracy_rate"] == 0.5
        assert summary["by_expert"]["exp-long"]["accuracy_rate"] == 1.0
        assert summary["by_expert"]["exp-short"]["accuracy_rate"] == 0.0
        assert summary["by_expert"]["exp-unknown"]["total_count"] == 0
