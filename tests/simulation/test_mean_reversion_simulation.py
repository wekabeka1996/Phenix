import math
from decimal import Decimal
from typing import List

import pytest

from apps.reference.domains.feature_engineering.bar_resampler import Bar
from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MRSignal,
    MRSignalType,
    MRStrategyConfig,
    MeanReversion1mStrategy,
)


class MarketSimulator:
    def __init__(
        self,
        symbol: str = "SIM_USDT",
        base_price: float = 100.0,
        amplitude: float = 2.0,
        period_bars: int = 60,
        noise_std: float = 0.1,
        timeframe_sec: int = 60,
    ) -> None:
        self.symbol = symbol
        self.base_price = base_price
        self.amplitude = amplitude
        self.period_bars = period_bars
        self.noise_std = noise_std
        self.timeframe_sec = timeframe_sec
        self.current_step = 0
        self.start_ts_ms = 1_700_000_000_000

    def generate_bars(self, num_bars: int) -> List[Bar]:
        bars: List[Bar] = []
        for _ in range(num_bars):
            angle = 2 * math.pi * (self.current_step / self.period_bars)
            center = self.base_price + self.amplitude * math.sin(angle)
            drift = self.noise_std if self.current_step % 2 == 0 else -self.noise_std
            close = Decimal(str(round(center + drift, 4)))
            open_price = Decimal(str(round(center - drift, 4)))
            high = Decimal(str(round(center + abs(self.amplitude) * 0.18 + abs(drift), 4)))
            low = Decimal(str(round(center - abs(self.amplitude) * 0.18 - abs(drift), 4)))
            start_ts_ms = self.start_ts_ms + self.current_step * self.timeframe_sec * 1000
            end_ts_ms = start_ts_ms + self.timeframe_sec * 1000 - 1
            bars.append(
                Bar(
                    symbol=self.symbol,
                    timeframe_sec=self.timeframe_sec,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=Decimal("10.0"),
                    trade_count=100,
                    start_ts_ms=start_ts_ms,
                    end_ts_ms=end_ts_ms,
                )
            )
            self.current_step += 1
        return bars


class TestMeanReversionSimulation:
    @pytest.fixture
    def strategy(self):
        config = MRStrategyConfig(
            bb_window=20,
            bb_num_std=1.6,
            min_bars=20,
            cooldown_sec=0,
            rsi_window=14,
            rsi_oversold=40,
            rsi_overbought=60,
            min_bb_width=Decimal("0.0005"),
            max_bb_width=Decimal("0.20"),
            allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
        )
        return MeanReversion1mStrategy(config=config, timeframe_sec=60)

    def test_sine_wave_on_bar_produces_long_and_short_signals(self, strategy):
        sim = MarketSimulator(amplitude=5.0, period_bars=32)
        signals: List[MRSignal] = []
        for bar in sim.generate_bars(96):
            strategy.set_regime(sim.symbol, "MEAN_REVERSION")
            sig = strategy.on_bar(sim.symbol, bar, bar.end_ts_ms)
            if sig and sig.is_signal:
                signals.append(sig)
                assert sig.rsi is not None
                assert isinstance(sig.rsi, Decimal)

        shorts = [s for s in signals if s.signal_type == MRSignalType.SHORT]
        longs = [s for s in signals if s.signal_type == MRSignalType.LONG]

        assert len(shorts) > 0
        assert len(longs) > 0
        for s in shorts:
            assert s.rsi >= Decimal("50")
            assert s.bb is not None
            assert s.bb.pct_b > 0.90
        for s in longs:
            assert s.rsi <= Decimal("50")
            assert s.bb is not None
            assert s.bb.pct_b < 0.10

    def test_trend_regime_blocks_on_bar_entries(self, strategy):
        sim = MarketSimulator(amplitude=5.0)
        signals = []
        for bar in sim.generate_bars(80):
            strategy.set_regime(sim.symbol, "TREND_UP")
            sig = strategy.on_bar(sim.symbol, bar, bar.end_ts_ms)
            if sig:
                signals.append(sig)

        actionable = [s for s in signals if s.is_signal]
        assert len(actionable) == 0
        neutrals = [s for s in signals if s.signal_type == MRSignalType.NEUTRAL]
        blocked_reasons = [s.why for s in neutrals if "regime" in s.why]
        assert len(blocked_reasons) > 0

    def test_rsi_attribute_integrity_on_bar_path(self, strategy):
        sim = MarketSimulator()
        for bar in sim.generate_bars(40):
            strategy.set_regime(sim.symbol, "MEAN_REVERSION")
            sig = strategy.on_bar(sim.symbol, bar, bar.end_ts_ms)
            if sig:
                assert hasattr(sig, "rsi")
                state = strategy.get_state(sim.symbol)
                if state.rsi is not None:
                    assert sig.rsi is not None
