import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader


def _copy_config_dir(tmp_path: Path) -> Path:
    src = Path(__file__).resolve().parents[2] / "config" / "aurora"
    dst = tmp_path / "aurora"
    shutil.copytree(src, dst)
    return dst


def test_root_rejects_unknown_key(monkeypatch, tmp_path):
    cfg_dir = _copy_config_dir(tmp_path)
    system_yaml = cfg_dir / "system.yaml"
    original = system_yaml.read_text(encoding="utf-8")
    system_yaml.write_text(original + "\nlevrage: true\n", encoding="utf-8")

    loader = ConfigLoader(config_dir=cfg_dir)

    with pytest.raises(ValidationError):
        loader.load_config()


def test_canonical_config_loads_strict(tmp_path):
    cfg_dir = _copy_config_dir(tmp_path)
    loader = ConfigLoader(config_dir=cfg_dir)
    config = loader.load_config()

    assert config.trading_mode in {"testnet", "production", "live", "hybrid_live_data_testnet_exec", "backtest"}
    assert config.system_meta.system_config_version is not None
