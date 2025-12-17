"""
CFG-AURORA-INSTRUMENTS-SSOT-01: Test suite for aurora_instruments SSOT enforcement

Tests verify:
1. aurora_instruments.yaml loads into config.aurora_instruments (root level, not trading.*)
2. Strict validation fails on unknown fields (extra='forbid')
3. Conflict detection for deprecated trading.aurora_instruments
4. Runtime does NOT read from config.trading.aurora_instruments (SSOT only)

Phase: CFG-AURORA-INSTRUMENTS-SSOT-01
Date: 2025-12-16
"""
import os
import tempfile
import pytest
from pathlib import Path
from apps.reference.config_loader import ConfigLoader
from pydantic import ValidationError


@pytest.fixture
def temp_config_dir():
    """Create temporary config directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def base_aurora_instruments_yaml():
    """Minimal valid aurora_instruments.yaml content."""
    return """
# Test aurora_instruments.yaml
ETHUSDT:
  weights:
    ema: 0.1
    volume: 0.2
  side_bias:
    penalty_factor: 0.5
    window_sec: 300
    target_ratio: 0.6
  exit:
    sl_pct: 0.02
    max_hold_sec: 600
  take_profit:
    tp_low_ratio: 0.5
    tp_high_ratio: 1.0
    partial_exit_pct: 0.5
  trailing_stop:
    enabled: false
    activation_pct: 0.02
    trail_pct: 0.01
    min_update_interval_sec: 5
  regime_thresholds:
    HIGH_VOLATILITY: 1.3
    DEFAULT: 1.0
  regime_sizing:
    HIGH_VOLATILITY: 0.5
    LOW_VOLATILITY: 1.5
"""


@pytest.fixture
def base_trading_yaml():
    """Minimal valid trading.yaml (no aurora_instruments)."""
    return """
mode: testnet
decision:
  signal_threshold: 0.1
  symbols_to_track: ["ETHUSDT"]
"""


@pytest.fixture
def base_domains_yaml():
    """Minimal domains.yaml for tests."""
    return """
decision_making:
  qos:
    mode: defer
    enforce: false
"""


@pytest.fixture
def base_instruments_yaml():
    """Minimal instruments.yaml for tests."""
    return """
ETHUSDT:
  symbol: ETHUSDT
  tick_size: 0.01
  step_size: 0.001
  min_qty: 0.001
  min_notional: 10.0
  quote: USDT
"""


@pytest.fixture
def base_system_yaml():
    """Minimal system.yaml for tests."""
    return """
logging:
  level: INFO
  file: logs/test.log
  format: json
"""


@pytest.fixture
def base_regime_yaml():
    """Minimal regime.yaml for tests."""
    return """
detection:
  enabled: false
"""


def test_aurora_instruments_ssot_loads_to_root_config(temp_config_dir, base_aurora_instruments_yaml, base_trading_yaml, base_domains_yaml, base_instruments_yaml, base_system_yaml, base_regime_yaml):
    """Test A: aurora_instruments.yaml loads into config.aurora_instruments (root level)."""
    # Setup
    (temp_config_dir / "aurora_instruments.yaml").write_text(base_aurora_instruments_yaml)
    (temp_config_dir / "trading.yaml").write_text(base_trading_yaml)
    (temp_config_dir / "domains.yaml").write_text(base_domains_yaml)
    (temp_config_dir / "instruments.yaml").write_text(base_instruments_yaml)
    (temp_config_dir / "system.yaml").write_text(base_system_yaml)
    (temp_config_dir / "regime.yaml").write_text(base_regime_yaml)

    loader = ConfigLoader(config_dir=temp_config_dir)
    config = loader.load_config()

    # Assertions
    assert hasattr(config, 'aurora_instruments'), "config.aurora_instruments должен существовать (root level)"
    assert isinstance(config.aurora_instruments, dict), "aurora_instruments должен быть dict"
    assert "ETHUSDT" in config.aurora_instruments, "ETHUSDT должен быть в aurora_instruments"

    ethusdt_cfg = config.aurora_instruments["ETHUSDT"]
    assert ethusdt_cfg.weights["ema"] == 0.1, "Вес ema должен быть 0.1"
    assert ethusdt_cfg.side_bias.penalty_factor == 0.5, "side_bias.penalty_factor должен быть 0.5"
    assert ethusdt_cfg.exit.sl_pct == 0.02, "exit.sl_pct должен быть 0.02"


def test_aurora_instruments_unknown_field_fails_strict_validation(temp_config_dir, base_trading_yaml, base_domains_yaml, base_instruments_yaml, base_system_yaml, base_regime_yaml):
    """Test B: Unknown field in aurora_instruments triggers ValidationError (extra='forbid')."""
    # Setup: aurora_instruments with unknown field
    invalid_aurora_instruments = """
ETHUSDT:
  weights:
    ema: 0.1
  side_bias:
    penalty_factor: 0.5
    window_sec: 300
    target_ratio: 0.6
  exit:
    sl_pct: 0.02
    max_hold_sec: 600
  take_profit:
    tp_low_ratio: 0.5
    tp_high_ratio: 1.0
    partial_exit_pct: 0.5
  trailing_stop:
    enabled: false
    activation_pct: 0.02
    trail_pct: 0.01
    min_update_interval_sec: 5
  regime_thresholds:
    DEFAULT: 1.0
  regime_sizing:
    DEFAULT: 1.0
  garbage_unknown_field: "should_fail"  # Unknown field
"""

    (temp_config_dir / "aurora_instruments.yaml").write_text(invalid_aurora_instruments)
    (temp_config_dir / "trading.yaml").write_text(base_trading_yaml)
    (temp_config_dir / "domains.yaml").write_text(base_domains_yaml)
    (temp_config_dir / "instruments.yaml").write_text(base_instruments_yaml)
    (temp_config_dir / "system.yaml").write_text(base_system_yaml)
    (temp_config_dir / "regime.yaml").write_text(base_regime_yaml)

    loader = ConfigLoader(config_dir=temp_config_dir)

    # Expect Pydantic ValidationError (extra='forbid')
    with pytest.raises(ValidationError) as exc_info:
        loader.load_config()

    # Check error mentions the unknown field
    error_str = str(exc_info.value)
    assert "garbage_unknown_field" in error_str or "Extra inputs are not permitted" in error_str, \
        "ValidationError должен упоминать unknown field или 'Extra inputs'"


def test_strict_mode_fails_on_trading_aurora_instruments_present(temp_config_dir, base_aurora_instruments_yaml, base_domains_yaml, base_instruments_yaml, base_system_yaml, base_regime_yaml):
    """Test C1: Strict mode fails when trading.aurora_instruments exists in trading.yaml."""
    # Setup: trading.yaml with aurora_instruments (deprecated)
    trading_with_aurora_instruments = """
mode: testnet
decision:
  signal_threshold: 0.1
  symbols_to_track: ["ETHUSDT"]

aurora_instruments:
  BTCUSDT:  # Deprecated section (minimal valid config to avoid Pydantic errors)
    weights:
      ema: 0.1
    side_bias:
      penalty_factor: 0.5
      window_sec: 300
      target_ratio: 0.6
    exit:
      sl_pct: 0.015
      max_hold_sec: 600
    take_profit:
      tp_low_ratio: 0.5
      tp_high_ratio: 1.0
      partial_exit_pct: 0.5
    trailing_stop:
      enabled: false
      activation_pct: 0.02
      trail_pct: 0.01
      min_update_interval_sec: 5
    regime_thresholds:
      DEFAULT: 1.0
    regime_sizing:
      DEFAULT: 1.0
"""

    (temp_config_dir / "aurora_instruments.yaml").write_text(base_aurora_instruments_yaml)
    (temp_config_dir / "trading.yaml").write_text(trading_with_aurora_instruments)
    (temp_config_dir / "domains.yaml").write_text(base_domains_yaml)
    (temp_config_dir / "instruments.yaml").write_text(base_instruments_yaml)
    (temp_config_dir / "system.yaml").write_text(base_system_yaml)
    (temp_config_dir / "regime.yaml").write_text(base_regime_yaml)

    # Enable strict mode
    os.environ["STRICT_CONFIG_CONFLICTS"] = "1"
    try:
        loader = ConfigLoader(config_dir=temp_config_dir)
        
        with pytest.raises(ValueError) as exc_info:
            loader.load_config()

        error_msg = str(exc_info.value)
        assert "trading.aurora_instruments" in error_msg or "DEPRECATED" in error_msg, \
            "Strict mode должен fail с упоминанием deprecated trading.aurora_instruments"
    finally:
        os.environ.pop("STRICT_CONFIG_CONFLICTS", None)


def test_non_strict_mode_warns_on_trading_aurora_instruments_present(temp_config_dir, base_aurora_instruments_yaml, base_domains_yaml, base_instruments_yaml, base_system_yaml, base_regime_yaml, caplog):
    """Test C2: Non-strict mode warns but loads when trading.aurora_instruments exists."""
    # Setup: trading.yaml with aurora_instruments (deprecated)
    trading_with_aurora_instruments = """
mode: testnet
decision:
  signal_threshold: 0.1
  symbols_to_track: ["ETHUSDT"]

aurora_instruments:
  BTCUSDT:  # Deprecated section (minimal valid config)
    weights:
      ema: 0.1
    side_bias:
      penalty_factor: 0.5
      window_sec: 300
      target_ratio: 0.6
    exit:
      sl_pct: 0.015
      max_hold_sec: 600
    take_profit:
      tp_low_ratio: 0.5
      tp_high_ratio: 1.0
      partial_exit_pct: 0.5
    trailing_stop:
      enabled: false
      activation_pct: 0.02
      trail_pct: 0.01
      min_update_interval_sec: 5
    regime_thresholds:
      DEFAULT: 1.0
    regime_sizing:
      DEFAULT: 1.0
"""

    (temp_config_dir / "aurora_instruments.yaml").write_text(base_aurora_instruments_yaml)
    (temp_config_dir / "trading.yaml").write_text(trading_with_aurora_instruments)
    (temp_config_dir / "domains.yaml").write_text(base_domains_yaml)
    (temp_config_dir / "instruments.yaml").write_text(base_instruments_yaml)
    (temp_config_dir / "system.yaml").write_text(base_system_yaml)
    (temp_config_dir / "regime.yaml").write_text(base_regime_yaml)

    # Disable strict mode (default)
    os.environ.pop("STRICT_CONFIG_CONFLICTS", None)

    loader = ConfigLoader(config_dir=temp_config_dir)
    config = loader.load_config()

    # Should load successfully
    assert config is not None, "Config должен загрузиться в non-strict mode"

    # Check warning was logged
    assert any("trading.aurora_instruments" in rec.message and "DEPRECATED" in rec.message 
               for rec in caplog.records), \
        "Non-strict mode должен логировать WARNING о deprecated trading.aurora_instruments"


def test_missing_aurora_instruments_yaml_allows_empty_dict(temp_config_dir, base_trading_yaml, base_domains_yaml, base_instruments_yaml, base_system_yaml, base_regime_yaml, caplog):
    """Test D: Missing aurora_instruments.yaml logs warning but allows empty config (backward compat)."""
    # Setup: NO aurora_instruments.yaml
    (temp_config_dir / "trading.yaml").write_text(base_trading_yaml)
    (temp_config_dir / "domains.yaml").write_text(base_domains_yaml)
    (temp_config_dir / "instruments.yaml").write_text(base_instruments_yaml)
    (temp_config_dir / "system.yaml").write_text(base_system_yaml)
    (temp_config_dir / "regime.yaml").write_text(base_regime_yaml)

    loader = ConfigLoader(config_dir=temp_config_dir)
    config = loader.load_config()

    # Should load with empty aurora_instruments
    assert hasattr(config, 'aurora_instruments'), "config.aurora_instruments должен существовать"
    assert config.aurora_instruments == {}, "aurora_instruments должен быть пустым dict"

    # Check warning was logged
    assert any("aurora_instruments.yaml NOT found" in rec.message 
               for rec in caplog.records), \
        "Должен быть WARNING о missing aurora_instruments.yaml"


def test_clean_config_with_aurora_instruments_ssot_only(temp_config_dir, base_aurora_instruments_yaml, base_trading_yaml, base_domains_yaml, base_instruments_yaml, base_system_yaml, base_regime_yaml):
    """Test E: Clean config (only SSOT, no deprecated sections) loads successfully."""
    # Setup: Clean config (no trading.aurora_instruments)
    (temp_config_dir / "aurora_instruments.yaml").write_text(base_aurora_instruments_yaml)
    (temp_config_dir / "trading.yaml").write_text(base_trading_yaml)
    (temp_config_dir / "domains.yaml").write_text(base_domains_yaml)
    (temp_config_dir / "instruments.yaml").write_text(base_instruments_yaml)
    (temp_config_dir / "system.yaml").write_text(base_system_yaml)
    (temp_config_dir / "regime.yaml").write_text(base_regime_yaml)

    loader = ConfigLoader(config_dir=temp_config_dir)
    config = loader.load_config()

    # Assertions
    assert config is not None, "Clean config должен загрузиться"
    assert hasattr(config, 'aurora_instruments'), "config.aurora_instruments должен существовать"
    assert "ETHUSDT" in config.aurora_instruments, "ETHUSDT должен быть в aurora_instruments"

    # Verify trading.aurora_instruments does NOT exist (removed in Phase 2)
    assert not hasattr(config.trading, 'aurora_instruments') or config.trading.aurora_instruments == {}, \
        "trading.aurora_instruments НЕ должен существовать (SSOT only)"


def test_runtime_no_access_to_trading_aurora_instruments(temp_config_dir, base_aurora_instruments_yaml, base_domains_yaml, base_instruments_yaml, base_system_yaml, base_regime_yaml):
    """Test F: Verify runtime CANNOT access config.trading.aurora_instruments (grep-style check)."""
    # This is more of a code review check, but we can verify the structure
    
    # Setup
    trading_yaml_clean = """
mode: testnet
decision:
  signal_threshold: 0.1
  symbols_to_track: ["ETHUSDT"]
# NO aurora_instruments section here
"""
    (temp_config_dir / "aurora_instruments.yaml").write_text(base_aurora_instruments_yaml)
    (temp_config_dir / "trading.yaml").write_text(trading_yaml_clean)
    (temp_config_dir / "domains.yaml").write_text(base_domains_yaml)
    (temp_config_dir / "instruments.yaml").write_text(base_instruments_yaml)
    (temp_config_dir / "system.yaml").write_text(base_system_yaml)
    (temp_config_dir / "regime.yaml").write_text(base_regime_yaml)

    loader = ConfigLoader(config_dir=temp_config_dir)
    config = loader.load_config()

    # Verify config.aurora_instruments exists (CANONICAL)
    assert hasattr(config, 'aurora_instruments'), "config.aurora_instruments должен быть доступен"
    assert "ETHUSDT" in config.aurora_instruments, "ETHUSDT должен быть в config.aurora_instruments"

    # Verify trading.aurora_instruments DOES NOT EXIST or is empty
    # (ConfigLoader no longer populates it after CFG-AURORA-INSTRUMENTS-SSOT-01)
    if hasattr(config.trading, 'aurora_instruments'):
        assert config.trading.aurora_instruments == {}, \
            "trading.aurora_instruments должен быть пустым (no mirror logic)"
    else:
        # If field doesn't exist at all, that's even better
        pass  # Test passes


def test_multiple_symbols_in_aurora_instruments(temp_config_dir, base_trading_yaml, base_domains_yaml, base_instruments_yaml, base_system_yaml, base_regime_yaml):
    """Test G: aurora_instruments.yaml with multiple symbols loads correctly."""
    multi_symbol_aurora_instruments = """
ETHUSDT:
  weights:
    ema: 0.1
  side_bias:
    penalty_factor: 0.5
    window_sec: 300
    target_ratio: 0.6
  exit:
    sl_pct: 0.02
    max_hold_sec: 600
  take_profit:
    tp_low_ratio: 0.5
    tp_high_ratio: 1.0
    partial_exit_pct: 0.5
  trailing_stop:
    enabled: false
    activation_pct: 0.02
    trail_pct: 0.01
    min_update_interval_sec: 5
  regime_thresholds:
    DEFAULT: 1.0
  regime_sizing:
    DEFAULT: 1.0

BTCUSDT:
  weights:
    ema: 0.2
  side_bias:
    penalty_factor: 0.6
    window_sec: 400
    target_ratio: 0.7
  exit:
    sl_pct: 0.025
    max_hold_sec: 700
  take_profit:
    tp_low_ratio: 0.6
    tp_high_ratio: 1.2
    partial_exit_pct: 0.6
  trailing_stop:
    enabled: true
    activation_pct: 0.03
    trail_pct: 0.015
    min_update_interval_sec: 10
  regime_thresholds:
    DEFAULT: 1.0
  regime_sizing:
    DEFAULT: 1.0
"""

    instruments_yaml_multi = """
ETHUSDT:
  symbol: ETHUSDT
  tick_size: 0.01
  step_size: 0.001
  min_qty: 0.001
  min_notional: 10.0
  quote: USDT
BTCUSDT:
  symbol: BTCUSDT
  tick_size: 0.1
  step_size: 0.001
  min_qty: 0.001
  min_notional: 10.0
  quote: USDT
"""

    (temp_config_dir / "aurora_instruments.yaml").write_text(multi_symbol_aurora_instruments)
    (temp_config_dir / "trading.yaml").write_text(base_trading_yaml)
    (temp_config_dir / "domains.yaml").write_text(base_domains_yaml)
    (temp_config_dir / "instruments.yaml").write_text(instruments_yaml_multi)
    (temp_config_dir / "system.yaml").write_text(base_system_yaml)  # FIX: Missing system.yaml
    (temp_config_dir / "regime.yaml").write_text(base_regime_yaml)  # FIX: Missing regime.yaml
