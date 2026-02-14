from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl

from backtest_engine.engine import BacktestEngine


def test_inclusive_one_day_5m_returns_288_bars(tmp_path: Path) -> None:
    base = tmp_path / "data" / "processed" / "BTCUSDT" / "5m"
    base.mkdir(parents=True, exist_ok=True)

    ts0 = datetime(2024, 1, 1, 0, 0, 0)
    rows = []
    for i in range(289):
        ts = ts0 + timedelta(minutes=5 * i)
        rows.append(
            {
                "open_time": ts,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 10.0,
            }
        )
    pl.DataFrame(rows).write_parquet(base / "2024-01_enriched.parquet")

    engine = BacktestEngine(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 1),
        symbol_list=["BTCUSDT"],
        timeframe="5m",
        data_dir=str(tmp_path / "data" / "processed"),
    )
    engine.load_data()

    assert engine.feed is not None
    assert len(engine.feed) == 288
