"""Coverage tests for RedisIdempotencyStore using fakeredis."""
import pytest
import json
import fakeredis
from vfoundation.core.idempotency.backends.redis_store import RedisIdempotencyStore
from vfoundation.core.idempotency.errors import BusyError, ConflictError, MissingError, StoreError, CBOpenError
from vfoundation.core.idempotency.store import ReserveStatus, ConfirmStatus, GetStatus, ReleaseStatus


@pytest.fixture
def mock_redis(monkeypatch):
    """Patch redis.from_url to return a fakeredis instance."""
    fake_client = fakeredis.FakeRedis(decode_responses=True)
    def fake_from_url(*args, **kwargs):
        return fake_client
        
    def fake_eval(self_obj, script, numkeys, *args):
        # We need to accept self_obj since it's an instance method replacement
        key = args[0] if args else ""
        if "err_eval" in key:
            import redis
            raise redis.RedisError("evalsha_failed")

        if "RESERVE" in script or len(args) == 5:
            if "duplicate_same" in key:
                return ["DUPLICATE_SAME", "1000"]
            elif "conflict" in key:
                return ["DUPLICATE_CONFLICT", "some_other"]
            elif "busy" in key:
                return ["EXTERN_OWNER", "other_own"]
            elif "err2" in key:
                return ["UNKNOWN"]
            return ["NEW", "1000"]
        elif "CONFIRM" in script or len(args) == 4:
            if "c2" in key:
                return ["NOT_VALID"]
            if "nonexistent" in key:
                return ["MISSING"]
            return ["CONFIRMED"]
        else:
            if "r4" in key:
                return ["WHAT"]
            if "nonexistent" in key:
                return ["MISSING"]
            if "r2" in key:
                return ["ERROR", "owner mismatch"]
            return ["RELEASED"]
        
    def fake_evalsha(self_obj, sha, numkeys, *args):
        return fake_eval(self_obj, sha, numkeys, *args)
        
    monkeypatch.setattr("redis.from_url", fake_from_url)
    monkeypatch.setattr(fakeredis.FakeRedis, "eval", fake_eval)
    monkeypatch.setattr(fakeredis.FakeRedis, "evalsha", fake_evalsha)
    
    return fake_client

@pytest.fixture
def store(mock_redis):
    # This will use the patched from_url
    return RedisIdempotencyStore(
        redis_url="redis://localhost",
        worker_id="test_worker",
        retry_max_attempts=1,
        cb_threshold=0.0, # Disable CB for standard tests or we can test it specifically
    )


class TestRedisIdempotencyStore:
    def test_init_success(self, mock_redis, monkeypatch):
        # mock script_load so it succeeds
        def fake_script_load(script):
            return "mock_sha"
        monkeypatch.setattr(mock_redis, "script_load", fake_script_load)
        
        store = RedisIdempotencyStore(
            redis_url="redis://localhost",
            worker_id="test_worker"
        )
        assert store.worker_id == "test_worker"
        assert store.client is not None
        assert store._use_sha is True
        
        res = store.reserve("shatest", "dig", 1000, "own")
        assert res.status == ReserveStatus.NEW

    def test_init_fallback_lua(self, mock_redis, monkeypatch):
        # Make script_load raise to test script_load failure fallback
        def broken_script_load(script):
            raise Exception("not supported")
        monkeypatch.setattr(mock_redis, "script_load", broken_script_load)
        store_fallback = RedisIdempotencyStore(
            redis_url="redis://localhost",
            worker_id="test_worker"
        )
        assert store_fallback._use_sha is False
        
        # Test that reserve still works with _use_sha = False (invoking eval directly)
        res = store_fallback.reserve("keyfb", "digfb", 1000, "ownerfb")
        assert res.status == ReserveStatus.NEW
        
        res_conf = store_fallback.confirm("keyfb", "OK")
        assert res_conf.status == ConfirmStatus.CONFIRMED
        
        res_rel = store_fallback.release("keyfb", "ownerfb")
        assert res_rel.status == ReleaseStatus.RELEASED

    def test_init_connection_error(self, monkeypatch):
        def fake_from_url(*args, **kwargs):
            raise ConnectionError("redis down")
        monkeypatch.setattr("redis.from_url", fake_from_url)
        with pytest.raises(StoreError, match="connect"):
            RedisIdempotencyStore("redis://localhost", "w1")

    def test_reserve_new(self, store):
        res = store.reserve("key1", "digest1", 1000, "owner1")
        assert res.status == ReserveStatus.NEW
        assert res.lease_ms == 1000

    def test_reserve_duplicate_same(self, store):
        res = store.reserve("duplicate_same", "digest2", 1000, "owner2")
        assert res.status == ReserveStatus.DUPLICATE_SAME

    def test_reserve_busy_extern_owner(self, store):
        with pytest.raises(BusyError):
            store.reserve("busy", "digest3", 1000, "other_owner")

    def test_reserve_conflict_different_digest(self, store):
        with pytest.raises(ConflictError):
            store.reserve("conflict", "different", 1000, "owner4")

    def test_reserve_store_error(self, store):
        with pytest.raises(StoreError):
            store.reserve("err_eval", "dig", 1000, "own")
            
    def test_reserve_unknown_status(self, store):
        with pytest.raises(StoreError):
            store.reserve("res_err2", "dig", 1000, "own")

    def test_confirm_success(self, store):
        res = store.confirm("c1", "OK", {"meta": 1})
        assert res.status == ConfirmStatus.CONFIRMED

    def test_confirm_missing(self, store):
        with pytest.raises(MissingError):
            store.confirm("nonexistent", "OK")
            
    def test_confirm_store_error(self, store):
        with pytest.raises(StoreError):
            store.confirm("err_eval", "OK")

    def test_confirm_unknown_status(self, store):
        with pytest.raises(StoreError):
            store.confirm("conf_c2", "OK")

    def test_get_status_empty(self, store):
        res = store.get_status("unknown")
        assert res.status == GetStatus.EMPTY

    def test_get_status_held(self, store):
        # use monkeypatch to insert mock raw data into fakeredis since reserve mock won't write
        import json
        store.client.set("idemp:held1", json.dumps({"status": "HELD", "owner": "own", "payload_digest": "dig"}))
        res = store.get_status("held1")
        assert res.status == GetStatus.HELD
        assert res.owner == "own"

    def test_get_status_confirmed(self, store):
        import json
        store.client.set("idemp:conf1", json.dumps({"status": "CONFIRMED", "owner": "own", "payload_digest": "dig", "meta": {"m": 2}}))
        res = store.get_status("conf1")
        assert res.status == GetStatus.CONFIRMED
        assert res.meta == {"m": 2}

    def test_get_status_store_error(self, store, monkeypatch):
        def fake_exists(*args, **kwargs):
            import redis
            raise redis.RedisError("exists error")
        monkeypatch.setattr(store.client, "exists", fake_exists)
        with pytest.raises(StoreError):
            store.get_status("unknown")

    def test_release_success(self, store):
        res = store.release("r1", "own")
        assert res.status == ReleaseStatus.RELEASED

    def test_release_missing(self, store):
        with pytest.raises(MissingError):
            store.release("nonexistent", "own")

    def test_release_error(self, store):
        with pytest.raises(StoreError):
            store.release("rel_r2", "own2")

    def test_release_store_error(self, store):
        with pytest.raises(StoreError):
            store.release("err_eval", "own")

    def test_release_unknown_status(self, store):
        with pytest.raises(StoreError):
            store.release("rel_r4", "own")

    def test_circuit_breaker_open(self, mock_redis):
        store_cb = RedisIdempotencyStore(
            redis_url="redis://localhost",
            worker_id="test_worker",
            retry_max_attempts=2,
            cb_threshold=0.5,
            cb_cooldown_ms=50
        )
        
        # Manually fail requests to open CB
        store_cb._record_cb_result(False)
        store_cb._record_cb_result(False)
        # artificially bump total to pass 100 window to trigger CB check?
        # CB triggers when _cb_total_count >= 100
        store_cb._cb_total_count = 100
        store_cb._cb_error_count = 60
        store_cb._record_cb_result(False) # trigger open
        
        assert store_cb._cb_state == "OPEN"
        with pytest.raises(CBOpenError):
            store_cb.get_status("anything")
            
        import time
        time.sleep(0.06) # wait for cooldown
        
        # Now it should be HALF_OPEN and allow one
        res = store_cb.get_status("anything")
        assert store_cb._cb_state == "HALF_OPEN"
        
        # succeed probes
        for _ in range(store_cb.cb_half_open_probes + 1):
            store_cb._record_cb_result(True)
        assert store_cb._cb_state == "CLOSED"

    def test_circuit_breaker_half_open_fail(self, mock_redis):
        store_cb = RedisIdempotencyStore(
            redis_url="redis://localhost",
            worker_id="test_worker"
        )
        store_cb._cb_state = "HALF_OPEN"
        store_cb._cb_total_count = 100
        store_cb._record_cb_result(False)
        assert store_cb._cb_state == "OPEN"

    def test_import_error_simulation(self, monkeypatch):
        # Simulate import error
        import sys
        monkeypatch.setitem(sys.modules, 'redis', None)
        import vfoundation.core.idempotency.backends.redis_store as rds
        
        rds.REDIS_AVAILABLE = False
        try:
            with pytest.raises(ImportError):
                rds.RedisIdempotencyStore("redis://localhost", "w1")
        finally:
            rds.REDIS_AVAILABLE = True
