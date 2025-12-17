"""
Tests for registry-driven strategy profile loading.

CFG-STRATEGIES-SSOT-03-REGISTRY-DRIVEN-LOADING-AND-ONE-CONFIG-TRUTH
"""

import pytest
import yaml
from pathlib import Path
from apps.reference.config_loader import ConfigLoader


def create_test_config(config_dir: Path, with_mr_assignment=True, with_mr_profile=True, with_aurora=False):
    """
    Helper to create test config structure.
    
    Args:
        config_dir: Path to config directory
        with_mr_assignment: Include mean_reversion_1m in strategies.yaml assignments
        with_mr_profile: Create mean_reversion_1m.yaml profile file
        with_aurora: Include aurora in assignments and profile
    """
    strategies_dir = config_dir / "strategies"
    strategies_dir.mkdir(parents=True, exist_ok=True)
    
    # Create minimal system.yaml
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
    with open(config_dir / "system.yaml", "w") as f:
        yaml.dump(system_yaml, f)
    
    # Create trading.yaml (minimal)
    trading_yaml = {
        "trading": {
            "mode": "testnet",
            "decision": {"signal_threshold": 0.1, "symbols_to_track": ["BTCUSDT"]},
            "risk_management": {"data_sources": {"portfolio_state": "testnet", "market_data": "live"}},
        }
    }
    with open(config_dir / "trading.yaml", "w") as f:
        yaml.dump(trading_yaml, f)
    
    # Create regime.yaml (minimal)
    regime_yaml = {}
    with open(config_dir / "regime.yaml", "w") as f:
        yaml.dump(regime_yaml, f)
    
    # Create domains.yaml (minimal with realistic domain structure)
    domains_yaml = {
        "decision_making": {
            "position_sizing": {
                "min_position_size_usd": 10
            }
        }
    }
    with open(config_dir / "domains.yaml", "w") as f:
        yaml.dump(domains_yaml, f)
    
    # Create instruments.yaml (minimal)
    instruments_yaml = {
        "instruments": {
            "BTCUSDT": {
                "step_size": "0.001",
                "tick_size": "0.01",
                "min_notional": "10"
            }
        }
    }
    with open(config_dir / "instruments.yaml", "w") as f:
        yaml.dump(instruments_yaml, f)

    # Create aurora_instruments.yaml (required for strict SSOT)
    aurora_instruments_yaml = {}
    with open(config_dir / "aurora_instruments.yaml", "w") as f:
        yaml.dump(aurora_instruments_yaml, f)
    
    # Create strategies.yaml
    assignments_dict = {}
    priorities_dict = {}
    
    strategy_list = []
    priority_counter = 1
    
    if with_aurora:
        strategy_list.append("aurora")
        priorities_dict["aurora"] = priority_counter
        priority_counter += 1
    
    if with_mr_assignment:
        strategy_list.append("mean_reversion_1m")
        priorities_dict["mean_reversion_1m"] = priority_counter
    
    if strategy_list:
        assignments_dict["BTCUSDT"] = strategy_list
    
    strategies_yaml = {
        "assignments": assignments_dict,
        "arbitration": {
            "mode": "priority",
            "priority": priorities_dict
        }
    }
    with open(config_dir / "strategies.yaml", "w") as f:
        yaml.dump(strategies_yaml, f)
    
    # Create strategy profiles
    if with_mr_profile:
        mr_profile = {
            "mean_reversion_1m": {
                "enabled": True,
                "timeframe_sec": 60,
                "strategy": {
                    "bb_window": 20,
                    "bb_num_std": 2.0
                }
            }
        }
        with open(strategies_dir / "mean_reversion_1m.yaml", "w") as f:
            yaml.dump(mr_profile, f)
    
    if with_aurora:
        aurora_profile = {
            "aurora": {
                "enabled": True
            }
        }
        with open(strategies_dir / "aurora.yaml", "w") as f:
            yaml.dump(aurora_profile, f)


class TestRegistryDrivenLoading:
    """Test that ConfigLoader loads strategy profiles ONLY from strategies_registry.assignments"""
    
    def test_registry_driven_load_mean_reversion(self, tmp_path):
        """
        Test that MR profile is loaded via registry assignments (not hardcoded).
        
        CFG-STRATEGIES-SSOT-03: ConfigLoader reads strategies.yaml assignments,
        then loads corresponding profiles from strategies/{id}.yaml
        """
        config_dir = tmp_path / "config" / "aurora"
        create_test_config(config_dir, with_mr_assignment=True, with_mr_profile=True)
        
        # Load config
        loader = ConfigLoader(config_dir=config_dir)
        config = loader.load_config()
        
        # VERIFY: mean_reversion_1m config loaded from profile (not hardcoded)
        assert hasattr(config, "mean_reversion_1m")
        assert config.mean_reversion_1m is not None
        assert config.mean_reversion_1m.enabled is True
        assert config.mean_reversion_1m.timeframe_sec == 60
    
    def test_assigned_strategy_missing_profile_fails(self, tmp_path):
        """
        Test FAIL-CLOSED: strategy assigned in registry but profile missing → ValueError.
        
        CFG-STRATEGIES-SSOT-03: Strict mode - missing profile for assigned strategy must crash.
        """
        config_dir = tmp_path / "config" / "aurora"
        # Create config WITHOUT MR profile (but WITH assignment)
        create_test_config(config_dir, with_mr_assignment=True, with_mr_profile=False)
        
        # Load config - MUST FAIL
        loader = ConfigLoader(config_dir=config_dir)
        with pytest.raises(ValueError) as exc_info:
            config = loader.load_config()
        
        # VERIFY: error message mentions missing profile
        error_msg = str(exc_info.value)
        assert "mean_reversion_1m" in error_msg
        assert "profile missing" in error_msg.lower() or "missing" in error_msg.lower()
    
    def test_unassigned_strategy_profile_not_loaded(self, tmp_path):
        """
        Test that strategy profile present but NOT in assignments → not loaded.
        
        CFG-STRATEGIES-SSOT-03: Only load profiles for strategies actually assigned.
        """
        config_dir = tmp_path / "config" / "aurora"
        # Create config WITH aurora assignment and profile, but MR profile without assignment
        create_test_config(config_dir, with_mr_assignment=False, with_mr_profile=True, with_aurora=True)
        
        # Load config
        loader = ConfigLoader(config_dir=config_dir)
        config = loader.load_config()
        
        # VERIFY: mean_reversion_1m NOT loaded (not in assignments)
        assert not hasattr(config, "mean_reversion_1m") or config.mean_reversion_1m is None
    
    def test_multiple_strategies_assigned_all_loaded(self, tmp_path):
        """
        Test that multiple strategies assigned → all profiles loaded.
        
        CFG-STRATEGIES-SSOT-03: BTC hybrid (aurora + MR) → both profiles loaded.
        """
        config_dir = tmp_path / "config" / "aurora"
        create_test_config(config_dir, with_mr_assignment=True, with_mr_profile=True, with_aurora=True)
        
        # Load config
        loader = ConfigLoader(config_dir=config_dir)
        config = loader.load_config()
        
        # VERIFY: BOTH profiles loaded
        assert hasattr(config, "mean_reversion_1m")
        assert config.mean_reversion_1m is not None
        assert config.mean_reversion_1m.enabled is True
