import time
from apps.reference.domains.execution_position.observability.drift_monitor import (
    compute_drift,
    aggregate_drift_metrics,
)


def test_compute_drift_tp_and_fn_and_fp():
    now = time.time()
    # Decision with matching event -> TP
    decisions = [
        {"rid": "r1", "verb": "OPEN", "pld": {"symbol": "ETHUSDT"}, "timestamp": now}
    ]
    events = [
        {
            "rid": "r1",
            "verb": "ORDER_PLACED",
            "pld": {"symbol": "ETHUSDT"},
            "timestamp": now,
        }
    ]

    report = compute_drift(decisions, events, time_window_sec=5)
    assert report.confusion.tp == 1
    assert report.confusion.fp == 0
    assert report.confusion.fn == 0

    # Decision without event -> FP
    decisions2 = [
        {"rid": "r2", "verb": "OPEN", "pld": {"symbol": "FOO"}, "timestamp": now}
    ]
    events2 = []
    report2 = compute_drift(decisions2, events2, time_window_sec=5)
    assert report2.confusion.fp == 1

    # Event without decision -> FN
    decisions3 = []
    events3 = [
        {
            "rid": "r3",
            "verb": "ORDER_PLACED",
            "pld": {"symbol": "BAR"},
            "timestamp": now,
        }
    ]
    report3 = compute_drift(decisions3, events3, time_window_sec=5)
    assert report3.confusion.fn == 1


def test_aggregate_drift_metrics():
    now = time.time()
    d1 = compute_drift(
        [{"rid": "r1", "verb": "OPEN", "pld": {"symbol": "A"}, "timestamp": now}],
        [
            {
                "rid": "r1",
                "verb": "ORDER_PLACED",
                "pld": {"symbol": "A"},
                "timestamp": now,
            }
        ],
        time_window_sec=5,
    )

    agg = aggregate_drift_metrics([d1])
    assert agg["confusion_tp_total"] == 1
    assert isinstance(agg["drift_pct_last"], float)
