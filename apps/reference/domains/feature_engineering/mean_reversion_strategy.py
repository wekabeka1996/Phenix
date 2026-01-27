"""
Mean Reversion 1m Strategy Module.

Phase B4: Bar-based mean reversion strategy using Bollinger Bands.

This module implements a 1-minute mean reversion strategy that:
1. Uses BarResampler to aggregate ticks into 1m bars
2. Computes Bollinger Bands on completed bars
3. Generates MR signals when price touches bands in FLAT regime
4. Adjusts parameters based on FLAT regime type (LOW/NORMAL/HIGH)

Entry signals:
- LONG: Price below lower BB + regime is FLAT
- SHORT: Price above upper BB + regime is FLAT

Exit targets:
- TP: Mean (middle BB)
- SL: ATR-based stop, adjusted by FLAT regime type
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum, auto
from typing import Optional, Dict, List, Any
import time



from .bar_resampler import Bar, BarResampler
from .indicators import (
    BollingerBands,
    compute_bollinger_bands,
    compute_atr,
    compute_rsi,
)
from .regime_mapping import (
    FlatRegime,
    map_to_flat_regime,
    get_mr_parameters,
    MRParameters,
    FlatRegimeThresholds,
)


class MRSignalType(Enum):
    """Mean Reversion signal types."""
    LONG = auto()   # Price below lower BB
    SHORT = auto()  # Price above upper BB
    NEUTRAL = auto()  # No signal


@dataclass
class MRSignal:
    """
    Mean Reversion signal with entry/exit parameters.
    
    Attributes:
        signal_type: LONG, SHORT, or NEUTRAL
        symbol: Trading pair symbol
        price: Current price (bar close)
        bb: Bollinger Bands values
        atr: Average True Range
        flat_regime: FLAT regime type (LOW/NORMAL/HIGH)
        mr_params: MR parameters for this regime
        entry_price: Suggested entry price
        stop_price: Suggested stop loss price
        target_price: Suggested take profit price (mid BB)
        confidence: Signal confidence [0, 1]
        timestamp_ms: Signal timestamp
        why: Explanation of signal
    """
    signal_type: MRSignalType
    symbol: str
    price: Decimal
    bb: Optional[BollingerBands] = None
    atr: Optional[Decimal] = None
    flat_regime: Optional[FlatRegime] = None
    mr_params: Optional[MRParameters] = None
    entry_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    target_price: Optional[Decimal] = None
    confidence: Decimal = Decimal("0")
    timestamp_ms: int = 0
    rsi: Optional[Decimal] = None
    why: str = ""
    # Enriched Context for Logging
    bar: Optional['Bar'] = None  # Full OHLCV
    config_params: Optional[Dict[str, Any]] = None  # Strategy config snapshot
    
    @property
    def is_signal(self) -> bool:
        """True if signal is actionable (LONG or SHORT)."""
        return self.signal_type in (MRSignalType.LONG, MRSignalType.SHORT)
    
    @property
    def side(self) -> Optional[str]:
        """Return 'BUY' or 'SELL' for FSM."""
        if self.signal_type == MRSignalType.LONG:
            return "BUY"
        elif self.signal_type == MRSignalType.SHORT:
            return "SELL"
        return None


@dataclass
class MRStrategyConfig:
    """
    Configuration for Mean Reversion 1m Strategy.
    
    Attributes:
        bb_window: Bollinger Bands window (default 20 bars)
        bb_num_std: Number of standard deviations (default 2.0)
        atr_window: ATR window for stop calculation (default 14 bars)
        rsi_window: RSI window for confirmation (default 14 bars)
        
        min_bars: Minimum bars needed before generating signals
        min_bb_width: Minimum BB width to trade (avoid tight ranges)
        max_bb_width: Maximum BB width to trade (avoid high volatility)
        
        entry_threshold: %B threshold for entry (0.05 means 5% inside band)
        rsi_oversold: RSI threshold for oversold (default 30)
        rsi_overbought: RSI threshold for overbought (default 70)
        
        sl_atr_mult: Stop loss as ATR multiple (adjusted by regime)
        tp_to_mid: Target at mid BB (True) or opposite band (False)
        
        cooldown_sec: Minimum time between signals for same symbol
    """
    bb_window: int = 20
    bb_num_std: float = 2.0
    atr_window: int = 14
    rsi_window: int = 14
    
    min_bars: int = 25  # Need bb_window + some buffer
    min_bb_width: Decimal = Decimal("0.001")  # 0.1%
    max_bb_width: Decimal = Decimal("0.05")   # 5%
    
    entry_threshold: Decimal = Decimal("0.05")  # 5% inside band
    rsi_oversold: Decimal = Decimal("30")
    rsi_overbought: Decimal = Decimal("70")
    
    sl_atr_mult: Decimal = Decimal("1.5")  # Base ATR multiplier
    tp_to_mid: bool = True
    
    cooldown_sec: int = 60  # 1 minute cooldown
    
    # Buffer percentages to widen TP/SL (additive, on top of ATR-based)
    sl_buffer_pct: Decimal = Decimal("0")  # Default 0%, can set 0.002 for +0.20%
    tp_buffer_pct: Decimal = Decimal("0")  # Default 0%, can set 0.002 for +0.20%
    
    # Whitelist of allowed Flat regimes (e.g., ["FLAT_LOW", "FLAT_NORMAL"])
    # If empty, all Flat regimes are allowed.
    allowed_regimes: List[str] = field(default_factory=list)


# Maximum bars to keep in memory per symbol (prevents memory leak)
MAX_BARS_PER_SYMBOL = 1000


@dataclass
class MRSymbolState:
    """
    Per-symbol state for Mean Reversion strategy.
    
    Tracks completed bars, indicators, and last signal time.
    
    Note: NOT thread-safe. Use separate instance per thread or add locking.
    
    T2B-02: resampler is deprecated. MR now consumes global EVT:BAR_CLOSED.
    """
    symbol: str
    # T2B-02: resampler deprecated - MR uses global BarAggregator SSOT
    resampler: Optional[BarResampler] = None
    bars: List[Bar] = field(default_factory=list)
    max_bars: int = MAX_BARS_PER_SYMBOL
    
    # Computed indicators
    bb: Optional[BollingerBands] = None
    atr: Optional[Decimal] = None
    rsi: Optional[Decimal] = None
    
    # Signal tracking
    last_signal_ts: int = 0
    last_signal_type: MRSignalType = MRSignalType.NEUTRAL
    
    def add_bar(self, bar: Bar) -> None:
        """Add completed bar and update state. Trims old bars if over limit."""
        self.bars.append(bar)
        # Prevent memory leak by trimming old bars
        if len(self.bars) > self.max_bars:
            self.bars = self.bars[-self.max_bars:]
    
    def get_closes(self, count: Optional[int] = None) -> List[Decimal]:
        """Get close prices from bars."""
        bars = self.bars[-count:] if count else self.bars
        return [b.close for b in bars]
    
    def reset(self) -> None:
        """Reset state."""
        self.bars.clear()
        self.bb = None
        self.atr = None
        self.rsi = None
        self.last_signal_ts = 0
        self.last_signal_type = MRSignalType.NEUTRAL


class MeanReversion1mStrategy:
    """
    Mean Reversion strategy for 1-minute bars.
    
    Workflow:
    1. Feed ticks via `on_tick()` → resampler aggregates into bars
    2. When bar completes → compute indicators
    3. Check regime → if FLAT, evaluate MR signal
    4. Generate MRSignal with entry/exit parameters
    
    Usage:
        strategy = MeanReversion1mStrategy(config)
        
        # In tick handler:
        signal = strategy.on_tick(symbol, price, volume, timestamp_ms)
        
        if signal and signal.is_signal:
            # Propose trade intent
            side = signal.side
            entry = signal.entry_price
            stop = signal.stop_price
            target = signal.target_price
    """
    
    def __init__(
        self,
        config: Optional[MRStrategyConfig] = None,
        timeframe_sec: int = 60,
        regime_sizing: Optional[Dict[str, Any]] = None,
        regime_thresholds: Optional[FlatRegimeThresholds] = None,
    ) -> None:
        """
        Initialize MR strategy.
        
        Args:
            config: Strategy configuration
            timeframe_sec: Bar timeframe in seconds (default 60 = 1m)
            regime_sizing: Optional dict with regime sizing multipliers from YAML
                           e.g., {"FLAT_LOW": {"sizing_mult": 0.8, "stop_mult": 0.6}}
        """
        self.config = config or MRStrategyConfig()
        self.timeframe_sec = timeframe_sec
        self._regime_sizing = regime_sizing or {}
        self._flat_regime_thresholds = regime_thresholds
        
        # Per-symbol state
        self._states: Dict[str, MRSymbolState] = {}
        
        # Current regime per symbol (from external regime detector)
        self._regimes: Dict[str, str] = {}
        
        # ATR% per symbol (for FLAT regime classification)
        self._atr_pct: Dict[str, Decimal] = {}
    
    def get_state(self, symbol: str) -> MRSymbolState:
        """Get or create state for symbol.
        
        T2B-02: No longer creates BarResampler - MR uses global BarAggregator SSOT.
        """
        if symbol not in self._states:
            # T2B-02: resampler=None - we now receive bars from global BarAggregator
            self._states[symbol] = MRSymbolState(
                symbol=symbol,
                resampler=None,  # DEPRECATED: SSOT migration
            )
        return self._states[symbol]
    
    def set_regime(self, symbol: str, regime: str) -> None:
        """
        Set current regime for symbol.
        
        Called by external regime detector when regime changes.
        """
        self._regimes[symbol] = regime
    
    def get_regime(self, symbol: str) -> str:
        """Get current regime for symbol."""
        return self._regimes[symbol] if symbol in self._regimes else "UNCERTAIN"

    def on_bar(
        self,
        symbol: str,
        bar: Bar,
        timestamp_ms: int,
    ) -> Optional[MRSignal]:
        """
        Process completed bar and generate MR signal (T2B-02 SSOT method).
        
        This is the new SSOT entry point. Bars are received from global BarAggregator
        via EVT:BAR_CLOSED instead of being built locally from ticks.
        
        Args:
            symbol: Trading pair symbol
            bar: Completed bar from global BarAggregator
            timestamp_ms: Event timestamp
            
        Returns:
            MRSignal if signal generated, None/neutral otherwise
        """
        state = self.get_state(symbol)
        price = bar.close
        
        # Add bar to history
        state.add_bar(bar)
        
        # Check if we have enough bars
        if len(state.bars) < self.config.min_bars:
            return self._neutral_signal(symbol, price, timestamp_ms, "insufficient_bars")
        
        # Update indicators
        self._update_indicators(state)
        
        # Check cooldown
        if self._in_cooldown(state, timestamp_ms):
            return self._neutral_signal(
                symbol, price, timestamp_ms, "cooldown", 
                bar=bar, rsi=state.rsi
            )
        
        # Check regime - only trade in FLAT regimes
        regime = self.get_regime(symbol)
        atr_pct = self._atr_pct.get(symbol)
        flat_regime = map_to_flat_regime(regime, atr_pct, self._flat_regime_thresholds)
        
        if flat_regime is None:
            return self._neutral_signal(
                symbol, price, timestamp_ms, 
                f"regime_not_flat:{regime}",
                bar=bar, rsi=state.rsi
            )
            
        # Strict allowlist semantics: only explicitly allowlisted regimes are tradable.
        # Empty allowlist => allow nothing (fail-closed).
        if flat_regime.name not in self.config.allowed_regimes:
            return self._neutral_signal(
                symbol, price, timestamp_ms,
                f"regime_not_allowed:{flat_regime.name}",
                bar=bar, rsi=state.rsi
            )
        
        # Get MR parameters for this regime (with config override support)
        mr_params = MRParameters.from_flat_regime(flat_regime, self._regime_sizing)
        
        # Evaluate MR signal
        signal = self._evaluate_signal(state, flat_regime, mr_params, timestamp_ms, bar)
        
        if signal.is_signal:
            state.last_signal_ts = timestamp_ms
            state.last_signal_type = signal.signal_type
        
        return signal
    
    def on_tick(
        self,
        symbol: str,
        price: Decimal,
        volume: Decimal,
        timestamp_ms: int
    ) -> Optional[MRSignal]:
        """
        DEPRECATED: Process tick via local BarResampler.
        
        T2B-02: This method is deprecated. Use on_bar() with bars from
        global BarAggregator (EVT:BAR_CLOSED) instead.
        
        Args:
            symbol: Trading pair symbol
            price: Tick price
            volume: Tick volume
            timestamp_ms: Tick timestamp
            
        Returns:
            MRSignal if bar completed and signal generated, None otherwise
        """
        state = self.get_state(symbol)
        
        # T2B-02: Check if resampler exists (for backward compatibility)
        if state.resampler is None:
            # SSOT mode: should use on_bar() instead
            return None
        
        # Add tick to resampler (DEPRECATED path)
        completed_bar = state.resampler.add_tick(symbol, price, volume, timestamp_ms)
        
        if completed_bar is None:
            # Bar not complete yet
            return None
        
        # Bar completed - add to history
        state.add_bar(completed_bar)
        
        # Check if we have enough bars
        if len(state.bars) < self.config.min_bars:
            return self._neutral_signal(symbol, price, timestamp_ms, "insufficient_bars")
        
        # Update indicators
        self._update_indicators(state)
        
        # Check cooldown
        if self._in_cooldown(state, timestamp_ms):
            return self._neutral_signal(
                symbol, price, timestamp_ms, "cooldown", 
                bar=completed_bar, rsi=state.rsi
            )
        
        # Check regime - only trade in FLAT regimes
        regime = self.get_regime(symbol)
        atr_pct = self._atr_pct.get(symbol)
        flat_regime = map_to_flat_regime(regime, atr_pct, self._flat_regime_thresholds)
        
        if flat_regime is None:
            return self._neutral_signal(
                symbol, price, timestamp_ms, 
                f"regime_not_flat:{regime}",
                bar=completed_bar, rsi=state.rsi
            )
            
        # Strict allowlist semantics: only explicitly allowlisted regimes are tradable.
        # Empty allowlist => allow nothing (fail-closed).
        if flat_regime.name not in self.config.allowed_regimes:
            return self._neutral_signal(
                symbol, price, timestamp_ms,
                f"regime_not_allowed:{flat_regime.name}",
                bar=completed_bar, rsi=state.rsi
            )
        
        # Get MR parameters for this regime (with config override support)
        mr_params = MRParameters.from_flat_regime(flat_regime, self._regime_sizing)
        
        # Evaluate MR signal
        signal = self._evaluate_signal(state, flat_regime, mr_params, timestamp_ms, completed_bar)
        
        if signal.is_signal:
            state.last_signal_ts = timestamp_ms
            state.last_signal_type = signal.signal_type
        
        return signal
    
    def _update_indicators(self, state: MRSymbolState) -> None:
        """Update indicators from completed bars."""
        closes = state.get_closes()
        
        # Bollinger Bands
        if len(closes) >= self.config.bb_window:
            state.bb = compute_bollinger_bands(
                closes,
                window=self.config.bb_window,
                num_std=self.config.bb_num_std
            )
        
        # ATR
        if len(state.bars) >= self.config.atr_window:
            # Extract highs, lows, closes for compute_atr
            highs = [b.high for b in state.bars]
            lows = [b.low for b in state.bars]
            state.atr = compute_atr(highs, lows, closes, self.config.atr_window)
            
            # Update ATR% for regime classification
            if state.atr and closes:
                current_price = closes[-1]
                if current_price > 0:
                    self._atr_pct[state.symbol] = state.atr / current_price
        
        # RSI
        if len(closes) >= self.config.rsi_window + 1:
            state.rsi = compute_rsi(closes, self.config.rsi_window)
    
    def _in_cooldown(self, state: MRSymbolState, timestamp_ms: int) -> bool:
        """Check if symbol is in cooldown period."""
        if state.last_signal_ts == 0:
            return False
        
        elapsed_sec = (timestamp_ms - state.last_signal_ts) / 1000
        return elapsed_sec < self.config.cooldown_sec
    
    def _evaluate_signal(
        self,
        state: MRSymbolState,
        flat_regime: FlatRegime,
        mr_params: MRParameters,
        timestamp_ms: int,
        bar: Optional[Bar] = None
    ) -> MRSignal:
        """
        Evaluate MR signal based on BB position and RSI.
        
        Returns MRSignal with entry/exit parameters.
        """
        symbol = state.symbol
        closes = state.get_closes()
        current_price = closes[-1] if closes else Decimal("0")
        bb = state.bb
        atr = state.atr
        rsi = state.rsi
        
        # Check BB is valid
        if bb is None:
            return self._neutral_signal(symbol, current_price, timestamp_ms, "no_bb", bar=bar, rsi=rsi)
        
        # Check BB width is within range
        bb_width = Decimal(str(bb.width))
        if bb_width < self.config.min_bb_width:
            return self._neutral_signal(
                symbol, current_price, timestamp_ms, 
                f"bb_width_too_narrow:{bb_width}",
                bar=bar, rsi=rsi
            )
        if bb_width > self.config.max_bb_width:
            return self._neutral_signal(
                symbol, current_price, timestamp_ms,
                f"bb_width_too_wide:{bb_width}",
                bar=bar, rsi=rsi
            )
        
        # Evaluate signal based on %B
        pct_b = Decimal(str(bb.pct_b))
        entry_threshold = Decimal(str(self.config.entry_threshold))
        
        signal_type = MRSignalType.NEUTRAL
        confidence = Decimal("0")
        why_parts = []
        
        # LONG: price below lower band
        if pct_b < entry_threshold:
            signal_type = MRSignalType.LONG
            confidence = Decimal("0.5") + (entry_threshold - pct_b) * Decimal("2")
            why_parts.append(f"price_below_lower_bb:pct_b={pct_b:.3f}")
            
            # RSI confirmation
            if rsi is not None and rsi < self.config.rsi_oversold:
                confidence += Decimal("0.2")
                why_parts.append(f"rsi_oversold:{rsi:.1f}")
        
        # SHORT: price above upper band
        elif pct_b > (1 - entry_threshold):
            signal_type = MRSignalType.SHORT
            confidence = Decimal("0.5") + (pct_b - (1 - entry_threshold)) * Decimal("2")
            why_parts.append(f"price_above_upper_bb:pct_b={pct_b:.3f}")
            
            # RSI confirmation
            if rsi is not None and rsi > self.config.rsi_overbought:
                confidence += Decimal("0.2")
                why_parts.append(f"rsi_overbought:{rsi:.1f}")
        
        if signal_type == MRSignalType.NEUTRAL:
            return self._neutral_signal(
                symbol, current_price, timestamp_ms,
                f"no_signal:pct_b={pct_b:.3f}",
                bar=bar, rsi=rsi
            )
        
        # Clamp confidence
        confidence = min(Decimal("1.0"), confidence)
        
        # Calculate entry/exit prices
        entry_price = current_price
        target_price = bb.mid if self.config.tp_to_mid else (
            bb.lower if signal_type == MRSignalType.SHORT else bb.upper
        )
        
        # Stop price: ATR-based, adjusted by regime
        sl_mult = Decimal(str(self.config.sl_atr_mult)) * mr_params.stop_mult
        atr_for_stop = atr if atr else (bb.upper - bb.lower) / Decimal("4")
        
        if signal_type == MRSignalType.LONG:
            stop_price = entry_price - (atr_for_stop * sl_mult)
        else:
            stop_price = entry_price + (atr_for_stop * sl_mult)
        
        # Apply SL buffer percentage (widen the stop)
        sl_buffer = entry_price * Decimal(str(self.config.sl_buffer_pct))
        if signal_type == MRSignalType.LONG:
            stop_price = stop_price - sl_buffer  # Move SL further down
        else:
            stop_price = stop_price + sl_buffer  # Move SL further up
        
        # Adjust target by regime
        if signal_type == MRSignalType.LONG:
            target_distance = target_price - entry_price
            target_price = entry_price + (target_distance * mr_params.target_mult)
        else:
            target_distance = entry_price - target_price
            target_price = entry_price - (target_distance * mr_params.target_mult)
        
        # Apply TP buffer percentage (widen the target)
        tp_buffer = entry_price * Decimal(str(self.config.tp_buffer_pct))
        if signal_type == MRSignalType.LONG:
            target_price = target_price + tp_buffer  # Move TP further up
        else:
            target_price = target_price - tp_buffer  # Move TP further down
        
        why_parts.append(f"regime:{flat_regime.name}")
        why = ";".join(why_parts)
        
        return MRSignal(
            signal_type=signal_type,
            symbol=symbol,
            price=current_price,
            bb=bb,
            atr=atr,
            flat_regime=flat_regime,
            mr_params=mr_params,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            confidence=confidence,
            timestamp_ms=timestamp_ms,
            rsi=rsi,
            why=why,
            bar=bar,
            config_params=self.config.__dict__.copy() if self.config else None
        )
    
    def _neutral_signal(
        self,
        symbol: str,
        price: Decimal,
        timestamp_ms: int,
        reason: str,
        bar: Optional[Bar] = None,
        rsi: Optional[Decimal] = None
    ) -> MRSignal:
        """Create neutral (no action) signal."""
        return MRSignal(
            signal_type=MRSignalType.NEUTRAL,
            symbol=symbol,
            price=price,
            timestamp_ms=timestamp_ms,
            rsi=rsi,
            why=f"neutral:{reason}",
            bar=bar,
            config_params=self.config.__dict__.copy() if self.config else None
        )
    
    def force_close_all(self, timestamp_ms: int) -> Dict[str, Optional[Bar]]:
        """
        Force close all pending bars (e.g., at session end).
        
        Returns dict of symbol → closed bar (or None).
        """
        result = {}
        for symbol, state in self._states.items():
            bar = state.resampler.force_close(timestamp_ms)
            if bar:
                state.add_bar(bar)
            result[symbol] = bar
        return result
    
    def reset_symbol(self, symbol: str) -> None:
        """Reset state for symbol."""
        if symbol in self._states:
            self._states[symbol].reset()
            self._states[symbol].resampler.reset()
        self._regimes.pop(symbol, None)
        self._atr_pct.pop(symbol, None)
    
    def reset_all(self) -> None:
        """Reset all state."""
        for state in self._states.values():
            state.reset()
            state.resampler.reset()
        self._regimes.clear()
        self._atr_pct.clear()
