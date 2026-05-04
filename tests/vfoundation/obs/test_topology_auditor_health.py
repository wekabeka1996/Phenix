"""Tests for TopologyAuditor.audit_health() — Phase 14D infrastructure health."""
import pytest
from vfoundation.obs.topology_auditor import TopologyAuditor, HealthCheck, HealthReport


class TestHealthCheckDataclass:
    def test_fields_and_defaults(self):
        hc = HealthCheck(name="redis", check_fn=lambda: True)
        assert hc.name == "redis"
        assert hc.critical is True

    def test_non_critical_flag(self):
        hc = HealthCheck(name="metrics", check_fn=lambda: False, critical=False)
        assert hc.critical is False


class TestHealthReportDataclass:
    def test_all_pass_report(self):
        r = HealthReport(healthy=True, checks_passed=3, checks_failed=0,
                         failures=[], critical_failure=False)
        assert r.healthy is True
        assert r.critical_failure is False


class TestAuditHealth:
    def test_all_checks_pass(self):
        auditor = TopologyAuditor()
        report = auditor.audit_health([
            HealthCheck("a", lambda: True),
            HealthCheck("b", lambda: True),
        ])
        assert report.healthy is True
        assert report.checks_passed == 2
        assert report.checks_failed == 0
        assert report.critical_failure is False
        assert report.failures == []

    def test_non_critical_fail_healthy_false_not_critical_fail(self):
        auditor = TopologyAuditor()
        report = auditor.audit_health([
            HealthCheck("ok", lambda: True),
            HealthCheck("optional", lambda: False, critical=False),
        ])
        assert report.healthy is False
        assert report.checks_failed == 1
        assert report.critical_failure is False
        assert any("optional" in f for f in report.failures)

    def test_critical_check_fail_sets_critical_failure(self):
        auditor = TopologyAuditor()
        report = auditor.audit_health([
            HealthCheck("redis", lambda: False, critical=True),
        ])
        assert report.healthy is False
        assert report.critical_failure is True

    def test_empty_checks_returns_healthy(self):
        auditor = TopologyAuditor()
        report = auditor.audit_health([])
        assert report.healthy is True
        assert report.checks_passed == 0
        assert report.checks_failed == 0

    def test_exception_in_check_treated_as_failure_no_crash(self):
        auditor = TopologyAuditor()
        def explode() -> bool:
            raise RuntimeError("connection refused")
        report = auditor.audit_health([HealthCheck("broken", explode, critical=False)])
        assert report.checks_failed == 1
        assert any("broken" in f for f in report.failures)

    def test_exception_in_critical_check_sets_critical_flag(self):
        auditor = TopologyAuditor()
        def crash() -> bool:
            raise OSError("disk full")
        report = auditor.audit_health([HealthCheck("db", crash, critical=True)])
        assert report.critical_failure is True

    def test_mixed_pass_fail_counts_correct(self):
        auditor = TopologyAuditor()
        report = auditor.audit_health([
            HealthCheck("a", lambda: True),
            HealthCheck("b", lambda: True),
            HealthCheck("c", lambda: False, critical=False),
        ])
        assert report.checks_passed == 2
        assert report.checks_failed == 1
        assert report.healthy is False
        assert report.critical_failure is False
