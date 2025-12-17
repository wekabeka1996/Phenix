"""
CFG-TRADING-YAML-BURN-DOWN-02: Final SSOT cleanup - remove all mirrors.

Tests that:
1. No fallback to trading.domains/instruments (fail-fast only)
2. Strict mode detects and fails on deprecated sections
3. SSOT files are mandatory
4. No mirrors exist in config
"""

import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from apps.reference.config_loader import ConfigLoader


@pytest.fixture
def temp_config_dir():
    """Create temporary config directory for isolated tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def write_yaml(path: Path, data: Dict[str, Any]) -> None:
    """Helper to write YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(data, f)


# =============================================================================
# Test A: Strict mode enforcement
# =============================================================================


def test_strict_mode_fails_when_trading_domains_present(temp_config_dir, monkeypatch):
    """
    CFG-TRADING-YAML-BURN-DOWN-02: Test that trading.domains triggers FAIL in strict mode.
    
    Setup:
    - domains.yaml present (SSOT)
    - trading.yaml has trading.domains (deprecated)
    - STRICT_CONFIG_CONFLICTS=1
    
    Expected:
    - ValueError raised with clear message
    """
    monkeypatch.setenv("STRICT_CONFIG_CONFLICTS", "1")

    write_yaml(
        temp_config_dir / "system.yaml",
        {"trading_mode": "testnet", "log_level": "INFO"},
    )
    write_yaml(temp_config_dir / "regime.yaml", {"regime": {"detection": {"enabled": False}}})
    write_yaml(
        temp_config_dir / "domains.yaml",
        {"decision_making": {"qos": {"mode": "strict"}}},
    )
    write_yaml(
        temp_config_dir / "instruments.yaml",
        {
            "TESTUSDT": {
                "symbol": "TESTUSDT",
                "tick_size": "0.01",
                "step_size": "0.1",
            }
        },
    )

    # Trading.yaml with deprecated trading.domains
    write_yaml(
        temp_config_dir / "trading.yaml",
        {
            "trading": {
                "mode": "testnet",
                "domains": {  # DEPRECATED - should trigger error
                    "decision_making": {"qos": {"mode": "defer"}}
                },
            }
        },
    )

    loader = ConfigLoader(temp_config_dir)

    # Should raise ValueError in strict mode
    with pytest.raises(ValueError, match="DEPRECATED.*trading.domains"):
        loader.load_config()


def test_strict_mode_fails_when_trading_instruments_present(temp_config_dir, monkeypatch):
    """
    CFG-TRADING-YAML-BURN-DOWN-02: Test that trading.instruments triggers FAIL in strict mode.
    
    Setup:
    - instruments.yaml present (SSOT)
    - trading.yaml has trading.instruments (deprecated)
    - STRICT_CONFIG_CONFLICTS=1
    
    Expected:
    - ValueError raised with clear message
    """
    monkeypatch.setenv("STRICT_CONFIG_CONFLICTS", "1")

    write_yaml(
        temp_config_dir / "system.yaml",
        {"trading_mode": "testnet", "log_level": "INFO"},
    )
    write_yaml(temp_config_dir / "regime.yaml", {"regime": {"detection": {"enabled": False}}})
    write_yaml(
        temp_config_dir / "domains.yaml",
        {"decision_making": {"qos": {"mode": "shadow"}}},
    )
    write_yaml(
        temp_config_dir / "instruments.yaml",
        {
            "BTCUSDT": {
                "symbol": "BTCUSDT",
                "tick_size": "0.10",
                "step_size": "0.001",
            }
        },
    )

    # Trading.yaml with deprecated trading.instruments
    write_yaml(
        temp_config_dir / "trading.yaml",
        {
            "trading": {
                "mode": "testnet",
                "instruments": {  # DEPRECATED - should trigger error
                    "ETHUSDT": {
                        "symbol": "ETHUSDT",
                        "tick_size": "0.01",
                        "step_size": "0.001",
                    }
                },
            }
        },
    )

    loader = ConfigLoader(temp_config_dir)

    # Should raise ValueError in strict mode
    with pytest.raises(ValueError, match="DEPRECATED.*trading.instruments"):
        loader.load_config()


# =============================================================================
# Test B: Fail-fast on missing SSOT
# =============================================================================


def test_missing_instruments_yaml_fails_fast(temp_config_dir):
    """
    CFG-TRADING-YAML-BURN-DOWN-02: Test that missing instruments.yaml causes fail-fast.
    
    Setup:
    - No instruments.yaml (missing SSOT)
    - trading.yaml exists but has no trading.instruments
    
    Expected:
    - ValueError raised (no fallback allowed)
    """
    write_yaml(
        temp_config_dir / "system.yaml",
        {"trading_mode": "testnet", "log_level": "INFO"},
    )
    write_yaml(temp_config_dir / "regime.yaml", {"regime": {"detection": {"enabled": False}}})
    write_yaml(
        temp_config_dir / "domains.yaml",
        {"decision_making": {"qos": {"mode": "shadow"}}},
    )

    # NO instruments.yaml

    write_yaml(
        temp_config_dir / "trading.yaml",
        {"trading": {"mode": "testnet"}},
    )

    loader = ConfigLoader(temp_config_dir)

    # Should raise ValueError
    with pytest.raises(ValueError, match="No instruments configuration found"):
        loader.load_config()


def test_missing_domains_yaml_fails_fast(temp_config_dir):
    """
    CFG-TRADING-YAML-BURN-DOWN-02: Test that missing domains.yaml causes fail-fast.
    
    Setup:
    - No domains.yaml (missing SSOT)
    - trading.yaml exists but has no trading.domains
    
    Expected:
    - ValueError raised (no fallback allowed)
    """
    write_yaml(
        temp_config_dir / "system.yaml",
        {"trading_mode": "testnet", "log_level": "INFO"},
    )
    write_yaml(temp_config_dir / "regime.yaml", {"regime": {"detection": {"enabled": False}}})

    # NO domains.yaml

    write_yaml(
        temp_config_dir / "instruments.yaml",
        {
            "TESTUSDT": {
                "symbol": "TESTUSDT",
                "tick_size": "0.01",
                "step_size": "0.1",
            }
        },
    )

    write_yaml(
        temp_config_dir / "trading.yaml",
        {"trading": {"mode": "testnet"}},
    )

    loader = ConfigLoader(temp_config_dir)

    # Should raise ValueError
    with pytest.raises(ValueError, match="No domains configuration found"):
        loader.load_config()


# =============================================================================
# Test C: Clean config (SSOT only)
# =============================================================================


def test_clean_config_with_ssot_only(temp_config_dir):
    """
    CFG-TRADING-YAML-BURN-DOWN-02: Test that clean config (SSOT only) loads successfully.
    
    Setup:
    - domains.yaml present
    - instruments.yaml present
    - trading.yaml has NO deprecated sections
    
    Expected:
    - Config loads successfully
    - config.domains populated from domains.yaml
    - config.instruments populated from instruments.yaml
    """
    write_yaml(
        temp_config_dir / "system.yaml",
        {"trading_mode": "testnet", "log_level": "INFO"},
    )
    write_yaml(temp_config_dir / "regime.yaml", {"regime": {"detection": {"enabled": False}}})
    write_yaml(
        temp_config_dir / "domains.yaml",
        {"decision_making": {"qos": {"mode": "shadow"}}},
    )
    write_yaml(
        temp_config_dir / "instruments.yaml",
        {
            "BTCUSDT": {
                "symbol": "BTCUSDT",
                "tick_size": "0.10",
                "step_size": "0.001",
            }
        },
    )

    # Clean trading.yaml - NO deprecated sections
    write_yaml(
        temp_config_dir / "trading.yaml",
        {
            "trading": {
                "mode": "testnet",
                "decision": {
                    "symbols_to_track": ["BTCUSDT"],
                },
            }
        },
    )

    loader = ConfigLoader(temp_config_dir)
    config = loader.load_config()

    # Assert: config populated from SSOT
    assert config.domains is not None
    assert config.domains.decision_making.qos.mode == "shadow"
    
    assert config.instruments is not None
    assert "BTCUSDT" in config.instruments
    assert config.instruments["BTCUSDT"].tick_size == 0.10


# =============================================================================
# Test D: Non-strict mode warnings
# =============================================================================


def test_non_strict_mode_warns_but_loads(temp_config_dir):
    """
    CFG-TRADING-YAML-BURN-DOWN-02: Test that non-strict mode warns but allows load.
    
    Setup:
    - SSOT files present
    - trading.yaml has deprecated sections
    - STRICT_CONFIG_CONFLICTS=0 (default)
    
    Expected:
    - WARNING logged
    - Config loads (deprecated sections ignored)
    """
    write_yaml(
        temp_config_dir / "system.yaml",
        {"trading_mode": "testnet", "log_level": "INFO"},
    )
    write_yaml(temp_config_dir / "regime.yaml", {"regime": {"detection": {"enabled": False}}})
    write_yaml(
        temp_config_dir / "domains.yaml",
        {"decision_making": {"qos": {"mode": "shadow"}}},
    )
    write_yaml(
        temp_config_dir / "instruments.yaml",
        {
            "BTCUSDT": {
                "symbol": "BTCUSDT",
                "tick_size": "0.10",
                "step_size": "0.001",
            }
        },
    )

    # Trading.yaml with deprecated sections (should trigger WARNING)
    write_yaml(
        temp_config_dir / "trading.yaml",
        {
            "trading": {
                "mode": "testnet",
                "decision": {
                    "symbols_to_track": ["BTCUSDT"],
                },
                "domains": {  # DEPRECATED
                    "decision_making": {"qos": {"mode": "defer"}}
                },
                "instruments": {  # DEPRECATED
                    "ETHUSDT": {
                        "symbol": "ETHUSDT",
                        "tick_size": "0.01",
                        "step_size": "0.001",
                    }
                },
            }
        },
    )

    loader = ConfigLoader(temp_config_dir)
    
    # Should load (with warnings, but not fail)
    config = loader.load_config()
    
    # Assert: SSOT data wins
    assert config.domains.decision_making.qos.mode == "shadow"  # From domains.yaml
    assert "BTCUSDT" in config.instruments  # From instruments.yaml
    assert "ETHUSDT" not in config.instruments  # trading.instruments ignored
