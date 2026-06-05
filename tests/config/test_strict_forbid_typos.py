import os
from pathlib import Path
import shutil

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader


def _write_yaml(path: Path, obj) -> None:  # type: ignore[no-untyped-def]
    path.write_text(yaml.safe_dump(obj, sort_keys=False), encoding="utf-8")


def test_trading_config_typos_fail_validation(tmp_path: Path) -> None:
    config_dir = tmp_path / "config" / "aurora"
    repo_root = Path(__file__).resolve().parents[2]
    shutil.copytree(repo_root / "config" / "aurora", config_dir)

    trading_path = config_dir / "trading.yaml"
    payload = yaml.safe_load(trading_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    trading = payload.get("trading")
    assert isinstance(trading, dict)

    # Typo at trading-level key: "levrage" (should be rejected by extra='forbid')
    trading["levrage"] = 10
    trading_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    os.environ.pop("STRICT_CONFIG_CONFLICTS", None)
    loader = ConfigLoader(config_dir=config_dir)
    with pytest.raises(ValidationError):
        loader.load_config()
