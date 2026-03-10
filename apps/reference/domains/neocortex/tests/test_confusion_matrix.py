"""
Tests for Formula B: Confusion-weighted reward matrix.

Verifies:
- Matrix indexing correctness (predicted × realized)
- Config matrix overrides hardcoded default
- Anti-collapse properties: E[MR_always] < E[diverse_policy]
- from_config integration with OracleConfig
- Entropy coefficient wiring
"""

from apps.reference.domains.neocortex.logic.reward.regime_labeler import (
    TREND_UP,
    TREND_DOWN,
    MEAN_REVERSION,
    HIGH_VOLATILITY,
    EXHAUSTION,
)
from apps.reference.domains.neocortex.logic.reward.reward_calculator import (
    RegimeRewardCalculator,
    REWARD_MATRIX,
    NUM_ACTIONS,
    ACTION_NAMES,
)
import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")))


# The exact matrix from regime_oracle_reward.yaml
# Anti-collapse: E[always_X] < 0 for all X given realized dist (MR 53-68%).
CONFIG_MATRIX = [
    [2.0, -1.5, -0.5, -1.0, -0.5],   # Predicted TREND_UP
    [-1.5,  2.0, -0.5, -1.0, -0.5],    # Predicted TREND_DOWN
    [-0.8, -0.8,  0.2, -1.5, -0.5],    # Predicted MR (low reward: 0.2)
    [-0.5, -0.5, -1.0,  3.0,  0.3],    # Predicted HIGH_VOLATILITY (miss-MR: -1.0)
    [-0.5, -0.5, -1.0,  0.3,  2.5],    # Predicted EXHAUSTION (miss-MR: -1.0)
]


class TestMatrixIndexing:
    """Verify C[predicted][realized] indexing is correct."""

    def test_diagonal_rewards_are_positive(self):
        """All correct predictions (diagonal) yield positive reward."""
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=CONFIG_MATRIX,
        )
        for i in range(NUM_ACTIONS):
            assert calc.compute_reward(i, i) > 0, (
                f"Diagonal reward for action {i} should be positive"
            )

    def test_mr_correct_reward_is_low(self):
        """MR correct = 0.2 (intentionally very low to discourage default-to-MR)."""
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=CONFIG_MATRIX,
        )
        assert calc.compute_reward(MEAN_REVERSION, MEAN_REVERSION) == 0.2

    def test_mr_missing_high_vol_is_harsh(self):
        """Predicting MR when HIGH_VOL happens = -1.5 (harsh penalty)."""
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=CONFIG_MATRIX,
        )
        assert calc.compute_reward(MEAN_REVERSION, HIGH_VOLATILITY) == -1.5

    def test_trend_up_correct(self):
        """Correctly predicting TREND_UP = +2.0."""
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=CONFIG_MATRIX,
        )
        assert calc.compute_reward(TREND_UP, TREND_UP) == 2.0

    def test_high_vol_correct(self):
        """Correctly predicting HIGH_VOLATILITY = +3.0."""
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=CONFIG_MATRIX,
        )
        assert calc.compute_reward(HIGH_VOLATILITY, HIGH_VOLATILITY) == 3.0

    def test_exhaustion_missing_mr_penalty(self):
        """Predicting EXHAUSTION when MR happens = -1.0 (prevents vol-collapse attractor)."""
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=CONFIG_MATRIX,
        )
        assert calc.compute_reward(EXHAUSTION, MEAN_REVERSION) == -1.0

    def test_exhaustion_partial_credit_high_vol(self):
        """Predicting EXHAUSTION when HIGH_VOL happens = +0.3 (vol-family partial credit)."""
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=CONFIG_MATRIX,
        )
        assert calc.compute_reward(EXHAUSTION, HIGH_VOLATILITY) == 0.3

    def test_symmetric_trend_penalties(self):
        """Predicting wrong trend direction = -1.5 (harsh, symmetric)."""
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=CONFIG_MATRIX,
        )
        assert calc.compute_reward(TREND_UP, TREND_DOWN) == -1.5
        assert calc.compute_reward(TREND_DOWN, TREND_UP) == -1.5

    def test_all_25_entries_accessible(self):
        """All 5x5 = 25 matrix entries are reachable without errors."""
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=CONFIG_MATRIX,
        )
        for pred in range(NUM_ACTIONS):
            for real in range(NUM_ACTIONS):
                reward = calc.compute_reward(pred, real)
                assert isinstance(reward, float), (
                    f"Reward for ({pred}, {real}) should be float"
                )


class TestAntiCollapse:
    """Verify the matrix makes ALL single-action strategies suboptimal."""

    # Realistic distribution from production logs (post-labeler-rewrite)
    LABEL_DIST = {
        TREND_UP: 0.109,
        TREND_DOWN: 0.110,
        MEAN_REVERSION: 0.528,
        HIGH_VOLATILITY: 0.136,
        EXHAUSTION: 0.117,
    }

    def _expected_reward_always(self, calc, action, label_dist):
        """Expected reward for always predicting `action` given label distribution."""
        total = 0.0
        for regime, prob in label_dist.items():
            total += prob * calc.compute_reward(action, regime)
        return total

    def test_no_single_action_is_profitable(self):
        """Under realistic label distribution, ALL single-action strategies have E < 0."""
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=CONFIG_MATRIX,
        )
        for action in range(NUM_ACTIONS):
            e = self._expected_reward_always(calc, action, self.LABEL_DIST)
            assert e < 0, (
                f"E[always {ACTION_NAMES[action]}] = {e:.4f}, must be negative "
                f"to prevent mode collapse"
            )

    def test_no_collapse_at_high_mr(self):
        """Even when MR is 68% of bars, no single-action strategy is profitable."""
        high_mr_dist = {
            TREND_UP: 0.051,
            TREND_DOWN: 0.057,
            MEAN_REVERSION: 0.678,
            HIGH_VOLATILITY: 0.111,
            EXHAUSTION: 0.105,
        }
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=CONFIG_MATRIX,
        )
        for action in range(NUM_ACTIONS):
            e = self._expected_reward_always(calc, action, high_mr_dist)
            assert e < 0, (
                f"E[always {ACTION_NAMES[action]}] = {e:.4f} at MR=68%, "
                f"must be negative"
            )

    def test_exhaustion_collapse_is_unprofitable(self):
        """Specifically: E[always EXHAUSTION] < -0.2 (the former attractor)."""
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=CONFIG_MATRIX,
        )
        e_exhaust = self._expected_reward_always(
            calc, EXHAUSTION, self.LABEL_DIST)
        assert e_exhaust < -0.2, (
            f"E[always EXHAUSTION] = {e_exhaust:.4f}, should be < -0.2"
        )

    def test_perfect_oracle_beats_all_collapse(self):
        """A perfect oracle dramatically outperforms any single-action strategy."""
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=CONFIG_MATRIX,
        )
        # Perfect oracle: sum(prob * diagonal_reward)
        e_perfect = sum(
            self.LABEL_DIST[r] * calc.compute_reward(r, r)
            for r in self.LABEL_DIST
        )
        # Best collapse strategy
        e_best_collapse = max(
            self._expected_reward_always(calc, a, self.LABEL_DIST)
            for a in range(NUM_ACTIONS)
        )
        assert e_perfect > e_best_collapse + 1.0, (
            f"Perfect oracle E={e_perfect:.4f} should beat best collapse "
            f"E={e_best_collapse:.4f} by > 1.0"
        )

    def test_mr_missing_volatility_dominates_penalty(self):
        """The -1.5 penalty for MR→H_VOL is the harshest in the MR row."""
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=CONFIG_MATRIX,
        )
        mr_row = [calc.compute_reward(MEAN_REVERSION, r)
                  for r in range(NUM_ACTIONS)]
        assert min(mr_row) == -1.5
        assert mr_row[HIGH_VOLATILITY] == min(mr_row)


class TestConfigMatrixOverride:
    """Verify config matrix overrides hardcoded default."""

    def test_custom_matrix_used(self):
        """When reward_matrix is provided, it's used instead of REWARD_MATRIX constant."""
        custom = [
            [10.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 10.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 10.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 10.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 10.0],
        ]
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=custom,
        )
        assert calc.compute_reward(0, 0) == 10.0
        assert calc.compute_reward(0, 1) == 0.0

    def test_none_matrix_falls_back_to_default(self):
        """When no matrix is provided, hardcoded REWARD_MATRIX is used."""
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=None,
        )
        # Check against the hardcoded REWARD_MATRIX constant
        assert calc.compute_reward(0, 0) == REWARD_MATRIX[0][0]

    def test_formula_a_ignores_matrix(self):
        """When formula B is disabled, matrix is ignored even if provided."""
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=False,
            reward_matrix=CONFIG_MATRIX,
        )
        # Formula A: correct = reward_correct * class_weight (default 1.0)
        assert calc.compute_reward(TREND_UP, TREND_UP) == 1.0
        # Formula A: wrong = reward_wrong
        assert calc.compute_reward(TREND_UP, TREND_DOWN) == -0.5


class TestFromConfig:
    """Verify from_config picks up the matrix field."""

    def test_from_config_with_matrix(self):
        """OracleConfig with reward_matrix field propagates to calculator."""

        class FakeConfig:
            reward_correct = 1.0
            reward_wrong = -0.5
            reward_matrix_enabled = True
            reward_matrix = CONFIG_MATRIX
            class_weights = {"PREDICT_MEAN_REVERSION": 0.7}

        calc = RegimeRewardCalculator.from_config(FakeConfig())
        assert calc.reward_matrix_enabled is True
        assert calc.compute_reward(MEAN_REVERSION, MEAN_REVERSION) == 0.2
        assert calc.compute_reward(MEAN_REVERSION, HIGH_VOLATILITY) == -1.5

    def test_from_config_without_matrix_attr(self):
        """Legacy config without reward_matrix field falls back gracefully."""

        class LegacyConfig:
            reward_correct = 1.0
            reward_wrong = -0.5
            reward_matrix_enabled = True
            class_weights = {}

        calc = RegimeRewardCalculator.from_config(LegacyConfig())
        # Falls back to hardcoded REWARD_MATRIX
        assert calc.compute_reward(0, 0) == REWARD_MATRIX[0][0]


class TestMatrixShape:
    """Validate matrix dimensions match NUM_ACTIONS."""

    def test_config_matrix_is_5x5(self):
        """The config matrix has exactly 5 rows and 5 cols."""
        assert len(CONFIG_MATRIX) == NUM_ACTIONS
        for row in CONFIG_MATRIX:
            assert len(row) == NUM_ACTIONS

    def test_hardcoded_matrix_is_5x5(self):
        """The hardcoded REWARD_MATRIX has exactly 5 rows and 5 cols."""
        assert len(REWARD_MATRIX) == NUM_ACTIONS
        for row in REWARD_MATRIX:
            assert len(row) == NUM_ACTIONS

    def test_invalid_indices_return_reward_wrong(self):
        """Out-of-bounds indices return reward_wrong, not crash."""
        calc = RegimeRewardCalculator(
            reward_correct=1.0, reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=CONFIG_MATRIX,
        )
        assert calc.compute_reward(-1, 0) == -0.5
        assert calc.compute_reward(0, 5) == -0.5
        assert calc.compute_reward(99, 99) == -0.5
