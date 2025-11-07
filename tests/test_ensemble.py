"""
Tests for Ensemble Model
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from apps.reference.domains.alpha_search.ensemble import (
    EnsembleModel,
    EnsembleConfig,
    EnsembleWeights
)
from apps.reference.domains.alpha_search.alpha_model import AlphaScore


class TestEnsembleWeights:
    """Test EnsembleWeights functionality."""

    def test_initialization(self):
        """Test weights initialization."""
        weights = EnsembleWeights()
        assert weights.model_weights == {}
        assert weights.last_updated is None
        assert weights.performance_score == 0.0

    def test_normalize(self):
        """Test weight normalization."""
        weights = EnsembleWeights()
        weights.model_weights = {"model1": 2.0, "model2": 3.0}
        weights.normalize()

        assert abs(weights.model_weights["model1"] - 0.4) < 0.001
        assert abs(weights.model_weights["model2"] - 0.6) < 0.001


class TestEnsembleModel:
    """Test EnsembleModel functionality."""

    @pytest.fixture
    def ensemble_config(self):
        """Create ensemble configuration."""
        return EnsembleConfig(
            rebalance_frequency_days=7,
            min_weight=0.0,
            max_weight=1.0,
            performance_window_days=30,
            risk_adjustment=True
        )

    @pytest.fixture
    def mock_models(self):
        """Create mock alpha models."""
        model1 = Mock()
        model1.name = "momentum"
        model1.calculate_alpha.return_value = AlphaScore(
            model_name="momentum",
            symbol="BTCUSDT",
            score=Decimal("0.8"),
            confidence=Decimal("0.7"),
            features_used=["price", "volume"],
            why=["strong_uptrend"]
        )

        model2 = Mock()
        model2.name = "mean_reversion"
        model2.calculate_alpha.return_value = AlphaScore(
            model_name="mean_reversion",
            symbol="BTCUSDT",
            score=Decimal("-0.3"),
            confidence=Decimal("0.6"),
            features_used=["price", "rsi"],
            why=["overbought_condition"]
        )

        return {"momentum": model1, "mean_reversion": model2}

    @pytest.fixture
    def ensemble_model(self, ensemble_config, mock_models):
        """Create ensemble model instance."""
        return EnsembleModel(ensemble_config, mock_models)

    def test_initialization(self, ensemble_config, mock_models):
        """Test ensemble model initialization."""
        model = EnsembleModel(ensemble_config, mock_models)

        assert model.name == "ensemble_2_models"
        assert len(model.models) == 2
        assert len(model.weights.model_weights) == 2
        assert abs(model.weights.model_weights["momentum"] - 0.5) < 0.001
        assert abs(model.weights.model_weights["mean_reversion"] - 0.5) < 0.001

    def test_generate_signal_combined(self, ensemble_model):
        """Test signal generation with combination."""
        market_data = pd.DataFrame({
            "timestamp": [datetime.now()],
            "price": [50000.0],
            "volume": [100.0]
        })

        score = ensemble_model.generate_signal(market_data, symbol="BTCUSDT")

        assert score.symbol == "BTCUSDT"
        assert score.model_name == "ensemble_2_models"
        assert score.confidence > Decimal("0")
        assert len(score.features_used) > 0
        assert len(score.why) > 0

    def test_generate_signal_no_models(self, ensemble_config):
        """Test signal generation with no models."""
        model = EnsembleModel(ensemble_config, {})

        market_data = pd.DataFrame()
        score = model.generate_signal(market_data, symbol="BTCUSDT")

        assert score.score == Decimal("0.0")
        assert score.confidence == Decimal("0.0")
        assert "no_models_available" in score.why

    def test_generate_signal_no_valid_signals(self, ensemble_config):
        """Test signal generation when all models return low confidence."""
        mock_model = Mock()
        mock_model.name = "weak_model"
        mock_model.calculate_alpha.return_value = AlphaScore(
            model_name="weak_model",
            symbol="BTCUSDT",
            score=Decimal("0.1"),
            confidence=Decimal("0.05"),  # Below threshold
            features_used=[],
            why=[]
        )

        model = EnsembleModel(ensemble_config, {"weak": mock_model})
        market_data = pd.DataFrame()

        score = model.generate_signal(market_data, symbol="BTCUSDT")

        assert score.score == Decimal("0.0")
        assert score.confidence == Decimal("0.0")
        assert "no_valid_scores" in score.why

    def test_weight_rebalancing(self, ensemble_model):
        """Test weight rebalancing based on performance."""
        # Simulate some performance data
        ensemble_model.model_performance["momentum"] = [0.8, 0.9, 0.7]
        ensemble_model.model_performance["mean_reversion"] = [0.4, 0.5, 0.3]

        # Force rebalance
        ensemble_model._rebalance_weights()

        # Momentum should get higher weight due to better performance
        assert ensemble_model.weights.model_weights[
            "momentum"] > ensemble_model.weights.model_weights["mean_reversion"]
        assert ensemble_model.weights.last_updated is not None

    def test_add_model(self, ensemble_model):
        """Test adding a new model."""
        new_model = Mock()
        new_model.name = "volatility"

        ensemble_model.add_model("volatility", new_model)

        assert "volatility" in ensemble_model.models
        assert "volatility" in ensemble_model.weights.model_weights
        assert "volatility" in ensemble_model.model_performance

    def test_remove_model(self, ensemble_model):
        """Test removing a model."""
        result = ensemble_model.remove_model("momentum")

        assert result is True
        assert "momentum" not in ensemble_model.models
        assert "momentum" not in ensemble_model.weights.model_weights

    def test_remove_nonexistent_model(self, ensemble_model):
        """Test removing a model that doesn't exist."""
        result = ensemble_model.remove_model("nonexistent")

        assert result is False

    def test_get_model_contributions(self, ensemble_model):
        """Test getting model contributions."""
        contributions = ensemble_model.get_model_contributions()

        assert "weights" in contributions
        assert "performance_scores" in contributions
        assert "last_rebalance" in contributions
        assert "ensemble_performance" in contributions

        assert len(contributions["weights"]) == 2
        assert len(contributions["performance_scores"]) == 2

    def test_get_ensemble_stats(self, ensemble_model):
        """Test getting comprehensive ensemble statistics."""
        stats = ensemble_model.get_ensemble_stats()

        assert stats["num_models"] == 2
        assert len(stats["active_models"]) <= 2
        assert "weights" in stats
        assert "performance" in stats
        assert "config" in stats

    def test_risk_adjustment(self, ensemble_config):
        """Test risk-adjusted weighting."""
        ensemble_config.risk_adjustment = True

        # Create models with different variance
        model1 = Mock()
        model1.name = "stable"
        model1.calculate_alpha.return_value = AlphaScore(
            model_name="stable",
            symbol="BTCUSDT",
            score=Decimal("0.5"),
            confidence=Decimal("0.8"),
            features_used=["price"],
            why=["stable_signal"]
        )

        model2 = Mock()
        model2.name = "volatile"
        model2.calculate_alpha.return_value = AlphaScore(
            model_name="volatile",
            symbol="BTCUSDT",
            score=Decimal("0.5"),
            confidence=Decimal("0.8"),
            features_used=["price"],
            why=["volatile_signal"]
        )

        models = {"stable": model1, "volatile": model2}
        ensemble = EnsembleModel(ensemble_config, models)

        # Simulate performance with different variance
        ensemble.model_performance["stable"] = [
            0.8, 0.81, 0.79]  # Low variance
        ensemble.model_performance["volatile"] = [
            0.8, 0.9, 0.6]   # High variance

        ensemble._rebalance_weights()

        # Stable model should get higher weight due to lower risk
        assert ensemble.weights.model_weights["stable"] > ensemble.weights.model_weights["volatile"]

    def test_min_max_weight_constraints(self, ensemble_config):
        """Test weight constraints."""
        ensemble_config.min_weight = 0.2
        ensemble_config.max_weight = 0.8

        models = {"model1": Mock(), "model2": Mock()}
        ensemble = EnsembleModel(ensemble_config, models)

        # Force extreme performance difference
        ensemble.model_performance["model1"] = [1.0, 1.0, 1.0]
        ensemble.model_performance["model2"] = [0.1, 0.1, 0.1]

        ensemble._rebalance_weights()

        # Check constraints are respected
        for weight in ensemble.weights.model_weights.values():
            assert weight >= ensemble_config.min_weight
            assert weight <= ensemble_config.max_weight

    def test_empty_performance_data(self, ensemble_model):
        """Test handling of empty performance data."""
        # Clear performance data
        ensemble_model.model_performance = {}

        # Should not crash
        ensemble_model._rebalance_weights()

        # Weights should remain unchanged
        assert len(ensemble_model.weights.model_weights) == 2
