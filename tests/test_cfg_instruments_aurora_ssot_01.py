from __future__ import annotations

from pathlib import Path

import pytest

from apps.reference.config_loader import ConfigLoader


def _write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _minimal_domains_yaml() -> str:
    # DomainsConfig is strict, but missing domain blocks are defaulted.
    # Non-empty dict is required by loader SSOT logic.
    return """\
decision_making: {}
"""


def test_instruments_yaml_to_config_instruments(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "config" / "aurora"

    _write_yaml(cfg_dir / "system.yaml", "logging: {level: INFO}\n")
    _write_yaml(
        cfg_dir / "trading.yaml",
        """\
trading:
  symbols_to_track: ["BTCUSDT"]
""",
    )
    _write_yaml(cfg_dir / "regime.yaml", "{}\n")
    _write_yaml(cfg_dir / "domains.yaml", _minimal_domains_yaml())

    _write_yaml(
        cfg_dir / "instruments.yaml",
        """\
instruments:
  BTCUSDT:
    symbol: BTCUSDT
    tick_size: "0.01"
    step_size: "0.001"
""",
    )

    cfg = ConfigLoader(config_dir=cfg_dir).load_config()

    assert "BTCUSDT" in cfg.instruments
    assert cfg.instruments["BTCUSDT"].tick_size == 0.01
    assert cfg.instruments["BTCUSDT"].step_size == 0.001


def test_instruments_yaml_overrides_trading_instruments(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "config" / "aurora"

    _write_yaml(cfg_dir / "system.yaml", "logging: {level: INFO}\n")
    _write_yaml(
        cfg_dir / "trading.yaml",
        """\
trading:
  symbols_to_track: ["BTCUSDT"]
  instruments:
    BTCUSDT:
      tick_size: "9"
      step_size: "9"
""",
    )
    _write_yaml(cfg_dir / "regime.yaml", "{}\n")
    _write_yaml(cfg_dir / "domains.yaml", _minimal_domains_yaml())

    _write_yaml(
        cfg_dir / "instruments.yaml",
        """\
BTCUSDT:
  symbol: BTCUSDT
  tick_size: "0.01"
  step_size: "0.001"
""",
    )

    cfg = ConfigLoader(config_dir=cfg_dir).load_config()

    assert cfg.instruments["BTCUSDT"].tick_size == 0.01
    assert cfg.instruments["BTCUSDT"].step_size == 0.001

    # Deprecated mirror for legacy runtime
    assert "BTCUSDT" in cfg.trading.instruments
    assert float(cfg.trading.instruments["BTCUSDT"].tick_size) == 0.01
    assert float(cfg.trading.instruments["BTCUSDT"].step_size) == 0.001


def test_missing_tick_or_step_fails_fast(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "config" / "aurora"

    _write_yaml(cfg_dir / "system.yaml", "logging: {level: INFO}\n")
    _write_yaml(
        cfg_dir / "trading.yaml",
        """\
trading:
  symbols_to_track: ["XRPUSDT"]
""",
    )
    _write_yaml(cfg_dir / "regime.yaml", "{}\n")
    _write_yaml(cfg_dir / "domains.yaml", _minimal_domains_yaml())

    _write_yaml(
        cfg_dir / "instruments.yaml",
        """\
XRPUSDT:
  symbol: XRPUSDT
  tick_size: "0.0001"
""",
    )

    with pytest.raises(ValueError) as e:
        ConfigLoader(config_dir=cfg_dir).load_config()

    msg = str(e.value)
    assert "Missing instruments precision" in msg
    assert "XRPUSDT" in msg
    assert "step_size" in msg
