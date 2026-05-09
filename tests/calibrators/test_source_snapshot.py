import hashlib
import json
from pathlib import Path

import pytest

from calibrators.datasets.builders.source_snapshot import (
    SnapshotSourceSpec,
    load_source_snapshot_manifest,
    sha256_file,
    snapshot_sources,
)


def test_snapshot_sources_copies_file_and_records_metadata(tmp_path: Path) -> None:
    source = tmp_path / "logs" / "order_log_v1.jsonl"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('{"rid":"rid_1"}\n', encoding="utf-8")

    out_dir = tmp_path / "artifacts" / "dataset"
    manifest = snapshot_sources(
        [
            SnapshotSourceSpec(
                role="order_log",
                source_path=source,
                source_kind="current_workspace_authority",
                required=True,
            )
        ],
        out_dir,
        "realized_outcome_builder",
        repo_root=tmp_path,
    )

    entry = manifest["sources"][0]
    copied = out_dir / entry["copied_to"]
    assert copied.exists()
    assert copied.read_text(
        encoding="utf-8") == source.read_text(encoding="utf-8")
    assert entry["role"] == "order_log"
    assert entry["source_kind"] == "current_workspace_authority"
    assert entry["size_bytes"] == source.stat().st_size
    assert entry["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert sha256_file(copied) == entry["sha256"]
    assert entry["copied_to"] == "source_snapshot/order_log_v1.jsonl"

    loaded = load_source_snapshot_manifest(
        out_dir / "source_snapshot" / "source_snapshot_manifest.json"
    )
    assert loaded["builder"] == "realized_outcome_builder"
    assert loaded["missing_required_sources"] == []


def test_missing_required_source_is_recorded_in_non_strict_mode(tmp_path: Path) -> None:
    out_dir = tmp_path / "artifacts" / "dataset"
    missing_source = tmp_path / "logs" / "order_log_v1.jsonl"

    manifest = snapshot_sources(
        [
            SnapshotSourceSpec(
                role="order_log",
                source_path=missing_source,
                source_kind="current_workspace_authority",
                required=True,
            )
        ],
        out_dir,
        "realized_outcome_builder",
        strict=False,
        repo_root=tmp_path,
    )

    assert manifest["missing_required_sources"] == ["order_log"]
    assert manifest["warnings"] == [
        f"MISSING_REQUIRED_SOURCE:order_log:{missing_source.as_posix()}"
    ]
    entry = manifest["sources"][0]
    assert entry["exists"] is False
    assert entry["copied_to"] is None


def test_missing_required_source_fails_in_strict_mode(tmp_path: Path) -> None:
    out_dir = tmp_path / "artifacts" / "dataset"
    missing_source = tmp_path / "logs" / "decision_ledger_v1.jsonl"

    with pytest.raises(FileNotFoundError) as exc_info:
        snapshot_sources(
            [
                SnapshotSourceSpec(
                    role="decision_ledger",
                    source_path=missing_source,
                    source_kind="current_workspace_authority",
                    required=True,
                )
            ],
            out_dir,
            "realized_outcome_builder",
            strict=True,
            repo_root=tmp_path,
        )

    assert "MISSING_REQUIRED_SOURCE:decision_ledger" in str(exc_info.value)
