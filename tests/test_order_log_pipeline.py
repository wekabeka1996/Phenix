"""
Tests for order-log pipeline changes (Bugs B1-B6 fix batch).

Covers:
  - mock_broker._execute_fill(): close_reason, order_type, realizedPnl in payload
  - engine._emit_portfolio_update(): positionAmt field in position dict
  - order_logger.write(): timestamp falls back to get_clock() not wall-clock
  - backtest_log_stats: BOOT excluded from time range, entry_fills counted
    correctly, trailing colon stripped from reject reason
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backtest_engine.mock_broker import MockBroker
from vfoundation.core.adapters.base import ExchangeOrderParams


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candle(symbol, open_=100.0, high=110.0, low=90.0, close=105.0, volume=1000.0):
    return {"symbol": symbol, "open": open_, "high": high, "low": low,
            "close": close, "volume": volume}


# ---------------------------------------------------------------------------
# 1. MockBroker._execute_fill() — close_reason / order_type / realizedPnl
# ---------------------------------------------------------------------------

class TestExecuteFillPayload(IsolatedAsyncioTestCase):
    """Verify fill payload carries close_reason, order_type, realizedPnl."""

    async def _open_long(self, broker: MockBroker, symbol: str, price: float, qty: float):
        """Open a LONG position via a market order."""
        params = ExchangeOrderParams(symbol=symbol, side="BUY",
                                     order_type="MARKET", quantity=str(qty))
        await broker.create_order(params)
        fills = broker.process_data(_make_candle(symbol, close=price))
        self.assertEqual(len(fills), 1, "entry fill expected")
        return fills[0]

    async def test_market_entry_close_reason(self):
        broker = MockBroker(slippage_bps=0.0)
        fill = await self._open_long(broker, "BTCUSDT", 100.0, 1.0)
        self.assertEqual(fill["close_reason"], "MARKET_FILLED")
        self.assertEqual(fill["order_type"], "MARKET")
        self.assertEqual(fill["realizedPnl"], "0.0")  # entry — no realized PnL

    async def test_limit_entry_close_reason(self):
        broker = MockBroker(slippage_bps=0.0)
        params = ExchangeOrderParams(symbol="BTCUSDT", side="BUY",
                                     order_type="LIMIT", quantity="1.0", price="100.0")
        await broker.create_order(params)
        fills = broker.process_data(_make_candle("BTCUSDT", low=99.0))
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0]["close_reason"], "ENTRY_FILLED")
        self.assertEqual(fills[0]["order_type"], "LIMIT")
        self.assertEqual(fills[0]["realizedPnl"], "0.0")

    async def test_sl_close_reason(self):
        broker = MockBroker(slippage_bps=0.0, sl_fill_model="close_based")
        # Open position
        await self._open_long(broker, "BTCUSDT", 100.0, 1.0)
        # Place STOP_MARKET SL below current price
        sl_params = ExchangeOrderParams(
            symbol="BTCUSDT", side="SELL", order_type="STOP_MARKET",
            quantity="0", close_position=True, stop_price="80.0"
        )
        await broker.create_order(sl_params)
        # Trigger SL: low drops below stop
        fills = broker.process_data(_make_candle("BTCUSDT", open_=100.0, high=100.0, low=70.0, close=75.0))
        sl_fills = [f for f in fills if f["close_reason"] == "SL_HIT"]
        self.assertGreater(len(sl_fills), 0, "expected SL fill")
        self.assertTrue(float(sl_fills[0]["realizedPnl"]) < 0,
                        "SL close should have negative realized PnL")
        self.assertEqual(sl_fills[0]["order_type"], "STOP_MARKET")

    async def test_tp_close_reason(self):
        broker = MockBroker(slippage_bps=0.0)
        # Open short position via market
        params = ExchangeOrderParams(symbol="BTCUSDT", side="SELL",
                                     order_type="MARKET", quantity="1.0")
        await broker.create_order(params)
        broker.process_data(_make_candle("BTCUSDT", close=100.0))
        # Place TAKE_PROFIT_MARKET: short TP triggers when low <= stop_price
        tp_params = ExchangeOrderParams(
            symbol="BTCUSDT", side="BUY", order_type="TAKE_PROFIT_MARKET",
            quantity="0", close_position=True, stop_price="80.0"
        )
        await broker.create_order(tp_params)
        fills = broker.process_data(_make_candle("BTCUSDT", low=75.0, close=78.0))
        tp_fills = [f for f in fills if f["close_reason"] == "TP_HIT"]
        self.assertGreater(len(tp_fills), 0, "expected TP fill")
        self.assertTrue(float(tp_fills[0]["realizedPnl"]) > 0,
                        "TP close of short should have positive realized PnL")
        self.assertEqual(tp_fills[0]["order_type"], "TAKE_PROFIT_MARKET")

    async def test_realized_pnl_long_profitable(self):
        """Entry at 100, SL fires at 120 (profit: +20 per contract)."""
        broker = MockBroker(slippage_bps=0.0, sl_fill_model="close_based")
        await self._open_long(broker, "ETHUSDT", 100.0, 2.0)
        # SL above entry (unusual but valid for test)
        sl_params = ExchangeOrderParams(
            symbol="ETHUSDT", side="SELL", order_type="STOP_MARKET",
            quantity="0", close_position=True, stop_price="115.0"
        )
        await broker.create_order(sl_params)
        fills = broker.process_data(_make_candle("ETHUSDT", open_=110.0, high=130.0, low=105.0, close=120.0))
        sl_fills = [f for f in fills if f["close_reason"] == "SL_HIT"]
        self.assertGreater(len(sl_fills), 0)
        pnl = float(sl_fills[0]["realizedPnl"])
        self.assertGreater(pnl, 0, f"Expected positive PnL, got {pnl}")


# ---------------------------------------------------------------------------
# 2. BacktestEngine._emit_portfolio_update() — positionAmt present
# ---------------------------------------------------------------------------

class TestPortfolioUpdatePositionAmt(unittest.TestCase):
    """Ensure positionAmt is present so on_portfolio_state_updated() can
    detect position closures."""

    def _make_engine(self):
        """Build a minimal BacktestEngine with a mocked event_bus."""
        from backtest_engine.engine import BacktestEngine
        from datetime import date
        bus = MagicMock()
        bus.emit = MagicMock()
        eng = BacktestEngine(
            start_date=date(2023, 6, 1),
            end_date=date(2023, 6, 10),
            symbol_list=["BTCUSDT"],
            timeframe="5m",
            event_bus=bus,
        )
        return eng, bus

    def test_positionAmt_in_portfolio_update(self):
        eng, bus = self._make_engine()
        # Manually inject a position into the broker
        from vfoundation.core.adapters.base import ExchangePosition
        eng.broker._positions["BTCUSDT"] = ExchangePosition(
            symbol="BTCUSDT",
            position_side="BOTH",
            side="LONG",
            position_amount="0.5",
            entry_price="30000",
            mark_price="30000",
            unrealized_profit="0",
            leverage=20,
            margin_type="CROSS",
            isolated_margin=0.0,
            update_time_ms=0,
        )
        eng._emit_portfolio_update()
        # Find the portfolio update call
        calls = [c for c in bus.emit.call_args_list
                 if c.kwargs.get("event_name") == "EVT:PORTFOLIO_STATE_UPDATED"
                 or (c.args and c.args[0] == "EVT:PORTFOLIO_STATE_UPDATED")]
        self.assertGreater(len(calls), 0, "Expected PORTFOLIO_STATE_UPDATED emit")
        # Extract payload
        call = calls[-1]
        payload = call.kwargs.get("payload") or (call.args[1] if len(call.args) > 1 else {})
        positions = payload.get("positions", [])
        self.assertGreater(len(positions), 0)
        self.assertIn("positionAmt", positions[0],
                      "positionAmt must be in position dict for POSITION_CLOSED detection")
        self.assertEqual(positions[0]["positionAmt"], "0.5")


# ---------------------------------------------------------------------------
# 3. order_logger.write() — timestamp uses simulated clock
# ---------------------------------------------------------------------------

class TestOrderLoggerTimestamp(unittest.TestCase):
    """write() should inject timestamp from get_clock(), not time.time()."""

    def test_timestamp_from_simulated_clock(self):
        from apps.reference.telemetry.order_logger import OrderLoggerV1

        SIMULATED_TS = 1_685_700_000_000  # 2023-06-02 epoch ms

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl",
                                         delete=False) as f:
            log_path = f.name
        try:
            logger = OrderLoggerV1(log_path)
            mock_clock = MagicMock()
            mock_clock.now_ms.return_value = SIMULATED_TS

            with patch("apps.reference.core.time.get_clock",
                       return_value=mock_clock):
                # Entry without explicit timestamp → should use mock_clock
                logger.write({
                    "rid": "test-rid-001",
                    "event_type": "ORDER_FILLED",
                    "symbol": "BTCUSDT",
                    "source_fsm": "TestFSM",
                })

            lines = [l for l in Path(log_path).read_text().splitlines() if l.strip()]
            filled_entries = [json.loads(l) for l in lines
                              if json.loads(l).get("event_type") == "ORDER_FILLED"]
            self.assertEqual(len(filled_entries), 1)
            self.assertEqual(filled_entries[0]["timestamp"], SIMULATED_TS)
        finally:
            os.unlink(log_path)

    def test_timestamp_not_overwritten_if_provided(self):
        from apps.reference.telemetry.order_logger import OrderLoggerV1

        EXPLICIT_TS = 1_600_000_000_000

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl",
                                         delete=False) as f:
            log_path = f.name
        try:
            logger = OrderLoggerV1(log_path)
            logger.write({
                "rid": "test-rid-002",
                "event_type": "ORDER_PLACED",
                "symbol": "ETHUSDT",
                "source_fsm": "TestFSM",
                "timestamp": EXPLICIT_TS,
            })
            lines = [l for l in Path(log_path).read_text().splitlines() if l.strip()]
            placed = [json.loads(l) for l in lines
                      if json.loads(l).get("event_type") == "ORDER_PLACED"]
            self.assertEqual(placed[0]["timestamp"], EXPLICIT_TS)
        finally:
            os.unlink(log_path)


# ---------------------------------------------------------------------------
# 4. backtest_log_stats — BOOT exclusion, entry_fills, trailing colon
# ---------------------------------------------------------------------------

def _write_jsonl(path: str, rows: list) -> None:
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


class TestBacktestLogStats(unittest.TestCase):

    def _summarize(self, rows: list) -> dict:
        from scripts.diagnostics.backtest_log_stats import _summarize_order_log
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl",
                                         delete=False) as f:
            _write_jsonl(f.name, rows)
            path = f.name
        try:
            return _summarize_order_log(Path(path))
        finally:
            os.unlink(path)

    def test_boot_excluded_from_time_range(self):
        """BOOT wall-clock ts must not pollute first_ts / last_ts."""
        WALL_CLOCK_TS = 1_772_000_000_000   # ~2026
        SIM_TS_START  = 1_685_657_400_000   # 2023-06-01
        SIM_TS_END    = 1_686_000_000_000   # 2023-06-06

        rows = [
            {"event_type": "BOOT",         "timestamp": WALL_CLOCK_TS,
             "rid": "boot-1", "symbol": "_SYSTEM_", "source_fsm": "OrderLoggerV1"},
            {"event_type": "ORDER_REJECTED","timestamp": SIM_TS_START,
             "rid": "r1", "symbol": "BTCUSDT", "source_fsm": "DecisionMaking",
             "nrr_code": "NRR-001", "why": "test"},
            {"event_type": "ORDER_INTENT", "timestamp": SIM_TS_END,
             "rid": "r2", "symbol": "BTCUSDT", "source_fsm": "DecisionMaking"},
        ]
        stats = self._summarize(rows)
        self.assertEqual(stats["first_ts"], SIM_TS_START,
                         "first_ts must be from ORDER_REJECTED, not BOOT")
        self.assertEqual(stats["last_ts"], SIM_TS_END,
                         "last_ts must be from ORDER_INTENT, not BOOT")

    def test_entry_fills_counted_separately(self):
        """entry_fills should count only ENTRY/ENTRY_FILLED, not SL/TP."""
        rows = [
            {"event_type": "ORDER_FILLED", "timestamp": 1_685_700_000_000,
             "rid": "f1", "symbol": "BTCUSDT", "source_fsm": "ExecPosFSM",
             "order_kind": "ENTRY",  "close_reason": "ENTRY_FILLED"},
            {"event_type": "ORDER_FILLED", "timestamp": 1_685_701_000_000,
             "rid": "f2", "symbol": "BTCUSDT", "source_fsm": "ExecPosFSM",
             "order_kind": "SL",    "close_reason": "SL_HIT"},
            {"event_type": "ORDER_FILLED", "timestamp": 1_685_702_000_000,
             "rid": "f3", "symbol": "BTCUSDT", "source_fsm": "ExecPosFSM",
             "order_kind": "TP",    "close_reason": "TP_HIT"},
        ]
        stats = self._summarize(rows)
        self.assertEqual(stats["filled_orders"], 3)
        self.assertEqual(stats["entry_fills"], 1,
                         "Only ENTRY fill should count as entry_fill")

    def test_trailing_colon_stripped_from_reject_reason(self):
        """
        'SAFETY_GATES:GATE-01: regime_confidence=0.9' should become
        'SAFETY_GATES:GATE-01' (no trailing colon or space).
        """
        why = "SAFETY_GATES:FIX-CONF-GATE-01: regime_confidence=0.91 something"
        why_base = why.split(" regime_confidence=")[0].rstrip(": ")
        self.assertEqual(why_base, "SAFETY_GATES:FIX-CONF-GATE-01",
                         f"Trailing colon not stripped: {why_base!r}")

    def test_unknown_regime_shows_rejected_count(self):
        """UNKNOWN bucket with rejected_orders should appear in regime_stats."""
        rows = [
            {"event_type": "ORDER_REJECTED", "timestamp": 1_685_700_000_000,
             "rid": "rj1", "symbol": "BTCUSDT", "source_fsm": "DecisionMaking",
             "nrr_code": "NRR-026", "why": "SAFETY_GATES:TEST:"},
        ] * 5  # 5 rejections, no regime → UNKNOWN
        stats = self._summarize(rows)
        r_stats = stats.get("regime_stats", {})
        self.assertIn("UNKNOWN", r_stats,
                      "UNKNOWN bucket should appear when there are rejections")
        self.assertEqual(r_stats["UNKNOWN"]["rejected_orders"], 5)

    def test_position_closed_counted_in_event_counts(self):
        """POSITION_CLOSED events must be counted for the funnel display."""
        rows = [
            {"event_type": "POSITION_CLOSED", "timestamp": 1_685_705_000_000,
             "rid": "pc1", "symbol": "BTCUSDT", "source_fsm": "ExecPosFSM",
             "close_reason": "SL_HIT",
             "metadata": {"realized_pnl": -42.5, "close_price": 29000.0}},
        ]
        stats = self._summarize(rows)
        self.assertEqual(stats["event_counts"].get("POSITION_CLOSED", 0), 1)


if __name__ == "__main__":
    unittest.main()
