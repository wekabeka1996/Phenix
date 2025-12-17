"""
CFG-FREEZE-SSOT-06: Test strict-by-default and CI gates.

Test Plan:
1. Strict mode active by default (no env set)
2. Opt-out works (STRICT_CONFIG_CONFLICTS=0)
3. trading.yaml with feature_engineering + strict → ValueError
4. trading.yaml with feature_engineering + non-strict → WARNING
5. Clean config loads in strict mode
6. Sanity: features.yaml + MR deprecated detections still work
"""
import os
import pytest
import yaml
from pathlib import Path
from apps.reference.config_loader import ConfigLoader


@pytest.fixture
def clean_env():
    """Cleanup STRICT_CONFIG_CONFLICTS env var."""
    original = os.environ.pop("STRICT_CONFIG_CONFLICTS", None)
    yield
    if original is not None:
        os.environ["STRICT_CONFIG_CONFLICTS"] = original


@pytest.fixture
def minimal_config(tmp_path):
    """Create minimal valid config structure."""
    config_dir = tmp_path / "config" / "aurora"
    config_dir.mkdir(parents=True)
    
    # instruments.yaml
    (config_dir / "instruments.yaml").write_text(yaml.dump({
        "instruments": {
            "BTCUSDT": {
                "tick_size": "0.01",
                "step_size": "0.00001",
                "base_asset": "BTC",
                "quote_asset": "USDT"
            }
        }
    }))
    
    # aurora_instruments.yaml
    (config_dir / "aurora_instruments.yaml").write_text(yaml.dump({
        "aurora_instruments": {
            "BTCUSDT": {}  # empty - no extra fields to trigger validation errors
        }
    }))
    
    # domains.yaml (simplified - no domains dict, just decision_making)
    (config_dir / "domains.yaml").write_text(yaml.dump({
        "decision_making": {
            "position_sizing": {
                "min_position_size_usd": 10
            }
        }
    }))
    
    # regime.yaml
    (config_dir / "regime.yaml").write_text(yaml.dump({
        "models": {},
        "hmm": {"states": 2}
    }))
    
    # strategies.yaml
    (config_dir / "strategies.yaml").write_text(yaml.dump({
        "assignments": {},
        "arbitration": {"mode": "priority"}
    }))
    
    # system.yaml (must include required bridge config)
    (config_dir / "system.yaml").write_text(yaml.dump({
        "trading_mode": "testnet",
        "bridge": {"retry_scheduler": {"max_attempts": 5, "min_retry_delay_ms": 500}},
    }))
    
    # trading.yaml (clean, no deprecated sections)
    (config_dir / "trading.yaml").write_text(yaml.dump({
        "runtime": {"mode": "backtest", "exchange": "binance"},
        "trading": {
            "mode": "testnet",
            "decision": {"signal_threshold": 0.1, "symbols_to_track": ["BTCUSDT"]},
            "risk_management": {"data_sources": {"portfolio_state": "testnet", "market_data": "live"}},
        },
        "binance_api": {
            "testnet": {"api_key": "x", "api_secret": "y", "rest_url": "https://test"},
            "live": {"api_key": "x", "api_secret": "y", "rest_url": "https://live"},
        },
    }))
    
    return config_dir


def test_strict_mode_default_active(clean_env):
    """T1: Strict mode active by default (no env set)."""
    # STRICT_CONFIG_CONFLICTS not set → strict=True
    assert "STRICT_CONFIG_CONFLICTS" not in os.environ
    assert ConfigLoader._get_strict_mode() is True


def test_strict_mode_opt_out(clean_env):
    """T2: Opt-out works (STRICT_CONFIG_CONFLICTS=0)."""
    os.environ["STRICT_CONFIG_CONFLICTS"] = "0"
    assert ConfigLoader._get_strict_mode() is False
    
    os.environ["STRICT_CONFIG_CONFLICTS"] = "false"
    assert ConfigLoader._get_strict_mode() is False


def test_strict_mode_explicit_enable(clean_env):
    """T1 variant: Explicit enable works."""
    os.environ["STRICT_CONFIG_CONFLICTS"] = "1"
    assert ConfigLoader._get_strict_mode() is True
    
    os.environ["STRICT_CONFIG_CONFLICTS"] = "true"
    assert ConfigLoader._get_strict_mode() is True


def test_feature_engineering_in_trading_yaml_strict_crash(minimal_config, clean_env):
    """T3: trading.yaml with feature_engineering + strict → ValueError."""
    config_dir = minimal_config
    
    # Add deprecated feature_engineering to trading.yaml
    (config_dir / "trading.yaml").write_text(yaml.dump({
        "runtime": {"mode": "backtest", "exchange": "binance"},
        "trading": {
            "mode": "testnet",
            "decision": {"signal_threshold": 0.1, "symbols_to_track": ["BTCUSDT"]},
            "risk_management": {"data_sources": {"portfolio_state": "testnet", "market_data": "live"}},
        },
        "binance_api": {
            "testnet": {"api_key": "x", "api_secret": "y", "rest_url": "https://test"},
            "live": {"api_key": "x", "api_secret": "y", "rest_url": "https://live"},
        },
        "feature_engineering": {"enabled": True, "lookback_periods": [120]}
    }))
    
    # Strict mode (default) → should crash
    os.environ.pop("STRICT_CONFIG_CONFLICTS", None)
    
    loader = ConfigLoader(config_dir=config_dir)
    from apps.reference.config_contract import ConfigContractError
    with pytest.raises(ConfigContractError, match="DEPRECATED: feature_engineering detected in trading.yaml"):
        loader.load_config()


def test_feature_engineering_in_trading_yaml_nonstrict_still_fails(minimal_config, clean_env):
    """T4: Deprecated feature_engineering always fails (no soft mode)."""
    config_dir = minimal_config
    
    # Add deprecated feature_engineering to trading.yaml
    (config_dir / "trading.yaml").write_text(yaml.dump({
        "runtime": {"mode": "backtest", "exchange": "binance"},
        "trading": {
            "mode": "testnet",
            "decision": {"signal_threshold": 0.1, "symbols_to_track": ["BTCUSDT"]},
            "risk_management": {"data_sources": {"portfolio_state": "testnet", "market_data": "live"}},
        },
        "binance_api": {
            "testnet": {"api_key": "x", "api_secret": "y", "rest_url": "https://test"},
            "live": {"api_key": "x", "api_secret": "y", "rest_url": "https://live"},
        },
        "feature_engineering": {"enabled": False}
    }))
    
    # Opt-out strict mode (should not change deprecated policy)
    os.environ["STRICT_CONFIG_CONFLICTS"] = "0"
    
    loader = ConfigLoader(config_dir=config_dir)
    from apps.reference.config_contract import ConfigContractError
    with pytest.raises(ConfigContractError):
        loader.load_config()


def test_clean_config_loads_in_strict_mode(minimal_config, clean_env):
    """T5: Clean config (no deprecated sections) loads in strict mode."""
    config_dir = minimal_config
    
    # trading.yaml already clean (no feature_engineering)
    # Strict mode (default)
    os.environ.pop("STRICT_CONFIG_CONFLICTS", None)
    
    # Should load without errors
    loader = ConfigLoader(config_dir=config_dir)
    config = loader.load_config()
    assert config is not None
    assert loader._get_strict_mode() is True


def test_sanity_features_yaml_deprecated_strict(minimal_config, clean_env):
    """T6a: Sanity check features.yaml deprecation still works (TASK 06)."""
    config_dir = minimal_config
    
    # Create orphaned features.yaml (deprecated in TASK 06)
    (config_dir / "features.yaml").write_text(yaml.dump({"features": ["RSI"]}))
    
    # Strict mode
    os.environ.pop("STRICT_CONFIG_CONFLICTS", None)
    
    loader = ConfigLoader(config_dir=config_dir)
    from apps.reference.config_contract import ConfigContractError
    with pytest.raises(ConfigContractError, match="features.yaml detected"):
        loader.load_config()


def test_sanity_mean_reversion_in_trading_yaml_strict(minimal_config, clean_env):
    """T6b: Sanity check MR in trading.yaml deprecation still works (TASK 08)."""
    config_dir = minimal_config
    
    # Add deprecated mean_reversion_1m to trading.yaml
    (config_dir / "trading.yaml").write_text(yaml.dump({
        "runtime": {"mode": "backtest"},
        "trading": {
            "mode": "testnet",
            "decision": {"signal_threshold": 0.1, "symbols_to_track": ["BTCUSDT"]},
            "risk_management": {"data_sources": {"portfolio_state": "testnet", "market_data": "live"}},
        },
        "binance_api": {
            "testnet": {"api_key": "x", "api_secret": "y", "rest_url": "https://test"},
            "live": {"api_key": "x", "api_secret": "y", "rest_url": "https://live"},
        },
        "mean_reversion_1m": {"enabled": True}
    }))
    
    # Strict mode
    os.environ.pop("STRICT_CONFIG_CONFLICTS", None)
    
    loader = ConfigLoader(config_dir=config_dir)
    from apps.reference.config_contract import ConfigContractError
    with pytest.raises(ConfigContractError, match="DEPRECATED: mean_reversion_1m detected in trading.yaml"):
        loader.load_config()
