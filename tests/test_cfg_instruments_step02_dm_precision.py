"""
CFG-INSTRUMENTS-STEP-02-DM-PRECISION: DecisionMaking precision via config.instruments SSOT.

Tests that DecisionMaking reads tick_size/step_size exclusively from config.instruments
(canonical SSOT from instruments.yaml), not from legacy trading.instruments.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.decision_making import DecisionMaking


def _write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _minimal_config(symbol: str = "XRPUSDT") -> str:
    """Minimal config YAML with one symbol."""
    return f"""\
trading:
  symbols_to_track: ["{symbol}"]
  decision:
    signal_threshold: 0.1
"""


def _minimal_domains_yaml() -> str:
    return "decision_making: {}\n"


def test_dm_precision_from_canonical_instruments(tmp_path: Path) -> None:
    """Test A: DecisionMaking reads precision from canonical config.instruments."""
    cfg_dir = tmp_path / "config" / "aurora"
    
    _write_yaml(cfg_dir / "system.yaml", "logging: {level: INFO}\n")
    _write_yaml(cfg_dir / "trading.yaml", _minimal_config("XRPUSDT"))
    _write_yaml(cfg_dir / "regime.yaml", "{}\n")
    _write_yaml(cfg_dir / "domains.yaml", _minimal_domains_yaml())
    
    # Canonical instruments.yaml with precision
    _write_yaml(
        cfg_dir / "instruments.yaml",
        """\
XRPUSDT:
  symbol: XRPUSDT
  tick_size: "0.0001"
  step_size: "0.1"
""",
    )
    
    config = ConfigLoader(config_dir=cfg_dir).load_config()
    
    # Create DecisionMaking with mocked FSM
    mock_fsm = MagicMock()
    dm = DecisionMaking(fsm=mock_fsm, config=config)
    
    # Call _get_precision (canonical method)
    tick_size, step_size = dm._get_precision("XRPUSDT")
    
    # Assert: values from instruments.yaml
    assert tick_size == 0.0001
    assert step_size == 0.1


def test_dm_precision_instruments_yaml_overrides_legacy(tmp_path: Path) -> None:
    """Test B: instruments.yaml overrides any legacy trading.instruments values."""
    cfg_dir = tmp_path / "config" / "aurora"
    
    _write_yaml(cfg_dir / "system.yaml", "logging: {level: INFO}\n")
    
    # Legacy trading.yaml with different precision
    _write_yaml(
        cfg_dir / "trading.yaml",
        """\
trading:
  symbols_to_track: ["XRPUSDT"]
  decision:
    signal_threshold: 0.1
  instruments:
    XRPUSDT:
      symbol: XRPUSDT
      tick_size: "9.0"
      step_size: "9.0"
""",
    )
    _write_yaml(cfg_dir / "regime.yaml", "{}\n")
    _write_yaml(cfg_dir / "domains.yaml", _minimal_domains_yaml())
    
    # Canonical instruments.yaml with correct precision
    _write_yaml(
        cfg_dir / "instruments.yaml",
        """\
XRPUSDT:
  symbol: XRPUSDT
  tick_size: "0.0001"
  step_size: "0.1"
""",
    )
    
    config = ConfigLoader(config_dir=cfg_dir).load_config()
    
    # Create DecisionMaking
    mock_fsm = MagicMock()
    dm = DecisionMaking(fsm=mock_fsm, config=config)
    
    # Call _get_precision
    tick_size, step_size = dm._get_precision("XRPUSDT")
    
    # Assert: canonical instruments.yaml wins (NOT 9.0 from trading.yaml)
    assert tick_size == 0.0001
    assert step_size == 0.1


def test_dm_precision_missing_symbol_fails_closed(tmp_path: Path) -> None:
    """Test C: Missing symbol in config.instruments → fail-closed (ValueError)."""
    cfg_dir = tmp_path / "config" / "aurora"
    
    _write_yaml(cfg_dir / "system.yaml", "logging: {level: INFO}\n")
    _write_yaml(cfg_dir / "trading.yaml", _minimal_config("SOLUSDT"))
    _write_yaml(cfg_dir / "regime.yaml", "{}\n")
    _write_yaml(cfg_dir / "domains.yaml", _minimal_domains_yaml())
    
    # instruments.yaml has SOLUSDT, but we'll request BTCUSDT (missing)
    _write_yaml(
        cfg_dir / "instruments.yaml",
        """\
SOLUSDT:
  symbol: SOLUSDT
  tick_size: "0.01"
  step_size: "0.01"
""",
    )
    
    config = ConfigLoader(config_dir=cfg_dir).load_config()
    
    mock_fsm = MagicMock()
    dm = DecisionMaking(fsm=mock_fsm, config=config)
    
    # Request precision for symbol NOT in instruments
    with pytest.raises(ValueError) as exc_info:
        dm._get_precision("BTCUSDT")
    
    assert "Missing instrument config" in str(exc_info.value)
    assert "BTCUSDT" in str(exc_info.value)


def test_dm_precision_missing_fields_fails_at_loader(tmp_path: Path) -> None:
    """Test D: Symbol present but missing tick/step → loader fail-fast (not DM)."""
    cfg_dir = tmp_path / "config" / "aurora"
    
    _write_yaml(cfg_dir / "system.yaml", "logging: {level: INFO}\n")
    _write_yaml(cfg_dir / "trading.yaml", _minimal_config("XRPUSDT"))
    _write_yaml(cfg_dir / "regime.yaml", "{}\n")
    _write_yaml(cfg_dir / "domains.yaml", _minimal_domains_yaml())
    
    # instruments.yaml missing step_size
    _write_yaml(
        cfg_dir / "instruments.yaml",
        """\
XRPUSDT:
  symbol: XRPUSDT
  tick_size: "0.0001"
""",
    )
    
    # Loader should fail-fast (CFG-INSTRUMENTS-AURORA-SSOT-01)
    with pytest.raises(ValueError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()
    
    assert "Missing instruments precision" in str(exc_info.value)
    assert "XRPUSDT" in str(exc_info.value)
    assert "step_size" in str(exc_info.value)
