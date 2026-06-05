import math

from apps.reference.domains.alpha_search.judge.simulator.disagreement_analyzer import (
    build_disagreement_record,
    compute_disagreement,
    determine_optimal_action,
)


class TestDetermineOptimalAction:
    def test_positive_long_outcome_case(self):
        action = determine_optimal_action(
            matched_trade=True,
            entry_price=100.0,
            exit_price=110.0,
            fee_per_cycle_bps=0.0,
            slippage_pct=0.0,
        )

        assert action == "OPEN_LONG"

    def test_positive_short_outcome_case(self):
        action = determine_optimal_action(
            matched_trade=True,
            entry_price=100.0,
            exit_price=90.0,
            fee_per_cycle_bps=0.0,
            slippage_pct=0.0,
        )

        assert action == "OPEN_SHORT"

    def test_abstain_no_trade_case(self):
        action = determine_optimal_action(
            matched_trade=False,
            entry_price=None,
            exit_price=None,
            fee_per_cycle_bps=25.0,
            slippage_pct=0.1,
        )

        assert action == "NO_ENTRY"

    def test_negative_actionable_outcome_can_resolve_to_no_entry(self):
        action = determine_optimal_action(
            matched_trade=True,
            entry_price=100.0,
            exit_price=100.1,
            fee_per_cycle_bps=25.0,
            slippage_pct=0.1,
        )

        assert action == "NO_ENTRY"

    def test_deterministic_rerun_behavior(self):
        first = determine_optimal_action(
            matched_trade=True,
            entry_price=100.0,
            exit_price=90.0,
            fee_per_cycle_bps=25.0,
            slippage_pct=0.1,
        )
        second = determine_optimal_action(
            matched_trade=True,
            entry_price=100.0,
            exit_price=90.0,
            fee_per_cycle_bps=25.0,
            slippage_pct=0.1,
        )

        assert first == second == "OPEN_SHORT"


class TestComputeDisagreement:
    def test_no_disagreement_when_verdict_matches_optimal_action(self):
        disagreement = compute_disagreement(
            verdict_action="OPEN_LONG",
            matched_trade=True,
            entry_price=100.0,
            exit_price=110.0,
            fee_per_cycle_bps=0.0,
            slippage_pct=0.0,
        )

        assert disagreement is None

    def test_open_long_mismatch_case(self):
        disagreement = compute_disagreement(
            verdict_action="OPEN_LONG",
            matched_trade=True,
            entry_price=100.0,
            exit_price=90.0,
            fee_per_cycle_bps=0.0,
            slippage_pct=0.0,
        )

        assert disagreement is not None
        assert disagreement["optimal_action"] == "OPEN_SHORT"
        assert math.isclose(disagreement["cost_of_disagreement"], 0.2)

    def test_open_short_mismatch_case(self):
        disagreement = compute_disagreement(
            verdict_action="OPEN_SHORT",
            matched_trade=True,
            entry_price=100.0,
            exit_price=110.0,
            fee_per_cycle_bps=0.0,
            slippage_pct=0.0,
        )

        assert disagreement is not None
        assert disagreement["optimal_action"] == "OPEN_LONG"
        assert math.isclose(disagreement["cost_of_disagreement"], 0.2)

    def test_no_entry_mismatch_abstain_case(self):
        disagreement = compute_disagreement(
            verdict_action="NO_ENTRY",
            matched_trade=True,
            entry_price=100.0,
            exit_price=110.0,
            fee_per_cycle_bps=0.0,
            slippage_pct=0.0,
        )

        assert disagreement is not None
        assert disagreement["optimal_action"] == "OPEN_LONG"
        assert math.isclose(disagreement["cost_of_disagreement"], 0.1)

    def test_cost_of_disagreement_uses_5b_net_return_when_available(self):
        disagreement = compute_disagreement(
            verdict_action="OPEN_LONG",
            matched_trade=True,
            entry_price=100.0,
            exit_price=90.0,
            fee_per_cycle_bps=25.0,
            slippage_pct=0.1,
            verdict_net_return=-0.1035,
        )

        assert disagreement is not None
        assert disagreement["optimal_action"] == "OPEN_SHORT"
        assert math.isclose(disagreement["cost_of_disagreement"], 0.2)

    def test_non_actionable_verdict_treatment_is_explicit(self):
        unknown = compute_disagreement(
            verdict_action="UNKNOWN",
            matched_trade=True,
            entry_price=100.0,
            exit_price=110.0,
            fee_per_cycle_bps=0.0,
            slippage_pct=0.0,
        )
        suppress = compute_disagreement(
            verdict_action="SUPPRESS",
            matched_trade=True,
            entry_price=100.0,
            exit_price=110.0,
            fee_per_cycle_bps=0.0,
            slippage_pct=0.0,
        )

        assert unknown is None
        assert suppress is None

    def test_build_disagreement_record(self):
        record = build_disagreement_record(
            verdict_id="v-1",
            strategy_id="aurora",
            symbol="BTCUSDT",
            tf_sec=300,
            bar_close_ts=1712000000000,
            verdict_action="OPEN_LONG",
            optimal_action="OPEN_SHORT",
            cost_of_disagreement=0.2,
            confidence=0.8,
            dissent_noted=True,
        )

        assert record == {
            "verdict_id": "v-1",
            "strategy_id": "aurora",
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1712000000000,
            "verdict_action": "OPEN_LONG",
            "optimal_action": "OPEN_SHORT",
            "cost_of_disagreement": 0.2,
            "confidence": 0.8,
            "dissent_noted": True,
        }
