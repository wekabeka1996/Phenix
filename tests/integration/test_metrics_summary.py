#!/usr/bin/env python3
"""
Integration tests for metrics summary generation.
"""

import json
import tempfile
from pathlib import Path
import pytest
from tools.metrics_summary import MetricsSummary


class TestMetricsSummary:
    """Test metrics summary generation."""

    def test_generate_report_structure(self):
        """Test that generated report has correct structure."""
        summary = MetricsSummary()

        report = summary.generate_report()

        # Check required fields
        assert "timestamp" in report
        assert "period_hours" in report
        assert "metrics" in report
        assert "alerts" in report

        # Check metrics fields
        metrics = report["metrics"]
        required_metrics = [
            "open_success_rate", "mean_time_to_open_ms", "defer_rate",
            "block_rate", "retry_count", "qos_cooldown_hits", "breakdown_by_symbol"
        ]

        for metric in required_metrics:
            assert metric in metrics

    def test_calculate_derived_metrics(self):
        """Test calculation of derived metrics."""
        summary = MetricsSummary()

        # Mock metrics data
        metrics = {
            "open_success_total": 95,
            "cmd_open_total": 100,
            "time_to_open_ms_sum": 5000,
            "time_to_open_count": 95,
            "defer_rate": 0.02,
            "block_rate": 0.01,
            "retry_count": 3,
            "qos_cooldown_hits": 1
        }

        derived = summary.calculate_derived_metrics(metrics)

        assert derived["open_success_rate"] == 0.95
        assert derived["mean_time_to_open_ms"] == round(5000 / 95, 2)
        assert derived["defer_rate"] == 0.02
        assert derived["block_rate"] == 0.01
        assert derived["retry_count"] == 3
        assert derived["qos_cooldown_hits"] == 1

    def test_check_alerts(self):
        """Test alert generation based on thresholds."""
        summary = MetricsSummary()

        # Metrics that should trigger alerts
        metrics = {
            "open_success_rate": 0.85,  # Below 0.9
            "mean_time_to_open_ms": 150,  # Above 100
            "defer_rate": 0.06,  # Above 0.05
            "block_rate": 0.03,  # Above 0.02
            "retry_count": 5,
            "qos_cooldown_hits": 2,
            "breakdown_by_symbol": {
                "BTCUSDT": {"open_success_rate": 0.85}  # Below 0.9
            }
        }

        alerts = summary.check_alerts(metrics)

        assert len(alerts) >= 4  # Should have multiple alerts
        assert any("Open success rate below 90%" in alert for alert in alerts)
        assert any("Mean time to open exceeds 100ms" in alert for alert in alerts)
        assert any("Defer rate above 5%" in alert for alert in alerts)
        assert any("Block rate above 2%" in alert for alert in alerts)

    def test_save_report(self):
        """Test saving report to JSON file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = MetricsSummary(reports_dir=temp_dir)

            report = summary.generate_report()
            summary.save_report(report, "test_report.json")

            # Verify file was created and contains valid JSON
            report_path = Path(temp_dir) / "test_report.json"
            assert report_path.exists()

            with open(report_path, 'r', encoding='utf-8') as f:
                saved_report = json.load(f)

            assert saved_report["period_hours"] == 24
            assert "metrics" in saved_report

    def test_run_method(self):
        """Test the main run method."""
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = MetricsSummary(reports_dir=temp_dir)

            result = summary.run()

            # Should return the report
            assert isinstance(result, dict)
            assert "metrics" in result

            # Should have saved the file
            report_path = Path(temp_dir) / "summary_gate_status.json"
            assert report_path.exists()
