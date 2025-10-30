"""Ultra-specific tests to hit exact missing lines for 90% coverage."""

import pathlib
from vfoundation.core.retry_cb import CircuitBreaker, RetryPolicy
from vfoundation.dr import wal


def test_circuit_breaker_unknown_state_fallback():
    """Test circuit breaker fallback return statement (line 50)"""
    cb = CircuitBreaker(threshold=5, cool_down_s=1.0)

    # Manually set an impossible state to trigger the fallback
    # (This is for covering the edge case at line 50)
    with cb._lock:
        cb.state = "UNKNOWN_STATE"  # Invalid state

    # Should fall back to True
    result = cb.allow()
    assert result is True


def test_retry_policy_custom_parameters():
    """Test RetryPolicy with various parameter combinations"""
    # Test default parameters
    policy1 = RetryPolicy()
    assert policy1.retries == 3
    assert policy1.base_ms == 20
    assert policy1.max_ms == 2000

    # Test custom parameters
    policy2 = RetryPolicy(retries=5, base_ms=50, max_ms=5000)
    assert policy2.retries == 5
    assert policy2.base_ms == 50
    assert policy2.max_ms == 5000

    # Test backoff calculation
    backoff = policy2.backoff_ms(3)
    assert backoff > 0
    assert backoff <= policy2.max_ms


def test_retry_policy_backoff_large_attempt():
    """Test backoff with very large attempt number"""
    policy = RetryPolicy(base_ms=10, max_ms=1000)

    # Large attempt number should still respect max_ms
    backoff = policy.backoff_ms(100)
    assert backoff <= policy.max_ms
    assert backoff > 0


def test_wal_get_wal_file_path(tmp_path):
    """Test _get_wal_file_path exposed function"""
    import pathlib

    wal_dir = tmp_path / "test_path"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)

    # Get current file path
    file_path = wal._get_wal_file_path()
    assert isinstance(file_path, pathlib.Path)
    assert file_path.parent == wal_dir
    assert file_path.suffix == ".jsonl"

    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))


def test_wal_verify_chain_hash_mismatch():
    """Test verify_chain with hash mismatch"""
    import hashlib
    import json

    # Create record with wrong hash
    record_data = {"rid": "test", "data": "value", "_prev": "0" * 64}
    record_json = json.dumps(record_data, sort_keys=True)
    hashlib.sha256(record_json.encode()).hexdigest()

    # Use wrong hash
    wrong_hash = "f" * 64
    record = {**record_data, "_hash": wrong_hash}

    # Should fail verification
    result = wal.verify_chain([record])
    assert not result


def test_wal_calculate_merkle_root_five_hashes():
    """Test merkle root with five hashes (odd number)"""
    hashes = ["1" * 64, "2" * 64, "3" * 64, "4" * 64, "5" * 64]

    root = wal.calculate_merkle_root(hashes)
    assert root is not None
    assert len(root) == 64

    # Different order = different root
    hashes_shuffled = ["5" * 64, "1" * 64, "3" * 64, "2" * 64, "4" * 64]
    root_shuffled = wal.calculate_merkle_root(hashes_shuffled)
    assert root != root_shuffled


def test_wal_append_lock_timeout(tmp_path):
    """Test WAL append with very short timeout"""
    wal_dir = tmp_path / "wal_short_timeout"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)

    # Append with short timeout (should still work for single thread)
    record = {"rid": "timeout-short", "data": "test"}
    hash_val = wal.append(record, lock_timeout_s=0.1)

    assert hash_val is not None

    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))


def test_wal_append_cas_lock_timeout(tmp_path):
    """Test append_cas with timeout parameter"""
    wal_dir = tmp_path / "wal_cas_timeout"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)

    # First append
    hash1 = wal.append({"rid": "r1", "data": "first"})

    # CAS append with custom timeout
    success, hash2 = wal.append_cas(
        {"rid": "r2", "data": "second"}, expected_prev_hash=hash1, lock_timeout_s=0.5
    )

    assert success
    assert hash2 is not None

    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))
