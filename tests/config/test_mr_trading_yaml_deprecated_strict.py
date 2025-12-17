"""
Tests for mean_reversion_1m deprecated detection in trading.yaml.

CFG-STRATEGIES-SSOT-05-MR-TRADING-YAML-BURN-DOWN-STRICT
"""

import pytest
import yaml
import os
from pathlib import Path
from apps.reference.config_loader import ConfigLoader
from pydantic import ValidationError


def create_minimal_config_with_mr_in_trading(config_dir: Path, mr_config: dict):
    """Create minimal config with MR section in trading.yaml."""
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
    
    # trading.yaml WITH mean_reversion_1m (DEPRECATED)
    trading_yaml = {
        "trading": {
            "mode": "testnet",
            "decision": {"signal_threshold": 0.1, "symbols_to_track": ["BTCUSDT"]},
            "risk_management": {"data_sources": {"portfolio_state": "testnet", "market_data": "live"}},
        },
        "mean_reversion_1m": mr_config  # DEPRECATED section
    }
    (config_dir / "trading.yaml").write_text(yaml.dump(trading_yaml))
    
    # regime.yaml
    regime_yaml = {
        "hmm": {
            "enabled": False
        },
        "models": {
            "sma_trend": {"sma_short_period": 10},
            "volatility": {"enabled": False},
            "mean_reversion": {"threshold": 0.005}
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
        "BTCUSDT": {
            "step_size": "0.001",
            "tick_size": "0.01",
            "min_notional": "10"
        }
    }
    (config_dir / "instruments.yaml").write_text(yaml.dump(instruments_yaml))
    
    # strategies.yaml (empty assignments)
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


def create_minimal_config_without_mr(config_dir: Path):
    """Create minimal config WITHOUT MR in trading.yaml."""
    create_minimal_config_with_mr_in_trading(config_dir, {})
    
    # Overwrite trading.yaml without MR section
    trading_yaml = {
        "trading": {
            "mode": "testnet",
            "decision": {"signal_threshold": 0.1, "symbols_to_track": ["BTCUSDT"]},
            "risk_management": {"data_sources": {"portfolio_state": "testnet", "market_data": "live"}},
        }
    }
    (config_dir / "trading.yaml").write_text(yaml.dump(trading_yaml))


class TestMeanReversionTradingYamlDeprecated:
    """Test that mean_reversion_1m in trading.yaml is detected as deprecated."""
    
    def test_mr_in_trading_yaml_strict_mode_crashes(self, tmp_path):
        """
        Test A: MR in trading.yaml + strict mode → ValueError.
        
        CFG-STRATEGIES-SSOT-05: MR in trading.yaml is DEPRECATED (SSOT: strategy profile).
        """
        config_dir = tmp_path / "config" / "aurora"
        config_dir.mkdir(parents=True)
        
        # Create config with MR in trading.yaml (DEPRECATED)
        mr_config = {
            "enabled": True,
            "assets": {
                "BTCUSDT": {
                    "enabled": True,
                    "strategy": {
                        "bb_window": 20
                    }
                }
            }
        }
        create_minimal_config_with_mr_in_trading(config_dir, mr_config)
        
        # Enable strict mode
        os.environ["STRICT_CONFIG_CONFLICTS"] = "1"
        try:
            loader = ConfigLoader(config_dir=config_dir)
            
            from apps.reference.config_contract import ConfigContractError
            with pytest.raises(ConfigContractError) as exc_info:
                loader.load_config()
            
            # VERIFY: error message mentions deprecated MR in trading.yaml
            error_msg = str(exc_info.value)
            assert "mean_reversion_1m" in error_msg.lower()
            assert "deprecated" in error_msg.lower()
            assert "trading.yaml" in error_msg.lower()
            assert "strategy profile" in error_msg.lower() or "strategies/" in error_msg.lower()
        finally:
            os.environ.pop("STRICT_CONFIG_CONFLICTS", None)
    
    def test_mr_in_trading_yaml_non_strict_still_fails(self, tmp_path):
        """
        Test B: MR in trading.yaml always fails (no soft mode).
        """
        config_dir = tmp_path / "config" / "aurora"
        config_dir.mkdir(parents=True)
        
        # Create config with MR in trading.yaml
        mr_config = {
            "enabled": True,
            "assets": {
                "BTCUSDT": {"enabled": True}
            }
        }
        create_minimal_config_with_mr_in_trading(config_dir, mr_config)
        
        # Ensure NON-strict mode
        os.environ["STRICT_CONFIG_CONFLICTS"] = "0"
        
        loader = ConfigLoader(config_dir=config_dir)
        from apps.reference.config_contract import ConfigContractError
        with pytest.raises(ConfigContractError):
            loader.load_config()
    
    def test_no_mr_in_trading_yaml_ok(self, tmp_path):
        """
        Test C: No MR in trading.yaml → no error.
        
        CFG-STRATEGIES-SSOT-05: Normal operation without deprecated section.
        """
        config_dir = tmp_path / "config" / "aurora"
        config_dir.mkdir(parents=True)
        
        # Create config WITHOUT MR in trading.yaml
        create_minimal_config_without_mr(config_dir)
        
        # Load config - should succeed
        loader = ConfigLoader(config_dir=config_dir)
        config = loader.load_config()
        
        # VERIFY: config loaded successfully
        assert config is not None
        assert hasattr(config, "trading_mode")
        assert config.trading_mode == "testnet"
    
    def test_mr_profile_loaded_when_assigned(self, tmp_path):
        """
        Test D: MR profile loads when assigned in strategies.yaml.
        
        CFG-STRATEGIES-SSOT-05: Strategy profile is SSOT for MR config.
        """
        config_dir = tmp_path / "config" / "aurora"
        config_dir.mkdir(parents=True)
        
        # Create base config
        create_minimal_config_without_mr(config_dir)
        
        # Create strategy profile
        strategies_dir = config_dir / "strategies"
        strategies_dir.mkdir(parents=True)
        
        mr_profile = {
            "mean_reversion_1m": {
                "enabled": True,
                "strategy": {
                    "bb_window": 40,
                    "bb_num_std": 2.5
                },
                "assets": {
                    "BTCUSDT": {
                        "enabled": True,
                        "strategy": {
                            "bb_window": 20
                        }
                    }
                }
            }
        }
        (strategies_dir / "mean_reversion_1m.yaml").write_text(yaml.dump(mr_profile))
        
        # Assign MR in strategies.yaml
        strategies_yaml = {
            "assignments": {
                "BTCUSDT": ["mean_reversion_1m"]
            },
            "arbitration": {
                "mode": "priority",
                "priority": {
                    "mean_reversion_1m": 1
                }
            }
        }
        (config_dir / "strategies.yaml").write_text(yaml.dump(strategies_yaml))
        
        # Load config
        loader = ConfigLoader(config_dir=config_dir)
        config = loader.load_config()
        
        # VERIFY: MR config loaded from profile
        assert config is not None
        assert hasattr(config, "mean_reversion_1m")
        assert config.mean_reversion_1m is not None
        assert config.mean_reversion_1m.enabled == True
        assert config.mean_reversion_1m.strategy.bb_window == 40
        
        # VERIFY: strategy registry loaded
        assert hasattr(config, "strategies_registry")
        assert config.strategies_registry is not None
        assert config.strategies_registry.assignments["BTCUSDT"] == ["mean_reversion_1m"]
    
    def test_mr_profile_missing_when_assigned_fails(self, tmp_path):
        """
        Test E: MR assigned but profile missing → ValueError (fail-closed).
        
        CFG-STRATEGIES-SSOT-05: Assigned strategy must have profile file.
        """
        config_dir = tmp_path / "config" / "aurora"
        config_dir.mkdir(parents=True)
        
        # Create base config
        create_minimal_config_without_mr(config_dir)
        
        # Create strategies dir but NO mean_reversion_1m.yaml
        strategies_dir = config_dir / "strategies"
        strategies_dir.mkdir(parents=True)
        
        # Assign MR in strategies.yaml (but profile missing!)
        strategies_yaml = {
            "assignments": {
                "BTCUSDT": ["mean_reversion_1m"]
            },
            "arbitration": {
                "mode": "priority",
                "priority": {
                    "mean_reversion_1m": 1
                }
            }
        }
        (config_dir / "strategies.yaml").write_text(yaml.dump(strategies_yaml))
        
        # Load config - should FAIL
        loader = ConfigLoader(config_dir=config_dir)
        
        with pytest.raises(ValueError) as exc_info:
            loader.load_config()
        
        # VERIFY: error mentions missing profile
        error_msg = str(exc_info.value)
        assert "mean_reversion_1m" in error_msg.lower()
        assert "missing" in error_msg.lower() or "not found" in error_msg.lower()
        assert "profile" in error_msg.lower() or "strategies/" in error_msg.lower()
