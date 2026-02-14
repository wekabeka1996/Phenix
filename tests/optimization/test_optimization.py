"""
tests/optimization/ — Unit tests for the Aurora hierarchical optimization module.

Coverage:
    - Walk-Forward splits (non-overlap, gap, boundaries)
    - Block Bootstrap (deterministic seed, distribution shapes)
    - Penalty functions (MDD, reject, starvation, churn, util)
    - Holdout gate (train vs holdout non-overlap)
    - DateRange splitting for train/holdout isolation
"""

import math
import statistics
import pytest
from types import SimpleNamespace

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ============================================================================
# Walk-Forward Splits
# ============================================================================

class TestWalkForwardSplits:
    """Verify WF folds are non-overlapping, have correct gap, and boundaries."""

    def test_single_fold_boundaries(self):
        from optimization.robustness import WalkForwardValidator
        wf = WalkForwardValidator(train_pct=0.6, gap_pct=0.1, test_pct=0.3, n_folds=1)
        folds = wf.generate_folds(1000)
        assert len(folds) == 1
        f = folds[0]
        assert f.train_start == 0
        assert f.train_end == 600
        assert f.gap_start == 600
        assert f.gap_end == 700
        assert f.test_start == 700
        assert f.test_end == 1000

    def test_gap_separates_train_test(self):
        from optimization.robustness import WalkForwardValidator
        wf = WalkForwardValidator(train_pct=0.6, gap_pct=0.1, test_pct=0.3, n_folds=1)
        folds = wf.generate_folds(500)
        for f in folds:
            assert f.gap_start >= f.train_end, "Gap must start after train ends"
            assert f.test_start >= f.gap_end, "Test must start after gap ends"

    def test_no_folds_too_few_bars(self):
        from optimization.robustness import WalkForwardValidator
        wf = WalkForwardValidator(n_folds=3)
        folds = wf.generate_folds(5)
        assert len(folds) == 0

    def test_date_range_sub_range(self):
        """DateRange.sub_range produces correct date slices."""
        from optimization.optimizer import DateRange
        dr = DateRange("2024-01-01", "2024-12-31")
        sub = dr.sub_range(0.0, 0.5)
        assert sub.start == "2024-01-01"
        # ~182 days into 365-day range
        sub2 = dr.sub_range(0.5, 1.0)
        assert sub2.start > sub.start
        assert sub2.end == "2024-12-31"
        # Non-overlap
        assert sub2.start >= sub.end or sub.end == sub2.start


# ============================================================================
# Block Bootstrap
# ============================================================================

class TestBlockBootstrap:
    """Verify bootstrap determinism and distribution shapes."""

    def test_deterministic_seed(self):
        """Same seed → same results."""
        from optimization.robustness import BlockBootstrap
        returns = [0.001 * i for i in range(100)]
        bs1 = BlockBootstrap(n_resamples=20, block_size=5, seed=42)
        bs2 = BlockBootstrap(n_resamples=20, block_size=5, seed=42)
        r1 = bs1.resample(returns)
        r2 = bs2.resample(returns)
        assert r1.pnl_samples == r2.pnl_samples
        assert r1.sharpe_samples == r2.sharpe_samples

    def test_p5_less_than_p95(self):
        """5th percentile Sharpe should be ≤ 95th percentile."""
        from optimization.robustness import BlockBootstrap
        import random
        rng = random.Random(123)
        returns = [rng.gauss(0.001, 0.01) for _ in range(200)]
        bs = BlockBootstrap(n_resamples=50, block_size=10, seed=7)
        result = bs.resample(returns)
        assert result.sharpe_p5 <= result.sharpe_p95

    def test_positive_returns_high_pnl_positive(self):
        """All-positive returns → most bootstrap samples should be positive PnL."""
        from optimization.robustness import BlockBootstrap
        returns = [0.01] * 100
        bs = BlockBootstrap(n_resamples=50, block_size=5, seed=0)
        result = bs.resample(returns)
        assert result.pnl_positive_pct >= 0.9


# ============================================================================
# Penalty Functions
# ============================================================================

class TestPenalties:
    """Verify penalty functions for Stage 1 objective."""

    def test_mdd_below_soft_no_penalty(self):
        from optimization.objectives import P_mdd
        assert P_mdd(15.0, soft=20.0, hard=35.0) == 0.0

    def test_mdd_between_soft_and_hard(self):
        from optimization.objectives import P_mdd
        p = P_mdd(27.5, soft=20.0, hard=35.0)
        assert 0.0 < p < 1.0
        assert abs(p - 0.5) < 0.01

    def test_mdd_above_hard_infinite(self):
        from optimization.objectives import P_mdd
        p = P_mdd(40.0, soft=20.0, hard=35.0)
        assert math.isinf(p)

    def test_starvation_no_penalty_above_min(self):
        from optimization.objectives import P_starvation
        assert P_starvation(15, min_trades=10) == 0.0

    def test_starvation_full_penalty_zero_trades(self):
        from optimization.objectives import P_starvation
        assert P_starvation(0, min_trades=10) == 1.0

    def test_starvation_partial_penalty(self):
        from optimization.objectives import P_starvation
        p = P_starvation(5, min_trades=10)
        assert abs(p - 0.5) < 0.01

    def test_churn_below_threshold_no_penalty(self):
        from optimization.objectives import P_churn
        assert P_churn(0.3, threshold=0.4) == 0.0

    def test_reject_above_threshold_penalty(self):
        from optimization.objectives import P_reject
        p = P_reject(0.5, threshold=0.3)
        assert p > 0.0

    def test_util_proximity_below_max_no_penalty(self):
        from optimization.objectives import P_util_proximity
        assert P_util_proximity(0.9, max_util=0.95) == 0.0

    def test_util_none_skips_penalty(self):
        """When utilization=None, compute_alpha_score should skip P_util entirely."""
        from optimization.objectives import AlphaMetrics, PenaltyConfig, compute_alpha_score
        am_none = AlphaMetrics(sharpe_ratio=1.0, total_trades=20, utilization=None)
        am_high = AlphaMetrics(sharpe_ratio=1.0, total_trades=20, utilization=0.99)
        pc = PenaltyConfig()
        score_none = compute_alpha_score(am_none, pc)
        score_high = compute_alpha_score(am_high, pc)
        # util=None should yield higher score (no penalty) than util=0.99
        assert score_none > score_high

    def test_hard_alpha_reject(self):
        """MDD above hard threshold → alpha_score = -1e9."""
        from optimization.objectives import AlphaMetrics, PenaltyConfig, compute_alpha_score
        am = AlphaMetrics(sharpe_ratio=2.0, max_drawdown_pct=40.0, total_trades=100)
        pc = PenaltyConfig()
        assert compute_alpha_score(am, pc) == -1e9


# ============================================================================
# Holdout Gate & Date Isolation
# ============================================================================

class TestHoldoutGate:
    """Verify holdout gate logic and train/holdout non-overlap."""

    def test_holdout_pass(self):
        from optimization.robustness import ColdHoldoutGate
        gate = ColdHoldoutGate(min_sharpe=1.0, max_mdd_p90_pct=25.0)
        result = gate.evaluate(sharpe=1.5, mdd_pct=10.0, mdd_p90_pct=15.0)
        assert result.passed is True

    def test_holdout_fail_sharpe(self):
        from optimization.robustness import ColdHoldoutGate
        gate = ColdHoldoutGate(min_sharpe=1.0, max_mdd_p90_pct=25.0)
        result = gate.evaluate(sharpe=0.5, mdd_pct=10.0)
        assert result.passed is False
        assert "Sharpe" in result.reason

    def test_holdout_fail_mdd(self):
        from optimization.robustness import ColdHoldoutGate
        gate = ColdHoldoutGate(min_sharpe=1.0, max_mdd_p90_pct=25.0)
        result = gate.evaluate(sharpe=1.5, mdd_pct=10.0, mdd_p90_pct=30.0)
        assert result.passed is False
        assert "MDD" in result.reason

    def test_train_holdout_non_overlap(self):
        """Train range and holdout range must not overlap (1-day gap for inclusive boundaries)."""
        from optimization.optimizer import compute_train_holdout_split
        from datetime import timedelta
        train, holdout = compute_train_holdout_split("2024-01-01", "2025-12-31", holdout_months=3)
        # Train ends 1 day BEFORE holdout starts (inclusive boundary safety)
        assert train.end_dt < holdout.start_dt
        gap_days = (holdout.start_dt - train.end_dt).days
        assert gap_days == 1, f"Expected 1-day gap, got {gap_days}"
        # No overlap whatsoever
        assert train.end_dt < holdout.start_dt

    def test_holdout_covers_end(self):
        """Holdout must extend to the full end date."""
        from optimization.optimizer import compute_train_holdout_split
        _, holdout = compute_train_holdout_split("2024-01-01", "2025-12-31", holdout_months=3)
        assert holdout.end == "2025-12-31"

    def test_train_covers_start(self):
        """Train must start at the full start date."""
        from optimization.optimizer import compute_train_holdout_split
        train, _ = compute_train_holdout_split("2024-01-01", "2025-12-31", holdout_months=3)
        assert train.start == "2024-01-01"


# ============================================================================
# Execution Stress
# ============================================================================

class TestExecutionStress:
    """Verify stress test reduces returns (adds costs)."""

    def test_stress_median_not_better_than_baseline(self):
        """Median stressed return across N seeds must be <= baseline mean.

        This avoids the flaky single-run test where one random seed might
        accidentally produce a better stressed return.
        """
        import statistics
        from optimization.robustness import ExecutionStress
        returns = [0.01] * 50
        baseline_mean = sum(returns) / len(returns)

        stressed_means = []
        for seed in range(10):
            stress = ExecutionStress(seed=seed)
            stressed = stress.apply_stress_to_returns(returns)
            stressed_means.append(sum(stressed) / len(stressed))

        median_stressed = statistics.median(stressed_means)
        assert median_stressed < baseline_mean, (
            f"median stressed ({median_stressed:.6f}) should be < baseline ({baseline_mean:.6f})"
        )

    def test_stress_params_applied(self):
        """Verify that stress parameters (fees, slippage) are actually injected."""
        from optimization.robustness import ExecutionStress
        stress = ExecutionStress(
            latency_ms_range=(100, 200),
            slippage_bps_range=(5, 10),
            fee_multiplier_range=(1.5, 2.0),
            seed=42,
        )
        returns = [0.01] * 20
        stressed = stress.apply_stress_to_returns(returns)
        # With fees_mult >= 1.5 and slippage >= 5 bps, every return should drop
        for orig, strd in zip(returns, stressed):
            assert strd < orig, f"With heavy stress params, {strd} should be < {orig}"


# ============================================================================
# Stage 0 / Stage 1 Data Contracts
# ============================================================================

class TestOptimizationDataContracts:
    """Contracts for regime timeline and reject-rate accounting."""

    def test_stage0_uncertain_normalization_uppercase(self):
        """UNCERTAIN/UNKNOWN must be normalized with upper().strip()."""
        from optimization.backtest_interface import BacktestAdapter, StageResult

        adapter = BacktestAdapter()
        stage_result = StageResult(
            success=True,
            regime_log=["LOW_VOL", "UNCERTAIN", "HIGH_VOL", "UNCERTAIN"],
        )
        metrics = adapter._extract_regime_metrics(stage_result)
        assert metrics.uncertain_share == 0.5
        assert metrics.uncertain_bars == 2
        assert metrics.total_bars == 4

    def test_reject_rate_counts_rejected_events(self):
        """10 proposed intents + 4 rejected events => reject_rate=0.4."""
        from optimization.backtest_interface import BacktestAdapter, StageResult

        adapter = BacktestAdapter()
        raw_result = SimpleNamespace(
            sharpe_ratio=0.0,
            calmar_ratio=0.0,
            max_drawdown=0.0,
            total_trades=0,
            roi_pct=0.0,
        )
        intent_log = [{"intent_status": "PROPOSED", "side": "BUY"} for _ in range(10)] + [
            {"intent_status": "REJECTED"} for _ in range(4)
        ]
        stage_result = StageResult(
            success=True,
            raw_result=raw_result,
            trade_intents=[{"side": "BUY"} for _ in range(10)],
            intent_log=intent_log,
        )

        metrics = adapter._extract_alpha_metrics(stage_result)
        assert metrics.reject_rate == 0.4

    def test_stability_score_varies_across_trials_not_nan(self):
        from optimization.objectives import RegimeStabilityMetrics, compute_stability_score

        m1 = RegimeStabilityMetrics(
            total_bars=100,
            definite_bars=70,
            uncertain_bars=30,
            regime_flips=20,
            duration_hours=10.0,
        )
        m2 = RegimeStabilityMetrics(
            total_bars=100,
            definite_bars=80,
            uncertain_bars=20,
            regime_flips=8,
            duration_hours=10.0,
        )
        s1 = compute_stability_score(m1)
        s2 = compute_stability_score(m2)
        assert math.isfinite(s1)
        assert math.isfinite(s2)
        assert s1 != s2


# ============================================================================
# Stage 2 Stress Rerun Contract
# ============================================================================

class TestStage2StressRerun:
    """Stage2 must rerun full backtests with stress overrides (not mutate returns)."""

    def test_stage2_uses_full_backtest_reruns_with_stress_overrides(self):
        from optimization.optimizer import AuroraOptimizer, DateRange
        from optimization.backtest_interface import StageResult
        from optimization.objectives import AlphaMetrics

        class _AdapterMock:
            def __init__(self):
                self.calls = []

            def run_stage1(self, overlay, *, start_date=None, end_date=None):
                self.calls.append((overlay, start_date, end_date))
                stress = (
                    overlay.get("trading", {})
                    .get("backtest", {})
                    .get("stress_overrides", {})
                )
                # Deterministic sharpe degradation based on fee multiplier
                fee_mult = float(stress.get("fee_mult", 1.0))
                sharpe = 1.0 - max(0.0, fee_mult - 1.0)
                metrics = AlphaMetrics(
                    sharpe_ratio=sharpe,
                    max_drawdown_pct=5.0,
                    total_trades=10,
                    roi_pct=1.0,
                )
                stage_result = StageResult(success=True, equity_snapshots=[1000.0, 1001.0, 1002.0])
                return metrics, stage_result

        opt = AuroraOptimizer.__new__(AuroraOptimizer)
        opt.optimizer_cfg = {
            "stage1": {"acceptance": {"max_dd_pct": 35.0}},
        }
        opt.adapter = _AdapterMock()

        s2_cfg = {
            "execution_stress": {
                "n_seeds": 3,
                "latency_ms_range": [10, 20],
                "slippage_bps_range": [1, 2],
                "fee_multiplier_range": [1.1, 1.2],
                "funding_bps_per_day_range": [1.0, 2.0],
            },
            "block_bootstrap": {"n_resamples": 10, "block_size_bars": 2},
        }
        fold = opt._run_single_fold(
            fold_id=0,
            candidate_overlay={},
            test_range=DateRange("2023-05-14", "2023-05-15"),
            s2_cfg=s2_cfg,
        )

        # 1 baseline + 3 stress reruns
        assert len(opt.adapter.calls) == 4
        assert len(fold.stress_runs) == 3
        for r in fold.stress_runs:
            assert "overrides" in r
            assert "fee_mult" in r["overrides"]
            assert "funding_bps_per_day" in r["overrides"]


class TestUniverseLock:
    def test_optimizer_universe_lock_rejects_non_btc_aurora(self):
        from optimization.optimizer import AuroraOptimizer

        with pytest.raises(ValueError, match="Optimization universe lock violation"):
            AuroraOptimizer._validate_universe_lock_cfg(
                {"data": {"symbols": ["ETHUSDT"], "strategy_id": "aurora"}}
            )

    def test_optimizer_universe_lock_accepts_btc_aurora(self):
        from optimization.optimizer import AuroraOptimizer

        symbols, strategy_id = AuroraOptimizer._validate_universe_lock_cfg(
            {"data": {"symbols": ["BTCUSDT"], "strategy_id": "aurora"}}
        )
        assert symbols == ["BTCUSDT"]
        assert strategy_id == "aurora"


class TestBacktestModeDefaults:
    def test_backtest_mode_default_is_strict(self):
        from apps.reference.config_models import BacktestConfig

        cfg = BacktestConfig(start_date="2024-01-01", end_date="2024-01-02")
        assert cfg.backtest_mode == "strict"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
