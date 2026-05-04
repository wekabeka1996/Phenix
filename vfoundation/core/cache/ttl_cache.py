"""
Monotonic TTL Cache with LRU Eviction and Background Janitor

Implements a thread-safe TTL cache using monotonic time (time.monotonic_ns())
with LRU eviction policy and background cleanup janitor.

Key features:
- Monotonic deadlines: immune to system clock changes
- LRU eviction: O(1) operations with OrderedDict
- Background janitor: periodic cleanup with configurable budget
- Thread-safe: uses RLock for all operations
- Metrics: comprehensive counters and gauges
- Fail-closed: graceful error handling without process crashes
"""

from __future__ import annotations
from typing import Dict, Any, Optional, Tuple, Callable, TypeVar, Generic
from collections import OrderedDict
import threading
import time
import logging
import os

K = TypeVar("K")
V = TypeVar("V")

logger = logging.getLogger(__name__)


def ns_from_ms(ms: int) -> int:
    """Convert milliseconds to nanoseconds"""
    return ms * 1_000_000


def ms_from_ns(ns: int) -> int:
    """Convert nanoseconds to milliseconds (floor)"""
    return ns // 1_000_000


def now_ns() -> int:
    """Get current monotonic time in nanoseconds"""
    return time.monotonic_ns()


def now_ms() -> int:
    """Get current monotonic time in milliseconds"""
    return ms_from_ns(time.monotonic_ns())


class CleanupStats:
    """Statistics from cleanup operation"""

    def __init__(self, expired: int, scanned: int, remaining: int):
        self.expired = expired
        self.scanned = scanned
        self.remaining = remaining

    def __repr__(self) -> str:
        return f"CleanupStats(expired={self.expired}, scanned={self.scanned}, remaining={self.remaining})"


class MonotonicTTLCache(Generic[K, V]):
    """
    Thread-safe TTL cache with monotonic time, LRU eviction, and background janitor.

    Uses time.monotonic_ns() for deadlines, ensuring immunity to system clock changes.
    LRU implemented with OrderedDict for O(1) operations.
    Background janitor thread performs periodic cleanup.
    """

    def __init__(
        self,
        max_entries: int = 10000,
        default_ttl_ms: Optional[int] = None,
        janitor_interval_ms: int = 500,
        scan_budget: int = 2000,
        clock: Callable[[], int] = time.monotonic_ns,
    ):
        """
        Initialize the cache.

        Args:
            max_entries: Maximum number of entries before LRU eviction
            default_ttl_ms: Default TTL in milliseconds (None = no default)
            janitor_interval_ms: Janitor cleanup interval
            scan_budget: Maximum entries to scan per cleanup cycle
            clock: Clock function (default: time.monotonic_ns)
        """
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        if default_ttl_ms is not None and default_ttl_ms <= 0:
            raise ValueError("default_ttl_ms must be positive")
        if janitor_interval_ms <= 0:
            raise ValueError("janitor_interval_ms must be positive")
        if scan_budget <= 0:
            raise ValueError("scan_budget must be positive")

        self.max_entries = max_entries
        self.default_ttl_ms = default_ttl_ms
        self.janitor_interval_ms = janitor_interval_ms
        self.scan_budget = scan_budget
        self.clock = clock

        # Core storage: OrderedDict for LRU (most recent at end)
        self._data: OrderedDict[K, Tuple[V, int]] = OrderedDict()  # key -> (value, deadline_ns)
        self._pinned: set[K] = set()  # Keys that should not be evicted by LRU

        # Thread safety
        self._lock = threading.RLock()

        # Janitor thread
        self._janitor_thread: Optional[threading.Thread] = None
        self._janitor_stop_event = threading.Event()
        self._janitor_running = False
        self._janitor_pid = os.getpid()  # Track process ID for multi-process safety

        # Metrics (thread-safe counters)
        self._metrics_lock = threading.Lock()
        self._metrics = {
            "janitor_runs_total": 0,
            "janitor_expired_total": 0,
            "janitor_evicted_total": 0,  # Note: this is for janitor evictions, separate from LRU evictions
            "cache_hits_total": 0,
            "cache_misses_total": 0,
            "cache_stale_hits_total": 0,
            "cache_evictions_total": 0,  # LRU evictions
            "cache_entries": 0,  # Gauge
            "janitor_last_run_ts": 0.0,  # Gauge, epoch seconds
            "janitor_errors_total": 0,
            "janitor_threads_active": 0,  # Gauge
        }

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics snapshot"""
        with self._metrics_lock:
            return self._metrics.copy()

    def set(self, key: K, value: V, ttl_ms: Optional[int] = None, pinned: bool = False) -> None:
        """
        Set a value with TTL.

        Args:
            key: Cache key
            value: Value to store
            ttl_ms: TTL in milliseconds (uses default_ttl_ms if None)
            pinned: If True, entry will not be evicted by LRU

        Raises:
            ValueError: If ttl_ms is invalid
        """
        if ttl_ms is None:
            if self.default_ttl_ms is None:
                raise ValueError("ttl_ms required when no default_ttl_ms set")
            ttl_ms = self.default_ttl_ms

        if ttl_ms <= 0:
            raise ValueError("ttl_ms must be positive")

        deadline_ns = self.clock() + ns_from_ms(ttl_ms)

        with self._lock:
            # Remove existing entry if present (will be re-added at end)
            self._data.pop(key, None)
            self._pinned.discard(key)

            # Evict if at capacity (LRU eviction) - skip pinned entries
            while len(self._data) >= self.max_entries:
                # Find LRU entry that's not pinned
                evicted_key = None
                for candidate in self._data:
                    if candidate not in self._pinned:
                        evicted_key = candidate
                        break

                if evicted_key is None:
                    # All entries are pinned, cannot evict
                    logger.warning(
                        f"Cannot evict: all {len(self._data)} entries are pinned, max_entries={self.max_entries}"
                    )
                    break

                # Remove the evicted entry
                _, _ = self._data.pop(evicted_key)
                self._pinned.discard(evicted_key)
                with self._metrics_lock:
                    self._metrics["cache_evictions_total"] += 1
                logger.debug(f"LRU evicted key: {evicted_key}")

            # Add new entry (most recent)
            self._data[key] = (value, deadline_ns)
            if pinned:
                self._pinned.add(key)

            with self._metrics_lock:
                self._metrics["cache_entries"] = len(self._data)

    def get(self, key: K) -> Optional[V]:
        """
        Get a value if not expired, moving it to most recent in LRU.

        Returns:
            Value if found and not expired, None otherwise
        """
        with self._lock:
            if key not in self._data:
                with self._metrics_lock:
                    self._metrics["cache_misses_total"] += 1
                return None

            value, deadline_ns = self._data[key]
            now_ns = self.clock()

            if now_ns >= deadline_ns:
                # Expired: remove and count as stale hit
                del self._data[key]
                with self._metrics_lock:
                    self._metrics["cache_stale_hits_total"] += 1
                    self._metrics["cache_entries"] = len(self._data)
                return None

            # Valid: move to end (most recent) and return
            self._data.move_to_end(key)
            with self._metrics_lock:
                self._metrics["cache_hits_total"] += 1
            return value

    def peek(self, key: K) -> Optional[Tuple[V, int]]:
        """
        Peek at a value and deadline without changing LRU order.

        Returns:
            (value, deadline_ns) if found, None otherwise
        """
        with self._lock:
            entry = self._data.get(key)
            return entry

    def delete(self, key: K) -> bool:
        """
        Delete a key.

        Returns:
            True if key existed and was deleted, False otherwise
        """
        with self._lock:
            if key in self._data:
                del self._data[key]
                self._pinned.discard(key)
                with self._metrics_lock:
                    self._metrics["cache_entries"] = len(self._data)
                return True
            return False

    def cleanup_expired(self, budget: Optional[int] = None) -> CleanupStats:
        """
        Scan and remove expired entries up to budget.

        Args:
            budget: Maximum entries to scan (uses self.scan_budget if None)

        Returns:
            CleanupStats with operation results
        """
        if budget is None:
            budget = self.scan_budget

        now_ns = self.clock()

        # Phase 1: Collect expired keys under lock
        with self._lock:
            keys_to_remove = []
            scanned_count = 0

            for key in list(
                self._data.keys()
            ):  # Create snapshot to avoid modification during iteration
                if scanned_count >= budget:
                    break
                scanned_count += 1

                _, deadline_ns = self._data[key]
                if now_ns >= deadline_ns:
                    keys_to_remove.append(key)

        # Phase 2: Remove expired entries outside lock
        expired_count = 0
        for key in keys_to_remove:
            # Double-check expiration outside lock (entry might have been refreshed)
            with self._lock:
                if key in self._data:
                    value, deadline_ns = self._data[key]
                    if now_ns >= deadline_ns:
                        del self._data[key]
                        self._pinned.discard(key)
                        expired_count += 1
                        with self._metrics_lock:
                            self._metrics["cache_entries"] = len(self._data)

        with self._metrics_lock:
            self._metrics["janitor_expired_total"] += expired_count

        return CleanupStats(expired=expired_count, scanned=scanned_count, remaining=len(self._data))

    def size(self) -> int:
        """Get current number of entries"""
        with self._lock:
            return len(self._data)

    def capacity(self) -> int:
        """Get maximum capacity"""
        return self.max_entries

    def start_janitor(self) -> None:
        """Start the background janitor thread (idempotent, multi-process safe)"""
        current_pid = os.getpid()

        with self._lock:
            # Multi-process guard: only allow janitor in the process that created the cache
            if self._janitor_pid != current_pid:
                logger.warning(
                    f"Janitor start blocked: cache created in PID {self._janitor_pid}, current PID {current_pid}"
                )
                return

            if self._janitor_running:
                return

            self._janitor_stop_event.clear()
            self._janitor_thread = threading.Thread(
                target=self._janitor_loop,
                daemon=True,
                name=f"MonotonicTTLCache-Janitor-PID{current_pid}",
            )
            self._janitor_thread.start()
            self._janitor_running = True
            with self._metrics_lock:
                self._metrics["janitor_threads_active"] = 1
            logger.info(f"Janitor thread started in PID {current_pid}")

    def stop_janitor(self, timeout_s: float = 2.0) -> None:
        """Stop the background janitor thread"""
        with self._lock:
            if not self._janitor_running:
                return

            self._janitor_stop_event.set()

        if self._janitor_thread:
            self._janitor_thread.join(timeout=timeout_s)
            if self._janitor_thread.is_alive():
                logger.warning("Janitor thread did not stop within timeout")
            else:
                logger.info("Janitor thread stopped")
                with self._metrics_lock:
                    self._metrics["janitor_threads_active"] = 0

        with self._lock:
            self._janitor_running = False

    def _janitor_loop(self) -> None:
        """Background janitor loop"""
        while not self._janitor_stop_event.is_set():
            try:
                # Perform cleanup
                stats = self.cleanup_expired()

                # Update metrics
                with self._metrics_lock:
                    self._metrics["janitor_runs_total"] += 1
                    self._metrics["janitor_last_run_ts"] = time.time()

                # Log if significant cleanup
                if stats.expired > 0:
                    logger.debug(f"Janitor cleaned {stats.expired} expired entries")

                # Sleep until next cycle
                if self._janitor_stop_event.wait(timeout=self.janitor_interval_ms / 1000.0):
                    break  # Stop event was set

            except Exception as e:
                logger.error(f"Janitor error: {e}", exc_info=True)
                with self._metrics_lock:
                    self._metrics["janitor_errors_total"] += 1

                # Brief backoff on error
                if not self._janitor_stop_event.wait(timeout=1.0):
                    continue
