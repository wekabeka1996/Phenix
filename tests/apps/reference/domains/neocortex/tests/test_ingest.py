"""
Ingestion Logic Tests
"""

import pytest
import numpy as np
from pydantic import ValidationError
from apps.reference.domains.neocortex.config_models import IngestConfig
from apps.reference.domains.neocortex.logic.ingest.parser import FeatureParser
from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def ingest_config():
    return IngestConfig(
        feature_list=["rsi", "obi", "vol"],
        normalization_method="zscore",
        normalization_window=100,
        buffer_size=1000,
        min_samples_before_ready=10,
        nan_strategy="zero"
    )

@pytest.fixture
def parser(ingest_config):
    return FeatureParser(ingest_config)

# =============================================================================
# TESTS
# =============================================================================

def test_parser_valid_payload(parser):
    """Test parsing of valid string-based payload."""
    payload = {
        "timestamp": 1234567890.0,
        "mid_price": "50000.50",
        "obi": "0.5",
        "features": {
            "rsi": "45.2",
            "obi": "0.5",
            "vol": "1.2"
        }
    }
    
    obs = parser.parse(payload)
    
    assert isinstance(obs, MarketObservation)
    assert obs.ts == 1234567890.0
    assert obs.mid_price == 50000.50
    assert obs.obi == 0.5
    
    # Check vector
    # Order matches config: rsi, obi, vol
    expected = np.array([45.2, 0.5, 1.2], dtype=np.float32)
    np.testing.assert_array_almost_equal(obs.features_vector, expected)

def test_parser_nested_vs_flat(parser):
    """Test robustness to nested vs flat structure."""
    # Flat structure where features are at root
    payload = {
        "ts": 100.0,
        "mid_price": 10.0,
        "rsi": "30.0",
        "obi": "0.1",
        "vol": "0.01"
    }
    
    obs = parser.parse(payload)
    np.testing.assert_array_almost_equal(
        obs.features_vector, 
        np.array([30.0, 0.1, 0.01], dtype=np.float32)
    )

def test_parser_missing_fields_strategy_zero(parser):
    """Test that missing fields default to 0.0 with nan_strategy='zero'."""
    payload = {
        "timestamp": 100.0,
        "features": {
            "rsi": "50.0"
            # Missing obi, vol
        }
    }
    
    obs = parser.parse(payload)
    # Expect [50.0, 0.0, 0.0]
    expected = np.array([50.0, 0.0, 0.0], dtype=np.float32)
    np.testing.assert_array_almost_equal(obs.features_vector, expected)

def test_parser_garbage_values(parser):
    """Test robustness against non-numeric strings."""
    payload = {
        "timestamp": 100.0,
        "features": {
            "rsi": "garbage", # Should become 0.0
            "obi": "0.5",
            "vol": None       # Should become 0.0
        }
    }
    
    obs = parser.parse(payload)
    expected = np.array([0.0, 0.5, 0.0], dtype=np.float32)
    np.testing.assert_array_almost_equal(obs.features_vector, expected)


def test_parser_applies_delta_pct_and_log_price_modes():
    cfg = IngestConfig(
        feature_list=["price", "delta_price", "ema_bias"],
        normalization_method="zscore",
        normalization_window=100,
        buffer_size=1000,
        min_samples_before_ready=10,
        nan_strategy="zero",
        price_feature_mode="log",
        delta_price_mode="pct",
    )
    parser = FeatureParser(cfg)

    payload = {
        "timestamp": 1.0,
        "features": {
            "price": "200.0",
            "delta_price": "10.0",
            "ema_bias": "0.6",
        },
    }
    obs = parser.parse(payload)
    expected = np.array([np.log(200.0), 0.05, 0.6], dtype=np.float32)
    np.testing.assert_allclose(obs.features_vector, expected, rtol=1e-5, atol=1e-6)


def test_parser_price_drop_mode_and_clipping():
    cfg = IngestConfig(
        feature_list=["price", "delta_price", "macro_resid"],
        normalization_method="zscore",
        normalization_window=100,
        buffer_size=1000,
        min_samples_before_ready=10,
        nan_strategy="zero",
        price_feature_mode="drop",
        delta_price_mode="pct",
        feature_clip_abs={"delta_price": 0.1, "macro_resid": 2.0},
    )
    parser = FeatureParser(cfg)
    payload = {
        "timestamp": 1.0,
        "features": {
            "price": "100.0",
            "delta_price": "1000.0",  # pct=10 -> clipped to 0.1
            "macro_resid": "inf",      # non-finite -> 0
        },
    }
    obs = parser.parse(payload)
    expected = np.array([0.0, 0.1, 0.0], dtype=np.float32)
    np.testing.assert_allclose(obs.features_vector, expected, rtol=1e-6, atol=1e-7)

def test_observation_tensor_conversion():
    """Test conversion to tensor (mocking torch availability if needed)."""
    obs = MarketObservation(
        ts=1.0, mid_price=10.0, volatility=0.1, obi=0.0,
        features_vector=np.zeros(5, dtype=np.float32)
    )
    
    try:
        import torch
        t = obs.to_tensor()
        assert torch.is_tensor(t)
        assert t.shape == (1, 5)
        assert t.dtype == torch.float32
    except ImportError:
        pytest.skip("PyTorch not installed")

def test_market_observation_immutability():
    """Verify dataclass is frozen."""
    obs = MarketObservation(
        ts=1.0, mid_price=10.0, volatility=0.1, obi=0.0,
        features_vector=np.zeros(1, dtype=np.float32)
    )
    with pytest.raises(FrozenInstanceError if hasattr(pytest, 'FrozenInstanceError') else AttributeError):
        # Dataclass frozen raises FrozenInstanceError or AttributeError depending on Python version/impl
        obs.ts = 2.0

