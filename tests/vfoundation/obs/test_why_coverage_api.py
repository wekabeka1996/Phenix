"""Tests for WhyCoverageReport extensions — Blueprint 11.2."""
from __future__ import annotations

from vfoundation.obs.why_chain_coverage import (
    WhyCoverageReport,
    measure_why_coverage,
)


class TestWhyCoverageAPI:
    def test_measure_why_coverage_delegates(self) -> None:
        """measure_why_coverage() produces a WhyCoverageReport."""
        events = [
            {"rid": "r1", "verb": "OPEN", "why": "signal above threshold"},
            {"rid": "r1", "verb": "FILL", "why": ""},
        ]
        report = measure_why_coverage(events, rid="r1")
        assert isinstance(report, WhyCoverageReport)
        assert report.rid == "r1"
        assert report.total_events == 2
        assert report.covered_events == 1

    def test_passes_threshold_true_and_false(self) -> None:
        """passes_threshold returns boolean based on coverage_pct."""
        report_good = WhyCoverageReport(rid="r1", total_events=10, covered_events=10)
        assert report_good.passes_threshold(95.0) is True

        report_bad = WhyCoverageReport(rid="r2", total_events=10, covered_events=5)
        assert report_bad.passes_threshold(95.0) is False

    def test_err_missing_why_lists_verbs(self) -> None:
        """err_missing_why returns list of verb strings from missing entries."""
        events = [
            {"rid": "r1", "verb": "OPEN", "why": ""},
            {"rid": "r1", "verb": "CLOSE", "why": ""},
            {"rid": "r1", "verb": "FILL", "why": "strong signal"},
        ]
        report = measure_why_coverage(events, rid="r1")
        missing_verbs = report.err_missing_why
        assert "OPEN" in missing_verbs
        assert "CLOSE" in missing_verbs
        assert "FILL" not in missing_verbs
