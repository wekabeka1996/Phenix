"""E2E test for config v2 migration - validates all resolvers return source="config_v2"."""

from apps.reference.domains.execution_position.manage_config import resolve_execution_manage_config
from apps.reference.domains.execution_position.brackets_config import resolve_brackets_config
from apps.reference.config_decision import resolve_decision_policy
from apps.reference.config_sizing import resolve_sizing_policy
from apps.reference.config_risk import resolve_daily_risk_state
from apps.reference.config_regimes import resolve_regime_detector_config
from apps.reference.config_features import resolve_feature_engineering_config
from apps.reference.config_exposure_policy import resolve_exposure_policy
from apps.reference.config_symbols import get_trading_symbols
from apps.reference.config_modes import compute_effective_trading_modes
from apps.reference.config_loader import get_config
import sys
from pathlib import Path
import yaml

sys.path.insert(0, str(Path.cwd()))


def test_all_resolvers_return_config_v2_source():
    """Test that all config resolvers return source="config_v2" after migration."""
    # Load real config v2
    config = get_config()

    # Test each resolver that should return objects with source attribute
    resolvers = [
        ("exposure_policy", lambda: resolve_exposure_policy(config)),
        ("feature_engineering", lambda: resolve_feature_engineering_config(config)),
        ("regime_detector", lambda: resolve_regime_detector_config(config)),
        ("decision_making", lambda: resolve_decision_policy(config)),
        ("execution_position", lambda: resolve_execution_manage_config(config)),
        ("brackets", lambda: resolve_brackets_config(config)),
    ]

    for name, resolver in resolvers:
        result = resolver()
        assert hasattr(
            result, 'source'), f"Resolver {name} result has no source attribute"
        assert result.source == "config_v2", f"Resolver {name} returned source='{result.source}', expected 'config_v2'"


def test_config_v2_structure_loaded():
    """Test that config v2 structure is properly loaded."""
    config = get_config()

    # Check that config_v2 exists
    assert hasattr(config, 'config_v2'), "Config has no config_v2 attribute"
    config_v2 = config.config_v2

    # Check core sections exist
    assert hasattr(config_v2, 'core'), "config_v2 has no core attribute"
    assert hasattr(config_v2, 'symbols'), "config_v2 has no symbols attribute"
    assert hasattr(
        config_v2, 'instruments'), "config_v2 has no instruments attribute"
    assert hasattr(config_v2, 'domains'), "config_v2 has no domains attribute"
    assert hasattr(config_v2, 'modes'), "config_v2 has no modes attribute"
    assert hasattr(
        config_v2, 'overrides'), "config_v2 has no overrides attribute"

    # Check expected domains are present
    expected_domains = [
        'decision', 'execution', 'features', 'regimes', 'risk', 'sizing'
    ]

    for domain in expected_domains:
        assert domain in config_v2.domains, f"Domain '{domain}' missing from config_v2.domains"

    # Check modes has profiles
    assert 'profiles' in config_v2.modes, "config_v2.modes has no profiles key"
    assert len(config_v2.modes['profiles']
               ) > 0, "config_v2.modes.profiles is empty"


def test_e2e_features_resolver_uses_config_v2():
    """FeatureEngineering resolver should pull values from config/domains/features.yaml."""
    config = get_config()
    features_cfg = resolve_feature_engineering_config(config)

    repo_yaml = yaml.safe_load(
        Path("config/domains/features.yaml").read_text(encoding="utf-8")
    )

    assert features_cfg.source == "config_v2"
    assert features_cfg.enable_new_metrics is repo_yaml["global"]["enable_new_metrics"]
    assert features_cfg.ema_period_short == repo_yaml["windows"]["ema"]["period_short"]
    assert features_cfg.ema_period_long == repo_yaml["windows"]["ema"]["period_long"]
    assert features_cfg.volume_window_sec == repo_yaml["windows"]["volume"]["window_sec"]
    assert features_cfg.volume_sma_length == repo_yaml["windows"]["volume"]["sma_length"]
    assert features_cfg.volatility_window_sec == repo_yaml["windows"]["volatility"]["window_sec"]
    assert features_cfg.volatility_sma_length == repo_yaml["windows"]["volatility"]["sma_length"]
    assert features_cfg.ema_bias_clamp == repo_yaml["features"]["ema"]["bias_clamp"]
    assert features_cfg.volume_spike_cap == repo_yaml["features"]["volume"]["spike_cap"]
    assert features_cfg.volatility_ratio_cap == repo_yaml["features"]["volatility"]["ratio_cap"]
    assert features_cfg.liquidity_depth_half == repo_yaml["features"]["liquidity"]["depth_half"]
    assert features_cfg.liquidity_kappa_min == repo_yaml["features"]["liquidity"]["kappa_min"]
    assert features_cfg.liquidity_kappa_max == repo_yaml["features"]["liquidity"]["kappa_max"]
    assert features_cfg.macro_sync_enabled is repo_yaml["macro_sync"]["enabled"]
    assert features_cfg.macro_sync_anchors == repo_yaml["macro_sync"]["anchors"]
    assert features_cfg.macro_sync_window == repo_yaml["macro_sync"]["window"]
