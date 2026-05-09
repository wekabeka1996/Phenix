import json
from pathlib import Path

import pytest

from calibrators.datasets.build_realized_outcome_dataset import build_parser
from calibrators.datasets.builders.realized_outcome_builder import (
    build_realized_outcome_dataset,
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _decision_row(*, rid: str | None = "rid_1", decision_id: str = "dec_1") -> dict[str, object]:
    return {
        "decision_id": decision_id,
        "rid": rid,
        "symbol": "BTCUSDT",
        "request_ts_ms": 1714568400000,
        "response_ts_ms": 1714568401000,
        "terminal_status": "EXECUTED_AND_CLOSED",
        "causal_state_snapshot": {
            "decision_basis_ts_ms": 1714568399000,
            "candidate_intent_summary": {
                "strategy_id": "aurora",
                "side": "BUY",
                "quantity": "0.5",
                "proposed_action": "OPEN_LONG",
            },
        },
    }


def _decision_rows(count: int) -> list[dict[str, object]]:
    return [
        _decision_row(rid=f"rid_{index}", decision_id=f"dec_{index}")
        for index in range(count)
    ]


def _entry_fill(*, lifecycle_id: str = "rid_1", rid: str = "ENTRY-1") -> dict[str, object]:
    return {
        "rid": rid,
        "event_type": "ORDER_FILLED",
        "lifecycle_id": lifecycle_id,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": 0.5,
        "price": 100.0,
        "order_kind": "ENTRY",
        "metadata": {"commission": 0.1},
        "timestamp": 1714568402000,
    }


def _entry_fill_for(index: int) -> dict[str, object]:
    return {
        **_entry_fill(lifecycle_id=f"rid_{index}", rid=f"ENTRY-{index}"),
        "metadata": {"commission": 0.1},
        "timestamp": 1714568402000 + index,
    }


def _close_row(
    *,
    rid: str = "rid_1",
    realized_pnl_net: float | None = 1.8,
    fees: float | None = 0.2,
    timestamp: int = 1714568600000,
    pnl_status: str = "resolved",
    close_price: float | None = 104.0,
) -> dict[str, object]:
    return {
        "rid": rid,
        "event_type": "POSITION_CLOSED",
        "lifecycle_id": "lc_1",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "trade_id": "trade_1",
        "fees": fees,
        "realized_pnl_net": realized_pnl_net,
        "pnl_status": pnl_status,
        "economic_close_detected": pnl_status == "resolved",
        "metadata": {
            "close_price": close_price,
            "realized_pnl": 2.0 if realized_pnl_net is not None else None,
            "close_fill_client_order_id": "close_fill_1",
        },
        "timestamp": timestamp,
    }


def _close_row_for(index: int) -> dict[str, object]:
    return {
        **_close_row(rid=f"rid_{index}", timestamp=1714568600000 + index),
        "trade_id": f"trade_{index}",
    }


def test_build_realized_row_from_exact_decision_and_close_rid(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
        [_decision_row()],
    )
    _write_jsonl(
        tmp_path / "logs" / "order_log_v1.jsonl",
        [_entry_fill(), _close_row()],
    )

    result = build_realized_outcome_dataset(repo_root=tmp_path)

    assert result.data_quality_summary["rows_emitted"] == 1
    assert result.data_quality_summary["schema_valid"] is True
    row = result.realized_rows[0]
    assert row["dataset_schema"] == "calibration_realized_trade_dataset_v1"
    assert row["decision_id"] == "dec_1"
    assert row["rid"] == "rid_1"
    assert row["synthetic"] is False
    assert {Path(path).name for path in row["source_paths"]} == {
        "decision_ledger_v1.jsonl",
        "order_log_v1.jsonl",
    }
    assert row["exact_roundtrip"] is True
    assert result.data_quality_summary["coverage_grade"] == "SPARSE_DIAGNOSTIC"
    assert result.data_quality_summary["promotion_grade"] is False
    assert "INSUFFICIENT_REALIZED_ROWS" in result.blockers


def test_missing_rid_decision_row_records_rejection_and_no_join(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
        [_decision_row(rid=None)],
    )
    _write_jsonl(
        tmp_path / "logs" / "order_log_v1.jsonl",
        [_entry_fill(), _close_row()],
    )

    result = build_realized_outcome_dataset(repo_root=tmp_path)

    assert result.realized_rows == []
    assert any(item["reason"] ==
               "MISSING_DECISION_RID" for item in result.rejected_rows)
    assert result.data_quality_summary["promotion_grade"] is False


def test_close_row_with_different_rid_emits_no_realized_row(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
        [_decision_row()],
    )
    _write_jsonl(
        tmp_path / "logs" / "order_log_v1.jsonl",
        [_entry_fill(), _close_row(rid="other_rid")],
    )

    result = build_realized_outcome_dataset(repo_root=tmp_path)

    assert result.realized_rows == []
    assert any(item["reason"] ==
               "NO_MATCHING_CLOSE_EVENT" for item in result.rejected_rows)


def test_duplicate_close_candidates_selects_deterministic_best_row(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
        [_decision_row()],
    )
    _write_jsonl(
        tmp_path / "logs" / "order_log_v1.jsonl",
        [
            _entry_fill(),
            _close_row(realized_pnl_net=None, fees=None, timestamp=1714568599000,
                       pnl_status="unresolved", close_price=None),
            _close_row(realized_pnl_net=1.8, fees=0.2,
                       timestamp=1714568600000),
        ],
    )

    result = build_realized_outcome_dataset(repo_root=tmp_path)

    assert result.data_quality_summary["rows_emitted"] == 1
    assert result.canonicalization_report["duplicate_close_candidates"] == 1
    assert result.realized_rows[0]["realized_pnl_net"] == pytest.approx(1.8)
    assert any(
        "Duplicate close candidates" in warning for warning in result.warnings)


def test_close_row_without_entry_fields_emits_diagnostics_only_partial_row(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
        [_decision_row()],
    )
    _write_jsonl(
        tmp_path / "logs" / "order_log_v1.jsonl",
        [_close_row()],
    )

    result = build_realized_outcome_dataset(repo_root=tmp_path)

    assert result.data_quality_summary["rows_emitted"] == 1
    assert result.realized_rows[0]["exact_roundtrip"] is False
    assert result.data_quality_summary["diagnostics_only"] is True
    assert result.data_quality_summary["promotion_grade"] is False
    assert "NO_EXACT_ROUNDTRIPS" in result.blockers


def test_sparse_realized_coverage_stays_diagnostics_only(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
        _decision_rows(47),
    )
    order_rows: list[dict[str, object]] = []
    for index in range(3):
        order_rows.append(_entry_fill_for(index))
        order_rows.append(_close_row_for(index))
    _write_jsonl(tmp_path / "logs" / "order_log_v1.jsonl", order_rows)

    result = build_realized_outcome_dataset(repo_root=tmp_path)

    assert result.data_quality_summary["eligible_input_rows"] == 47
    assert result.data_quality_summary["matched_rows"] == 3
    assert result.data_quality_summary["unmatched_rows"] == 44
    assert result.data_quality_summary["match_coverage_pct"] == pytest.approx(
        6.383)
    assert result.data_quality_summary["exact_roundtrip_coverage_pct"] == pytest.approx(
        6.383)
    assert result.data_quality_summary["coverage_grade"] == "SPARSE_DIAGNOSTIC"
    assert result.data_quality_summary["diagnostics_only"] is True
    assert result.data_quality_summary["promotion_grade"] is False
    assert "INSUFFICIENT_REALIZED_ROWS" in result.blockers
    assert "INSUFFICIENT_REALIZED_COVERAGE" in result.blockers


def test_realized_coverage_becomes_promotion_eligible_only_when_thresholds_pass(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
        _decision_rows(30),
    )
    order_rows: list[dict[str, object]] = []
    for index in range(30):
        order_rows.append(_entry_fill_for(index))
        order_rows.append(_close_row_for(index))
    _write_jsonl(tmp_path / "logs" / "order_log_v1.jsonl", order_rows)

    result = build_realized_outcome_dataset(repo_root=tmp_path)

    assert result.data_quality_summary["eligible_input_rows"] == 30
    assert result.data_quality_summary["matched_rows"] == 30
    assert result.data_quality_summary["unmatched_rows"] == 0
    assert result.data_quality_summary["match_coverage_pct"] == pytest.approx(
        100.0)
    assert result.data_quality_summary["coverage_grade"] == "PROMOTION_ELIGIBLE"
    assert result.data_quality_summary["diagnostics_only"] is False
    assert result.data_quality_summary["promotion_grade"] is True


def test_builder_writes_source_snapshot_manifest_and_dataset_manifest_reference(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
        [_decision_row()],
    )
    _write_jsonl(
        tmp_path / "logs" / "order_log_v1.jsonl",
        [_entry_fill(), _close_row()],
    )

    out_dir = tmp_path / "artifacts" / "realized"
    result = build_realized_outcome_dataset(
        repo_root=tmp_path, out_dir=out_dir)

    snapshot_manifest_path = out_dir / \
        "source_snapshot" / "source_snapshot_manifest.json"
    dataset_manifest_path = out_dir / "dataset_manifest.json"
    report_path = out_dir / "DATA_QUALITY_REPORT.md"

    assert snapshot_manifest_path.exists()
    assert dataset_manifest_path.exists()
    assert report_path.exists()

    snapshot_manifest = json.loads(
        snapshot_manifest_path.read_text(encoding="utf-8"))
    dataset_manifest = json.loads(
        dataset_manifest_path.read_text(encoding="utf-8"))
    quality_report = report_path.read_text(encoding="utf-8")

    assert result.manifest["source_snapshot_manifest"] == "source_snapshot/source_snapshot_manifest.json"
    assert dataset_manifest["source_snapshot_manifest"] == "source_snapshot/source_snapshot_manifest.json"
    assert dataset_manifest["source_snapshot_requested"] is True
    assert dataset_manifest["source_snapshot"]["missing_required_sources"] == [
    ]
    assert {entry["role"] for entry in snapshot_manifest["sources"]} == {
        "decision_ledger",
        "order_log",
        "trade_lifecycle",
    }
    copied_roles = {
        entry["role"]: entry["copied_to"]
        for entry in snapshot_manifest["sources"]
        if entry["exists"]
    }
    assert copied_roles["decision_ledger"] == "source_snapshot/decision_ledger_v1.jsonl"
    assert copied_roles["order_log"] == "source_snapshot/order_log_v1.jsonl"
    assert "source_snapshot/source_snapshot_manifest.json" in quality_report
    assert "MISSING_OPTIONAL_SOURCE:trade_lifecycle" in quality_report


def test_cli_help_works() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--help"])
    assert exc_info.value.code == 0


def test_cli_snapshot_sources_defaults_true_and_can_be_disabled() -> None:
    parser = build_parser()

    default_args = parser.parse_args(["--out-dir", "artifacts/out"])
    disabled_args = parser.parse_args(
        ["--out-dir", "artifacts/out", "--no-snapshot-sources"])

    assert default_args.snapshot_sources is True
    assert disabled_args.snapshot_sources is False
