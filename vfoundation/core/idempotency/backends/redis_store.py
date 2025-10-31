"""
Redis-based distributed idempotency store implementation.

Provides exactly-once semantics via atomic Lua scripts.
SLO: p95 ≤ 10ms for local Redis operations.
"""

from __future__ import annotations

import json
import random
import time
from typing import Any, Callable, Dict, List, Optional, TypeVar, cast

try:
    import redis
    from redis import Redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    Redis = None  # type: ignore[misc, assignment]

from .redis_protocol import RedisClientProtocol, RecordTD

from ..errors import (
    BusyError,
    CBOpenError,
    ConflictError,
    MissingError,
    StoreError,
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

T = TypeVar("T")


# Lua script for atomic reserve operation
RESERVE_SCRIPT = """
local key = KEYS[1]
local owner = ARGV[1]
local payload_digest = ARGV[2]
local ttl_ms = tonumber(ARGV[3])
local ts_ns = ARGV[4]

local exists = redis.call('EXISTS', key)

if exists == 0 then
    -- NEW: create record
    local record = {
        owner = owner,
        payload_digest = payload_digest,
        status = "HELD",
        ts_ns = ts_ns,
        lease_ms = ttl_ms
    }
    redis.call('SET', key, cjson.encode(record))
    redis.call('PEXPIRE', key, ttl_ms)
    return {"NEW", ttl_ms}
end

-- Record exists - check for conflicts
local raw = redis.call('GET', key)
local record = cjson.decode(raw)

if record.owner ~= owner then
    -- EXTERN_OWNER
    return {"EXTERN_OWNER", record.owner}
end

if record.payload_digest == payload_digest then
    -- DUPLICATE_SAME (idempotent no-op)
    return {"DUPLICATE_SAME", record.lease_ms or ttl_ms}
end

-- DUPLICATE_CONFLICT (different payload)
return {"DUPLICATE_CONFLICT", record.payload_digest}
"""

# Lua script for atomic confirm operation
CONFIRM_SCRIPT = """
local key = KEYS[1]
local final_status = ARGV[1]
local meta = ARGV[2]
local ts_ns = ARGV[3]

local exists = redis.call('EXISTS', key)
if exists == 0 then
    return {"MISSING"}
end

local raw = redis.call('GET', key)
local record = cjson.decode(raw)

-- Update status and meta
record.status = "CONFIRMED"
record.final_status = final_status
record.confirm_ts_ns = ts_ns

if meta ~= "" then
    record.meta = cjson.decode(meta)
end

redis.call('SET', key, cjson.encode(record))
return {"CONFIRMED"}
"""

# Lua script for atomic release operation
RELEASE_SCRIPT = """
local key = KEYS[1]
local owner = ARGV[1]

local exists = redis.call('EXISTS', key)
if exists == 0 then
    return {"MISSING"}
end

local raw = redis.call('GET', key)
local record = cjson.decode(raw)

-- Only owner can release
if record.owner ~= owner then
    return {"ERROR", "owner mismatch"}
end

redis.call('DEL', key)
return {"RELEASED"}
"""


class RedisIdempotencyStore(DistributedIdempotencyStore):
    """
    Redis-based distributed idempotency store.

    Uses Lua scripts for atomic operations.
    Key format: idemp:{key}
    """

    def __init__(
        self,
        redis_url: str,
        worker_id: str,
        ttl_ms: int = 60_000,
        timeout_ms: int = 100,
        retry_max_attempts: int = 3,
        retry_base_ms: int = 50,
        retry_max_ms: int = 1000,
        cb_threshold: float = 0.6,
        cb_cooldown_ms: int = 3000,
        cb_half_open_probes: int = 2,
    ) -> None:
        """
        Initialize Redis idempotency store.

        Args:
            redis_url: Redis connection URL
            worker_id: Unique worker identifier
            ttl_ms: Default TTL for idempotency records
            timeout_ms: I/O timeout for Redis operations
            retry_max_attempts: Max retry attempts
            retry_base_ms: Base retry delay
            retry_max_ms: Max retry delay
            cb_threshold: CB error rate threshold
            cb_cooldown_ms: CB cooldown period
            cb_half_open_probes: CB half-open probes
        """
        if not REDIS_AVAILABLE:
            raise ImportError("redis package not installed. Install with: pip install redis")

        super().__init__()

        self.worker_id = worker_id
        self.ttl_ms = ttl_ms
        self.timeout_ms = timeout_ms

        # Retry config
        self.retry_max_attempts = retry_max_attempts
        self.retry_base_ms = retry_base_ms
        self.retry_max_ms = retry_max_ms

        # CB config
        self.cb_threshold = cb_threshold
        self.cb_cooldown_ms = cb_cooldown_ms
        self.cb_half_open_probes = cb_half_open_probes

        # CB state
        self._cb_state = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
        self._cb_error_count = 0
        self._cb_total_count = 0
        self._cb_open_until_ns = 0
        self._cb_half_open_successes = 0

        # Connect to Redis
        if not REDIS_AVAILABLE or redis is None:
            raise ImportError("redis package required for RedisIdempotencyStore")

        try:
            redis_client: Any = redis.from_url(  # type: ignore[no-untyped-call]
                redis_url,
                socket_timeout=timeout_ms / 1000.0,
                socket_connect_timeout=timeout_ms / 1000.0,
                decode_responses=True,
            )
            self.client: RedisClientProtocol = cast(RedisClientProtocol, redis_client)
            # Test connection
            self.client.ping()
        except Exception as e:
            raise StoreError("connect", str(e))

        # Load Lua scripts
        try:
            reserve_sha = self.client.script_load(RESERVE_SCRIPT)
            confirm_sha = self.client.script_load(CONFIRM_SCRIPT)
            release_sha = self.client.script_load(RELEASE_SCRIPT)
            self._reserve_sha: Optional[str] = reserve_sha
            self._confirm_sha: Optional[str] = confirm_sha
            self._release_sha: Optional[str] = release_sha
            self._use_sha = True  # Use evalsha for real Redis
        except Exception:
            # Fallback for fakeredis (doesn't support SCRIPT LOAD)
            self._use_sha = False
            self._reserve_sha = None
            self._confirm_sha = None
            self._release_sha = None

    def _make_key(self, key: str) -> str:
        """Make Redis key with idemp: prefix."""
        return f"idemp:{key}"

    def _check_cb(self, operation: str) -> None:
        """Check circuit breaker state before operation."""
        now_ns = time.time_ns()

        if self._cb_state == "OPEN":
            # Check if cooldown expired
            if now_ns >= self._cb_open_until_ns:
                self._cb_state = "HALF_OPEN"
                self._cb_half_open_successes = 0
            else:
                self.metrics.idemp_cb_open_total += 1
                raise CBOpenError(operation)

        # CLOSED or HALF_OPEN: allow operation

    def _record_cb_result(self, success: bool) -> None:
        """Record operation result for CB."""
        self._cb_total_count += 1

        if not success:
            self._cb_error_count += 1

        # Calculate error rate (rolling window of last 100)
        if self._cb_total_count >= 100:
            error_rate = self._cb_error_count / self._cb_total_count

            if self._cb_state == "CLOSED":
                if error_rate >= self.cb_threshold:
                    # Open CB
                    self._cb_state = "OPEN"
                    self._cb_open_until_ns = time.time_ns() + (self.cb_cooldown_ms * 1_000_000)
            elif self._cb_state == "HALF_OPEN":
                if success:
                    self._cb_half_open_successes += 1
                    if self._cb_half_open_successes >= self.cb_half_open_probes:
                        # Close CB
                        self._cb_state = "CLOSED"
                        self._cb_error_count = 0
                        self._cb_total_count = 0
                else:
                    # Re-open CB
                    self._cb_state = "OPEN"
                    self._cb_open_until_ns = time.time_ns() + (self.cb_cooldown_ms * 1_000_000)

            # Reset counters after window
            if self._cb_total_count >= 200:
                self._cb_error_count = 0
                self._cb_total_count = 0

    def _retry_operation(
        self,
        operation: str,
        func: Callable[[], T],
    ) -> T:
        """Retry operation with exponential backoff."""
        attempt = 0
        last_error: Optional[Exception] = None

        while attempt < self.retry_max_attempts:
            try:
                self._check_cb(operation)
                result = func()
                self._record_cb_result(success=True)
                return result

            except (CBOpenError, BusyError, ConflictError, MissingError):
                # Don't retry these
                raise

            except Exception as e:
                last_error = e
                attempt += 1
                self.metrics.idemp_retries_total += 1
                self._record_cb_result(success=False)

                if attempt >= self.retry_max_attempts:
                    break

                # Exponential backoff with jitter
                delay_ms = min(self.retry_base_ms * (2 ** (attempt - 1)), self.retry_max_ms)
                # Add 20% jitter
                jitter = delay_ms * 0.2 * random.random()
                time.sleep((delay_ms + jitter) / 1000.0)

        # All retries failed
        self._record_cb_result(success=False)
        raise StoreError(operation, str(last_error))

    def reserve(self, key: str, payload_digest: str, ttl_ms: int, owner: str) -> ReserveResult:
        """Reserve idempotency key atomically (Lua script)."""
        redis_key = self._make_key(key)

        def _do_reserve() -> ReserveResult:
            start_ns = time.time_ns()

            try:
                if self._use_sha and self._reserve_sha:
                    result = self.client.evalsha(
                        self._reserve_sha,
                        1,
                        redis_key,
                        owner,
                        payload_digest,
                        str(ttl_ms),
                        str(time.time_ns()),
                    )
                else:
                    # Fallback: eval inline
                    result = self.client.eval(
                        RESERVE_SCRIPT,
                        1,
                        redis_key,
                        owner,
                        payload_digest,
                        str(ttl_ms),
                        str(time.time_ns()),
                    )

                result_list = cast(List[str], result)
                status_str = result_list[0]

                # Record latency
                elapsed_ns = time.time_ns() - start_ns
                self.metrics.record_reserve_latency(elapsed_ns / 1_000_000)

                if status_str == "NEW":
                    lease_ms = int(result_list[1])
                    res = ReserveResult(status=ReserveStatus.NEW, lease_ms=lease_ms)
                    self.metrics.idemp_reserve_total["NEW"] = (
                        self.metrics.idemp_reserve_total.get("NEW", 0) + 1
                    )
                    return res

                elif status_str == "DUPLICATE_SAME":
                    lease_ms = int(result_list[1])
                    res = ReserveResult(status=ReserveStatus.DUPLICATE_SAME, lease_ms=lease_ms)
                    self.metrics.idemp_reserve_total["DUPLICATE_SAME"] = (
                        self.metrics.idemp_reserve_total.get("DUPLICATE_SAME", 0) + 1
                    )
                    return res

                elif status_str == "DUPLICATE_CONFLICT":
                    self.metrics.idemp_conflict_total += 1
                    self.metrics.idemp_reserve_total["DUPLICATE_CONFLICT"] = (
                        self.metrics.idemp_reserve_total.get("DUPLICATE_CONFLICT", 0) + 1
                    )
                    actual_digest = result_list[1]
                    raise ConflictError(key, payload_digest, actual_digest)

                elif status_str == "EXTERN_OWNER":
                    self.metrics.idemp_busy_total += 1
                    self.metrics.idemp_reserve_total["EXTERN_OWNER"] = (
                        self.metrics.idemp_reserve_total.get("EXTERN_OWNER", 0) + 1
                    )
                    extern_owner = result_list[1]
                    raise BusyError(key, extern_owner)

                else:
                    raise StoreError("reserve", f"unknown status: {status_str}")

            except redis.RedisError as e:
                raise StoreError("reserve", str(e))

        return self._retry_operation("reserve", _do_reserve)

    def confirm(
        self, key: str, final_status: str, meta: Optional[Dict[str, Any]] = None
    ) -> ConfirmResult:
        """Confirm idempotency record atomically (Lua script)."""
        redis_key = self._make_key(key)

        def _do_confirm() -> ConfirmResult:
            start_ns = time.time_ns()

            try:
                meta_json = json.dumps(meta) if meta else ""

                if self._use_sha and self._confirm_sha:
                    result = self.client.evalsha(
                        self._confirm_sha,
                        1,
                        redis_key,
                        final_status,
                        meta_json,
                        str(time.time_ns()),
                    )
                else:
                    result = self.client.eval(
                        CONFIRM_SCRIPT,
                        1,
                        redis_key,
                        final_status,
                        meta_json,
                        str(time.time_ns()),
                    )

                result_list = cast(List[str], result)
                status_str = result_list[0]

                # Record latency
                elapsed_ns = time.time_ns() - start_ns
                self.metrics.record_confirm_latency(elapsed_ns / 1_000_000)

                if status_str == "CONFIRMED":
                    res = ConfirmResult(status=ConfirmStatus.CONFIRMED)
                    self.metrics.idemp_confirm_total["CONFIRMED"] = (
                        self.metrics.idemp_confirm_total.get("CONFIRMED", 0) + 1
                    )
                    return res

                elif status_str == "MISSING":
                    self.metrics.idemp_confirm_total["MISSING"] = (
                        self.metrics.idemp_confirm_total.get("MISSING", 0) + 1
                    )
                    raise MissingError(key, "confirm")

                else:
                    raise StoreError("confirm", f"unknown status: {status_str}")

            except redis.RedisError as e:
                raise StoreError("confirm", str(e))

        return self._retry_operation("confirm", _do_confirm)

    def get_status(self, key: str) -> StatusResult:
        """Get current status of idempotency record."""
        redis_key = self._make_key(key)

        def _do_get_status() -> StatusResult:
            try:
                exists = self.client.exists(redis_key)
                if not exists:
                    return StatusResult(status=GetStatus.EMPTY)

                raw = self.client.get(redis_key)
                if not raw:
                    return StatusResult(status=GetStatus.EMPTY)

                raw_str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                record: RecordTD = json.loads(raw_str)

                if record.get("status") == "CONFIRMED":
                    meta_raw = record.get("meta")
                    meta: Optional[Dict[str, Any]] = None
                    if meta_raw and isinstance(meta_raw, dict):
                        meta = meta_raw
                    return StatusResult(
                        status=GetStatus.CONFIRMED,
                        owner=record.get("owner"),
                        payload_digest=record.get("payload_digest"),
                        ts_ns=int(record.get("ts_ns", 0)),
                        meta=meta,
                    )
                else:
                    return StatusResult(
                        status=GetStatus.HELD,
                        owner=record.get("owner"),
                        payload_digest=record.get("payload_digest"),
                        ts_ns=int(record.get("ts_ns", 0)),
                    )

            except redis.RedisError as e:
                raise StoreError("get_status", str(e))

        return self._retry_operation("get_status", _do_get_status)

    def release(self, key: str, owner: str) -> ReleaseResult:
        """Release idempotency key atomically (Lua script)."""
        redis_key = self._make_key(key)

        def _do_release() -> ReleaseResult:
            try:
                if self._use_sha and self._release_sha:
                    result = self.client.evalsha(
                        self._release_sha,
                        1,
                        redis_key,
                        owner,
                    )
                else:
                    result = self.client.eval(
                        RELEASE_SCRIPT,
                        1,
                        redis_key,
                        owner,
                    )

                result_list = cast(List[str], result)
                status_str = result_list[0]

                if status_str == "RELEASED":
                    res = ReleaseResult(status=ReleaseStatus.RELEASED)
                    self.metrics.idemp_release_total["RELEASED"] = (
                        self.metrics.idemp_release_total.get("RELEASED", 0) + 1
                    )
                    return res

                elif status_str == "MISSING":
                    self.metrics.idemp_release_total["MISSING"] = (
                        self.metrics.idemp_release_total.get("MISSING", 0) + 1
                    )
                    raise MissingError(key, "release")

                elif status_str == "ERROR":
                    error_msg = result_list[1] if len(result_list) > 1 else "unknown"
                    raise StoreError("release", error_msg)

                else:
                    raise StoreError("release", f"unknown status: {status_str}")

            except redis.RedisError as e:
                raise StoreError("release", str(e))

        return self._retry_operation("release", _do_release)
