from __future__ import annotations

import json
from pathlib import Path

import SEMA_ATOM_FORWARD_COLLECTOR as fc


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")


def test_rejected_reference_price_coverage_null_when_no_rejects() -> None:
    contracts, results = fc.RejectedDecisionCollector([]).collect()
    assert contracts == []
    assert results["rejected_events_found"] == 0
    assert results["rejected_reference_price_coverage"] is None


def test_low_support_manifest_loader_reads_counts(tmp_path: Path) -> None:
    payload = {
        "PROMISING_LOW_SUPPORT": [
            {
                "context_id": "BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50",
                "train_count": 2,
                "validation_count": 1,
            }
        ],
        "INCONCLUSIVE_LOW_POWER": [
            {
                "context_id": "ETHUSDT|SELL|aurora|TREND_DOWN|0.00..0.25",
                "train_count": 1,
                "validation_count": 2,
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    baseline = fc._load_low_support_baseline(manifest_path)
    assert baseline == {
        "BTCUSDT|BUY|aurora|LOW_VOLATILITY|0.25..0.50": 3,
        "ETHUSDT|SELL|aurora|TREND_DOWN|0.00..0.25": 3,
    }


def test_forward_collector_end_to_end(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path
    logs_dir = repo / "logs"
    recorder_day = repo / "data" / "recorder" / "2026-05-08"
    order_log = logs_dir / "order_log_v1.jsonl"
    baseline_saf = repo / "aurora_real_logs_v02.saf.jsonl"
    manifest = repo / "SEMA_ATOM_POC_03B_CANDIDATE_MANIFEST.json"
    trade_lifecycle = logs_dir / "trade_lifecycle.jsonl"
    shadow_dir = logs_dir / "shadow_telemetry"
    shadow_dir.mkdir(parents=True)
    trade_lifecycle.write_text("", encoding="utf-8")
    baseline_saf.write_text("", encoding="utf-8")
    (repo / "SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md").write_text("stub", encoding="utf-8")
    (repo / "SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md").write_text("stub", encoding="utf-8")
    (repo / "SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION_REPORT.md").write_text("stub", encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "PROMISING_LOW_SUPPORT": [
                    {
                        "context_id": "BTCUSDT|BUY|aurora|TREND_UP|0.25..0.50",
                        "train_count": 2,
                        "validation_count": 2,
                    }
                ],
                "INCONCLUSIVE_LOW_POWER": [],
            }
        ),
        encoding="utf-8",
    )

    # 2026-05-08 UTC timestamps.
    rows = [
        {
            "rid": "accepted-1",
            "event_type": "ORDER_INTENT",
            "lifecycle_id": "life-1",
            "symbol": "BTCUSDT",
            "strategy_id": "aurora",
            "side": "BUY",
            "price": 100.0,
            "source_fsm": "DecisionMaking",
            "regime": "TREND_UP",
            "regime_confidence": 0.3,
            "timestamp": 1778198700000,
        },
        {
            "rid": "entry-1",
            "event_type": "ORDER_FILLED",
            "lifecycle_id": "life-1",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "price": 100.0,
            "source_fsm": "ExecPosFSM",
            "order_kind": "ENTRY",
            "timestamp": 1778199000000,
        },
        {
            "rid": "accepted-1",
            "event_type": "POSITION_CLOSED",
            "lifecycle_id": "life-1",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "close_price": 102.0,
            "realized_pnl_net": 5.0,
            "fees": 1.0,
            "trade_id": "trade-1",
            "timestamp": 1778200800000,
        },
        {
            "rid": "reject-1",
            "event_type": "DECISION_INTENT_REJECTED",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "strategy_id": "aurora",
            "regime": "LOW_VOLATILITY",
            "regime_confidence": 0.4,
            "why": "blocked",
            "metadata": {
                "reject_reason": "LOW_VOL_COST_FLOOR_DENY",
                "low_vol_cost_floor": {
                    "entry_price": 100.0,
                    "direction_confidence": 0.2,
                },
            },
            "timestamp": 1778202000000,
        },
        {
            "rid": "reject-2",
            "event_type": "DECISION_INTENT_REJECTED",
            "symbol": "ETHUSDT",
            "side": "SELL",
            "strategy_id": "aurora",
            "regime": "LOW_VOLATILITY",
            "regime_confidence": 0.4,
            "metadata": {"reject_reason": "LOW_VOL_COST_FLOOR_DENY"},
            "timestamp": 1778202300000,
        },
    ]
    _write_jsonl(order_log, rows)

    recorder_day.mkdir(parents=True, exist_ok=True)
    (recorder_day / "BTCUSDT_300.csv").write_text(
        "\n".join(
            [
                "timestamp,close,high,low",
                "1778199000000,100,101,99.5",
                "1778199300000,101,102,100",
                "1778199600000,102,103,101",
                "1778200800000,102,103,101.5",
                "1778202900000,101,101.5,100.5",
                "1778203800000,103,103.5,102.5",
                "1778205600000,104,104.5,103.5",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(fc, "REPO_ROOT", repo)
    monkeypatch.setattr(fc, "DEFAULT_ORDER_LOG_PATH", order_log)
    monkeypatch.setattr(fc, "DEFAULT_TRADE_LIFECYCLE_PATH", trade_lifecycle)
    monkeypatch.setattr(fc, "DEFAULT_SHADOW_TELEMETRY_DIR", shadow_dir)
    monkeypatch.setattr(fc, "DEFAULT_RECORDER_ROOT", repo / "data" / "recorder")
    monkeypatch.setattr(fc, "DEFAULT_BASELINE_SAF_PATH", baseline_saf)
    monkeypatch.setattr(fc, "DEFAULT_POC02_REPORT_PATH", repo / "SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md")
    monkeypatch.setattr(fc, "DEFAULT_POC03_REPORT_PATH", repo / "SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md")
    monkeypatch.setattr(fc, "DEFAULT_POC03B_MANIFEST_PATH", manifest)
    monkeypatch.setattr(fc, "DEFAULT_POC04_REPORT_PATH", repo / "SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION_REPORT.md")
    monkeypatch.setattr(fc, "DEFAULT_INDEX_PATH", repo / "SEMA_ATOM_FORWARD_COLLECTION_INDEX.json")

    rc = fc.main(["--from", "2026-05-08", "--to", "2026-05-09"])
    assert rc == 0

    slice_path = repo / "aurora_forward_slice_2026-05-08_2026-05-09.saf.jsonl"
    report_path = repo / "SEMA_ATOM_FORWARD_COLLECTION_2026-05-08_2026-05-09_REPORT.md"
    index_path = repo / "SEMA_ATOM_FORWARD_COLLECTION_INDEX.json"

    assert baseline_saf.read_text(encoding="utf-8") == ""
    atoms = [json.loads(line) for line in slice_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(atoms) == 2
    assert {atom["atom_kind"] for atom in atoms} == {"ACCEPTED", "REJECTED"}

    report = report_path.read_text(encoding="utf-8")
    assert "FORWARD_COLLECTION_COMPLETED_WITH_RESIDUALS" in report
    assert "accepted_atoms_created: 1" in report
    assert "rejected_atoms_created: 1" in report
    assert "diagnostics_only_atoms_created: 0" in report
    assert "atoms_created_reconciliation_ok: True" in report
    assert "rejected_reference_price_coverage: 0.5" in report
    assert "contexts promoted from low-support: 1" in report
    assert '"2026-05-09"' in report

    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert index_payload["slices"][0]["slice_id"] == "2026-05-08_2026-05-09"
    assert index_payload["slices"][0]["atoms_created"] == 2
    assert index_payload["slices"][0]["accepted_atoms_created"] == 1
    assert index_payload["slices"][0]["rejected_atoms_created"] == 1


def test_forward_collector_blocks_unresolved_accepted_from_trainable_saf(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path
    logs_dir = repo / "logs"
    recorder_day = repo / "data" / "recorder" / "2026-05-08"
    order_log = logs_dir / "order_log_v1.jsonl"
    baseline_saf = repo / "aurora_real_logs_v02.saf.jsonl"
    manifest = repo / "SEMA_ATOM_POC_03B_CANDIDATE_MANIFEST.json"
    trade_lifecycle = logs_dir / "trade_lifecycle.jsonl"
    shadow_dir = logs_dir / "shadow_telemetry"
    shadow_dir.mkdir(parents=True)
    trade_lifecycle.write_text("", encoding="utf-8")
    baseline_saf.write_text("", encoding="utf-8")
    (repo / "SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md").write_text("stub", encoding="utf-8")
    (repo / "SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md").write_text("stub", encoding="utf-8")
    (repo / "SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION_REPORT.md").write_text("stub", encoding="utf-8")
    manifest.write_text(json.dumps({"PROMISING_LOW_SUPPORT": [], "INCONCLUSIVE_LOW_POWER": []}), encoding="utf-8")

    rows = [
        {
            "rid": "accepted-unresolved",
            "event_type": "ORDER_INTENT",
            "lifecycle_id": "life-unresolved",
            "symbol": "BTCUSDT",
            "strategy_id": "aurora",
            "side": "SELL",
            "price": 100.0,
            "source_fsm": "DecisionMaking",
            "regime": "TREND_DOWN",
            "regime_confidence": 0.3,
            "timestamp": 1778207102724,
        },
        {
            "rid": "entry-unresolved",
            "event_type": "ORDER_FILLED",
            "lifecycle_id": "life-unresolved",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "price": 100.0,
            "source_fsm": "ExecPosFSM",
            "order_kind": "ENTRY",
            "timestamp": 1778207561575,
        },
        {
            "rid": "accepted-unresolved",
            "event_type": "POSITION_CLOSED",
            "lifecycle_id": "life-unresolved",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "close_price": None,
            "realized_pnl_net": None,
            "fees": None,
            "pnl_status": "unresolved",
            "trade_id": None,
            "timestamp": 1778213714281,
            "why": "POSITION_CLOSED_DETECTED",
        },
        {
            "rid": "reject-1",
            "event_type": "DECISION_INTENT_REJECTED",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "strategy_id": "aurora",
            "regime": "LOW_VOLATILITY",
            "regime_confidence": 0.4,
            "why": "blocked",
            "metadata": {
                "reject_reason": "LOW_VOL_COST_FLOOR_DENY",
                "low_vol_cost_floor": {
                    "entry_price": 100.0,
                    "direction_confidence": 0.2,
                },
            },
            "timestamp": 1778202000000,
        },
    ]
    _write_jsonl(order_log, rows)

    recorder_day.mkdir(parents=True, exist_ok=True)
    (recorder_day / "BTCUSDT_300.csv").write_text(
        "\n".join(
            [
                "timestamp,close,high,low",
                "1778207561575,100,100.5,99.9",
                "1778207861575,99.8,100.1,99.7",
                "1778208161575,99.9,100.2,99.6",
                "1778213561575,99.7,100.0,99.5",
                "1778203800000,103,103.5,102.5",
                "1778205600000,104,104.5,103.5",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(fc, "REPO_ROOT", repo)
    monkeypatch.setattr(fc, "DEFAULT_ORDER_LOG_PATH", order_log)
    monkeypatch.setattr(fc, "DEFAULT_TRADE_LIFECYCLE_PATH", trade_lifecycle)
    monkeypatch.setattr(fc, "DEFAULT_SHADOW_TELEMETRY_DIR", shadow_dir)
    monkeypatch.setattr(fc, "DEFAULT_RECORDER_ROOT", repo / "data" / "recorder")
    monkeypatch.setattr(fc, "DEFAULT_BASELINE_SAF_PATH", baseline_saf)
    monkeypatch.setattr(fc, "DEFAULT_POC02_REPORT_PATH", repo / "SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md")
    monkeypatch.setattr(fc, "DEFAULT_POC03_REPORT_PATH", repo / "SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md")
    monkeypatch.setattr(fc, "DEFAULT_POC03B_MANIFEST_PATH", manifest)
    monkeypatch.setattr(fc, "DEFAULT_POC04_REPORT_PATH", repo / "SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION_REPORT.md")
    monkeypatch.setattr(fc, "DEFAULT_INDEX_PATH", repo / "SEMA_ATOM_FORWARD_COLLECTION_INDEX.json")

    rc = fc.main(["--from", "2026-05-08", "--to", "2026-05-09"])
    assert rc == 0

    slice_path = repo / "aurora_forward_slice_2026-05-08_2026-05-09.saf.jsonl"
    report_path = repo / "SEMA_ATOM_FORWARD_COLLECTION_2026-05-08_2026-05-09_REPORT.md"
    index_path = repo / "SEMA_ATOM_FORWARD_COLLECTION_INDEX.json"

    atoms = [json.loads(line) for line in slice_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(atoms) == 1
    assert atoms[0]["atom_kind"] == "REJECTED"
    assert all(atom["atom_kind"] != "ACCEPTED" for atom in atoms)

    report = report_path.read_text(encoding="utf-8")
    assert "accepted close events found: 1" in report
    assert "accepted contracts completed: 0" in report
    assert "accepted_atoms_created: 0" in report
    assert "diagnostics_only_atoms_created: 0" in report
    assert "incomplete_accepted_missing_realized_pnl_net: 1" in report
    assert "atoms created: 1" in report
    assert "atoms_created_reconciliation_ok: True" in report

    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert index_payload["slices"][0]["atoms_created"] == 1
    assert index_payload["slices"][0]["accepted_atoms_created"] == 0
    assert index_payload["slices"][0]["rejected_atoms_created"] == 1
    assert index_payload["slices"][0]["incomplete_accepted_missing_realized_pnl_net"] == 1
