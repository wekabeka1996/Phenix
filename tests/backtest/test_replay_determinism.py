from datetime import datetime, date
from unittest.mock import MagicMock

import polars as pl

from backtest_engine.engine import BacktestEngine


class _EventBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict, str]] = []

    def emit(self, event_name=None, payload=None, why=None, data_ref=None, **kwargs):
        name = event_name if event_name is not None else kwargs.get("event_name")
        pld = payload if payload is not None else kwargs.get("payload")
        reason = why if why is not None else kwargs.get("why")
        if name is None:
            return
        self.events.append((name, pld or {}, reason or ""))


def _run_once() -> list[dict]:
    bus = _EventBus()
    engine = BacktestEngine(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 1),
        symbol_list=["BTCUSDT"],
        timeframe="1h",
        event_bus=bus,
        data_dir="/tmp/data",
        initial_balance=10000.0,
    )

    engine.feed = pl.DataFrame(
        {
            "ts": [datetime(2024, 1, 1, 0, 0, 0)],
            "symbol": ["BTCUSDT"],
            "open": [49000.0],
            "high": [51000.0],
            "low": [48000.0],
            "close": [50000.0],
            "volume": [1000.0],
        }
    )

    fill = {
        "order_id": "det-001",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "price": 50000.0,
        "quantity": 0.1,
        "fee": "5.0",
        "timestamp": 1704067200000,
    }
    broker = MagicMock()
    broker.process_data.return_value = [fill]
    engine.broker = broker

    engine.run(max_ticks=1)

    return [pld for name, pld, _ in bus.events if name == "EVT:TRADE_EXECUTED"]


def test_two_runs_produce_identical_trade_executed_events() -> None:
    trades_1 = _run_once()
    trades_2 = _run_once()

    assert trades_1 == trades_2