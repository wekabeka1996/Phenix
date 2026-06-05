"""
Tests: MR strategy None-resampler guards (T2B-02).

Verifies that force_close_all, reset_symbol, reset_all do NOT crash
when resampler is None (which is always the case in production SSOT mode).
"""

import pytest
from decimal import Decimal
from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MeanReversion1mStrategy,
    MRStrategyConfig,
)
from apps.reference.domains.feature_engineering.bar_resampler import Bar


def _make_strategy() -> MeanReversion1mStrategy:
    """Create a strategy instance in SSOT mode (resampler=None by default)."""
    config = MRStrategyConfig()
    return MeanReversion1mStrategy(config)


def _make_bar(symbol: str = "BTCUSDT") -> Bar:
    """Create a minimal Bar for testing."""
    ts = 1_700_000_000_000
    return Bar(
        symbol=symbol,
        timeframe_sec=60,
        open=Decimal("30000"),
        high=Decimal("30100"),
        low=Decimal("29900"),
        close=Decimal("30050"),
        volume=Decimal("1.5"),
        trade_count=10,
        start_ts_ms=ts,
        end_ts_ms=ts + 60_000,
    )


class TestResetSymbolNoResampler:
    """reset_symbol() must not crash when resampler is None."""

    def test_reset_symbol_no_resampler_no_state(self):
        """reset_symbol on unknown symbol is a no-op, no crash."""
        strategy = _make_strategy()
        strategy.reset_symbol("BTCUSDT")  # symbol not in _states yet

    def test_reset_symbol_no_resampler_with_state(self):
        """reset_symbol after state was created must not crash."""
        strategy = _make_strategy()
        # Force state creation via on_bar
        strategy.on_bar("BTCUSDT", _make_bar(), timestamp_ms=1_700_000_000_000)
        assert "BTCUSDT" in strategy._states

        # Confirm resampler is None (SSOT mode)
        assert strategy._states["BTCUSDT"].resampler is None

        # Must not raise AttributeError
        strategy.reset_symbol("BTCUSDT")

        # State should be cleared
        assert strategy._states["BTCUSDT"].bars == []

    def test_reset_symbol_clears_regime_and_atr(self):
        """reset_symbol also clears regime and atr_pct caches."""
        strategy = _make_strategy()
        strategy.set_regime("BTCUSDT", "FLAT_LOW")
        strategy._atr_pct["BTCUSDT"] = Decimal("0.01")
        strategy.on_bar("BTCUSDT", _make_bar(), timestamp_ms=1_700_000_000_000)

        strategy.reset_symbol("BTCUSDT")

        assert "BTCUSDT" not in strategy._regimes
        assert "BTCUSDT" not in strategy._atr_pct


class TestResetAllNoResampler:
    """reset_all() must not crash when all resamplers are None."""

    def test_reset_all_empty(self):
        """reset_all with no symbols is a no-op."""
        strategy = _make_strategy()
        strategy.reset_all()  # should not crash

    def test_reset_all_single_symbol(self):
        """reset_all with one symbol must not crash."""
        strategy = _make_strategy()
        strategy.on_bar("BTCUSDT", _make_bar(), timestamp_ms=1_700_000_000_000)
        assert strategy._states["BTCUSDT"].resampler is None

        strategy.reset_all()

        assert strategy._states["BTCUSDT"].bars == []
        assert strategy._regimes == {}
        assert strategy._atr_pct == {}

    def test_reset_all_multiple_symbols(self):
        """reset_all with multiple symbols must not crash."""
        strategy = _make_strategy()
        ts = 1_700_000_000_000
        strategy.on_bar("BTCUSDT", _make_bar("BTCUSDT"), timestamp_ms=ts)
        strategy.on_bar("ETHUSDT", _make_bar("ETHUSDT"), timestamp_ms=ts)

        # Confirm all resamplers are None
        for sym in ("BTCUSDT", "ETHUSDT"):
            assert strategy._states[sym].resampler is None

        strategy.reset_all()  # must not raise

        for sym in ("BTCUSDT", "ETHUSDT"):
            assert strategy._states[sym].bars == []


class TestForceCloseAllNoResampler:
    """force_close_all() must return {symbol: None} without crashing."""

    def test_force_close_all_empty(self):
        """force_close_all with no symbols returns empty dict."""
        strategy = _make_strategy()
        result = strategy.force_close_all(timestamp_ms=1_700_000_000_000)
        assert result == {}

    def test_force_close_all_returns_none_per_symbol(self):
        """force_close_all returns {symbol: None} when resampler is None."""
        strategy = _make_strategy()
        ts = 1_700_000_000_000
        strategy.on_bar("BTCUSDT", _make_bar("BTCUSDT"), timestamp_ms=ts)
        assert strategy._states["BTCUSDT"].resampler is None

        result = strategy.force_close_all(timestamp_ms=ts)

        assert "BTCUSDT" in result
        assert result["BTCUSDT"] is None

    def test_force_close_all_multiple_symbols_all_none(self):
        """force_close_all with multiple symbols all return None."""
        strategy = _make_strategy()
        ts = 1_700_000_000_000
        symbols = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
        for sym in symbols:
            strategy.on_bar(sym, _make_bar(sym), timestamp_ms=ts)

        result = strategy.force_close_all(timestamp_ms=ts)

        assert set(result.keys()) == set(symbols)
        for sym in symbols:
            assert result[sym] is None, f"Expected None for {sym}, got {result[sym]}"


class TestOnTickRemoved:
    """Verify on_tick is no longer part of the public API."""

    def test_on_tick_not_defined(self):
        """MeanReversion1mStrategy must not have on_tick method (T2B-02 cleanup)."""
        strategy = _make_strategy()
        assert not hasattr(strategy, "on_tick"), (
            "on_tick() should have been removed (T2B-02). "
            "Use on_bar() via EVT:BAR_CLOSED instead."
        )
