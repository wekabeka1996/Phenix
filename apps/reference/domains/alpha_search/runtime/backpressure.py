"""
Backpressure Queue
==================

Bounded queue between IngestGateway and ScenarioManager.

Policies:
- drop_oldest: for live low-latency mode (default)
- drop_newest: discard incoming when full
- block: for deterministic replay (back-pressure to reader)
"""

import collections
import logging
import threading
from typing import Any, Dict, Optional

from .contracts import AlphaInputV1

LOG = logging.getLogger(__name__)


class BoundedIngestQueue:
    """
    Bounded FIFO queue with configurable overflow policy.

    Thread-safe for producer/consumer patterns between
    IngestGateway (producer) and ScenarioManager (consumer).
    """

    def __init__(
        self,
        maxsize: int = 4000,
        policy: str = "drop_oldest",
    ):
        self._maxsize = maxsize
        self._policy = policy
        self._lock = threading.Lock()

        if policy == "drop_oldest":
            self._queue: collections.deque = collections.deque(maxlen=maxsize)
        else:
            self._queue = collections.deque()

        # Stats
        self._total_put = 0
        self._total_dropped = 0
        self._total_get = 0

    def put(self, item: AlphaInputV1) -> bool:
        """
        Enqueue a snapshot.

        Returns True if accepted, False if dropped.
        For 'block' policy, always returns True (waits indefinitely).
        """
        with self._lock:
            self._total_put += 1

            if self._policy == "drop_oldest":
                # deque with maxlen auto-drops oldest
                was_full = len(self._queue) >= self._maxsize
                self._queue.append(item)
                if was_full:
                    self._total_dropped += 1
                return True

            elif self._policy == "drop_newest":
                if len(self._queue) >= self._maxsize:
                    self._total_dropped += 1
                    return False
                self._queue.append(item)
                return True

            elif self._policy == "block":
                # For replay mode: just accept (no bound)
                self._queue.append(item)
                return True

            return False

    def get(self) -> Optional[AlphaInputV1]:
        """Dequeue oldest snapshot. Returns None if empty."""
        with self._lock:
            if self._queue:
                self._total_get += 1
                return self._queue.popleft()
            return None

    def get_batch(self, max_items: int = 10) -> list:
        """Dequeue up to max_items snapshots at once."""
        with self._lock:
            items = []
            while self._queue and len(items) < max_items:
                items.append(self._queue.popleft())
                self._total_get += 1
            return items

    @property
    def size(self) -> int:
        return len(self._queue)

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "size": len(self._queue),
            "capacity": self._maxsize,
            "policy": self._policy,
            "total_put": self._total_put,
            "total_get": self._total_get,
            "total_dropped": self._total_dropped,
            "utilization_pct": round(
                len(self._queue) / max(self._maxsize, 1) * 100, 1
            ),
        }
