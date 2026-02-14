"""
Unit tests for SL Sensitivity Compare logic.
=============================================

Tests build_compare_json and write_band_csv on synthetic data.
"""
import sys, os, json, csv, tempfile
from dataclasses import dataclass
from pathlib import Path
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backtest_engine.sl_fill_policy import SLBandRecord

# We import from the tool module
from tools.sl_fill_sensitivity import build_compare_json, write_band_csv


# ---------- synthetic BacktestResult ----------

@dataclass
class _FakeResult:
    """Minimal stand-in for BacktestResult fields used by build_compare_json."""
    start_balance: float = 1000.0
    end_balance: float = 1100.0
    total_pnl: float = 100.0
    roi_pct: float = 10.0
    max_drawdown: float = 0.05
    total_trades: int = 10
    win_rate: float = 0.6


# ---------- Tests ----------

class TestBuildCompareJson:
    def test_delta_computation(self):
        opt = _FakeResult(end_balance=1200, roi_pct=20.0, max_drawdown=0.04, total_trades=12)
        con = _FakeResult(end_balance=1050, roi_pct=5.0, max_drawdown=0.08, total_trades=12)
        band = [
            SLBandRecord(
                order_id="1", symbol="X", bar_ts=0, side="SELL",
                stop_price=100, bar_open=101, bar_high=102, bar_low=90, bar_close=95,
                fill_optimistic=99.95, fill_conservative=90.0,
                slippage_optimistic_bps=5, slippage_conservative_bps=1000,
                delta_fill_pct=0.0995,
            ),
        ]
        result = build_compare_json(opt, con, band, band, "test_run")
        assert result["run_id_base"] == "test_run"
        assert result["delta"]["end_equity"] == pytest.approx(150.0)
        assert result["delta"]["roi_pct"] == pytest.approx(15.0)
        assert result["sl_band"]["count_sl"] == 1

    def test_empty_band(self):
        opt = _FakeResult()
        con = _FakeResult()
        result = build_compare_json(opt, con, [], [], "empty")
        assert result["sl_band"]["count_sl"] == 0


class TestWriteBandCsv:
    def test_writes_file(self):
        band = [
            SLBandRecord(
                order_id="SL-1", symbol="BTCUSDT", bar_ts=123456, side="SELL",
                stop_price=27000, bar_open=27500, bar_high=27600, bar_low=24500, bar_close=24800,
                fill_optimistic=26986.5, fill_conservative=24500,
                slippage_optimistic_bps=5.0, slippage_conservative_bps=926.0,
                delta_fill_pct=0.092,
            ),
        ]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "band.csv"
            write_band_csv(band, p)
            assert p.exists()
            with open(p) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["order_id"] == "SL-1"
            assert float(rows[0]["stop_price"]) == 27000.0

    def test_empty_band(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "band.csv"
            write_band_csv([], p)
            assert p.exists()
            text = p.read_text()
            assert "no SL triggers" in text


class TestJsonSerializable:
    """Ensure compare JSON is fully JSON-serializable (no custom objects)."""
    def test_serializable(self):
        opt = _FakeResult(end_balance=1100, roi_pct=10.0, max_drawdown=0.05, total_trades=5)
        con = _FakeResult(end_balance=1050, roi_pct=5.0, max_drawdown=0.06, total_trades=5)
        band = [
            SLBandRecord(
                order_id="1", symbol="X", bar_ts=0, side="SELL",
                stop_price=100, bar_open=100, bar_high=100, bar_low=90, bar_close=95,
                fill_optimistic=99.95, fill_conservative=90.0,
                slippage_optimistic_bps=5, slippage_conservative_bps=1000,
                delta_fill_pct=0.0995,
            ),
        ]
        result = build_compare_json(opt, con, band, band, "test")
        # Must not raise
        text = json.dumps(result, default=str)
        parsed = json.loads(text)
        assert "optimistic" in parsed
        assert "conservative" in parsed
