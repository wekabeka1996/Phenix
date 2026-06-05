"""Tests for vfoundation.obs.topology_auditor — Phase 5.1."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from vfoundation.obs.topology_auditor import TopologyAuditor, DriftReport


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pytest.ini").exists():
            return parent
    raise RuntimeError("Cannot detect repo root")


class _FakeBus:
    """Minimal FSMCore stand-in."""

    def __init__(self, domains: dict | None = None) -> None:
        self.domains: Dict[str, Any] = domains or {}
        self.emitted: list = []

    def emit(self, event_name: str, payload: dict, why: str, data_ref: list | None = None) -> None:
        self.emitted.append((event_name, payload, why))


class TestTopologyAuditor:
    def test_loads_expected_owners(self) -> None:
        auditor = TopologyAuditor(repo_root=_repo_root())
        owners = auditor.get_expected_owners()
        assert len(owners) >= 5, f"Expected ≥5 owners from registry, got {len(owners)}"
        # Known owners from verb registry
        assert "execution_position" in owners
        assert "market_data" in owners

    def test_unknown_owner_ignored(self) -> None:
        auditor = TopologyAuditor(repo_root=_repo_root())
        assert "unknown" not in auditor.get_expected_owners()

    def test_audit_all_registered_healthy(self) -> None:
        """When all expected domains are registered, report is healthy."""
        auditor = TopologyAuditor(repo_root=_repo_root())
        owners = auditor.get_expected_owners()
        bus = _FakeBus(domains={name: object() for name in owners})
        auditor._bus = bus

        report = auditor.audit()
        assert report.healthy
        assert len(report.missing) == 0
        assert len(bus.emitted) == 0  # No drift event

    def test_audit_missing_domain_emits_event(self) -> None:
        """When domains are missing, audit emits EVT:TOPOLOGY_DRIFT_DETECTED."""
        bus = _FakeBus(domains={})  # No domains registered
        auditor = TopologyAuditor(bus=bus, repo_root=_repo_root())

        report = auditor.audit()
        assert not report.healthy
        assert len(report.missing) > 0
        assert len(bus.emitted) == 1
        assert bus.emitted[0][0] == "EVT:TOPOLOGY_DRIFT_DETECTED"
        assert "missing" in bus.emitted[0][1]

    def test_audit_extra_domain(self) -> None:
        auditor = TopologyAuditor(repo_root=_repo_root())
        owners = auditor.get_expected_owners()
        domains = {name: object() for name in owners}
        domains["totally_new_domain"] = object()
        bus = _FakeBus(domains=domains)
        auditor._bus = bus

        report = auditor.audit()
        assert report.healthy  # Extra domains don't make it unhealthy
        assert "totally_new_domain" in report.extra

    def test_no_bus_still_works(self) -> None:
        auditor = TopologyAuditor(bus=None, repo_root=_repo_root())
        report = auditor.audit()
        # Without a bus, registered = empty, so all expected are "missing"
        assert not report.healthy


class TestDriftReport:
    def test_report_computes_sets(self) -> None:
        report = DriftReport(
            expected={"a", "b", "c"},
            registered={"b", "c", "d"},
            missing=set(), extra=set(),
        )
        assert report.missing == {"a"}
        assert report.extra == {"d"}
        assert not report.healthy

    def test_healthy_when_all_present(self) -> None:
        report = DriftReport(
            expected={"a", "b"},
            registered={"a", "b", "c"},
            missing=set(), extra=set(),
        )
        assert report.healthy
        assert report.extra == {"c"}
