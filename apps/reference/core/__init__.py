"""
Core infrastructure module for Aurora.

T2B-04: Time abstraction for deterministic testing.
"""

from .time import Clock, LiveClock, MockClock, get_clock, set_clock, reset_clock

__all__ = [
    "Clock",
    "LiveClock",
    "MockClock",
    "get_clock",
    "set_clock",
    "reset_clock",
]
