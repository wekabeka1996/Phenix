"""
CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION: Strategies Registry Strict Tests

Tests verify:
1. Strict mode fails if strategies.yaml missing
2. Extra keys in strategies.yaml cause Pydantic ValidationError (extra='forbid')
3. Assignments validation (valid strategy IDs)
4. Arbitration config validation
"""
import os
import tempfile
import pytest
from pathlib import Path
from apps.reference.config_loader import ConfigLoader
from pydantic import ValidationError


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CANON_AURORA_DIR = _REPO_ROOT / "config" / "aurora"


def _read_canonical_yaml(rel_path: str) -> str:
  return (_CANON_AURORA_DIR / rel_path).read_text(encoding="utf-8")


@pytest.fixture
def temp_config_dir():
    """Create temporary config directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def base_strategies_yaml():
    """Minimal valid strategies.yaml content."""
    return """
version: "1.0.0"

assignments:
  ETHUSDT:
    - aurora
  BTCUSDT:
    - aurora
    - mean_reversion

arbitration:
  mode: priority
  window_ms: 1000
  priority:
    aurora: 1
    mean_reversion: 2
  logging:
    rejected_why_prefix: "ARBITRATION_REJECT"
    log_level: "INFO"
"""


@pytest.fixture
def base_trading_yaml():
    """Canonical trading.yaml (kept in sync with strict config contract)."""
    return _read_canonical_yaml("trading.yaml")


@pytest.fixture
def base_system_yaml():
    """Canonical system.yaml (strict, no-defaults compatible)."""
    return _read_canonical_yaml("system.yaml")


@pytest.fixture
def base_regime_yaml():
    """Canonical regime.yaml."""
    return _read_canonical_yaml("regime.yaml")


@pytest.fixture
def base_domains_yaml():
    """Canonical domains.yaml (SSOT)."""
    return _read_canonical_yaml("domains.yaml")



@pytest.fixture
def base_instruments_yaml():
    """Canonical instruments.yaml (SSOT)."""
    return _read_canonical_yaml("instruments.yaml")


@pytest.fixture(autouse=True)
def create_strategy_profiles(temp_config_dir):
    """CFG-STRATEGIES-SSOT-03: Create strategy profile files (aurora.yaml, mean_reversion.yaml)."""
    strategies_dir = temp_config_dir / "strategies"
    strategies_dir.mkdir(parents=True, exist_ok=True)

    # Use canonical strategy profiles to stay in sync with strict schema.
    (strategies_dir / "aurora.yaml").write_text(
        _read_canonical_yaml("strategies/aurora.yaml"), encoding="utf-8"
    )
    (strategies_dir / "mean_reversion.yaml").write_text(
        _read_canonical_yaml("strategies/mean_reversion.yaml"), encoding="utf-8"
    )


def test_strict_mode_fails_on_missing_strategies_yaml(
    temp_config_dir, base_trading_yaml, base_system_yaml, base_regime_yaml, base_domains_yaml, base_instruments_yaml
):
    """Test A1: Strict mode fails when strategies.yaml is missing."""
    # Setup: NO strategies.yaml
    (temp_config_dir / "trading.yaml").write_text(base_trading_yaml)
    (temp_config_dir / "system.yaml").write_text(base_system_yaml)
    (temp_config_dir / "regime.yaml").write_text(base_regime_yaml)
    (temp_config_dir / "domains.yaml").write_text(base_domains_yaml)
    (temp_config_dir / "instruments.yaml").write_text(base_instruments_yaml)

    # Enable strict mode
    os.environ["STRICT_CONFIG_CONFLICTS"] = "1"
    try:
        loader = ConfigLoader(config_dir=temp_config_dir)
        
        from apps.reference.config_contract import ConfigContractError
        with pytest.raises(ConfigContractError) as exc_info:
            loader.load_config()

        error_msg = str(exc_info.value)
        assert "strategies.yaml" in error_msg.lower(), \
            "Strict mode должен fail с упоминанием strategies.yaml"
    finally:
        os.environ.pop("STRICT_CONFIG_CONFLICTS", None)


def test_missing_strategies_yaml_fails_even_non_strict(
    temp_config_dir, base_trading_yaml, base_system_yaml, base_regime_yaml, base_domains_yaml, base_instruments_yaml
):
    """Test A2: strategies.yaml is mandatory even in non-strict mode."""
    # Setup: NO strategies.yaml
    (temp_config_dir / "trading.yaml").write_text(base_trading_yaml)
    (temp_config_dir / "system.yaml").write_text(base_system_yaml)
    (temp_config_dir / "regime.yaml").write_text(base_regime_yaml)
    (temp_config_dir / "domains.yaml").write_text(base_domains_yaml)
    (temp_config_dir / "instruments.yaml").write_text(base_instruments_yaml)

    # Disable strict mode
    os.environ["STRICT_CONFIG_CONFLICTS"] = "0"
    try:
        loader = ConfigLoader(config_dir=temp_config_dir)
        from apps.reference.config_contract import ConfigContractError
        with pytest.raises(ConfigContractError):
            loader.load_config()
    finally:
        os.environ.pop("STRICT_CONFIG_CONFLICTS", None)


def test_strategies_yaml_extra_keys_fail_validation(
    temp_config_dir, base_trading_yaml, base_system_yaml, base_regime_yaml, base_domains_yaml,
    base_instruments_yaml
):
    """Test B: Extra keys in strategies.yaml cause Pydantic ValidationError (extra='forbid')."""
    strategies_with_extra_key = """
version: "1.0.0"

assignments:
  ETHUSDT:
    - aurora

arbitration:
  mode: priority
  window_ms: 1000
  priority:
    aurora: 1
  logging:
    rejected_why_prefix: "ARBITRATION_REJECT"
    log_level: "INFO"

# Extra invalid key (should fail with extra='forbid')
unknown_key: "invalid"
"""

    (temp_config_dir / "strategies.yaml").write_text(strategies_with_extra_key)
    (temp_config_dir / "trading.yaml").write_text(base_trading_yaml)
    (temp_config_dir / "system.yaml").write_text(base_system_yaml)
    (temp_config_dir / "regime.yaml").write_text(base_regime_yaml)
    (temp_config_dir / "domains.yaml").write_text(base_domains_yaml)
    (temp_config_dir / "instruments.yaml").write_text(base_instruments_yaml)

    loader = ConfigLoader(config_dir=temp_config_dir)
    
    with pytest.raises(ValidationError) as exc_info:
        loader.load_config()

    error_msg = str(exc_info.value)
    assert "extra" in error_msg.lower() or "unexpected" in error_msg.lower(), \
        "ValidationError должен упоминать extra/unexpected fields"


def test_strategies_yaml_loads_successfully(
    temp_config_dir, base_strategies_yaml, base_trading_yaml, base_system_yaml,
    base_regime_yaml, base_domains_yaml, base_instruments_yaml
):
    """Test C: Valid strategies.yaml loads successfully with correct structure."""
    (temp_config_dir / "strategies.yaml").write_text(base_strategies_yaml)
    (temp_config_dir / "trading.yaml").write_text(base_trading_yaml)
    (temp_config_dir / "system.yaml").write_text(base_system_yaml)
    (temp_config_dir / "regime.yaml").write_text(base_regime_yaml)
    (temp_config_dir / "domains.yaml").write_text(base_domains_yaml)
    (temp_config_dir / "instruments.yaml").write_text(base_instruments_yaml)

    loader = ConfigLoader(config_dir=temp_config_dir)
    config = loader.load_config()

    # Verify strategies_registry loaded
    assert config.strategies_registry is not None, "strategies_registry должен загрузиться"
    assert config.strategies_registry.version == "1.0.0"
    
    # Verify assignments
    assert "ETHUSDT" in config.strategies_registry.assignments
    assert "aurora" in config.strategies_registry.assignments["ETHUSDT"]
    
    assert "BTCUSDT" in config.strategies_registry.assignments
    assert len(config.strategies_registry.assignments["BTCUSDT"]) == 2
    assert "aurora" in config.strategies_registry.assignments["BTCUSDT"]
    assert "mean_reversion" in config.strategies_registry.assignments["BTCUSDT"]
    
    # Verify arbitration
    assert config.strategies_registry.arbitration.mode == "priority"
    assert config.strategies_registry.arbitration.priority["aurora"] == 1
    assert config.strategies_registry.arbitration.priority["mean_reversion"] == 2
    assert config.strategies_registry.arbitration.logging.rejected_why_prefix == "ARBITRATION_REJECT"


def test_invalid_mode_fails_validation(
    temp_config_dir, base_trading_yaml, base_system_yaml,
    base_regime_yaml, base_domains_yaml, base_instruments_yaml
):
    """Test D: Invalid arbitration mode causes ValidationError."""
    strategies_with_invalid_mode = """
version: "1.0.0"

assignments:
  ETHUSDT:
    - aurora

arbitration:
  mode: prioirty  # TYPO: should be 'priority'
  window_ms: 1000
  priority:
    aurora: 1
  logging:
    rejected_why_prefix: "ARBITRATION_REJECT"
    log_level: "INFO"
"""

    (temp_config_dir / "strategies.yaml").write_text(strategies_with_invalid_mode)
    (temp_config_dir / "trading.yaml").write_text(base_trading_yaml)
    (temp_config_dir / "system.yaml").write_text(base_system_yaml)
    (temp_config_dir / "regime.yaml").write_text(base_regime_yaml)
    (temp_config_dir / "domains.yaml").write_text(base_domains_yaml)
    (temp_config_dir / "instruments.yaml").write_text(base_instruments_yaml)

    loader = ConfigLoader(config_dir=temp_config_dir)
    
    with pytest.raises(ValidationError) as exc_info:
        loader.load_config()

    error_msg = str(exc_info.value)
    assert "mode" in error_msg.lower() or "literal" in error_msg.lower(), \
        "ValidationError должен упоминать неправильный mode"


def test_missing_priority_for_hybrid_symbol_fails(
    temp_config_dir, base_trading_yaml, base_system_yaml,
    base_regime_yaml, base_domains_yaml, base_instruments_yaml
):
    """Test E: Missing priority for hybrid symbol strategy causes ValidationError."""
    strategies_missing_priority = """
version: "1.0.0"

assignments:
  BTCUSDT:
    - aurora
    - mean_reversion  # HYBRID

arbitration:
  mode: priority
  window_ms: 1000
  priority:
    aurora: 1
    # MISSING: mean_reversion priority
  logging:
    rejected_why_prefix: "ARBITRATION_REJECT"
    log_level: "INFO"
"""

    (temp_config_dir / "strategies.yaml").write_text(strategies_missing_priority)
    (temp_config_dir / "trading.yaml").write_text(base_trading_yaml)
    (temp_config_dir / "system.yaml").write_text(base_system_yaml)
    (temp_config_dir / "regime.yaml").write_text(base_regime_yaml)
    (temp_config_dir / "domains.yaml").write_text(base_domains_yaml)
    (temp_config_dir / "instruments.yaml").write_text(base_instruments_yaml)

    loader = ConfigLoader(config_dir=temp_config_dir)
    
    with pytest.raises(ValueError) as exc_info:
        loader.load_config()

    error_msg = str(exc_info.value)
    assert "missing_priority" in error_msg.lower() or "mean_reversion" in error_msg.lower(), \
        "ValueError должен упоминать missing_priority для mean_reversion"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
