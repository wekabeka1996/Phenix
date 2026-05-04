"""
Backpressure Contract — Phase 17.4.

Per-key bounded queues with ACCEPT/THROTTLE/REJECT actions.
Thread-safe for concurrent producers.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Dict, List, Optional


class BackpressureAction(Enum):
    """Result of an offer() attempt."""

    ACCEPT = "accept"
    THROTTLE = "throttle"
    REJECT = "reject"


@dataclass
class QueueStats:
    """Snapshot of a single queue's state."""

    key: str
    current_size: int
    max_size: int
    total_offered: int = 0
    total_rejected: int = 0
    p95_latency_ms: float = 0.0
    throttle_active: bool = False

    @property
    def utilization_pct(self) -> float:
        """Current utilization as percentage 0-100."""
        if self.max_size <= 0:
            return 100.0
        return (self.current_size / self.max_size) * 100.0


class BoundedQueue:
    """
    Per-key bounded queue with backpressure signals.

    - ACCEPT: item added, queue below throttle threshold
    - THROTTLE: item added, but queue above throttle_pct
    - REJECT: queue full, item NOT added
    """

    def __init__(
        self,
        max_size: int = 1000,
        throttle_pct: float = 80.0,
    ) -> None:
        self._max_size = max_size
        self._throttle_pct = throttle_pct
        self._queues: Dict[str, Deque[Any]] = {}
        self._stats: Dict[str, QueueStats] = {}
        self._offer_timestamps: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def offer(self, key: str, item: Any) -> BackpressureAction:
        """
        Attempt to enqueue an item under the given key.

        Returns:
            ACCEPT if below throttle threshold.
            THROTTLE if above threshold but still under max.
            REJECT if queue is full (item NOT added).
        """
        with self._lock:
            q = self._queues.setdefault(key, deque())
            st = self._stats.setdefault(
                key, QueueStats(key=key, current_size=0, max_size=self._max_size)
            )
            ts_deque = self._offer_timestamps.setdefault(key, deque(maxlen=self._max_size))
            st.total_offered += 1

            if len(q) >= self._max_size:
                st.total_rejected += 1
                return BackpressureAction.REJECT

            q.append(item)
            ts_deque.append(time.monotonic())
            st.current_size = len(q)
            st.throttle_active = st.utilization_pct >= self._throttle_pct

            if st.throttle_active:
                return BackpressureAction.THROTTLE
            return BackpressureAction.ACCEPT

    def poll(self, key: str) -> Optional[Any]:
        """Dequeue one item from the key's queue. Returns None if empty."""
        with self._lock:
            q = self._queues.get(key)
            if not q:
                return None
            item = q.popleft()
            st = self._stats.get(key)
            if st:
                st.current_size = len(q)
            return item

    def stats(self, key: str) -> Optional[QueueStats]:
        """Get stats for a specific key, with p95 latency computation."""
        with self._lock:
            st = self._stats.get(key)
            if st is not None:
                ts_deque = self._offer_timestamps.get(key)
                if ts_deque and len(ts_deque) >= 2:
                    intervals = [
                        (ts_deque[i] - ts_deque[i - 1]) * 1000.0
                        for i in range(1, len(ts_deque))
                    ]
                    intervals.sort()
                    idx = max(0, int(len(intervals) * 0.95) - 1)
                    st.p95_latency_ms = intervals[idx]
            return st

    def all_stats(self) -> List[QueueStats]:
        """Get stats for all keys."""
        with self._lock:
            return list(self._stats.values())

    def is_throttled(self, key: str) -> bool:
        """Blueprint 17.4: True if the key's queue is in throttle zone."""
        with self._lock:
            st = self._stats.get(key)
            if st is None:
                return False
            return st.utilization_pct >= self._throttle_pct
