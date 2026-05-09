from __future__ import annotations

import json
from pathlib import Path

from tools.analysis import capture_nrr062_fresh_cohort as mod


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _write_csv(path: Path, open_times: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write("open_time,open,high,low,close,volume\n")
        for ts in open_times:
            f.write(f"{ts},1,1,1,1,1\n")


def test_build_parser_default_out_dir_logs_frozen() -> None:
    parser = mod.build_parser()
    args = parser.parse_args([])
    assert str(args.out_dir).replace("\\", "/") == "logs/frozen"


def test_resolve_and_validate_out_dir_rejects_reports_forensics(tmp_path: Path) -> None:
    ok, err, _ = mod.resolve_and_validate_out_dir(
        tmp_path, Path("reports/forensics"))
    assert ok is False
    assert err.startswith("out_dir_must_be_under_logs_frozen:")


def test_probe_order_nrr062_counts_and_extracts_ts(tmp_path: Path) -> None:
    order_log = tmp_path / "order_log_v1.jsonl"
    _write_jsonl(
        order_log,
        [
            {"event_type": "DECISION_INTENT_REJECTED", "nrr_code": "NRR-062",
                "symbol": "BTCUSDT", "ts_ms": 1000, "rid": "r1"},
            {"event_type": "DECISION_INTENT_REJECTED", "nrr_code": "NRR-061",
                "symbol": "BTCUSDT", "ts_ms": 2000, "rid": "r2"},
            {"event_type": "DECISION_INTENT_REJECTED", "nrr_code": "NRR-062",
                "symbol": "ETHUSDT", "timestamp": 3000, "rid": "r3"},
        ],
    )
    nrr, malformed, rows = mod.probe_order_nrr062(order_log)
    assert nrr == 2
    assert malformed == 0
    assert {r["rid"] for r in rows} == {"r1", "r3"}
    assert {r["ts_ms"] for r in rows} == {1000, 3000}


def test_assess_recorder_coverage_detects_insufficient_horizon(tmp_path: Path) -> None:
    recorder_root = tmp_path / "data" / "recorder"
    # max_ts 2000 does not cover required_end 1000 + HORIZON
    _write_csv(recorder_root / "2026-05-06" / "BTCUSDT_180.csv", [1000, 2000])

    nrr_rows = [{"symbol": "BTCUSDT", "ts_ms": 1000, "rid": "r1"}]
    cov = mod.assess_recorder_coverage(recorder_root, nrr_rows)
    assert cov["evaluated"] is True
    assert cov["coverage_sufficient"] is False
    assert cov["symbols"]["BTCUSDT"]["has_any_sufficient_timeframe"] is False


def test_main_dry_run_writes_no_freeze(tmp_path: Path, monkeypatch) -> None:
    logs = tmp_path / "logs"
    _write_jsonl(
        logs / "order_log_v1.jsonl",
        [{"event_type": "DECISION_INTENT_REJECTED", "nrr_code": "NRR-062",
            "symbol": "BTCUSDT", "ts_ms": 1000, "rid": "r1"}],
    )
    _write_jsonl(logs / "shadow_critical_event_journal_v1.jsonl", [])
    _write_jsonl(logs / "regime_confidence_audit_v1.jsonl", [])
    _write_jsonl(logs / "trade_lifecycle.jsonl", [])

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "capture_nrr062_fresh_cohort.py",
            "--dry-run",
            "--out-dir",
            "logs/frozen",
        ],
    )

    rc = mod.main()
    assert rc == 0
    frozen_dir = tmp_path / "logs" / "frozen"
    # dry-run path is reported but no capture directory should be created
    assert not any(frozen_dir.glob("nrr062_fresh_capture_*"))


def test_main_respects_min_nrr062_threshold(tmp_path: Path, monkeypatch) -> None:
    logs = tmp_path / "logs"
    _write_jsonl(
        logs / "order_log_v1.jsonl",
        [{"event_type": "DECISION_INTENT_REJECTED", "nrr_code": "NRR-062",
            "symbol": "BTCUSDT", "ts_ms": 1000, "rid": "r1"}],
    )
    _write_jsonl(logs / "shadow_critical_event_journal_v1.jsonl", [])
    _write_jsonl(logs / "regime_confidence_audit_v1.jsonl", [])
    _write_jsonl(logs / "trade_lifecycle.jsonl", [])

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "capture_nrr062_fresh_cohort.py",
            "--min-nrr062",
            "2",
            "--out-dir",
            "logs/frozen",
        ],
    )

    rc = mod.main()
    assert rc == 0
    frozen_dir = tmp_path / "logs" / "frozen"
    assert not any(frozen_dir.glob("nrr062_fresh_capture_*"))


def test_main_capture_path_is_under_logs_frozen(tmp_path: Path, monkeypatch) -> None:
    logs = tmp_path / "logs"
    _write_jsonl(
        logs / "order_log_v1.jsonl",
        [{"event_type": "DECISION_INTENT_REJECTED", "nrr_code": "NRR-062",
            "symbol": "BTCUSDT", "ts_ms": 1000, "rid": "r1"}],
    )
    _write_jsonl(logs / "shadow_critical_event_journal_v1.jsonl", [])
    _write_jsonl(logs / "regime_confidence_audit_v1.jsonl", [])
    _write_jsonl(logs / "trade_lifecycle.jsonl", [])

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "capture_nrr062_fresh_cohort.py",
            "--out-dir",
            "logs/frozen",
        ],
    )

    rc = mod.main()
    assert rc == 0
    captures = list(
        (tmp_path / "logs" / "frozen").glob("nrr062_fresh_capture_*"))
    assert captures, "expected capture dir under logs/frozen"
