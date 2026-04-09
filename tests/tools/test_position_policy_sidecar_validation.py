import json
from pathlib import Path

from tools.forensics.position_policy_sidecar_validation import build_report


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _mode_active_row(ts_ms: int) -> dict:
    return {
        "record_kind": "position_policy_sidecar",
        "event_type": "POSITION_POLICY_SIDECAR_MODE_ACTIVE",
        "ts_ms": ts_ms,
        "trace_id": f"pps:__DOMAIN__:{ts_ms}:1",
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


def _sidecar_row(
    *,
    ts_ms: int,
    symbol: str,
    event_type: str,
    trigger_event: str,
    suppression_reason: str | None = None,
    manage_state: str | None = None,
    portfolio_snapshot_status: str | None = None,
    portfolio_symbol_present: bool | None = None,
    features_fresh: bool = True,
    regime_fresh: bool = True,
    trace_id: str | None = None,
    soft_close_pressure: float | None = None,
) -> dict:
    position_snapshot = {
        "symbol": symbol,
        "manage_state": manage_state,
        "closing_position": False,
        "side": "BUY" if manage_state else "",
        "position_qty": "0.01" if manage_state else "",
        "entry_price": "100" if manage_state else "",
        "portfolio_position_amt": "0.01" if portfolio_snapshot_status == "present" else None,
        "portfolio_snapshot_status": portfolio_snapshot_status,
        "portfolio_symbol_present": portfolio_symbol_present,
        "mark_price": None,
        "portfolio_entry_price": "100" if portfolio_snapshot_status == "present" else None,
        "unrealized_pnl_usdt": None,
        "unrealized_pnl_pct": None,
        "position_open_ts": 1.0 if manage_state else 0.0,
    }
    row = {
        "record_kind": "position_policy_sidecar",
        "event_type": event_type,
        "trigger_event": trigger_event,
        "ts_ms": ts_ms,
        "trace_id": trace_id or f"pps:{symbol}:{ts_ms}:1",
        "symbol": symbol,
        "sidecar_version": "1.0.0",
        "mode": "shadow",
        "evaluation_mode": "phase1_recommendation_only",
        "reason_codes": [f"trigger:{trigger_event.lower()}"],
        "position_snapshot": position_snapshot,
        "feature_ref": {},
        "regime_ref": {},
        "freshness_snapshot": {
            "portfolio_fresh": True,
            "features_fresh": features_fresh,
            "regime_fresh": regime_fresh,
        },
    }
    if suppression_reason is not None:
        row["suppression_reason"] = suppression_reason
    if event_type in {
        "POSITION_POLICY_SIDECAR_SCORES",
        "POSITION_POLICY_SIDECAR_EVALUATED",
        "POSITION_POLICY_SIDECAR_RECOMMENDED",
    }:
        row["score_snapshot"] = {
            "soft_close_pressure": 0.25 if soft_close_pressure is None else soft_close_pressure
        }
    return row


def _fill_ingress_row(*, ts_ms: int, symbol: str, rid: str) -> dict:
    return {
        "record_kind": "execution_fill_ingress",
        "ts_ms": ts_ms,
        "symbol": symbol,
        "rid": rid,
        "fill_source": "trade_executed",
        "manage_state_before": "BRACKETS_PENDING",
        "manage_state_after": "BRACKETS_PENDING",
        "result": None,
    }


def _symbol_transition(report: dict, slice_index: int, symbol: str) -> dict:
    return next(
        item
        for item in report["restart_slices"][slice_index]["symbol_transition_history"]
        if item["symbol"] == symbol
    )


def _fill_ingress_summary_entry(report: dict, symbol: str) -> dict:
    return next(
        item
        for item in report["fill_ingress_symbol_transition_summary"]
        if item["symbol"] == symbol
    )


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


def test_build_report_segments_restart_slices_and_isolates_latest_slice(tmp_path: Path) -> None:
    trade_lifecycle_path = tmp_path / "logs" / "trade_lifecycle.jsonl"
    _write_jsonl(
        trade_lifecycle_path,
        [
            _mode_active_row(1000),
            _sidecar_row(
                ts_ms=1010,
                symbol="BTCUSDT",
                event_type="POSITION_POLICY_SIDECAR_EVALUATED",
                trigger_event="PORTFOLIO_STATE_UPDATED",
                manage_state="BRACKETS_PENDING",
                portfolio_snapshot_status="present",
                portfolio_symbol_present=True,
            ),
            _mode_active_row(2000),
            _sidecar_row(
                ts_ms=2010,
                symbol="ETHUSDT",
                event_type="POSITION_POLICY_SIDECAR_SUPPRESSED",
                trigger_event="PORTFOLIO_STATE_UPDATED",
                suppression_reason="features_snapshot_missing_or_stale",
                manage_state="BRACKETS_PENDING",
                portfolio_snapshot_status="symbol_absent",
                portfolio_symbol_present=False,
            ),
        ],
    )

    report = build_report(
        wal_glob=str(tmp_path / "ops" / "wal" / "*.jsonl"),
        order_log_path=tmp_path / "logs" / "order_log_v1.jsonl",
        trade_lifecycle_path=trade_lifecycle_path,
        overlap_window_ms=60_000,
    )

    assert len(report["restart_slices"]) == 2
    assert report["restart_slices"][0]["start_ts_ms"] == 1000
    assert report["restart_slices"][0]["event_type_counts"]["POSITION_POLICY_SIDECAR_EVALUATED"] == 1
    assert report["restart_slices"][1]["start_ts_ms"] == 2000
    assert report["restart_slices"][1]["event_type_counts"].get(
        "POSITION_POLICY_SIDECAR_EVALUATED", 0) == 0
    assert report["latest_slice_verdict"]["slice_start_ts_ms"] == 2000
    assert report["latest_slice_verdict"]["reached_evaluated"] is False


def test_build_report_classifies_fresh_candidates_and_carried_symbol_absent_state(tmp_path: Path) -> None:
    trade_lifecycle_path = tmp_path / "logs" / "trade_lifecycle.jsonl"
    _write_jsonl(
        trade_lifecycle_path,
        [
            _mode_active_row(1000),
            _fill_ingress_row(ts_ms=1010, symbol="SOLUSDT", rid="rid-sol-1"),
            _sidecar_row(
                ts_ms=1020,
                symbol="SOLUSDT",
                event_type="POSITION_POLICY_SIDECAR_SUPPRESSED",
                trigger_event="PORTFOLIO_STATE_UPDATED",
                suppression_reason="regime_snapshot_missing_or_stale",
                manage_state="BRACKETS_PENDING",
                portfolio_snapshot_status="present",
                portfolio_symbol_present=True,
            ),
            _sidecar_row(
                ts_ms=1030,
                symbol="BTCUSDT",
                event_type="POSITION_POLICY_SIDECAR_SUPPRESSED",
                trigger_event="PORTFOLIO_STATE_UPDATED",
                suppression_reason="features_snapshot_missing_or_stale",
                manage_state="BRACKETS_PENDING",
                portfolio_snapshot_status="symbol_absent",
                portfolio_symbol_present=False,
            ),
            _sidecar_row(
                ts_ms=1040,
                symbol="XRPUSDT",
                event_type="POSITION_POLICY_SIDECAR_SUPPRESSED",
                trigger_event="PORTFOLIO_STATE_UPDATED",
                suppression_reason="no_manage_flow_for_symbol",
                manage_state=None,
                portfolio_snapshot_status="symbol_absent",
                portfolio_symbol_present=False,
            ),
        ],
    )

    report = build_report(
        wal_glob=str(tmp_path / "ops" / "wal" / "*.jsonl"),
        order_log_path=tmp_path / "logs" / "order_log_v1.jsonl",
        trade_lifecycle_path=trade_lifecycle_path,
        overlap_window_ms=60_000,
    )

    classification = report["restart_slices"][0]["candidate_classification"]
    assert classification["fresh_portfolio_present_candidates"]["symbols"] == [
        "SOLUSDT"]
    assert classification["carried_local_lifecycle_symbol_absent"]["symbols"] == [
        "BTCUSDT"]
    assert classification["no_lifecycle_no_manage_flow"]["symbols"] == [
        "XRPUSDT"]
    assert classification["fresh_portfolio_present_candidates"][
        "dominant_suppression_reason"]["reason"] == "regime_snapshot_missing_or_stale"
    assert report["latest_slice_verdict"]["has_fresh_fill_open_candidate_proof"] is True
    assert report["latest_slice_verdict"]["fresh_portfolio_present_candidate_count"] == 1


def test_build_report_counts_execution_fill_ingress_per_slice(tmp_path: Path) -> None:
    trade_lifecycle_path = tmp_path / "logs" / "trade_lifecycle.jsonl"
    _write_jsonl(
        trade_lifecycle_path,
        [
            _mode_active_row(1000),
            _fill_ingress_row(ts_ms=1010, symbol="SOLUSDT", rid="rid-sol-1"),
            _mode_active_row(2000),
            _fill_ingress_row(ts_ms=2010, symbol="ETHUSDT", rid="rid-eth-1"),
            _fill_ingress_row(ts_ms=2020, symbol="ETHUSDT", rid="rid-eth-2"),
        ],
    )

    report = build_report(
        wal_glob=str(tmp_path / "ops" / "wal" / "*.jsonl"),
        order_log_path=tmp_path / "logs" / "order_log_v1.jsonl",
        trade_lifecycle_path=trade_lifecycle_path,
        overlap_window_ms=60_000,
    )

    assert report["restart_slices"][0]["execution_fill_ingress"]["count"] == 1
    assert report["restart_slices"][0]["execution_fill_ingress"]["count_by_symbol"]["SOLUSDT"] == 1
    assert report["restart_slices"][1]["execution_fill_ingress"]["count"] == 2
    assert report["restart_slices"][1]["execution_fill_ingress"]["count_by_symbol"]["ETHUSDT"] == 2
    assert report["policy_rows"]["fill_ingress_count"] == 3
    assert report["aggregate_summary"]["fill_ingress_row_count"] == 3


def test_build_report_latest_slice_verdict_marks_no_fresh_candidate_evidence(tmp_path: Path) -> None:
    trade_lifecycle_path = tmp_path / "logs" / "trade_lifecycle.jsonl"
    _write_jsonl(
        trade_lifecycle_path,
        [
            _mode_active_row(1000),
            _sidecar_row(
                ts_ms=1010,
                symbol="BTCUSDT",
                event_type="POSITION_POLICY_SIDECAR_EVALUATED",
                trigger_event="REGIME_DETECTED",
                manage_state="BRACKETS_PENDING",
                portfolio_snapshot_status="present",
                portfolio_symbol_present=True,
            ),
            _mode_active_row(2000),
            _sidecar_row(
                ts_ms=2010,
                symbol="BTCUSDT",
                event_type="POSITION_POLICY_SIDECAR_SUPPRESSED",
                trigger_event="PORTFOLIO_STATE_UPDATED",
                suppression_reason="features_snapshot_missing_or_stale",
                manage_state="BRACKETS_PENDING",
                portfolio_snapshot_status="symbol_absent",
                portfolio_symbol_present=False,
            ),
            _sidecar_row(
                ts_ms=2020,
                symbol="XRPUSDT",
                event_type="POSITION_POLICY_SIDECAR_SUPPRESSED",
                trigger_event="PORTFOLIO_STATE_UPDATED",
                suppression_reason="no_manage_flow_for_symbol",
                manage_state=None,
                portfolio_snapshot_status="symbol_absent",
                portfolio_symbol_present=False,
            ),
        ],
    )

    report = build_report(
        wal_glob=str(tmp_path / "ops" / "wal" / "*.jsonl"),
        order_log_path=tmp_path / "logs" / "order_log_v1.jsonl",
        trade_lifecycle_path=trade_lifecycle_path,
        overlap_window_ms=60_000,
    )

    latest_slice = report["restart_slices"][1]
    assert latest_slice["candidate_classification"]["carried_local_lifecycle_symbol_absent"]["symbols"] == [
        "BTCUSDT"]
    assert latest_slice["candidate_classification"]["fresh_portfolio_present_candidates"]["symbol_count"] == 0
    assert report["latest_slice_verdict"]["non_evaluation_category"] == "no_fresh_candidate_evidence"
    assert report["latest_slice_verdict"]["non_evaluation_detail"] == "carried_local_lifecycle_symbol_absent_dominant"
    assert report["latest_slice_verdict"]["has_fresh_fill_open_candidate_proof"] is False


def test_build_report_preserves_within_slice_portfolio_present_history_when_latest_row_degrades(tmp_path: Path) -> None:
    trade_lifecycle_path = tmp_path / "logs" / "trade_lifecycle.jsonl"
    _write_jsonl(
        trade_lifecycle_path,
        [
            _mode_active_row(1000),
            _fill_ingress_row(ts_ms=1010, symbol="SOLUSDT", rid="rid-sol-1"),
            _sidecar_row(
                ts_ms=1020,
                symbol="SOLUSDT",
                event_type="POSITION_POLICY_SIDECAR_SUPPRESSED",
                trigger_event="PORTFOLIO_STATE_UPDATED",
                suppression_reason="regime_snapshot_missing_or_stale",
                manage_state="BRACKETS_PENDING",
                portfolio_snapshot_status="present",
                portfolio_symbol_present=True,
                features_fresh=True,
                regime_fresh=False,
            ),
            _sidecar_row(
                ts_ms=1030,
                symbol="SOLUSDT",
                event_type="POSITION_POLICY_SIDECAR_SUPPRESSED",
                trigger_event="FEATURES_CALCULATED",
                suppression_reason="features_snapshot_missing_or_stale",
                manage_state="BRACKETS_PENDING",
                portfolio_snapshot_status="symbol_absent",
                portfolio_symbol_present=False,
                features_fresh=False,
                regime_fresh=True,
            ),
        ],
    )

    report = build_report(
        wal_glob=str(tmp_path / "ops" / "wal" / "*.jsonl"),
        order_log_path=tmp_path / "logs" / "order_log_v1.jsonl",
        trade_lifecycle_path=trade_lifecycle_path,
        overlap_window_ms=60_000,
    )

    latest_slice = report["restart_slices"][0]
    assert latest_slice["candidate_classification"]["carried_local_lifecycle_symbol_absent"]["symbols"] == [
        "SOLUSDT"]

    transition = _symbol_transition(report, 0, "SOLUSDT")
    assert transition["had_slice_fill_ingress"] is True
    assert transition["ever_portfolio_present"] is True
    assert transition["ever_portfolio_symbol_present_true"] is True
    assert transition["ever_portfolio_present_after_fill"] is True
    assert transition["ever_portfolio_present_candidate_after_fill"] is True
    assert transition["ended_symbol_absent"] is True
    assert transition["latest_classification_bucket"] == "carried_local_lifecycle_symbol_absent"
    assert transition["first_fill_ingress_ts_ms"] == 1010
    assert transition["first_portfolio_present_ts_ms"] == 1020
    assert transition["latest_policy_row_ts_ms"] == 1030
    assert transition["first_policy_row_after_fill_ingress"]["portfolio_snapshot_status"] == "present"
    assert transition["first_blocker_after_fill"] == "regime_snapshot_missing_or_stale"
    assert transition["latest_blocker"] == "features_snapshot_missing_or_stale"
    assert transition["blocker_reason_changed_after_fill"] is True
    assert transition["blocker_reason_progression_after_fill"] == [
        "regime_snapshot_missing_or_stale",
        "features_snapshot_missing_or_stale",
    ]
    assert transition["operator_verdict"] == "became_candidate_but_never_evaluated"

    summary = _fill_ingress_summary_entry(report, "SOLUSDT")
    assert summary["ever_portfolio_present"] is True
    assert summary["latest_classification_bucket"] == "carried_local_lifecycle_symbol_absent"
    assert summary["operator_verdict"] == "became_candidate_but_never_evaluated"


def test_build_report_fill_ingress_summary_marks_never_became_candidate(tmp_path: Path) -> None:
    trade_lifecycle_path = tmp_path / "logs" / "trade_lifecycle.jsonl"
    _write_jsonl(
        trade_lifecycle_path,
        [
            _mode_active_row(2000),
            _fill_ingress_row(ts_ms=2010, symbol="BTCUSDT", rid="rid-btc-1"),
            _sidecar_row(
                ts_ms=2020,
                symbol="BTCUSDT",
                event_type="POSITION_POLICY_SIDECAR_SUPPRESSED",
                trigger_event="PORTFOLIO_STATE_UPDATED",
                suppression_reason="features_snapshot_missing_or_stale",
                manage_state="BRACKETS_PENDING",
                portfolio_snapshot_status="symbol_absent",
                portfolio_symbol_present=False,
                features_fresh=False,
                regime_fresh=True,
            ),
        ],
    )

    report = build_report(
        wal_glob=str(tmp_path / "ops" / "wal" / "*.jsonl"),
        order_log_path=tmp_path / "logs" / "order_log_v1.jsonl",
        trade_lifecycle_path=trade_lifecycle_path,
        overlap_window_ms=60_000,
    )

    summary = _fill_ingress_summary_entry(report, "BTCUSDT")
    assert summary["had_fill_ingress"] is True
    assert summary["ever_portfolio_present"] is False
    assert summary["ever_features_fresh"] is False
    assert summary["ever_regime_fresh"] is True
    assert summary["ever_evaluated"] is False
    assert summary["first_blocker_after_fill"] == "features_snapshot_missing_or_stale"
    assert summary["latest_blocker"] == "features_snapshot_missing_or_stale"
    assert summary["operator_verdict"] == "never_became_candidate"

    verdict = report["latest_slice_verdict"]
    assert verdict["has_fill_ingress_evidence"] is True
    assert verdict["has_fresh_fill_open_candidate_proof"] is False
    assert verdict["fill_ingress_transition_verdict"] == "no_portfolio_present_candidate_proven"
    assert verdict["non_evaluation_category"] == "no_fresh_candidate_evidence"
    assert verdict["non_evaluation_detail"] == "fill_ingress_never_reached_portfolio_present_candidate"


def test_build_report_fill_ingress_summary_marks_evaluated_then_decayed(tmp_path: Path) -> None:
    trade_lifecycle_path = tmp_path / "logs" / "trade_lifecycle.jsonl"
    _write_jsonl(
        trade_lifecycle_path,
        [
            _mode_active_row(3000),
            _fill_ingress_row(ts_ms=3010, symbol="ETHUSDT", rid="rid-eth-1"),
            _sidecar_row(
                ts_ms=3020,
                symbol="ETHUSDT",
                event_type="POSITION_POLICY_SIDECAR_EVALUATED",
                trigger_event="PORTFOLIO_STATE_UPDATED",
                manage_state="BRACKETS_PENDING",
                portfolio_snapshot_status="present",
                portfolio_symbol_present=True,
                features_fresh=True,
                regime_fresh=True,
            ),
            _sidecar_row(
                ts_ms=3030,
                symbol="ETHUSDT",
                event_type="POSITION_POLICY_SIDECAR_SUPPRESSED",
                trigger_event="PORTFOLIO_STATE_UPDATED",
                suppression_reason="portfolio_snapshot_missing_or_stale",
                manage_state="BRACKETS_PENDING",
                portfolio_snapshot_status="symbol_absent",
                portfolio_symbol_present=False,
                features_fresh=True,
                regime_fresh=True,
            ),
        ],
    )

    report = build_report(
        wal_glob=str(tmp_path / "ops" / "wal" / "*.jsonl"),
        order_log_path=tmp_path / "logs" / "order_log_v1.jsonl",
        trade_lifecycle_path=trade_lifecycle_path,
        overlap_window_ms=60_000,
    )

    transition = _symbol_transition(report, 0, "ETHUSDT")
    assert transition["ever_evaluated"] is True
    assert transition["ever_evaluated_after_fill"] is True
    assert transition["ended_symbol_absent"] is True
    assert transition["first_evaluated_after_fill_ts_ms"] == 3020
    assert transition["latest_blocker"] == "portfolio_snapshot_missing_or_stale"
    assert transition["operator_verdict"] == "evaluated_then_decayed"

    summary = _fill_ingress_summary_entry(report, "ETHUSDT")
    assert summary["ever_evaluated"] is True
    assert summary["latest_classification_bucket"] == "carried_local_lifecycle_symbol_absent"
    assert summary["operator_verdict"] == "evaluated_then_decayed"

    verdict = report["latest_slice_verdict"]
    assert verdict["reached_evaluated"] is True
    assert verdict["fill_ingress_transition_verdict"] == "candidate_existed_then_degraded"
    assert verdict["fill_ingress_transition_verdict_counts"]["evaluated_then_decayed"] == 1


def test_build_report_recommendation_truth_marks_threshold_non_attainment(tmp_path: Path) -> None:
    trade_lifecycle_path = tmp_path / "logs" / "trade_lifecycle.jsonl"
    _write_jsonl(
        trade_lifecycle_path,
        [
            _mode_active_row(1000),
            _sidecar_row(
                ts_ms=1010,
                symbol="BTCUSDT",
                event_type="POSITION_POLICY_SIDECAR_EVALUATED",
                trigger_event="REGIME_DETECTED",
                manage_state="BRACKETS_PENDING",
                portfolio_snapshot_status="present",
                portfolio_symbol_present=True,
                soft_close_pressure=0.30,
            ),
        ],
    )

    report = build_report(
        wal_glob=str(tmp_path / "ops" / "wal" / "*.jsonl"),
        order_log_path=tmp_path / "logs" / "order_log_v1.jsonl",
        trade_lifecycle_path=trade_lifecycle_path,
        overlap_window_ms=60_000,
        recommend_threshold=0.70,
    )

    truth = report["recommendation_truth"]
    assert truth["classification"] == "truthful_threshold_non_attainment"
    assert truth["truthful_zero_recommendation"] is True
    assert truth["recommendation_count"] == 0
    assert truth["threshold_crossing_evaluated_count"] == 0
    assert truth["max_evaluated_soft_close_pressure"] == 0.30
    assert truth["by_symbol"]["BTCUSDT"]["max_evaluated_soft_close_pressure"] == 0.30
    assert report["aggregate_summary"]["recommendation_truth_classification"] == "truthful_threshold_non_attainment"
    assert report["latest_slice_verdict"]["recommendation_truth_classification"] == "truthful_threshold_non_attainment"
    assert report["latest_slice_verdict"]["max_evaluated_soft_close_pressure"] == 0.30


def test_build_report_recommendation_truth_detects_threshold_crossing_without_recommendation(tmp_path: Path) -> None:
    trade_lifecycle_path = tmp_path / "logs" / "trade_lifecycle.jsonl"
    trace_id = "pps:ETHUSDT:2010:1"
    _write_jsonl(
        trade_lifecycle_path,
        [
            _mode_active_row(2000),
            _sidecar_row(
                ts_ms=2010,
                symbol="ETHUSDT",
                event_type="POSITION_POLICY_SIDECAR_EVALUATED",
                trigger_event="REGIME_DETECTED",
                manage_state="BRACKETS_PENDING",
                portfolio_snapshot_status="present",
                portfolio_symbol_present=True,
                trace_id=trace_id,
                soft_close_pressure=0.80,
            ),
        ],
    )

    report = build_report(
        wal_glob=str(tmp_path / "ops" / "wal" / "*.jsonl"),
        order_log_path=tmp_path / "logs" / "order_log_v1.jsonl",
        trade_lifecycle_path=trade_lifecycle_path,
        overlap_window_ms=60_000,
        recommend_threshold=0.70,
    )

    truth = report["recommendation_truth"]
    assert truth["classification"] == "recommendation_emission_gap"
    assert truth["threshold_crossing_evaluated_count"] == 1
    assert truth["missing_recommendation_after_threshold_crossing_count"] == 1
    assert truth["missing_recommendation_after_threshold_crossing_samples"][0]["trace_id"] == trace_id
    assert report["latest_slice_verdict"]["recommendation_truth_classification"] == "recommendation_emission_gap"
    assert report["latest_slice_verdict"]["threshold_crossing_evaluated_count"] == 1


def test_build_report_counts_matched_recommendations_when_recommendation_present(tmp_path: Path) -> None:
    trade_lifecycle_path = tmp_path / "logs" / "trade_lifecycle.jsonl"
    order_log_path = tmp_path / "logs" / "order_log_v1.jsonl"
    trace_id = "pps:BTCUSDT:3010:1"
    _write_jsonl(
        trade_lifecycle_path,
        [
            _mode_active_row(3000),
            _sidecar_row(
                ts_ms=3010,
                symbol="BTCUSDT",
                event_type="POSITION_POLICY_SIDECAR_EVALUATED",
                trigger_event="REGIME_DETECTED",
                manage_state="BRACKETS_PENDING",
                portfolio_snapshot_status="present",
                portfolio_symbol_present=True,
                trace_id=trace_id,
                soft_close_pressure=0.85,
            ),
            _sidecar_row(
                ts_ms=3011,
                symbol="BTCUSDT",
                event_type="POSITION_POLICY_SIDECAR_RECOMMENDED",
                trigger_event="REGIME_DETECTED",
                manage_state="BRACKETS_PENDING",
                portfolio_snapshot_status="present",
                portfolio_symbol_present=True,
                trace_id=trace_id,
                soft_close_pressure=0.85,
            ),
        ],
    )
    _write_jsonl(
        order_log_path,
        [
            {
                "event_type": "ORDER_FILLED",
                "symbol": "BTCUSDT",
                "timestamp": 3020,
                "rid": "rid-close-1",
            }
        ],
    )

    report = build_report(
        wal_glob=str(tmp_path / "ops" / "wal" / "*.jsonl"),
        order_log_path=order_log_path,
        trade_lifecycle_path=trade_lifecycle_path,
        overlap_window_ms=60_000,
        recommend_threshold=0.70,
    )

    assert report["overlap"]["matched_recommendations"] == 1
    truth = report["recommendation_truth"]
    assert truth["classification"] == "recommendations_matched"
    assert truth["recommendation_count"] == 1
    assert truth["threshold_crossing_evaluated_count"] == 1
    assert truth["unmatched_recommendation_count"] == 0
