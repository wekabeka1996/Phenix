"""
T4: Aggregate Reporter Tests
==============================

Tests for apps/reference/domains/alpha_search/runtime/reporting.py
8 tests covering CSV output, JSONL health/summary, and stats.
"""

import csv
import json
import pytest
from pathlib import Path

from apps.reference.domains.alpha_search.runtime.reporting import (
    AggregateReporter,
    CSV_COLUMNS,
)


@pytest.mark.unit
class TestLogResult:
    """Tests for CSV result logging."""

    def test_writes_csv_row(self, tmp_path):
        """Row appended to aggregate_metrics.csv."""
        session_dir = tmp_path / "session"
        reporter = AggregateReporter(session_dir)
        reporter.log_result({
            "scenario_id": "S01",
            "strategy_type": "aurora",
            "symbol": "BTCUSDT",
            "score": 0.15,
        })

        csv_path = session_dir / "aggregate" / "aggregate_metrics.csv"
        assert csv_path.exists()
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["scenario_id"] == "S01"

    def test_csv_header_written_once(self, tmp_path):
        """Header written on first call, not duplicated."""
        session_dir = tmp_path / "session"
        reporter = AggregateReporter(session_dir)
        reporter.log_result({"score": 0.1})
        reporter.log_result({"score": 0.2})

        csv_path = session_dir / "aggregate" / "aggregate_metrics.csv"
        lines = csv_path.read_text(encoding="utf-8").strip().split("\n")
        # First line is header, rest are data
        header_count = sum(1 for l in lines if l.startswith("timestamp,"))
        assert header_count == 1

    def test_csv_columns_match_schema(self, tmp_path):
        """All CSV_COLUMNS present in header."""
        session_dir = tmp_path / "session"
        reporter = AggregateReporter(session_dir)
        reporter.log_result({"score": 0.1})

        csv_path = session_dir / "aggregate" / "aggregate_metrics.csv"
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert set(reader.fieldnames) == set(CSV_COLUMNS)

    def test_multiple_results_accumulate(self, tmp_path):
        """100 results -> 100 csv rows."""
        session_dir = tmp_path / "session"
        reporter = AggregateReporter(session_dir)
        for i in range(100):
            reporter.log_result({"score": 0.01 * i, "scenario_id": f"S{i:03d}"})

        assert reporter.stats["csv_rows"] == 100


@pytest.mark.unit
class TestLogHealth:
    """Tests for health JSONL logging."""

    def test_writes_jsonl(self, tmp_path):
        """JSON line appended to health.jsonl."""
        session_dir = tmp_path / "session"
        reporter = AggregateReporter(session_dir)
        reporter.log_health({"event": "SCENARIO_INIT", "scenario_id": "S01"})

        path = session_dir / "aggregate" / "health.jsonl"
        assert path.exists()
        record = json.loads(path.read_text(encoding="utf-8").strip())
        assert record["event"] == "SCENARIO_INIT"
        assert "ts" in record


@pytest.mark.unit
class TestLogSummary:
    """Tests for summary JSONL logging."""

    def test_writes_jsonl(self, tmp_path):
        """JSON line appended to summary.jsonl."""
        session_dir = tmp_path / "session"
        reporter = AggregateReporter(session_dir)
        reporter.log_summary({"S01": {"pnl": 100.0}, "S02": {"pnl": -50.0}})

        path = session_dir / "aggregate" / "summary.jsonl"
        assert path.exists()
        record = json.loads(path.read_text(encoding="utf-8").strip())
        assert "scenarios" in record
        assert "ts" in record


@pytest.mark.unit
class TestReporterLifecycle:
    """Tests for reporter setup."""

    def test_creates_aggregate_directory(self, tmp_path):
        """aggregate/ dir created on init."""
        session_dir = tmp_path / "session"
        reporter = AggregateReporter(session_dir)
        assert (session_dir / "aggregate").exists()

    def test_stats_property(self, tmp_path):
        """csv_rows counter correct."""
        session_dir = tmp_path / "session"
        reporter = AggregateReporter(session_dir)
        assert reporter.stats["csv_rows"] == 0
        reporter.log_result({"score": 0.1})
        assert reporter.stats["csv_rows"] == 1
