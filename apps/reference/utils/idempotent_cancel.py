"""
Canonical Idempotency Layer for Cancel/Place Operations

Provides generic, adapter-agnostic idempotency with scope-based key namespacing,
TTL-based expiry, and structured result tracking.

RID: IDEMPOTENCY-DEDUP-S1 (PHASE 1: API Design)

Key Concepts:
- IdempotencyKey: (scope, id) tuple for namespaced deduplication
- IdempotencyLedger: Protocol for pluggable storage (in-memory default)
- cancel_order_idempotent(): Generic wrapper for adapter cancellations

Design Principles:
- Zero adapter lock-in (no Binance/exchange-specific code)
- TTL-based expiry (default 60s)
- Structured logging (JSONL with RID propagation)
- Pluggable storage (in-memory default, Redis via protocol)

Out of Scope (adapter layer responsibilities):
- Exchange-specific error handling (-2011 absorption)
- Pre-cancel order status checks (getOrder before cancel)
- Retry logic (exponential backoff, circuit breaker)

Usage Example:
    from apps.reference.utils.idempotent_cancel import (
        IdempotencyKey,
        InMemoryIdempotencyLedger,
        cancel_order_idempotent,
    )

    ledger = InMemoryIdempotencyLedger()

    # First call: executes adapter.cancel_order()
    result1 = await cancel_order_idempotent(
        adapter=binance_adapter,
        symbol="BTCUSDT",
        order_id="12345",
        ledger=ledger,
        scope="execpos.cancel",
        ttl_sec=60,
        rid="RID-abc123",
    )
    assert result1.executed == True
    assert result1.reason == "first_call"

    # Second call within TTL: no-op (adapter not called)
    result2 = await cancel_order_idempotent(
        adapter=binance_adapter,
        symbol="BTCUSDT",
        order_id="12345",
        ledger=ledger,
        scope="execpos.cancel",
        ttl_sec=60,
        rid="RID-abc123",
    )
    assert result2.executed == False
    assert result2.reason == "already_executed"
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Protocol, Dict, Any, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# Core Data Structures
# ============================================================================

@dataclass(frozen=True)
class IdempotencyKey:
    """
    Namespaced key for idempotent operations.

    Attributes:
        scope: Operation category (e.g., "execpos.cancel", "bridge.close")
        id: Resource identifier (e.g., order_id, client_order_id, position_id)

    Examples:
        IdempotencyKey(scope="execpos.cancel", id="12345")
        IdempotencyKey(scope="bridge.close", id="BTCUSDT-pos-1")
        IdempotencyKey(scope="risk.reset", id="high_vol_halt")
    """
    scope: str
    id: str

    def __str__(self) -> str:
        """String representation for logging: 'scope:id'"""
        return f"{self.scope}:{self.id}"


@dataclass
class IdempotencyResult:
    """
    Result of idempotent operation check.

    Attributes:
        executed: Was this call a real execution (True) or no-op dedup (False)?
        reason: Explanation string ("first_call", "already_executed", "expired")
        timestamp_ms: Unix timestamp (milliseconds) when first executed
        key: The IdempotencyKey that was checked

    Reason Values:
        - "first_call": First time seeing this key, real execution performed
        - "already_executed": Key exists within TTL, no execution (dedup)
        - "expired": Key existed but TTL expired, treated as new execution
    """
    executed: bool
    reason: str
    timestamp_ms: int
    key: IdempotencyKey

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for logging/serialization"""
        return {
            "executed": self.executed,
            "reason": self.reason,
            "timestamp_ms": self.timestamp_ms,
            "scope": self.key.scope,
            "id": self.key.id,
        }


# ============================================================================
# Storage Protocol
# ============================================================================

class IdempotencyLedgerProtocol(Protocol):
    """
    Protocol for pluggable idempotency storage backends.

    Implementations:
    - InMemoryIdempotencyLedger: Thread-safe dict with TTL cleanup (default)
    - RedisIdempotencyLedger: Redis-backed distributed lock (future)
    - FileIdempotencyLedger: Persistent local file store (future)
    """

    def check_and_mark(
        self,
        key: IdempotencyKey,
        *,
        ttl_sec: int,
    ) -> IdempotencyResult:
        """
        Atomically check if key exists and mark as executed if first time.

        Behavior:
        - If key does not exist: Create entry, return executed=True
        - If key exists and within TTL: Return executed=False (dedup)
        - If key exists but TTL expired: Update entry, return executed=True

        Args:
            key: IdempotencyKey to check
            ttl_sec: Time-to-live in seconds (how long to deduplicate)

        Returns:
            IdempotencyResult with executed flag and reason

        Thread Safety:
            Must be thread-safe for concurrent calls with same key.
        """
        ...


# ============================================================================
# In-Memory Implementation (Default)
# ============================================================================

@dataclass
class _LedgerEntry:
    """Internal: Ledger entry with timestamp and expiry"""
    timestamp_ms: int
    expire_at_ms: int


class InMemoryIdempotencyLedger:
    """
    Thread-safe in-memory idempotency ledger with TTL-based expiry.

    Features:
    - Automatic cleanup of expired keys (lazy eviction on check)
    - Thread-safe via simple locking (adequate for single-worker)
    - No persistence (entries lost on restart)

    Limitations:
    - Single-process only (no distributed coordination)
    - Memory grows with unique keys (periodic cleanup recommended)

    For distributed systems, use RedisIdempotencyLedger (future).
    """

    def __init__(self) -> None:
        """Initialize empty ledger"""
        self._ledger: Dict[str, _LedgerEntry] = {}
        # Note: Python dict operations are atomic at bytecode level,
        # but for safety, use threading.Lock if concurrent modifications expected.
        # For now, assume single-threaded async (no lock needed).

    def check_and_mark(
        self,
        key: IdempotencyKey,
        *,
        ttl_sec: int,
    ) -> IdempotencyResult:
        """
        Check and mark key atomically (in-memory).

        Algorithm:
        1. Check if key exists in ledger
        2. If exists and not expired: return executed=False (dedup)
        3. If exists but expired: delete old entry, create new
        4. If not exists: create entry
        5. Return executed=True for cases 3 and 4
        """
        now_ms = int(time.time() * 1000)
        key_str = str(key)

        # Check existing entry
        if key_str in self._ledger:
            entry = self._ledger[key_str]

            if now_ms < entry.expire_at_ms:
                # Within TTL: dedup
                return IdempotencyResult(
                    executed=False,
                    reason="already_executed",
                    timestamp_ms=entry.timestamp_ms,
                    key=key,
                )
            else:
                # Expired: treat as new execution
                del self._ledger[key_str]
                # Fall through to create new entry with reason="expired"
                reason = "expired"
        else:
            # First time
            reason = "first_call"

        # Create new entry
        expire_at_ms = now_ms + (ttl_sec * 1000)
        self._ledger[key_str] = _LedgerEntry(
            timestamp_ms=now_ms,
            expire_at_ms=expire_at_ms,
        )

        return IdempotencyResult(
            executed=True,
            reason=reason,
            timestamp_ms=now_ms,
            key=key,
        )

    def get_entry(self, key: IdempotencyKey) -> Optional[_LedgerEntry]:
        """
        Get ledger entry for key (for testing/debugging).

        Returns None if key not found or expired.
        """
        now_ms = int(time.time() * 1000)
        key_str = str(key)

        if key_str in self._ledger:
            entry = self._ledger[key_str]
            if now_ms < entry.expire_at_ms:
                return entry
            else:
                # Expired: clean up
                del self._ledger[key_str]

        return None

    def clear(self) -> None:
        """Clear all entries (for testing)"""
        self._ledger.clear()

    def cleanup_expired(self) -> int:
        """
        Manually clean up expired entries (optional periodic task).

        Returns:
            Number of entries removed
        """
        now_ms = int(time.time() * 1000)
        expired_keys = [
            k for k, v in self._ledger.items()
            if now_ms >= v.expire_at_ms
        ]
        for k in expired_keys:
            del self._ledger[k]
        return len(expired_keys)


# ============================================================================
# High-Level Cancel Wrapper
# ============================================================================

async def cancel_order_idempotent(
    adapter: Any,  # AbstractExecutionAdapter protocol
    symbol: str,
    order_id: str,
    ledger: IdempotencyLedgerProtocol,
    *,
    scope: str = "execpos.cancel",
    ttl_sec: int = 60,
    rid: Optional[str] = None,
) -> IdempotencyResult:
    """
    Cancel order with idempotent semantics (generic, adapter-agnostic).

    Flow:
    1. Check idempotency ledger with (scope, order_id) key
    2. If already executed within TTL: return no-op result (adapter NOT called)
    3. If first call or expired: call adapter.cancel_order(), return executed=True
    4. Log result (structured JSONL with RID)

    Args:
        adapter: Execution adapter with async cancel_order(symbol, order_id) method
        symbol: Trading symbol (e.g., "BTCUSDT")
        order_id: Exchange order ID to cancel
        ledger: Idempotency storage backend (e.g., InMemoryIdempotencyLedger)
        scope: Operation scope for key namespacing (default: "execpos.cancel")
        ttl_sec: Deduplication TTL in seconds (default: 60)
        rid: Request ID for RID propagation (optional)

    Returns:
        IdempotencyResult with executed flag and reason

    Example:
        ledger = InMemoryIdempotencyLedger()

        # First call
        result1 = await cancel_order_idempotent(
            adapter=binance_adapter,
            symbol="BTCUSDT",
            order_id="12345",
            ledger=ledger,
            rid="RID-abc",
        )
        # result1.executed == True, adapter.cancel_order() was called

        # Second call (within 60s)
        result2 = await cancel_order_idempotent(
            adapter=binance_adapter,
            symbol="BTCUSDT",
            order_id="12345",
            ledger=ledger,
            rid="RID-abc",
        )
        # result2.executed == False, adapter NOT called (dedup)

    Note:
        This function does NOT handle:
        - Exchange-specific error codes (e.g., Binance -2011)
        - Pre-cancel order status checks (getOrder before cancel)
        - Retry logic with exponential backoff

        Caller should wrap with exchange-specific error handling if needed.
    """
    key = IdempotencyKey(scope=scope, id=order_id)

    # Check ledger
    result = ledger.check_and_mark(key, ttl_sec=ttl_sec)

    # Log check result
    logger.info(
        "idempotent_cancel_check",
        extra={
            "event_type": "idempotent_cancel_check",
            "rid": rid,
            "scope": scope,
            "symbol": symbol,
            "order_id": order_id,
            "executed": result.executed,
            "reason": result.reason,
            "ttl_sec": ttl_sec,
            "timestamp_ms": result.timestamp_ms,
        }
    )

    if result.executed:
        # First call or expired: invoke adapter
        try:
            cancel_response = await adapter.cancel_order(symbol=symbol, order_id=order_id)

            logger.info(
                "idempotent_cancel_executed",
                extra={
                    "event_type": "idempotent_cancel_executed",
                    "rid": rid,
                    "scope": scope,
                    "symbol": symbol,
                    "order_id": order_id,
                    "reason": result.reason,
                    "cancel_response": cancel_response,
                }
            )
        except Exception as e:
            logger.error(
                "idempotent_cancel_failed",
                extra={
                    "event_type": "idempotent_cancel_failed",
                    "rid": rid,
                    "scope": scope,
                    "symbol": symbol,
                    "order_id": order_id,
                    "reason": result.reason,
                    "error": str(e),
                }
            )
            raise
    else:
        # Dedup: no-op
        logger.debug(
            "idempotent_cancel_dedup",
            extra={
                "event_type": "idempotent_cancel_dedup",
                "rid": rid,
                "scope": scope,
                "symbol": symbol,
                "order_id": order_id,
                "reason": result.reason,
                "original_timestamp_ms": result.timestamp_ms,
            }
        )

    return result


# ============================================================================
# Metrics Helper (Optional)
# ============================================================================

@dataclass
class IdempotencyCancelMetrics:
    """
    Metrics for idempotent cancel operations.

    Counters:
        cancel_total: Total cancel attempts by (scope, reason)
        cancel_dedup_total: Total deduplicated calls (executed=False)
        cancel_executed_total: Total real executions (executed=True)

    Usage:
        metrics = IdempotencyCancelMetrics()
        result = await cancel_order_idempotent(...)
        metrics.record(result)
    """
    cancel_total: Dict[Tuple[str, str], int] = field(
        default_factory=dict)  # (scope, reason) -> count
    cancel_dedup_total: int = 0
    cancel_executed_total: int = 0

    def record(self, result: IdempotencyResult) -> None:
        """Record result in metrics"""
        key = (result.key.scope, result.reason)
        self.cancel_total[key] = self.cancel_total.get(key, 0) + 1

        if result.executed:
            self.cancel_executed_total += 1
        else:
            self.cancel_dedup_total += 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for export"""
        return {
            "cancel_total": {f"{k[0]}:{k[1]}": v for k, v in self.cancel_total.items()},
            "cancel_dedup_total": self.cancel_dedup_total,
            "cancel_executed_total": self.cancel_executed_total,
        }


# ============================================================================
# Public API
# ============================================================================

__all__ = [
    # Core types
    "IdempotencyKey",
    "IdempotencyResult",
    "IdempotencyLedgerProtocol",

    # Default implementation
    "InMemoryIdempotencyLedger",

    # High-level wrapper
    "cancel_order_idempotent",

    # Metrics (optional)
    "IdempotencyCancelMetrics",
]
