"""Phase 0.7 — BacktestEngine DataContract integration tests.

Validates that _validate_ohlcv_contract() (unit) and BacktestEngine.load_data()
(integration) both fail-fast on OHLCV contract violations.

Test structure:
  TestValidateOhlcvContractUnit  — 6 tests (direct helper calls)
  TestLoadDataContractIntegration — 3 tests (full engine parquet round-trip)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from backtest_engine.engine import _validate_ohlcv_contract, BacktestEngine


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_valid_frame(n: int = 10) -> pl.DataFrame:
    """Minimal valid post-select polars frame (engine columns: ts/open/high/low/close/volume)."""
    ts0 = datetime(2024, 1, 1)
    return pl.DataFrame(
        {
            "ts": [ts0 + timedelta(minutes=5 * i) for i in range(n)],
            "open": [100.0 + i for i in range(n)],
            "high": [102.0 + i for i in range(n)],
            "low": [98.0 + i for i in range(n)],
            "close": [101.0 + i for i in range(n)],
            "volume": [1000.0] * n,
        }
    )


def _make_parquet(tmp_path: Path, rows: list[dict], filename: str = "2024-01_enriched.parquet") -> Path:
    """Write minimal OHLCV parquet to tmp_path under symbol/timeframe dir structure."""
    base = tmp_path / "data" / "processed" / "BTCUSDT" / "5m"
    base.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(base / filename)
    return base / filename


def _valid_ohlcv_rows(n: int = 20) -> list[dict]:
    ts0 = datetime(2024, 1, 1)
    return [
        {
            "open_time": ts0 + timedelta(minutes=5 * i),
            "open": 100.0,
            "high": 102.0,
            "low": 98.0,
            "close": 101.0,
            "volume": 500.0,
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Unit: _validate_ohlcv_contract()
# ---------------------------------------------------------------------------

class TestValidateOhlcvContractUnit:
    """Direct unit tests for _validate_ohlcv_contract()."""

    def test_valid_frame_passes(self) -> None:
        """A well-formed frame must pass without raising."""
        frame = _make_valid_frame()
        _validate_ohlcv_contract(frame, symbol="BTCUSDT")  # no exception

    def test_missing_column_raises(self) -> None:
        """Drop a required column → ValueError."""
        frame = _make_valid_frame().drop("volume")
        with pytest.raises(ValueError, match="missing columns"):
            _validate_ohlcv_contract(frame, symbol="BTCUSDT")

    def test_null_in_close_raises(self) -> None:
        """Introduce a null into close → nullable=False violation."""
        frame = _make_valid_frame()
        # Replace first close with null
        frame = frame.with_columns(
            pl.when(pl.int_range(pl.len()) == 0)
            .then(None)
            .otherwise(pl.col("close"))
            .alias("close")
        )
        with pytest.raises(ValueError, match="DataContract violation"):
            _validate_ohlcv_contract(frame, symbol="BTCUSDT")

    def test_high_less_than_low_raises(self) -> None:
        """OHLCV semantic invariant: high >= low must hold."""
        frame = _make_valid_frame()
        # Swap high and low so high < low on all rows
        frame = frame.with_columns(
            pl.col("low").alias("high"),
            pl.col("high").alias("low"),
        )
        with pytest.raises(ValueError, match="high < low"):
            _validate_ohlcv_contract(frame, symbol="BTCUSDT")

    def test_negative_volume_raises(self) -> None:
        """Negative volume violates the OHLCV contract."""
        frame = _make_valid_frame()
        frame = frame.with_columns(
            pl.when(pl.int_range(pl.len()) == 0)
            .then(-1.0)
            .otherwise(pl.col("volume"))
            .alias("volume")
        )
        with pytest.raises(ValueError, match="volume < 0"):
            _validate_ohlcv_contract(frame, symbol="BTCUSDT")

    def test_single_row_valid_passes(self) -> None:
        """Edge-case: single row with perfect OHLCV values passes."""
        frame = pl.DataFrame(
            {
                "ts": [datetime(2024, 6, 1)],
                "open": [100.0],
                "high": [100.0],
                "low": [100.0],
                "close": [100.0],
                "volume": [0.0],
            }
        )
        _validate_ohlcv_contract(frame, symbol="ETHUSDT")  # no exception


# ---------------------------------------------------------------------------
# Integration: BacktestEngine.load_data()
# ---------------------------------------------------------------------------

class TestLoadDataContractIntegration:
    """load_data() must propagate DataContract ValueError as fatal error."""

    def test_valid_parquet_loads_successfully(self, tmp_path: Path) -> None:
        """Golden path: valid parquet file loads without error."""
        _make_parquet(tmp_path, _valid_ohlcv_rows(20))

        engine = BacktestEngine(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            symbol_list=["BTCUSDT"],
            timeframe="5m",
            data_dir=str(tmp_path / "data" / "processed"),
        )
        engine.load_data()
        assert engine.feed is not None

    def test_high_less_than_low_in_parquet_raises(self, tmp_path: Path) -> None:
        """Parquet with high < low must cause load_data() to raise ValueError."""
        bad_rows = _valid_ohlcv_rows(10)
        # Corrupt one row: swap high and low
        bad_rows[0]["high"], bad_rows[0]["low"] = bad_rows[0]["low"] - 1, bad_rows[0]["high"] + 1
        _make_parquet(tmp_path, bad_rows)

        engine = BacktestEngine(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            symbol_list=["BTCUSDT"],
            timeframe="5m",
            data_dir=str(tmp_path / "data" / "processed"),
        )
        with pytest.raises(ValueError, match="DataContract violation"):
            engine.load_data()

    def test_null_close_in_parquet_raises(self, tmp_path: Path) -> None:
        """Parquet with null close values must cause load_data() to raise ValueError."""
        rows = _valid_ohlcv_rows(10)
        # polars will honour None for Float64
        rows[3]["close"] = None
        _make_parquet(tmp_path, rows)

        engine = BacktestEngine(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            symbol_list=["BTCUSDT"],
            timeframe="5m",
            data_dir=str(tmp_path / "data" / "processed"),
        )
        with pytest.raises(ValueError, match="DataContract violation"):
            engine.load_data()
