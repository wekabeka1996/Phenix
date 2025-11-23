from decimal import Decimal

from apps.reference.tools.execpos_metrics_aggregator import (
    ExecPosMetricsAggregator,
    summarize_trace_metrics,
)
from apps.reference.tools.tca_execpos.engine import TCAEngine
from apps.reference.tools.tca_execpos.model import ExecPosTCATradeRecord
from apps.reference.tools.order_trace.types import TraceEvent, TradeTrace


def test_execpos_metrics_aggregator_basic_counts():
    agg = ExecPosMetricsAggregator()

    agg.add_trade(result="win", source="tca")
    agg.add_bracket_violation(severity="ALERT", kind="MISSING_SL")
    agg.add_watchdog_alert(severity="WARN", kind="ORPHAN_SL")
    agg.add_trailing_signal(kind="EXIT")

    data = agg.to_dict()

    assert {"labels": {"result": "WIN", "source": "TCA"}, "value": 1} in data["execpos_trades_total"]
    assert {"labels": {"severity": "ALERT", "kind": "MISSING_SL"}, "value": 1} in data["execpos_bracket_violations_total"]
    assert {"labels": {"severity": "WARN", "kind": "ORPHAN_SL"}, "value": 1} in data["execpos_watchdog_alerts_total"]
    assert {"labels": {"kind": "EXIT"}, "value": 1} in data["execpos_trailing_signals_total"]


def test_summarize_trace_metrics_consumes_events_and_pnl():
    trace = TradeTrace(trace_id="rid1", symbol="BTCUSDT", direction="LONG", exit_info={"pnl": 10})
    trace.events = [
        TraceEvent(ts=1.0, source="runtime", event_type="EXEC_TRADE", payload={"qty": "1", "price": "100"}),
        TraceEvent(ts=2.0, source="runtime", event_type="WATCHDOG_ALERT", payload={"severity": "ALERT", "kind": "MISSING_SL"}),
        TraceEvent(ts=3.0, source="runtime", event_type="TRAILING_SL_UPDATED", payload={"kind": "EXIT"}),
    ]

    agg = summarize_trace_metrics(trace)
    data = agg.to_dict()

    assert any(item["labels"]["result"] == "WIN" for item in data["execpos_trades_total"])
    assert {"labels": {"severity": "ALERT", "kind": "MISSING_SL"}, "value": 1} in data["execpos_watchdog_alerts_total"]
    assert {"labels": {"kind": "EXIT"}, "value": 1} in data["execpos_trailing_signals_total"]


def test_tca_engine_outputs_canonical_metrics():
    # Build minimal TraceEvents for TCA
    order_event = TraceEvent(
        ts=1.0,
        source="runtime",
        event_type="EXEC_ORDER",
        payload={"order_id": "o1", "symbol": "BTCUSDT", "type": "LIMIT", "price": "100", "side": "BUY", "status": "PLACED"},
    )
    trade_event = TraceEvent(
        ts=2.0,
        source="runtime",
        event_type="EXEC_TRADE",
        payload={"trade_id": "t1", "order_id": "o1", "symbol": "BTCUSDT", "side": "BUY", "qty": "1", "price": "99", "fee": "0"},
    )

    engine = TCAEngine()
    records, summaries, metrics = engine.compute_metrics([order_event, trade_event])

    assert len(records) == 1
    assert summaries
    counters = metrics["counters"]["execpos_trades_total"]
    assert counters and counters[0]["value"] == 1
