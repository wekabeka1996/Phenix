"""
CFG-INSTRUMENTS-STEP-03-EXECUTION-PRECISION: execution_position precision via config.instruments SSOT.

Tests that execution_position domains (fsm_open, fsm_manage) read tick_size/step_size
exclusively from config.instruments (canonical SSOT), not from legacy trading.instruments.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, PropertyMock

import pytest

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM


def _write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _minimal_config(symbol: str = "XRPUSDT") -> str:
    return f"""\
trading:
  symbols_to_track: ["{symbol}"]
  decision:
    signal_threshold: 0.1
"""


def _minimal_domains_yaml() -> str:
    return """\
decision_making: {}
execution_position:
  fsm_open:
    idempotency_window_sec: 60
"""


def test_execution_precision_from_canonical_instruments(tmp_path: Path) -> None:
    """Test A: execution_position reads precision from canonical config.instruments."""
    cfg_dir = tmp_path / "config" / "aurora"
    
    _write_yaml(cfg_dir / "system.yaml", "logging: {level: INFO}\n")
    _write_yaml(cfg_dir / "trading.yaml", _minimal_config("XRPUSDT"))
    _write_yaml(cfg_dir / "regime.yaml", "{}\n")
    _write_yaml(cfg_dir / "domains.yaml", _minimal_domains_yaml())
    
    # Canonical instruments.yaml
    _write_yaml(
        cfg_dir / "instruments.yaml",
        """\
XRPUSDT:
  symbol: XRPUSDT
  tick_size: "0.0001"
  step_size: "0.1"
  min_notional: "10"
""",
    )
    
    config = ConfigLoader(config_dir=cfg_dir).load_config()
    
    # Create OpenFlowFSM with proper parameters
    # OpenFlowFSM.__init__(cooldown_sec, guard_enabled, config, metrics_collector)
    mock_metrics = MagicMock()
    fsm_open = OpenFlowFSM(
        cooldown_sec=1.0,
        guard_enabled=True,
        config=config,
        metrics_collector=mock_metrics
    )
    
    # Call _get_instrument_specs (canonical method)
    specs = fsm_open._get_instrument_specs("XRPUSDT")
    
    # Assert: values from instruments.yaml
    assert specs["tick_size"] == Decimal("0.0001")
    assert specs["step_size"] == Decimal("0.1")
    assert specs["min_notional"] == Decimal("10")


def test_execution_precision_instruments_yaml_overrides_legacy(tmp_path: Path) -> None:
    """Test B: instruments.yaml overrides any legacy trading.instruments values."""
    cfg_dir = tmp_path / "config" / "aurora"
    
    _write_yaml(cfg_dir / "system.yaml", "logging: {level: INFO}\n")
    
    # Legacy trading.yaml with different precision (will be mirrored but ignored)
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
      min_notional: "999"
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
  min_notional: "10"
""",
    )
    
    config = ConfigLoader(config_dir=cfg_dir).load_config()
    
    # Create OpenFlowFSM with proper parameters
    mock_metrics = MagicMock()
    fsm_open = OpenFlowFSM(
        cooldown_sec=1.0,
        guard_enabled=True,
        config=config,
        metrics_collector=mock_metrics
    )
    
    # Call _get_instrument_specs
    specs = fsm_open._get_instrument_specs("XRPUSDT")
    
    # Assert: canonical instruments.yaml wins (NOT 9.0 from trading.yaml)
    assert specs["tick_size"] == Decimal("0.0001")
    assert specs["step_size"] == Decimal("0.1")
    assert specs["min_notional"] == Decimal("10")


def test_execution_no_legacy_trading_instruments_access(tmp_path: Path) -> None:
    """Test C: execution doesn't access trading.instruments (contract guard)."""
    cfg_dir = tmp_path / "config" / "aurora"
    
    _write_yaml(cfg_dir / "system.yaml", "logging: {level: INFO}\n")
    _write_yaml(cfg_dir / "trading.yaml", _minimal_config("XRPUSDT"))
    _write_yaml(cfg_dir / "regime.yaml", "{}\n")
    _write_yaml(cfg_dir / "domains.yaml", _minimal_domains_yaml())
    
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
    
    # GUARD: Make trading.instruments raise exception on access
    class GuardedInstruments:
        def __getitem__(self, key):
            raise AssertionError(f"❌ Legacy access to trading.instruments[{key}]")
        
        def get(self, key, default=None):
            raise AssertionError(f"❌ Legacy access to trading.instruments.get({key})")
        
        def __bool__(self):
            # Allow truthiness check (if instruments:)
            return True
    
    # Monkeypatch to guard legacy access
    original_instruments = config.trading.instruments
    config.trading.instruments = GuardedInstruments()
    
    try:
        # Create OpenFlowFSM and call precision method with proper parameters
        mock_metrics = MagicMock()
        fsm_open = OpenFlowFSM(
            cooldown_sec=1.0,
            guard_enabled=True,
            config=config,
            metrics_collector=mock_metrics
        )
        
        # This should NOT raise AssertionError (no legacy access)
        specs = fsm_open._get_instrument_specs("XRPUSDT")
        
        # Assert: execution successfully used config.instruments
        assert specs["tick_size"] == Decimal("0.0001")
        assert specs["step_size"] == Decimal("0.1")
    finally:
        # Restore original
        config.trading.instruments = original_instruments


def test_execution_precision_missing_symbol_uses_defaults(tmp_path: Path) -> None:
    """Test D: Missing symbol → use safe defaults (не падає, бо execution має fallback)."""
    cfg_dir = tmp_path / "config" / "aurora"
    
    _write_yaml(cfg_dir / "system.yaml", "logging: {level: INFO}\n")
    _write_yaml(cfg_dir / "trading.yaml", _minimal_config("SOLUSDT"))
    _write_yaml(cfg_dir / "regime.yaml", "{}\n")
    _write_yaml(cfg_dir / "domains.yaml", _minimal_domains_yaml())
    
    # instruments.yaml має SOLUSDT, запитуємо BTCUSDT (missing)
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
    
    mock_metrics = MagicMock()
    fsm_open = OpenFlowFSM(
        cooldown_sec=1.0,
        guard_enabled=True,
        config=config,
        metrics_collector=mock_metrics
    )
    
    # Request specs for missing symbol
    specs = fsm_open._get_instrument_specs("BTCUSDT")
    
    # Assert: returns defaults (execution є більш tolerant, ніж DM)
    # Це нормально для execution, бо він може мати fallback
    assert "tick_size" in specs
    assert "step_size" in specs
    assert specs["tick_size"] > 0
    assert specs["step_size"] > 0
