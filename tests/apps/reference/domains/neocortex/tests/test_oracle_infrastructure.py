"""
Unit tests for Regime Oracle infrastructure (REGIME_PIVOT_PLAN Phase 1).

Tests:
- OracleConfig loading and validation
- RegimeLabeler ground-truth classification
- RegimeRewardCalculator (Formula A + B)
- FeatureRingBuffer settlement logic
"""

from apps.reference.domains.neocortex.logic.reward.regime_labeler import (
    RegimeLabeler,
    TREND_UP,
    TREND_DOWN,
    MEAN_REVERSION,
    HIGH_VOLATILITY,
    EXHAUSTION,
    REGIME_NAMES,
)
from apps.reference.domains.neocortex.logic.reward.reward_calculator import (
    RegimeRewardCalculator,
    REWARD_MATRIX,
    NUM_ACTIONS,
)
from apps.reference.domains.neocortex.logic.reward.feature_buffer import (
    FeatureRingBuffer,
    SettledEpisode,
)
import sys
import os
import pytest
import numpy as np

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")))


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def labeler() -> RegimeLabeler:
    """Default labeler with calibrated thresholds."""
    return RegimeLabeler(
        high_vol_threshold=0.8,
        exhaustion_vol_now_threshold=0.5,
        exhaustion_vol_future_threshold=0.1,
        trend_delta_pct_threshold=0.0002,
        trend_ema_threshold=0.0008,
        mr_delta_pct_threshold=0.0001,
    )


@pytest.fixture
def calculator() -> RegimeRewardCalculator:
    """Default calculator with Formula A."""
    return RegimeRewardCalculator(
        reward_correct=1.0,
        reward_wrong=-0.5,
        reward_matrix_enabled=False,
        class_weights={
            "PREDICT_TREND_UP": 1.5,
            "PREDICT_TREND_DOWN": 1.5,
            "PREDICT_MEAN_REVERSION": 0.7,
            "PREDICT_HIGH_VOLATILITY": 2.0,
            "PREDICT_EXHAUSTION": 2.5,
        },
    )


@pytest.fixture
def buffer() -> FeatureRingBuffer:
    """Default ring buffer with horizon=5."""
    return FeatureRingBuffer(horizon_bars=5)


def _make_features(
    price: float = 100.0,
    delta_price: float = 0.0,
    ema_bias: float = 0.5,
    volatility_state: float = 0.0,
) -> dict:
    """Helper to build a minimal feature dict for labeler tests.

    Note: ema_bias is in [0,1]@0.5 format (labeler re-centers to 0).
    delta_price is raw USD (labeler divides by price).
    """
    return {
        "price": price,
        "delta_price": delta_price,
        "ema_bias": ema_bias,
        "volatility_state": volatility_state,
    }


# =============================================================================
# RegimeLabeler Tests
# =============================================================================

class TestRegimeLabeler:

    def test_high_volatility_spike(self, labeler):
        """Future vol_state > high_vol_threshold -> HIGH_VOLATILITY."""
        features_t = _make_features(volatility_state=0.3)
        features_t_h = _make_features(volatility_state=0.9)  # > 0.8
        assert labeler.compute_realized_regime(
            features_t, features_t_h) == HIGH_VOLATILITY

    def test_exhaustion_vol_collapse(self, labeler):
        """Vol was high now, collapsed to low future -> EXHAUSTION."""
        features_t = _make_features(volatility_state=0.7)  # > 0.5
        features_t_h = _make_features(volatility_state=0.05)  # < 0.1
        assert labeler.compute_realized_regime(
            features_t, features_t_h) == EXHAUSTION

    def test_trend_up(self, labeler):
        """Positive delta_pct + positive ema_centered -> TREND_UP."""
        # delta_pct = 0.05/100 = 0.0005 > 0.0002
        # ema_centered = 0.502 - 0.5 = 0.002 > 0.0008
        features_t = _make_features(price=100.0, volatility_state=0.0)
        features_t_h = _make_features(
            delta_price=0.05,  # 0.05/100 = 0.0005 > threshold 0.0002
            ema_bias=0.502,    # centered = 0.002 > threshold 0.0008
            volatility_state=0.3,  # not high vol
        )
        assert labeler.compute_realized_regime(
            features_t, features_t_h) == TREND_UP

    def test_trend_down(self, labeler):
        """Negative delta_pct + negative ema_centered -> TREND_DOWN."""
        features_t = _make_features(price=100.0, volatility_state=0.0)
        features_t_h = _make_features(
            delta_price=-0.05,  # -0.0005 < -0.0002
            ema_bias=0.498,     # centered = -0.002 < -0.0008
            volatility_state=0.3,
        )
        assert labeler.compute_realized_regime(
            features_t, features_t_h) == TREND_DOWN

    def test_mean_reversion(self, labeler):
        """Small moves -> MEAN_REVERSION."""
        features_t = _make_features(price=100.0, volatility_state=0.0)
        features_t_h = _make_features(
            delta_price=0.005,   # 0.005/100 = 0.00005 < mr_threshold 0.0001
            ema_bias=0.5001,     # centered = 0.0001 (doesn't matter for MR)
            volatility_state=0.0,
        )
        assert labeler.compute_realized_regime(
            features_t, features_t_h) == MEAN_REVERSION

    def test_default_fallback_is_mr(self, labeler):
        """Edge case: delta_pct above MR but no EMA confirmation -> MR fallback."""
        features_t = _make_features(price=100.0, volatility_state=0.0)
        features_t_h = _make_features(
            delta_price=0.03,   # 0.0003 > trend threshold, but...
            ema_bias=0.5003,    # centered = 0.0003 < ema_threshold 0.0008
            volatility_state=0.3,
        )
        # delta_pct passes trend but ema doesn't confirm -> falls through to MR
        assert labeler.compute_realized_regime(
            features_t, features_t_h) == MEAN_REVERSION

    def test_high_vol_has_priority_over_trend(self, labeler):
        """Even if trend features are present, HIGH_VOL takes priority."""
        features_t = _make_features(price=100.0, volatility_state=0.3)
        features_t_h = _make_features(
            delta_price=0.05,
            ema_bias=0.502,
            volatility_state=0.9,  # HIGH_VOL triggers first
        )
        assert labeler.compute_realized_regime(
            features_t, features_t_h) == HIGH_VOLATILITY

    def test_exhaustion_priority_over_trend(self, labeler):
        """Exhaustion detected even if trend features present."""
        features_t = _make_features(
            price=100.0, volatility_state=0.7)  # was high
        features_t_h = _make_features(
            delta_price=0.05,
            ema_bias=0.502,
            # collapsed (< 0.1), and vol_state_future < high_vol_threshold
            volatility_state=0.05,
        )
        assert labeler.compute_realized_regime(
            features_t, features_t_h) == EXHAUSTION

    def test_none_features_rejected(self, labeler):
        """None values are rejected instead of becoming synthetic label truth."""
        features_t = {"price": None, "delta_price": None,
                      "ema_bias": None, "volatility_state": None}
        features_t_h = {"price": None, "delta_price": None,
                        "ema_bias": None, "volatility_state": None}
        with pytest.raises(ValueError, match="required feature"):
            labeler.compute_realized_regime(features_t, features_t_h)

    def test_all_five_regimes_reachable(self, labeler):
        """Verify all 5 regimes are reachable with appropriate features."""
        results = set()
        # HIGH_VOL
        results.add(labeler.compute_realized_regime(
            _make_features(volatility_state=0.3),
            _make_features(volatility_state=0.9),
        ))
        # EXHAUSTION
        results.add(labeler.compute_realized_regime(
            _make_features(volatility_state=0.7),
            _make_features(volatility_state=0.05),
        ))
        # TREND_UP
        results.add(labeler.compute_realized_regime(
            _make_features(price=100.0),
            _make_features(delta_price=0.05, ema_bias=0.502,
                           volatility_state=0.3),
        ))
        # TREND_DOWN
        results.add(labeler.compute_realized_regime(
            _make_features(price=100.0),
            _make_features(delta_price=-0.05, ema_bias=0.498,
                           volatility_state=0.3),
        ))
        # MEAN_REVERSION
        results.add(labeler.compute_realized_regime(
            _make_features(price=100.0),
            _make_features(delta_price=0.005, ema_bias=0.5001),
        ))
        assert results == {TREND_UP, TREND_DOWN,
                           MEAN_REVERSION, HIGH_VOLATILITY, EXHAUSTION}

    def test_from_config(self):
        """Test the from_config classmethod."""
        class FakeConfig:
            high_vol_threshold = 0.8
            exhaustion_vol_now_threshold = 0.5
            exhaustion_vol_future_threshold = 0.1
            trend_delta_pct_threshold = 0.0002
            trend_ema_threshold = 0.0008
            mr_delta_pct_threshold = 0.0001

        lab = RegimeLabeler.from_config(FakeConfig())
        assert lab.high_vol_threshold == 0.8
        assert lab.trend_delta_pct_threshold == 0.0002


# =============================================================================
# RegimeRewardCalculator Tests
# =============================================================================

class TestRegimeRewardCalculator:

    def test_formula_a_correct_prediction(self, calculator):
        """Correct prediction gets reward_correct * class_weight."""
        # TREND_UP correct: 1.0 * 1.5 = 1.5
        assert calculator.compute_reward(
            TREND_UP, TREND_UP) == pytest.approx(1.5)
        # MR correct: 1.0 * 0.7 = 0.7
        assert calculator.compute_reward(
            MEAN_REVERSION, MEAN_REVERSION) == pytest.approx(0.7)
        # EXHAUSTION correct: 1.0 * 2.5 = 2.5
        assert calculator.compute_reward(
            EXHAUSTION, EXHAUSTION) == pytest.approx(2.5)

    def test_formula_a_wrong_prediction(self, calculator):
        """Wrong prediction gets flat reward_wrong."""
        assert calculator.compute_reward(
            TREND_UP, TREND_DOWN) == pytest.approx(-0.5)
        assert calculator.compute_reward(
            HIGH_VOLATILITY, MEAN_REVERSION) == pytest.approx(-0.5)

    def test_formula_b_confusion_matrix(self):
        """Formula B returns values from REWARD_MATRIX."""
        calc = RegimeRewardCalculator(
            reward_correct=1.0,
            reward_wrong=-0.5,
            reward_matrix_enabled=True,
            reward_matrix=REWARD_MATRIX,
        )
        # Diagonal (correct)
        assert calc.compute_reward(TREND_UP, TREND_UP) == pytest.approx(1.0)
        assert calc.compute_reward(
            EXHAUSTION, EXHAUSTION) == pytest.approx(1.0)
        # Trend direction error
        assert calc.compute_reward(TREND_UP, TREND_DOWN) == pytest.approx(-1.0)
        # Partial credit: EXHAUSTION predicted, HIGH_VOL realized
        assert calc.compute_reward(
            EXHAUSTION, HIGH_VOLATILITY) == pytest.approx(0.3)
        # Partial credit: HIGH_VOL predicted, EXHAUSTION realized
        assert calc.compute_reward(
            HIGH_VOLATILITY, EXHAUSTION) == pytest.approx(0.3)

    def test_invalid_action_returns_wrong(self, calculator):
        """Out-of-range actions return reward_wrong."""
        assert calculator.compute_reward(-1, 0) == pytest.approx(-0.5)
        assert calculator.compute_reward(0, 99) == pytest.approx(-0.5)
        assert calculator.compute_reward(5, 0) == pytest.approx(-0.5)

    def test_no_class_weights_default_to_one(self):
        """Without class_weights, correct reward = reward_correct * 1.0."""
        calc = RegimeRewardCalculator(reward_correct=2.0, reward_wrong=-1.0)
        assert calc.compute_reward(TREND_UP, TREND_UP) == pytest.approx(2.0)
        assert calc.compute_reward(
            EXHAUSTION, EXHAUSTION) == pytest.approx(2.0)

    def test_from_config(self):
        """Test the from_config classmethod."""
        class FakeConfig:
            reward_correct = 1.0
            reward_wrong = -0.5
            reward_matrix_enabled = False
            class_weights = {"PREDICT_TREND_UP": 1.5}

        calc = RegimeRewardCalculator.from_config(FakeConfig())
        assert calc.compute_reward(TREND_UP, TREND_UP) == pytest.approx(1.5)


# =============================================================================
# FeatureRingBuffer Tests
# =============================================================================

class TestFeatureRingBuffer:

    def test_warmup_no_settlement(self, buffer):
        """During warmup, push_and_settle returns None."""
        z = np.zeros(16)
        for i in range(5):  # horizon=5, need 6 entries for first settlement
            result = buffer.push_and_settle(
                "BTCUSDT", float(i), z, 0, {"price": i})
            assert result is None

    def test_first_settlement_at_horizon_plus_one(self, buffer):
        """First SettledEpisode appears when buffer has horizon+1 entries."""
        z = np.zeros(16)
        # Push horizon_bars + 1 = 6 entries
        for i in range(6):
            result = buffer.push_and_settle(
                "BTCUSDT", float(i), z, i % 5, {"price": i})
            if i < 5:
                assert result is None
            else:
                assert result is not None
                assert isinstance(result, SettledEpisode)

    def test_settled_episode_pairs_correctly(self, buffer):
        """Settled episode pairs oldest (t) with newest (t+H) features."""
        z = np.zeros(16)
        features_list = [{"price": i, "delta_price": i * 0.01}
                         for i in range(7)]

        results = []
        for i in range(7):
            r = buffer.push_and_settle(
                "BTCUSDT", float(i), z, i, features_list[i])
            if r is not None:
                results.append(r)

        # Should have 2 settlements (entries 6 and 7 trigger them)
        assert len(results) == 2

        # First settlement: t=0, t+H=5
        ep0 = results[0]
        assert ep0.timestamp_t == 0.0
        assert ep0.timestamp_t_plus_h == 5.0
        assert ep0.features_t["price"] == 0
        assert ep0.features_t_plus_h["price"] == 5
        assert ep0.predicted_action == 0

        # Second settlement: t=1, t+H=6
        ep1 = results[1]
        assert ep1.timestamp_t == 1.0
        assert ep1.timestamp_t_plus_h == 6.0
        assert ep1.features_t["price"] == 1
        assert ep1.features_t_plus_h["price"] == 6
        assert ep1.predicted_action == 1

    def test_multi_symbol_independence(self, buffer):
        """Each symbol has its own independent buffer."""
        z = np.zeros(16)
        # Push 6 entries for BTC
        for i in range(6):
            buffer.push_and_settle("BTCUSDT", float(i), z, 0, {"sym": "BTC"})

        # ETH is still warming up
        assert buffer.warmup_remaining("ETHUSDT") == 6
        r = buffer.push_and_settle("ETHUSDT", 0.0, z, 0, {"sym": "ETH"})
        assert r is None
        assert buffer.warmup_remaining("ETHUSDT") == 5

    def test_warmup_remaining(self, buffer):
        """warmup_remaining decreases correctly."""
        z = np.zeros(16)
        assert buffer.warmup_remaining("BTCUSDT") == 6  # horizon+1

        for i in range(3):
            buffer.push_and_settle("BTCUSDT", float(i), z, 0, {})

        assert buffer.warmup_remaining("BTCUSDT") == 3

    def test_reset_single_symbol(self, buffer):
        """reset(symbol) clears only that symbol."""
        z = np.zeros(16)
        for i in range(3):
            buffer.push_and_settle("BTCUSDT", float(i), z, 0, {})
            buffer.push_and_settle("ETHUSDT", float(i), z, 0, {})

        buffer.reset("BTCUSDT")
        assert buffer.warmup_remaining("BTCUSDT") == 6
        assert buffer.warmup_remaining("ETHUSDT") == 3

    def test_reset_all(self, buffer):
        """reset() clears all symbols."""
        z = np.zeros(16)
        for i in range(3):
            buffer.push_and_settle("BTCUSDT", float(i), z, 0, {})

        buffer.reset()
        assert buffer.symbols == []

    def test_invalid_horizon(self):
        """horizon_bars < 1 raises ValueError."""
        with pytest.raises(ValueError, match="horizon_bars must be >= 1"):
            FeatureRingBuffer(horizon_bars=0)

    def test_latent_z_preserved(self, buffer):
        """Latent z vector is correctly stored and returned in settlement."""
        z_values = [np.random.randn(16) for _ in range(6)]
        for i in range(6):
            result = buffer.push_and_settle(
                "BTC", float(i), z_values[i], 0, {"i": i})
            if result is not None:
                np.testing.assert_array_equal(result.latent_z_t, z_values[0])

    def test_symbol_property(self, buffer):
        """symbols property lists active symbols."""
        z = np.zeros(16)
        buffer.push_and_settle("BTCUSDT", 0.0, z, 0, {})
        buffer.push_and_settle("ETHUSDT", 0.0, z, 0, {})
        assert sorted(buffer.symbols) == ["BTCUSDT", "ETHUSDT"]


# =============================================================================
# OracleConfig Tests (integration with config_models.py)
# =============================================================================

class TestOracleConfig:

    def test_config_loads_from_yaml(self, tmp_path):
        """OracleConfig can be constructed from parsed YAML data."""
        from apps.reference.domains.neocortex.config_models import OracleConfig

        data = {
            "horizon_bars": 5,
            "high_vol_threshold": 0.8,
            "exhaustion_vol_now_threshold": 0.5,
            "exhaustion_vol_future_threshold": 0.1,
            "trend_delta_pct_threshold": 0.0002,
            "trend_ema_threshold": 0.0008,
            "mr_delta_pct_threshold": 0.0001,
            "reward_correct": 1.0,
            "reward_wrong": -0.5,
            "reward_matrix_enabled": False,
            "reward_matrix": None,
            "class_weights": {
                "PREDICT_TREND_UP": 1.5,
                "PREDICT_TREND_DOWN": 1.5,
                "PREDICT_MEAN_REVERSION": 0.7,
                "PREDICT_HIGH_VOLATILITY": 2.0,
                "PREDICT_EXHAUSTION": 2.5,
            },
        }
        cfg = OracleConfig(**data)
        assert cfg.horizon_bars == 5
        assert cfg.class_weights["PREDICT_EXHAUSTION"] == 2.5
        assert cfg.reward_matrix_enabled is False
        assert cfg.high_vol_threshold == 0.8

    def test_extra_field_forbidden(self):
        """extra='forbid' rejects unknown fields."""
        from apps.reference.domains.neocortex.config_models import OracleConfig
        from pydantic import ValidationError

        data = {
            "horizon_bars": 5,
            "high_vol_threshold": 0.8,
            "exhaustion_vol_now_threshold": 0.5,
            "exhaustion_vol_future_threshold": 0.1,
            "trend_delta_pct_threshold": 0.0002,
            "trend_ema_threshold": 0.0008,
            "mr_delta_pct_threshold": 0.0001,
            "reward_correct": 1.0,
            "reward_wrong": -0.5,
            "class_weights": {},
            "unknown_field": 42,
        }
        with pytest.raises(ValidationError):
            OracleConfig(**data)

    def test_ppo_config_reward_mode(self):
        """PPOConfig accepts reward_mode field."""
        from apps.reference.domains.neocortex.config_models import PPOConfig

        cfg = PPOConfig(
            state_dim=16,
            action_dim=5,
            hidden_dims=[256, 128],
            objective_split_enforced=True,
            policy_training_mode="disabled",
            learning_rate=0.0003,
            gamma=0.99,
            gae_lambda=0.95,
            clip_epsilon=0.2,
            entropy_coef=0.01,
            max_grad_norm=0.5,
            numerical_safety={
                "gradient_clip_threshold": 1.0,
                "on_invalid": "sanitize",
            },
            rollout_length=2048,
            num_epochs=10,
            minibatch_size=64,
            reward_mode="regime_oracle",
        )
        assert cfg.reward_mode == "regime_oracle"
        assert cfg.action_dim == 5

    def test_ppo_config_accepts_explicit_pnl_reward_mode(self):
        """PPOConfig accepts explicit pnl reward mode."""
        from apps.reference.domains.neocortex.config_models import PPOConfig

        cfg = PPOConfig(
            state_dim=16,
            action_dim=3,
            hidden_dims=[256, 128],
            reward_mode="pnl",
            objective_split_enforced=True,
            policy_training_mode="disabled",
            learning_rate=0.0003,
            gamma=0.99,
            gae_lambda=0.95,
            clip_epsilon=0.2,
            entropy_coef=0.01,
            max_grad_norm=0.5,
            numerical_safety={
                "gradient_clip_threshold": 1.0,
                "on_invalid": "sanitize",
            },
            rollout_length=2048,
            num_epochs=10,
            minibatch_size=64,
        )
        assert cfg.reward_mode == "pnl"


# =============================================================================
# Integration: Labeler + Calculator pipeline
# =============================================================================

class TestOraclePipeline:

    def test_end_to_end_correct_prediction(self, labeler, calculator):
        """Full pipeline: features -> label -> reward for correct prediction."""
        features_t = _make_features(price=100.0, volatility_state=0.0)
        features_t_h = _make_features(
            delta_price=0.05, ema_bias=0.502, volatility_state=0.3,
        )
        realized = labeler.compute_realized_regime(features_t, features_t_h)
        assert realized == TREND_UP

        reward = calculator.compute_reward(TREND_UP, realized)
        assert reward == pytest.approx(1.5)  # 1.0 * 1.5 class weight

    def test_end_to_end_wrong_prediction(self, labeler, calculator):
        """Full pipeline: wrong prediction gets penalty."""
        features_t = _make_features(price=100.0, volatility_state=0.0)
        features_t_h = _make_features(
            delta_price=0.05, ema_bias=0.502, volatility_state=0.3,
        )
        realized = labeler.compute_realized_regime(features_t, features_t_h)
        assert realized == TREND_UP

        reward = calculator.compute_reward(TREND_DOWN, realized)
        assert reward == pytest.approx(-0.5)

    def test_buffer_plus_labeler_pipeline(self, labeler, calculator):
        """Full pipeline: buffer -> settle -> label -> reward."""
        buf = FeatureRingBuffer(horizon_bars=3)
        z = np.zeros(16)

        # Simulate 4 bars: calm -> vol spike
        features_sequence = [
            _make_features(price=100.0, volatility_state=0.1),  # t=0
            _make_features(price=100.0, volatility_state=0.2),  # t=1
            _make_features(price=100.0, volatility_state=0.3),  # t=2
            # t=3 (vol spike)
            _make_features(price=100.0, volatility_state=0.9),
        ]

        settled = None
        for i, feat in enumerate(features_sequence):
            settled = buf.push_and_settle(
                "BTC", float(i), z, HIGH_VOLATILITY, feat)

        # Settlement: t=0 -> t+3
        assert settled is not None
        realized = labeler.compute_realized_regime(
            settled.features_t, settled.features_t_plus_h
        )
        # vol_state_future = 0.9 > 0.8 -> HIGH_VOL
        assert realized == HIGH_VOLATILITY
        assert settled.predicted_action == HIGH_VOLATILITY

        reward = calculator.compute_reward(settled.predicted_action, realized)
        assert reward == pytest.approx(2.0)  # 1.0 * 2.0 class weight
