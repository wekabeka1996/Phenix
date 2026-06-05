"""Coverage tests for SimpleRedisIdempotencyStore using fakeredis."""
import pytest
import json
import fakeredis
from vfoundation.core.idempotency.backends.simple_redis_store import SimpleRedisIdempotencyStore
from vfoundation.core.idempotency.errors import BusyError, ConflictError, MissingError, StoreError
from vfoundation.core.idempotency.store import ReserveStatus, ConfirmStatus, GetStatus, ReleaseStatus


@pytest.fixture
def mock_redis(monkeypatch):
    """Patch redis.from_url to return a fakeredis instance."""
    fake_client = fakeredis.FakeRedis(decode_responses=True)
    def fake_from_url(*args, **kwargs):
        return fake_client
    monkeypatch.setattr("redis.from_url", fake_from_url)
    return fake_client


@pytest.fixture
def store(mock_redis):
    # This will use the patched from_url
    return SimpleRedisIdempotencyStore(redis_url="redis://localhost", worker_id="test_worker")


class TestSimpleRedisIdempotencyStore:
    def test_init_success(self, store):
        assert store.worker_id == "test_worker"
        assert store.client is not None

    def test_init_connection_error(self, monkeypatch):
        def fake_from_url(*args, **kwargs):
            raise ConnectionError("redis down")
        monkeypatch.setattr("redis.from_url", fake_from_url)
        with pytest.raises(StoreError, match="connect"):
            SimpleRedisIdempotencyStore("redis://localhost", "w1")
            
    def test_reserve_new(self, store):
        res = store.reserve("key1", "digest1", 1000, "owner1")
        assert res.status == ReserveStatus.NEW
        assert res.lease_ms == 1000
        
        # Verify in redis
        raw = store.client.get("idemp:key1")
        assert raw is not None
        record = json.loads(raw)
        assert record["owner"] == "owner1"
        assert record["status"] == "HELD"

    def test_reserve_duplicate_same(self, store):
        store.reserve("key2", "digest2", 1000, "owner2")
        # Same owner and digest
        res = store.reserve("key2", "digest2", 1000, "owner2")
        assert res.status == ReserveStatus.DUPLICATE_SAME
        
    def test_reserve_busy_extern_owner(self, store):
        store.reserve("key3", "digest3", 1000, "owner3")
        with pytest.raises(BusyError):
            store.reserve("key3", "digest3", 1000, "other_owner")
            
    def test_reserve_conflict_different_digest(self, store):
        store.reserve("key4", "digest4", 1000, "owner4")
        with pytest.raises(ConflictError):
            store.reserve("key4", "different", 1000, "owner4")
            
    def test_reserve_race_condition(self, store, monkeypatch):
        # Fake a case where exists() returns True but get() returns None
        original_exists = store.client.exists
        def fake_exists(key):
            if key == "idemp:race": return True
            return original_exists(key)
        monkeypatch.setattr(store.client, "exists", fake_exists)
        
        # When get() is called on "idemp:race", fakeredis will return None
        # It should recurse and then call exists() again. We need exists() to return False the second time.
        call_count = [0]
        def fake_exists_dynamic(key):
            if key == "idemp:race":
                call_count[0] += 1
                if call_count[0] == 1:
                    return True  # First call: pretend it's there
                return False     # Second call: pretend it's gone
            return original_exists(key)
        monkeypatch.setattr(store.client, "exists", fake_exists_dynamic)
        
        res = store.reserve("race", "digest_race", 1000, "owner")
        assert res.status == ReserveStatus.NEW

    def test_reserve_store_error(self, store, monkeypatch):
        def fake_exists(key):
            raise Exception("unexpected")
        monkeypatch.setattr(store.client, "exists", fake_exists)
        with pytest.raises(StoreError):
            store.reserve("ex", "dig", 1000, "own")

    def test_confirm_success(self, store):
        store.reserve("conf", "dig", 1000, "own")
        res = store.confirm("conf", "OK", {"meta_info": 1})
        assert res.status == ConfirmStatus.CONFIRMED
        
        record = json.loads(store.client.get("idemp:conf"))
        assert record["status"] == "CONFIRMED"
        assert record["final_status"] == "OK"
        assert record["meta"] == {"meta_info": 1}
        
    def test_confirm_missing_key(self, store):
        with pytest.raises(MissingError):
            store.confirm("nonexistent", "OK")
            
    def test_confirm_store_error(self, store, monkeypatch):
        store.reserve("err", "dig", 1000, "own")
        def fake_get(key):
            raise Exception("redis broken")
        monkeypatch.setattr(store.client, "get", fake_get)
        with pytest.raises(StoreError):
            store.confirm("err", "OK")

    def test_get_status_empty(self, store):
        res = store.get_status("unknown")
        assert res.status == GetStatus.EMPTY
        
    def test_get_status_held(self, store):
        store.reserve("held", "dig", 1000, "own")
        res = store.get_status("held")
        assert res.status == GetStatus.HELD
        assert res.owner == "own"
        
    def test_get_status_confirmed(self, store):
        store.reserve("conf2", "dig", 1000, "own")
        store.confirm("conf2", "OK")
        res = store.get_status("conf2")
        assert res.status == GetStatus.CONFIRMED
        
    def test_get_status_store_error(self, store, monkeypatch):
        def fake_exists(key):
            raise Exception("boom")
        monkeypatch.setattr(store.client, "exists", fake_exists)
        with pytest.raises(StoreError):
            store.get_status("err")
            
    def test_release_success(self, store):
        store.reserve("rel", "dig", 1000, "own")
        res = store.release("rel", "own")
        assert res.status == ReleaseStatus.RELEASED
        assert store.client.exists("idemp:rel") == 0
        
    def test_release_missing(self, store):
        with pytest.raises(MissingError):
            store.release("nonexistent", "own")
            
    def test_release_wrong_owner(self, store):
        store.reserve("rel2", "dig", 1000, "own1")
        with pytest.raises(StoreError):
            store.release("rel2", "own2")

    def test_release_store_error(self, store, monkeypatch):
        store.reserve("err3", "dig", 1000, "own")
        def fake_delete(key):
            raise Exception("cant delete")
        monkeypatch.setattr(store.client, "delete", fake_delete)
        with pytest.raises(StoreError):
            store.release("err3", "own")

    def test_import_error_simulation(self, monkeypatch):
        # Simulate import error
        import sys
        monkeypatch.setitem(sys.modules, 'redis', None)
        # Import the module under test again to trigger the conditional block
        import importlib
        import vfoundation.core.idempotency.backends.simple_redis_store as srs
        
        # Actually simulating the module-level fallback might require reloading
        # Let's just set the variable manually to test the constructor's reaction
        srs.REDIS_AVAILABLE = False
        try:
            with pytest.raises(ImportError):
                srs.SimpleRedisIdempotencyStore("redis://localhost", "w1")
        finally:
            srs.REDIS_AVAILABLE = True
