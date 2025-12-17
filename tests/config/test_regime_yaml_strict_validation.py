"""
Tests for regime.yaml strict validation (extra keys).

CFG-FEATURES-REGIME-SSOT-04-LIVE-OR-DEPRECATE
"""

import pytest
import yaml
from pathlib import Path
from apps.reference.config_loader import ConfigLoader
from pydantic import ValidationError


def create_minimal_config(config_dir: Path, regime_yaml_content: dict):
    """Create minimal valid config structure with custom regime.yaml."""
    # system.yaml
    system_yaml = {
        "trading_mode": "testnet",
        "bridge": {"retry_scheduler": {"max_attempts": 5, "min_retry_delay_ms": 500}},
        "binance_api": {
            "testnet": {
                "api_key": "test",
                "api_secret": "test",
                "rest_url": "https://test",
            },
            "live": {
                "api_key": "test",
                "api_secret": "test",
                "rest_url": "https://live",
            },
        }
    }
    (config_dir / "system.yaml").write_text(yaml.dump(system_yaml))
    
    # trading.yaml
    trading_yaml = {
        "trading": {
            "mode": "testnet",
            "decision": {"signal_threshold": 0.1, "symbols_to_track": ["BTCUSDT"]},
            "risk_management": {"data_sources": {"portfolio_state": "testnet", "market_data": "live"}},
        }
    }
    (config_dir / "trading.yaml").write_text(yaml.dump(trading_yaml))
    
    # regime.yaml (provided by caller)
    (config_dir / "regime.yaml").write_text(yaml.dump(regime_yaml_content))
    
    # domains.yaml
    domains_yaml = {
        "decision_making": {
            "position_sizing": {
                "min_position_size_usd": 10
            }
        }
    }
    (config_dir / "domains.yaml").write_text(yaml.dump(domains_yaml))
    
    # instruments.yaml
    instruments_yaml = {
        "instruments": {
            "BTCUSDT": {
                "step_size": "0.001",
                "tick_size": "0.01",
                "min_notional": "10"
            }
        }
    }
    (config_dir / "instruments.yaml").write_text(yaml.dump(instruments_yaml))
    
    # strategies.yaml
    strategies_yaml = {
        "assignments": {},
        "arbitration": {
            "mode": "priority",
            "priority": {}
        }
    }
    (config_dir / "strategies.yaml").write_text(yaml.dump(strategies_yaml))
    
    # aurora_instruments.yaml (suppress warning)
    (config_dir / "aurora_instruments.yaml").write_text(yaml.dump({}))


class TestRegimeYamlStrictValidation:
    """Test that regime.yaml extra keys are rejected (extra='forbid')"""
    
    def test_valid_regime_yaml_loads_successfully(self, tmp_path):
        """
        Test VALID regime.yaml loads successfully.
        
        CFG-FEATURES-REGIME-SSOT-04: regime.yaml is SSOT, valid config should load.
        """
        config_dir = tmp_path / "config" / "aurora"
        config_dir.mkdir(parents=True)
        
        # Valid regime.yaml
        regime_yaml = {
            "hmm": {
                "enabled": True,
                "K": 3
            },
            "models": {
                "sma_trend": {
                    "sma_short_period": 10,
                    "sma_long_period": 50
                },
                "volatility": {
                    "enabled": True,
                    "atr_period": 14
                },
                "mean_reversion": {
                    "threshold": 0.005
                }
            }
        }
        
        create_minimal_config(config_dir, regime_yaml)
        
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
        config_dir = tmp_path / "config" / "aurora"
        config_dir.mkdir(parents=True)
        
        # regime.yaml with EXTRA KEY in models
        regime_yaml = {
            "hmm": {
                "enabled": True
            },
            "models": {
                "sma_trend": {
                    "sma_short_period": 10
                },
                "volatility": {
                    "enabled": True
                },
                "mean_reversion": {
                    "threshold": 0.005
                },
                "unknown_model": {  # EXTRA KEY (not in RegimeModelsConfig)
                    "some_param": 123
                }
            }
        }
        
        create_minimal_config(config_dir, regime_yaml)
        
        # Load config - should FAIL
        loader = ConfigLoader(config_dir=config_dir)
        
        with pytest.raises(ValidationError) as exc_info:
            loader.load_config()
        
        # VERIFY: error mentions extra key
        error_msg = str(exc_info.value)
        assert "unknown_model" in error_msg or "extra" in error_msg.lower()
    
    def test_minimal_regime_yaml_loads(self, tmp_path):
        """
        Test MINIMAL regime.yaml (empty models) loads successfully.
        
        CFG-FEATURES-REGIME-SSOT-04: Default factory values should work.
        """
        config_dir = tmp_path / "config" / "aurora"
        config_dir.mkdir(parents=True)
        
        # Minimal regime.yaml
        regime_yaml = {
            "hmm": {
                "enabled": False
            }
        }
        
        create_minimal_config(config_dir, regime_yaml)
        
        # Load config - should succeed
        loader = ConfigLoader(config_dir=config_dir)
        config = loader.load_config()
        
        # VERIFY: config loaded with defaults
        assert config is not None
        # models should exist with default factory
        if hasattr(config, "models") and config.models:
            assert hasattr(config.models, "sma_trend")
