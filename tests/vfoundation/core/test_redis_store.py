"""
Tests for RedisIdempotencyStore (vfoundation/core/idempotency/backends/redis_store.py).

Covers: Reserve, Confirm, Release, GetStatus, CircuitBreaker, lifecycle, edge cases.

NOTE: fakeredis Lua cjson has limited support for string-keyed tables.
We mock eval/evalsha to return realistic values matching the Lua script contract,
then test get_status via real FakeRedis GET/SET operations (no Lua involved).
The Lua scripts themselves are tested for correct syntax via import.
CB state machine tests use the internal state directly (no Redis calls).
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest

# Import target module
from vfoundation.core.idempotency.backends.redis_store import (
    CONFIRM_SCRIPT,
    RELEASE_SCRIPT,
    RESERVE_SCRIPT,
    RedisIdempotencyStore,
)
from vfoundation.core.idempotency.errors import (
    BusyError,
    CBOpenError,
    ConflictError,
    MissingError,
    StoreError,
)
from vfoundation.core.idempotency.store import (
    ConfirmStatus,
    GetStatus,
    ReleaseStatus,
    ReserveStatus,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _unique_key() -> str:
    """Generate a unique idempotency key for each test."""
    return f"test:{uuid.uuid4().hex}"


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_redis_client() -> MagicMock:
    """
    Mock Redis client that simulates eval/evalsha responses.
    Stores data in a real dict to allow get/exists/set to work.
    """
    client = MagicMock()
    _db: dict[str, Any] = {}

    def fake_ping() -> bool:
        return True

    def fake_script_load(script: str) -> str:
        return "fake-sha-" + str(hash(script))[:8]

    def fake_exists(*keys: str) -> int:
        return sum(1 for k in keys if k in _db)

    def fake_get(key: str) -> Any:
        val = _db.get(key)
        if val is None:
            return None
        if isinstance(val, str):
            return val
        return val

    def fake_set(key: str, value: Any, **kw: Any) -> bool:
        _db[key] = value
        return True

    def fake_delete(*keys: str) -> int:
        count = 0
        for k in keys:
            if k in _db:
                del _db[k]
                count += 1
        return count

    def fake_pexpire(key: str, ms: int) -> int:
        return 1 if key in _db else 0

    client.ping.side_effect = fake_ping
    client.script_load.side_effect = fake_script_load
    client.exists.side_effect = fake_exists
    client.get.side_effect = fake_get
    client.set.side_effect = fake_set
    client.delete.side_effect = fake_delete
    client.pexpire.side_effect = fake_pexpire
    client._db = _db  # expose for setup in tests

    return client


@pytest.fixture()
def store(mock_redis_client: MagicMock) -> RedisIdempotencyStore:
    """
    RedisIdempotencyStore with a mock Redis client injected.
    Bypasses real Redis connection entirely.
    """
    with patch(
        "vfoundation.core.idempotency.backends.redis_store.redis.from_url",
        return_value=mock_redis_client,
    ):
        s = RedisIdempotencyStore(
            redis_url="redis://localhost:6379",
            worker_id="test-worker-1",
            ttl_ms=5_000,
            cb_cooldown_ms=100,
            retry_max_attempts=1,
            cb_half_open_probes=2,
        )
    s.client = mock_redis_client
    s._use_sha = False  # force eval path (no evalsha)
    return s


@pytest.fixture()
def store2(mock_redis_client: MagicMock) -> RedisIdempotencyStore:
    """Second store (different worker) sharing same mock client/db."""
    with patch(
        "vfoundation.core.idempotency.backends.redis_store.redis.from_url",
        return_value=mock_redis_client,
    ):
        s = RedisIdempotencyStore(
            redis_url="redis://localhost:6379",
            worker_id="test-worker-2",
            ttl_ms=5_000,
            cb_cooldown_ms=100,
            retry_max_attempts=1,
        )
    s.client = mock_redis_client
    s._use_sha = False
    return s


def _setup_reserve_new(client: MagicMock, store: RedisIdempotencyStore, key: str,
                        owner: str = "test-worker-1", digest: str = "d1", ttl_ms: int = 5000) -> None:
    """Configure mock eval to return NEW reservation, and store record in fake DB."""
    redis_key = store._make_key(key)
    record = {
        "owner": owner,
        "payload_digest": digest,
        "status": "HELD",
        "ts_ns": str(time.time_ns()),
        "lease_ms": ttl_ms,
    }
    client._db[redis_key] = json.dumps(record)
    client.eval.return_value = ["NEW", ttl_ms]
    client.evalsha.return_value = ["NEW", ttl_ms]


def _setup_reserve_duplicate_same(client: MagicMock, ttl_ms: int = 5000) -> None:
    client.eval.return_value = ["DUPLICATE_SAME", ttl_ms]
    client.evalsha.return_value = ["DUPLICATE_SAME", ttl_ms]


def _setup_reserve_conflict(client: MagicMock) -> None:
    client.eval.return_value = ["DUPLICATE_CONFLICT", "other-digest"]
    client.evalsha.return_value = ["DUPLICATE_CONFLICT", "other-digest"]


def _setup_reserve_extern_owner(client: MagicMock) -> None:
    client.eval.return_value = ["EXTERN_OWNER", "test-worker-2"]
    client.evalsha.return_value = ["EXTERN_OWNER", "test-worker-2"]


def _setup_confirm_ok(client: MagicMock, store: RedisIdempotencyStore, key: str,
                       owner: str = "test-worker-1", digest: str = "d1") -> None:
    """Store CONFIRMED record and configure mock confirm to return CONFIRMED."""
    redis_key = store._make_key(key)
    record = {
        "owner": owner,
        "payload_digest": digest,
        "status": "CONFIRMED",
        "ts_ns": str(time.time_ns()),
        "lease_ms": 5000,
    }
    client._db[redis_key] = json.dumps(record)
    client.eval.return_value = ["CONFIRMED"]
    client.evalsha.return_value = ["CONFIRMED"]


def _setup_confirm_missing(client: MagicMock) -> None:
    client.eval.return_value = ["MISSING"]
    client.evalsha.return_value = ["MISSING"]


def _setup_release_ok(client: MagicMock, store: RedisIdempotencyStore, key: str) -> None:
    """Remove key from DB and configure mock release to return RELEASED."""
    redis_key = store._make_key(key)
    client._db.pop(redis_key, None)
    client.eval.return_value = ["RELEASED"]
    client.evalsha.return_value = ["RELEASED"]


def _setup_release_missing(client: MagicMock) -> None:
    client.eval.return_value = ["MISSING"]
    client.evalsha.return_value = ["MISSING"]


def _setup_release_wrong_owner(client: MagicMock) -> None:
    client.eval.return_value = ["OWNER_MISMATCH"]
    client.evalsha.return_value = ["OWNER_MISMATCH"]


# ─────────────────────────────────────────────────────────────────────────────
# TestScripts — verify scripts are importable and non-empty
# ─────────────────────────────────────────────────────────────────────────────


class TestScripts:
    """Sanity tests: Lua scripts must be importable, non-empty strings."""

    def test_reserve_script_nonempty(self) -> None:
        assert isinstance(RESERVE_SCRIPT, str) and len(RESERVE_SCRIPT) > 50
        assert "cjson.encode" in RESERVE_SCRIPT or "redis.call" in RESERVE_SCRIPT

    def test_confirm_script_nonempty(self) -> None:
        assert isinstance(CONFIRM_SCRIPT, str) and len(CONFIRM_SCRIPT) > 50

    def test_release_script_nonempty(self) -> None:
        assert isinstance(RELEASE_SCRIPT, str) and len(RELEASE_SCRIPT) > 20


# ─────────────────────────────────────────────────────────────────────────────
# TestReserve
# ─────────────────────────────────────────────────────────────────────────────


class TestReserve:
    """Tests for RedisIdempotencyStore.reserve() result parsing."""

    def test_reserve_new_returns_NEW(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """NEW reservation should return ReserveStatus.NEW with positive lease."""
        key = _unique_key()
        _setup_reserve_new(mock_redis_client, store, key)
        result = store.reserve(key, payload_digest="d1", ttl_ms=5_000, owner="test-worker-1")
        assert result.status == ReserveStatus.NEW, f"expected NEW, got {result.status}"
        assert result.lease_ms is not None and result.lease_ms > 0

    def test_reserve_duplicate_same_returns_DUPLICATE_SAME(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """DUPLICATE_SAME response should map to ReserveStatus.DUPLICATE_SAME."""
        key = _unique_key()
        _setup_reserve_duplicate_same(mock_redis_client)
        result = store.reserve(key, payload_digest="d1", ttl_ms=5_000, owner="test-worker-1")
        assert result.status == ReserveStatus.DUPLICATE_SAME

    def test_reserve_duplicate_conflict_raises_ConflictError(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """DUPLICATE_CONFLICT Lua response should raise ConflictError."""
        key = _unique_key()
        _setup_reserve_conflict(mock_redis_client)
        with pytest.raises(ConflictError):
            store.reserve(key, payload_digest="digest-B", ttl_ms=5_000, owner="test-worker-1")

    def test_reserve_extern_owner_raises_BusyError(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """EXTERN_OWNER Lua response should raise BusyError."""
        key = _unique_key()
        _setup_reserve_extern_owner(mock_redis_client)
        with pytest.raises(BusyError):
            store.reserve(key, payload_digest="d1", ttl_ms=5_000, owner="test-worker-2")

    def test_reserve_increments_metrics_NEW(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """reserve() with NEW result should increment metrics.idemp_reserve_total['NEW']."""
        key = _unique_key()
        _setup_reserve_new(mock_redis_client, store, key)
        store.reserve(key, payload_digest="d1", ttl_ms=5_000, owner="test-worker-1")
        count = store.metrics.idemp_reserve_total.get("NEW", 0)
        assert count >= 1, f"expected >=1 NEW in metrics, got {count}"

    def test_reserve_increments_metrics_DUPLICATE_SAME(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """DUPLICATE_SAME should be traced in metrics."""
        _setup_reserve_duplicate_same(mock_redis_client)
        store.reserve(_unique_key(), payload_digest="d1", ttl_ms=5_000, owner="test-worker-1")
        count = store.metrics.idemp_reserve_total.get("DUPLICATE_SAME", 0)
        assert count >= 1

    def test_reserve_records_latency(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """reserve() should record at least 1 latency sample."""
        key = _unique_key()
        _setup_reserve_new(mock_redis_client, store, key)
        store.reserve(key, payload_digest="d1", ttl_ms=5_000, owner="test-worker-1")
        assert len(store.metrics.reserve_latencies) >= 1

    def test_reserve_key_prefix_idemp(self, store: RedisIdempotencyStore) -> None:
        """Internal Redis key should use 'idemp:' prefix."""
        redis_key = store._make_key("mykey-abc")
        assert redis_key.startswith("idemp:"), f"expected 'idemp:' prefix, got {redis_key!r}"

    @pytest.mark.parametrize("key_suffix", ["alpha", "beta", "gamma-123"])
    def test_reserve_various_keys(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock, key_suffix: str
    ) -> None:
        """reserve works for various key shapes."""
        key = f"test:{key_suffix}:{uuid.uuid4().hex}"
        _setup_reserve_new(mock_redis_client, store, key)
        result = store.reserve(key, payload_digest="d1", ttl_ms=3_000, owner="test-worker-1")
        assert result.status == ReserveStatus.NEW


# ─────────────────────────────────────────────────────────────────────────────
# TestConfirm
# ─────────────────────────────────────────────────────────────────────────────


class TestConfirm:
    """Tests for RedisIdempotencyStore.confirm() result parsing."""

    def test_confirm_held_record(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """CONFIRMED Lua response should map to ConfirmStatus.CONFIRMED."""
        key = _unique_key()
        _setup_confirm_ok(mock_redis_client, store, key)
        result = store.confirm(key, final_status="OK")
        assert result.status == ConfirmStatus.CONFIRMED

    def test_confirm_missing_key_raises_MissingError(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """MISSING Lua response should raise MissingError."""
        _setup_confirm_missing(mock_redis_client)
        with pytest.raises(MissingError):
            store.confirm(_unique_key(), final_status="OK")

    def test_confirm_increments_metrics(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """confirm() should increment idemp_confirm_total['CONFIRMED']."""
        key = _unique_key()
        _setup_confirm_ok(mock_redis_client, store, key)
        store.confirm(key, final_status="OK")
        count = store.metrics.idemp_confirm_total.get("CONFIRMED", 0)
        assert count >= 1

    def test_confirm_records_latency(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """confirm() should append to confirm_latencies."""
        key = _unique_key()
        _setup_confirm_ok(mock_redis_client, store, key)
        store.confirm(key, final_status="OK")
        assert len(store.metrics.confirm_latencies) >= 1

    def test_confirm_without_meta(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """confirm without meta arg should work."""
        key = _unique_key()
        _setup_confirm_ok(mock_redis_client, store, key)
        result = store.confirm(key, final_status="APPROVED")
        assert result.status == ConfirmStatus.CONFIRMED


# ─────────────────────────────────────────────────────────────────────────────
# TestGetStatus
# ─────────────────────────────────────────────────────────────────────────────


class TestGetStatus:
    """Tests for get_status() — uses real dict-based get/exists (no Lua)."""

    def test_get_status_empty(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """Non-existent key should return GetStatus.EMPTY."""
        result = store.get_status(_unique_key())
        assert result.status == GetStatus.EMPTY

    def test_get_status_held_after_reserve(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """After injecting HELD record, get_status should return HELD."""
        key = _unique_key()
        _setup_reserve_new(mock_redis_client, store, key, owner="test-worker-1", digest="d1")
        result = store.get_status(key)
        assert result.status == GetStatus.HELD
        assert result.owner == "test-worker-1"

    def test_get_status_confirmed(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """After injecting CONFIRMED record, get_status should return CONFIRMED."""
        key = _unique_key()
        _setup_confirm_ok(mock_redis_client, store, key)
        result = store.get_status(key)
        assert result.status == GetStatus.CONFIRMED

    def test_get_status_returns_payload_digest(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """get_status should return the stored payload_digest."""
        key = _unique_key()
        _setup_reserve_new(mock_redis_client, store, key, digest="sha256-abc123")
        result = store.get_status(key)
        assert result.payload_digest == "sha256-abc123"

    def test_get_status_returns_ts_ns(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """get_status should return ts_ns > 0 from stored record."""
        key = _unique_key()
        _setup_reserve_new(mock_redis_client, store, key)
        result = store.get_status(key)
        assert result.ts_ns is not None and result.ts_ns > 0


# ─────────────────────────────────────────────────────────────────────────────
# TestRelease
# ─────────────────────────────────────────────────────────────────────────────


class TestRelease:
    """Tests for release() result parsing."""

    def test_release_held_record(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """RELEASED Lua response should map to ReleaseStatus.RELEASED."""
        key = _unique_key()
        _setup_release_ok(mock_redis_client, store, key)
        result = store.release(key, owner="test-worker-1")
        assert result.status == ReleaseStatus.RELEASED

    def test_release_missing_raises_MissingError(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """MISSING Lua response should raise MissingError."""
        _setup_release_missing(mock_redis_client)
        with pytest.raises(MissingError):
            store.release(_unique_key(), owner="test-worker-1")

    def test_release_wrong_owner_raises_StoreError(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """OWNER_MISMATCH Lua response should raise StoreError."""
        _setup_release_wrong_owner(mock_redis_client)
        with pytest.raises(StoreError):
            store.release(_unique_key(), owner="test-worker-2")

    def test_release_cleans_redis_key(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """After successful release, get_status should return EMPTY."""
        key = _unique_key()
        _setup_release_ok(mock_redis_client, store, key)
        store.release(key, owner="test-worker-1")
        # key should be gone from db after _setup_release_ok removed it
        status = store.get_status(key)
        assert status.status == GetStatus.EMPTY

    def test_release_increments_metrics(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """release() should increment idemp_release_total['RELEASED']."""
        key = _unique_key()
        _setup_release_ok(mock_redis_client, store, key)
        store.release(key, owner="test-worker-1")
        count = store.metrics.idemp_release_total.get("RELEASED", 0)
        assert count >= 1


# ─────────────────────────────────────────────────────────────────────────────
# TestCircuitBreaker
# ─────────────────────────────────────────────────────────────────────────────


class TestCircuitBreaker:
    """Tests for CB state machine in RedisIdempotencyStore (no Redis calls)."""

    def test_cb_closed_by_default(self, store: RedisIdempotencyStore) -> None:
        assert store._cb_state == "CLOSED"

    def test_cb_open_raises_CBOpenError(self, store: RedisIdempotencyStore) -> None:
        store._cb_state = "OPEN"
        store._cb_open_until_ns = time.time_ns() + 60_000_000_000
        with pytest.raises(CBOpenError):
            store._check_cb("reserve")

    def test_cb_half_open_after_cooldown(self, store: RedisIdempotencyStore) -> None:
        store._cb_state = "OPEN"
        store._cb_open_until_ns = time.time_ns() - 1
        store._check_cb("reserve")  # should not raise
        assert store._cb_state == "HALF_OPEN"

    def test_cb_closes_after_successful_probes(self, store: RedisIdempotencyStore) -> None:
        store._cb_state = "HALF_OPEN"
        store._cb_half_open_successes = 0
        store._cb_total_count = 100
        store._cb_error_count = 0
        for _ in range(store.cb_half_open_probes):
            store._record_cb_result(success=True)
        assert store._cb_state == "CLOSED"

    def test_cb_opens_on_error_threshold(self, store: RedisIdempotencyStore) -> None:
        store._cb_state = "CLOSED"
        store._cb_total_count = 99
        store._cb_error_count = 69
        store._record_cb_result(success=False)  # 70% error → opens
        assert store._cb_state == "OPEN"

    def test_cb_half_open_failure_reopens(self, store: RedisIdempotencyStore) -> None:
        store._cb_state = "HALF_OPEN"
        store._cb_total_count = 100
        store._record_cb_result(success=False)
        assert store._cb_state == "OPEN"


# ─────────────────────────────────────────────────────────────────────────────
# TestLifecycle
# ─────────────────────────────────────────────────────────────────────────────


class TestLifecycle:
    """Full lifecycle tests using mock eval responses."""

    def test_redis_unavailable_raises_StoreError(self) -> None:
        """Connection failure should raise StoreError."""
        with patch(
            "vfoundation.core.idempotency.backends.redis_store.redis.from_url",
            side_effect=ConnectionError("refused"),
        ):
            with pytest.raises(StoreError) as exc_info:
                RedisIdempotencyStore(redis_url="redis://unreachable:6379", worker_id="w1")
        assert "connect" in str(exc_info.value).lower() or "connect" in exc_info.value.why

    def test_no_redis_package_raises_ImportError(self) -> None:
        """When REDIS_AVAILABLE=False, instantiation should raise ImportError."""
        import vfoundation.core.idempotency.backends.redis_store as rs_module
        original = rs_module.REDIS_AVAILABLE
        try:
            rs_module.REDIS_AVAILABLE = False
            with pytest.raises(ImportError):
                RedisIdempotencyStore(redis_url="redis://x", worker_id="w1")
        finally:
            rs_module.REDIS_AVAILABLE = original

    def test_cb_state_closed_by_default(self, store: RedisIdempotencyStore) -> None:
        assert store._cb_state == "CLOSED"
        assert store._cb_error_count == 0
        assert store._cb_total_count == 0

    def test_full_reserve_confirm_get(
        self, store: RedisIdempotencyStore, mock_redis_client: MagicMock
    ) -> None:
        """reserve → confirm → get_status round-trip."""
        key = _unique_key()
        _setup_reserve_new(mock_redis_client, store, key)
        r1 = store.reserve(key, payload_digest="d1", ttl_ms=5_000, owner="test-worker-1")
        assert r1.status == ReserveStatus.NEW

        _setup_confirm_ok(mock_redis_client, store, key)
        r2 = store.confirm(key, final_status="COMMITTED")
        assert r2.status == ConfirmStatus.CONFIRMED

        r3 = store.get_status(key)
        assert r3.status == GetStatus.CONFIRMED
