"""
Test: Ensemble Features Plumbing (ALPHA-A1)

Verifies that features are correctly passed through the ensemble to individual models.
This was a critical bug where features was always empty {}.
"""

import pytest
from decimal import Decimal
from typing import Dict, Any, Optional, List
from unittest.mock import Mock, patch

from apps.reference.domains.alpha_search.ensemble import EnsembleModel, EnsembleConfig
from apps.reference.domains.alpha_search.alpha_model import AlphaModel, AlphaScore


class MockAlphaModel(AlphaModel):
    """Mock model that records what features it receives."""
    
    def __init__(self, name: str = "mock_model"):
        self._model_name = name  # Set BEFORE super().__init__() calls get_model_name()
        self._received_features: Dict[str, Any] = {}
        self._received_symbol: str = ""
        super().__init__({})
    
    def get_model_name(self) -> str:
        return self._model_name
    
    def get_required_features(self) -> List[str]:
        return ["rsi_14", "bb_position"]
    
    def calculate_alpha(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        features: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AlphaScore:
        # Record what was passed
        self._received_features = features.copy()
        self._received_symbol = symbol
        
        # Return non-trivial score if features present
        score = Decimal("0.5") if features.get("rsi_14") else Decimal("0.0")
        
        return AlphaScore(
            model_name=self._model_name,
            symbol=symbol,
            score=score,
            confidence=Decimal("0.7"),
            features_used=list(features.keys()),
            why=[f"received_{len(features)}_features"]
        )


class TestEnsembleFeaturesPassing:
    """Test suite for ALPHA-A1: features plumbing fix."""
    
    def test_calculate_alpha_passes_features_to_models(self):
        """CRITICAL: calculate_alpha must pass features to underlying models."""
        # Setup
        mock_model = MockAlphaModel("test_model")
        config = EnsembleConfig()
        ensemble = EnsembleModel(config=config, models={"test": mock_model})
        
        test_features = {
            "rsi_14": 25.0,
            "bb_position": 0.2,
            "volume_ratio": 1.5
        }
        
        # Execute
        result = ensemble.calculate_alpha(
            symbol="BTCUSDT",
            market_data={"close": 50000.0},
            features=test_features,
            context={}
        )
        
        # Verify: model received actual features, not empty dict
        assert mock_model._received_features != {}, "Model received empty features dict!"
        assert mock_model._received_features == test_features
        assert mock_model._received_symbol == "BTCUSDT"
        
    def test_generate_signal_passes_features_to_models(self):
        """generate_signal with features arg must propagate to models."""
        import pandas as pd
        
        mock_model = MockAlphaModel("test_model")
        config = EnsembleConfig()
        ensemble = EnsembleModel(config=config, models={"test": mock_model})
        
        test_features = {
            "rsi_14": 30.0,
            "bb_position": 0.8,
            "stoch_k": 75.0
        }
        
        # Execute via generate_signal
        result = ensemble.generate_signal(
            market_data=pd.DataFrame([{"close": 50000.0}]),
            portfolio_state=None,
            symbol="ETHUSDT",
            features=test_features
        )
        
        # Verify
        assert mock_model._received_features == test_features
        
    def test_empty_features_still_works(self):
        """Empty features should not crash, just produce low-confidence scores."""
        mock_model = MockAlphaModel("test_model")
        config = EnsembleConfig()
        ensemble = EnsembleModel(config=config, models={"test": mock_model})
        
        # Empty features
        result = ensemble.calculate_alpha(
            symbol="BTCUSDT",
            market_data={"close": 50000.0},
            features={},  # Empty
            context={}
        )
        
        # Should work but model receives empty
        assert mock_model._received_features == {}
        # Score should reflect lack of features
        # (model returns 0 if no rsi_14)
        
    def test_mean_reversion_model_receives_features(self):
        """Integration test: MeanReversionAlphaModel actually sees features."""
        from apps.reference.domains.alpha_search.models.mean_reversion import MeanReversionAlphaModel
        
        mr_model = MeanReversionAlphaModel()
        config = EnsembleConfig()
        ensemble = EnsembleModel(config=config, models={"mr": mr_model})
        
        # Features that should produce a buy signal (oversold)
        oversold_features = {
            "bb_position": 0.1,  # Near lower band
            "bb_width": 0.05,
            "rsi_14": 25,        # Oversold
            "price_sma_20_deviation": -0.03,  # Below SMA
            "volume_sma_ratio": 1.8,  # High volume
            "stoch_k": 15,
            "stoch_d": 20
        }
        
        result = ensemble.calculate_alpha(
            symbol="BTCUSDT",
            market_data={"close": 50000.0},
            features=oversold_features,
            context={}
        )
        
        # Should get a BUY signal (negative score in mean reversion inverted logic)
        # Mean reversion: low bb_position + low RSI = buy signal (positive score)
        assert result.score != Decimal("0.0"), "MeanReversion should produce non-zero score with valid features"
        assert result.confidence > Decimal("0.0")


class TestEnsembleSymbolPassing:
    """Test that symbol is correctly passed to models."""
    
    def test_symbol_passed_to_model(self):
        """Symbol should reach the underlying model."""
        mock_model = MockAlphaModel("test_model")
        config = EnsembleConfig()
        ensemble = EnsembleModel(config=config, models={"test": mock_model})
        
        result = ensemble.calculate_alpha(
            symbol="SOLUSDT",
            market_data={"close": 100.0},
            features={"rsi_14": 50},
            context={}
        )
        
        assert mock_model._received_symbol == "SOLUSDT"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
