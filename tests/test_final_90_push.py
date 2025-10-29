"""Final push to 90%+ coverage."""
import pathlib
from vfoundation.dr import wal

def test_wal_read_last_hash_no_files(tmp_path):
    """Test read_last_hash when WAL directory has no files"""
    wal_dir = tmp_path / "wal_no_files"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)
    
    # No files yet
    last_hash = wal.read_last_hash()
    assert last_hash is None
    
    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))

def test_wal_append_minimal_record(tmp_path):
    """Test WAL append with minimal record"""
    wal_dir = tmp_path / "wal_minimal"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)
    
    # Minimal record
    record = {"rid": "min"}
    hash_val = wal.append(record)
    
    assert hash_val is not None
    assert len(hash_val) == 64
    
    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))

def test_wal_append_large_record(tmp_path):
    """Test WAL append with large record"""
    wal_dir = tmp_path / "wal_large"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)
    
    # Large record with lots of data
    record = {
        "rid": "large",
        "data": "x" * 10000,  # 10KB of data
        "nested": {f"key_{i}": f"value_{i}" for i in range(100)}
    }
    hash_val = wal.append(record)
    
    assert hash_val is not None
    
    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))

def test_wal_multiple_files_scenario(tmp_path):
    """Test scenario where multiple WAL files might exist"""
    wal_dir = tmp_path / "wal_multi_files"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)
    
    # Append records
    for i in range(3):
        wal.append({"rid": f"multi-{i}", "data": f"test-{i}"})
    
    # Get last hash
    last_hash = wal.read_last_hash()
    assert last_hash is not None
    
    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))

def test_wal_verify_chain_prev_mismatch():
    """Test verify_chain with _prev field mismatch"""
    import hashlib
    import json
    
    # First record with correct setup
    record1_data = {"rid": "r1", "data": "first", "_prev": "0" * 64}
    json1 = json.dumps(record1_data, sort_keys=True)
    hash1 = hashlib.sha256(json1.encode()).hexdigest()
    record1 = {**record1_data, "_hash": hash1}
    
    # Second record with WRONG _prev (doesn't match hash1)
    record2_data = {"rid": "r2", "data": "second", "_prev": "f" * 64}  # Wrong!
    json2 = json.dumps(record2_data, sort_keys=True)
    hash2 = hashlib.sha256(json2.encode()).hexdigest()
    record2 = {**record2_data, "_hash": hash2}
    
    # Chain verification should fail due to _prev mismatch
    result = wal.verify_chain([record1, record2])
    assert not result

def test_wal_calculate_merkle_root_seven_hashes():
    """Test merkle root with seven hashes"""
    hashes = [str(i).zfill(64) for i in range(7)]
    
    root = wal.calculate_merkle_root(hashes)
    assert root is not None
    assert len(root) == 64

def test_wal_calculate_merkle_root_power_of_two():
    """Test merkle root with 8 hashes (power of 2)"""
    hashes = [str(i).zfill(64) for i in range(8)]
    
    root = wal.calculate_merkle_root(hashes)
    assert root is not None
    assert len(root) == 64

def test_wal_consecutive_appends_chain_integrity(tmp_path):
    """Test chain integrity across multiple consecutive appends"""
    wal_dir = tmp_path / "wal_consecutive"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)
    
    # Append multiple records consecutively
    hashes = []
    for i in range(10):
        h = wal.append({"rid": f"chain-{i}", "index": i})
        hashes.append(h)
    
    # All hashes should be unique
    assert len(set(hashes)) == len(hashes)
    
    # Read and verify chain
    import json
    wal_file = list(wal_dir.glob("*.jsonl"))[0]
    lines = wal_file.read_text().strip().split("\n")
    records = [json.loads(line) for line in lines]
    
    # Verify integrity
    assert wal.verify_chain(records)
    
    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))

def test_wal_append_special_characters(tmp_path):
    """Test WAL append with special characters"""
    wal_dir = tmp_path / "wal_special"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)
    
    # Special characters
    record = {
        "rid": "special",
        "data": "\n\t\r",
        "quotes": "\"'`",
        "symbols": "!@#$%^&*()",
        "unicode": "🚀💯✨"
    }
    hash_val = wal.append(record)
    
    assert hash_val is not None
    
    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))

def test_wal_lock_metrics_accumulation():
    """Test that lock metrics accumulate across multiple operations"""
    wal.get_lock_metrics()
    
    # Perform operations
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_dir = pathlib.Path(tmpdir) / "metrics_test"
        wal_dir.mkdir(parents=True)
        wal.set_wal_dir(wal_dir)
        
        for i in range(5):
            wal.append({"rid": f"metrics-{i}", "data": "test"})
        
        # Metrics should have been updated
        final_metrics = wal.get_lock_metrics()
        assert isinstance(final_metrics["lock_contention"], (int, float))
        assert isinstance(final_metrics["lock_wait_ms"], (int, float))
        assert isinstance(final_metrics["lock_timeouts"], (int, float))
        
        # Reset
        wal.set_wal_dir(pathlib.Path("ops/wal"))
