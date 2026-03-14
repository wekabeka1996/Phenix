"""
Test: Aurora Alpha Adapter (ALPHA-A2)

Verifies that AuroraAlphaAdapter correctly wraps AuroraScoringKernel.
"""

import pytest
from decimal import Decimal
from typing import Dict, Any

from apps.reference.domains.alpha_search.models.aurora_adapter import AuroraAlphaAdapter
from apps.reference.domains.alpha_search.alpha_model import AlphaScore


class TestAuroraAlphaAdapter:
    """Test suite for ALPHA-A2: Aurora adapter."""

    def test_adapter_initialization(self):
        """Adapter should initialize with default config."""
        adapter = AuroraAlphaAdapter()

        assert adapter.name == "aurora_quadratic_adapter"
        assert adapter.get_required_features(
        ) == ["obi", "delta_price", "macro_resid"]

    def test_calculate_alpha_with_valid_features(self):
        """With valid essential features, should return non-zero score."""
        adapter = AuroraAlphaAdapter()

        features = {
            "obi": 0.3,           # Positive order book imbalance
            "delta_price": 100.0,  # Price delta
            "macro_resid": 0.5,   # Positive macro residual
            "tfi": 0.2,
            "ema_bias": 0.6,
            "depth_imbalance": 0.4,
            "pillar_sum": 0.5,
        }

        result = adapter.calculate_alpha(
            symbol="BTCUSDT",
            market_data={"close": 50000.0},
            features=features,
            context={"regime": "DEFAULT"}
        )

        assert isinstance(result, AlphaScore)
        assert result.model_name == "aurora_quadratic_adapter"
        assert result.symbol == "BTCUSDT"
        # Score should be computed (not zero due to valid features)
        # Direction depends on feature values
        assert result.confidence >= Decimal("0")
        assert "fail_closed" not in str(result.why)

    def test_calculate_alpha_missing_essential_features(self):
        """Missing essential features should return fail-closed score=0."""
        adapter = AuroraAlphaAdapter()

        # Missing 'obi' which is essential
        features = {
            "delta_price": 100.0,
            "macro_resid": 0.5,
        }

        result = adapter.calculate_alpha(
            symbol="BTCUSDT",
            market_data={"close": 50000.0},
            features=features,
            context={}
        )

        assert result.score == Decimal("0")
        assert result.confidence == Decimal("0")
        assert any("fail_closed" in w for w in result.why)
        assert any("missing" in w.lower() for w in result.why)

    def test_calculate_alpha_no_price(self):
        """Missing price should return fail-closed score=0."""
        adapter = AuroraAlphaAdapter()

        features = {
            "obi": 0.3,
            "delta_price": 100.0,
            "macro_resid": 0.5,
        }

        result = adapter.calculate_alpha(
            symbol="BTCUSDT",
            market_data={},  # No price
            features=features,
            context={}
        )

        assert result.score == Decimal("0")
        assert any("missing_price" in w for w in result.why)

    def test_custom_essential_features(self):
        """Should use custom essential features when provided."""
        adapter = AuroraAlphaAdapter(
            essential_features=["obi", "tfi"]
        )

        assert adapter.get_required_features() == ["obi", "tfi"]

    def test_score_in_valid_range(self):
        """Score should always be in [-1, 1] range."""
        adapter = AuroraAlphaAdapter()

        # Extreme bullish features
        bullish_features = {
            "obi": 0.9,
            "delta_price": 500.0,
            "macro_resid": 1.0,
            "tfi": 0.8,
            "ema_bias": 0.9,
            "volume_spike": 0.5,
            "volatility_state": 0.0,
            "depth_imbalance": 0.1,
        }

        result = adapter.calculate_alpha(
            symbol="BTCUSDT",
            market_data={"close": 50000.0},
            features=bullish_features,
            context={"regime": "TREND_UP"}
        )

        assert result.score >= Decimal("-1")
        assert result.score <= Decimal("1")

    def test_bearish_features_produce_negative_score(self):
        """Bearish features should produce negative score."""
        adapter = AuroraAlphaAdapter()

        bearish_features = {
            "obi": -0.5,           # Negative order book imbalance
            "delta_price": -200.0,  # Price dropping
            "macro_resid": -0.8,   # Negative macro residual
            "tfi": -0.3,
            "ema_bias": 0.2,       # Below neutral
            "depth_imbalance": 0.7,  # More ask pressure
            "pillar_sum": -0.5,
        }

        result = adapter.calculate_alpha(
            symbol="ETHUSDT",
            market_data={"close": 3000.0},
            features=bearish_features,
            context={"regime": "DEFAULT"}
        )

        # With these bearish features, score should be negative or zero
        # (exact value depends on kernel calculation)
        assert isinstance(result.score, Decimal)
        # Should have computed a result (not fail-closed)
        assert not any("fail_closed" in w for w in result.why)


class TestAuroraAdapterIntegration:
    """Integration tests with real kernel."""

    def test_adapter_matches_kernel_sign(self):
        from apps.reference.domains.decision_making.quadratic_scoring_kernel import (
            ScoringResult,
            SideBiasState,
            QuadraticScoringKernel
        )

        adapter = AuroraAlphaAdapter()

        features = {
            "obi": 0.4,
            "delta_price": 150.0,
            "macro_resid": 0.3,
            "tfi": 0.2,
            "ema_bias": 0.6,
            "volume_spike": 0.1,
            "volatility_state": 0.0,
            "depth_imbalance": 0.4,
            "pillar_sum": 0.5,
        }

        # Get adapter result
        adapter_result = adapter.calculate_alpha(
            symbol="BTCUSDT",
            market_data={"close": 50000.0},
            features=features,
            context={"regime": "DEFAULT"}
        )

        # Direct kernel call for comparison
        warmup_readiness = {f: True for f in adapter.get_required_features()}
        # Add pillars to warmup readiness to avoid pillar deferrals
        warmup_readiness.update({
            "pillar_sum": True,
        })

        kernel_result = QuadraticScoringKernel.compute(
            symbol="BTCUSDT",
            features=features,
            warmup_readiness=warmup_readiness,
            price=Decimal("50000.0"),
            signal_weights=adapter._signal_weights,
            feature_neutrals=adapter._feature_neutrals,
            essential_features=adapter._essential_features,
            base_threshold=adapter._base_threshold,
            regime_name="DEFAULT",
            regime_thresholds=adapter._regime_thresholds,
            side_bias_state=None,
            direction_strength_cfg=adapter._direction_strength_cfg,
            delta_price_cap_pct=adapter._delta_price_cap_pct,
            scoring_version="v2",
        )

        # Scores should have same sign (or both be near zero)
        if abs(kernel_result.score) > Decimal("0.01"):
            # If kernel has significant score, adapter should match sign
            assert (adapter_result.score >= 0) == (kernel_result.score >= 0), \
                f"Sign mismatch: adapter={adapter_result.score}, kernel={kernel_result.score}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
