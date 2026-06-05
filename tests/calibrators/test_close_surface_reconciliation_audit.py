import json
from pathlib import Path

from calibrators.datasets.audit_close_surface_reconciliation import (
    _classify_close_surface_bucket,
    analyze_close_surface_reconciliation,
    write_close_surface_reconciliation_artifacts,
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_close_surface_bucket_helper_covers_decision_and_builder_edges() -> None:
    decision = {"realized_fields_present": True}

    bucket, _ = _classify_close_surface_bucket(
        decision,
        {
            "order_exact_position_closed_count": 0,
            "order_lifecycle_bridge_position_closed_count": 0,
            "order_trade_bridge_position_closed_count": 0,
            "order_exact_close_fill_count": 0,
            "order_lifecycle_bridge_close_fill_count": 0,
            "order_trade_bridge_close_fill_count": 0,
            "order_exact_close_submitted_count": 0,
            "order_lifecycle_bridge_close_submitted_count": 0,
            "order_trade_bridge_close_submitted_count": 0,
            "order_exact_alternative_terminal_count": 0,
            "order_lifecycle_bridge_alternative_terminal_count": 0,
            "order_trade_bridge_alternative_terminal_count": 0,
            "trade_exact_terminal_close_count": 0,
            "trade_lifecycle_bridge_terminal_close_count": 0,
            "trade_trade_bridge_terminal_close_count": 0,
        },
    )
    assert bucket == "DECISION_LEDGER_REALIZED_ONLY"

    bucket, _ = _classify_close_surface_bucket(
        {"realized_fields_present": False},
        {
            "order_exact_position_closed_count": 1,
            "order_lifecycle_bridge_position_closed_count": 0,
            "order_trade_bridge_position_closed_count": 0,
            "order_exact_close_fill_count": 0,
            "order_lifecycle_bridge_close_fill_count": 0,
            "order_trade_bridge_close_fill_count": 0,
            "order_exact_close_submitted_count": 0,
            "order_lifecycle_bridge_close_submitted_count": 0,
            "order_trade_bridge_close_submitted_count": 0,
            "order_exact_alternative_terminal_count": 0,
            "order_lifecycle_bridge_alternative_terminal_count": 0,
            "order_trade_bridge_alternative_terminal_count": 0,
            "trade_exact_terminal_close_count": 0,
            "trade_lifecycle_bridge_terminal_close_count": 0,
            "trade_trade_bridge_terminal_close_count": 0,
        },
    )
    assert bucket == "BUILDER_CANONICALIZATION_GAP"

    bucket, _ = _classify_close_surface_bucket(
        {"realized_fields_present": False},
        {
            "order_exact_position_closed_count": 0,
            "order_lifecycle_bridge_position_closed_count": 0,
            "order_trade_bridge_position_closed_count": 1,
            "order_exact_close_fill_count": 0,
            "order_lifecycle_bridge_close_fill_count": 0,
            "order_trade_bridge_close_fill_count": 0,
            "order_exact_close_submitted_count": 0,
            "order_lifecycle_bridge_close_submitted_count": 0,
            "order_trade_bridge_close_submitted_count": 0,
            "order_exact_alternative_terminal_count": 0,
            "order_lifecycle_bridge_alternative_terminal_count": 0,
            "order_trade_bridge_alternative_terminal_count": 0,
            "trade_exact_terminal_close_count": 0,
            "trade_lifecycle_bridge_terminal_close_count": 0,
            "trade_trade_bridge_terminal_close_count": 0,
        },
    )
    assert bucket == "TRADE_ID_BRIDGE_AVAILABLE"


def test_close_surface_reconciliation_audit_writes_required_outputs(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts" / \
        "calibration_datasets" / "_post_03q_realized_outcome"
    snapshot_dir = artifact_dir / "source_snapshot"

    _write_jsonl(
        snapshot_dir / "decision_ledger_v1.jsonl",
        [
            {
                "decision_id": "dec_tl_closed",
                "rid": "rid_tl_closed",
                "symbol": "BNBUSDT",
                "terminal_status": "INVALID_FOR_DATASET",
                "lifecycle_id": "lc_tl_closed",
                "trade_id": "trade_tl_closed",
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
            {
                "decision_id": "dec_alt_terminal",
                "rid": "rid_alt_terminal",
                "symbol": "XRPUSDT",
                "terminal_status": "INVALID_FOR_DATASET",
                "lifecycle_id": "lc_alt_terminal",
                "apply_result": "SHADOW_RECORDED",
                "causal_state_snapshot": {
                    "decision_basis_ts_ms": 1714568460000,
                    "candidate_intent_summary": {
                        "strategy_id": "aurora",
                        "side": "BUY",
                        "proposed_action": "OPEN_LONG",
                    },
                },
            },
            {
                "decision_id": "dec_bridge",
                "rid": "rid_bridge",
                "symbol": "BTCUSDT",
                "terminal_status": "EXECUTED_AND_CLOSED",
                "lifecycle_id": "lc_bridge",
                "trade_id": "trade_bridge",
                "apply_result": "SHADOW_RECORDED",
                "realized_pnl_net": 1.25,
                "fees": 0.11,
                "causal_state_snapshot": {
                    "decision_basis_ts_ms": 1714568520000,
                    "candidate_intent_summary": {
                        "strategy_id": "aurora",
                        "side": "BUY",
                        "proposed_action": "OPEN_LONG",
                    },
                },
            },
            {
                "decision_id": "dec_runtime_gap",
                "rid": "rid_runtime_gap",
                "symbol": "ETHUSDT",
                "terminal_status": "INVALID_FOR_DATASET",
                "lifecycle_id": "lc_runtime_gap",
                "apply_result": "SHADOW_RECORDED",
                "causal_state_snapshot": {
                    "decision_basis_ts_ms": 1714568580000,
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
        snapshot_dir / "order_log_v1.jsonl",
        [
            {"rid": "rid_tl_closed", "event_type": "ORDER_INTENT",
                "lifecycle_id": "lc_tl_closed"},
            {"rid": "rid_tl_closed", "event_type": "ORDER_PLACED",
                "lifecycle_id": "lc_tl_closed"},
            {"rid": "rid_alt_terminal", "event_type": "ORDER_INTENT",
                "lifecycle_id": "lc_alt_terminal"},
            {"rid": "rid_alt_terminal", "event_type": "ORDER_PLACED",
                "lifecycle_id": "lc_alt_terminal"},
            {"rid": "rid_alt_terminal", "event_type": "ORDER_CANCELLED",
                "lifecycle_id": "lc_alt_terminal"},
            {"rid": "rid_alt_terminal", "event_type": "ORDER_TIMEOUT",
                "lifecycle_id": "lc_alt_terminal"},
            {"rid": "rid_bridge", "event_type": "ORDER_INTENT",
                "lifecycle_id": "lc_bridge", "trade_id": "trade_bridge"},
            {"rid": "rid_bridge", "event_type": "ORDER_PLACED",
                "lifecycle_id": "lc_bridge", "trade_id": "trade_bridge"},
            {
                "rid": "child_close_bridge",
                "event_type": "POSITION_CLOSED",
                "lifecycle_id": "lc_bridge",
                "trade_id": "trade_bridge",
                "realized_pnl_net": 1.25,
                "fees": 0.11,
                "timestamp": 1714568620000,
            },
            {"rid": "rid_runtime_gap", "event_type": "ORDER_INTENT",
                "lifecycle_id": "lc_runtime_gap"},
            {"rid": "rid_runtime_gap", "event_type": "ORDER_PLACED",
                "lifecycle_id": "lc_runtime_gap"},
            {
                "rid": "child_close_runtime_gap",
                "event_type": "ORDER_FILLED",
                "order_kind": "CLOSE",
                "close_reason": "TP",
                "lifecycle_id": "lc_runtime_gap",
                "timestamp": 1714568640000,
            },
        ],
    )
    _write_jsonl(
        snapshot_dir / "trade_lifecycle.jsonl",
        [
            {
                "rid": "rid_tl_closed",
                "event_type": "POSITION_CLOSED",
                "status": "CLOSED",
                "lifecycle_id": "lc_tl_closed",
                "trade_id": "trade_tl_closed",
                "close_ts_ms": 1714568600000,
            },
            {
                "rid": "rid_alt_terminal",
                "event_type": "POSITION_CLOSED",
                "status": "CLOSED",
                "lifecycle_id": "lc_alt_terminal",
                "close_ts_ms": 1714568610000,
            },
        ],
    )
    _write_jsonl(artifact_dir / "realized_trades.jsonl", [])
    _write_jsonl(
        artifact_dir / "rejected_rows.jsonl",
        [
            {"decision_id": "dec_tl_closed", "rid": "rid_tl_closed",
                "reason": "NO_MATCHING_CLOSE_EVENT"},
            {"decision_id": "dec_alt_terminal", "rid": "rid_alt_terminal",
                "reason": "NO_MATCHING_CLOSE_EVENT"},
            {"decision_id": "dec_bridge", "rid": "rid_bridge",
                "reason": "NO_MATCHING_CLOSE_EVENT"},
            {"decision_id": "dec_runtime_gap", "rid": "rid_runtime_gap",
                "reason": "NO_MATCHING_CLOSE_EVENT"},
        ],
    )
    (snapshot_dir / "source_snapshot_manifest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-05-10T00:00:00+00:00",
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
                        "mtime_utc": "2026-05-10T00:00:00+00:00",
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
                        "mtime_utc": "2026-05-10T00:00:00+00:00",
                        "copied_to": "source_snapshot/order_log_v1.jsonl",
                        "required": True,
                        "notes": None,
                    },
                    {
                        "role": "trade_lifecycle",
                        "source_path": (tmp_path / "logs" / "trade_lifecycle.jsonl").as_posix(),
                        "source_kind": "current_workspace_authority",
                        "exists": True,
                        "size_bytes": (snapshot_dir / "trade_lifecycle.jsonl").stat().st_size,
                        "sha256": "unused",
                        "mtime_utc": "2026-05-10T00:00:00+00:00",
                        "copied_to": "source_snapshot/trade_lifecycle.jsonl",
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

    result = analyze_close_surface_reconciliation(
        tmp_path,
        realized_artifact_dir=artifact_dir,
    )

    rows = {
        row["rid"]: row
        for row in result["close_expected_unmatched_ledger"]["rows"]
    }
    assert rows["rid_tl_closed"]["close_surface_bucket"] == "ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED"
    assert rows["rid_alt_terminal"]["close_surface_bucket"] == "ORDER_LOG_HAS_ALTERNATIVE_TERMINAL_EVENT"
    assert rows["rid_bridge"]["close_surface_bucket"] == "LIFECYCLE_ID_BRIDGE_AVAILABLE"
    assert rows["rid_runtime_gap"]["close_surface_bucket"] == "RUNTIME_LOGGING_GAP"
    assert result["close_surface_reconciliation_matrix"]["recommended_next_package"] == "03T_RUNTIME_POSITION_CLOSED_EMISSION_REPAIR"

    out_dir = tmp_path / "calibrators" / "datasets" / \
        "close_surface_reconciliation_post_03r"
    write_close_surface_reconciliation_artifacts(result, out_dir)

    assert (out_dir / "CLOSE_EXPECTED_UNMATCHED_LEDGER.json").exists()
    assert (out_dir / "CLOSE_EXPECTED_UNMATCHED_LEDGER.csv").exists()
    assert (out_dir / "CLOSE_EXPECTED_UNMATCHED_LEDGER.md").exists()
    assert (out_dir / "CLOSE_SURFACE_RECONCILIATION_MATRIX.json").exists()
    assert (out_dir / "CLOSE_SURFACE_RECONCILIATION_MATRIX.md").exists()
    assert (out_dir / "ORDER_LOG_VS_TRADE_LIFECYCLE_CLOSE_AUDIT.md").exists()
    assert (out_dir / "DECISION_LEDGER_REALIZED_FIELDS_AUDIT.md").exists()
    json.loads(
        (out_dir / "CLOSE_EXPECTED_UNMATCHED_LEDGER.json").read_text(encoding="utf-8"))
    json.loads(
        (out_dir / "CLOSE_SURFACE_RECONCILIATION_MATRIX.json").read_text(encoding="utf-8"))
