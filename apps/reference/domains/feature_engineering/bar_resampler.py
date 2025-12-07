"""
Bar Resampler: Tick → OHLCV bar aggregation.

Phase B1: Core infrastructure for bar-based strategies (1m Mean Reversion).

Responsibilities:
- Aggregate ticks into OHLCV bars (default 1m)
- Emit Bar dataclass when bar closes
- Maintain sliding window of completed bars for indicator calculation

Usage:
    resampler = BarResampler(timeframe_sec=60)  # 1 minute bars
    for tick in ticks:
        closed_bar = resampler.add_tick(symbol, price, volume, ts_ms)
        if closed_bar:
            # Process completed bar (calculate indicators, emit event, etc.)
            pass
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Deque, Dict
from collections import deque
import time


@dataclass
class Bar:
    """
    OHLCV bar representation.
    
    Attributes:
        symbol: Trading symbol (e.g., "BTCUSDT")
        timeframe_sec: Bar duration in seconds (e.g., 60 for 1m)
        open: Opening price
        high: Highest price during bar
        low: Lowest price during bar
        close: Closing price
        volume: Total volume during bar
        trade_count: Number of trades in bar
        start_ts_ms: Bar start timestamp (milliseconds)
        end_ts_ms: Bar end timestamp (milliseconds)
    """
    symbol: str
    timeframe_sec: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    trade_count: int
    start_ts_ms: int
    end_ts_ms: int

    @property
    def mid(self) -> Decimal:
        """Midpoint price (high + low) / 2."""
        return (self.high + self.low) / 2

    @property
    def range_pct(self) -> float:
        """Price range as percentage of open."""
        if self.open == 0:
            return 0.0
        return float((self.high - self.low) / self.open)

    @property
    def is_bullish(self) -> bool:
        """True if close > open."""
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        """True if close < open."""
        return self.close < self.open


class BarResampler:
    """
    Tick → OHLCV bar resampler.
    
    Aggregates incoming ticks into fixed-timeframe bars.
    Returns completed Bar when a new bar period starts.
    
    Thread-safety: NOT thread-safe. Use one instance per symbol or add locking.
    
    Example:
        resampler = BarResampler(timeframe_sec=60)
        
        # Process tick stream
        bar = resampler.add_tick("BTCUSDT", Decimal("50000"), Decimal("0.1"), ts_ms)
        if bar:
            print(f"Bar closed: O={bar.open} H={bar.high} L={bar.low} C={bar.close}")
    """

    def __init__(
        self,
        timeframe_sec: int = 60,
        max_bars: int = 1000,
    ):
        """
        Initialize bar resampler.
        
        Args:
            timeframe_sec: Bar duration in seconds (default 60 = 1 minute)
            max_bars: Maximum number of completed bars to keep in memory
        """
        if timeframe_sec <= 0:
            raise ValueError(f"timeframe_sec must be positive, got {timeframe_sec}")
        
        self.timeframe_sec = timeframe_sec
        self.timeframe_ms = timeframe_sec * 1000
        self.max_bars = max_bars
        
        # Current incomplete bar (None if no ticks yet)
        self._current_bar: Optional[Bar] = None
        
        # Completed bars (most recent last)
        self._completed_bars: Deque[Bar] = deque(maxlen=max_bars)
        
        # Metrics
        self._ticks_processed: int = 0
        self._bars_completed: int = 0

    def add_tick(
        self,
        symbol: str,
        price: Decimal,
        volume: Decimal = Decimal("0"),
        ts_ms: Optional[int] = None,
    ) -> Optional[Bar]:
        """
        Add a tick and return completed Bar if bar period ended.
        
        Args:
            symbol: Trading symbol
            price: Tick price
            volume: Tick volume (default 0)
            ts_ms: Tick timestamp in milliseconds (default: current time)
            
        Returns:
            Completed Bar if this tick caused a bar close, None otherwise
        """
        if ts_ms is None:
            ts_ms = int(time.time() * 1000)
        
        self._ticks_processed += 1
        
        # First tick ever
        if self._current_bar is None:
            bar_start = self._align_to_bar_boundary(ts_ms)
            self._current_bar = Bar(
                symbol=symbol,
                timeframe_sec=self.timeframe_sec,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=volume,
                trade_count=1,
                start_ts_ms=bar_start,
                end_ts_ms=ts_ms,
            )
            return None
        
        # Check if tick belongs to a new bar period
        bar_end_ts = self._current_bar.start_ts_ms + self.timeframe_ms
        
        if ts_ms >= bar_end_ts:
            # Close current bar
            self._current_bar.end_ts_ms = bar_end_ts - 1  # Last ms of bar
            closed_bar = self._current_bar
            self._completed_bars.append(closed_bar)
            self._bars_completed += 1
            
            # Start new bar (aligned to boundary)
            new_bar_start = self._align_to_bar_boundary(ts_ms)
            self._current_bar = Bar(
                symbol=symbol,
                timeframe_sec=self.timeframe_sec,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=volume,
                trade_count=1,
                start_ts_ms=new_bar_start,
                end_ts_ms=ts_ms,
            )
            
            return closed_bar
        
        # Update current bar
        self._current_bar.close = price
        self._current_bar.high = max(self._current_bar.high, price)
        self._current_bar.low = min(self._current_bar.low, price)
        self._current_bar.volume += volume
        self._current_bar.trade_count += 1
        self._current_bar.end_ts_ms = ts_ms
        
        return None

    def _align_to_bar_boundary(self, ts_ms: int) -> int:
        """Align timestamp to bar boundary (floor to timeframe)."""
        return (ts_ms // self.timeframe_ms) * self.timeframe_ms

    def get_completed_bars(self, n: Optional[int] = None) -> list[Bar]:
        """
        Get last N completed bars (most recent last).
        
        Args:
            n: Number of bars to return (None = all)
            
        Returns:
            List of completed bars
        """
        if n is None:
            return list(self._completed_bars)
        return list(self._completed_bars)[-n:]

    def get_closes(self, n: Optional[int] = None) -> list[Decimal]:
        """
        Get close prices from last N completed bars.
        
        Args:
            n: Number of closes to return (None = all)
            
        Returns:
            List of close prices (oldest first)
        """
        bars = self.get_completed_bars(n)
        return [bar.close for bar in bars]

    def get_current_bar(self) -> Optional[Bar]:
        """Get current incomplete bar (None if no ticks yet)."""
        return self._current_bar

    def force_close(self, ts_ms: Optional[int] = None) -> Optional[Bar]:
        """
        Force close current bar (e.g., at session end).
        
        Args:
            ts_ms: Close timestamp (default: current time)
            
        Returns:
            Closed bar or None if no current bar
        """
        if self._current_bar is None:
            return None
        
        if ts_ms is None:
            ts_ms = int(time.time() * 1000)
        
        self._current_bar.end_ts_ms = ts_ms
        closed_bar = self._current_bar
        self._completed_bars.append(closed_bar)
        self._bars_completed += 1
        self._current_bar = None
        
        return closed_bar

    def reset(self) -> None:
        """Reset resampler state (clear all bars)."""
        self._current_bar = None
        self._completed_bars.clear()
        self._ticks_processed = 0
        self._bars_completed = 0

    def get_metrics(self) -> Dict[str, int]:
        """Get resampler metrics."""
        return {
            "ticks_processed": self._ticks_processed,
            "bars_completed": self._bars_completed,
            "bars_in_memory": len(self._completed_bars),
            "has_current_bar": self._current_bar is not None,
        }


class MultiSymbolBarResampler:
    """
    Bar resampler for multiple symbols.
    
    Maintains separate BarResampler instance per symbol.
    
    Example:
        resampler = MultiSymbolBarResampler(timeframe_sec=60)
        
        bar = resampler.add_tick("BTCUSDT", Decimal("50000"), Decimal("0.1"), ts_ms)
        bar = resampler.add_tick("ETHUSDT", Decimal("3000"), Decimal("1.0"), ts_ms)
    """

    def __init__(
        self,
        timeframe_sec: int = 60,
        max_bars: int = 1000,
    ):
        """
        Initialize multi-symbol bar resampler.
        
        Args:
            timeframe_sec: Bar duration in seconds (default 60 = 1 minute)
            max_bars: Maximum number of completed bars to keep per symbol
        """
        self.timeframe_sec = timeframe_sec
        self.max_bars = max_bars
        self._resamplers: Dict[str, BarResampler] = {}

    def add_tick(
        self,
        symbol: str,
        price: Decimal,
        volume: Decimal = Decimal("0"),
        ts_ms: Optional[int] = None,
    ) -> Optional[Bar]:
        """
        Add a tick for a symbol and return completed Bar if bar period ended.
        
        Args:
            symbol: Trading symbol
            price: Tick price
            volume: Tick volume (default 0)
            ts_ms: Tick timestamp in milliseconds
            
        Returns:
            Completed Bar if this tick caused a bar close, None otherwise
        """
        if symbol not in self._resamplers:
            self._resamplers[symbol] = BarResampler(
                timeframe_sec=self.timeframe_sec,
                max_bars=self.max_bars,
            )
        
        return self._resamplers[symbol].add_tick(symbol, price, volume, ts_ms)

    def get_resampler(self, symbol: str) -> Optional[BarResampler]:
        """Get resampler for a specific symbol."""
        return self._resamplers.get(symbol)

    def get_completed_bars(self, symbol: str, n: Optional[int] = None) -> list[Bar]:
        """Get completed bars for a symbol."""
        resampler = self._resamplers.get(symbol)
        if resampler is None:
            return []
        return resampler.get_completed_bars(n)

    def get_closes(self, symbol: str, n: Optional[int] = None) -> list[Decimal]:
        """Get close prices for a symbol."""
        resampler = self._resamplers.get(symbol)
        if resampler is None:
            return []
        return resampler.get_closes(n)

    def reset(self, symbol: Optional[str] = None) -> None:
        """
        Reset resampler state.
        
        Args:
            symbol: Symbol to reset (None = reset all)
        """
        if symbol is None:
            self._resamplers.clear()
        elif symbol in self._resamplers:
            self._resamplers[symbol].reset()

    def get_metrics(self) -> Dict[str, Dict[str, int]]:
        """Get metrics for all symbols."""
        return {
            symbol: resampler.get_metrics()
            for symbol, resampler in self._resamplers.items()
        }
