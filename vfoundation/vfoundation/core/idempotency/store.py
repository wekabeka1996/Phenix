"""
Abstract interface for distributed idempotency store.

Provides exactly-once semantics across multiple workers via atomic reserve/confirm/release operations.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ReserveStatus(Enum):
    """Status codes for reserve operation."""
    NEW = "NEW"  # Successfully reserved (first time)
    DUPLICATE_SAME = "DUPLICATE_SAME"  # Same payload_digest (no-op)
    DUPLICATE_CONFLICT = "DUPLICATE_CONFLICT"  # Different payload_digest (conflict)
    EXTERN_OWNER = "EXTERN_OWNER"  # Held by another worker
    ERROR = "ERROR"  # Store error


class ConfirmStatus(Enum):
    """Status codes for confirm operation."""
    CONFIRMED = "CONFIRMED"  # Successfully confirmed
    MISSING = "MISSING"  # Record not found
    ERROR = "ERROR"  # Store error


class GetStatus(Enum):
    """Status codes for get_status operation."""
    EMPTY = "EMPTY"  # No record exists
    HELD = "HELD"  # Reserved but not confirmed
    CONFIRMED = "CONFIRMED"  # Confirmed (finalized)


class ReleaseStatus(Enum):
    """Status codes for release operation."""
    RELEASED = "RELEASED"  # Successfully released
    MISSING = "MISSING"  # Record not found
    ERROR = "ERROR"  # Store error


@dataclass
class ReserveResult:
    """Result of reserve operation."""
    status: ReserveStatus
    lease_ms: Optional[int] = None  # Lease duration if NEW
    owner: Optional[str] = None  # Owner if EXTERN_OWNER
    error: Optional[str] = None  # Error details if ERROR


@dataclass
class ConfirmResult:
    """Result of confirm operation."""
    status: ConfirmStatus
    error: Optional[str] = None


@dataclass
class StatusResult:
    """Result of get_status operation."""
    status: GetStatus
    owner: Optional[str] = None
    payload_digest: Optional[str] = None
    ts_ns: Optional[int] = None
    meta: Optional[Dict[str, Any]] = None


@dataclass
class ReleaseResult:
    """Result of release operation."""
    status: ReleaseStatus
    error: Optional[str] = None


@dataclass
class IdempotencyMetrics:
    """Metrics for idempotency operations."""
    idemp_reserve_total: Dict[str, int] = field(default_factory=dict)
    idemp_confirm_total: Dict[str, int] = field(default_factory=dict)
    idemp_release_total: Dict[str, int] = field(default_factory=dict)
    idemp_conflict_total: int = 0
    idemp_busy_total: int = 0
    idemp_retries_total: int = 0
    idemp_cb_open_total: int = 0
    
    # Latency tracking (milliseconds)
    reserve_latencies: List[float] = field(default_factory=list)
    confirm_latencies: List[float] = field(default_factory=list)
    
    def record_reserve_latency(self, latency_ms: float) -> None:
        """Record reserve operation latency."""
        self.reserve_latencies.append(latency_ms)
        # Keep last 1000 samples
        if len(self.reserve_latencies) > 1000:
            self.reserve_latencies.pop(0)
    
    def record_confirm_latency(self, latency_ms: float) -> None:
        """Record confirm operation latency."""
        self.confirm_latencies.append(latency_ms)
        if len(self.confirm_latencies) > 1000:
            self.confirm_latencies.pop(0)
    
    def get_p95_reserve_latency(self) -> Optional[float]:
        """Calculate p95 reserve latency."""
        if not self.reserve_latencies:
            return None
        sorted_lats = sorted(self.reserve_latencies)
        idx = int(len(sorted_lats) * 0.95)
        return sorted_lats[idx] if idx < len(sorted_lats) else sorted_lats[-1]
    
    def get_p95_confirm_latency(self) -> Optional[float]:
        """Calculate p95 confirm latency."""
        if not self.confirm_latencies:
            return None
        sorted_lats = sorted(self.confirm_latencies)
        idx = int(len(sorted_lats) * 0.95)
        return sorted_lats[idx] if idx < len(sorted_lats) else sorted_lats[-1]


class DistributedIdempotencyStore(ABC):
    """
    Abstract interface for distributed idempotency store.
    
    Ensures exactly-once semantics across multiple workers via atomic operations.
    """
    
    def __init__(self) -> None:
        """Initialize store."""
        self.metrics = IdempotencyMetrics()
    
    @abstractmethod
    def reserve(
        self,
        key: str,
        payload_digest: str,
        ttl_ms: int,
        owner: str
    ) -> ReserveResult:
        """
        Atomically reserve idempotency key.
        
        Args:
            key: Idempotent key (e.g., client_order_id)
            payload_digest: SHA256 digest of request payload
            ttl_ms: Lease duration in milliseconds
            owner: Worker/process identifier
        
        Returns:
            ReserveResult with status:
            - NEW: Successfully reserved (first time)
            - DUPLICATE_SAME: Same payload_digest (no-op, safe to proceed)
            - DUPLICATE_CONFLICT: Different payload_digest (reject)
            - EXTERN_OWNER: Held by another worker (busy)
            - ERROR: Store backend error
        
        Implementation must be atomic (use Lua script/transaction).
        """
        pass
    
    @abstractmethod
    def confirm(
        self,
        key: str,
        final_status: str,
        meta: Optional[Dict[str, Any]] = None
    ) -> ConfirmResult:
        """
        Confirm idempotency record with final status.
        
        Args:
            key: Idempotent key
            final_status: Final status (e.g., "ORDER_PLACED", "REJECTED")
            meta: Optional metadata (e.g., exchange_order_id, filled_qty)
        
        Returns:
            ConfirmResult with status:
            - CONFIRMED: Successfully confirmed
            - MISSING: Record not found
            - ERROR: Store backend error
        """
        pass
    
    @abstractmethod
    def get_status(self, key: str) -> StatusResult:
        """
        Get current status of idempotency record.
        
        Args:
            key: Idempotent key
        
        Returns:
            StatusResult with status:
            - EMPTY: No record exists
            - HELD: Reserved but not confirmed
            - CONFIRMED: Finalized with confirmation
        """
        pass
    
    @abstractmethod
    def release(self, key: str, owner: str) -> ReleaseResult:
        """
        Release idempotency key (cancel/timeout).
        
        Args:
            key: Idempotent key
            owner: Worker identifier (must match reserve owner)
        
        Returns:
            ReleaseResult with status:
            - RELEASED: Successfully released
            - MISSING: Record not found
            - ERROR: Store backend error
        
        Only current owner can release.
        """
        pass
    
    def _measure_latency(self, operation: str) -> "_LatencyMeasurer":
        """Context manager to measure and record operation latency."""
        return _LatencyMeasurer(self, operation)


class _LatencyMeasurer:
    """Context manager for latency measurement."""
    
    def __init__(self, store: DistributedIdempotencyStore, operation: str) -> None:
        self.store = store
        self.operation = operation
        self.start_ns = 0
    
    def __enter__(self) -> None:
        self.start_ns = time.time_ns()
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        elapsed_ns = time.time_ns() - self.start_ns
        latency_ms = elapsed_ns / 1_000_000
        
        if self.operation == "reserve":
            self.store.metrics.record_reserve_latency(latency_ms)
        elif self.operation == "confirm":
            self.store.metrics.record_confirm_latency(latency_ms)
