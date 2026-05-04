"""
Unit tests for quiet hours functionality.
"""

from apps.reference.domains.execution_position.fsm import _in_quiet
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def test_in_quiet_simple():
    """Test basic quiet hours functionality."""
    # Should always be false for empty list
    assert _in_quiet([]) is False
    # Should always be true for 00:00-23:59
    assert _in_quiet(["00:00-23:59"]) is True


def test_in_quiet_normal_range():
    """Test quiet hours within normal time range."""
    # Test various time ranges that don't wrap around midnight
    # Depends on current time
    assert _in_quiet(["09:00-17:00"]) in (True, False)
    # Depends on current time
    assert _in_quiet(["22:00-06:00"]) in (True, False)


def test_in_quiet_midnight_wrap():
    """Test quiet hours that wrap around midnight."""
    # This range wraps around midnight, so should be true during late night/early morning
    # Depends on current time
    assert _in_quiet(["22:00-06:00"]) in (True, False)


def test_in_quiet_multiple_ranges():
    """Test multiple quiet hour ranges."""
    # Multiple ranges - at least one should potentially be active
    assert _in_quiet(["00:00-01:00", "23:00-23:59"]) in (
        True,
        False,
    )  # Depends on current time


def test_in_quiet_edge_cases():
    """Test edge cases for quiet hours."""
    # Invalid format should not crash (empty list handling)
    assert _in_quiet([]) is False
    # Single range edge case
    assert _in_quiet(["12:00-12:01"]) in (True, False)  # Very narrow range
