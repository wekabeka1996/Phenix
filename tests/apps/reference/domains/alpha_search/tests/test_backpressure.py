"""
T3: Backpressure Queue Tests
==============================

Tests for apps/reference/domains/alpha_search/runtime/backpressure.py
14 tests covering FIFO ordering, policies, stats, thread safety.
"""

import threading
import pytest
from unittest.mock import MagicMock

from apps.reference.domains.alpha_search.runtime.backpressure import BoundedIngestQueue


@pytest.mark.unit
class TestFIFO:
    """Tests for basic FIFO behavior."""

    def test_put_get_fifo(self):
        """Items dequeued in insertion order."""
        q = BoundedIngestQueue(maxsize=10, policy="drop_oldest")
        items = [MagicMock(name=f"item_{i}") for i in range(5)]
        for item in items:
            q.put(item)

        for expected in items:
            assert q.get() is expected

    def test_get_empty_returns_none(self):
        """Empty queue returns None."""
        q = BoundedIngestQueue(maxsize=10, policy="drop_oldest")
        assert q.get() is None

    def test_size_property(self):
        """Reflects current queue length."""
        q = BoundedIngestQueue(maxsize=10, policy="drop_oldest")
        assert q.size == 0
        q.put(MagicMock())
        assert q.size == 1
        q.put(MagicMock())
        assert q.size == 2
        q.get()
        assert q.size == 1


@pytest.mark.unit
class TestDropOldestPolicy:
    """Tests for drop_oldest overflow policy."""

    def test_drop_oldest_policy(self):
        """Full queue drops oldest on put."""
        q = BoundedIngestQueue(maxsize=3, policy="drop_oldest")

        items = [MagicMock(name=f"item_{i}") for i in range(5)]
        for item in items:
            q.put(item)

        # Queue maxlen=3 via deque, so oldest are auto-dropped
        # Should have items[2], items[3], items[4]
        assert q.size == 3
        assert q.get() is items[2]
        assert q.get() is items[3]
        assert q.get() is items[4]

    def test_drop_oldest_stats(self):
        """total_dropped incremented on drop."""
        q = BoundedIngestQueue(maxsize=2, policy="drop_oldest")
        q.put(MagicMock())
        q.put(MagicMock())
        q.put(MagicMock())  # Drops oldest

        assert q._total_dropped == 1

    def test_maxsize_respected(self):
        """Queue never exceeds maxsize for drop_oldest."""
        q = BoundedIngestQueue(maxsize=5, policy="drop_oldest")
        for i in range(100):
            q.put(MagicMock())
        assert q.size <= 5


@pytest.mark.unit
class TestDropNewestPolicy:
    """Tests for drop_newest overflow policy."""

    def test_drop_newest_policy(self):
        """Full queue rejects new item."""
        q = BoundedIngestQueue(maxsize=2, policy="drop_newest")
        item1 = MagicMock()
        item2 = MagicMock()
        item3 = MagicMock()

        assert q.put(item1) is True
        assert q.put(item2) is True
        assert q.put(item3) is False  # Rejected

        assert q.size == 2
        assert q.get() is item1  # Originals preserved
        assert q.get() is item2

    def test_drop_newest_returns_false(self):
        """put() returns False for rejected items."""
        q = BoundedIngestQueue(maxsize=1, policy="drop_newest")
        q.put(MagicMock())
        assert q.put(MagicMock()) is False


@pytest.mark.unit
class TestBlockPolicy:
    """Tests for block overflow policy."""

    def test_block_policy_no_limit(self):
        """Block mode accepts unlimited items."""
        q = BoundedIngestQueue(maxsize=2, policy="block")
        for i in range(100):
            assert q.put(MagicMock()) is True
        assert q.size == 100


@pytest.mark.unit
class TestBatchAndStats:
    """Tests for batch get and statistics."""

    def test_get_batch_returns_up_to_max(self):
        """Batch dequeue respects max_items."""
        q = BoundedIngestQueue(maxsize=100, policy="drop_oldest")
        for i in range(10):
            q.put(MagicMock())

        batch = q.get_batch(max_items=5)
        assert len(batch) == 5
        assert q.size == 5

    def test_get_batch_empty_returns_empty_list(self):
        """Empty queue -> []."""
        q = BoundedIngestQueue(maxsize=10, policy="drop_oldest")
        assert q.get_batch(max_items=5) == []

    def test_stats_counters(self):
        """total_put, total_get, total_dropped correct."""
        q = BoundedIngestQueue(maxsize=3, policy="drop_oldest")
        q.put(MagicMock())
        q.put(MagicMock())
        q.put(MagicMock())
        q.put(MagicMock())  # Drops oldest
        q.get()

        stats = q.stats
        assert stats["total_put"] == 4
        assert stats["total_get"] == 1
        assert stats["total_dropped"] == 1
        assert stats["capacity"] == 3
        assert stats["policy"] == "drop_oldest"

    def test_utilization_pct(self):
        """Percentage calculation correct."""
        q = BoundedIngestQueue(maxsize=10, policy="drop_oldest")
        for i in range(5):
            q.put(MagicMock())
        assert q.stats["utilization_pct"] == 50.0


@pytest.mark.unit
class TestThreadSafety:
    """Thread safety tests for concurrent access."""

    def test_concurrent_put_get(self):
        """Multiple threads doing put/get simultaneously."""
        q = BoundedIngestQueue(maxsize=1000, policy="drop_oldest")
        errors = []
        put_count = 500
        get_count = 500

        def producer():
            for i in range(put_count):
                try:
                    q.put(MagicMock())
                except Exception as e:
                    errors.append(e)

        def consumer():
            count = 0
            for _ in range(get_count):
                try:
                    q.get()
                    count += 1
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=producer),
            threading.Thread(target=producer),
            threading.Thread(target=consumer),
            threading.Thread(target=consumer),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0
        # Total puts = 1000, total_put counter should match
        assert q._total_put == put_count * 2
