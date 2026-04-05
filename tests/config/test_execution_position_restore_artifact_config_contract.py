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


def test_production_config_exposes_execution_restore_artifact_contract() -> None:
    cfg = ConfigLoader().load_config()

    restore = cfg.domains.execution_position.restore_artifact
    assert restore.mode.value == "writer_only"
    assert str(restore.storage_path) == "ops/restore/execution_position_restore_envelope_v1.json"
    assert int(restore.flush_interval_ms) == 30000


def test_invalid_execution_restore_artifact_mode_is_rejected(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["execution_position"]["restore_artifact"]["mode"] = "WRITER_ONLY"
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert "restore_artifact" in str(exc_info.value)
    assert "WRITER_ONLY" in str(exc_info.value)


def test_empty_execution_restore_artifact_storage_path_is_rejected(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["execution_position"]["restore_artifact"]["storage_path"] = ""
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert "restore_artifact" in str(exc_info.value)
    assert "storage_path" in str(exc_info.value)


@pytest.mark.parametrize("bad_value", [0, -1])
def test_non_positive_execution_restore_artifact_flush_interval_is_rejected(
    tmp_path: Path,
    bad_value: int,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["execution_position"]["restore_artifact"]["flush_interval_ms"] = bad_value
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert "restore_artifact" in str(exc_info.value)
    assert "flush_interval_ms" in str(exc_info.value)
