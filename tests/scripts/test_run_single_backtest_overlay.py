from pathlib import Path

import pytest

from scripts.diagnostics.run_single_backtest import _load_overlay_yaml


def test_load_overlay_yaml_accepts_wrapped_overlay(tmp_path: Path):
    overlay_path = tmp_path / "wrapped.yaml"
    overlay_path.write_text(
        "meta:\n"
        "  candidate: march_v1\n"
        "overlay:\n"
        "  strategies:\n"
        "    aurora:\n"
        "      assets:\n"
        "        ETHUSDT:\n"
        "          allowed_regimes:\n"
        "            - FLAT_LOW\n",
        encoding="utf-8",
    )

    overlay = _load_overlay_yaml(str(overlay_path))

    assert overlay["strategies"]["aurora"]["assets"]["ETHUSDT"]["allowed_regimes"] == ["FLAT_LOW"]


def test_load_overlay_yaml_accepts_raw_mapping(tmp_path: Path):
    overlay_path = tmp_path / "raw.yaml"
    overlay_path.write_text(
        "strategies:\n"
        "  aurora:\n"
        "    assets:\n"
        "      ETHUSDT:\n"
        "        signal_threshold:\n"
        "          value: 0.01\n",
        encoding="utf-8",
    )

    overlay = _load_overlay_yaml(str(overlay_path))

    assert overlay["strategies"]["aurora"]["assets"]["ETHUSDT"]["signal_threshold"]["value"] == 0.01


def test_load_overlay_yaml_rejects_missing_file():
    with pytest.raises(FileNotFoundError):
        _load_overlay_yaml("does-not-exist.yaml")