"""Simple tests to reach 90% coverage target."""
import pathlib
from vfoundation.dr import wal
from vfoundation.core.retry_cb import RetryPolicy

def test_retry_policy_backoff():
    """Test retry policy backoff calculation"""
    policy = RetryPolicy(retries=5, base_ms=5, max_ms=500)
    
    # Test backoff progression (exponential with jitter)
    backoff0 = policy.backoff_ms(0)
    backoff1 = policy.backoff_ms(1)
    backoff2 = policy.backoff_ms(2)
    
    # Should increase exponentially (with jitter tolerance)
    # Base pattern: 5 * 2^n + jitter(0-10)
    # backoff0: ~5-15, backoff1: ~10-20, backoff2: ~20-30
    # Note: Relaxed bounds because jitter can overlap ranges
    assert backoff0 < backoff2, f"Expected backoff0={backoff0} < backoff2={backoff2}"
    
    # Verify approximate exponential growth (with generous jitter tolerance)
    assert 5 <= backoff0 <= 15, f"backoff0={backoff0} should be in [5, 15]"
    assert 8 <= backoff1 <= 22, f"backoff1={backoff1} should be in [8, 22]"
    assert 18 <= backoff2 <= 32, f"backoff2={backoff2} should be in [18, 32]"
    
    # Should respect max_ms
    backoff_large = policy.backoff_ms(20)
    assert backoff_large <= policy.max_ms

def test_retry_policy_max_retries():
    """Test retry policy retries parameter"""
    policy = RetryPolicy(retries=10)
    assert policy.retries == 10
    
    policy2 = RetryPolicy(retries=3)
    assert policy2.retries == 3

def test_wal_append_with_custom_timeout(tmp_path):
    """Test WAL append with custom lock timeout"""
    wal_dir = tmp_path / "wal_timeout"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)
    
    # Append with custom timeout
    record = {"rid": "timeout-test", "data": "value"}
    hash_val = wal.append(record, lock_timeout_s=1.0)
    
    assert hash_val is not None
    assert len(hash_val) == 64
    
    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))

def test_wal_get_lock_metrics():
    """Test WAL lock metrics getter"""
    metrics = wal.get_lock_metrics()
    
    assert "lock_contention" in metrics
    assert "lock_wait_ms" in metrics
    assert "lock_timeouts" in metrics
    
    assert isinstance(metrics["lock_contention"], (int, float))
    assert isinstance(metrics["lock_wait_ms"], (int, float))
    assert isinstance(metrics["lock_timeouts"], (int, float))

def test_wal_verify_chain_empty_list():
    """Test verify_chain with empty list"""
    result = wal.verify_chain([])
    assert result is True  # Empty chain is valid

def test_wal_calculate_merkle_root_empty():
    """Test merkle root with empty hash list"""
    root = wal.calculate_merkle_root([])
    assert root == "0" * 64  # Empty merkle root

def test_wal_calculate_merkle_root_single():
    """Test merkle root with single hash"""
    single_hash = "a" * 64
    root = wal.calculate_merkle_root([single_hash])
    # Single hash should hash with itself
    assert root is not None
    assert len(root) == 64
