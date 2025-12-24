"""Tests for regime.yaml strict validation (extra keys).

CFG-FEATURES-REGIME-SSOT-04-LIVE-OR-DEPRECATE
"""

import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader


def _copy_canonical_config_dir(tmp_path: Path) -> Path:
    src = Path(__file__).resolve().parents[2] / "config" / "aurora"
    dst = tmp_path / "aurora"
    shutil.copytree(src, dst)
    return dst


class TestRegimeYamlStrictValidation:
    """Test that regime.yaml extra keys are rejected (extra='forbid')"""
    
    def test_valid_regime_yaml_loads_successfully(self, tmp_path):
        """
        Test VALID regime.yaml loads successfully.
        
        CFG-FEATURES-REGIME-SSOT-04: regime.yaml is SSOT, valid config should load.
        """
        config_dir = _copy_canonical_config_dir(tmp_path)
        
        # Valid regime.yaml
        regime_yaml = {
            "hmm": {
                "enabled": True,
                "K": 3
            },
            "features": {},
            "hotreload_whitelist": [],
            "models": {
                "sma_trend": {
                    "sma_short_period": 10,
                    "sma_long_period": 50,
                    "confidence_multiplier": 1.0,
                    "confidence_min": 0.0,
                    "confidence_max": 1.0,
                },
                "volatility": {
                    "enabled": True,
                    "atr_period": 14,
                    "atr_sma_length": 20,
                    "allow_close_to_close_atr": True,
                    "threshold_multiplier": 2.0,
                    "low_vol_multiplier": 0.5,
                    "high_vol_confidence_multiplier": 1.0,
                    "low_vol_confidence_multiplier": 1.0,
                },
                "mean_reversion": {
                    "threshold": 0.005,
                    "confidence_multiplier": 1.0,
                }
            }
        }
        
        (config_dir / "regime.yaml").write_text(yaml.dump(regime_yaml), encoding="utf-8")
        
        # Load config - should succeed
        loader = ConfigLoader(config_dir=config_dir)
        config = loader.load_config()
        
        # VERIFY: config loaded successfully
        assert config is not None
        assert hasattr(config, "models")
        assert config.models is not None
        assert config.models.sma_trend.sma_short_period == 10
    
    def test_extra_key_in_regime_models_fails_validation(self, tmp_path):
        """
        Test EXTRA KEY in regime.yaml models → ValidationError.
        
        CFG-FEATURES-REGIME-SSOT-04: RegimeModelsConfig has extra='forbid',
        unknown keys should fail Pydantic validation.
        """
        config_dir = _copy_canonical_config_dir(tmp_path)
        
        # regime.yaml with EXTRA KEY in models
        regime_yaml = {
            "hmm": {
                "enabled": True
            },
            "features": {},
            "hotreload_whitelist": [],
            "models": {
                "sma_trend": {
                    "sma_short_period": 10,
                    "sma_long_period": 50,
                    "confidence_multiplier": 1.0,
                    "confidence_min": 0.0,
                    "confidence_max": 1.0,
                },
                "volatility": {
                    "enabled": True,
                    "atr_period": 14,
                    "atr_sma_length": 20,
                    "allow_close_to_close_atr": True,
                    "threshold_multiplier": 2.0,
                    "low_vol_multiplier": 0.5,
                    "high_vol_confidence_multiplier": 1.0,
                    "low_vol_confidence_multiplier": 1.0,
                },
                "mean_reversion": {
                    "threshold": 0.005,
                    "confidence_multiplier": 1.0,
                },
                "unknown_model": {  # EXTRA KEY (not in RegimeModelsConfig)
                    "some_param": 123
                }
            }
        }
        
        (config_dir / "regime.yaml").write_text(yaml.dump(regime_yaml), encoding="utf-8")
        
        # Load config - should FAIL
        loader = ConfigLoader(config_dir=config_dir)
        
        with pytest.raises(ValidationError) as exc_info:
            loader.load_config()
        
        # VERIFY: error mentions extra key
        error_msg = str(exc_info.value)
        assert "unknown_model" in error_msg or "extra" in error_msg.lower()
    
    def test_minimal_regime_yaml_loads(self, tmp_path):
        """
        Test MINIMAL regime.yaml missing required keys fails fast.
        
        TASK22: With zero-defaults config models, absent keys must raise ValidationError.
        """
        config_dir = _copy_canonical_config_dir(tmp_path)

        # Minimal regime.yaml without required keys
        regime_yaml = {
            "hmm": {
                "enabled": False
            }
        }

        (config_dir / "regime.yaml").write_text(yaml.dump(regime_yaml), encoding="utf-8")

        loader = ConfigLoader(config_dir=config_dir)

        with pytest.raises(ValidationError) as exc_info:
            loader.load_config()

        error_msg = str(exc_info.value)
        assert "field required" in error_msg.lower()
