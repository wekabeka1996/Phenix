import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from apps.reference.config_loader import ConfigLoader


def _copy_canonical_config_dir(tmp_path: Path) -> Path:
    src = Path(__file__).resolve().parents[2] / "config" / "aurora"
    dst = tmp_path / "aurora"
    shutil.copytree(src, dst)
    return dst


def _delete_dotted_key(yaml_path: Path, dotted_path: str) -> None:
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return

    keys = dotted_path.split(".")
    cur = data
    for key in keys[:-1]:
        if not isinstance(cur, dict) or key not in cur:
            return
        cur = cur[key]

    if isinstance(cur, dict):
        cur.pop(keys[-1], None)

    yaml_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _get_dotted_key(yaml_path: Path, dotted_path: str):
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    keys = dotted_path.split(".")
    cur = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


@pytest.mark.timeout(30)
def test_optional_required_null_autofill_enables_loader(tmp_path):
    cfg_dir = _copy_canonical_config_dir(tmp_path)

    # Remove a few Optional-but-required keys (strict schema expects explicit nulls).
    aurora_yaml = cfg_dir / "strategies" / "aurora.yaml"
    _delete_dotted_key(aurora_yaml, "aurora.decision.testnet")
    _delete_dotted_key(aurora_yaml, "aurora.decision.production")

    trading_yaml = cfg_dir / "trading.yaml"
    _delete_dotted_key(trading_yaml, "trading.execution.manage.emergency")

    # Sanity: loader should fail before autofill.
    loader = ConfigLoader(config_dir=cfg_dir)
    with pytest.raises(Exception):
        loader.load_config()

    # Run autofill against temp config directory.
    plan_report = tmp_path / "plan.md"
    applied_report = tmp_path / "applied.md"

    env = dict(os.environ)
    # Keep strict config on (default), but do not let local STRICT override leak.
    env.pop("STRICT_CONFIG_CONFLICTS", None)

    subprocess.check_call(
        [
            "venv/bin/python",
            "tools/autofill_config_defaults_into_yaml.py",
            "--apply",
            "--autofill-optional-nulls",
            "--config-dir",
            str(cfg_dir),
            "--plan-report",
            str(plan_report),
            "--applied-report",
            str(applied_report),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
    )

    # Verify keys are now explicitly present (null/empty collection).
    assert _get_dotted_key(aurora_yaml, "aurora.decision.testnet") is None
    assert _get_dotted_key(aurora_yaml, "aurora.decision.production") is None
    assert _get_dotted_key(trading_yaml, "trading.execution.manage.emergency") is None

    # Loader should now succeed.
    loader2 = ConfigLoader(config_dir=cfg_dir)
    config = loader2.load_config()
    assert config is not None
