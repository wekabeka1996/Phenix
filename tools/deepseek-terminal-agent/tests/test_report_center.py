"""Tests for ReportCenter."""
from __future__ import annotations

import pytest

from deepseek_terminal_agent.sessions.report_center import ReportCenter


def test_register_report(tmp_path):
    center = ReportCenter(root_dir=tmp_path)
    rec = center.register_report(
        source_path="reports/audit.md",
        report_type="AUDIT_REPORT_V1",
        verdict="PASSED",
        summary="All systems nominal",
    )
    assert rec.report_id
    assert rec.status == "draft"
    assert rec.verdict == "PASSED"
    assert rec.schema_version == 1


def test_report_persists(tmp_path):
    center = ReportCenter(root_dir=tmp_path)
    rec = center.register_report(
        source_path="test.md",
        verdict="OK",
    )
    loaded = center.get_report(rec.report_id)
    assert loaded.report_id == rec.report_id


def test_report_not_found(tmp_path):
    center = ReportCenter(root_dir=tmp_path)
    with pytest.raises(KeyError):
        center.get_report("nonexistent")


def test_update_status(tmp_path):
    center = ReportCenter(root_dir=tmp_path)
    rec = center.register_report(source_path="test.md", verdict="DONE")
    updated = center.update_status(rec.report_id, "accepted")
    assert updated.status == "accepted"
    reloaded = center.get_report(rec.report_id)
    assert reloaded.status == "accepted"


def test_list_reports_by_type(tmp_path):
    center = ReportCenter(root_dir=tmp_path)
    center.register_report(
        source_path="a.md", report_type="AGENT_REPORT_V1", verdict="OK")
    center.register_report(
        source_path="b.md", report_type="TEST_REPORT", verdict="PASS")
    center.register_report(
        source_path="c.md", report_type="AGENT_REPORT_V1", verdict="FAIL")

    agent_reports = center.list_reports(report_type="AGENT_REPORT_V1")
    assert len(agent_reports) == 2

    test_reports = center.list_reports(report_type="TEST_REPORT")
    assert len(test_reports) == 1


def test_list_reports_by_status(tmp_path):
    center = ReportCenter(root_dir=tmp_path)
    r1 = center.register_report(source_path="a.md", verdict="OK")
    r2 = center.register_report(source_path="b.md", verdict="OK")
    center.update_status(r1.report_id, "accepted")

    accepted = center.list_reports(status="accepted")
    assert len(accepted) == 1
    assert accepted[0].report_id == r1.report_id

    draft = center.list_reports(status="draft")
    assert len(draft) == 1
    assert draft[0].report_id == r2.report_id


def test_scan_indexes_markdown_files(tmp_path):
    """scan_and_index discovers markdown files in known paths."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "AGENT_REPORT_V5.md").write_text(
        "AGENT_REPORT_V5\nverdict: PARTIAL_STABLE_CHECKPOINT\nsummary: Things work",
        encoding="utf-8",
    )
    center = ReportCenter(root_dir=tmp_path)
    new_records = center.scan_and_index()
    assert len(new_records) >= 1
    assert any("AGENT_REPORT" in r.report_type for r in new_records)


def test_scan_idempotent(tmp_path):
    """Scanning twice does not double-index."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "REPORT.md").write_text("verdict: DONE\nsummary: test", encoding="utf-8")
    center = ReportCenter(root_dir=tmp_path)
    first = center.scan_and_index()
    second = center.scan_and_index()
    assert len(second) == 0  # Already indexed


def test_no_report_implies_task_not_done(tmp_path):
    """DONE contract: empty report center means no completed task."""
    center = ReportCenter(root_dir=tmp_path)
    reports = center.list_reports(status="accepted")
    assert reports == []
