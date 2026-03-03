"""
TASK54: Test weight key validation for AuroraInstrumentConfig.

Ensures that only canonical feature keys are accepted in per-asset weights config.
Invalid/legacy keys (ema, volume, macro, liquidity, volatility) should fail validation.
"""

import pytest
from pydantic import ValidationError

from apps.reference.config_models import (
    AuroraInstrumentConfig,
    CANONICAL_WEIGHT_KEYS,
)


def _make_minimal_aurora_instrument_config(**overrides):
    """Create minimal valid AuroraInstrumentConfig with all required fields.
    
    Note: max_risk_score must be OMITTED (not set to None) per MR-RISK-GATE-NONE-FIX-01.
    """
    base = {
        "enabled": True,
        "position_mode": "STRICT",
        "weights": None,
        "side_bias": None,
        "regime_thresholds": None,
        "regime_sizing": None,
        "exit": None,
        "take_profit": None,
        "trailing_stop": None,
        # PURGE-04: execution and ema_clamp removed from model
        "signal_threshold": None,
        # max_risk_score OMITTED - explicit null is forbidden
        "cooldown_sec": None,
        "allowed_regimes": None,
        "timeframe_sec": None,
    }
    base.update(overrides)
    return AuroraInstrumentConfig(**base)


class TestWeightKeyValidation:
    """Test suite for TASK54: Weight Key Mismatch Fix."""

    def test_canonical_keys_accepted(self):
        """All canonical feature keys should be accepted."""
        cfg = _make_minimal_aurora_instrument_config(
            weights={
                "obi": 0.15,
                "tfi": 0.15,
                "delta_price": 0.10,
                "ema_bias": 0.15,
                "volume_spike": 0.10,
                "volatility_state": 0.10,
                "depth_imbalance": 0.15,
                "macro_sync": 0.10,
            }
        )
        assert cfg.weights is not None
        assert len(cfg.weights) == 8

    def test_partial_weights_accepted(self):
        """Subset of canonical keys should be valid."""
        cfg = _make_minimal_aurora_instrument_config(
            weights={
                "obi": 0.5,
                "tfi": 0.5,
            }
        )
        assert cfg.weights == {"obi": 0.5, "tfi": 0.5}

    def test_legacy_abbr_keys_rejected(self):
        """Legacy abbreviated keys (ema, volume, etc.) should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            _make_minimal_aurora_instrument_config(
                weights={
                    "ema": 0.15,  # Should be ema_bias
                    "volume": 0.10,  # Should be volume_spike
                    "obi": 0.15,
                }
            )
        
        error_msg = str(exc_info.value)
        assert "Invalid weight keys" in error_msg
        assert "ema" in error_msg
        assert "volume" in error_msg

    def test_single_invalid_key_rejected(self):
        """Even a single invalid key should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            _make_minimal_aurora_instrument_config(
                weights={
                    "obi": 0.5,
                    "volatility": 0.5,  # Should be volatility_state
                }
            )
        
        error_msg = str(exc_info.value)
        assert "volatility" in error_msg.lower()

    def test_all_legacy_keys_rejected(self):
        """All legacy abbreviated keys should be rejected."""
        legacy_keys = ["ema", "volume", "macro", "liquidity", "volatility"]
        
        for legacy_key in legacy_keys:
            with pytest.raises(ValidationError) as exc_info:
                _make_minimal_aurora_instrument_config(
                    weights={legacy_key: 1.0}
                )
            assert "Invalid weight keys" in str(exc_info.value), f"Key '{legacy_key}' should be rejected"

    def test_none_weights_accepted(self):
        """None weights should be valid (uses global fallback)."""
        cfg = _make_minimal_aurora_instrument_config(weights=None)
        assert cfg.weights is None

    def test_empty_weights_accepted(self):
        """Empty weights dict should be valid."""
        cfg = _make_minimal_aurora_instrument_config(weights={})
        assert cfg.weights == {}

    def test_canonical_keys_constant_complete(self):
        """CANONICAL_WEIGHT_KEYS should contain all expected weighted features (liquidity is a gate, not a weight)."""
        expected = {
            "obi", "tfi", "delta_price", "ema_bias", "volume_spike",
            "volatility_state", "depth_imbalance", "absorption", "macro_sync", "macro_resid"
        }
        assert CANONICAL_WEIGHT_KEYS == expected
        assert len(CANONICAL_WEIGHT_KEYS) == 10

    def test_typo_key_rejected(self):
        """Typos in weight keys should fail validation."""
        with pytest.raises(ValidationError) as exc_info:
            _make_minimal_aurora_instrument_config(
                weights={"ema_bais": 1.0}  # Typo: bais instead of bias
            )
        assert "Invalid weight keys" in str(exc_info.value)


class TestConfigLoadWithNewWeights:
    """Integration test: verify production config loads with fixed weight keys."""

    def test_production_aurora_yaml_loads(self):
        """aurora.yaml should load without weight key validation errors."""
        from apps.reference.config_loader import ConfigLoader
        import os
        
        # Skip if not in project root
        config_path = "config/aurora/strategies/aurora.yaml"
        if not os.path.exists(config_path):
            pytest.skip("aurora.yaml not found")
        
        # This will raise ValidationError if weight keys are invalid
        loader = ConfigLoader()
        config = loader.load_config()
        
        # Verify aurora assets loaded
        aurora_cfg = config.strategies.aurora
        assert aurora_cfg is not None
        
        # Check weights for each symbol
        for symbol in ["ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT", "BTCUSDT"]:
            instr_cfg = aurora_cfg.assets.get(symbol)
            if instr_cfg and instr_cfg.weights:
                # All keys should be canonical
                for key in instr_cfg.weights.keys():
                    assert key in CANONICAL_WEIGHT_KEYS, f"{symbol}: invalid key '{key}'"

    def test_global_signal_weights_are_canonical(self):
        """Global signal_weights should also use canonical keys."""
        from apps.reference.config_loader import ConfigLoader
        import os
        
        if not os.path.exists("config/aurora/strategies/aurora.yaml"):
            pytest.skip("aurora.yaml not found")
        
        loader = ConfigLoader()
        config = loader.load_config()
        
        # Global weights from strategies.aurora.decision.signal_weights
        global_weights = config.strategies.aurora.decision.signal_weights.model_dump()
        
        for key in global_weights.keys():
            assert key in CANONICAL_WEIGHT_KEYS, f"Global signal_weights has non-canonical key: '{key}'"
