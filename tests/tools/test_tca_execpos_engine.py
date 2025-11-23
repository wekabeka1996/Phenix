"""
Tests for TCA Engine
====================
"""
import pytest
from apps.reference.tools.tca_execpos.engine import TCAEngine
from apps.reference.tools.order_trace.types import TraceEvent


@pytest.fixture
def engine():
    return TCAEngine()


def test_tca_engine_basic_flow(engine):
    """Test basic flow with one order and one trade."""
    events = [
        TraceEvent(
            ts=1000.0,
            source="WAL",
            event_type="EXEC_ORDER",
            payload={
                "order_id": "ord1",
                "symbol": "BTCUSDT",
                "status": "PLACED",
                "type": "LIMIT",
                "price": "50000",
                "qty": "1.0",
                "client_order_id": "cid1"
            }
        ),
        TraceEvent(
            ts=1000.5,
            source="WAL",
            event_type="EXEC_TRADE",
            payload={
                "trade_id": "trd1",
                "order_id": "ord1",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "1.0",
                "price": "50000",
                "fee": "5.0",
                "role": "ENTRY"
            }
        )
    ]

    records, summaries, canonical_metrics = engine.compute_metrics(events)

    assert len(records) == 1
    r = records[0]
    assert r.trade_id == "trd1"
    assert r.order_id == "ord1"
    assert r.symbol == "BTCUSDT"
    assert r.side == "BUY"
    assert r.qty == 1.0
    assert r.exec_price == 50000.0
    assert r.fee == 5.0
    assert r.time_to_fill_ms == 500.0
    assert r.slippage_bps == 0.0  # Limit price matched exec price
    assert r.client_order_id == "cid1"

    assert len(summaries) == 2  # BTCUSDT + GLOBAL
    s = summaries[0]
    assert s.scope == "BTCUSDT"
    assert s.total_volume == 50000.0
    assert s.total_fees == 5.0
    assert s.trade_count == 1
    assert s.avg_slippage_bps == 0.0
    assert s.avg_time_to_fill_ms == 500.0


def test_tca_engine_slippage_buy(engine):
    """Test slippage calculation for BUY order (Market)."""
    # BUY: Exec > Ref is BAD (Negative slippage?)
    # Wait, logic in engine:
    # if side == "BUY": diff = ref_price - price (Lower is better)
    # If Ref=50000, Exec=50100 (Worse price) -> 50000 - 50100 = -100.
    # Slippage = -100 / 50000 = -0.002 = -20 bps. Correct.

    events = [
        TraceEvent(
            ts=1000.0,
            source="WAL",
            event_type="EXEC_ORDER",
            payload={
                "order_id": "ord1",
                "symbol": "BTCUSDT",
                "status": "PLACED",
                "type": "LIMIT",
                # Using price as ref for test simplicity (simulating mark price)
                "price": "50000"
            }
        ),
        TraceEvent(
            ts=1000.1,
            source="WAL",
            event_type="EXEC_TRADE",
            payload={
                "trade_id": "trd1",
                "order_id": "ord1",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "1.0",
                "price": "50100",  # Worse price
                "fee": "5.0"
            }
        )
    ]

    records, _, _ = engine.compute_metrics(events)
    r = records[0]
    assert r.ref_price == 50000.0
    assert r.exec_price == 50100.0
    assert r.slippage_bps == -20.0


def test_tca_engine_slippage_sell(engine):
    """Test slippage calculation for SELL order."""
    # SELL: Exec < Ref is BAD (Negative slippage)
    # Ref=50000, Exec=49900 (Worse) -> 49900 - 50000 = -100.
    # Slippage = -100 / 50000 = -20 bps. Correct.

    events = [
        TraceEvent(
            ts=1000.0,
            source="WAL",
            event_type="EXEC_ORDER",
            payload={
                "order_id": "ord1",
                "symbol": "BTCUSDT",
                "status": "PLACED",
                "type": "LIMIT",
                "price": "50000"
            }
        ),
        TraceEvent(
            ts=1000.1,
            source="WAL",
            event_type="EXEC_TRADE",
            payload={
                "trade_id": "trd1",
                "order_id": "ord1",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "qty": "1.0",
                # Worse price (e.g. limit filled lower? unlikely for limit but possible for market)
                "price": "49900",
                "fee": "5.0"
            }
        )
    ]

    records, _, _ = engine.compute_metrics(events)
    r = records[0]
    assert r.slippage_bps == -20.0


def test_tca_engine_partial_fills(engine):
    """Test partial fills aggregation."""
    events = [
        TraceEvent(
            ts=1000.0,
            source="WAL",
            event_type="EXEC_ORDER",
            payload={"order_id": "ord1", "symbol": "BTCUSDT",
                     "status": "PLACED", "type": "LIMIT", "price": "50000"}
        ),
        TraceEvent(
            ts=1000.1,
            source="WAL",
            event_type="EXEC_TRADE",
            payload={"trade_id": "trd1", "order_id": "ord1", "symbol": "BTCUSDT",
                     "side": "BUY", "qty": "0.5", "price": "50000", "fee": "2.5"}
        ),
        TraceEvent(
            ts=1000.2,
            source="WAL",
            event_type="EXEC_TRADE",
            payload={"trade_id": "trd2", "order_id": "ord1", "symbol": "BTCUSDT",
                     "side": "BUY", "qty": "0.5", "price": "50000", "fee": "2.5"}
        )
    ]

    records, summaries, canonical_metrics = engine.compute_metrics(events)
    assert len(records) == 2

    s = summaries[0]
    assert s.total_volume == 50000.0  # 0.5*50000 + 0.5*50000
    assert s.total_fees == 5.0
    assert s.trade_count == 2


def test_tca_can_produce_execpos_metrics(engine):
    """Test TCA produces canonical execpos_* counters."""
    events = [
        TraceEvent(
            ts=1000.0,
            source="WAL",
            event_type="EXEC_ORDER",
            payload={"order_id": "ord1", "symbol": "BTCUSDT",
                     "status": "PLACED", "type": "LIMIT", "price": "50000"}
        ),
        TraceEvent(
            ts=1000.1,
            source="WAL",
            event_type="EXEC_TRADE",
            payload={"trade_id": "trd1", "order_id": "ord1", "symbol": "BTCUSDT",
                     "side": "BUY", "qty": "1.0", "price": "50000", "fee": "5.0"}
        ),
        TraceEvent(
            ts=1000.2,
            source="WAL",
            event_type="EXEC_TRADE",
            payload={"trade_id": "trd2", "order_id": "ord2", "symbol": "ETHUSDT",
                     "side": "SELL", "qty": "10.0", "price": "3000", "fee": "3.0"}
        )
    ]

    records, summaries, canonical_metrics = engine.compute_metrics(events)

    # Verify canonical_metrics structure
    assert "counters" in canonical_metrics
    assert "prometheus" in canonical_metrics

    # Verify counters dict has execpos_trades_total
    counters = canonical_metrics["counters"]
    assert "execpos_trades_total" in counters

    trades = counters["execpos_trades_total"]
    assert len(trades) == 1  # All trades map to UNKNOWN/TCA (pnl-less)

    # Verify label structure
    trade_entry = trades[0]
    assert trade_entry["labels"]["result"] == "UNKNOWN"
    assert trade_entry["labels"]["source"] == "TCA"
    assert trade_entry["value"] == 2  # 2 trades

    # Verify Prometheus text format
    prom_text = canonical_metrics["prometheus"]
    assert isinstance(prom_text, str)
    assert 'execpos_trades_total{result="UNKNOWN",source="TCA"} 2' in prom_text
