"""
Unit tests for drift_monitor (FSMP-P1-T03).

Coverage: perfect match, only decisions, only events, partial overlap.
"""

import sys
from pathlib import Path

# Add vfoundation to path
sys.path.insert(0, str(Path(__file__).parent.parent / "vfoundation"))

from apps.reference.domains.execution_position.drift_monitor import (
    compute_drift,
    aggregate_drift_metrics,
    ConfusionMatrix,
    DriftReport,
    Mismatch,
)


def test_perfect_match_zero_drift():
    """Test perfect match: all decisions matched by events → drift=0."""
    decisions = [
        {
            "op": "DEC",
            "verb": "OPEN",
            "rid": "r1",
            "pld": {"symbol": "BTCUSDT"},
            "timestamp": 1000.0,
        },
        {
            "op": "DEC",
            "verb": "CLOSE",
            "rid": "r2",
            "pld": {"symbol": "ETHUSDT"},
            "timestamp": 2000.0,
        },
    ]

    events = [
        {
            "op": "EVT",
            "verb": "ORDER_PLACED",
            "rid": "r1",
            "pld": {"symbol": "BTCUSDT"},
            "timestamp": 1000.1,  # Within 1s window
        },
        {
            "op": "EVT",
            "verb": "CANCELLED",
            "rid": "r2",
            "pld": {"symbol": "ETHUSDT"},
            "timestamp": 2000.2,
        },
    ]

    report = compute_drift(decisions, events)

    assert report.confusion.tp == 2
    assert report.confusion.fp == 0
    assert report.confusion.fn == 0
    assert report.confusion.drift_pct == 0.0
    assert report.confusion.accuracy == 100.0
    assert len(report.mismatches) == 0


def test_only_decisions_no_events():
    """Test only decisions, no events → all FP."""
    decisions = [
        {
            "op": "DEC",
            "verb": "OPEN",
            "rid": "r1",
            "pld": {"symbol": "BTCUSDT"},
            "timestamp": 1000.0,
        },
        {
            "op": "DEC",
            "verb": "CLOSE",
            "rid": "r2",
            "pld": {"symbol": "ETHUSDT"},
            "timestamp": 2000.0,
        },
    ]

    events = []

    report = compute_drift(decisions, events)

    assert report.confusion.tp == 0
    assert report.confusion.fp == 2
    assert report.confusion.fn == 0
    assert report.confusion.drift_pct == 100.0  # (2+0)/(0+2+0+0) = 100%
    assert len(report.mismatches) == 2
    assert all(m.type == "FP" for m in report.mismatches)


def test_only_events_no_decisions():
    """Test only events, no decisions → all FN."""
    decisions = []

    events = [
        {
            "op": "EVT",
            "verb": "ORDER_PLACED",
            "rid": "r1",
            "pld": {"symbol": "BTCUSDT"},
            "timestamp": 1000.0,
        },
        {
            "op": "EVT",
            "verb": "FILL",
            "rid": "r2",
            "pld": {"symbol": "ETHUSDT"},
            "timestamp": 2000.0,
        },
    ]

    report = compute_drift(decisions, events)

    assert report.confusion.tp == 0
    assert report.confusion.fp == 0
    assert report.confusion.fn == 2
    assert report.confusion.drift_pct == 100.0  # (0+2)/(0+0+2+0) = 100%
    assert len(report.mismatches) == 2
    assert all(m.type == "FN" for m in report.mismatches)


def test_partial_overlap_mixed_drift():
    """Test partial overlap: 1 TP, 1 FP, 1 FN."""
    decisions = [
        {
            "op": "DEC",
            "verb": "OPEN",
            "rid": "r1",
            "pld": {"symbol": "BTCUSDT"},
            "timestamp": 1000.0,
        },
        {
            "op": "DEC",
            "verb": "CLOSE",
            "rid": "r2",
            "pld": {"symbol": "ETHUSDT"},
            "timestamp": 2000.0,
        },
    ]

    events = [
        {
            "op": "EVT",
            "verb": "ORDER_PLACED",
            "rid": "r1",
            "pld": {"symbol": "BTCUSDT"},
            "timestamp": 1000.1,  # Matches DEC r1
        },
        {
            "op": "EVT",
            "verb": "FILL",
            "rid": "r3",
            "pld": {"symbol": "SOLUSDT"},
            "timestamp": 3000.0,  # No matching DEC
        },
    ]

    report = compute_drift(decisions, events)

    assert report.confusion.tp == 1  # r1 matched
    assert report.confusion.fp == 1  # r2 DEC:CLOSE without event
    assert report.confusion.fn == 1  # r3 EVT:FILL without decision

    # drift = (1 FP + 1 FN) / (1 TP + 1 FP + 1 FN + 0 TN) = 2/3 = 66.67%
    assert 66.0 <= report.confusion.drift_pct <= 67.0

    assert len(report.mismatches) == 2  # 1 FP + 1 FN


def test_time_window_outside_match():
    """Test decisions/events outside time window → no match."""
    decisions = [
        {
            "op": "DEC",
            "verb": "OPEN",
            "rid": "r1",
            "pld": {"symbol": "BTCUSDT"},
            "timestamp": 1000.0,
        },
    ]

    events = [
        {
            "op": "EVT",
            "verb": "ORDER_PLACED",
            "rid": "r1",
            "pld": {"symbol": "BTCUSDT"},
            "timestamp": 1002.0,  # 2s later, outside 1s window
        },
    ]

    report = compute_drift(decisions, events, time_window_sec=1.0)

    assert report.confusion.tp == 0
    assert report.confusion.fp == 1  # DEC without match
    assert report.confusion.fn == 1  # EVT without match


def test_aggregate_drift_metrics():
    """Test aggregation of multiple drift reports."""
    report1 = DriftReport(
        confusion=ConfusionMatrix(tp=10, fp=2, fn=1, tn=0),
        records_processed=13,
    )

    report2 = DriftReport(
        confusion=ConfusionMatrix(tp=8, fp=3, fn=2, tn=0),
        records_processed=13,
    )

    metrics = aggregate_drift_metrics([report1, report2])

    assert metrics["confusion_tp_total"] == 18
    assert metrics["confusion_fp_total"] == 5
    assert metrics["confusion_fn_total"] == 3
    assert metrics["confusion_tn_total"] == 0

    # drift_pct_last should be from report2
    # report2: (3+2)/(8+3+2+0) = 5/13 = 38.46%
    assert 38.0 <= metrics["drift_pct_last"] <= 39.0


def test_confusion_matrix_edge_cases():
    """Test ConfusionMatrix edge cases."""
    # Empty matrix
    cm = ConfusionMatrix()
    assert cm.drift_pct == 0.0
    assert cm.accuracy == 0.0

    # Only TP
    cm = ConfusionMatrix(tp=10)
    assert cm.drift_pct == 0.0
    assert cm.accuracy == 100.0

    # Only FP
    cm = ConfusionMatrix(fp=5)
    assert cm.drift_pct == 100.0
    assert cm.accuracy == 0.0


def test_mismatch_serialization():
    """Test Mismatch to_dict serialization."""
    mismatch = Mismatch(
        rid="r1",
        symbol="BTCUSDT",
        type="FP",
        decision_verb="OPEN",
        timestamp=1234.5,
    )

    data = mismatch.to_dict()

    assert data["rid"] == "r1"
    assert data["symbol"] == "BTCUSDT"
    assert data["type"] == "FP"
    assert data["decision_verb"] == "OPEN"
    assert data["event_verb"] is None


def test_drift_report_limits_mismatches():
    """Test DriftReport limits mismatches to 5 in to_dict."""
    mismatches = [Mismatch(rid=f"r{i}", symbol="BTC", type="FP") for i in range(10)]

    report = DriftReport(
        confusion=ConfusionMatrix(fp=10),
        mismatches=mismatches,
    )

    data = report.to_dict()

    assert len(data["mismatches"]) == 5  # Limited to 5
    assert data["confusion"]["fp"] == 10  # Full count preserved


def test_close_decision_with_reduce_only_fill():
    """Test DEC:CLOSE matches FILL with reduceOnly=True but not reduceOnly=False."""
    decisions = [
        {
            "op": "DEC",
            "verb": "CLOSE",
            "rid": "r1",
            "pld": {"symbol": "BTCUSDT"},
            "timestamp": 1000.0,
        },
    ]

    events = [
        {
            "op": "EVT",
            "verb": "FILL",
            "rid": "r1",
            "pld": {"symbol": "BTCUSDT", "reduceOnly": False},  # Not a position closure
            "timestamp": 1000.1,
        },
        {
            "op": "EVT",
            "verb": "FILL",
            "rid": "r1",
            "pld": {"symbol": "BTCUSDT", "reduceOnly": True},  # Valid position closure
            "timestamp": 1000.2,
        },
    ]

    report = compute_drift(decisions, events)

    # DEC:CLOSE should match the reduceOnly=True FILL, not the reduceOnly=False one
    assert report.confusion.tp == 1
    assert report.confusion.fp == 0
    assert report.confusion.fn == 1  # The reduceOnly=False FILL is unmatched
    assert len(report.mismatches) == 1
    assert report.mismatches[0].type == "FN"


def test_close_decision_with_cancelled():
    """Test DEC:CLOSE matches CANCELLED events."""
    decisions = [
        {
            "op": "DEC",
            "verb": "CLOSE",
            "rid": "r1",
            "pld": {"symbol": "BTCUSDT"},
            "timestamp": 1000.0,
        },
    ]

    events = [
        {
            "op": "EVT",
            "verb": "CANCELLED",
            "rid": "r1",
            "pld": {"symbol": "BTCUSDT"},
            "timestamp": 1000.1,
        },
    ]

    report = compute_drift(decisions, events)

    assert report.confusion.tp == 1
    assert report.confusion.fp == 0
    assert report.confusion.fn == 0
    assert len(report.mismatches) == 0
