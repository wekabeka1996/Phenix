from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader


def _copy_canonical_config_dir(tmp_path: Path) -> Path:
    src = Path(__file__).resolve().parents[2] / "config" / "aurora"
    dst = tmp_path / "aurora"
    shutil.copytree(src, dst)
    return dst


def test_loader_rejects_phantom_advanced_stale_cancel_regime_label(tmp_path: Path) -> None:
    """
    Full config-load regression: phantom labels in advanced_stale_cancel must fail closed
    during ConfigLoader.load_config(), not silently disable the feature at runtime.
    """
    cfg_dir = _copy_canonical_config_dir(tmp_path)
    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    adv = domains["execution_position"]["pending_entry_ttl"]["advanced_stale_cancel"]
    adv["may_cancel_regimes"]["BUY"] = ["BEAR_TREND"]
    domains_path.write_text(yaml.safe_dump(domains, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValidationError, match="Unknown regime label"):
        ConfigLoader(config_dir=cfg_dir).load_config()
