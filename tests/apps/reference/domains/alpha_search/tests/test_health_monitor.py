"""
T3: Health Monitor Tests
=========================

Tests for apps/reference/domains/alpha_search/runtime/health.py
12 tests covering heartbeat, degradation, recovery, and health checks.
"""

import time
import pytest

from apps.reference.domains.alpha_search.runtime.contracts import RuntimeConfig
from apps.reference.domains.alpha_search.runtime.health import HealthMonitor


def _make_monitor(heartbeat_sec=30.0):
    """Create a HealthMonitor with custom heartbeat."""
    cfg = RuntimeConfig(health_heartbeat_sec=heartbeat_sec)
    return HealthMonitor(cfg)


@pytest.mark.unit
class TestRecordSuccess:
    """Tests for record_success behavior."""

    def test_updates_heartbeat(self):
        """Last heartbeat timestamp updated on success."""
        monitor = _make_monitor()
        before = time.time()
        monitor.record_success("S01")
        after = time.time()

        assert "S01" in monitor._last_heartbeat
        assert before <= monitor._last_heartbeat["S01"] <= after

    def test_resets_failures(self):
        """Consecutive failure counter reset to 0."""
        monitor = _make_monitor()
        monitor._consecutive_failures["S01"] = 2
        monitor.record_success("S01")
        assert monitor._consecutive_failures["S01"] == 0

    def test_recovers_degraded(self):
        """Degraded scenario removed from set on success."""
        monitor = _make_monitor()
        monitor._degraded.add("S01")
        monitor.record_success("S01")
        assert "S01" not in monitor._degraded


@pytest.mark.unit
class TestRecordFailure:
    """Tests for record_failure and degradation."""

    def test_increments_counter(self):
        """Counter incremented on failure."""
        monitor = _make_monitor()
        monitor.record_failure("S01", "err1")
        assert monitor._consecutive_failures["S01"] == 1
        monitor.record_failure("S01", "err2")
        assert monitor._consecutive_failures["S01"] == 2

    def test_degradation_after_threshold(self):
        """3 consecutive failures -> degraded."""
        monitor = _make_monitor()
        for i in range(3):
            monitor.record_failure("S01", f"err_{i}")
        assert "S01" in monitor._degraded
        assert monitor._total_degradations == 1

    def test_no_degradation_below_threshold(self):
        """2 failures -> not degraded."""
        monitor = _make_monitor()
        monitor.record_failure("S01", "err1")
        monitor.record_failure("S01", "err2")
        assert "S01" not in monitor._degraded

    def test_is_degraded_query(self):
        """is_degraded returns True for degraded, False for healthy."""
        monitor = _make_monitor()
        assert monitor.is_degraded("S01") is False
        for i in range(3):
            monitor.record_failure("S01", f"err_{i}")
        assert monitor.is_degraded("S01") is True


@pytest.mark.unit
class TestCheckHealth:
    """Tests for check_health status report."""

    def test_healthy(self):
        """Recent heartbeat -> 'healthy'."""
        monitor = _make_monitor(heartbeat_sec=30.0)
        monitor.record_success("S01")
        statuses = monitor.check_health(["S01"])
        assert statuses["S01"] == "healthy"

    def test_stale(self):
        """Old heartbeat -> 'stale'."""
        monitor = _make_monitor(heartbeat_sec=5.0)
        # Set a very old heartbeat (5 * 3 = 15s stale threshold)
        monitor._last_heartbeat["S01"] = time.time() - 100.0
        statuses = monitor.check_health(["S01"])
        assert statuses["S01"] == "stale"

    def test_degraded(self):
        """Degraded scenario -> 'degraded'."""
        monitor = _make_monitor()
        for i in range(3):
            monitor.record_failure("S01", f"err_{i}")
        statuses = monitor.check_health(["S01"])
        assert statuses["S01"] == "degraded"

    def test_unknown(self):
        """No heartbeat ever -> 'unknown'."""
        monitor = _make_monitor()
        statuses = monitor.check_health(["S_NEVER_SEEN"])
        assert statuses["S_NEVER_SEEN"] == "unknown"

    def test_stats_property(self):
        """All fields present and correct."""
        monitor = _make_monitor()
        monitor.record_success("S01")
        monitor.check_health(["S01"])

        stats = monitor.stats
        assert "total_checks" in stats
        assert "total_degradations" in stats
        assert "currently_degraded" in stats
        assert "heartbeat_ages" in stats
        assert stats["total_checks"] == 1
