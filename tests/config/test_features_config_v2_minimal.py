"""
tests/config/test_features_config_v2_minimal.py
Verify features domain loads correctly and validator passes.

Constraint: EP-CONFIG-FEATURES-OVERRIDES-S9
"""

import pytest
from pathlib import Path
from apps.reference.config_loader import reload_config
from apps.reference.config_features import resolve_feature_engineering_config
from tools.config_validator_v2 import validate_config_v2


def test_features_yaml_exists_and_loads():
    """
    Scenario 1: config/domains/features.yaml exists and can be loaded.
    """
    features_path = Path(
        __file__).parents[2] / "config" / "domains" / "features.yaml"

    assert features_path.exists(
    ), f"features.yaml not found at {features_path}"

    # Load via config loader
    cfg = reload_config()

    assert cfg.config_v2 is not None, "config_v2 not loaded"
    assert cfg.config_v2.domains is not None, "config_v2.domains not loaded"
    assert "features" in cfg.config_v2.domains, "features domain not in config_v2.domains"

    features_cfg = cfg.config_v2.domains["features"]
    assert features_cfg is not None, "features domain is None"
    assert isinstance(
        features_cfg, dict), f"features domain should be dict, got {type(features_cfg)}"

    # Verify expected keys from specification.md
    assert "global" in features_cfg, "Missing 'global' section in features.yaml"
    assert "windows" in features_cfg, "Missing 'windows' section in features.yaml"
    assert "features" in features_cfg, "Missing 'features' section in features.yaml"
    assert "macro_sync" in features_cfg, "Missing 'macro_sync' section in features.yaml"


def test_features_resolver_can_parse_v2_config():
    """
    Scenario 2: resolve_feature_engineering_config can parse features.yaml without errors.
    """
    cfg = reload_config()

    # Should not raise ValueError about missing features domain
    try:
        features_config = resolve_feature_engineering_config(cfg)
    except ValueError as exc:
        if "missing or empty" in str(exc):
            pytest.fail(
                f"features domain should be present and valid, got error: {exc}")
        raise

    # Verify returned config
    assert features_config is not None, "resolve_feature_engineering_config returned None"
    assert features_config.source == "config_v2", f"Expected source=config_v2, got {features_config.source}"

    # Verify key fields from features.yaml
    assert features_config.enable_new_metrics is True, "enable_new_metrics should be True"
    assert features_config.ema_period_short == 3, f"ema_period_short should be 3, got {features_config.ema_period_short}"
    assert features_config.ema_period_long == 7, f"ema_period_long should be 7, got {features_config.ema_period_long}"
    assert features_config.macro_sync_enabled is True, "macro_sync_enabled should be True"
    assert features_config.macro_sync_anchors == ["BTCUSDT", "ETHUSDT"], \
        f"macro_sync_anchors should be ['BTCUSDT', 'ETHUSDT'], got {features_config.macro_sync_anchors}"


def test_features_validator_returns_ok_or_warning():
    """
    Scenario 3: config_validator_v2 should return features: ok (or warning, not error).
    """
    config_root = Path(__file__).parents[2]

    result = validate_config_v2(config_root=config_root)

    assert "features" in result["domains"], "features domain not validated"

    features_status = result["domains"]["features"]["status"]
    assert features_status in ["ok", "warning"], \
        f"features domain should be ok or warning, got {features_status}. Errors: {result['domains']['features'].get('errors', [])}"

    # Should not have critical errors
    features_errors = result["domains"]["features"].get("errors", [])
    assert not any("missing or empty" in str(e) for e in features_errors), \
        f"features should not error about missing domain: {features_errors}"


def test_features_yaml_matches_specification():
    """
    Scenario 4: features.yaml structure matches docs/config_v2/specification.md.
    """
    cfg = reload_config()
    features_cfg = cfg.config_v2.domains.get("features")

    assert features_cfg is not None, "features domain not loaded"

    # Specification requires these sections
    required_sections = ["global", "windows", "features", "macro_sync"]
    for section in required_sections:
        assert section in features_cfg, f"Missing required section '{section}' per specification.md"

    # Validate subsections
    assert "ema" in features_cfg["windows"], "Missing windows.ema"
    assert "volume" in features_cfg["windows"], "Missing windows.volume"
    assert "volatility" in features_cfg["windows"], "Missing windows.volatility"

    assert "ema" in features_cfg["features"], "Missing features.ema"
    assert "volume" in features_cfg["features"], "Missing features.volume"
    assert "volatility" in features_cfg["features"], "Missing features.volatility"
    assert "liquidity" in features_cfg["features"], "Missing features.liquidity"

    # Validate critical fields
    assert "enable_new_metrics" in features_cfg["global"], "Missing global.enable_new_metrics"
    assert "enabled" in features_cfg["macro_sync"], "Missing macro_sync.enabled"
    assert "anchors" in features_cfg["macro_sync"], "Missing macro_sync.anchors"


def test_features_domain_not_empty():
    """
    Scenario 5: features domain is not None/empty after loading.

    This was the original error: "AuroraConfig.config_v2.domains['features'] is missing or empty"
    """
    cfg = reload_config()

    features_cfg = cfg.config_v2.domains.get("features")

    assert features_cfg is not None, "features domain should not be None"
    assert len(features_cfg) > 0, "features domain should not be empty dict"
    assert isinstance(
        features_cfg, dict), f"features domain should be dict, got {type(features_cfg)}"


def test_validator_schema_status_ok():
    """
    Scenario 6: Validator schema status should be 'ok' (no schema errors).
    """
    config_root = Path(__file__).parents[2]

    result = validate_config_v2(config_root=config_root)

    schema_status = result["domains"]["schema"]["status"]
    schema_errors = result["domains"]["schema"].get("errors", [])

    assert schema_status == "ok", \
        f"Schema validation should pass, got status={schema_status}. Errors: {schema_errors}"
