import json
from pathlib import Path

from tools.forensics.position_policy_sidecar_validation import build_report


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_build_report_counts_ingress_events_and_flags_missing_bootstrap(tmp_path: Path) -> None:
    wal_path = tmp_path / "ops" / "wal" / "2026-04-03.jsonl"
    _write_jsonl(
        wal_path,
        [
            {"verb": "TRADE_EXECUTED", "pld": {"symbol": "BTCUSDT"}},
            {"verb": "ORDER_STATE_CHANGED", "pld": {"symbol": "BTCUSDT"}},
            {"event_type": "EVT:REGIME_DETECTED", "pld": {"symbol": "BTCUSDT"}},
        ],
    )

    report = build_report(
        wal_glob=str(tmp_path / "ops" / "wal" / "*.jsonl"),
        order_log_path=tmp_path / "logs" / "order_log_v1.jsonl",
        trade_lifecycle_path=tmp_path / "logs" / "trade_lifecycle.jsonl",
        overlap_window_ms=60_000,
    )

    assert report["wal"]["ingress_event_counts"]["TRADE_EXECUTED"] == 1
    assert report["wal"]["ingress_event_counts"]["ORDER_STATE_CHANGED"] == 1
    assert report["wal"]["ingress_event_counts"]["REGIME_DETECTED"] == 1
    assert report["bootstrap"]["mode_active_present"] is False
    assert report["bootstrap"]["signal"] == "missing_mode_active_row"
    assert report["paths"]["trade_lifecycle_exists"] is False


def test_build_report_detects_mode_active_bootstrap_row(tmp_path: Path) -> None:
    trade_lifecycle_path = tmp_path / "logs" / "trade_lifecycle.jsonl"
    _write_jsonl(
        trade_lifecycle_path,
        [
            {
                "record_kind": "position_policy_sidecar",
                "event_type": "POSITION_POLICY_SIDECAR_MODE_ACTIVE",
                "ts_ms": 1,
                "trace_id": "pps:__DOMAIN__:1:1",
                "symbol": "__DOMAIN__",
                "sidecar_version": "1.0.0",
                "mode": "shadow",
                "evaluation_mode": "phase1_recommendation_only",
                "reason_codes": ["sidecar_initialized"],
                "position_snapshot": {},
                "feature_ref": {},
                "regime_ref": {},
                "freshness_snapshot": {},
            }
        ],
    )

    report = build_report(
        wal_glob=str(tmp_path / "ops" / "wal" / "*.jsonl"),
        order_log_path=tmp_path / "logs" / "order_log_v1.jsonl",
        trade_lifecycle_path=trade_lifecycle_path,
        overlap_window_ms=60_000,
    )

    assert report["policy_rows"]["event_type_counts"]["POSITION_POLICY_SIDECAR_MODE_ACTIVE"] == 1
    assert report["bootstrap"]["mode_active_count"] == 1
    assert report["bootstrap"]["mode_active_present"] is True
    assert report["bootstrap"]["signal"] is None
    assert report["paths"]["trade_lifecycle_exists"] is True


def test_build_report_counts_trigger_events_from_policy_rows(tmp_path: Path) -> None:
    trade_lifecycle_path = tmp_path / "logs" / "trade_lifecycle.jsonl"
    _write_jsonl(
        trade_lifecycle_path,
        [
            {
                "record_kind": "position_policy_sidecar",
                "event_type": "POSITION_POLICY_SIDECAR_SUPPRESSED",
                "trigger_event": "REGIME_DETECTED",
                "ts_ms": 2,
                "trace_id": "pps:BTCUSDT:2:1",
                "symbol": "BTCUSDT",
                "sidecar_version": "1.0.0",
                "mode": "shadow",
                "evaluation_mode": "phase1_recommendation_only",
                "reason_codes": ["trigger:regime_detected", "startup_grace_active"],
                "position_snapshot": {},
                "feature_ref": {},
                "regime_ref": {"ts_ms": 1, "update_count": 1},
                "freshness_snapshot": {},
                "suppression_reason": "startup_grace_active",
            }
        ],
    )

    report = build_report(
        wal_glob=str(tmp_path / "ops" / "wal" / "*.jsonl"),
        order_log_path=tmp_path / "logs" / "order_log_v1.jsonl",
        trade_lifecycle_path=trade_lifecycle_path,
        overlap_window_ms=60_000,
    )

    assert report["policy_rows"]["observed_trigger_event_counts"]["REGIME_DETECTED"] == 1
