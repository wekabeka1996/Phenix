"""
Time abstraction package for deterministic testing.

T2B-04: Pre-Shadow requirement.
"""

from .clock import Clock, LiveClock, MockClock, get_clock, set_clock, reset_clock

__all__ = [
    "Clock",
    "LiveClock", 
    "MockClock",
    "get_clock",
    "set_clock",
    "reset_clock",
]
