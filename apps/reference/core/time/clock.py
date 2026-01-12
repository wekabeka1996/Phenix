"""
Time abstraction for deterministic testing (T2B-04).

This module provides a Clock abstraction that allows:
1. LiveClock — real wall-clock time for production
2. MockClock — controlled time for testing/simulation

Usage:
    from apps.reference.core.time.clock import LiveClock, MockClock
    
    # Production
    clock = LiveClock()
    now_ms = clock.now_ms()
    
    # Testing/Simulation
    clock = MockClock(start_ms=1000000)
    clock.advance_ms(5000)  # Jump 5 seconds
    await clock.sleep_ms(1000)  # Instant, no real delay

T2B-04: Pre-Shadow requirement for deterministic backtest.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Optional


class Clock(ABC):
    """Abstract clock interface for time abstraction.
    
    Allows swapping between real time (production) and simulated time (testing).
    """
    
    @abstractmethod
    def now_ms(self) -> int:
        """Get current time in milliseconds since epoch.
        
        Returns:
            Current timestamp in milliseconds.
        """
        ...
    
    @abstractmethod
    def now_sec(self) -> float:
        """Get current time in seconds since epoch.
        
        Returns:
            Current timestamp in seconds (float for sub-second precision).
        """
        ...
    
    @abstractmethod
    def monotonic(self) -> float:
        """Get monotonic clock value (for duration measurements).
        
        Returns:
            Monotonic time in seconds.
        """
        ...
    
    @abstractmethod
    async def sleep_ms(self, ms: int) -> None:
        """Sleep for specified milliseconds.
        
        In production: real sleep.
        In simulation: instant return (or controlled advance).
        
        Args:
            ms: Duration to sleep in milliseconds.
        """
        ...
    
    @abstractmethod
    async def sleep_sec(self, sec: float) -> None:
        """Sleep for specified seconds.
        
        Args:
            sec: Duration to sleep in seconds.
        """
        ...


class LiveClock(Clock):
    """Production clock using real system time.
    
    All time operations use actual system time and real delays.
    """
    
    def now_ms(self) -> int:
        """Get current wall time in milliseconds."""
        return int(time.time() * 1000)
    
    def now_sec(self) -> float:
        """Get current wall time in seconds."""
        return time.time()
    
    def monotonic(self) -> float:
        """Get monotonic clock value."""
        return time.monotonic()
    
    async def sleep_ms(self, ms: int) -> None:
        """Sleep for real milliseconds."""
        if ms > 0:
            await asyncio.sleep(ms / 1000.0)
    
    async def sleep_sec(self, sec: float) -> None:
        """Sleep for real seconds."""
        if sec > 0:
            await asyncio.sleep(sec)


class MockClock(Clock):
    """Simulated clock for testing and backtest.
    
    Time is fully controlled — no real delays, instant "sleep".
    
    Usage:
        clock = MockClock(start_ms=1705000000000)  # Jan 2024
        
        assert clock.now_ms() == 1705000000000
        
        clock.advance_ms(5000)  # Jump 5 seconds
        assert clock.now_ms() == 1705000005000
        
        await clock.sleep_ms(1000)  # Instant, also advances time
        assert clock.now_ms() == 1705000006000
    """
    
    def __init__(self, start_ms: int = 1705000000000, start_monotonic: float = 0.0):
        """Initialize mock clock.
        
        Args:
            start_ms: Initial wall time in milliseconds (default: ~Jan 2024).
            start_monotonic: Initial monotonic value.
        """
        self._time_ms: int = start_ms
        self._monotonic: float = start_monotonic
    
    def now_ms(self) -> int:
        """Get simulated time in milliseconds."""
        return self._time_ms
    
    def now_sec(self) -> float:
        """Get simulated time in seconds."""
        return self._time_ms / 1000.0
    
    def monotonic(self) -> float:
        """Get simulated monotonic value."""
        return self._monotonic
    
    def advance_ms(self, ms: int) -> None:
        """Advance simulated time by milliseconds.
        
        Args:
            ms: Milliseconds to advance.
        """
        self._time_ms += ms
        self._monotonic += ms / 1000.0
    
    def advance_sec(self, sec: float) -> None:
        """Advance simulated time by seconds.
        
        Args:
            sec: Seconds to advance.
        """
        self._time_ms += int(sec * 1000)
        self._monotonic += sec
    
    def set_time_ms(self, ms: int) -> None:
        """Set absolute simulated time.
        
        Args:
            ms: New time in milliseconds.
        """
        self._time_ms = ms
    
    async def sleep_ms(self, ms: int) -> None:
        """Simulated sleep — advances time instantly (no real delay).
        
        Args:
            ms: Duration in milliseconds (added to simulated time).
        """
        if ms > 0:
            self.advance_ms(ms)
    
    async def sleep_sec(self, sec: float) -> None:
        """Simulated sleep — advances time instantly (no real delay).
        
        Args:
            sec: Duration in seconds (added to simulated time).
        """
        if sec > 0:
            self.advance_sec(sec)


# Singleton for default live clock (can be swapped in tests)
_default_clock: Optional[Clock] = None


def get_clock() -> Clock:
    """Get the global clock instance.
    
    Returns LiveClock by default. Can be overridden via set_clock().
    
    Returns:
        Current global clock.
    """
    global _default_clock
    if _default_clock is None:
        _default_clock = LiveClock()
    return _default_clock


def set_clock(clock: Clock) -> None:
    """Set the global clock instance (for testing).
    
    Args:
        clock: Clock instance to use globally.
    """
    global _default_clock
    _default_clock = clock


def reset_clock() -> None:
    """Reset to default LiveClock."""
    global _default_clock
    _default_clock = None
