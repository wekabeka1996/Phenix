"""Tests for Backpressure Contract — Phase 17.4."""
import pytest

from vfoundation.core.backpressure import (
    BackpressureAction,
    BoundedQueue,
    QueueStats,
)


class TestBoundedQueue:
    """Phase 17.4: BoundedQueue backpressure tests."""

    def test_accept_below_threshold(self):
        """Items below throttle threshold return ACCEPT."""
        q = BoundedQueue(max_size=10, throttle_pct=80.0)
        action = q.offer("key1", "item1")
        assert action == BackpressureAction.ACCEPT

    def test_throttle_above_threshold(self):
        """Items above throttle threshold return THROTTLE."""
        q = BoundedQueue(max_size=10, throttle_pct=80.0)
        for i in range(8):
            q.offer("key1", f"item{i}")
        # 8/10 = 80% → THROTTLE
        action = q.offer("key1", "item8")
        assert action == BackpressureAction.THROTTLE

    def test_reject_at_capacity(self):
        """Items at full capacity return REJECT and are NOT added."""
        q = BoundedQueue(max_size=3, throttle_pct=80.0)
        q.offer("key1", "a")
        q.offer("key1", "b")
        q.offer("key1", "c")
        action = q.offer("key1", "d")
        assert action == BackpressureAction.REJECT
        # Queue still has 3 items, 'd' was NOT added
        st = q.stats("key1")
        assert st is not None
        assert st.current_size == 3
        assert st.total_rejected == 1

    def test_poll_dequeues_fifo(self):
        """poll() returns items in FIFO order."""
        q = BoundedQueue(max_size=10)
        q.offer("key1", "first")
        q.offer("key1", "second")
        assert q.poll("key1") == "first"
        assert q.poll("key1") == "second"
        assert q.poll("key1") is None


class TestQueueStats:
    """Phase 17.4: QueueStats tests."""

    def test_utilization_pct(self):
        """utilization_pct correctly computes percentage."""
        st = QueueStats(key="k", current_size=7, max_size=10)
        assert st.utilization_pct == pytest.approx(70.0)

    def test_all_stats(self):
        """all_stats returns stats for all keys."""
        q = BoundedQueue(max_size=10)
        q.offer("k1", "a")
        q.offer("k2", "b")
        stats = q.all_stats()
        assert len(stats) == 2
        keys = {s.key for s in stats}
        assert keys == {"k1", "k2"}


class TestBackpressureExtensions:
    """Blueprint 17.4: is_throttled, p95_latency_ms, throttle_active."""

    def test_is_throttled_false_below_threshold(self) -> None:
        """is_throttled returns False when queue well below throttle_pct."""
        bq = BoundedQueue(max_size=100, throttle_pct=80.0)
        bq.offer("k1", "item1")
        assert bq.is_throttled("k1") is False

    def test_is_throttled_true_above_threshold(self) -> None:
        """is_throttled returns True when queue at/above throttle_pct."""
        bq = BoundedQueue(max_size=10, throttle_pct=50.0)
        for i in range(6):  # 60% > 50%
            bq.offer("k1", f"item{i}")
        assert bq.is_throttled("k1") is True

    def test_stats_has_p95_and_throttle_active(self) -> None:
        """stats() populates p95_latency_ms and throttle_active fields."""
        bq = BoundedQueue(max_size=100, throttle_pct=80.0)
        for i in range(20):
            bq.offer("k1", f"item{i}")
        st = bq.stats("k1")
        assert st is not None
        assert hasattr(st, "p95_latency_ms")
        assert hasattr(st, "throttle_active")
        assert st.throttle_active is False  # 20/100 = 20% < 80%
        assert st.p95_latency_ms >= 0.0
