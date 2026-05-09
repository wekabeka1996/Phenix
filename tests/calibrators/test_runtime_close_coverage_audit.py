import json
from pathlib import Path

from calibrators.datasets.audit_runtime_close_coverage import (
    analyze_runtime_close_coverage,
    write_runtime_close_coverage_artifacts,
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_runtime_close_coverage_classifies_rejected_and_source_gap(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
        [
            {
                "decision_id": "dec_reject",
                "rid": "rid_reject",
                "symbol": "BTCUSDT",
                "terminal_status": "REJECTED_UPSTREAM",
                "apply_result": "SHADOW_RECORDED",
                "causal_state_snapshot": {
                    "decision_basis_ts_ms": 1714568399000,
                    "candidate_intent_summary": {
                        "strategy_id": "aurora",
                        "side": "BUY",
                        "proposed_action": "OPEN_LONG",
                    },
                },
            },
            {
                "decision_id": "dec_gap",
                "rid": "rid_gap",
                "symbol": "ETHUSDT",
                "terminal_status": "INVALID_FOR_DATASET",
                "lifecycle_id": "lc_gap",
                "trade_id": "trade_gap",
                "apply_result": "SHADOW_RECORDED",
                "causal_state_snapshot": {
                    "decision_basis_ts_ms": 1714568400000,
                    "candidate_intent_summary": {
                        "strategy_id": "aurora",
                        "side": "SELL",
                        "proposed_action": "OPEN_SHORT",
                    },
                },
            },
        ],
    )
    _write_jsonl(
        tmp_path / "artifacts" / "calibration_datasets" /
        "_smoke_03g_realized_outcome" / "rejected_rows.jsonl",
        [
            {"decision_id": "dec_reject", "rid": "rid_reject",
                "reason": "NO_MATCHING_CLOSE_EVENT"},
            {"decision_id": "dec_gap", "rid": "rid_gap",
                "reason": "NO_MATCHING_CLOSE_EVENT"},
        ],
    )
    _write_jsonl(
        tmp_path / "reports" / "forensics" / "snapshot" / "order_log_v1.jsonl",
        [
            {
                "rid": "rid_gap",
                "event_type": "POSITION_CLOSED",
                "lifecycle_id": "rid_gap",
                "trade_id": "trade_gap",
                "symbol": "ETHUSDT",
                "realized_pnl_net": 1.5,
                "fees": 0.1,
                "timestamp": 1714568600000,
            }
        ],
    )

    result = analyze_runtime_close_coverage(tmp_path)

    rows = {row["rid"]: row for row in result["unmatched_classification"]["rows"]}
    assert rows["rid_reject"]["classification"] == "NOT_EXECUTED_OR_REJECTED"
    assert rows["rid_gap"]["classification"] == "SOURCE_LOGGING_GAP"
    assert result["source_inputs"]["authority_order_log_exists"] is False


def test_runtime_close_coverage_classifies_lifecycle_bridge_and_writes_outputs(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
        [
            {
                "decision_id": "dec_bridge",
                "rid": "rid_bridge",
                "symbol": "XRPUSDT",
                "terminal_status": "INVALID_FOR_DATASET",
                "lifecycle_id": "lc_bridge",
                "trade_id": "trade_bridge",
                "apply_result": "SHADOW_RECORDED",
                "causal_state_snapshot": {
                    "decision_basis_ts_ms": 1714568500000,
                    "candidate_intent_summary": {
                        "strategy_id": "aurora",
                        "side": "SELL",
                        "proposed_action": "OPEN_SHORT",
                    },
                },
            }
        ],
    )
    _write_jsonl(
        tmp_path / "artifacts" / "calibration_datasets" /
        "_smoke_03g_realized_outcome" / "rejected_rows.jsonl",
        [{"decision_id": "dec_bridge", "rid": "rid_bridge",
            "reason": "NO_MATCHING_CLOSE_EVENT"}],
    )
    _write_jsonl(
        tmp_path / "logs" / "trade_lifecycle.jsonl",
        [
            {
                "event_type": "POSITION_CLOSED",
                "lifecycle_id": "lc_bridge",
                "rid": "other_runtime_rid",
                "trade_id": "trade_bridge",
                "status": "CLOSED",
                "close_ts_ms": 1714568600000,
            }
        ],
    )

    result = analyze_runtime_close_coverage(tmp_path)
    row = result["unmatched_classification"]["rows"][0]
    assert row["classification"] == "LIFECYCLE_ID_BRIDGE_AVAILABLE_BUT_UNUSED"

    out_dir = tmp_path / "calibrators" / "datasets" / "runtime_close_coverage"
    write_runtime_close_coverage_artifacts(result, out_dir)

    assert (out_dir / "unmatched_decision_ledger.csv").exists()
    assert (out_dir / "unmatched_decision_ledger.json").exists()
    assert (out_dir / "UNMATCHED_DECISION_LEDGER.md").exists()
    assert (out_dir / "order_log_event_taxonomy.json").exists()
    assert (out_dir / "ORDER_LOG_EVENT_TAXONOMY.md").exists()
    assert (out_dir / "lifecycle_bridge_audit.json").exists()
    assert (out_dir / "LIFECYCLE_BRIDGE_AUDIT.md").exists()
    assert (out_dir / "unmatched_classification.json").exists()
    assert (out_dir / "UNMATCHED_CLASSIFICATION.md").exists()
    assert "MISSING_SOURCE_SNAPSHOT" in (
        out_dir / "ORDER_LOG_EVENT_TAXONOMY.md").read_text(encoding="utf-8")


def test_runtime_close_coverage_prefers_artifact_snapshot_over_missing_live_authority(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts" / \
        "calibration_datasets" / "_smoke_03j_realized_outcome"
    snapshot_dir = artifact_dir / "source_snapshot"

    _write_jsonl(
        snapshot_dir / "decision_ledger_v1.jsonl",
        [
            {
                "decision_id": "dec_snapshot",
                "rid": "rid_snapshot",
                "symbol": "BTCUSDT",
                "terminal_status": "EXECUTED_AND_CLOSED",
                "apply_result": "SHADOW_RECORDED",
                "causal_state_snapshot": {
                    "decision_basis_ts_ms": 1714568399000,
                    "candidate_intent_summary": {
                        "strategy_id": "aurora",
                        "side": "BUY",
                        "proposed_action": "OPEN_LONG",
                    },
                },
            }
        ],
    )
    _write_jsonl(
        snapshot_dir / "order_log_v1.jsonl",
        [
            {
                "rid": "rid_snapshot",
                "event_type": "POSITION_CLOSED",
                "lifecycle_id": "lc_snapshot",
                "trade_id": "trade_snapshot",
                "symbol": "BTCUSDT",
                "realized_pnl_net": 2.5,
                "fees": 0.2,
                "timestamp": 1714568600000,
            }
        ],
    )
    _write_jsonl(
        artifact_dir / "rejected_rows.jsonl",
        [
            {
                "decision_id": "dec_snapshot",
                "rid": "rid_snapshot",
                "reason": "NO_MATCHING_CLOSE_EVENT",
            }
        ],
    )
    (snapshot_dir / "source_snapshot_manifest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-05-07T00:00:00+00:00",
                "builder": "realized_outcome_builder",
                "repo_root": tmp_path.as_posix(),
                "sources": [
                    {
                        "role": "decision_ledger",
                        "source_path": (tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl").as_posix(),
                        "source_kind": "current_workspace_authority",
                        "exists": True,
                        "size_bytes": (snapshot_dir / "decision_ledger_v1.jsonl").stat().st_size,
                        "sha256": "unused",
                        "mtime_utc": "2026-05-07T00:00:00+00:00",
                        "copied_to": "source_snapshot/decision_ledger_v1.jsonl",
                        "required": True,
                        "notes": None,
                    },
                    {
                        "role": "order_log",
                        "source_path": (tmp_path / "logs" / "order_log_v1.jsonl").as_posix(),
                        "source_kind": "current_workspace_authority",
                        "exists": True,
                        "size_bytes": (snapshot_dir / "order_log_v1.jsonl").stat().st_size,
                        "sha256": "unused",
                        "mtime_utc": "2026-05-07T00:00:00+00:00",
                        "copied_to": "source_snapshot/order_log_v1.jsonl",
                        "required": True,
                        "notes": None,
                    },
                    {
                        "role": "trade_lifecycle",
                        "source_path": (tmp_path / "logs" / "trade_lifecycle.jsonl").as_posix(),
                        "source_kind": "current_workspace_authority",
                        "exists": False,
                        "size_bytes": None,
                        "sha256": None,
                        "mtime_utc": None,
                        "copied_to": None,
                        "required": False,
                        "notes": None,
                    },
                ],
                "missing_required_sources": [],
                "warnings": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result = analyze_runtime_close_coverage(
        tmp_path,
        realized_artifact_dir=artifact_dir,
    )

    row = result["unmatched_classification"]["rows"][0]
    assert row["classification"] == "CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED"
    assert result["source_inputs"]["audit_source_kind"] == "artifact_authority_snapshot"
    assert result["source_inputs"]["authority_order_log_exists"] is True
    assert result["source_inputs"]["source_snapshot_manifest"]["exists"] is True
    assert result["source_inputs"]["decision_ledger"]["source_kind"] == "artifact_authority_snapshot"
