from decimal import Decimal
import json
from pathlib import Path
from unittest.mock import MagicMock

import jsonschema

from apps.reference.domains.market_data.bar_aggregator import BarAggregator
from apps.reference.domains.market_data.websocket_aggregator import WebSocketAggregator


def test_websocket_aggregator_emits_fresh_trade_flow_state():
    symbol = "BTCUSDT"
    agg = WebSocketAggregator([symbol], window_seconds=60)
    t0_ms = 1_700_000_000_000

    agg.on_book_ticker(symbol, "100.0", "10.0", "101.0", "10.0", t0_ms + 100)
    agg.on_trade(symbol, "100.5", "1.25", False, t0_ms, trade_id=1)

    tick = agg.get_market_tick(symbol)

    assert tick is not None
    assert tick["trade_flow_state"] == "fresh"
    assert 0 <= tick["trade_flow_age_ms"] <= 100
    assert tick["trade_flow_last_trade_ts_ms"] == t0_ms
    assert tick["trade_flow_window_sec"] == 60


def test_websocket_aggregator_emits_degraded_when_trade_window_expires():
    symbol = "BTCUSDT"
    agg = WebSocketAggregator([symbol], window_seconds=60)
    t0_ms = 1_700_000_000_000

    agg.on_book_ticker(symbol, "100.0", "10.0", "101.0", "10.0", t0_ms)
    agg.on_trade(symbol, "100.5", "1.25", False, t0_ms, trade_id=1)
    agg.on_book_ticker(symbol, "100.2", "11.0", "101.2", "12.0", t0_ms + 61_000)

    tick = agg.get_market_tick(symbol)

    assert tick is not None
    assert tick["ts"] == t0_ms + 61_000
    assert tick["buy_volume"] == "0"
    assert tick["sell_volume"] == "0"
    assert tick["buy_count"] == 0
    assert tick["sell_count"] == 0
    assert tick["trade_flow_state"] == "degraded"
    assert tick["trade_flow_age_ms"] > tick["trade_flow_window_sec"] * 1000
    assert tick["trade_flow_last_trade_ts_ms"] == t0_ms


def test_market_tick_schema_accepts_trade_flow_metadata_and_old_payload():
    schema = json.loads(Path("schemas/market_tick_received_v1.json").read_text(encoding="utf-8"))
    payload = {
        "ts": 1_700_000_000_000,
        "symbol": "BTCUSDT",
        "price": "100.5",
        "bid": "100.0",
        "ask": "101.0",
        "mid": "100.5",
        "bid_size": "10",
        "ask_size": "10",
        "buy_volume": "1",
        "sell_volume": "0",
        "data_type": "market_tick_aggregated",
        "data_source": "websocket_live",
    }

    jsonschema.validate(payload, schema)

    payload.update(
        {
            "trade_flow_state": "fresh",
            "trade_flow_age_ms": 250,
            "trade_flow_last_trade_ts_ms": 1_700_000_000_000,
            "trade_flow_window_sec": 60,
        }
    )
    jsonschema.validate(payload, schema)


def test_bar_aggregator_preserves_and_aggregates_trade_flow_metadata():
    emit_spy = MagicMock()
    bar_agg = BarAggregator(timeframes_sec=[60], emit_fn=emit_spy)
    base_ts = 1_000_000

    bar_agg.on_tick(
        "BTCUSDT",
        Decimal("100"),
        Decimal("1"),
        base_ts,
        {
            "trade_flow_state": "fresh",
            "trade_flow_age_ms": 500,
            "trade_flow_last_trade_ts_ms": base_ts - 500,
            "trade_flow_window_sec": 60,
        },
    )
    bar_agg.on_tick(
        "BTCUSDT",
        Decimal("101"),
        Decimal("0"),
        base_ts + 10_000,
        {
            "trade_flow_state": "degraded",
            "trade_flow_age_ms": 61_000,
            "trade_flow_last_trade_ts_ms": base_ts - 500,
            "trade_flow_window_sec": 60,
        },
    )
    completed = bar_agg.on_tick(
        "BTCUSDT",
        Decimal("102"),
        Decimal("0"),
        base_ts + 25_000,
        {
            "trade_flow_state": "fresh",
            "trade_flow_age_ms": 0,
            "trade_flow_last_trade_ts_ms": base_ts + 25_000,
            "trade_flow_window_sec": 60,
        },
    )

    assert len(completed) == 1
    bar = completed[0]
    assert bar.trade_flow_state == "degraded"
    assert bar.trade_flow_age_ms == 61_000
    assert bar.trade_flow_last_trade_ts_ms == base_ts - 500
    assert bar.trade_flow_window_sec == 60

    emitted_payload = emit_spy.call_args.args[1]
    emitted_bar = emitted_payload["bar"]
    assert emitted_bar["trade_flow_state"] == "degraded"
    assert emitted_bar["trade_flow_age_ms"] == 61_000
    assert emitted_bar["trade_flow_last_trade_ts_ms"] == base_ts - 500
    assert emitted_bar["trade_flow_window_sec"] == 60
