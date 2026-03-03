"""
Contract test: MeanReversion1mStrategy reset/force_close methods are safe when resampler is None.

MR-NONE-RESAMPLER-CONTRACT-01:
T2B-02 migrated MR strategy to bar-driven (SSOT). All states are created with
resampler=None (line 279 in mean_reversion_strategy.py). Three public methods
previously crashed with AttributeError when called:

  - force_close_all()  → state.resampler.force_close(...)  # AttributeError
  - reset_symbol()     → self._states[symbol].resampler.reset()  # AttributeError
  - reset_all()        → state.resampler.reset()  # AttributeError

None-guards added so these methods work safely in SSOT mode.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MeanReversion1mStrategy,
    MRStrategyConfig,
)


def _make_strategy_with_symbol(symbol: str = "BTCUSDT") -> MeanReversion1mStrategy:
    """Build a strategy instance with one symbol state (resampler=None by default)."""
    config = MRStrategyConfig()
    regime_sizing = {
        "FLAT_LOW": {"sizing_mult": 0.8, "stop_mult": 1.0, "target_mult": 0.8},
        "FLAT_NORMAL": {"sizing_mult": 1.0, "stop_mult": 1.0, "target_mult": 1.0},
        "FLAT_HIGH": {"sizing_mult": 0.7, "stop_mult": 1.5, "target_mult": 1.2},
    }
    strategy = MeanReversion1mStrategy(
        config=config,
        timeframe_sec=180,
        regime_sizing=regime_sizing,
    )
    # Force-initialize state for the symbol (creates state with resampler=None)
    strategy.get_state(symbol)
    return strategy


class TestNoneResamplerSafety:
    """reset_symbol/reset_all/force_close_all must not crash when resampler is None."""

    def test_reset_symbol_no_crash(self):
        """
        reset_symbol() must not raise AttributeError when resampler is None.
        Previously crashed: self._states[symbol].resampler.reset()
        """
        strategy = _make_strategy_with_symbol("BTCUSDT")
        assert strategy._states["BTCUSDT"].resampler is None

        # Must not raise
        strategy.reset_symbol("BTCUSDT")

    def test_reset_all_no_crash(self):
        """
        reset_all() must not raise AttributeError when resampler is None.
        Previously crashed: state.resampler.reset()
        """
        strategy = _make_strategy_with_symbol("BTCUSDT")
        strategy.get_state("ETHUSDT")  # Add second symbol

        assert strategy._states["BTCUSDT"].resampler is None
        assert strategy._states["ETHUSDT"].resampler is None

        # Must not raise
        strategy.reset_all()

    def test_force_close_all_no_crash(self):
        """
        force_close_all() must not raise AttributeError when resampler is None.
        Previously crashed: state.resampler.force_close(timestamp_ms)
        """
        strategy = _make_strategy_with_symbol("BTCUSDT")

        # Must not raise
        result = strategy.force_close_all(timestamp_ms=1700000000000)

    def test_force_close_all_returns_none_per_symbol(self):
        """
        force_close_all() must return {symbol: None} when resampler is None.
        No bars can be force-closed without a resampler.
        """
        strategy = _make_strategy_with_symbol("BTCUSDT")
        result = strategy.force_close_all(timestamp_ms=1700000000000)

        assert "BTCUSDT" in result
        assert result["BTCUSDT"] is None

    def test_reset_symbol_clears_regime(self):
        """reset_symbol() must still clear regime state even without resampler."""
        strategy = _make_strategy_with_symbol("BTCUSDT")
        strategy._regimes["BTCUSDT"] = "FLAT_HIGH"
        strategy._atr_pct["BTCUSDT"] = 0.002

        strategy.reset_symbol("BTCUSDT")

        assert "BTCUSDT" not in strategy._regimes
        assert "BTCUSDT" not in strategy._atr_pct

    def test_reset_all_clears_all_regimes(self):
        """reset_all() must clear all regime state even without resampler."""
        strategy = _make_strategy_with_symbol("BTCUSDT")
        strategy.get_state("ETHUSDT")
        strategy._regimes = {"BTCUSDT": "FLAT_LOW", "ETHUSDT": "FLAT_NORMAL"}
        strategy._atr_pct = {"BTCUSDT": 0.001, "ETHUSDT": 0.003}

        strategy.reset_all()

        assert len(strategy._regimes) == 0
        assert len(strategy._atr_pct) == 0

    def test_reset_nonexistent_symbol_no_crash(self):
        """reset_symbol() on unknown symbol must silently do nothing."""
        strategy = _make_strategy_with_symbol("BTCUSDT")

        # Must not raise for unknown symbol
        strategy.reset_symbol("XRPUSDT")
