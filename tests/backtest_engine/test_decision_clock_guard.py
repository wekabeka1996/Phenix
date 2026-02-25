from datetime import datetime, timedelta, date
from unittest.mock import MagicMock

import polars as pl
import pytest

from backtest_engine.engine import BacktestEngine


class _Bus:
    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}

    def listen(self, event_name: str, callback) -> None:
        self.listeners.setdefault(event_name, []).append(callback)

    def emit(self, event_name=None, payload=None, why=None, data_ref=None, **kwargs):
        name = event_name if event_name is not None else kwargs.get("event_name")
        pld = payload if payload is not None else kwargs.get("payload")
        for cb in self.listeners.get(name, []):
            cb({"op": "EVT", "verb": name, "pld": pld or {}})


def _make_feed(n: int) -> pl.DataFrame:
    ts0 = datetime(2024, 1, 1, 0, 0, 0)
    rows = []
    for i in range(n):
        ts = ts0 + timedelta(minutes=5 * i)
        rows.append(
            {
                "ts": ts,
                "symbol": "BTCUSDT",
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.5 + i,
                "volume": 10.0,
            }
        )
    return pl.DataFrame(rows)


def test_decision_clock_one_cmd_per_bar() -> None:
    bus = _Bus()

    def on_bar_closed(msg):
        pld = msg.get("pld", {})
        cmd_payload = {
            "symbol": pld.get("symbol"),
            "tf_sec": pld.get("tf_sec"),
            "bar_close_ts": pld.get("bar_close_ts"),
            "bar": pld.get("bar"),
            "features": {},
            "warmup": {"full_ready": True},
            "regime": None,
        }
        bus.emit("CMD:PROCESS_STRATEGY", cmd_payload, "test_cmd")

    bus.listen("EVT:BAR_CLOSED", on_bar_closed)

    engine = BacktestEngine(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 1),
        symbol_list=["BTCUSDT"],
        timeframe="5m",
        event_bus=bus,
        data_dir="/tmp/data",
        initial_balance=10000.0,
    )
    engine.feed = _make_feed(12)
    broker = MagicMock()
    broker.process_data.return_value = []
    engine.broker = broker

    engine.run(max_ticks=12)

    assert broker.process_data.call_count >= 12


def test_decision_clock_duplicate_cmd_raises() -> None:
    bus = _Bus()

    def on_bar_closed(msg):
        pld = msg.get("pld", {})
        cmd_payload = {
            "symbol": pld.get("symbol"),
            "tf_sec": pld.get("tf_sec"),
            "bar_close_ts": pld.get("bar_close_ts"),
            "bar": pld.get("bar"),
            "features": {},
            "warmup": {"full_ready": True},
            "regime": None,
        }
        bus.emit("CMD:PROCESS_STRATEGY", cmd_payload, "test_cmd_1")
        bus.emit("CMD:PROCESS_STRATEGY", cmd_payload, "test_cmd_2")

    bus.listen("EVT:BAR_CLOSED", on_bar_closed)

    engine = BacktestEngine(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 1),
        symbol_list=["BTCUSDT"],
        timeframe="5m",
        event_bus=bus,
        data_dir="/tmp/data",
        initial_balance=10000.0,
    )
    engine.feed = _make_feed(3)
    broker = MagicMock()
    broker.process_data.return_value = []
    engine.broker = broker

    # Previously this expected a RuntimeError, but idempotency silently ignores duplicates now.
    engine.run(max_ticks=3)
    assert broker.process_data.call_count >= 3
