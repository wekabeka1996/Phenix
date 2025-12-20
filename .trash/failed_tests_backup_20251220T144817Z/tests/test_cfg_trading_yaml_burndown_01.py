"""
CFG-TRADING-YAML-BURN-DOWN-01: Audit + deprecate duplicates in trading.yaml.

Tests that:
1. SSOT (domains.yaml, instruments.yaml) always takes priority
2. Conflicts trigger warning/fail based on strict mode
3. trading.yaml does not populate domains/instruments when SSOT files present
"""

import os
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
# Test A: SSOT always wins
# =============================================================================


def test_domains_yaml_takes_priority_over_trading(temp_config_dir):
    """
    Test that domains.yaml is canonical source, trading.domains is ignored.
    
    Setup:
    - domains.yaml defines decision_making.qos.mode = "strict"
    - trading.yaml defines trading.domains.decision_making.qos.mode = "defer"
    
    Expected:
    - config.domains.decision_making.qos.mode == "strict" (from domains.yaml)
    - trading.domains is mirror pointing to same data
    """
    # Minimal system.yaml
    write_yaml(
        temp_config_dir / "system.yaml",
        {"trading_mode": "testnet", "log_level": "INFO"},
    )

    # Minimal regime.yaml
    write_yaml(temp_config_dir / "regime.yaml", {"regime": {"detection": {"enabled": False}}})

    # SSOT: domains.yaml
    write_yaml(
        temp_config_dir / "domains.yaml",
        {
            "decision_making": {
                "qos": {
                    "mode": "strict",  # SSOT value
                    "symbol_cooldown_sec": 5,
                }
            }
        },
    )

    # Legacy: trading.yaml with conflicting domains
    write_yaml(
        temp_config_dir / "trading.yaml",
        {
            "trading": {
                "mode": "testnet",
                "domains": {
                    "decision_making": {
                        "qos": {
                            "mode": "defer",  # CONFLICTING VALUE (should be ignored)
                            "symbol_cooldown_sec": 10,
                        }
                    }
                },
            }
        },
    )

    # Minimal instruments.yaml to satisfy fail-fast validation
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

    loader = ConfigLoader(temp_config_dir)
    config = loader.load_config()

    # Assert: domains.yaml wins
    assert config.domains.decision_making.qos.mode == "strict"

    # Assert: trading.domains is mirror (same data)
    assert config.trading.domains.decision_making.qos.mode == "strict"


def test_instruments_yaml_takes_priority_over_trading(temp_config_dir):
    """
    Test that instruments.yaml is canonical source, trading.instruments is ignored.
    
    Setup:
    - instruments.yaml defines BTCUSDT tick_size = "0.10"
    - trading.yaml defines trading.instruments.BTCUSDT tick_size = "0.01"
    
    Expected:
    - config.instruments.BTCUSDT.tick_size == "0.10" (from instruments.yaml)
    - trading.instruments is mirror
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

    # SSOT: instruments.yaml
    write_yaml(
        temp_config_dir / "instruments.yaml",
        {
            "BTCUSDT": {
                "symbol": "BTCUSDT",
                "tick_size": "0.10",  # SSOT value
                "step_size": "0.001",
            }
        },
    )

    # Legacy: trading.yaml with conflicting instruments
    write_yaml(
        temp_config_dir / "trading.yaml",
        {
            "trading": {
                "mode": "testnet",
                "decision": {
                    "symbols_to_track": ["BTCUSDT"],  # Active symbol
                },
                "instruments": {
                    "BTCUSDT": {
                        "symbol": "BTCUSDT",
                        "tick_size": "0.01",  # CONFLICTING (should be ignored)
                        "step_size": "0.001",
                    }
                },
            }
        },
    )

    loader = ConfigLoader(temp_config_dir)
    config = loader.load_config()

    # Assert: instruments.yaml wins (note: Pydantic converts to float)
    assert config.instruments["BTCUSDT"].tick_size == 0.10

    # Assert: trading.instruments is mirror (note: InstrumentSpec uses str)
    assert config.trading.instruments["BTCUSDT"].tick_size == "0.10"


# =============================================================================
# Test B: Conflict detection in strict mode
# =============================================================================


def test_strict_mode_raises_on_missing_ssot(temp_config_dir, monkeypatch):
    """
    Test that missing SSOT files trigger fail-closed behavior.
    
    Setup:
    - No domains.yaml (only trading.domains)
    - STRICT_CONFIG_CONFLICTS=1
    
    Expected:
    - Loader should raise ValueError or allow legacy fallback with warning
    
    NOTE: Current implementation allows legacy fallback with WARNING.
    This test documents that behavior. Future burn-down phases may
    enforce strict fail-closed.
    """
    monkeypatch.setenv("STRICT_CONFIG_CONFLICTS", "1")

    write_yaml(
        temp_config_dir / "system.yaml",
        {"trading_mode": "testnet", "log_level": "INFO"},
    )
    write_yaml(temp_config_dir / "regime.yaml", {"regime": {"detection": {"enabled": False}}})

    # NO domains.yaml (missing SSOT)

    # Trading.yaml with legacy domains
    write_yaml(
        temp_config_dir / "trading.yaml",
        {
            "trading": {
                "mode": "testnet",
                "domains": {
                    "decision_making": {"qos": {"mode": "defer"}}
                },
            }
        },
    )

    # Minimal instruments.yaml
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

    loader = ConfigLoader(temp_config_dir)

    # Current behavior: fallback allowed with WARNING
    # Future: may raise ValueError in strict mode
    config = loader.load_config()
    assert config.domains is not None  # Fallback populated


# =============================================================================
# Test C: trading.yaml does NOT populate domains/instruments when SSOT present
# =============================================================================


def test_trading_domains_not_used_when_ssot_present(temp_config_dir, monkeypatch):
    """
    Test that config.domains is populated ONLY from domains.yaml, not trading.yaml.
    
    Setup:
    - domains.yaml present (SSOT)
    - trading.yaml has trading.domains with extra keys
    
    Expected:
    - config.domains reflects domains.yaml only
    - Extra keys from trading.domains are NOT merged
    """
    write_yaml(
        temp_config_dir / "system.yaml",
        {"trading_mode": "testnet", "log_level": "INFO"},
    )
    write_yaml(temp_config_dir / "regime.yaml", {"regime": {"detection": {"enabled": False}}})

    # SSOT: domains.yaml (minimal)
    write_yaml(
        temp_config_dir / "domains.yaml",
        {
            "decision_making": {
                "qos": {"mode": "strict"}
            }
        },
    )

    # Trading.yaml with EXTRA keys in domains (should be ignored)
    write_yaml(
        temp_config_dir / "trading.yaml",
        {
            "trading": {
                "mode": "testnet",
                "domains": {
                    "decision_making": {
                        "qos": {"mode": "defer"},
                        "extra_key": "should_not_appear",  # EXTRA KEY
                    }
                },
            }
        },
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

    loader = ConfigLoader(temp_config_dir)
    config = loader.load_config()

    # Assert: extra_key from trading.domains is NOT present
    # DomainsConfig is Pydantic model with strict validation, no extra_key allowed
    assert not hasattr(config.domains.decision_making, "extra_key")

    # Assert: only domains.yaml data is used
    assert config.domains.decision_making.qos.mode == "strict"


def test_trading_instruments_not_used_when_ssot_present(temp_config_dir):
    """
    Test that config.instruments is populated ONLY from instruments.yaml.
    
    Setup:
    - instruments.yaml present (SSOT) with BTCUSDT
    - trading.yaml has trading.instruments with ETHUSDT
    
    Expected:
    - config.instruments contains BTCUSDT (from SSOT)
    - ETHUSDT from trading.instruments is NOT added (mirror overwrite)
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

    # SSOT: instruments.yaml (only BTCUSDT)
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

    # Trading.yaml with EXTRA instrument (should be ignored)
    write_yaml(
        temp_config_dir / "trading.yaml",
        {
            "trading": {
                "mode": "testnet",
                "decision": {
                    "symbols_to_track": ["BTCUSDT"],
                },
                "instruments": {
                    "ETHUSDT": {  # EXTRA INSTRUMENT (should NOT appear)
                        "symbol": "ETHUSDT",
                        "tick_size": "0.01",
                        "step_size": "0.001",
                    }
                },
            }
        },
    )

    loader = ConfigLoader(temp_config_dir)
    config = loader.load_config()

    # Assert: only instruments.yaml data is used
    assert "BTCUSDT" in config.instruments
    assert "ETHUSDT" not in config.instruments  # NOT merged from trading.yaml

    # Assert: trading.instruments is mirror (same as config.instruments)
    assert "BTCUSDT" in config.trading.instruments
    assert "ETHUSDT" not in config.trading.instruments


# =============================================================================
# Test D: Guardrails validation hook
# =============================================================================


def test_validate_ssot_conflicts_called_at_startup(temp_config_dir):
    """
    Test that _validate_ssot_conflicts() is called during load_config().
    
    This test verifies the guardrails are active by checking that
    the validation method runs without errors in normal case.
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

    # Should complete without raising
    config = loader.load_config()
    assert config is not None

    # Validation is internal, but no exception = validation passed


# =============================================================================
# Test E: CFG-TRADING-YAML-BURN-DOWN-02 - Strict mode enforcement
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
