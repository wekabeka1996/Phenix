"""
Unit tests for FeatureEngineering config module.

Tests config loading, defaults, and edge cases for robustness.
"""

import pytest
from apps.reference.domains.feature_engineering.config import (
    FeatureEngineeringConfig,
    ConfigDefaults,
    EMAConfig,
    VolumeConfig,
    VolatilityConfig,
    LiquidityConfig,
    MacroSyncConfig,
)


def test_config_defaults():
    """Test that ConfigDefaults has expected values."""
    assert ConfigDefaults.EMA_PERIOD_SHORT == 3
    assert ConfigDefaults.EMA_PERIOD_LONG == 7
    assert ConfigDefaults.VOLUME_SMA_LENGTH == 5
    assert ConfigDefaults.VOLATILITY_SMA_LENGTH == 10
    assert ConfigDefaults.LIQUIDITY_DEPTH_HALF == 1000.0
    assert ConfigDefaults.EMA_BIAS_CLAMP == 0.02
    assert ConfigDefaults.VOLUME_SPIKE_CAP == 3.0
    assert ConfigDefaults.VOLATILITY_RATIO_CAP == 3.0


def test_empty_dict_config_uses_defaults():
    """Test that empty dict config returns all defaults."""
    config = FeatureEngineeringConfig({})

    assert config.enable_new_metrics == ConfigDefaults.ENABLE_NEW_METRICS
    assert config.ema.period_short == ConfigDefaults.EMA_PERIOD_SHORT
    assert config.ema.period_long == ConfigDefaults.EMA_PERIOD_LONG
    assert config.ema.bias_clamp == ConfigDefaults.EMA_BIAS_CLAMP

    assert config.volume.sma_length == ConfigDefaults.VOLUME_SMA_LENGTH
    assert config.volume.window_sec == ConfigDefaults.VOLUME_WINDOW_SEC
    assert config.volume.spike_cap == ConfigDefaults.VOLUME_SPIKE_CAP

    assert config.volatility.sma_length == ConfigDefaults.VOLATILITY_SMA_LENGTH
    assert config.volatility.window_sec == ConfigDefaults.VOLATILITY_WINDOW_SEC
    assert config.volatility.ratio_cap == ConfigDefaults.VOLATILITY_RATIO_CAP

    assert config.liquidity.depth_half == ConfigDefaults.LIQUIDITY_DEPTH_HALF
    assert config.liquidity.kappa_min == ConfigDefaults.LIQUIDITY_KAPPA_MIN
    assert config.liquidity.kappa_max == ConfigDefaults.LIQUIDITY_KAPPA_MAX

    assert config.macro_sync.enabled == ConfigDefaults.MACRO_SYNC_ENABLED
    assert config.macro_sync.anchors == ["BTCUSDT", "ETHUSDT"]
    assert config.macro_sync.window == ConfigDefaults.MACRO_SYNC_WINDOW


def test_dict_config_with_values():
    """Test dict config with custom values."""
    config_dict = {
        "trading": {
            "feature_engineering": {
                "enable_new_metrics": False,
                "ema": {
                    "period_short": 5,
                    "period_long": 10,
                    "bias_clamp": 0.03,
                },
                "volume": {
                    "sma_length": 7,
                    "window_sec": 120,
                    "spike_cap": 5.0,
                },
                "volatility": {
                    "sma_length": 15,
                    "window_sec": 90,
                    "ratio_cap": 4.0,
                },
                "liquidity": {
                    "depth_half": 2000.0,
                    "kappa_min": 0.4,
                    "kappa_max": 0.95,
                }
            },
            "market_data": {
                "macro_sync": {
                    "enabled": True,
                    "anchors": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
                    "window": 100,
                }
            }
        }
    }

    config = FeatureEngineeringConfig(config_dict)

    assert config.enable_new_metrics is False
    assert config.ema.period_short == 5
    assert config.ema.period_long == 10
    assert config.ema.bias_clamp == 0.03

    assert config.volume.sma_length == 7
    assert config.volume.window_sec == 120
    assert config.volume.spike_cap == 5.0

    assert config.volatility.sma_length == 15
    assert config.volatility.window_sec == 90
    assert config.volatility.ratio_cap == 4.0

    assert config.liquidity.depth_half == 2000.0
    assert config.liquidity.kappa_min == 0.4
    assert config.liquidity.kappa_max == 0.95

    assert config.macro_sync.enabled is True
    assert config.macro_sync.anchors == ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    assert config.macro_sync.window == 100


def test_partial_dict_config_fills_defaults():
    """Test that partial config fills missing values with defaults."""
    config_dict = {
        "trading": {
            "feature_engineering": {
                "ema": {
                    "period_short": 4,
                    # period_long missing - should use default
                }
            }
        }
    }

    config = FeatureEngineeringConfig(config_dict)

    assert config.ema.period_short == 4
    assert config.ema.period_long == ConfigDefaults.EMA_PERIOD_LONG  # default
    assert config.ema.bias_clamp == ConfigDefaults.EMA_BIAS_CLAMP  # default


def test_pydantic_model_config():
    """Test with Pydantic-like config object (attribute access)."""
    from types import SimpleNamespace

    # Simulate Pydantic model structure
    ema_cfg = SimpleNamespace(
        period_short=6,
        period_long=12,
        bias_clamp=0.025
    )

    fe_cfg = SimpleNamespace(
        enable_new_metrics=True,
        ema=ema_cfg
    )

    trading_cfg = SimpleNamespace(
        feature_engineering=fe_cfg
    )

    config_obj = SimpleNamespace(
        trading=trading_cfg
    )

    config = FeatureEngineeringConfig(config_obj)

    assert config.enable_new_metrics is True
    assert config.ema.period_short == 6
    assert config.ema.period_long == 12
    assert config.ema.bias_clamp == 0.025


def test_malformed_config_uses_defaults():
    """Test that malformed/invalid config gracefully falls back to defaults."""
    # Test with None
    config1 = FeatureEngineeringConfig(None)
    assert config1.ema.period_short == ConfigDefaults.EMA_PERIOD_SHORT

    # Test with invalid structure
    config2 = FeatureEngineeringConfig({"invalid": "structure"})
    assert config2.ema.period_short == ConfigDefaults.EMA_PERIOD_SHORT

    # Test with non-dict, non-object
    config3 = FeatureEngineeringConfig("invalid")
    assert config3.ema.period_short == ConfigDefaults.EMA_PERIOD_SHORT


def test_dataclass_defaults():
    """Test that dataclass constructors have proper defaults."""
    ema = EMAConfig()
    assert ema.period_short == ConfigDefaults.EMA_PERIOD_SHORT
    assert ema.period_long == ConfigDefaults.EMA_PERIOD_LONG
    assert ema.bias_clamp == ConfigDefaults.EMA_BIAS_CLAMP

    volume = VolumeConfig()
    assert volume.sma_length == ConfigDefaults.VOLUME_SMA_LENGTH
    assert volume.window_sec == ConfigDefaults.VOLUME_WINDOW_SEC
    assert volume.spike_cap == ConfigDefaults.VOLUME_SPIKE_CAP

    volatility = VolatilityConfig()
    assert volatility.sma_length == ConfigDefaults.VOLATILITY_SMA_LENGTH
    assert volatility.window_sec == ConfigDefaults.VOLATILITY_WINDOW_SEC
    assert volatility.ratio_cap == ConfigDefaults.VOLATILITY_RATIO_CAP

    liquidity = LiquidityConfig()
    assert liquidity.depth_half == ConfigDefaults.LIQUIDITY_DEPTH_HALF
    assert liquidity.kappa_min == ConfigDefaults.LIQUIDITY_KAPPA_MIN
    assert liquidity.kappa_max == ConfigDefaults.LIQUIDITY_KAPPA_MAX

    macro = MacroSyncConfig()
    assert macro.enabled == ConfigDefaults.MACRO_SYNC_ENABLED
    assert macro.anchors == ["BTCUSDT", "ETHUSDT"]
    assert macro.window == ConfigDefaults.MACRO_SYNC_WINDOW


def test_config_immutability():
    """Test that config values can be safely read multiple times."""
    config_dict = {
        "trading": {
            "feature_engineering": {
                "ema": {"period_short": 5}
            }
        }
    }

    config = FeatureEngineeringConfig(config_dict)

    # Read same value multiple times
    val1 = config.ema.period_short
    val2 = config.ema.period_short
    val3 = config.ema.period_short

    assert val1 == val2 == val3 == 5


def test_macro_sync_anchors_are_copied():
    """Test that default anchors list is properly copied (not referenced)."""
    config1 = FeatureEngineeringConfig({})
    config2 = FeatureEngineeringConfig({})

    # Modify one config's anchors
    config1.macro_sync.anchors.append("SOLUSDT")

    # Ensure other config is not affected
    assert "SOLUSDT" in config1.macro_sync.anchors
    assert "SOLUSDT" not in config2.macro_sync.anchors


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
