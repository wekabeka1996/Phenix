"""
Tests for Alpha Model Framework

Tests cover:
- ABC functionality
- Baseline model implementations
- Registry operations
- Score calculation and validation
"""

import pytest
from decimal import Decimal
from datetime import datetime
import time
from apps.reference.domains.alpha_search import (
    AlphaModel, AlphaScore, AlphaModelRegistry,
    MomentumAlphaModel, MeanReversionAlphaModel, VolatilityAlphaModel
)


class TestAlphaScore:
    """Test AlphaScore model."""

    def test_valid_score_creation(self):
        """Test creating a valid AlphaScore."""
        score = AlphaScore(
            model_name="test_model",
            symbol="BTCUSDT",
            score=Decimal('0.75'),
            confidence=Decimal('0.9'),
            features_used=['feature1', 'feature2'],
            why=['Strong signal', 'Volume confirms']
        )

        assert score.model_name == "test_model"
        assert score.symbol == "BTCUSDT"
        assert score.score == Decimal('0.75')
        assert score.confidence == Decimal('0.9')
        assert score.features_used == ['feature1', 'feature2']
        assert score.why == ['Strong signal', 'Volume confirms']
        assert isinstance(score.timestamp, datetime)

    def test_score_validation(self):
        """Test score field validation."""
        # Valid score
        AlphaScore(
            model_name="test",
            symbol="BTC",
            score=Decimal('1.0'),
            confidence=Decimal('1.0')
        )

        # Invalid score (> 1.0)
        with pytest.raises(ValueError):
            AlphaScore(
                model_name="test",
                symbol="BTC",
                score=Decimal('1.5'),
                confidence=Decimal('1.0')
            )

        # Invalid confidence (> 1.0)
        with pytest.raises(ValueError):
            AlphaScore(
                model_name="test",
                symbol="BTC",
                score=Decimal('0.5'),
                confidence=Decimal('1.2')
            )


class TestAlphaModelABC:
    """Test AlphaModel abstract base class."""

    def test_abstract_methods(self):
        """Test that ABC cannot be instantiated directly."""
        with pytest.raises(TypeError):
            AlphaModel()

    def test_model_metadata(self):
        """Test model metadata generation."""
        model = MomentumAlphaModel()
        metadata = model.get_metadata()

        assert metadata['name'] == 'momentum_v1'
        assert metadata['type'] == 'MomentumAlphaModel'
        assert 'required_features' in metadata
        assert 'config' in metadata

    def test_is_ready(self):
        """Test feature readiness check."""
        model = MomentumAlphaModel()

        # Missing features
        features = {'price_momentum_5m': 0.1}
        assert not model.is_ready(features)

        # All features present
        features = {
            'price_momentum_5m': 0.1,
            'price_momentum_1h': 0.2,
            'price_momentum_1d': 0.15,
            'volume_momentum_5m': 0.05,
            'rsi_14': 55,
            'macd_signal': 0.01
        }
        assert model.is_ready(features)


class TestMomentumAlphaModel:
    """Test Momentum Alpha Model."""

    def test_model_name(self):
        """Test model name."""
        model = MomentumAlphaModel()
        assert model.get_model_name() == "momentum_v1"

    def test_required_features(self):
        """Test required features list."""
        model = MomentumAlphaModel()
        required = model.get_required_features()
        assert 'price_momentum_5m' in required
        assert 'rsi_14' in required
        assert len(required) == 6

    def test_calculate_alpha_upward_momentum(self):
        """Test upward momentum calculation."""
        model = MomentumAlphaModel()

        market_data = {'current_price': 50000}
        features = {
            'price_momentum_5m': 0.02,   # +2%
            'price_momentum_1h': 0.015,  # +1.5%
            'price_momentum_1d': 0.01,   # +1%
            'volume_momentum_5m': 0.03,  # +3% volume
            'rsi_14': 60,
            'macd_signal': 0.005
        }

        score = model.calculate_alpha("BTCUSDT", market_data, features)

        assert score.model_name == "momentum_v1"
        assert score.symbol == "BTCUSDT"
        assert score.score > 0  # Positive momentum
        assert 0 <= score.confidence <= 1
        assert len(score.why) > 0
        assert 'upward' in ' '.join(score.why).lower()

    def test_calculate_alpha_downward_momentum(self):
        """Test downward momentum calculation."""
        model = MomentumAlphaModel()

        market_data = {'current_price': 50000}
        features = {
            'price_momentum_5m': -0.02,   # -2%
            'price_momentum_1h': -0.015,  # -1.5%
            'price_momentum_1d': -0.01,   # -1%
            'volume_momentum_5m': -0.03,  # -3% volume
            'rsi_14': 40,
            'macd_signal': -0.005
        }

        score = model.calculate_alpha("BTCUSDT", market_data, features)

        assert score.score < 0  # Negative momentum
        assert 'downward' in ' '.join(score.why).lower()

    def test_calculate_alpha_neutral(self):
        """Test neutral momentum."""
        model = MomentumAlphaModel()

        market_data = {'current_price': 50000}
        features = {
            'price_momentum_5m': 0.001,
            'price_momentum_1h': -0.001,
            'price_momentum_1d': 0.0005,
            'volume_momentum_5m': 0.0,
            'rsi_14': 50,
            'macd_signal': 0.0
        }

        score = model.calculate_alpha("BTCUSDT", market_data, features)

        assert abs(score.score) < 0.1  # Near neutral
        assert 'neutral' in ' '.join(score.why).lower()


class TestMeanReversionAlphaModel:
    """Test Mean Reversion Alpha Model."""

    def test_model_name(self):
        """Test model name."""
        model = MeanReversionAlphaModel()
        assert model.get_model_name() == "mean_reversion_v1"

    def test_calculate_alpha_oversold(self):
        """Test oversold condition detection."""
        model = MeanReversionAlphaModel()

        market_data = {'current_price': 50000}
        features = {
            'bb_position': 0.1,  # Near lower band
            'bb_width': 0.06,
            'rsi_14': 25,  # Oversold
            'price_sma_20_deviation': -0.03,  # Below SMA
            'volume_sma_ratio': 1.8,  # High volume
            'stoch_k': 15,
            'stoch_d': 20
        }

        score = model.calculate_alpha("BTCUSDT", market_data, features)

        assert score.score < -0.3  # Strong buy signal
        assert 'oversold' in ' '.join(score.why).lower()
        assert 'lower' in ' '.join(score.why).lower()

    def test_calculate_alpha_overbought(self):
        """Test overbought condition detection."""
        model = MeanReversionAlphaModel()

        market_data = {'current_price': 50000}
        features = {
            'bb_position': 0.9,  # Near upper band
            'bb_width': 0.06,
            'rsi_14': 75,  # Overbought
            'price_sma_20_deviation': 0.03,  # Above SMA
            'volume_sma_ratio': 1.6,
            'stoch_k': 85,
            'stoch_d': 80
        }

        score = model.calculate_alpha("BTCUSDT", market_data, features)

        assert score.score > 0.3  # Strong sell signal
        assert 'overbought' in ' '.join(score.why).lower()
        assert 'upper' in ' '.join(score.why).lower()


class TestVolatilityAlphaModel:
    """Test Volatility Alpha Model."""

    def test_model_name(self):
        """Test model name."""
        model = VolatilityAlphaModel()
        assert model.get_model_name() == "volatility_v1"

    def test_calculate_alpha_high_volatility(self):
        """Test high volatility detection."""
        model = VolatilityAlphaModel()

        market_data = {'current_price': 50000}
        features = {
            'atr_14': 1000,
            'atr_ratio': 1.5,  # 50% above average
            'bb_width': 0.08,
            'bb_width_change': 0.01,  # Expanding
            'realized_volatility_1h': 0.05,
            'realized_volatility_1d': 0.03,
            'volume_volatility_ratio': 1.4,
            'price_range_ratio': 1.3
        }

        score = model.calculate_alpha("BTCUSDT", market_data, features)

        assert score.score > 0.3  # High volatility signal
        assert 'expansion' in ' '.join(score.why).lower(
        ) or 'elevated' in ' '.join(score.why).lower()

    def test_calculate_alpha_low_volatility(self):
        """Test low volatility detection."""
        model = VolatilityAlphaModel()

        market_data = {'current_price': 50000}
        features = {
            'atr_14': 500,
            'atr_ratio': 0.7,  # 30% below average
            'bb_width': 0.03,
            'bb_width_change': -0.005,  # Contracting
            'realized_volatility_1h': 0.015,
            'realized_volatility_1d': 0.02,
            'volume_volatility_ratio': 0.8,
            'price_range_ratio': 0.9
        }

        score = model.calculate_alpha("BTCUSDT", market_data, features)

        # Low volatility signal (adjusted threshold)
        assert score.score < -0.05
        assert 'weak' in ' '.join(score.why).lower() or 'contraction' in ' '.join(
            score.why).lower() or 'low' in ' '.join(score.why).lower()


class TestAlphaModelIntegration:
    """Test alpha model integration with DecisionMaking."""

    def test_decision_making_alpha_integration(self):
        """Test that DecisionMaking can initialize and use alpha models."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking

        # Check if alpha models are available
        try:
            from apps.reference.domains.alpha_search.alpha_model import ALPHA_MODELS_AVAILABLE
        except ImportError:
            ALPHA_MODELS_AVAILABLE = False

        # Mock FSM
        class MockFSM:
            def __init__(self):
                self.events = []

            def emit(self, event_type, payload=None, why=None, data_ref=None):
                self.events.append({
                    'type': event_type,
                    'payload': payload,
                    'why': why,
                    'data_ref': data_ref
                })

            def listen(self, event_type, handler):
                pass

        mock_fsm = MockFSM()
        config = {
            'decision': {
                'position_sizing': {'min_position_size_usd': 10, 'liquidity_based_cap_usd': 10000},
                'qos': {'mode': 'defer', 'enforce': False},
                'features': {'ttl_sec': 5}
            },
            'tca_prefs': {
                'max_slippage_bps': 10,
                'max_latency_ms': 500
            },
            'risk_budgets': {
                'trade_cvar95_max_bps': 100,
                'session_cvar95_max_bps': 200
            },
            'instruments': {
                'BTCUSDT': {
                    'step_size': '0.001'
                }
            }
        }

        dm = DecisionMaking(mock_fsm, config)

        # Check that alpha registry is initialized
        if ALPHA_MODELS_AVAILABLE:
            assert dm.alpha_registry is not None
            models = dm.alpha_registry.list_models()
            assert 'momentum_v1' in models
            assert 'mean_reversion_v1' in models
            assert 'volatility_v1' in models
        else:
            # If alpha models are not available, registry should be None
            assert dm.alpha_registry is None

    def test_alpha_score_event_emission(self):
        """Test that alpha scores are emitted as events."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        from vfoundation.core.protocol import Message

        # Check if alpha models are available
        try:
            from apps.reference.domains.alpha_search.alpha_model import ALPHA_MODELS_AVAILABLE
        except ImportError:
            ALPHA_MODELS_AVAILABLE = False

        if not ALPHA_MODELS_AVAILABLE:
            pytest.skip("Alpha models not available")

        # Mock FSM
        class MockFSM:
            def __init__(self):
                self.events = []

            def emit(self, event_type, payload=None, why=None, data_ref=None):
                self.events.append({
                    'type': event_type,
                    'payload': payload,
                    'why': why,
                    'data_ref': data_ref
                })

            def listen(self, event_type, handler):
                pass

        mock_fsm = MockFSM()
        config = {
            'decision': {
                'position_sizing': {'min_position_size_usd': 10, 'liquidity_based_cap_usd': 10000},
                'qos': {'mode': 'defer', 'enforce': False},
                'features': {'ttl_sec': 5}
            },
            'tca_prefs': {
                'max_slippage_bps': 10,
                'max_latency_ms': 500
            },
            'risk_budgets': {
                'trade_cvar95_max_bps': 100,
                'session_cvar95_max_bps': 200
            },
            'instruments': {
                'BTCUSDT': {
                    'step_size': '0.001'
                }
            }
        }

        dm = DecisionMaking(mock_fsm, config)

        # Create mock features event
        features_payload = {
            'symbol': 'BTCUSDT',
            'features': {
                'price': 50000,
                'price_momentum_5m': 0.01,
                'price_momentum_1h': 0.005,
                'price_momentum_1d': 0.002,
                'volume_momentum_5m': 0.02,
                'rsi_14': 55,
                'macd_signal': 0.001,
                'bb_position': 0.6,
                'bb_width': 0.05,
                'price_sma_20_deviation': 0.01,
                'volume_sma_ratio': 1.2,
                'stoch_k': 60,
                'stoch_d': 58,
                'atr_14': 1000,
                'atr_ratio': 1.2,
                'realized_volatility_1h': 0.03,
                'realized_volatility_1d': 0.025,
                'volume_volatility_ratio': 1.1,
                'price_range_ratio': 1.1,
                'bb_width_change': 0.01
            },
            'ts': int(time.time() * 1000)
        }

        mock_message = Message(
            op="EVT",
            verb="FEATURES_CALCULATED",
            src="test",
            dst="decision_making",
            pld=features_payload,
            rid="test-rid"
        )

        # Call on_features
        dm.on_features(mock_message)

        # Check that alpha score event was emitted
        alpha_events = [e for e in mock_fsm.events if e['type']
                        == 'EVT:ALPHA_SCORE_CALCULATED']
        assert len(alpha_events) == 1

        event = alpha_events[0]
        assert event['payload']['symbol'] == 'BTCUSDT'
        assert 'scores' in event['payload']
        # All 3 models should produce scores
        assert len(event['payload']['scores']) == 3
        assert event['why'] == 'alpha_calculation'
        assert len(event['data_ref']) == 3
