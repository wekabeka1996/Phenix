import pytest
import time
from apps.reference.domains.execution_position.telemetry.drift_monitor import compute_drift, ConfusionMatrix, Mismatch, DriftReport, aggregate_drift_metrics

def test_confusion_matrix_drift_pct():
    """Verify drift_pct calculation."""
    cm = ConfusionMatrix(tp=10, fp=2, fn=2, tn=6)
    assert cm.drift_pct == 20.0 # (2+2)/20 * 100
    assert cm.accuracy == 80.0

def test_confusion_matrix_empty():
    """Handle empty matrix."""
    cm = ConfusionMatrix()
    assert cm.drift_pct == 0.0
    assert cm.accuracy == 0.0

def test_compute_drift_perfect_match():
    """TP: Decision matched by Event."""
    decisions = [{"rid": "r1", "verb": "OPEN", "pld": {"symbol": "BTCUSDT"}, "timestamp": 1000}]
    events = [{"rid": "r1", "verb": "FILL", "pld": {"symbol": "BTCUSDT"}, "timestamp": 1000.5}]
    
    report = compute_drift(decisions, events, time_window_sec=1.0)
    assert report.confusion.tp == 1
    assert report.confusion.fp == 0
    assert report.confusion.fn == 0
    assert len(report.mismatches) == 0

def test_compute_drift_false_positive():
    """FP: Decision without matching event."""
    # Verb mismatch or time window mismatch
    decisions = [{"rid": "r1", "verb": "OPEN", "pld": {"symbol": "BTCUSDT"}, "timestamp": 1000}]
    events = [{"rid": "r1", "verb": "CANCELLED", "pld": {"symbol": "BTCUSDT"}, "timestamp": 1000}]
    
    report = compute_drift(decisions, events, time_window_sec=1.0)
    assert report.confusion.fp == 1
    assert report.confusion.tp == 0
    # The event becomes a False Negative because it wasn't matched
    assert report.confusion.fn == 1

def test_compute_drift_false_negative():
    """FN: Event without matching decision."""
    decisions = []
    events = [{"rid": "r1", "verb": "FILL", "pld": {"symbol": "BTCUSDT"}, "timestamp": 1000}]
    
    report = compute_drift(decisions, events, time_window_sec=1.0)
    assert report.confusion.fn == 1
    assert report.mismatches[0].type == "FN"

def test_compute_drift_close_reduce_only():
    """Match CLOSE decision with reduceOnly FILL."""
    decisions = [{"rid": "r1", "verb": "CLOSE", "pld": {"symbol": "BTCUSDT"}, "timestamp": 1000}]
    events = [{"rid": "r1", "verb": "FILL", "pld": {"symbol": "BTCUSDT", "reduceOnly": True}, "timestamp": 1000}]
    
    report = compute_drift(decisions, events, time_window_sec=1.0)
    assert report.confusion.tp == 1

def test_compute_drift_close_not_reduce_only():
    """CLOSE decision should NOT match non-reduceOnly FILL."""
    decisions = [{"rid": "r1", "verb": "CLOSE", "pld": {"symbol": "BTCUSDT"}, "timestamp": 1000}]
    events = [{"rid": "r1", "verb": "FILL", "pld": {"symbol": "BTCUSDT", "reduceOnly": False}, "timestamp": 1000}]
    
    report = compute_drift(decisions, events, time_window_sec=1.0)
    assert report.confusion.fp == 1 # Decision not matched
    assert report.confusion.tp == 0

def test_aggregate_drift_metrics():
    """Verify aggregation of multiple reports."""
    r1 = DriftReport(confusion=ConfusionMatrix(tp=1, fp=1))
    r2 = DriftReport(confusion=ConfusionMatrix(tp=2, fn=1))
    
    summary = aggregate_drift_metrics([r1, r2])
    assert summary["confusion_tp_total"] == 3
    assert summary["confusion_fp_total"] == 1
    assert summary["confusion_fn_total"] == 1
    # drift_pct_last should be from r2: (0+1)/3 * 100 = 33.33
    assert summary["drift_pct_last"] == round(33.33, 2)

def test_aggregate_drift_metrics_empty():
    """Handle empty list of reports."""
    summary = aggregate_drift_metrics([])
    assert summary["confusion_tp_total"] == 0
    assert summary["drift_pct_last"] == 0.0
