# -*- coding: utf-8 -*-
"""
Tests for execpos_metrics_aggregator.py

RID: EP-METRICS-TOOLS-IMPLEMENT-S7

Validates canonical ExecPos metrics aggregator for tooling:
- execpos_trades_total{result, source}
- execpos_bracket_violations_total{severity, kind}
- execpos_watchdog_alerts_total{severity, kind}
- execpos_trailing_signals_total{kind}

Related: apps/reference/tools/execpos_metrics_aggregator.py
"""
from apps.reference.tools.execpos_metrics_aggregator import (
    ExecPosMetricsAggregator,
    summarize_trace_metrics,
)
import sys
from pathlib import Path

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestExecPosMetricsAggregatorBasic:
    """Test basic counter increments and dict output."""

    def test_add_trade_and_to_dict(self):
        """Test adding trades with various result/source combinations and dict output."""
        agg = ExecPosMetricsAggregator()

        # Add some trades
        agg.add_trade(result="win", source="tca")
        agg.add_trade(result="win", source="tca")
        agg.add_trade(result="loss", source="trace")
        agg.add_trade(result="flat", source="runtime")
        agg.add_trade(result="unknown", source="unknown")

        # Get dict output
        metrics = agg.to_dict()

        # Verify structure
        assert "execpos_trades_total" in metrics
        trades = metrics["execpos_trades_total"]
        assert isinstance(trades, list)

        # Verify counts
        # Convert to dict for easier lookup
        trades_dict = {
            (item["labels"]["result"], item["labels"]["source"]): item["value"]
            for item in trades
        }

        assert trades_dict[("WIN", "TCA")] == 2
        assert trades_dict[("LOSS", "TRACE")] == 1
        assert trades_dict[("FLAT", "RUNTIME")] == 1
        assert trades_dict[("UNKNOWN", "UNKNOWN")] == 1

    def test_add_bracket_violation_and_to_prometheus_text(self):
        """Test adding bracket violations and Prometheus text output."""
        agg = ExecPosMetricsAggregator()

        # Add violations
        agg.add_bracket_violation(severity="WARN", kind="MISSING_SL")
        agg.add_bracket_violation(severity="WARN", kind="MISSING_SL")
        agg.add_bracket_violation(severity="ALERT", kind="ORPHAN_SL")
        agg.add_bracket_violation(severity="ALERT", kind="TOO_MANY_SL")

        # Get Prometheus text
        prom_text = agg.to_prometheus_text()

        # Verify format
        assert isinstance(prom_text, str)
        assert 'execpos_bracket_violations_total{severity="WARN",kind="MISSING_SL"} 2' in prom_text
        assert 'execpos_bracket_violations_total{severity="ALERT",kind="ORPHAN_SL"} 1' in prom_text
        assert 'execpos_bracket_violations_total{severity="ALERT",kind="TOO_MANY_SL"} 1' in prom_text

    def test_add_watchdog_alert(self):
        """Test adding watchdog alerts."""
        agg = ExecPosMetricsAggregator()

        agg.add_watchdog_alert(severity="WARN", kind="MISSING_SL")
        agg.add_watchdog_alert(severity="ALERT", kind="ORPHAN_SL")
        agg.add_watchdog_alert(severity="ALERT", kind="STALE_LEVELS")

        metrics = agg.to_dict()
        alerts = metrics["execpos_watchdog_alerts_total"]

        # Convert to lookup dict
        alerts_dict = {
            (item["labels"]["severity"], item["labels"]["kind"]): item["value"]
            for item in alerts
        }

        assert alerts_dict[("WARN", "MISSING_SL")] == 1
        assert alerts_dict[("ALERT", "ORPHAN_SL")] == 1
        assert alerts_dict[("ALERT", "STALE_LEVELS")] == 1

    def test_add_trailing_signal(self):
        """Test adding trailing signals."""
        agg = ExecPosMetricsAggregator()

        agg.add_trailing_signal(kind="EXIT")
        agg.add_trailing_signal(kind="MOVE_SL")
        agg.add_trailing_signal(kind="BREAKEVEN")
        agg.add_trailing_signal(kind="TIME_EXIT")
        agg.add_trailing_signal(kind="UNKNOWN")

        metrics = agg.to_dict()
        signals = metrics["execpos_trailing_signals_total"]

        # Convert to lookup dict
        signals_dict = {item["labels"]["kind"]: item["value"]
                        for item in signals}

        assert signals_dict["EXIT"] == 1
        assert signals_dict["MOVE_SL"] == 1
        assert signals_dict["BREAKEVEN"] == 1
        assert signals_dict["TIME_EXIT"] == 1
        assert signals_dict["UNKNOWN"] == 1


class TestExecPosMetricsAggregatorNormalization:
    """Test label normalization (unknown values)."""

    def test_unknown_labels_normalized_trades(self):
        """Test that unknown/invalid trade labels are normalized to UNKNOWN."""
        agg = ExecPosMetricsAggregator()

        # Add trades with invalid values
        agg.add_trade(result="invalid_result", source="tca")
        agg.add_trade(result="win", source="invalid_source")
        agg.add_trade(result=None, source=None)
        agg.add_trade(result="", source="")

        metrics = agg.to_dict()
        trades = metrics["execpos_trades_total"]

        # Convert to lookup dict
        trades_dict = {
            (item["labels"]["result"], item["labels"]["source"]): item["value"]
            for item in trades
        }

        # All invalid results should map to UNKNOWN
        assert trades_dict[("UNKNOWN", "TCA")] == 1
        assert trades_dict[("WIN", "UNKNOWN")] == 1
        assert trades_dict[("UNKNOWN", "UNKNOWN")] == 2  # None + empty string

    def test_unknown_labels_normalized_violations(self):
        """Test that unknown/invalid violation labels are normalized."""
        agg = ExecPosMetricsAggregator()

        # Add violations with invalid severity
        agg.add_bracket_violation(severity="INVALID", kind="MISSING_SL")
        agg.add_bracket_violation(severity=None, kind="ORPHAN_SL")
        agg.add_bracket_violation(severity="", kind="TOO_MANY_SL")

        # Kind is not normalized (any string accepted), but severity should default to WARN
        metrics = agg.to_dict()
        violations = metrics["execpos_bracket_violations_total"]

        # Convert to lookup dict
        violations_dict = {
            (item["labels"]["severity"], item["labels"]["kind"]): item["value"]
            for item in violations
        }

        # All invalid severities should map to WARN
        assert violations_dict[("WARN", "MISSING_SL")] == 1
        assert violations_dict[("WARN", "ORPHAN_SL")] == 1
        assert violations_dict[("WARN", "TOO_MANY_SL")] == 1

    def test_unknown_labels_normalized_trailing(self):
        """Test that unknown trailing signal kinds are normalized to UNKNOWN."""
        agg = ExecPosMetricsAggregator()

        # Add signals with invalid kinds
        agg.add_trailing_signal(kind="invalid_kind")
        agg.add_trailing_signal(kind=None)
        agg.add_trailing_signal(kind="")

        metrics = agg.to_dict()
        signals = metrics["execpos_trailing_signals_total"]

        # Convert to lookup dict
        signals_dict = {item["labels"]["kind"]: item["value"]
                        for item in signals}

        # All invalid kinds should map to UNKNOWN
        assert signals_dict["UNKNOWN"] == 3

    def test_case_insensitive_normalization(self):
        """Test that label values are case-insensitive (normalized to upper)."""
        agg = ExecPosMetricsAggregator()

        # Add with different cases
        agg.add_trade(result="Win", source="TCA")
        agg.add_trade(result="WIN", source="tca")
        agg.add_trade(result="win", source="Tca")

        metrics = agg.to_dict()
        trades = metrics["execpos_trades_total"]

        # All should be counted under WIN/TCA
        trades_dict = {
            (item["labels"]["result"], item["labels"]["source"]): item["value"]
            for item in trades
        }

        assert trades_dict[("WIN", "TCA")] == 3


class TestExecPosMetricsAggregatorHelpers:
    """Test helper methods for consuming tool inputs."""

    def test_consume_tca_records(self):
        """Test consuming TCA records (pnl-less -> result=unknown)."""
        agg = ExecPosMetricsAggregator()

        # Mock TCA records (any iterable)
        mock_records = [
            {"trade_id": "T1"},
            {"trade_id": "T2"},
            {"trade_id": "T3"},
        ]

        agg.consume_tca_records(mock_records)

        metrics = agg.to_dict()
        trades = metrics["execpos_trades_total"]

        # All should be counted as unknown/tca
        trades_dict = {
            (item["labels"]["result"], item["labels"]["source"]): item["value"]
            for item in trades
        }

        assert trades_dict[("UNKNOWN", "TCA")] == 3

    def test_consume_trace_events_exec_trade(self):
        """Test consuming trace events with EXEC_TRADE."""
        agg = ExecPosMetricsAggregator()

        # Mock TraceEvent objects
        class MockTraceEvent:
            def __init__(self, event_type, source="trace", payload=None):
                self.event_type = event_type
                self.source = source
                self.payload = payload or {}

        events = [
            MockTraceEvent("EXEC_TRADE", source="trace", payload={"qty": 10}),
            MockTraceEvent("EXEC_TRADE", source="trace", payload={"qty": 20}),
        ]

        agg.consume_trace_events(events)

        metrics = agg.to_dict()
        trades = metrics["execpos_trades_total"]

        trades_dict = {
            (item["labels"]["result"], item["labels"]["source"]): item["value"]
            for item in trades
        }

        assert trades_dict[("UNKNOWN", "TRACE")] == 2

    def test_consume_trace_events_watchdog(self):
        """Test consuming trace events with WATCHDOG events."""
        agg = ExecPosMetricsAggregator()

        class MockTraceEvent:
            def __init__(self, event_type, payload=None):
                self.event_type = event_type
                self.source = "watchdog"
                self.payload = payload or {}

        events = [
            MockTraceEvent("WATCHDOG_ALERT", payload={
                           "severity": "WARN", "kind": "MISSING_SL"}),
            MockTraceEvent("WATCHDOG_ALERT", payload={
                           "severity": "ALERT", "kind": "ORPHAN_SL"}),
        ]

        agg.consume_trace_events(events)

        metrics = agg.to_dict()
        alerts = metrics["execpos_watchdog_alerts_total"]

        alerts_dict = {
            (item["labels"]["severity"], item["labels"]["kind"]): item["value"]
            for item in alerts
        }

        assert alerts_dict[("WARN", "MISSING_SL")] == 1
        assert alerts_dict[("ALERT", "ORPHAN_SL")] == 1

    def test_consume_trace_events_bracket(self):
        """Test consuming trace events with BRACKET events."""
        agg = ExecPosMetricsAggregator()

        class MockTraceEvent:
            def __init__(self, event_type, payload=None):
                self.event_type = event_type
                self.source = "bracket"
                self.payload = payload or {}

        events = [
            MockTraceEvent("BRACKET_VIOLATION", payload={
                           "severity": "WARN", "kind": "MISSING_SL"}),
            MockTraceEvent("BRACKET_ALERT", payload={
                           "severity": "ALERT", "kind": "TOO_MANY_SL"}),
        ]

        agg.consume_trace_events(events)

        metrics = agg.to_dict()
        violations = metrics["execpos_bracket_violations_total"]

        violations_dict = {
            (item["labels"]["severity"], item["labels"]["kind"]): item["value"]
            for item in violations
        }

        assert violations_dict[("WARN", "MISSING_SL")] == 1
        assert violations_dict[("ALERT", "TOO_MANY_SL")] == 1

    def test_consume_trace_events_trailing(self):
        """Test consuming trace events with TRAILING events."""
        agg = ExecPosMetricsAggregator()

        class MockTraceEvent:
            def __init__(self, event_type, payload=None):
                self.event_type = event_type
                self.source = "trailing"
                self.payload = payload or {}

        events = [
            MockTraceEvent("TRAILING_SL_UPDATED", payload={"kind": "MOVE_SL"}),
            MockTraceEvent("TRAILING_EXIT", payload={"kind": "EXIT"}),
        ]

        agg.consume_trace_events(events)

        metrics = agg.to_dict()
        signals = metrics["execpos_trailing_signals_total"]

        signals_dict = {item["labels"]["kind"]: item["value"]
                        for item in signals}

        assert signals_dict["MOVE_SL"] == 1
        assert signals_dict["EXIT"] == 1


class TestExecPosMetricsAggregatorPrometheusFormat:
    """Test Prometheus text exposition format."""

    def test_prometheus_text_format_basic(self):
        """Test basic Prometheus text format."""
        agg = ExecPosMetricsAggregator()

        agg.add_trade(result="win", source="tca")
        agg.add_bracket_violation(severity="WARN", kind="MISSING_SL")
        agg.add_watchdog_alert(severity="ALERT", kind="ORPHAN_SL")
        agg.add_trailing_signal(kind="EXIT")

        prom_text = agg.to_prometheus_text()

        # Verify format matches Prometheus exposition
        assert 'execpos_trades_total{result="WIN",source="TCA"} 1' in prom_text
        assert 'execpos_bracket_violations_total{severity="WARN",kind="MISSING_SL"} 1' in prom_text
        assert 'execpos_watchdog_alerts_total{severity="ALERT",kind="ORPHAN_SL"} 1' in prom_text
        assert 'execpos_trailing_signals_total{kind="EXIT"} 1' in prom_text

    def test_prometheus_text_empty_aggregator(self):
        """Test Prometheus text with no metrics added."""
        agg = ExecPosMetricsAggregator()

        prom_text = agg.to_prometheus_text()

        # Should be empty string
        assert prom_text == ""

    def test_prometheus_text_multiline(self):
        """Test Prometheus text with multiple metrics is newline-separated."""
        agg = ExecPosMetricsAggregator()

        agg.add_trade(result="win", source="tca")
        agg.add_trade(result="loss", source="trace")

        prom_text = agg.to_prometheus_text()

        lines = prom_text.strip().split("\n")
        assert len(lines) == 2
        assert all('execpos_trades_total{' in line for line in lines)


class TestSummarizeTraceMetrics:
    """Test summarize_trace_metrics helper function."""

    def test_summarize_trace_with_pnl_win(self):
        """Test deriving win result from trace exit_info.pnl > 0."""

        class MockTrace:
            def __init__(self):
                self.exit_info = {"pnl": 100.0}
                self.events = []

        trace = MockTrace()
        agg = summarize_trace_metrics(trace)

        metrics = agg.to_dict()
        trades = metrics["execpos_trades_total"]

        trades_dict = {
            (item["labels"]["result"], item["labels"]["source"]): item["value"]
            for item in trades
        }

        assert trades_dict[("WIN", "TRACE")] == 1

    def test_summarize_trace_with_pnl_loss(self):
        """Test deriving loss result from trace exit_info.pnl < 0."""

        class MockTrace:
            def __init__(self):
                self.exit_info = {"pnl": -50.0}
                self.events = []

        trace = MockTrace()
        agg = summarize_trace_metrics(trace)

        metrics = agg.to_dict()
        trades = metrics["execpos_trades_total"]

        trades_dict = {
            (item["labels"]["result"], item["labels"]["source"]): item["value"]
            for item in trades
        }

        assert trades_dict[("LOSS", "TRACE")] == 1

    def test_summarize_trace_with_pnl_flat(self):
        """Test deriving flat result from trace exit_info.pnl == 0."""

        class MockTrace:
            def __init__(self):
                self.exit_info = {"pnl": 0.0}
                self.events = []

        trace = MockTrace()
        agg = summarize_trace_metrics(trace)

        metrics = agg.to_dict()
        trades = metrics["execpos_trades_total"]

        trades_dict = {
            (item["labels"]["result"], item["labels"]["source"]): item["value"]
            for item in trades
        }

        assert trades_dict[("FLAT", "TRACE")] == 1

    def test_summarize_trace_no_pnl_consumes_events(self):
        """Test that if pnl absent, trace events are consumed normally."""

        class MockTraceEvent:
            def __init__(self, event_type, payload=None):
                self.event_type = event_type
                self.source = "trace"
                self.payload = payload or {}

        class MockTrace:
            def __init__(self):
                self.exit_info = {}  # No pnl
                self.events = [
                    MockTraceEvent("EXEC_TRADE", payload={"qty": 10}),
                ]

        trace = MockTrace()
        agg = summarize_trace_metrics(trace)

        metrics = agg.to_dict()
        trades = metrics["execpos_trades_total"]

        trades_dict = {
            (item["labels"]["result"], item["labels"]["source"]): item["value"]
            for item in trades
        }

        # Should count EXEC_TRADE as unknown/trace
        assert trades_dict[("UNKNOWN", "TRACE")] == 1
