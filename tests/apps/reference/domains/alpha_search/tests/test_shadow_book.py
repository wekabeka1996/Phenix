"""
T2: Shadow Book Tests
=====================

Tests for apps/reference/domains/alpha_search/runtime/shadow_book.py
12 tests covering PnL calculations, drawdown, Sharpe ratio, metrics.
"""

import math
import pytest

from apps.reference.domains.alpha_search.runtime.shadow_book import ShadowBook


@pytest.mark.unit
class TestRecordTrade:

    def test_buy_profit(self):
        """BUY: exit > entry = positive PnL."""
        book = ShadowBook("S1", notional_size=1000.0)
        trade = book.record_trade(
            "BTC", "BUY", 100.0, 110.0, 0, 1, 5, "aurora")
        assert trade.pnl == pytest.approx(100.0)  # (110-100)/100 * 1000

    def test_buy_loss(self):
        """BUY: exit < entry = negative PnL."""
        book = ShadowBook("S1", notional_size=1000.0)
        trade = book.record_trade("BTC", "BUY", 100.0, 90.0, 0, 1, 5, "aurora")
        assert trade.pnl == pytest.approx(-100.0)

    def test_sell_profit(self):
        """SELL: exit < entry = positive PnL."""
        book = ShadowBook("S1", notional_size=1000.0)
        trade = book.record_trade(
            "BTC", "SELL", 100.0, 90.0, 0, 1, 5, "aurora")
        assert trade.pnl == pytest.approx(100.0)

    def test_sell_loss(self):
        """SELL: exit > entry = negative PnL."""
        book = ShadowBook("S1", notional_size=1000.0)
        trade = book.record_trade(
            "BTC", "SELL", 100.0, 110.0, 0, 1, 5, "aurora")
        assert trade.pnl == pytest.approx(-100.0)


@pytest.mark.unit
class TestMetrics:

    def test_cumulative_pnl_accumulates(self):
        """Multiple trades sum correctly."""
        book = ShadowBook("S1", notional_size=1000.0)
        book.record_trade("BTC", "BUY", 100.0, 110.0, 0, 1, 1, "a")  # +100
        book.record_trade("BTC", "BUY", 100.0, 105.0, 1, 2, 1, "a")  # +50
        book.record_trade("BTC", "BUY", 100.0, 95.0, 2, 3, 1, "a")   # -50
        assert book.cumulative_pnl == pytest.approx(100.0)

    def test_max_drawdown(self):
        """Peak -> valley tracking for max drawdown."""
        book = ShadowBook("S1", notional_size=1000.0)
        book.record_trade("BTC", "BUY", 100.0, 120.0, 0,
                          1, 1, "a")  # +200, peak=200
        book.record_trade("BTC", "BUY", 100.0, 85.0, 1, 2,
                          1, "a")   # -150, cum=50, dd=150
        book.record_trade("BTC", "BUY", 100.0, 90.0, 2, 3,
                          1, "a")   # -100, cum=-50, dd=250
        assert book._max_drawdown == pytest.approx(250.0)

    def test_sharpe_positive(self):
        """Varying profits yield positive Sharpe."""
        book = ShadowBook("S1", notional_size=1000.0)
        # Varying exit prices to create non-zero std dev with positive mean
        exits = [103.0, 107.0, 104.0, 108.0, 105.0,
                 106.0, 109.0, 102.0, 110.0, 104.0]
        for exit_price in exits:
            book.record_trade("BTC", "BUY", 100.0, exit_price,
                              0, 1, 1, "a")
        metrics = book.get_metrics()
        assert metrics["sharpe_ratio"] > 0

    def test_sharpe_zero_variance(self):
        """All same PnL -> Sharpe = 0 (zero std)."""
        book = ShadowBook("S1", notional_size=1000.0)
        for _ in range(5):
            book.record_trade("BTC", "BUY", 100.0, 110.0, 0, 1, 1, "a")
        # All same PnL = zero variance -> sharpe = 0
        assert book._calc_sharpe() == 0.0

    def test_sharpe_insufficient_data(self):
        """< 2 trades -> Sharpe = 0."""
        book = ShadowBook("S1")
        assert book._calc_sharpe() == 0.0
        book.record_trade("BTC", "BUY", 100.0, 110.0, 0, 1, 1, "a")
        assert book._calc_sharpe() == 0.0

    def test_get_metrics_keys(self):
        """All expected keys present in metrics."""
        book = ShadowBook("S1")
        m = book.get_metrics()
        expected = {"scenario_id", "total_trades", "wins", "losses", "win_rate",
                    "cumulative_pnl", "max_drawdown", "sharpe_ratio",
                    "avg_pnl_per_trade", "notional_size"}
        assert expected == set(m.keys())

    def test_win_rate(self):
        """Win rate = wins / total."""
        book = ShadowBook("S1", notional_size=1000.0)
        book.record_trade("BTC", "BUY", 100.0, 110.0, 0, 1, 1, "a")  # win
        book.record_trade("BTC", "BUY", 100.0, 110.0, 0, 1, 1, "a")  # win
        book.record_trade("BTC", "BUY", 100.0, 90.0, 0, 1, 1, "a")   # loss
        m = book.get_metrics()
        assert m["win_rate"] == pytest.approx(2 / 3, abs=0.001)

    def test_notional_scales_pnl(self):
        """Different notional produces proportional PnL."""
        book1 = ShadowBook("S1", notional_size=1000.0)
        book2 = ShadowBook("S2", notional_size=2000.0)
        t1 = book1.record_trade("BTC", "BUY", 100.0, 110.0, 0, 1, 1, "a")
        t2 = book2.record_trade("BTC", "BUY", 100.0, 110.0, 0, 1, 1, "a")
        assert t2.pnl == pytest.approx(t1.pnl * 2)
