
import pytest
from decimal import Decimal
from apps.reference.domains.alpha_search.models.momentum import MomentumAlphaModel
from apps.reference.domains.alpha_search.models.mean_reversion import MeanReversionAlphaModel
from apps.reference.domains.alpha_search.models.volatility import VolatilityAlphaModel

class TestModelsDeterminism:

    def test_momentum_output_range(self):
        """Test that Momentum model clamps output to [-1, 1] even with extreme inputs."""
        model = MomentumAlphaModel()
        
        # Extreme bullish inputs (Momentum features are % change, e.g. 0.01 = 1%)
        features_bull = {
            "price_momentum_5m": 0.05,  # 5% up
            "price_momentum_1h": 0.10,  # 10% up
            "price_momentum_1d": 0.20,  # 20% up
            "volume_momentum_5m": 0.5,
            "rsi_14": 60,               # Strong but not overbought
            "macd_signal": 100
        }
        score = model.calculate_alpha("BTCUSDT", {}, features_bull)
        assert -1.0 <= score.score <= 1.0
        assert score.score > 0 # Should be bullish (positive)

        # Extreme bearish inputs
        features_bear = {
            "price_momentum_5m": -0.05,
            "price_momentum_1h": -0.10,
            "price_momentum_1d": -0.20,
            "volume_momentum_5m": 0.5, # High volume supports move
            "rsi_14": 40,
            "macd_signal": -100
        }
        score = model.calculate_alpha("BTCUSDT", {}, features_bear)
        assert -1.0 <= score.score <= 1.0
        assert score.score < 0 # Should be bearish (negative)

    def test_mean_reversion_determinism(self):
        """Test strict determinism for Mean Reversion model."""
        model = MeanReversionAlphaModel()
        
        # Scenario: Price slightly below SMA but within bands
        # bb_position: 0.2 means near lower band -> OVERSOLD -> BUY SIGNAL
        # In MeanReversion model: Buy is NEGATIVE score (-1 = Strong Buy)
        features = {
            "bb_position": 0.2, 
            "bb_width": 0.1,
            "rsi_14": 30, # Oversold
            "price_sma_20_deviation": -0.05,
            "volume_sma_ratio": 1.5,
            "stoch_k": 10,
            "stoch_d": 15
        }
        
        score1 = model.calculate_alpha("ETHUSDT", {}, features)
        score2 = model.calculate_alpha("ETHUSDT", {}, features)
        
        # Determinism check
        assert score1.score == score2.score
        assert score1.confidence == score2.confidence
        # Mean reversion model uses positive score for buy pressure in this contract.
        assert score1.score > 0

    def test_volatility_clamping(self):
        """Test Volatility model handles zero/extreme values gracefully."""
        model = VolatilityAlphaModel()
        
        # Zero/Missing-like values (defaults covered in code, but explicit features here)
        features = {
            "atr_ratio": 0.0,
            "bb_width": 0.0,
            "bb_width_change": 0.0,
            "realized_volatility_1h": 0.0,
            "realized_volatility_1d": 0.0,
            "volume_volatility_ratio": 0.0,
            "price_range_ratio": 0.0
        }
        
        score = model.calculate_alpha("SOLUSDT", {}, features)
        assert -1.0 <= score.score <= 1.0
        # Check validation logic doesn't crash on 0
        
        # Extreme volatility
        features_extreme = {
            "atr_ratio": 50.0, # Massive ATR expansion
            "bb_width": 10.0,
            "bb_width_change": 1.0, # Doubling
            "realized_volatility_1h": 0.5,
            "realized_volatility_1d": 0.1,
            "volume_volatility_ratio": 5.0,
            "price_range_ratio": 5.0
        }
        score_ext = model.calculate_alpha("SOLUSDT", {}, features_extreme)
        assert -1.0 <= score_ext.score <= 1.0
        # Likely high positive score (breakout)
        assert score_ext.score > 0

    def test_model_initialization(self):
        """Ensure models initialize without config and have correct names."""
        m1 = MomentumAlphaModel()
        assert m1.get_model_name() == "momentum_v1"
        
        m2 = MeanReversionAlphaModel()
        assert m2.get_model_name() == "mean_reversion_v1"
        
        m3 = VolatilityAlphaModel()
        assert m3.get_model_name() == "volatility_v1"
