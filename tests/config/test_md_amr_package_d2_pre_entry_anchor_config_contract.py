import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader


def _copy_config_to_tmp(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(Path("config/aurora"), cfg_dir)
    return cfg_dir


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_md_amr_entry_anchor_persistence_contract_is_exposed_in_production_config() -> None:
    cfg = ConfigLoader().load_config()

    persistence = cfg.strategies.md_amr.entry_anchor_persistence
    assert str(
        persistence.storage_path) == "ops/restore/md_amr_entry_anchor_state_v1.json"


def test_md_amr_entry_anchor_persistence_rejects_empty_storage_path(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    md_amr_path = cfg_dir / "strategies" / "md_amr.yaml"
    md_amr_cfg = yaml.safe_load(md_amr_path.read_text(encoding="utf-8"))
    md_amr_cfg["md_amr"]["entry_anchor_persistence"]["storage_path"] = ""
    _write_yaml(md_amr_path, md_amr_cfg)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert "entry_anchor_persistence" in str(exc_info.value)
    assert "storage_path" in str(exc_info.value)


def test_md_amr_entry_anchor_persistence_forbids_unknown_fields(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    md_amr_path = cfg_dir / "strategies" / "md_amr.yaml"
    md_amr_cfg = yaml.safe_load(md_amr_path.read_text(encoding="utf-8"))
    md_amr_cfg["md_amr"]["entry_anchor_persistence"]["unexpected"] = True
    _write_yaml(md_amr_path, md_amr_cfg)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert "entry_anchor_persistence" in str(exc_info.value)
    assert "unexpected" in str(exc_info.value)
