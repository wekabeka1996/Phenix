from __future__ import annotations

import json
from pathlib import Path

from tools.analysis import config_snapshot as mod


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_freeze_config_snapshot_copies_present_configs_and_tracks_missing(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "config" / "aurora" / "domains.yaml",
        "decision_making:\n  low_vol_cost_floor_gate:\n    enabled: true\n",
    )
    _write_text(
        tmp_path / "config" / "aurora" / "trading.yaml",
        "trading:\n  mode: testnet\n",
    )

    bundle_root = tmp_path / "logs" / "frozen" / "bundle_a"
    result = mod.freeze_config_snapshot(
        tmp_path,
        bundle_root,
        git_state={
            "branch": "main",
            "commit_sha": "abc123",
            "status_short": [" M config/aurora/domains.yaml"],
            "dirty_worktree": True,
            "dirty_config_paths": ["M config/aurora/domains.yaml"],
            "capture_status": "OK",
            "capture_error": None,
        },
    )

    manifest = result["manifest"]
    manifest_path = bundle_root / mod.CONFIG_SNAPSHOT_MANIFEST_NAME

    assert manifest_path.is_file()
    assert result["snapshot_root"] == "logs/frozen/bundle_a/config_snapshot"
    assert (bundle_root / "config_snapshot" / "config" /
            "aurora" / "domains.yaml").is_file()
    assert manifest["summary"]["required_present"] == 2
    assert manifest["summary"]["all_required_present"] is False
    assert "config/aurora/strategies.yaml" in manifest["summary"]["missing_configs"]
    assert manifest["git"]["commit_sha"] == "abc123"


def test_freeze_config_snapshot_records_parse_errors_without_dropping_file(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "config" / "aurora" / "domains.yaml",
        "decision_making: [unterminated\n",
    )

    bundle_root = tmp_path / "logs" / "frozen" / "bundle_b"
    result = mod.freeze_config_snapshot(tmp_path, bundle_root)
    manifest = json.loads(
        (bundle_root / mod.CONFIG_SNAPSHOT_MANIFEST_NAME).read_text(encoding="utf-8")
    )

    domains_entry = next(
        entry for entry in manifest["files"] if entry["config"] == "config/aurora/domains.yaml"
    )
    assert domains_entry["exists"] is True
    assert domains_entry["parse_status"] == "PARSE_ERROR"
    assert domains_entry["parse_error"]
    assert result["manifest"]["summary"]["parse_status_counts"]["PARSE_ERROR"] == 1
