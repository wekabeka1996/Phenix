"""
Tests for mean_reversion deprecated detection in trading.yaml.

CFG-STRATEGIES-SSOT-05-MR-TRADING-YAML-BURN-DOWN-STRICT
"""

import pytest
import yaml
import os
from pathlib import Path
import shutil
from apps.reference.config_loader import ConfigLoader


def _copy_canonical_config_dir(tmp_path: Path) -> Path:
    src = Path(__file__).resolve().parents[2] / "config" / "aurora"
    dst = tmp_path / "aurora"
    shutil.copytree(src, dst)
    return dst


def _read_canonical_strategy_profile(rel_path: str) -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / "config" / "aurora" / "strategies" / rel_path).read_text(encoding="utf-8")


def _set_mean_reversion_in_trading_yaml(config_dir: Path, mr_config: dict | None) -> None:
    """Inject/remove deprecated top-level mean_reversion key in trading.yaml."""
    trading_path = config_dir / "trading.yaml"
    data = yaml.safe_load(trading_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError("trading.yaml did not parse to a dict")

    if mr_config is None:
        data.pop("mean_reversion", None)
    else:
        data["mean_reversion"] = mr_config

    trading_path.write_text(yaml.dump(data), encoding="utf-8")


class TestMeanReversionTradingYamlDeprecated:
    """Test that mean_reversion in trading.yaml is detected as deprecated."""
    
    def test_mr_in_trading_yaml_strict_mode_crashes(self, tmp_path):
        """
        Test A: MR in trading.yaml + strict mode → ValueError.
        
        CFG-STRATEGIES-SSOT-05: MR in trading.yaml is DEPRECATED (SSOT: strategy profile).
        """
        config_dir = _copy_canonical_config_dir(tmp_path)
        
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
        _set_mean_reversion_in_trading_yaml(config_dir, mr_config)
        
        # Enable strict mode
        os.environ["STRICT_CONFIG_CONFLICTS"] = "1"
        try:
            loader = ConfigLoader(config_dir=config_dir)
            
            from apps.reference.config_contract import ConfigContractError
            with pytest.raises(ConfigContractError) as exc_info:
                loader.load_config()
            
            # VERIFY: error message mentions deprecated MR in trading.yaml
            error_msg = str(exc_info.value)
            assert "mean_reversion" in error_msg.lower()
            assert "deprecated" in error_msg.lower()
            assert "trading.yaml" in error_msg.lower()
            assert "strategy profile" in error_msg.lower() or "strategies/" in error_msg.lower()
        finally:
            os.environ.pop("STRICT_CONFIG_CONFLICTS", None)
    
    def test_mr_in_trading_yaml_non_strict_still_fails(self, tmp_path):
        """
        Test B: MR in trading.yaml always fails (no soft mode).
        """
        config_dir = _copy_canonical_config_dir(tmp_path)
        
        # Create config with MR in trading.yaml
        mr_config = {
            "enabled": True,
            "assets": {
                "BTCUSDT": {"enabled": True}
            }
        }
        _set_mean_reversion_in_trading_yaml(config_dir, mr_config)
        
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
        config_dir = _copy_canonical_config_dir(tmp_path)
        
        # Ensure config has NO deprecated MR key in trading.yaml
        _set_mean_reversion_in_trading_yaml(config_dir, None)
        
        # Load config - should succeed
        loader = ConfigLoader(config_dir=config_dir)
        config = loader.load_config()
        
        # VERIFY: config loaded successfully
        assert config is not None
        assert hasattr(config, "trading_mode")
        assert config.trading_mode in {"testnet", "production", "live", "hybrid_live_data_testnet_exec", "backtest"}
    
    def test_mr_profile_loaded_when_assigned(self, tmp_path):
        """
        Test D: MR profile loads when assigned in strategies.yaml.
        
        CFG-STRATEGIES-SSOT-05: Strategy profile is SSOT for MR config.
        """
        config_dir = _copy_canonical_config_dir(tmp_path)
        
        # Base config: ensure deprecated MR is not present in trading.yaml
        _set_mean_reversion_in_trading_yaml(config_dir, None)
        
        # Create strategy profile
        strategies_dir = config_dir / "strategies"
        strategies_dir.mkdir(parents=True, exist_ok=True)
        
        # Use canonical profile to satisfy strict schema (zero-defaults => keys required).
        (strategies_dir / "mean_reversion.yaml").write_text(
            _read_canonical_strategy_profile("mean_reversion.yaml"), encoding="utf-8"
        )
        
        # Assign MR in strategies.yaml
        strategies_yaml = {
            "version": "1.0.0",
            "assignments": {
                "BTCUSDT": ["aurora", "mean_reversion"]
            },
            "arbitration": {
                "mode": "priority",
                "window_ms": 1000,
                "priority": {
                    "aurora": 1,
                    "mean_reversion": 2,
                },
                "logging": {"rejected_why_prefix": "ARBITRATION_REJECT", "log_level": "INFO"},
            }
        }
        (config_dir / "strategies.yaml").write_text(yaml.dump(strategies_yaml), encoding="utf-8")
        
        # Load config
        loader = ConfigLoader(config_dir=config_dir)
        config = loader.load_config()
        
        # VERIFY: MR config loaded from profile
        assert config is not None
        assert config.strategies.mean_reversion is not None
        assert config.strategies.mean_reversion.enabled is True
        # Canonical profile: BTCUSDT override uses bb_window=40
        assert config.strategies.mean_reversion.assets["BTCUSDT"].strategy.bb_window == 40
        
        # VERIFY: strategy registry loaded
        assert hasattr(config, "strategies_registry")
        assert config.strategies_registry is not None
        assert set(config.strategies_registry.assignments["BTCUSDT"]) == {"aurora", "mean_reversion"}
    
    def test_mr_profile_missing_when_assigned_fails(self, tmp_path):
        """
        Test E: MR assigned but profile missing → ValueError (fail-closed).
        
        CFG-STRATEGIES-SSOT-05: Assigned strategy must have profile file.
        """
        config_dir = _copy_canonical_config_dir(tmp_path)
        
        # Base config: ensure deprecated MR is not present in trading.yaml
        _set_mean_reversion_in_trading_yaml(config_dir, None)
        
        # Create strategies dir but NO mean_reversion.yaml
        strategies_dir = config_dir / "strategies"
        strategies_dir.mkdir(parents=True, exist_ok=True)

        # Canonical config includes this profile; remove it to simulate missing profile.
        mr_profile_path = strategies_dir / "mean_reversion.yaml"
        if mr_profile_path.exists():
            mr_profile_path.unlink()
        
        # Assign MR in strategies.yaml (but profile missing!)
        strategies_yaml = {
            "version": "1.0.0",
            "assignments": {
                "BTCUSDT": ["aurora", "mean_reversion"]
            },
            "arbitration": {
                "mode": "priority",
                "window_ms": 1000,
                "priority": {
                    "aurora": 1,
                    "mean_reversion": 2,
                },
                "logging": {"rejected_why_prefix": "ARBITRATION_REJECT", "log_level": "INFO"},
            }
        }
        (config_dir / "strategies.yaml").write_text(yaml.dump(strategies_yaml), encoding="utf-8")
        
        # Load config - should FAIL
        loader = ConfigLoader(config_dir=config_dir)
        
        with pytest.raises(ValueError) as exc_info:
            loader.load_config()
        
        # VERIFY: error mentions missing profile
        error_msg = str(exc_info.value)
        assert "mean_reversion" in error_msg.lower()
        assert "missing" in error_msg.lower() or "not found" in error_msg.lower()
        assert "profile" in error_msg.lower() or "strategies/" in error_msg.lower()
