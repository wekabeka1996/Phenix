# -*- coding: utf-8 -*-
"""
Tests for Order Trace CLI --metrics mode

RID: EP-METRICS-TOOLS-IMPLEMENT-S7

Validates OrderTrace CLI can export canonical metrics via --output=metrics.

Related: tools/order_trace_cli.py
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class MockTraceEvent:
    """Mock TraceEvent for testing."""

    def __init__(self, event_type, source="trace", payload=None, ts=1000.0, why=""):
        self.event_type = event_type
        self.source = source
        self.payload = payload or {}
        self.ts = ts
        self.why = why


class MockTradeTrace:
    """Mock TradeTrace for testing."""

    def __init__(self, trace_id="T123", symbol="BTCUSDT", direction="LONG", events=None, exit_info=None):
        self.trace_id = trace_id
        self.symbol = symbol
        self.direction = direction
        self.events = events or []
        self.entry_info = None
        self.exit_info = exit_info or {}
        self.gaps = []

    def to_dict(self):
        return {
            "trace_id": self.trace_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "events": [{"event_type": e.event_type} for e in self.events],
        }


@pytest.fixture
def mock_build_trace():
    """Mock build_trace_for_trade function."""
    with patch("tools.order_trace_cli.build_trace_for_trade") as mock:
        yield mock


@pytest.fixture
def mock_trace_sources():
    """Mock TraceSources."""
    with patch("tools.order_trace_cli.TraceSources") as mock:
        yield mock


class TestOrderTraceCLIMetricsMode:
    """Test OrderTrace CLI --output=metrics mode."""

    def test_metrics_dict_output_with_pnl_win(self, mock_build_trace, mock_trace_sources, capsys):
        """Test --output=metrics with dict format (win trade)."""
        # Setup mock trace with win (pnl > 0)
        trace = MockTradeTrace(
            trace_id="T123",
            events=[
                MockTraceEvent("EXEC_TRADE", payload={"qty": 10}),
            ],
            exit_info={"pnl": 100.0},
        )
        mock_build_trace.return_value = trace

        # Simulate CLI args
        test_args = [
            "tools/order_trace_cli.py",
            "--trade-id",
            "T123",
            "--logs-root",
            "./logs",
            "--output",
            "metrics",
            "--metrics-format",
            "dict",
        ]

        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                from tools.order_trace_cli import main

                main()

            assert exc_info.value.code == 0

        # Verify output
        captured = capsys.readouterr()
        output = json.loads(captured.out)

        # Should have execpos_trades_total with win
        assert "execpos_trades_total" in output
        trades = output["execpos_trades_total"]

        # Will have 2 entries: WIN (from pnl) + UNKNOWN (from EXEC_TRADE event)
        assert len(trades) == 2

        # Find WIN entry
        win_entry = next(
            (t for t in trades if t["labels"]["result"] == "WIN"), None)
        assert win_entry is not None
        assert win_entry["labels"]["source"] == "TRACE"
        assert win_entry["value"] == 1

    def test_metrics_prometheus_output(self, mock_build_trace, mock_trace_sources, capsys):
        """Test --output=metrics with prometheus format."""
        # Setup mock trace with loss (pnl < 0)
        trace = MockTradeTrace(
            trace_id="T456",
            events=[
                MockTraceEvent("EXEC_TRADE", payload={"qty": 5}),
            ],
            exit_info={"pnl": -50.0},
        )
        mock_build_trace.return_value = trace

        # Simulate CLI args
        test_args = [
            "tools/order_trace_cli.py",
            "--trade-id",
            "T456",
            "--logs-root",
            "./logs",
            "--output",
            "metrics",
            "--metrics-format",
            "prometheus",
        ]

        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                from tools.order_trace_cli import main

                main()

            assert exc_info.value.code == 0

        # Verify output
        captured = capsys.readouterr()
        assert 'execpos_trades_total{result="LOSS",source="TRACE"} 1' in captured.out

    def test_metrics_mode_with_multiple_events(self, mock_build_trace, mock_trace_sources, capsys):
        """Test --output=metrics with trace containing multiple event types."""
        # Setup mock trace with multiple events
        trace = MockTradeTrace(
            trace_id="T789",
            events=[
                MockTraceEvent("EXEC_TRADE", payload={"qty": 10}),
                MockTraceEvent("WATCHDOG_ALERT", payload={
                               "severity": "WARN", "kind": "MISSING_SL"}),
                MockTraceEvent("BRACKET_VIOLATION", payload={
                               "severity": "ALERT", "kind": "ORPHAN_SL"}),
                MockTraceEvent("TRAILING_SL_UPDATED",
                               payload={"kind": "MOVE_SL"}),
            ],
            exit_info={"pnl": 0.0},  # flat
        )
        mock_build_trace.return_value = trace

        # Simulate CLI args
        test_args = [
            "tools/order_trace_cli.py",
            "--trade-id",
            "T789",
            "--logs-root",
            "./logs",
            "--output",
            "metrics",
        ]

        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                from tools.order_trace_cli import main

                main()

            assert exc_info.value.code == 0

        # Verify output contains all metric types
        captured = capsys.readouterr()
        output = json.loads(captured.out)

        # Should have all 4 metric types
        assert "execpos_trades_total" in output
        assert "execpos_watchdog_alerts_total" in output
        assert "execpos_bracket_violations_total" in output
        assert "execpos_trailing_signals_total" in output

        # Verify counts
        trades = output["execpos_trades_total"]
        assert trades[0]["labels"]["result"] == "FLAT"
        assert trades[0]["value"] == 1

        watchdog = output["execpos_watchdog_alerts_total"]
        assert len(watchdog) == 1
        assert watchdog[0]["labels"]["severity"] == "WARN"
        assert watchdog[0]["labels"]["kind"] == "MISSING_SL"

        brackets = output["execpos_bracket_violations_total"]
        assert len(brackets) == 1
        assert brackets[0]["labels"]["severity"] == "ALERT"

        trailing = output["execpos_trailing_signals_total"]
        assert len(trailing) == 1
        assert trailing[0]["labels"]["kind"] == "MOVE_SL"

    def test_metrics_mode_no_pnl_falls_back_to_events(self, mock_build_trace, mock_trace_sources, capsys):
        """Test --output=metrics when pnl absent (falls back to consuming events)."""
        # Setup mock trace without pnl
        trace = MockTradeTrace(
            trace_id="T999",
            events=[
                MockTraceEvent("EXEC_TRADE", payload={"qty": 10}),
                MockTraceEvent("EXEC_TRADE", payload={"qty": 5}),
            ],
            exit_info={},  # No pnl
        )
        mock_build_trace.return_value = trace

        # Simulate CLI args
        test_args = [
            "tools/order_trace_cli.py",
            "--trade-id",
            "T999",
            "--logs-root",
            "./logs",
            "--output",
            "metrics",
        ]

        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                from tools.order_trace_cli import main

                main()

            assert exc_info.value.code == 0

        # Verify output
        captured = capsys.readouterr()
        output = json.loads(captured.out)

        # Should count EXEC_TRADE events as UNKNOWN (pnl-less)
        trades = output["execpos_trades_total"]
        # May have 2 entries if both events counted
        total_trades = sum(
            item["value"] for item in trades if item["labels"]["result"] == "UNKNOWN")
        assert total_trades == 2

    def test_default_output_mode_not_affected(self, mock_build_trace, mock_trace_sources, capsys):
        """Test that default text output mode is not affected by metrics changes."""
        # Setup mock trace
        trace = MockTradeTrace(
            trace_id="T111",
            events=[MockTraceEvent("EXEC_TRADE")],
            exit_info={"pnl": 10.0},
        )
        trace.entry_info = {"ts": 1000.0, "price": 50000,
                            "size": 1.0, "reason": "signal"}
        trace.exit_info = {"ts": 2000.0, "price": 50100,
                           "size": 1.0, "reason": "tp", "pnl": 100.0}

        mock_build_trace.return_value = trace

        # Simulate CLI args without --output=metrics (default text mode)
        test_args = [
            "tools/order_trace_cli.py",
            "--trade-id",
            "T111",
            "--logs-root",
            "./logs",
        ]

        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                from tools.order_trace_cli import main

                main()

            assert exc_info.value.code == 0

        # Verify output is narrative text (not metrics)
        captured = capsys.readouterr()
        assert "TRADE NARRATIVE" in captured.out
        assert "T111" in captured.out
        # Should NOT contain metrics
        assert "execpos_trades_total" not in captured.out
