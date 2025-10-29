"""Tests to push coverage to 90% by targeting specific uncovered lines."""
import pathlib
import json
from vfoundation.dr import wal
from vfoundation.core.retry_cb import CircuitBreaker

def test_circuit_breaker_state_transitions():
    """Test all circuit breaker state transitions"""
    cb = CircuitBreaker(threshold=2, cool_down_s=0.1)
    
    # Initial state: CLOSED
    assert cb.state == "CLOSED"
    assert cb.allow()
    
    # One failure - still CLOSED
    cb.on_failure()
    assert cb.state == "CLOSED"
    assert cb.allow()
    
    # Second failure - now OPEN
    cb.on_failure()
    assert cb.state == "OPEN"
    assert not cb.allow()
    
    # Wait for cooldown and transition to HALF_OPEN
    import time
    time.sleep(0.15)
    assert cb.allow()  # First call in HALF_OPEN returns True
    assert cb.state == "HALF_OPEN"
    
    # Another call in HALF_OPEN also returns True
    assert cb.allow()
    
    # Success closes the circuit
    cb.on_success()
    assert cb.state == "CLOSED"
    assert cb.failures == 0

def test_circuit_breaker_half_open_failure():
    """Test circuit breaker failing in HALF_OPEN state"""
    cb = CircuitBreaker(threshold=1, cool_down_s=0.1)
    
    # Trip the breaker
    cb.on_failure()
    assert cb.state == "OPEN"
    
    # Wait and transition to HALF_OPEN
    import time
    time.sleep(0.15)
    assert cb.allow()
    assert cb.state == "HALF_OPEN"
    
    # Failure in HALF_OPEN goes back to OPEN
    cb.on_failure()
    assert cb.state == "OPEN"
    assert cb.failures >= cb.threshold

def test_wal_append_multiple_same_day(tmp_path):
    """Test multiple WAL appends on the same day (same file)"""
    wal_dir = tmp_path / "wal_same_day"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)
    
    # Append multiple records
    records = [
        {"rid": f"r{i}", "data": f"value{i}"}
        for i in range(5)
    ]
    
    hashes = []
    for record in records:
        h = wal.append(record)
        assert h is not None
        hashes.append(h)
    
    # All hashes should be unique
    assert len(set(hashes)) == len(hashes)
    
    # Verify all records in single file
    wal_files = list(wal_dir.glob("*.jsonl"))
    assert len(wal_files) == 1
    
    lines = wal_files[0].read_text().strip().split("\n")
    assert len(lines) == 5
    
    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))

def test_wal_verify_chain_single_record():
    """Test verify_chain with single record"""
    import hashlib
    
    # Create record without _hash field first
    record_data = {"rid": "single", "data": "test", "_prev": "0" * 64}
    record_json = json.dumps(record_data, sort_keys=True)
    actual_hash = hashlib.sha256(record_json.encode()).hexdigest()
    
    # Add hash field
    record = {**record_data, "_hash": actual_hash}
    
    # Single record chain should be valid
    assert wal.verify_chain([record])

def test_wal_verify_chain_two_records():
    """Test verify_chain with two linked records"""
    import hashlib
    
    # First record
    record1_data = {"rid": "r1", "data": "first", "_prev": "0" * 64}
    json1 = json.dumps(record1_data, sort_keys=True)
    hash1 = hashlib.sha256(json1.encode()).hexdigest()
    record1 = {**record1_data, "_hash": hash1}
    
    # Second record
    record2_data = {"rid": "r2", "data": "second", "_prev": hash1}
    json2 = json.dumps(record2_data, sort_keys=True)
    hash2 = hashlib.sha256(json2.encode()).hexdigest()
    record2 = {**record2_data, "_hash": hash2}
    
    # Chain should be valid
    assert wal.verify_chain([record1, record2])

def test_wal_read_last_hash_empty_file(tmp_path):
    """Test read_last_hash with empty file"""
    wal_dir = tmp_path / "wal_empty_file"
    wal_dir.mkdir(parents=True, exist_ok=True)
    
    # Create empty file
    empty_file = wal_dir / "2024-01-01.jsonl"
    empty_file.write_text("")
    
    wal.set_wal_dir(wal_dir)
    
    # Should return None for empty file
    last_hash = wal.read_last_hash()
    assert last_hash is None
    
    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))
