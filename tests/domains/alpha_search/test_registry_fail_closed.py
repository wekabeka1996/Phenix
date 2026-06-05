
import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal
from apps.reference.domains.alpha_search.alpha_model import AlphaModelRegistry, AlphaModel, AlphaScore

class BrokenModel(AlphaModel):
    def get_model_name(self) -> str:
        return "broken_model"
    
    def calculate_alpha(self, symbol, market_data, features, context=None) -> AlphaScore:
        raise ValueError("Simulated crash")
        
    def get_required_features(self):
        return ["price"]

class GreedyModel(AlphaModel):
    def get_model_name(self) -> str:
        return "greedy_model"
    
    def calculate_alpha(self, symbol, market_data, features, context=None) -> AlphaScore:
        return AlphaScore(
            model_name=self.name,
            symbol=symbol,
            score=Decimal("0.5"),
            confidence=Decimal("1.0"),
            why=["Because I said so"]
        )

    def get_required_features(self):
        return ["required_feature"]

class TestRegistryFailClosed:
    
    @pytest.fixture
    def registry(self):
        return AlphaModelRegistry()

    def test_warmup_skip_empty_features(self, registry):
        """Test that empty features result in empty list (warmup)."""
        # Register a model that requires features
        registry.register(GreedyModel())
        
        # Call with empty features
        scores = registry.calculate_all_alpha("BTCUSDT", {}, {}, {})
        
        # Should return empty list because logic checks is_ready -> returns False
        assert scores == []

    def test_missing_required_feature_skip(self, registry):
        """Test that missing required feature prevents model execution."""
        model = GreedyModel()
        registry.register(model)
        
        # Provide wrong features
        features = {"other_feature": 100}
        
        scores = registry.calculate_all_alpha("BTCUSDT", {}, features, {})
        assert scores == []

    @patch("apps.reference.domains.alpha_search.alpha_model.inc_alpha_model_error")
    @patch("apps.reference.domains.alpha_search.alpha_model.LOG")
    def test_model_exception_isolation(self, mock_log, mock_inc_metric, registry):
        """Test that one broken model does not stop others and metrics are incremented."""
        broken = BrokenModel()
        working = GreedyModel()
        
        registry.register(broken)
        registry.register(working)
        
        # Provide features for both
        features = {"price": 100, "required_feature": 1}
        
        scores = registry.calculate_all_alpha("BTCUSDT", {}, features, {})
        
        # Expect 1 score (from working model)
        assert len(scores) == 1
        assert scores[0].model_name == "greedy_model"
        
        # Verify metric increment
        mock_inc_metric.assert_called_with("broken_model")
        # Verify logging
        mock_log.exception.assert_called()
