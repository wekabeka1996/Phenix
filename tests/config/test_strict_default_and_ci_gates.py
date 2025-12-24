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
import shutil
from pathlib import Path
from apps.reference.config_loader import ConfigLoader
from pydantic import ValidationError


@pytest.fixture
def clean_env():
    """Cleanup STRICT_CONFIG_CONFLICTS env var."""
    original = os.environ.pop("STRICT_CONFIG_CONFLICTS", None)
    yield
    if original is not None:
        os.environ["STRICT_CONFIG_CONFLICTS"] = original


@pytest.fixture
def minimal_config(tmp_path):
    """Create a minimal *strict-valid* config directory by copying canonical SSOT."""
    config_dir = tmp_path / "config" / "aurora"

    repo_root = Path(__file__).resolve().parents[2]
    src = repo_root / "config" / "aurora"
    shutil.copytree(src, config_dir)
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
    
    # Add deprecated feature_engineering to trading.yaml (preserve required structure)
    trading_path = config_dir / "trading.yaml"
    payload = yaml.safe_load(trading_path.read_text())
    assert isinstance(payload, dict)
    payload["feature_engineering"] = {"enabled": True, "lookback_periods": [120]}
    trading_path.write_text(yaml.safe_dump(payload, sort_keys=False))
    
    # Strict mode (default) → should crash
    os.environ.pop("STRICT_CONFIG_CONFLICTS", None)
    
    loader = ConfigLoader(config_dir=config_dir)
    from apps.reference.config_contract import ConfigContractError
    with pytest.raises(ConfigContractError, match="DEPRECATED: feature_engineering detected in trading.yaml"):
        loader.load_config()


def test_feature_engineering_in_trading_yaml_nonstrict_still_fails(minimal_config, clean_env):
    """T4: Deprecated feature_engineering always fails (no soft mode)."""
    config_dir = minimal_config
    
    # Add deprecated feature_engineering to trading.yaml (preserve required structure)
    trading_path = config_dir / "trading.yaml"
    payload = yaml.safe_load(trading_path.read_text())
    assert isinstance(payload, dict)
    payload["feature_engineering"] = {"enabled": False}
    trading_path.write_text(yaml.safe_dump(payload, sort_keys=False))
    
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


def test_fail_fast_missing_required_key_in_trading_yaml(minimal_config, clean_env):
    """Negative: missing required YAML key must fail fast (no permissive defaults)."""
    config_dir = minimal_config

    strategy_path = config_dir / "strategies" / "aurora.yaml"
    payload = yaml.safe_load(strategy_path.read_text())
    assert isinstance(payload, dict)

    # Remove a required key under aurora.decision (SSOT: strategies/aurora.yaml)
    del payload["aurora"]["decision"]["retry_ttl_ms"]
    strategy_path.write_text(yaml.safe_dump(payload, sort_keys=False))

    os.environ.pop("STRICT_CONFIG_CONFLICTS", None)
    loader = ConfigLoader(config_dir=config_dir)

    with pytest.raises(ValidationError) as exc_info:
        loader.load_config()

    msg = str(exc_info.value)
    assert (
        "strategies.aurora.decision.retry_ttl_ms" in msg
        or "aurora.decision.retry_ttl_ms" in msg
        or "retry_ttl_ms" in msg
    )


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
    
    # Add deprecated mean_reversion to trading.yaml (preserve required structure)
    trading_path = config_dir / "trading.yaml"
    payload = yaml.safe_load(trading_path.read_text())
    assert isinstance(payload, dict)
    payload["mean_reversion"] = {"enabled": True}
    trading_path.write_text(yaml.safe_dump(payload, sort_keys=False))
    
    # Strict mode
    os.environ.pop("STRICT_CONFIG_CONFLICTS", None)
    
    loader = ConfigLoader(config_dir=config_dir)
    from apps.reference.config_contract import ConfigContractError
    with pytest.raises(ConfigContractError, match="DEPRECATED: mean_reversion detected in trading.yaml"):
        loader.load_config()
