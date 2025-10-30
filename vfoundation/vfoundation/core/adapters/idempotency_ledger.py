"""
Idempotency Ledger (FSMP-P2-T01)

Lightweight in-memory ledger for exactly-once semantics at adapter boundary.
Stores {key, first_seen_ts, last_status, last_payload_digest} with TTL and LRU eviction.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass
class LedgerEntry:
    """Single ledger entry for idempotency tracking."""

    key: str
    first_seen_ts: float  # Unix timestamp when first seen
    last_status: str  # Last known status (e.g., "ORDER_PLACED", "CANCELLED")
    last_payload_digest: str  # SHA256 digest of last response payload
    last_event: Optional[Dict[str, Any]] = None  # Last event returned


class IdempotencyLedger:
    """
    In-memory idempotency ledger with TTL and LRU eviction.

    Thread-safe implementation for concurrent adapter operations.
    """

    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 10000) -> None:
        """
        Initialize ledger.

        Args:
            ttl_seconds: Time-to-live for entries (default 1 hour)
            max_entries: Maximum entries before LRU eviction
        """
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries

        self._ledger: Dict[str, LedgerEntry] = {}
        self._lock = threading.RLock()

        # LRU tracking: map key → last_access_ts
        self._access_times: Dict[str, float] = {}

    def check_and_store(
        self, key: str, status: str, payload: Dict[str, Any], event: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check if key exists, store if new.

        Args:
            key: Idempotency key
            status: Operation status (e.g., "ORDER_PLACED")
            payload: Response payload for digest calculation
            event: Event to return on duplicate

        Returns:
            Tuple of (is_duplicate, last_event_if_duplicate)
            - (False, None): New operation, stored
            - (True, last_event): Duplicate, returning cached event
        """
        with self._lock:
            now = time.time()

            # Check for existing entry
            if key in self._ledger:
                entry = self._ledger[key]

                # Check TTL
                if now - entry.first_seen_ts > self.ttl_seconds:
                    # Expired, treat as new
                    self._store_entry(key, status, payload, event, now)
                    return (False, None)

                # Valid duplicate - update access time and return cached event
                self._access_times[key] = now
                return (True, entry.last_event)

            # New entry - store it
            self._store_entry(key, status, payload, event, now)
            return (False, None)

    def _store_entry(
        self,
        key: str,
        status: str,
        payload: Dict[str, Any],
        event: Optional[Dict[str, Any]],
        timestamp: float,
    ) -> None:
        """
        Store entry in ledger (internal, assumes lock held).

        Args:
            key: Idempotency key
            status: Operation status
            payload: Response payload
            event: Event to cache
            timestamp: Current timestamp
        """
        # Evict LRU if at capacity
        if len(self._ledger) >= self.max_entries:
            self._evict_lru()

        # Calculate payload digest
        payload_str = str(sorted(payload.items()))  # Deterministic serialization
        digest = hashlib.sha256(payload_str.encode()).hexdigest()

        # Store entry
        entry = LedgerEntry(
            key=key,
            first_seen_ts=timestamp,
            last_status=status,
            last_payload_digest=digest,
            last_event=event,
        )
        self._ledger[key] = entry
        self._access_times[key] = timestamp

    def _evict_lru(self) -> None:
        """
        Evict least recently used entry (internal, assumes lock held).
        """
        if not self._access_times:
            return

        # Find LRU key
        lru_key = min(self._access_times.items(), key=lambda x: x[1])[0]

        # Remove from ledger and access times
        del self._ledger[lru_key]
        del self._access_times[lru_key]

    def get(self, key: str) -> Optional[LedgerEntry]:
        """
        Get entry by key (returns None if not found or expired).

        Args:
            key: Idempotency key

        Returns:
            LedgerEntry if found and valid, None otherwise
        """
        with self._lock:
            if key not in self._ledger:
                return None

            entry = self._ledger[key]
            now = time.time()

            # Check TTL
            if now - entry.first_seen_ts > self.ttl_seconds:
                # Expired, remove and return None
                del self._ledger[key]
                del self._access_times[key]
                return None

            # Update access time
            self._access_times[key] = now
            return entry

    def clear(self) -> None:
        """Clear all entries (useful for testing)."""
        with self._lock:
            self._ledger.clear()
            self._access_times.clear()

    def size(self) -> int:
        """Get current ledger size."""
        with self._lock:
            return len(self._ledger)

    def stats(self) -> Dict[str, Any]:
        """
        Get ledger statistics.

        Returns:
            Dictionary with size, max_entries, ttl_seconds
        """
        with self._lock:
            return {
                "size": len(self._ledger),
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
                "oldest_entry_age_seconds": self._get_oldest_age(),
            }

    def _get_oldest_age(self) -> Optional[float]:
        """Get age of oldest entry in seconds (internal, assumes lock held)."""
        if not self._ledger:
            return None

        now = time.time()
        oldest_ts = min(entry.first_seen_ts for entry in self._ledger.values())
        return now - oldest_ts
