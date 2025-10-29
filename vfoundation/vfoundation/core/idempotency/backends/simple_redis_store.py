"""
Simple Redis store without Lua scripts (для тестів з fakeredis).

Використовує базові команди Redis: SETNX, GET, SET, DEL, EXPIRE.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

try:
    import redis
    from redis import Redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    Redis = None  # type: ignore[misc, assignment]

from ..errors import (
    BusyError,
    ConflictError,
    MissingError,
)
from ..store import (
    ConfirmResult,
    ConfirmStatus,
    DistributedIdempotencyStore,
    GetStatus,
    ReleaseResult,
    ReleaseStatus,
    ReserveResult,
    ReserveStatus,
    StatusResult,
)


class SimpleRedisIdempotencyStore(DistributedIdempotencyStore):
    """
    Simple Redis store without Lua scripts (non-atomic, test-only).
    
    Uses basic Redis commands for compatibility with fakeredis.
    NOT production-ready (no atomic guarantees).
    """
    
    def __init__(
        self,
        redis_url: str,
        worker_id: str,
        ttl_ms: int = 60_000,
        timeout_ms: int = 100,
    ) -> None:
        """Initialize simple Redis store."""
        if not REDIS_AVAILABLE:
            raise ImportError("redis package not installed")
        
        super().__init__()
        
        self.worker_id = worker_id
        self.ttl_ms = ttl_ms
        self.timeout_ms = timeout_ms
        
        # Connect to Redis
        try:
            client_temp: Any = redis.from_url(  # type: ignore[no-untyped-call]
                redis_url,
                socket_timeout=timeout_ms / 1000.0,
                socket_connect_timeout=timeout_ms / 1000.0,
                decode_responses=True,
            )
            self.client: Any = client_temp
            self.client.ping()
        except Exception as e:
            from ..errors import StoreError
            raise StoreError("connect", str(e))
    
    def _make_key(self, key: str) -> str:
        """Make Redis key with idemp: prefix."""
        return f"idemp:{key}"
    
    def reserve(
        self,
        key: str,
        payload_digest: str,
        ttl_ms: int,
        owner: str
    ) -> ReserveResult:
        """Reserve idempotency key (non-atomic version)."""
        redis_key = self._make_key(key)
        start_ns = time.time_ns()
        
        try:
            # Check if key exists
            exists = self.client.exists(redis_key)
            
            if not exists:
                # NEW: create record
                record = {
                    "owner": owner,
                    "payload_digest": payload_digest,
                    "status": "HELD",
                    "ts_ns": time.time_ns(),
                    "lease_ms": ttl_ms
                }
                self.client.set(redis_key, json.dumps(record))
                self.client.pexpire(redis_key, ttl_ms)
                
                elapsed_ns = time.time_ns() - start_ns
                self.metrics.record_reserve_latency(elapsed_ns / 1_000_000)
                self.metrics.idemp_reserve_total["NEW"] = \
                    self.metrics.idemp_reserve_total.get("NEW", 0) + 1
                
                return ReserveResult(status=ReserveStatus.NEW, lease_ms=ttl_ms)
            
            # Record exists - check for conflicts
            raw = self.client.get(redis_key)
            if not raw or not isinstance(raw, str):
                # Race condition: key deleted between EXISTS and GET
                return self.reserve(key, payload_digest, ttl_ms, owner)
            
            record = json.loads(raw)
            
            elapsed_ns = time.time_ns() - start_ns
            self.metrics.record_reserve_latency(elapsed_ns / 1_000_000)
            
            if record.get("owner") != owner:
                # EXTERN_OWNER
                self.metrics.idemp_busy_total += 1
                self.metrics.idemp_reserve_total["EXTERN_OWNER"] = \
                    self.metrics.idemp_reserve_total.get("EXTERN_OWNER", 0) + 1
                raise BusyError(key, record.get("owner", "unknown"))
            
            if record.get("payload_digest") == payload_digest:
                # DUPLICATE_SAME (idempotent no-op)
                self.metrics.idemp_reserve_total["DUPLICATE_SAME"] = \
                    self.metrics.idemp_reserve_total.get("DUPLICATE_SAME", 0) + 1
                return ReserveResult(
                    status=ReserveStatus.DUPLICATE_SAME,
                    lease_ms=record.get("lease_ms", ttl_ms)
                )
            
            # DUPLICATE_CONFLICT (different payload)
            self.metrics.idemp_conflict_total += 1
            self.metrics.idemp_reserve_total["DUPLICATE_CONFLICT"] = \
                self.metrics.idemp_reserve_total.get("DUPLICATE_CONFLICT", 0) + 1
            raise ConflictError(key, payload_digest, record.get("payload_digest", "unknown"))
        
        except (BusyError, ConflictError):
            raise
        except Exception as e:
            from ..errors import StoreError
            raise StoreError("reserve", str(e))
    
    def confirm(
        self,
        key: str,
        final_status: str,
        meta: Optional[Dict[str, Any]] = None
    ) -> ConfirmResult:
        """Confirm idempotency record."""
        redis_key = self._make_key(key)
        start_ns = time.time_ns()
        
        try:
            exists = self.client.exists(redis_key)
            if not exists:
                self.metrics.idemp_confirm_total["MISSING"] = \
                    self.metrics.idemp_confirm_total.get("MISSING", 0) + 1
                raise MissingError(key, "confirm")
            
            raw = self.client.get(redis_key)
            if not raw or not isinstance(raw, str):
                raise MissingError(key, "confirm")
            
            record = json.loads(raw)
            record["status"] = "CONFIRMED"
            record["final_status"] = final_status
            record["confirm_ts_ns"] = time.time_ns()
            if meta:
                record["meta"] = meta
            
            self.client.set(redis_key, json.dumps(record))
            
            elapsed_ns = time.time_ns() - start_ns
            self.metrics.record_confirm_latency(elapsed_ns / 1_000_000)
            self.metrics.idemp_confirm_total["CONFIRMED"] = \
                self.metrics.idemp_confirm_total.get("CONFIRMED", 0) + 1
            
            return ConfirmResult(status=ConfirmStatus.CONFIRMED)
        
        except MissingError:
            raise
        except Exception as e:
            from ..errors import StoreError
            raise StoreError("confirm", str(e))
    
    def get_status(self, key: str) -> StatusResult:
        """Get current status of idempotency record."""
        redis_key = self._make_key(key)
        
        try:
            exists = self.client.exists(redis_key)
            if not exists:
                return StatusResult(status=GetStatus.EMPTY)
            
            raw = self.client.get(redis_key)
            if not raw or not isinstance(raw, str):
                return StatusResult(status=GetStatus.EMPTY)
            
            record = json.loads(raw)
            
            if record.get("status") == "CONFIRMED":
                return StatusResult(
                    status=GetStatus.CONFIRMED,
                    owner=record.get("owner"),
                    payload_digest=record.get("payload_digest"),
                    ts_ns=int(record.get("ts_ns", 0)),
                    meta=record.get("meta"),
                )
            else:
                return StatusResult(
                    status=GetStatus.HELD,
                    owner=record.get("owner"),
                    payload_digest=record.get("payload_digest"),
                    ts_ns=int(record.get("ts_ns", 0)),
                )
        
        except Exception as e:
            from ..errors import StoreError
            raise StoreError("get_status", str(e))
    
    def release(self, key: str, owner: str) -> ReleaseResult:
        """Release idempotency key."""
        redis_key = self._make_key(key)
        
        try:
            exists = self.client.exists(redis_key)
            if not exists:
                self.metrics.idemp_release_total["MISSING"] = \
                    self.metrics.idemp_release_total.get("MISSING", 0) + 1
                raise MissingError(key, "release")
            
            raw = self.client.get(redis_key)
            if not raw or not isinstance(raw, str):
                raise MissingError(key, "release")
            
            record = json.loads(raw)
            
            # Only owner can release
            if record.get("owner") != owner:
                from ..errors import StoreError
                raise StoreError("release", "owner mismatch")
            
            self.client.delete(redis_key)
            
            self.metrics.idemp_release_total["RELEASED"] = \
                self.metrics.idemp_release_total.get("RELEASED", 0) + 1
            
            return ReleaseResult(status=ReleaseStatus.RELEASED)
        
        except MissingError:
            raise
        except Exception as e:
            from ..errors import StoreError
            raise StoreError("release", str(e))
