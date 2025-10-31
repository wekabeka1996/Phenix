from __future__ import annotations
from typing import Dict, Any, Optional
import threading
import time
from enum import Enum
from ..cache.ttl_cache import MonotonicTTLCache
from ...config import config


class InflightState(Enum):
    """State of an inflight request"""

    PENDING = "pending"
    DONE = "done"


class IdempotencyStore:
    def __init__(
        self,
        default_ttl_ms: Optional[int] = None,
        max_entries: Optional[int] = None,
        idem_pending_ttl_ms: Optional[int] = None,
        idem_inflight_cap: int = 1000,
    ) -> None:
        # Use config defaults if not explicitly provided
        if default_ttl_ms is None:
            default_ttl_ms = config.idem_ttl_ms
        if max_entries is None:
            max_entries = config.idem_max_entries

        self._lock = threading.Lock()
        self._seen: Dict[str, Any] = {}  # RID -> result (legacy)
        self._cache = MonotonicTTLCache[str, Any](
            max_entries=max_entries, default_ttl_ms=default_ttl_ms
        )
        self.default_ttl_ms = default_ttl_ms
        self.idem_pending_ttl_ms = idem_pending_ttl_ms or (
            default_ttl_ms * 2
        )  # Default: 2x result TTL
        self.idem_inflight_cap = idem_inflight_cap  # Admission control for concurrent PENDING

        # Single-flight: per-key locks and inflight registry
        self._key_locks: Dict[str, threading.Lock] = {}  # idempotent_key -> Lock
        self._inflight: Dict[
            str, tuple[InflightState, Optional[Any], int]
        ] = {}  # key -> (state, result, expire_monotonic_ns)

        # Metrics
        self._metrics = {
            "idem_acquired": 0,
            "idem_inflight": 0,
            "idem_dedup": 0,
            "idem_inflight_evicted_total": 0,
            "idem_pending_ttl_near_expiry_total": 0,
            "idem_inflight_over_cap_total": 0,
            "idem_inflight_cardinality": 0,  # Gauge
            "idem_inflight_duration_ms_p95": 0.0,  # Gauge, p95 of inflight durations
        }

    def get_metrics(self) -> Dict[str, Any]:
        """Get idempotency metrics including cache metrics"""
        cache_metrics = self._cache.get_metrics()
        with self._lock:
            metrics = self._metrics.copy()

        # Merge cache metrics
        metrics.update(
            {
                "cache_entries": cache_metrics.get("cache_entries", 0),
                "cache_hits_total": cache_metrics.get("cache_hits_total", 0),
                "cache_misses_total": cache_metrics.get("cache_misses_total", 0),
                "cache_stale_hits_total": cache_metrics.get("cache_stale_hits_total", 0),
                "cache_evictions_total": cache_metrics.get("cache_evictions_total", 0),
                "janitor_runs_total": cache_metrics.get("janitor_runs_total", 0),
                "janitor_expired_total": cache_metrics.get("janitor_expired_total", 0),
                "janitor_evicted_total": cache_metrics.get("janitor_evicted_total", 0),
                "janitor_last_run_ts": cache_metrics.get("janitor_last_run_ts", 0.0),
                "janitor_errors_total": cache_metrics.get("janitor_errors_total", 0),
                "idem_inflight_evicted_total": self._metrics.get("idem_inflight_evicted_total", 0),
                "idem_pending_ttl_near_expiry_total": self._metrics.get(
                    "idem_pending_ttl_near_expiry_total", 0
                ),
            }
        )
        return metrics

    def begin(self, idempotent_key: str) -> Dict[str, bool]:
        """
        Try to begin processing for idempotent_key (single-flight).

        Returns:
            {"acquired": True} - caller should execute handler
            {"inflight": True} - another request is processing this key
        """
        with self._lock:
            # Check if already completed (cached result)
            cached_result = self._cache.get(idempotent_key)
            if cached_result is not None and cached_result != "__PENDING__":
                self._metrics["idem_dedup"] += 1
                return {"dedup": True}  # Will be handled by get_if_done

            # Check if currently inflight
            if idempotent_key in self._inflight:
                state, _, expire_monotonic_ns = self._inflight[idempotent_key]
                current_monotonic_ns = time.monotonic_ns()

                if current_monotonic_ns <= expire_monotonic_ns and state == InflightState.PENDING:
                    self._metrics["idem_inflight"] += 1
                    return {"inflight": True}
                else:
                    # Expired or done, remove
                    del self._inflight[idempotent_key]

            # Admission control: check inflight capacity
            pending_count = sum(
                1 for state, _, _ in self._inflight.values() if state == InflightState.PENDING
            )
            if pending_count >= self.idem_inflight_cap:
                self._metrics["idem_inflight_over_cap_total"] += 1
                return {"over_cap": True}  # Backpressure: too many concurrent requests

            # Acquire: mark as inflight PENDING
            expire_monotonic_ns = time.monotonic_ns() + self.idem_pending_ttl_ms * 1_000_000
            self._inflight[idempotent_key] = (InflightState.PENDING, None, expire_monotonic_ns)

            # Pin the key in cache to prevent LRU eviction during processing
            # Use a sentinel value to indicate PENDING state
            self._cache.set(
                idempotent_key, "__PENDING__", ttl_ms=self.idem_pending_ttl_ms, pinned=True
            )

            self._metrics["idem_acquired"] += 1
            self._metrics["idem_inflight_cardinality"] = len(self._inflight)

            return {"acquired": True}

    def complete(self, idempotent_key: str, result: Any, ttl_ms: Optional[int] = None) -> None:
        """
        Mark inflight request as complete and cache result for subsequent requests.

        Args:
            idempotent_key: The key to complete
            result: Result to cache
            ttl_ms: TTL for cached result (default: self.default_ttl_ms)
        """
        if ttl_ms is None:
            ttl_ms = self.default_ttl_ms

        with self._lock:
            # Update inflight to DONE (use longer TTL to survive cache expiry)
            done_ttl_ms = max(ttl_ms, self.idem_pending_ttl_ms)
            if idempotent_key in self._inflight:
                self._inflight[idempotent_key] = (
                    InflightState.DONE,
                    result,
                    time.monotonic_ns() + done_ttl_ms * 1_000_000,
                )

            # Update pinned cache entry with actual result (keep pinned=True)
            self._cache.set(idempotent_key, result, ttl_ms, pinned=True)

    def get_if_done(self, idempotent_key: str) -> Optional[Any]:
        """
        Get result if request is done (either from cache or completed inflight).

        Returns:
            Result if available, None if not found or still pending
        """
        with self._lock:
            # Check cache first (skip PENDING sentinels)
            cached_result = self._cache.get(idempotent_key)
            if cached_result is not None and cached_result != "__PENDING__":
                return cached_result

            # Check inflight (might be DONE but not yet in cache)
            if idempotent_key in self._inflight:
                state, result, expire_monotonic_ns = self._inflight[idempotent_key]
                current_monotonic_ns = time.monotonic_ns()
                if current_monotonic_ns <= expire_monotonic_ns and state == InflightState.DONE:
                    return result

            return None

    # Legacy methods remain unchanged for backward compatibility
    def seen(self, rid: str) -> bool:
        """Legacy method for RID-based idempotency"""
        with self._lock:
            return rid in self._seen

    def remember(self, rid: str, result: Any) -> None:
        """Legacy method for RID-based idempotency"""
        with self._lock:
            self._seen[rid] = result

    def get(self, rid: str) -> Any:
        """Legacy method for RID-based idempotency"""
        with self._lock:
            return self._seen.get(rid)

    def key_seen(self, idempotent_key: str) -> bool:
        """Check if idempotent key has been seen (and not expired)"""
        with self._lock:
            return self._cache.get(idempotent_key) is not None

    def key_remember(self, idempotent_key: str, result: Any, ttl_ms: Optional[int] = None) -> None:
        """Remember result for idempotent key with TTL"""
        self._cache.set(idempotent_key, result, ttl_ms, pinned=False)

    def key_get(self, idempotent_key: str) -> Optional[Any]:
        """Get cached result for idempotent key if not expired"""
        return self._cache.get(idempotent_key)

    def cleanup_expired(self) -> None:
        """Manual cleanup of expired entries in cache and inflight registry"""
        # Cleanup cache
        self._cache.cleanup_expired()

        # Cleanup expired inflight entries
        with self._lock:
            current_monotonic_ns = time.monotonic_ns()
            expired_keys = []

            for key, (state, result, expire_monotonic_ns) in self._inflight.items():
                if current_monotonic_ns > expire_monotonic_ns:
                    expired_keys.append(key)
                    self._metrics["idem_inflight_evicted_total"] += 1

                    # Alert if PENDING expired (potential duplicate execution)
                    if state == InflightState.PENDING:
                        self._metrics["idem_pending_ttl_near_expiry_total"] += 1
                        # Note: This is actually expiry, not "near". Metric name could be improved

            for key in expired_keys:
                del self._inflight[key]
                # Unpin expired PENDING entries from cache
                if self._cache.get(key) == "__PENDING__":
                    # Force remove the sentinel (this will unpin it)
                    self._cache.delete(key)

    def start_janitor(self) -> None:
        """Start background janitor for cache cleanup"""
        self._cache.start_janitor()

    def stop_janitor(self, timeout_s: float = 2.0) -> None:
        """Stop background janitor"""
        self._cache.stop_janitor(timeout_s)
