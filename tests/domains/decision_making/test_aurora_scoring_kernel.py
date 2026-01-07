"""
Tests for AuroraScoringKernel — Pure Scoring Logic.

Verifies:
1. Score calculation with various feature inputs
2. Threshold adjustments from regime
3. Side bias penalties
4. Side determination (buy/sell/neutral)
5. Deferred states for missing data
"""
import pytest
import decimal
from decimal import Decimal

from apps.reference.domains.decision_making.aurora_scoring_kernel import (
    AuroraScoringKernel,
    ScoringResult,
    SideBiasState,
)


class TestAuroraScoringKernelBasic:
    """Basic scoring kernel tests."""

    @pytest.fixture
    def base_config(self):
        """Common configuration for tests."""
        return {
            "symbol": "BTCUSDT",
            "features": {
                "obi": 0.5,
                "tfi": 0.3,
                "delta_price": 100,  # raw USD delta
                "ema_bias": 0.1,
                "volume_spike": 0.0,
                "volatility_state": 0.0,
                "depth_imbalance": 0.2,
                "macro_sync": 0.0,
            },
            "warmup_readiness": {
                "obi": True,
                "tfi": True,
                "delta_price": True,
                "ema_bias": True,
            },
            "price": Decimal("50000"),
            "signal_weights": {
                "obi": 0.3,
                "tfi": 0.2,
                "delta_price": 0.15,
                "ema_bias": 0.15,
                "volume_spike": 0.1,
                "volatility_state": 0.05,
                "depth_imbalance": 0.05,
            },
            "feature_neutrals": {
                "obi": 0.0,
                "tfi": 0.0,
                "delta_price": 0.0,
                "ema_bias": 0.0,
            },
            "essential_features": ["obi", "tfi", "delta_price", "ema_bias"],
            "base_threshold": Decimal("0.1"),
            "regime_name": "TREND_UP",
            "regime_thresholds": {
                "TREND_UP": 1.0,
                "TREND_DOWN": 1.0,
                "HIGH_VOLATILITY": 1.2,
                "DEFAULT": 1.0,
            },
            "direction_strength_cfg": {
                "directional_features": ["obi", "tfi", "delta_price", "ema_bias"],
                "strength_features": ["volume_spike", "volatility_state"],
                "strength_alpha": 0.5,
                "strength_cap": 1.5,
            },
            "delta_price_cap_pct": Decimal("0.005"),
        }

    def test_kernel_returns_scoring_result(self, base_config):
        """Kernel should return ScoringResult dataclass."""
        result = AuroraScoringKernel.compute(
            **base_config,
            side_bias_state=None,
        )
        assert isinstance(result, ScoringResult)
        assert isinstance(result.score, Decimal)
        assert result.side in ("buy", "sell", "")

    def test_neutral_signal_returns_empty_side(self, base_config):
        """Signal below threshold should return empty side."""
        # Set features to near-zero
        base_config["features"] = {
            "obi": 0.01,
            "tfi": 0.01,
            "delta_price": 0,
            "ema_bias": 0.0,
            "volume_spike": 0.0,
            "volatility_state": 0.0,
            "depth_imbalance": 0.0,
            "macro_sync": 0.0,
        }
        result = AuroraScoringKernel.compute(
            **base_config,
            side_bias_state=None,
        )
        # Should be neutral due to low signal
        assert result.side == "" or abs(result.score) < result.thr_buy

    def test_missing_essential_features_defers(self, base_config):
        """Missing essential features in readiness should defer."""
        base_config["warmup_readiness"] = {"obi": True}  # Missing tfi, delta_price, ema_bias
        result = AuroraScoringKernel.compute(
            **base_config,
            side_bias_state=None,
        )
        assert result.deferred is True
        assert "MISSING_READY_KEYS" in str(result.defer_reason)


class TestSideBiasPenalty:
    """Tests for side bias penalty calculation."""

    @pytest.fixture
    def neutral_config(self):
        """Configuration that would produce a signal."""
        return {
            "symbol": "BTCUSDT",
            "features": {"obi": 0.5, "tfi": 0.3, "delta_price": 0, "ema_bias": 0.2},
            "warmup_readiness": {"obi": True, "tfi": True, "delta_price": True, "ema_bias": True},
            "price": Decimal("50000"),
            "signal_weights": {"obi": 0.4, "tfi": 0.3, "delta_price": 0.15, "ema_bias": 0.15},
            "feature_neutrals": {"obi": 0.0, "tfi": 0.0, "delta_price": 0.0, "ema_bias": 0.0},
            "essential_features": ["obi", "tfi", "delta_price", "ema_bias"],
            "base_threshold": Decimal("0.1"),
            "regime_name": "DEFAULT",
            "regime_thresholds": {"DEFAULT": 1.0},
            "direction_strength_cfg": {
                "directional_features": ["obi", "tfi", "ema_bias"],
                "strength_features": [],
                "strength_alpha": 0.5,
                "strength_cap": 1.5,
            },
            "delta_price_cap_pct": Decimal("0.005"),
        }

    def test_sell_overload_penalizes_sell_threshold(self, neutral_config):
        """Too many sells should increase sell threshold."""
        side_bias = SideBiasState(
            buy_count=5,
            sell_count=20,  # 80% sells, target is 72%
            window_sec=420,
            target_ratio=0.72,
            penalty_factor=0.25,
            min_intents=18,
        )
        result = AuroraScoringKernel.compute(
            **neutral_config,
            side_bias_state=side_bias,
        )
        assert result.sell_bias_mult > Decimal("1.0")
        assert result.buy_bias_mult == Decimal("1.0")

    def test_buy_overload_penalizes_buy_threshold(self, neutral_config):
        """Too many buys should increase buy threshold."""
        side_bias = SideBiasState(
            buy_count=20,  # 80% buys
            sell_count=5,
            window_sec=420,
            target_ratio=0.72,
            penalty_factor=0.25,
            min_intents=18,
        )
        result = AuroraScoringKernel.compute(
            **neutral_config,
            side_bias_state=side_bias,
        )
        assert result.buy_bias_mult > Decimal("1.0")
        assert result.sell_bias_mult == Decimal("1.0")

    def test_below_min_intents_no_penalty(self, neutral_config):
        """Below min_intents, no bias penalty should be applied."""
        side_bias = SideBiasState(
            buy_count=2,
            sell_count=8,  # Would be 80% sells, but only 10 total < 18 min
            window_sec=420,
            target_ratio=0.72,
            penalty_factor=0.25,
            min_intents=18,
        )
        result = AuroraScoringKernel.compute(
            **neutral_config,
            side_bias_state=side_bias,
        )
        assert result.buy_bias_mult == Decimal("1.0")
        assert result.sell_bias_mult == Decimal("1.0")


class TestRegimeThresholds:
    """Tests for regime-based threshold adjustments."""

    @pytest.fixture
    def base_config(self):
        return {
            "symbol": "BTCUSDT",
            "features": {"obi": 0.5, "tfi": 0.3, "delta_price": 0, "ema_bias": 0.1},
            "warmup_readiness": {"obi": True, "tfi": True, "delta_price": True, "ema_bias": True},
            "price": Decimal("50000"),
            "signal_weights": {"obi": 0.4, "tfi": 0.3, "delta_price": 0.15, "ema_bias": 0.15},
            "feature_neutrals": {"obi": 0.0, "tfi": 0.0, "delta_price": 0.0, "ema_bias": 0.0},
            "essential_features": ["obi", "tfi", "delta_price", "ema_bias"],
            "base_threshold": Decimal("0.1"),
            "direction_strength_cfg": {
                "directional_features": ["obi", "tfi"],
                "strength_features": [],
                "strength_alpha": 0.5,
                "strength_cap": 1.5,
            },
            "delta_price_cap_pct": Decimal("0.005"),
        }

    def test_high_volatility_increases_threshold(self, base_config):
        """HIGH_VOLATILITY regime should increase threshold."""
        base_config["regime_name"] = "HIGH_VOLATILITY"
        base_config["regime_thresholds"] = {
            "HIGH_VOLATILITY": 1.5,
            "DEFAULT": 1.0,
        }
        result = AuroraScoringKernel.compute(
            **base_config,
            side_bias_state=None,
        )
        # Threshold should be 0.1 * 1.5 = 0.15
        assert result.threshold_factor == Decimal("1.5")
        assert result.thr_buy == Decimal("0.15")

    def test_missing_regime_uses_default(self, base_config):
        """Unknown regime should use DEFAULT threshold."""
        base_config["regime_name"] = "UNKNOWN_REGIME"
        base_config["regime_thresholds"] = {
            "TREND_UP": 1.0,
            "DEFAULT": 1.1,
        }
        result = AuroraScoringKernel.compute(
            **base_config,
            side_bias_state=None,
        )
        assert result.threshold_factor == Decimal("1.1")

    def test_missing_default_defers(self, base_config):
        """Missing DEFAULT threshold should defer."""
        base_config["regime_name"] = "UNKNOWN_REGIME"
        base_config["regime_thresholds"] = {
            "TREND_UP": 1.0,
            # No DEFAULT
        }
        result = AuroraScoringKernel.compute(
            **base_config,
            side_bias_state=None,
        )
        assert result.deferred is True
        assert "MISSING_REGIME_THRESHOLD" in str(result.defer_reason)
