"""
Tests for features.yaml deprecated detection.

CFG-FEATURES-REGIME-SSOT-04-LIVE-OR-DEPRECATE
"""

import pytest
import yaml
import os
from pathlib import Path
from apps.reference.config_loader import ConfigLoader


def create_minimal_config(config_dir: Path):
    """Create minimal valid config structure."""
    # system.yaml
    system_yaml = {
        "trading_mode": "testnet",
        "binance_api": {
            "testnet": {
                "api_key": "test",
                "api_secret": "test"
            }
        }
    }
    (config_dir / "system.yaml").write_text(yaml.dump(system_yaml))
    
    # trading.yaml
    trading_yaml = {
        "trading": {}
    }
    (config_dir / "trading.yaml").write_text(yaml.dump(trading_yaml))
    
    # regime.yaml
    regime_yaml = {
        "hmm": {
            "enabled": False
        }
    }
    (config_dir / "regime.yaml").write_text(yaml.dump(regime_yaml))
    
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
    
    # aurora_instruments.yaml (optional but suppresses warning)
    aurora_instruments_yaml = {}
    (config_dir / "aurora_instruments.yaml").write_text(yaml.dump(aurora_instruments_yaml))


class TestFeaturesYamlDeprecated:
    """Test that features.yaml is detected as deprecated/unused"""
    
    def test_features_yaml_exists_strict_mode_crashes(self, tmp_path):
        """
        Test STRICT MODE: features.yaml exists → ValueError.
        
        CFG-FEATURES-REGIME-SSOT-04: features.yaml is orphaned (not loaded),
        strict mode must crash to prevent confusion.
        """
        config_dir = tmp_path / "config" / "aurora"
        config_dir.mkdir(parents=True)
        
        # Create minimal config
        create_minimal_config(config_dir)
        
        # Create orphaned features.yaml
        features_yaml = {
            "feature_engineering": {
                "enable_new_metrics": True
            }
        }
        (config_dir / "features.yaml").write_text(yaml.dump(features_yaml))
        
        # Enable strict mode
        os.environ["STRICT_CONFIG_CONFLICTS"] = "1"
        try:
            loader = ConfigLoader(config_dir=config_dir)
            
            with pytest.raises(ValueError) as exc_info:
                loader.load_config()
            
            # VERIFY: error message mentions deprecated
            error_msg = str(exc_info.value)
            assert "features.yaml" in error_msg.lower()
            assert "deprecated" in error_msg.lower() or "orphaned" in error_msg.lower()
        finally:
            os.environ.pop("STRICT_CONFIG_CONFLICTS", None)
    
    def test_features_yaml_exists_non_strict_warns(self, tmp_path, caplog):
        """
        Test NON-STRICT MODE: features.yaml exists → WARNING logged.
        
        CFG-FEATURES-REGIME-SSOT-04: Non-strict mode allows boot but warns.
        """
        config_dir = tmp_path / "config" / "aurora"
        config_dir.mkdir(parents=True)
        
        # Create minimal config
        create_minimal_config(config_dir)
        
        # Create orphaned features.yaml
        features_yaml = {
            "feature_engineering": {
                "enable_new_metrics": True
            }
        }
        (config_dir / "features.yaml").write_text(yaml.dump(features_yaml))
        
        # Ensure NON-strict mode
        os.environ.pop("STRICT_CONFIG_CONFLICTS", None)
        
        loader = ConfigLoader(config_dir=config_dir)
        config = loader.load_config()
        
        # VERIFY: config loaded successfully
        assert config is not None
        
        # VERIFY: warning was logged
        assert any("features.yaml" in rec.message.lower() for rec in caplog.records)
        assert any("deprecated" in rec.message.lower() or "orphaned" in rec.message.lower() for rec in caplog.records)
    
    def test_features_yaml_missing_no_error(self, tmp_path):
        """
        Test NORMAL CASE: features.yaml missing → no error.
        
        CFG-FEATURES-REGIME-SSOT-04: Normal operation without orphaned file.
        """
        config_dir = tmp_path / "config" / "aurora"
        config_dir.mkdir(parents=True)
        
        # Create minimal config (WITHOUT features.yaml)
        create_minimal_config(config_dir)
        
        # Load config - should succeed
        loader = ConfigLoader(config_dir=config_dir)
        config = loader.load_config()
        
        # VERIFY: config loaded successfully
        assert config is not None
        assert hasattr(config, "trading_mode")
        assert config.trading_mode == "testnet"
