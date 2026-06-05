import json
from pathlib import Path

import pytest

from calibrators.datasets.build_realized_outcome_dataset import build_parser
from calibrators.datasets.builders.realized_outcome_builder import (
    build_realized_outcome_dataset,
)
from apps.reference.domains.shadow_telemetry.ledger_writer import ShadowTelemetrySink


class _StubEvent:
    def __init__(self, payload: dict[str, object]) -> None:
        self.pld = payload


class _StubFSM:
    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}

    def listen(self, event_name: str, handler) -> None:
        self.listeners.setdefault(event_name, []).append(handler)

    def emit(self, event_name: str, payload: dict[str, object], why: str = "") -> None:
        del why
        for handler in self.listeners.get(event_name, []):
            handler(_StubEvent(payload))


def _make_sink(path: Path, **kwargs: object) -> ShadowTelemetrySink:
    sink_kwargs = {
        "queue_maxsize": 8,
        "overflow_policy": "fail_closed",
        "enqueue_timeout_ms": 0,
        "shutdown_timeout_ms": 2000,
    }
    sink_kwargs.update(kwargs)
    return ShadowTelemetrySink(path=path, **sink_kwargs)


def _read_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _causal_snapshot(
    values: list[float],
    *,
    tick_ts_ms: int = 1_700_000_000_000,
) -> dict[str, object]:
    return {
        "tick_ts_ms": tick_ts_ms,
        "state_vector": values,
        "event_time_source": "aurora_event",
        "event_time_is_causal": True,
        "trainable": True,
        "dataset_visibility": "trainable",
    }


def _decision_trace_payload(
    *,
    decision_id: str,
    rid: str,
    symbol: str,
    accepted_or_rejected: str,
    gate_chain_result: str,
    reject_reason: str | None = None,
) -> dict[str, object]:
    return {
        "rid": rid,
        "decision_id": decision_id,
        "cycle_key": f"ENTRY:{symbol}:300:1700000000000",
        "symbol": symbol,
        "side": "BUY",
        "strategy_id": "aurora",
        "ts": 1_700_000_001_234,
        "event_ts_ms": 1_700_000_001_234,
        "tf_sec": 300,
        "bar_close_ts_ms": 1_700_000_000_000,
        "intent_side": "LONG",
        "lifecycle_id": f"LIFE:{decision_id}",
        "intent_id": f"LIFE:{decision_id}",
        "raw_score": 0.88,
        "decision_score": 0.91,
        "active_threshold": 0.45,
        "score_to_threshold_ratio": 2.022222222222222,
        "decision_surface": "aurora_quadratic",
        "gate_chain_result": gate_chain_result,
        "accepted_or_rejected": accepted_or_rejected,
        "reject_reason": reject_reason,
        "regime": "TREND_UP",
        "regime_confidence": 0.82,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _decision_row(
    *,
    rid: str | None = "rid_1",
    decision_id: str = "dec_1",
    **overrides: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
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
    payload.update(overrides)
    return payload


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
    lifecycle_id: str = "lc_1",
    trade_id: str = "trade_1",
    realized_pnl_net: float | None = 1.8,
    fees: float | None = 0.2,
    timestamp: int = 1714568600000,
    pnl_status: str = "resolved",
    close_price: float | None = 104.0,
) -> dict[str, object]:
    return {
        "rid": rid,
        "event_type": "POSITION_CLOSED",
        "lifecycle_id": lifecycle_id,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "trade_id": trade_id,
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


def test_builder_uses_latest_appended_decision_row_revision_for_duplicate_rid(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
        [
            _decision_row(
                terminal_status="INVALID_FOR_DATASET",
                invalid_reason_code="OUTCOME_UNRESOLVED",
                lifecycle_id="lc_1",
            ),
            _decision_row(
                lifecycle_id="lc_1",
            ),
        ],
    )
    _write_jsonl(
        tmp_path / "logs" / "order_log_v1.jsonl",
        [_entry_fill(), _close_row()],
    )

    result = build_realized_outcome_dataset(repo_root=tmp_path)

    assert result.data_quality_summary["eligible_input_rows"] == 1
    assert result.data_quality_summary["rows_emitted"] == 1
    assert result.realized_rows[0]["terminal_status"] == "EXECUTED_AND_CLOSED"


def test_builder_exposes_accepted_unresolved_separately_from_rejections_and_final_rows(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
        [
            _decision_row(
                terminal_status="INVALID_FOR_DATASET",
                invalid_reason_code="OUTCOME_UNRESOLVED",
                accepted_or_rejected="ACCEPTED",
                revision_status="SEED_PENDING_OUTCOME",
                outcome_status="UNRESOLVED_ACCEPTED",
                dataset_visibility="diagnostics_only",
                lifecycle_id="lc_accepted_unresolved",
            )
        ],
    )
    _write_jsonl(
        tmp_path / "logs" / "order_log_v1.jsonl",
        [],
    )

    out_dir = tmp_path / "artifacts" / "accepted_unresolved"
    result = build_realized_outcome_dataset(
        repo_root=tmp_path, out_dir=out_dir)

    assert result.realized_rows == []
    assert result.rejected_rows == []
    assert len(result.accepted_unresolved_rows) == 1
    unresolved_row = result.accepted_unresolved_rows[0]
    assert unresolved_row["reason"] == "ACCEPTED_UNRESOLVED"
    assert unresolved_row["outcome_status"] == "UNRESOLVED_ACCEPTED"
    assert unresolved_row["revision_status"] == "SEED_PENDING_OUTCOME"
    assert result.data_quality_summary["accepted_unresolved_rows"] == 1
    assert result.data_quality_summary["rows_emitted"] == 0
    assert result.manifest["accepted_unresolved_rows"] == 1
    assert (out_dir / "accepted_unresolved_rows.jsonl").exists()
    quality_report = (
        out_dir / "DATA_QUALITY_REPORT.md").read_text(encoding="utf-8")
    assert "accepted_unresolved_rows: 1" in quality_report


def test_sink_seed_then_terminal_revision_builder_collapses_to_latest_final_row(tmp_path: Path) -> None:
    ledger_path = tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl"
    fsm = _StubFSM()
    sink = _make_sink(
        ledger_path,
        pending_ttl_ms=10_000,
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    sink.start()
    sink.register(fsm)

    fsm.emit(
        "SHADOW:NEOCORTEX_DECISION_LOGGED",
        {
            "decision_id": "decision-e2e-1",
            "rid": "RID-E2E-1",
            "symbol": "BTCUSDT",
            "authority_mode": "gated",
            "request_ts_ms": 1_700_000_000_000,
            "response_ts_ms": 1_700_000_000_010,
            "apply_result": "GATED_ALLOW",
            "action": "ALLOW",
            "fallback_reason": None,
            "causal_state_snapshot": _causal_snapshot([0.1, 0.2]),
            "data_quality_flags": {
                "snapshot_missing": False,
                "supports_counterfactual_join": True,
                "has_nan": False,
                "is_stale": False,
            },
        },
    )
    fsm.emit(
        "EVT:DECISION_TRACE_EMITTED",
        _decision_trace_payload(
            decision_id="decision-e2e-1",
            rid="RID-E2E-1",
            symbol="BTCUSDT",
            accepted_or_rejected="ACCEPTED",
            gate_chain_result="ALLOW",
        ),
    )
    fsm.emit(
        "EVT:TRADE_INTENT_PROPOSED",
        {
            "rid": "RID-E2E-1",
            "symbol": "BTCUSDT",
            "lifecycle_id": "LIFE:decision-e2e-1",
            "idempotent_key": "LIFE:decision-e2e-1",
            "authority_context": {
                "decision_id": "decision-e2e-1",
                "authority_mode": "gated",
                "action": "allow",
                "apply_result": "GATED_ALLOW",
            },
        },
    )
    fsm.emit(
        "EVT:TRADE_EXECUTED",
        {
            "rid": "RID-E2E-1",
            "symbol": "BTCUSDT",
            "lifecycle_id": "LIFE:decision-e2e-1",
            "trade_id": "TRADE-E2E-1",
        },
    )
    fsm.emit(
        "EVT:POSITION_CLOSED",
        {
            "decision_id": "decision-e2e-1",
            "rid": "RID-E2E-1",
            "symbol": "BTCUSDT",
            "lifecycle_id": "LIFE:decision-e2e-1",
            "trade_id": "TRADE-E2E-1",
            "realized_pnl_net": 1.8,
            "fees": 0.2,
            "close_reason": "TP_HIT",
            "timestamp": 1714568600000,
            "metadata": {"realized_pnl": 2.0, "close_price": 104.0},
        },
    )

    assert sink.wait_until_idle(2.0)
    sink.stop()

    ledger_rows = _read_rows(ledger_path)
    assert len(ledger_rows) == 2
    assert ledger_rows[0]["decision_id"] == "decision-e2e-1"
    assert ledger_rows[0]["rid"] == "RID-E2E-1"
    assert ledger_rows[0]["revision_status"] == "SEED_PENDING_OUTCOME"
    assert ledger_rows[0]["outcome_status"] == "UNRESOLVED_ACCEPTED"
    assert ledger_rows[1]["decision_id"] == "decision-e2e-1"
    assert ledger_rows[1]["rid"] == "RID-E2E-1"
    assert ledger_rows[1]["revision_status"] == "OUTCOME_FINAL"
    assert ledger_rows[1]["outcome_status"] == "REALIZED"

    _write_jsonl(
        tmp_path / "logs" / "order_log_v1.jsonl",
        [
            _entry_fill(lifecycle_id="LIFE:decision-e2e-1", rid="ENTRY-E2E-1"),
            _close_row(
                rid="RID-E2E-1",
                lifecycle_id="LIFE:decision-e2e-1",
                trade_id="TRADE-E2E-1",
            ),
        ],
    )

    result = build_realized_outcome_dataset(repo_root=tmp_path)

    assert result.data_quality_summary["eligible_input_rows"] == 1
    assert result.data_quality_summary["rows_emitted"] == 1
    assert result.realized_rows[0]["decision_id"] == "decision-e2e-1"
    assert result.realized_rows[0]["terminal_status"] == "EXECUTED_AND_CLOSED"
    assert result.accepted_unresolved_rows == []
    assert result.rejected_rows == []


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


def test_rejected_rows_do_not_contaminate_close_coverage_denominator(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
        [
            _decision_row(rid="rid_rejected", decision_id="decision_rejected",
                          terminal_status="REJECTED_UPSTREAM"),
            _decision_row(
                rid="rid_executed", decision_id="decision_executed", lifecycle_id="lc_executed"),
        ],
    )
    _write_jsonl(
        tmp_path / "logs" / "order_log_v1.jsonl",
        [
            _entry_fill(rid="rid_executed", lifecycle_id="lc_executed"),
            _close_row(rid="rid_executed", lifecycle_id="lc_executed"),
        ],
    )

    result = build_realized_outcome_dataset(repo_root=tmp_path)

    assert result.data_quality_summary["total_decision_rows"] == 2
    assert result.data_quality_summary["rejected_or_not_executed_rows"] == 1
    assert result.data_quality_summary["execution_eligible_rows"] == 1
    assert result.data_quality_summary["entry_filled_rows"] == 1
    assert result.data_quality_summary["close_expected_rows"] == 1
    assert result.data_quality_summary["close_matched_rows"] == 1
    assert result.data_quality_summary["exact_roundtrip_rows"] == 1
    assert result.data_quality_summary["eligible_input_rows"] == 1
    assert result.data_quality_summary["match_coverage_pct"] == pytest.approx(
        100.0)
    assert result.data_quality_summary["decision_to_execution_rate"] == pytest.approx(
        50.0)
    assert result.data_quality_summary["execution_to_close_coverage_pct"] == pytest.approx(
        100.0)
    assert result.data_quality_summary["close_to_exact_roundtrip_pct"] == pytest.approx(
        100.0)
    assert result.data_quality_summary["total_decision_to_exact_roundtrip_pct"] == pytest.approx(
        50.0)


def test_execution_evidence_overrides_reject_terminal_status_in_denominator(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
        [
            _decision_row(
                rid="rid_conflict",
                decision_id="decision_conflict",
                terminal_status="REJECTED_UPSTREAM",
                lifecycle_id="lc_conflict",
            )
        ],
    )
    _write_jsonl(
        tmp_path / "logs" / "order_log_v1.jsonl",
        [
            _entry_fill(rid="rid_conflict", lifecycle_id="lc_conflict"),
            _close_row(rid="rid_conflict", lifecycle_id="lc_conflict"),
        ],
    )

    result = build_realized_outcome_dataset(repo_root=tmp_path)

    assert result.data_quality_summary["rejected_or_not_executed_rows"] == 0
    assert result.data_quality_summary["execution_eligible_rows"] == 1
    assert result.data_quality_summary["close_expected_rows"] == 1
    assert result.data_quality_summary["close_matched_rows"] == 1
    assert result.data_quality_summary["match_coverage_pct"] == pytest.approx(
        100.0)


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

    assert result.data_quality_summary["total_decision_rows"] == 47
    assert result.data_quality_summary["execution_eligible_rows"] == 47
    assert result.data_quality_summary["entry_filled_rows"] == 3
    assert result.data_quality_summary["close_expected_rows"] == 3
    assert result.data_quality_summary["eligible_input_rows"] == 3
    assert result.data_quality_summary["matched_rows"] == 3
    assert result.data_quality_summary["unmatched_rows"] == 0
    assert result.data_quality_summary["match_coverage_pct"] == pytest.approx(
        100.0)
    assert result.data_quality_summary["execution_to_close_coverage_pct"] == pytest.approx(
        100.0)
    assert result.data_quality_summary["close_to_exact_roundtrip_pct"] == pytest.approx(
        100.0)
    assert result.data_quality_summary["total_decision_to_exact_roundtrip_pct"] == pytest.approx(
        6.383)
    assert result.data_quality_summary["exact_roundtrip_coverage_pct"] == pytest.approx(
        100.0)
    assert result.data_quality_summary["coverage_grade"] == "SPARSE_DIAGNOSTIC"
    assert result.data_quality_summary["diagnostics_only"] is True
    assert result.data_quality_summary["promotion_grade"] is False
    assert "INSUFFICIENT_REALIZED_ROWS" in result.blockers
    assert "INSUFFICIENT_REALIZED_COVERAGE" not in result.blockers


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
    denominator_audit_json = out_dir / "denominator_audit.json"
    denominator_audit_md = out_dir / "DENOMINATOR_AUDIT.md"

    assert snapshot_manifest_path.exists()
    assert dataset_manifest_path.exists()
    assert report_path.exists()
    assert denominator_audit_json.exists()
    assert denominator_audit_md.exists()

    snapshot_manifest = json.loads(
        snapshot_manifest_path.read_text(encoding="utf-8"))
    dataset_manifest = json.loads(
        dataset_manifest_path.read_text(encoding="utf-8"))
    denominator_audit = json.loads(
        denominator_audit_json.read_text(encoding="utf-8"))
    quality_report = report_path.read_text(encoding="utf-8")

    assert result.manifest["source_snapshot_manifest"] == "source_snapshot/source_snapshot_manifest.json"
    assert dataset_manifest["source_snapshot_manifest"] == "source_snapshot/source_snapshot_manifest.json"
    assert dataset_manifest["source_snapshot_requested"] is True
    assert dataset_manifest["source_snapshot"]["missing_required_sources"] == [
    ]
    assert dataset_manifest["coverage_denominator_kind"] == "close_expected_rows"
    assert denominator_audit["coverage_denominator_kind"] == "close_expected_rows"
    assert denominator_audit["close_expected_rows"] == 1
    assert "coverage_denominator_kind: close_expected_rows" in quality_report
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
