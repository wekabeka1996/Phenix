"""
XAI Store — explainability record storage.

Provides an ABC and in-memory implementation for storing XAI records
(why-chain event traceability data) per Constitution §9 (explainability).

These records are append-only, keyed by rid, and support:
- store(rid, record): append XAI record for a request
- get(rid): retrieve all records for a request
- list_rids(): list all tracked request IDs
- clear(): reset store (for testing)
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class XAIRecord:
    """
    Single explainability record for one FSM event in a request chain.

    Args:
        rid: Request ID this record belongs to
        step: Step number in the why-chain (0-indexed)
        verb: FSM verb that generated this record
        why: Human-readable reason (WHY-discipline, ≤80 chars)
        payload_summary: Optional short summary of payload (for audit)
        meta: Optional arbitrary metadata
    """

    def __init__(
        self,
        rid: str,
        step: int,
        verb: str,
        why: str,
        payload_summary: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        if len(why) > 80:
            raise ValueError(f"WHY must be ≤80 chars, got {len(why)}")
        self.rid = rid
        self.step = step
        self.verb = verb
        self.why = why
        self.payload_summary = payload_summary
        self.meta = meta or {}

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for storage/export."""
        return {
            "rid": self.rid,
            "step": self.step,
            "verb": self.verb,
            "why": self.why,
            "payload_summary": self.payload_summary,
            "meta": self.meta,
        }


class XAIStore(ABC):
    """Abstract base class for XAI record stores."""

    @abstractmethod
    def store(self, rid: str, record: XAIRecord) -> None:
        """Append an XAI record for the given request ID."""
        ...

    @abstractmethod
    def get(self, rid: str) -> List[XAIRecord]:
        """Return all XAI records for the given request ID, ordered by step."""
        ...

    @abstractmethod
    def list_rids(self) -> List[str]:
        """Return list of all tracked request IDs."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear all records (primarily for testing)."""
        ...


class InMemoryXAIStore(XAIStore):
    """
    Thread-safe in-memory XAI store.

    Uses a dict of rid → List[XAIRecord], capped at max_records_per_rid.
    Suitable for single-process use (tests, dev, local observability).
    """

    def __init__(self, max_records_per_rid: int = 1000) -> None:
        """
        Args:
            max_records_per_rid: Maximum XAI records per request ID (default 1000).
        """
        self._max_per_rid = max_records_per_rid
        self._store: Dict[str, List[XAIRecord]] = {}
        self._lock = threading.Lock()

    def store(self, rid: str, record: XAIRecord) -> None:
        """Append XAI record to this request's chain. Thread-safe."""
        with self._lock:
            if rid not in self._store:
                self._store[rid] = []
            records = self._store[rid]
            if len(records) < self._max_per_rid:
                records.append(record)

    def get(self, rid: str) -> List[XAIRecord]:
        """Return records for rid, ordered by step. Returns [] for unknown rid."""
        with self._lock:
            records = list(self._store.get(rid, []))
        return sorted(records, key=lambda r: r.step)

    def list_rids(self) -> List[str]:
        """Return sorted list of all tracked request IDs."""
        with self._lock:
            return sorted(self._store.keys())

    def clear(self) -> None:
        """Clear all records. Thread-safe."""
        with self._lock:
            self._store.clear()


xai_store = InMemoryXAIStore()


def append_why(
    rid: str,
    verb: str,
    why: str,
    payload_summary: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """Append a WHY-chain entry into the process-wide XAI store."""
    if not rid:
        return
    safe_why = (why or "UNKNOWN")[:80]
    step = len(xai_store.get(rid))
    record = XAIRecord(
        rid=rid,
        step=step,
        verb=verb,
        why=safe_why,
        payload_summary=payload_summary,
        meta=meta,
    )
    xai_store.store(rid, record)
