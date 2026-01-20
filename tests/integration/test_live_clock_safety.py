"""
T2B-04: Integration test for Clock abstraction safety.

Verifies that:
1. LiveClock returns times close to system time.time()
2. LiveClock is the default when get_clock() is called.
3. MockClock can be set for deterministic testing.
"""

import time
import pytest

from apps.reference.core.time import (
    Clock,
    LiveClock,
    MockClock,
    get_clock,
    set_clock,
    reset_clock,
)


class TestLiveClockSafety:
    """Test that LiveClock behaves correctly in production scenarios."""

    def test_live_clock_now_ms_matches_system_time(self):
        """LiveClock.now_ms() should be within 50ms of time.time() * 1000."""
        clock = LiveClock()
        
        # Take multiple samples to reduce timing variance
        for _ in range(5):
            system_ms = int(time.time() * 1000)
            clock_ms = clock.now_ms()
            
            delta = abs(clock_ms - system_ms)
            assert delta < 50, (
                f"LiveClock.now_ms()={clock_ms} differs from system time={system_ms} "
                f"by {delta}ms (> 50ms threshold)"
            )

    def test_live_clock_now_sec_matches_system_time(self):
        """LiveClock.now_sec() should be within 0.05s of time.time()."""
        clock = LiveClock()
        
        for _ in range(5):
            system_sec = time.time()
            clock_sec = clock.now_sec()
            
            delta = abs(clock_sec - system_sec)
            assert delta < 0.05, (
                f"LiveClock.now_sec()={clock_sec} differs from system time={system_sec} "
                f"by {delta}s (> 0.05s threshold)"
            )

    def test_live_clock_monotonic_increases(self):
        """LiveClock.monotonic() should always increase."""
        clock = LiveClock()
        
        prev = clock.monotonic()
        for _ in range(10):
            curr = clock.monotonic()
            assert curr >= prev, (
                f"Monotonic time went backwards: {prev} -> {curr}"
            )
            prev = curr


class TestGetClockDefault:
    """Test that get_clock() returns LiveClock by default."""

    def setup_method(self):
        """Reset clock before each test."""
        reset_clock()

    def teardown_method(self):
        """Reset clock after each test."""
        reset_clock()

    def test_get_clock_returns_live_clock_by_default(self):
        """get_clock() should return a LiveClock instance when not configured."""
        clock = get_clock()
        
        assert isinstance(clock, LiveClock), (
            f"get_clock() returned {type(clock).__name__}, expected LiveClock"
        )

    def test_get_clock_returns_same_instance(self):
        """get_clock() should return the same clock instance on repeated calls."""
        clock1 = get_clock()
        clock2 = get_clock()
        
        assert clock1 is clock2, "get_clock() should return singleton instance"


class TestMockClockDeterminism:
    """Test that MockClock enables deterministic testing."""

    def setup_method(self):
        """Reset clock before each test."""
        reset_clock()

    def teardown_method(self):
        """Reset clock after each test."""
        reset_clock()

    def test_mock_clock_returns_fixed_time(self):
        """MockClock should return exact configured time."""
        mock = MockClock(start_ms=1000000)
        set_clock(mock)
        
        clock = get_clock()
        assert clock.now_ms() == 1000000
        assert clock.now_ms() == 1000000  # Same time, no advancement

    def test_mock_clock_advance(self):
        """MockClock.advance_ms() should move time forward."""
        mock = MockClock(start_ms=1000000)
        set_clock(mock)
        
        clock = get_clock()
        assert clock.now_ms() == 1000000
        
        mock.advance_ms(5000)
        assert clock.now_ms() == 1005000

    def test_set_clock_overrides_default(self):
        """set_clock() should override the default LiveClock."""
        mock = MockClock(start_ms=42000)
        set_clock(mock)
        
        clock = get_clock()
        assert isinstance(clock, MockClock)
        assert clock.now_ms() == 42000


class TestClockIntegrationWithDomains:
    """Test that domains can use clock abstraction safely."""

    def test_fsm_imports_get_clock(self):
        """Verify fsm.py now imports get_clock instead of time."""
        # This test verifies the refactoring was applied correctly
        from apps.reference.domains.execution_position import fsm
        
        # Check module doesn't have direct time import at module level
        # (it may still be imported in stdlib, but not used in business logic)
        import inspect
        source = inspect.getsource(fsm)
        
        assert "from apps.reference.core.time import get_clock" in source, (
            "fsm.py should import get_clock from apps.reference.core.time"
        )

    def test_decision_making_uses_clock_instance(self):
        """Verify decision_making.py uses Clock abstraction."""
        from apps.reference.domains.decision_making import decision_making
        
        import inspect
        source = inspect.getsource(decision_making)
        
        assert "self._clock" in source, (
            "decision_making.py should use self._clock for time operations"
        )
        # Verify no direct time.time() calls remain
        assert "time.time()" not in source, (
            "decision_making.py should not have direct time.time() calls"
        )


@pytest.mark.asyncio
class TestAsyncClockOperations:
    """Test async clock operations."""

    async def test_live_clock_sleep_ms_actually_sleeps(self):
        """LiveClock.sleep_ms() should actually wait."""
        clock = LiveClock()
        
        start = time.monotonic()
        await clock.sleep_ms(100)  # 100ms
        elapsed = time.monotonic() - start
        
        assert elapsed >= 0.09, (  # Allow 10ms variance
            f"sleep_ms(100) only waited {elapsed*1000:.1f}ms"
        )
        assert elapsed < 0.2, (
            f"sleep_ms(100) waited too long: {elapsed*1000:.1f}ms"
        )

    async def test_mock_clock_sleep_is_instant(self):
        """MockClock.sleep_ms() should return immediately."""
        mock = MockClock(start_ms=0)
        
        start = time.monotonic()
        await mock.sleep_ms(10000)  # 10 seconds - would block if real
        elapsed = time.monotonic() - start
        
        assert elapsed < 0.1, (
            f"MockClock.sleep_ms() should be instant, took {elapsed*1000:.1f}ms"
        )
