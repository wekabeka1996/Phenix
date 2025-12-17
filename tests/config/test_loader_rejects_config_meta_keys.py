import shutil
from pathlib import Path

import pytest

from apps.reference.config_loader import ConfigLoader
from apps.reference.config_contract import ConfigContractError


def _copy_config_dir(tmp_path: Path) -> Path:
    src = Path(__file__).resolve().parents[2] / "config" / "aurora"
    dst = tmp_path / "aurora"
    shutil.copytree(src, dst)
    return dst


def test_loader_rejects_config_prefix_keys(tmp_path):
    cfg_dir = _copy_config_dir(tmp_path)
    system_yaml = cfg_dir / "system.yaml"
    original = system_yaml.read_text(encoding="utf-8")
    system_yaml.write_text(original + "\n_config_noise: true\n", encoding="utf-8")

    loader = ConfigLoader(config_dir=cfg_dir)

    with pytest.raises(ConfigContractError):
        loader.load_config()
