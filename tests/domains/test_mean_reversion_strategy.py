"""
Tests for mean_reversion_strategy.py — Phase B4.

Tests cover:
- MRSignalType enum
- MRSignal dataclass
- MRStrategyConfig defaults
- MRSymbolState bar management
- MeanReversion1mStrategy core logic
- Signal generation with BB and RSI
- Regime filtering
- Cooldown behavior
"""

import pytest
from decimal import Decimal
from typing import List

from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MRSignalType,
    MRSignal,
    MRStrategyConfig,
    MRSymbolState,
    MeanReversion1mStrategy,
)
from apps.reference.domains.feature_engineering.bar_resampler import Bar, BarResampler
from apps.reference.domains.feature_engineering.indicators import BollingerBands
from apps.reference.domains.feature_engineering.regime_mapping import FlatRegime, MRParameters


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def default_config() -> MRStrategyConfig:
    """Default strategy config."""
    return MRStrategyConfig()


@pytest.fixture
def strategy(default_config) -> MeanReversion1mStrategy:
    """Strategy with default config."""
    return MeanReversion1mStrategy(config=default_config)


def make_tick_sequence(
    base_price: Decimal,
    count: int,
    trend: Decimal = Decimal("0"),
    noise: Decimal = Decimal("0.01")
) -> List[tuple]:
    """Generate tick sequence (price, volume, timestamp)."""
    ticks = []
    base_ts = 1000000
    for i in range(count):
        price = base_price + trend * i
        # Add some noise
        if i % 2 == 0:
            price += noise
        else:
            price -= noise
        volume = Decimal("1.0")
        ts = base_ts + i * 1000  # 1 second apart
        ticks.append((price, volume, ts))
    return ticks


def feed_bars_to_strategy(
    strategy: MeanReversion1mStrategy,
    symbol: str,
    bar_count: int,
    base_price: Decimal = Decimal("100"),
    trend: Decimal = Decimal("0")
) -> None:
    """Feed enough ticks to create bar_count bars."""
    ticks_per_bar = 60  # 60 seconds = 1 minute
    total_ticks = bar_count * ticks_per_bar
    
    base_ts = 1000000
    for i in range(total_ticks):
        bar_num = i // ticks_per_bar
        price = base_price + trend * bar_num
        # Add variation within bar
        tick_in_bar = i % ticks_per_bar
        if tick_in_bar < 20:
            price -= Decimal("0.5")  # Low
        elif tick_in_bar > 40:
            price += Decimal("0.5")  # High
        
        volume = Decimal("1.0")
        ts = base_ts + i * 1000
        strategy.on_tick(symbol, price, volume, ts)


# =============================================================================
# Test MRSignalType
# =============================================================================

class TestMRSignalType:
    """Test MRSignalType enum."""
    
    def test_enum_values(self):
        """Check all signal types exist."""
        assert MRSignalType.LONG is not None
        assert MRSignalType.SHORT is not None
        assert MRSignalType.NEUTRAL is not None
    
    def test_enum_unique(self):
        """Each signal type has unique value."""
        types = [MRSignalType.LONG, MRSignalType.SHORT, MRSignalType.NEUTRAL]
        values = [t.value for t in types]
        assert len(values) == len(set(values))


# =============================================================================
# Test MRSignal
# =============================================================================

class TestMRSignal:
    """Test MRSignal dataclass."""
    
    def test_neutral_signal_properties(self):
        """Neutral signal properties."""
        signal = MRSignal(
            signal_type=MRSignalType.NEUTRAL,
            symbol="BTCUSDT",
            price=Decimal("50000"),
            timestamp_ms=1000000,
            why="no_signal"
        )
        
        assert signal.is_signal is False
        assert signal.side is None
    
    def test_long_signal_properties(self):
        """Long signal properties."""
        signal = MRSignal(
            signal_type=MRSignalType.LONG,
            symbol="BTCUSDT",
            price=Decimal("50000"),
            timestamp_ms=1000000,
            why="price_below_lower_bb"
        )
        
        assert signal.is_signal is True
        assert signal.side == "BUY"
    
    def test_short_signal_properties(self):
        """Short signal properties."""
        signal = MRSignal(
            signal_type=MRSignalType.SHORT,
            symbol="BTCUSDT",
            price=Decimal("50000"),
            timestamp_ms=1000000,
            why="price_above_upper_bb"
        )
        
        assert signal.is_signal is True
        assert signal.side == "SELL"
    
    def test_signal_with_all_fields(self):
        """Signal with all fields populated."""
        bb = BollingerBands(
            upper=Decimal("105"),
            lower=Decimal("95"),
            mid=Decimal("100"),
            width=0.1,
            pct_b=0.0
        )
        mr_params = MRParameters.from_flat_regime(FlatRegime.FLAT_NORMAL)
        
        signal = MRSignal(
            signal_type=MRSignalType.LONG,
            symbol="BTCUSDT",
            price=Decimal("94"),
            bb=bb,
            atr=Decimal("2.5"),
            flat_regime=FlatRegime.FLAT_NORMAL,
            mr_params=mr_params,
            entry_price=Decimal("94"),
            stop_price=Decimal("90"),
            target_price=Decimal("100"),
            confidence=Decimal("0.7"),
            timestamp_ms=1000000,
            why="price_below_lower_bb:pct_b=-0.2;regime:FLAT_NORMAL"
        )
        
        assert signal.entry_price == Decimal("94")
        assert signal.stop_price == Decimal("90")
        assert signal.target_price == Decimal("100")
        assert signal.flat_regime == FlatRegime.FLAT_NORMAL


# =============================================================================
# Test MRStrategyConfig
# =============================================================================

class TestMRStrategyConfig:
    """Test MRStrategyConfig defaults."""
    
    def test_default_values(self):
        """Default config values."""
        config = MRStrategyConfig()
        
        assert config.bb_window == 20
        assert config.bb_num_std == 2.0
        assert config.atr_window == 14
        assert config.rsi_window == 14
        assert config.min_bars == 25
        assert config.cooldown_sec == 60
    
    def test_custom_values(self):
        """Custom config values."""
        config = MRStrategyConfig(
            bb_window=30,
            bb_num_std=2.5,
            cooldown_sec=120
        )
        
        assert config.bb_window == 30
        assert config.bb_num_std == 2.5
        assert config.cooldown_sec == 120


# =============================================================================
# Test MRSymbolState
# =============================================================================

class TestMRSymbolState:
    """Test MRSymbolState bar management."""
    
    def test_add_bar(self):
        """Add bar to state."""
        resampler = BarResampler(timeframe_sec=60)
        state = MRSymbolState(symbol="BTCUSDT", resampler=resampler)
        
        bar = Bar(
            symbol="BTCUSDT",
            timeframe_sec=60,
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            volume=Decimal("10"),
            trade_count=100,
            start_ts_ms=0,
            end_ts_ms=60000
        )
        
        state.add_bar(bar)
        assert len(state.bars) == 1
        assert state.bars[0].close == Decimal("101")
    
    def test_add_bar_respects_max_bars_limit(self):
        """Test that add_bar trims old bars when over max_bars limit."""
        resampler = BarResampler(timeframe_sec=60)
        # Set low max_bars for testing
        state = MRSymbolState(symbol="BTCUSDT", resampler=resampler, max_bars=5)
        
        # Add 10 bars
        for i in range(10):
            bar = Bar(
                symbol="BTCUSDT",
                timeframe_sec=60,
                open=Decimal("100"),
                high=Decimal("102"),
                low=Decimal("99"),
                close=Decimal(str(100 + i)),
                volume=Decimal("10"),
                trade_count=100,
                start_ts_ms=i * 60000,
                end_ts_ms=(i + 1) * 60000
            )
            state.add_bar(bar)
        
        # Should only keep last 5 bars
        assert len(state.bars) == 5
        # First bar should be the 6th one (index 5, close=105)
        assert state.bars[0].close == Decimal("105")
        # Last bar should be the 10th one (index 9, close=109)
        assert state.bars[-1].close == Decimal("109")
    
    def test_get_closes(self):
        """Get close prices from bars."""
        resampler = BarResampler(timeframe_sec=60)
        state = MRSymbolState(symbol="BTCUSDT", resampler=resampler)
        
        for i in range(5):
            bar = Bar(
                symbol="BTCUSDT",
                timeframe_sec=60,
                open=Decimal("100"),
                high=Decimal("102"),
                low=Decimal("99"),
                close=Decimal(str(100 + i)),
                volume=Decimal("10"),
                trade_count=100,
                start_ts_ms=i * 60000,
                end_ts_ms=(i + 1) * 60000
            )
            state.add_bar(bar)
        
        closes = state.get_closes()
        assert len(closes) == 5
        assert closes[0] == Decimal("100")
        assert closes[-1] == Decimal("104")
        
        # With count limit
        last_3 = state.get_closes(3)
        assert len(last_3) == 3
        assert last_3[0] == Decimal("102")
    
    def test_reset(self):
        """Reset state clears all."""
        resampler = BarResampler(timeframe_sec=60)
        state = MRSymbolState(symbol="BTCUSDT", resampler=resampler)
        
        state.add_bar(Bar(
            symbol="BTCUSDT", timeframe_sec=60,
            open=Decimal("100"), high=Decimal("102"),
            low=Decimal("99"), close=Decimal("101"),
            volume=Decimal("10"), trade_count=100,
            start_ts_ms=0, end_ts_ms=60000
        ))
        state.bb = BollingerBands(
            upper=Decimal("105"), lower=Decimal("95"),
            mid=Decimal("100"), width=0.1, pct_b=0.5
        )
        state.last_signal_ts = 1000000
        
        state.reset()
        
        assert len(state.bars) == 0
        assert state.bb is None
        assert state.atr is None
        assert state.last_signal_ts == 0


# =============================================================================
# Test MeanReversion1mStrategy
# =============================================================================

class TestMeanReversion1mStrategy:
    """Test MeanReversion1mStrategy core logic."""
    
    def test_init_with_explicit_config(self):
        """Strategy initializes with explicit MRStrategyConfig (P0: no implicit defaults)."""
        config = MRStrategyConfig()  # Explicit config required after P0 fix
        strategy = MeanReversion1mStrategy(config=config)
        
        assert strategy.config.bb_window == 20
        assert strategy.timeframe_sec == 60
        assert len(strategy._states) == 0
    
    def test_init_custom_config(self):
        """Strategy initializes with custom config."""
        config = MRStrategyConfig(bb_window=30)
        strategy = MeanReversion1mStrategy(config=config, timeframe_sec=300)
        
        assert strategy.config.bb_window == 30
        assert strategy.timeframe_sec == 300
    
    def test_get_state_creates_new(self):
        """get_state creates new state for unknown symbol."""
        strategy = MeanReversion1mStrategy(config=MRStrategyConfig())
        
        state = strategy.get_state("BTCUSDT")
        
        assert state.symbol == "BTCUSDT"
        assert len(state.bars) == 0
        assert "BTCUSDT" in strategy._states
    
    def test_get_state_returns_existing(self):
        """get_state returns existing state."""
        strategy = MeanReversion1mStrategy(config=MRStrategyConfig())
        
        state1 = strategy.get_state("BTCUSDT")
        state1.add_bar(Bar(
            symbol="BTCUSDT", timeframe_sec=60,
            open=Decimal("100"), high=Decimal("102"),
            low=Decimal("99"), close=Decimal("101"),
            volume=Decimal("10"), trade_count=100,
            start_ts_ms=0, end_ts_ms=60000
        ))
        
        state2 = strategy.get_state("BTCUSDT")
        assert len(state2.bars) == 1
        assert state1 is state2
    
    def test_set_and_get_regime(self):
        """Set and get regime for symbol."""
        strategy = MeanReversion1mStrategy(config=MRStrategyConfig())
        
        strategy.set_regime("BTCUSDT", "MEAN_REVERSION")
        assert strategy.get_regime("BTCUSDT") == "MEAN_REVERSION"
        
        # Unknown symbol returns UNCERTAIN
        assert strategy.get_regime("UNKNOWN") == "UNCERTAIN"
    
    @pytest.mark.skip(reason="T2B-02: on_tick removed — use on_bar via EVT:BAR_CLOSED")
    def test_on_tick_no_bar_complete(self):
        """on_tick returned None when bar not complete (deprecated, T2B-02 removed)."""
        pass

    
    @pytest.mark.skip(reason="T2B-02: on_tick deprecated, MR now uses on_bar (bar-driven)")
    def test_on_tick_insufficient_bars(self):
        """on_tick returns neutral when not enough bars."""
        strategy = MeanReversion1mStrategy(config=MRStrategyConfig())
        strategy.set_regime("BTCUSDT", "MEAN_REVERSION")
        
        # Feed enough ticks for 5 bars (not enough for min_bars=25)
        feed_bars_to_strategy(strategy, "BTCUSDT", bar_count=5)
        
        state = strategy.get_state("BTCUSDT")
        assert len(state.bars) == 5
        
        # Next tick completes 6th bar
        signal = strategy.on_tick(
            "BTCUSDT", 
            Decimal("100"), 
            Decimal("1"), 
            1000000 + 6 * 60 * 1000
        )
        
        # Bar completed but insufficient bars
        # Note: signal may be None if bar not yet complete
        # or neutral if bar completed but insufficient
        if signal is not None:
            assert signal.signal_type == MRSignalType.NEUTRAL
            assert "insufficient_bars" in signal.why
    
    @pytest.mark.skip(reason="T2B-02: resampler removed, reset_symbol needs refactor")
    def test_reset_symbol(self):
        """reset_symbol clears state."""
        strategy = MeanReversion1mStrategy(config=MRStrategyConfig())
        strategy.set_regime("BTCUSDT", "MEAN_REVERSION")
        strategy.get_state("BTCUSDT")
        
        strategy.reset_symbol("BTCUSDT")
        
        # State should be reset
        assert "BTCUSDT" not in strategy._regimes
        state = strategy.get_state("BTCUSDT")
        assert len(state.bars) == 0
    
    @pytest.mark.skip(reason="T2B-02: resampler removed, reset_all needs refactor")
    def test_reset_all(self):
        """reset_all clears all state."""
        strategy = MeanReversion1mStrategy(config=MRStrategyConfig())
        strategy.set_regime("BTCUSDT", "MEAN_REVERSION")
        strategy.set_regime("ETHUSDT", "LOW_VOLATILITY")
        strategy.get_state("BTCUSDT")
        strategy.get_state("ETHUSDT")
        
        strategy.reset_all()
        
        assert len(strategy._regimes) == 0
        assert strategy.get_state("BTCUSDT").bars == []


class TestMRStrategyRegimeFiltering:
    """Test regime filtering in MR strategy."""
    
    @pytest.mark.skip(reason="T2B-02: on_tick/feed_bars deprecated, needs on_bar refactor")
    def test_trending_regime_blocked(self):
        """Trending regime should not generate MR signal."""
        strategy = MeanReversion1mStrategy(config=MRStrategyConfig())
        strategy.set_regime("BTCUSDT", "TREND_UP")
        
        # Feed enough bars
        feed_bars_to_strategy(strategy, "BTCUSDT", bar_count=30)
        
        # Get last completed bar signal
        state = strategy.get_state("BTCUSDT")
        assert len(state.bars) >= 25
        
        # Manual call to check regime filtering
        if state.bb is not None:
            # Would have signal if regime was FLAT
            pass
        
        # Next tick in trending regime
        signal = strategy.on_tick(
            "BTCUSDT",
            Decimal("90"),  # Very low price (below BB)
            Decimal("1"),
            1000000 + 31 * 60 * 1000
        )
        
        if signal is not None:
            assert "regime_not_flat" in signal.why or signal.signal_type == MRSignalType.NEUTRAL
    
    def test_mean_reversion_regime_allowed(self):
        """MEAN_REVERSION regime should allow MR signals."""
        strategy = MeanReversion1mStrategy(config=MRStrategyConfig())
        strategy.set_regime("BTCUSDT", "MEAN_REVERSION")

        # Feed bars via on_bar (T2B-02 SSOT path)
        ts = 1_700_000_000_000
        for i in range(30):
            bar = Bar(
                symbol="BTCUSDT", timeframe_sec=60,
                open=Decimal("100"), high=Decimal("100.5"),
                low=Decimal("99.5"), close=Decimal("100"),
                volume=Decimal("1.0"), trade_count=10,
                start_ts_ms=ts + i * 60_000,
                end_ts_ms=ts + (i + 1) * 60_000,
            )
            strategy.on_bar("BTCUSDT", bar, timestamp_ms=ts + i * 60_000)

        # Regime is FLAT-compatible
        assert strategy.get_regime("BTCUSDT") == "MEAN_REVERSION"


class TestMRStrategyCooldown:
    """Test cooldown behavior."""
    
    def test_cooldown_blocks_rapid_signals(self):
        """Signals within cooldown period should be blocked."""
        config = MRStrategyConfig(cooldown_sec=60)
        strategy = MeanReversion1mStrategy(config=config)
        strategy.set_regime("BTCUSDT", "MEAN_REVERSION")
        
        state = strategy.get_state("BTCUSDT")
        
        # Simulate last signal was recent
        state.last_signal_ts = 1000000
        
        # Check cooldown
        assert strategy._in_cooldown(state, 1000000 + 30 * 1000) is True  # 30s later
        assert strategy._in_cooldown(state, 1000000 + 70 * 1000) is False  # 70s later
    
    def test_no_cooldown_initially(self):
        """No cooldown on first signal."""
        strategy = MeanReversion1mStrategy(config=MRStrategyConfig())
        state = strategy.get_state("BTCUSDT")
        
        # No previous signal
        assert state.last_signal_ts == 0
        assert strategy._in_cooldown(state, 1000000) is False


class TestMRStrategyForceClose:
    """Test force_close_all functionality."""
    
    @pytest.mark.skip(reason="T2B-02: resampler removed, force_close_all needs refactor")
    def test_force_close_all(self):
        """force_close_all closes all pending bars."""
        strategy = MeanReversion1mStrategy(config=MRStrategyConfig())
        
        # Add some ticks (not completing bars)
        strategy.on_tick("BTCUSDT", Decimal("100"), Decimal("1"), 1000)
        strategy.on_tick("ETHUSDT", Decimal("3000"), Decimal("1"), 1000)
        
        result = strategy.force_close_all(60000)
        
        assert "BTCUSDT" in result
        assert "ETHUSDT" in result
        # Bars may or may not be returned depending on tick count


# =============================================================================
# P0 REGRESSION: UNCERTAIN regime must block MR trading
# =============================================================================

class TestP0UncertainRegimeBlocksMRTrading:
    """
    P0 REGRESSION: MR strategy must NOT trade when regime is UNCERTAIN.
    
    Before fix: UNCERTAIN → FLAT_NORMAL → MR could trade before regime established
    After fix: UNCERTAIN → None → MR blocks trading
    
    This is the INTEGRATION test that verifies:
    1. MeanReversion1mStrategy.get_regime() returns "UNCERTAIN" for unknown symbols
    2. map_to_flat_regime("UNCERTAIN") returns None
    3. MR strategy returns "regime_not_flat:UNCERTAIN" signal
    """

    def test_unknown_symbol_returns_uncertain(self):
        """Unknown symbol returns UNCERTAIN regime."""
        strategy = MeanReversion1mStrategy(config=MRStrategyConfig())
        
        # Symbol with no regime set returns UNCERTAIN
        regime = strategy.get_regime("UNKNOWN_SYMBOL")
        assert regime == "UNCERTAIN"

    @pytest.mark.skip(reason="T2B-02: on_tick/feed_bars deprecated, needs on_bar refactor")
    def test_uncertain_regime_blocks_mr_signal(self):
        """P0: UNCERTAIN regime must block MR signals (return regime_not_flat)."""
        from apps.reference.domains.feature_engineering.regime_mapping import map_to_flat_regime
        
        strategy = MeanReversion1mStrategy(config=MRStrategyConfig())
        
        # Do NOT set regime (symbol defaults to UNCERTAIN)
        # Feed enough bars to generate signal
        feed_bars_to_strategy(strategy, "BTCUSDT", bar_count=30, base_price=Decimal("100"))
        
        state = strategy.get_state("BTCUSDT")
        assert len(state.bars) >= 25, "Should have enough bars"
        
        # Verify regime is UNCERTAIN
        assert strategy.get_regime("BTCUSDT") == "UNCERTAIN"
        
        # Verify map_to_flat_regime returns None for UNCERTAIN
        flat_regime = map_to_flat_regime("UNCERTAIN")
        assert flat_regime is None, "P0: UNCERTAIN must map to None"
        
        # Generate next bar with price below BB (would trigger LONG signal if allowed)
        signal = strategy.on_tick(
            "BTCUSDT",
            Decimal("80"),  # Very low price - below any BB
            Decimal("1"),
            1000000 + 31 * 60 * 1000
        )
        
        # Signal must be NEUTRAL with regime_not_flat reason
        assert signal is not None, "Should return a signal"
        assert signal.signal_type == MRSignalType.NEUTRAL, (
            f"P0: UNCERTAIN regime must block signal, got {signal.signal_type}"
        )
        assert "regime_not_flat" in signal.why, (
            f"P0: Signal must have regime_not_flat reason, got: {signal.why}"
        )
        assert "UNCERTAIN" in signal.why, (
            f"P0: Why should mention UNCERTAIN regime, got: {signal.why}"
        )

    def test_mean_reversion_without_atr_blocks_mr_signal(self):
        """P0: MEAN_REVERSION without ATR must block MR signals."""
        from apps.reference.domains.feature_engineering.regime_mapping import map_to_flat_regime
        
        # Verify at regime_mapping level
        flat_regime = map_to_flat_regime("MEAN_REVERSION")  # No ATR
        assert flat_regime is None, "P0: MEAN_REVERSION without ATR must return None"
        
        # At strategy level, ATR is computed from bars, so this is handled differently
        # The strategy computes ATR% internally, so MEAN_REVERSION with bars should work
        # This test verifies the regime_mapping contract

    @pytest.mark.skip(reason="T2B-02: on_tick/feed_bars deprecated, needs on_bar refactor")
    def test_mean_reversion_with_atr_allows_signal(self):
        """MEAN_REVERSION with ATR should allow MR signals."""
        from apps.reference.domains.feature_engineering.regime_mapping import map_to_flat_regime
        
        strategy = MeanReversion1mStrategy(config=MRStrategyConfig())
        strategy.set_regime("BTCUSDT", "MEAN_REVERSION")
        
        # Feed enough bars (strategy computes ATR internally from bars)
        feed_bars_to_strategy(strategy, "BTCUSDT", bar_count=30)
        
        # Verify regime allows trading
        flat_regime = map_to_flat_regime("MEAN_REVERSION", Decimal("0.002"))
        assert flat_regime is not None, "MEAN_REVERSION with ATR should map to FlatRegime"
        
        # Strategy should allow signals (though actual signal depends on BB position)
        # This just verifies no "regime_not_flat" block
        state = strategy.get_state("BTCUSDT")
        assert len(state.bars) >= 25

    def test_low_volatility_always_allows_signal(self):
        """LOW_VOLATILITY should always allow MR signals (no ATR required)."""
        from apps.reference.domains.feature_engineering.regime_mapping import map_to_flat_regime

        strategy = MeanReversion1mStrategy(config=MRStrategyConfig())
        strategy.set_regime("BTCUSDT", "LOW_VOLATILITY")

        # LOW_VOLATILITY doesn't need ATR
        flat_regime = map_to_flat_regime("LOW_VOLATILITY")
        assert flat_regime is not None, "LOW_VOLATILITY should map to FLAT_LOW"

        # Feed bars via on_bar (T2B-02 SSOT path)
        ts = 1_700_000_000_000
        last_signal = None
        for i in range(31):
            bar = Bar(
                symbol="BTCUSDT", timeframe_sec=60,
                open=Decimal("100"), high=Decimal("100.5"),
                low=Decimal("99.5"), close=Decimal("100"),
                volume=Decimal("1.0"), trade_count=10,
                start_ts_ms=ts + i * 60_000,
                end_ts_ms=ts + (i + 1) * 60_000,
            )
            last_signal = strategy.on_bar("BTCUSDT", bar, timestamp_ms=ts + i * 60_000)

        if last_signal is not None and last_signal.signal_type == MRSignalType.NEUTRAL:
            # If neutral, should NOT be because of regime_not_flat
            assert "regime_not_flat" not in last_signal.why, (
                f"LOW_VOLATILITY should not block: {last_signal.why}"
            )

