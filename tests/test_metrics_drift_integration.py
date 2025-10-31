"""
Tests for drift metrics integration in /metrics endpoint.
"""

import pytest
import sys
from pathlib import Path

# Add vfoundation to path
sys.path.insert(0, str(Path(__file__).parent.parent / "vfoundation"))

from vfoundation.obs.debug_api import (
    metrics,
    add_drift_report,
    _drift_reports,
    _drift_lock,
)
from apps.reference.domains.execution_position.drift_monitor import (
    ConfusionMatrix,
    DriftReport,
)


@pytest.fixture(autouse=True)
def clear_drift_reports():
    """Clear drift reports before each test"""
    with _drift_lock:
        _drift_reports.clear()
    yield
    with _drift_lock:
        _drift_reports.clear()


def test_metrics_contains_drift_fields_when_no_reports():
    """Test /metrics returns zero drift metrics when no reports exist"""
    result = metrics()

    # All drift fields should be present
    assert "confusion_tp_total" in result
    assert "confusion_fp_total" in result
    assert "confusion_fn_total" in result
    assert "confusion_tn_total" in result
    assert "drift_pct_last" in result
    assert "accuracy_last" in result

    # All should be zero/0.0
    assert result["confusion_tp_total"] == 0
    assert result["confusion_fp_total"] == 0
    assert result["confusion_fn_total"] == 0
    assert result["confusion_tn_total"] == 0
    assert result["drift_pct_last"] == 0.0
    assert result["accuracy_last"] == 0.0


def test_metrics_aggregates_single_drift_report():
    """Test /metrics aggregates metrics from single drift report"""
    # Create report with known confusion matrix
    confusion = ConfusionMatrix(tp=10, fp=2, fn=1, tn=0)
    report = DriftReport(confusion=confusion, mismatches=[], records_processed=13)

    add_drift_report(report)
    result = metrics()

    assert result["confusion_tp_total"] == 10
    assert result["confusion_fp_total"] == 2
    assert result["confusion_fn_total"] == 1
    assert result["confusion_tn_total"] == 0

    # drift_pct = (FP + FN) / (TP + FP + FN + TN) * 100 = (2+1)/(10+2+1+0)*100 = 23.08%
    expected_drift = round(((2 + 1) / (10 + 2 + 1 + 0)) * 100, 2)
    assert result["drift_pct_last"] == expected_drift

    # accuracy = (TP + TN) / total * 100 = (10+0)/(10+2+1+0)*100 = 76.92%
    expected_accuracy = round(((10 + 0) / (10 + 2 + 1 + 0)) * 100, 2)
    assert result["accuracy_last"] == expected_accuracy


def test_metrics_aggregates_multiple_drift_reports():
    """Test /metrics sums confusion metrics across multiple reports"""
    # Report 1
    confusion1 = ConfusionMatrix(tp=10, fp=2, fn=1, tn=0)
    report1 = DriftReport(confusion=confusion1, mismatches=[], records_processed=13)

    # Report 2
    confusion2 = ConfusionMatrix(tp=15, fp=1, fn=2, tn=0)
    report2 = DriftReport(confusion=confusion2, mismatches=[], records_processed=18)

    add_drift_report(report1)
    add_drift_report(report2)

    result = metrics()

    # Should sum all metrics
    assert result["confusion_tp_total"] == 10 + 15  # 25
    assert result["confusion_fp_total"] == 2 + 1  # 3
    assert result["confusion_fn_total"] == 1 + 2  # 3
    assert result["confusion_tn_total"] == 0 + 0  # 0

    # drift_pct_last should be from last report (report2)
    # report2: (1+2)/(15+1+2+0)*100 = 16.67%
    expected_drift_last = round(((1 + 2) / (15 + 1 + 2 + 0)) * 100, 2)
    assert result["drift_pct_last"] == expected_drift_last


def test_metrics_limits_report_storage_to_100():
    """Test that add_drift_report keeps only last 100 reports"""
    # Add 150 reports
    for i in range(150):
        confusion = ConfusionMatrix(tp=i, fp=0, fn=0, tn=0)
        report = DriftReport(confusion=confusion, mismatches=[], records_processed=i)
        add_drift_report(report)

    # Should keep only last 100
    with _drift_lock:
        assert len(_drift_reports) == 100
        # First report should be from iteration 50 (tp=50)
        assert _drift_reports[0]["confusion"]["tp"] == 50
        # Last report should be from iteration 149 (tp=149)
        assert _drift_reports[-1]["confusion"]["tp"] == 149


def test_metrics_perfect_accuracy_zero_drift():
    """Test /metrics with perfect match (100% accuracy, 0% drift)"""
    confusion = ConfusionMatrix(tp=20, fp=0, fn=0, tn=0)
    report = DriftReport(confusion=confusion, mismatches=[], records_processed=20)

    add_drift_report(report)
    result = metrics()

    assert result["drift_pct_last"] == 0.0
    assert result["accuracy_last"] == 100.0


def test_metrics_complete_drift():
    """Test /metrics with complete drift (0% accuracy, 100% drift)"""
    confusion = ConfusionMatrix(tp=0, fp=10, fn=10, tn=0)
    report = DriftReport(confusion=confusion, mismatches=[], records_processed=20)

    add_drift_report(report)
    result = metrics()

    assert result["drift_pct_last"] == 100.0
    assert result["accuracy_last"] == 0.0
