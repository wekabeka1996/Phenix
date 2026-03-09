from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from apps.reference.config_loader import ConfigLoader


def _copy_canonical_config_dir(dst_config_dir: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    src = repo_root / "config" / "aurora"
    import shutil

    shutil.copytree(src, dst_config_dir)


def _set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "testnet_key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "testnet_secret")
    monkeypatch.setenv("BINANCE_FUTURES_API_KEY_LIVE", "live_key")
    monkeypatch.setenv("BINANCE_FUTURES_API_SECRET_LIVE", "live_secret")
    monkeypatch.setenv("BINANCE_FUTURES_BASE_URL_LIVE", "https://fapi.binance.com")


def test_md_amr_profile_yaml_fully_loaded_for_xrp_and_bnb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config" / "aurora"
    _copy_canonical_config_dir(config_dir)
    _set_required_env(monkeypatch)

    cfg = ConfigLoader(config_dir=config_dir).load_config()
    md_amr = cfg.strategies.md_amr
    assert md_amr is not None

    repo_root = Path(__file__).resolve().parents[2]
    md_yaml_path = repo_root / "config" / "aurora" / "strategies" / "md_amr.yaml"
    raw = yaml.safe_load(md_yaml_path.read_text(encoding="utf-8"))
    raw_md = raw["md_amr"]

    for symbol in ("XRPUSDT", "BNBUSDT"):
        asset = md_amr.assets[symbol]
        raw_asset = raw_md["assets"][symbol]
        assert asset.enabled is True
        assert asset.allowed_regimes == raw_asset["allowed_regimes"]
        assert asset.exit is not None
        assert asset.exit.sl_pct == raw_asset["exit"]["sl_pct"]
        assert asset.exit.tp_rr == raw_asset["exit"]["tp_rr"]
        assert asset.exit.regime_tpsl is not None
        assert asset.exit.regime_tpsl.sl_mult == raw_asset["exit"]["regime_tpsl"]["sl_mult"]
        assert asset.exit.regime_tpsl.tp_mult == raw_asset["exit"]["regime_tpsl"]["tp_mult"]


def test_md_amr_launch_contract_rejects_missing_assigned_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config" / "aurora"
    _copy_canonical_config_dir(config_dir)
    _set_required_env(monkeypatch)

    md_yaml_path = config_dir / "strategies" / "md_amr.yaml"
    raw = yaml.safe_load(md_yaml_path.read_text(encoding="utf-8"))
    raw["md_amr"]["assets"].pop("BNBUSDT", None)
    md_yaml_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="BNBUSDT"):
        ConfigLoader(config_dir=config_dir).load_config()


def test_md_amr_launch_contract_rejects_empty_allowed_regimes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config" / "aurora"
    _copy_canonical_config_dir(config_dir)
    _set_required_env(monkeypatch)

    md_yaml_path = config_dir / "strategies" / "md_amr.yaml"
    raw = yaml.safe_load(md_yaml_path.read_text(encoding="utf-8"))
    raw["md_amr"]["assets"]["XRPUSDT"]["allowed_regimes"] = []
    md_yaml_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="allowed_regimes"):
        ConfigLoader(config_dir=config_dir).load_config()
