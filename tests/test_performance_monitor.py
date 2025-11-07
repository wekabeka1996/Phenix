"""
Tests for Performance Monitor
"""

import asyncio
import pytest
import time
from datetime import datetime
from unittest.mock import Mock, patch

from apps.reference.monitoring.performance_monitor import (
    PerformanceMonitor,
    SLOConfig,
    PerformanceMetrics,
    DecisionTiming
)


class TestPerformanceMonitor:
    """Test PerformanceMonitor functionality."""

    @pytest.fixture
    def slo_config(self):
        """Create SLO configuration for testing."""
        return SLOConfig(
            p95_target_ms=50.0,
            timeout_rate_target=0.01,
            why_coverage_target=0.95
        )

    @pytest.fixture
    def performance_monitor(self, slo_config):
        """Create PerformanceMonitor instance."""
        return PerformanceMonitor(slo_config=slo_config, max_samples=100)

    def test_initialization(self, slo_config):
        """Test PerformanceMonitor initialization."""
        monitor = PerformanceMonitor(slo_config=slo_config)

        assert monitor.config == slo_config
        assert len(monitor._timings) == 0
        assert monitor._running is False

    def test_start_end_decision_success(self, performance_monitor):
        """Test successful decision timing."""
        rid = "test_rid_123"

        # Start timing
        timing_id = performance_monitor.start_decision(rid)
        assert timing_id.endswith(f"_{rid}")

        # Simulate some processing time
        time.sleep(0.01)  # 10ms

        # End timing
        performance_monitor.end_decision(
            timing_id,
            success=True,
            why_chain_length=3
        )

        # Check metrics
        metrics = performance_monitor.get_current_metrics()
        assert metrics.total_decisions == 1
        assert metrics.successful_decisions == 1
        assert metrics.failed_decisions == 0
        assert metrics.timeouts == 0
        assert metrics.p95_latency_ms > 0
        assert metrics.why_coverage == 1.0  # 100% coverage

    def test_start_end_decision_failure(self, performance_monitor):
        """Test failed decision timing."""
        rid = "test_rid_fail"

        # Start timing
        timing_id = performance_monitor.start_decision(rid)

        # End timing with failure
        performance_monitor.end_decision(
            timing_id,
            success=False,
            why_chain_length=1,
            error_message="Test error"
        )

        # Check metrics
        metrics = performance_monitor.get_current_metrics()
        assert metrics.total_decisions == 1
        assert metrics.successful_decisions == 0
        assert metrics.failed_decisions == 1
        assert metrics.why_coverage == 1.0

    def test_record_timeout(self, performance_monitor):
        """Test timeout recording."""
        rid = "test_rid_timeout"

        # Start timing
        timing_id = performance_monitor.start_decision(rid)

        # Record timeout
        performance_monitor.record_timeout(rid)

        # Check metrics
        metrics = performance_monitor.get_current_metrics()
        assert metrics.total_decisions == 1
        assert metrics.timeouts == 1
        assert metrics.timeout_rate == 1.0

    def test_multiple_decisions(self, performance_monitor):
        """Test multiple decision timings."""
        rids = ["rid1", "rid2", "rid3", "rid4", "rid5"]

        timing_ids = []
        for rid in rids:
            timing_ids.append(performance_monitor.start_decision(rid))

        # End with different outcomes
        performance_monitor.end_decision(
            timing_ids[0], success=True, why_chain_length=2)
        performance_monitor.end_decision(
            timing_ids[1], success=True, why_chain_length=0)
        performance_monitor.end_decision(
            timing_ids[2], success=False, why_chain_length=1)
        performance_monitor.record_timeout(rids[3])  # Use rid, not timing_id
        performance_monitor.end_decision(
            timing_ids[4], success=True, why_chain_length=3)

        metrics = performance_monitor.get_current_metrics()
        assert metrics.total_decisions == 5
        assert metrics.successful_decisions == 3
        assert metrics.failed_decisions == 1
        assert metrics.timeouts == 1
        # 3/5 have WHY chains (rid1, rid3, rid5)
        assert metrics.why_coverage == 0.6

    def test_slo_compliance_check(self, performance_monitor):
        """Test SLO compliance checking."""
        # Add some fast successful decisions
        for i in range(10):
            rid = f"rid_{i}"
            timing_id = performance_monitor.start_decision(rid)
            time.sleep(0.001)  # 1ms
            performance_monitor.end_decision(
                timing_id, success=True, why_chain_length=2
            )

        slo_status = performance_monitor.check_slo_compliance()

        # Should be compliant
        assert slo_status["p95_latency"]["compliant"] is True
        assert slo_status["timeout_rate"]["compliant"] is True
        assert slo_status["why_coverage"]["compliant"] is True
        assert slo_status["overall_compliant"] is True

    def test_slo_violation_p95(self, performance_monitor):
        """Test p95 SLO violation."""
        # Add slow decisions that violate p95 target
        for i in range(5):
            rid = f"slow_rid_{i}"
            timing_id = performance_monitor.start_decision(rid)
            time.sleep(0.1)  # 100ms - violates 50ms target
            performance_monitor.end_decision(
                timing_id, success=True, why_chain_length=1
            )

        slo_status = performance_monitor.check_slo_compliance()

        assert slo_status["p95_latency"]["compliant"] is False
        assert slo_status["overall_compliant"] is False

    def test_slo_violation_timeout_rate(self, performance_monitor):
        """Test timeout rate SLO violation."""
        # Add mostly timeouts
        for i in range(100):
            rid = f"timeout_rid_{i}"
            performance_monitor.start_decision(rid)
            if i < 5:  # Only 5 successful
                performance_monitor.end_decision(
                    f"{rid}_{time.time()}", success=True, why_chain_length=1
                )
            else:
                performance_monitor.record_timeout(rid)

        slo_status = performance_monitor.check_slo_compliance()

        assert slo_status["timeout_rate"]["compliant"] is False
        assert slo_status["overall_compliant"] is False

    def test_slo_violation_why_coverage(self, performance_monitor):
        """Test WHY coverage SLO violation."""
        # Add decisions with low WHY coverage
        for i in range(20):
            rid = f"why_rid_{i}"
            timing_id = performance_monitor.start_decision(rid)
            # Only 5 have WHY chains (25% coverage, violates 95% target)
            why_length = 1 if i < 5 else 0
            performance_monitor.end_decision(
                timing_id, success=True, why_chain_length=why_length
            )

        slo_status = performance_monitor.check_slo_compliance()

        assert slo_status["why_coverage"]["compliant"] is False
        assert slo_status["overall_compliant"] is False

    def test_alert_callback(self, performance_monitor):
        """Test alert callback functionality."""
        alert_calls = []

        def mock_callback(alert_type, data):
            alert_calls.append((alert_type, data))

        performance_monitor.add_alert_callback(mock_callback)

        # Create SLO violation
        for i in range(5):
            rid = f"violation_rid_{i}"
            timing_id = performance_monitor.start_decision(rid)
            time.sleep(0.1)  # Violate p95
            performance_monitor.end_decision(
                timing_id, success=True, why_chain_length=1
            )

        # Manually trigger alert check (normally done in background)
        slo_status = performance_monitor.check_slo_compliance()
        if not slo_status["overall_compliant"]:
            performance_monitor._send_alert("SLO_VIOLATION", {
                "violations": ["test violation"],
                "metrics": {"test": "data"}
            })

        assert len(alert_calls) == 1
        assert alert_calls[0][0] == "SLO_VIOLATION"

    def test_clear_old_data(self, performance_monitor):
        """Test clearing old timing data."""
        # Add some data
        for i in range(10):
            rid = f"clear_rid_{i}"
            timing_id = performance_monitor.start_decision(rid)
            performance_monitor.end_decision(
                timing_id, success=True, why_chain_length=1
            )

        assert len(performance_monitor._timings) == 10

        # Clear data older than 0 hours (should clear all)
        cleared = performance_monitor.clear_old_data(max_age_hours=0)
        assert cleared == 10
        assert len(performance_monitor._timings) == 0

    def test_get_recent_timings(self, performance_monitor):
        """Test getting recent timing records."""
        # Add some data
        for i in range(5):
            rid = f"recent_rid_{i}"
            timing_id = performance_monitor.start_decision(rid)
            performance_monitor.end_decision(
                timing_id, success=True, why_chain_length=1
            )

        recent = performance_monitor.get_recent_timings(limit=3)
        assert len(recent) == 3

        recent = performance_monitor.get_recent_timings(limit=10)
        assert len(recent) == 5

    def test_export_metrics_json(self, performance_monitor):
        """Test JSON export of metrics."""
        # Add some data
        rid = "export_rid"
        timing_id = performance_monitor.start_decision(rid)
        performance_monitor.end_decision(
            timing_id, success=True, why_chain_length=2
        )

        json_str = performance_monitor.export_metrics_json()
        assert isinstance(json_str, str)
        assert "metrics" in json_str
        assert "slo_status" in json_str
        assert "export_rid" not in json_str  # Should not contain PII

    @pytest.mark.asyncio
    async def test_background_monitoring(self, performance_monitor):
        """Test background monitoring task."""
        # Start monitoring
        await performance_monitor.start_monitoring(check_interval_seconds=1)

        # Add some data that should trigger alerts
        for i in range(3):
            rid = f"bg_rid_{i}"
            timing_id = performance_monitor.start_decision(rid)
            time.sleep(0.1)  # Violate p95
            performance_monitor.end_decision(
                timing_id, success=True, why_chain_length=1
            )

        # Wait for monitoring cycle
        await asyncio.sleep(1.5)

        # Stop monitoring
        await performance_monitor.stop_monitoring()

        # Should have detected violations
        assert performance_monitor._running is False

    def test_empty_metrics(self, performance_monitor):
        """Test metrics when no data is available."""
        metrics = performance_monitor.get_current_metrics()

        assert metrics.total_decisions == 0
        assert metrics.p95_latency_ms == 0.0
        assert metrics.timeout_rate == 0.0
        assert metrics.why_coverage == 0.0

    def test_max_samples_limit(self):
        """Test that max_samples limit is respected."""
        monitor = PerformanceMonitor(max_samples=3)

        # Add more than max_samples
        for i in range(5):
            rid = f"limit_rid_{i}"
            timing_id = monitor.start_decision(rid)
            monitor.end_decision(timing_id, success=True, why_chain_length=1)

        assert len(monitor._timings) == 3  # Should be limited to 3
