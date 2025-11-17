"""FeatureEngineering resolver tests for config v2 only mode."""

from pathlib import Path
import yaml
import pytest

from apps.reference.config_loader import load_config
from apps.reference.config_features import resolve_feature_engineering_config
from apps.reference.config_models import FeatureEngineeringConfig


def _read_repo_features_yaml() -> dict:
    """Load repository features.yaml for expected values."""
    yaml_path = Path("config/domains/features.yaml")
    return yaml.safe_load(yaml_path.read_text(encoding="utf-8"))


def test_features_v2_happy_path():
    """Resolver should return config_v2-backed FeatureEngineeringConfig."""
    cfg = load_config().model_copy(deep=True)
    features_yaml = _read_repo_features_yaml()

    result = resolve_feature_engineering_config(cfg)

    assert isinstance(result, FeatureEngineeringConfig)
    assert result.source == "config_v2"
    assert result.enable_new_metrics is features_yaml["global"]["enable_new_metrics"]
    assert result.ema_period_short == features_yaml["windows"]["ema"]["period_short"]
    assert result.ema_period_long == features_yaml["windows"]["ema"]["period_long"]
    assert result.volume_window_sec == features_yaml["windows"]["volume"]["window_sec"]
    assert result.volume_sma_length == features_yaml["windows"]["volume"]["sma_length"]
    assert result.volatility_window_sec == features_yaml["windows"]["volatility"]["window_sec"]
    assert result.volatility_sma_length == features_yaml["windows"]["volatility"]["sma_length"]
    assert result.ema_bias_clamp == features_yaml["features"]["ema"]["bias_clamp"]
    assert result.volume_spike_cap == features_yaml["features"]["volume"]["spike_cap"]
    assert result.volatility_ratio_cap == features_yaml["features"]["volatility"]["ratio_cap"]
    assert result.liquidity_depth_half == features_yaml["features"]["liquidity"]["depth_half"]
    assert result.liquidity_kappa_min == features_yaml["features"]["liquidity"]["kappa_min"]
    assert result.liquidity_kappa_max == features_yaml["features"]["liquidity"]["kappa_max"]
    assert result.macro_sync_enabled is features_yaml["macro_sync"]["enabled"]
    assert result.macro_sync_anchors == features_yaml["macro_sync"]["anchors"]
    assert result.macro_sync_window == features_yaml["macro_sync"]["window"]


def test_features_v2_missing_config_raises():
    """Resolver must raise if config_v2.features payload absent."""
    cfg = load_config().model_copy(deep=True)
    cfg.config_v2.domains.pop("features", None)

    with pytest.raises(ValueError):
        resolve_feature_engineering_config(cfg)
