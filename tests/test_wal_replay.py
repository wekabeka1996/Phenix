from __future__ import annotations
from vfoundation.dr import wal
from vfoundation.dr.replay import replay_for_rid, replay_for_rid_with_integrity
import json
import pathlib
import tempfile

def test_wal_and_replay(tmp_path, monkeypatch):
    # Set WAL dir to tmp_path for this test
    wal_dir = tmp_path / "ops" / "wal"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)
    
    rid = "abc"
    wal.append({"rid": rid, "hello": "world"})
    
    # Temporarily change replay to use the correct WAL dir
    monkeypatch.chdir(tmp_path)
    
    seen = []
    evs = replay_for_rid(rid, handler=lambda e: seen.append(e))
    assert evs and seen and evs[0]["rid"] == rid


def test_wal_and_replay_with_integrity(tmp_path, monkeypatch):
    """Test new replay_for_rid_with_integrity function"""
    # Set WAL dir to tmp_path for this test
    wal_dir = tmp_path / "ops" / "wal"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)
    
    rid = "test-integrity"

    # Append multiple events to create a chain
    wal.append({"rid": rid, "event": "first", "data": "test1"})
    wal.append({"rid": rid, "event": "second", "data": "test2"})

    # Temporarily change replay to use the correct WAL dir
    monkeypatch.chdir(tmp_path)
    
    seen = []
    events, integrity_ok, merkle_root = replay_for_rid_with_integrity(
        rid,
        handler=lambda e: seen.append(e)
    )

    # Check basic functionality
    assert len(events) == 2
    assert len(seen) == 2
    assert events[0]["rid"] == rid
    assert events[1]["rid"] == rid
    
    # Check integrity results
    assert isinstance(integrity_ok, bool)
    assert integrity_ok  # Should be valid chain
    assert isinstance(merkle_root, str)
    assert len(merkle_root) == 64  # SHA256 hex string
    
    # Verify events contain hash chain data
    assert "_hash" in events[0]
    assert "_prev" in events[0]
    assert "_hash" in events[1] 
    assert "_prev" in events[1]
    assert len(seen) == 2
    assert events[0]["rid"] == rid
    assert events[1]["rid"] == rid
    
    # Check integrity fields
    assert isinstance(integrity_ok, bool)
    assert isinstance(merkle_root, str)
    assert len(merkle_root) == 64  # SHA256 hex length


def test_replay_chain_integrity():
    """Test replay verifies hash chain integrity"""
    import hashlib
    from vfoundation.dr import wal as wal_module
    
    with tempfile.TemporaryDirectory() as temp_dir:
        wal_dir = pathlib.Path(temp_dir)
        wal_module.set_wal_dir(wal_dir)
        
        wal_file = wal_dir / "2025-01-12.jsonl"
        
        # Create events with valid hash chain
        prev_hash = "0" * 64
        event1 = {"rid": "r1", "_prev": prev_hash}
        hash1 = hashlib.sha256(json.dumps(event1, sort_keys=True).encode()).hexdigest()
        event1["_hash"] = hash1
        
        event2 = {"rid": "r1", "_prev": hash1}
        hash2 = hashlib.sha256(json.dumps(event2, sort_keys=True).encode()).hexdigest()
        event2["_hash"] = hash2
        
        events = [event1, event2]
        
        with open(wal_file, 'w') as f:
            for event in events:
                f.write(json.dumps(event) + "\n")
        
        events_found, integrity_ok, merkle_root = replay_for_rid_with_integrity("r1", lambda e: None)
        
        assert len(events_found) == 2
        assert integrity_ok is True  # Should pass with valid chain
        assert merkle_root  # Should have merkle root


def test_replay_invalid_json_lines():
    """Test replay handles invalid JSON lines gracefully"""
    from vfoundation.dr import wal as wal_module
    
    with tempfile.TemporaryDirectory() as temp_dir:
        wal_dir = pathlib.Path(temp_dir)
        wal_module.set_wal_dir(wal_dir)
        
        wal_file = wal_dir / "2025-01-12.jsonl"
        
        # Mix of valid and invalid JSON
        with open(wal_file, 'w') as f:
            f.write('{"rid": "r1", "valid": true}\n')
            f.write('invalid json line\n')  # Should be skipped
            f.write('{"rid": "r1", "valid": true, "second": 1}\n')
            f.write('{broken json\n')  # Should be skipped
        
        events_found, _, _ = replay_for_rid_with_integrity("r1", lambda e: None)
        
        # Only 2 valid events should be found
        assert len(events_found) == 2
        assert events_found[0]["valid"] is True
        assert events_found[1]["second"] == 1


def test_replay_nonexistent_wal_dir():
    """Test replay when WAL directory doesn't exist"""
    with tempfile.TemporaryDirectory() as temp_dir:
        non_existent = pathlib.Path(temp_dir) / "nonexistent"
        
        # Test with non-existent directory
        import os
        old_wal = os.environ.get("WAL_DIR")
        os.environ["WAL_DIR"] = str(non_existent)
        
        try:
            events, integrity_ok, merkle_root = replay_for_rid_with_integrity("r1", lambda e: None)
            
            assert events == []
            assert integrity_ok is True  # Empty is considered valid
            assert merkle_root == "0" * 64  # Default root
        finally:
            if old_wal:
                os.environ["WAL_DIR"] = old_wal
            else:
                os.environ.pop("WAL_DIR", None)


def test_merkle_root_calculation():
    """Test merkle root calculation"""
    # Test edge cases
    assert wal.calculate_merkle_root([]) == "0" * 64
    assert wal.calculate_merkle_root(["single"]) == "single"
    
    # Test with multiple hashes
    hashes = ["a", "b", "c", "d"]
    root = wal.calculate_merkle_root(hashes)
    assert isinstance(root, str)
    assert len(root) == 64


def test_wal_hash_chain_integrity_append(tmp_path, monkeypatch):
    """Test that WAL append creates proper hash-chain integrity (AURORA_HARDENING_V1)."""
    # Set WAL dir to tmp_path for this test
    wal_dir = tmp_path / "ops" / "wal"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)
    
    rid = "test-chain"
    
    # Append first event
    hash1 = wal.append({"rid": rid, "event": "first", "data": "test1"})
    assert hash1
    assert len(hash1) == 64  # SHA256 hex length
    
    # Append second event - should reference first event's hash
    hash2 = wal.append({"rid": rid, "event": "second", "data": "test2"})
    assert hash2
    assert len(hash2) == 64
    assert hash2 != hash1  # Different content, different hash
    
    # Read raw WAL file to verify hash chain structure
    wal_file = wal_dir / f"{pathlib.Path().cwd().name.replace('Olimp_v1', '')}2025-01-25.jsonl"
    if not wal_file.exists():
        # Try alternative naming
        import datetime
        today = datetime.date.today().strftime("%Y-%m-%d")
        wal_file = wal_dir / f"{today}.jsonl"
    
    assert wal_file.exists(), f"WAL file not found at {wal_file}"
    
    with open(wal_file, 'r') as f:
        lines = f.readlines()
        assert len(lines) == 2
        
        event1 = json.loads(lines[0])
        event2 = json.loads(lines[1])
        
        # First event should have _prev = "0"*64 (genesis)
        assert event1["_prev"] == "0" * 64
        assert event1["_hash"] == hash1
        assert event1["rid"] == rid
        
        # Second event should reference first event's hash
        assert event2["_prev"] == hash1
        assert event2["_hash"] == hash2
        assert event2["rid"] == rid


def test_wal_hash_chain_integrity_verification(tmp_path, monkeypatch):
    """Test hash-chain integrity verification during replay (AURORA_HARDENING_V1)."""
    # Set WAL dir to tmp_path for this test
    wal_dir = tmp_path / "ops" / "wal"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)
    
    rid = "test-verification"
    
    # Create valid chain
    wal.append({"rid": rid, "event": "first"})
    wal.append({"rid": rid, "event": "second"})
    wal.append({"rid": rid, "event": "third"})
    
    # Test replay with integrity check
    monkeypatch.chdir(tmp_path)
    events, integrity_ok, merkle_root = replay_for_rid_with_integrity(rid, lambda e: None)
    
    assert len(events) == 3
    assert integrity_ok is True  # Valid chain
    assert isinstance(merkle_root, str)
    assert len(merkle_root) == 64


def test_wal_hash_chain_corruption_detection(tmp_path, monkeypatch):
    """Test detection of hash-chain corruption during replay (AURORA_HARDENING_V1)."""
    # Set WAL dir to tmp_path for this test
    wal_dir = tmp_path / "ops" / "wal"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)
    
    rid = "test-corruption"
    
    # Create valid chain
    wal.append({"rid": rid, "event": "first"})
    wal.append({"rid": rid, "event": "second"})
    
    # Manually corrupt the WAL file by changing a _prev hash
    wal_file = wal_dir / f"{pathlib.Path().cwd().name.replace('Olimp_v1', '')}2025-01-25.jsonl"
    if not wal_file.exists():
        import datetime
        today = datetime.date.today().strftime("%Y-%m-%d")
        wal_file = wal_dir / f"{today}.jsonl"
    
    with open(wal_file, 'r') as f:
        lines = f.readlines()
    
    # Corrupt second event's _prev hash
    event2 = json.loads(lines[1])
    event2["_prev"] = "f" * 64  # Invalid previous hash
    lines[1] = json.dumps(event2) + "\n"
    
    with open(wal_file, 'w') as f:
        f.writelines(lines)
    
    # Test replay - should detect corruption
    monkeypatch.chdir(tmp_path)
    events, integrity_ok, merkle_root = replay_for_rid_with_integrity(rid, lambda e: None)
    
    assert len(events) == 2  # Both events loaded
    assert integrity_ok is False  # But integrity check failed


def test_wal_record_hash_mismatch_detection(tmp_path, monkeypatch):
    """Test detection of record content corruption (hash mismatch) during replay (AURORA_HARDENING_V1)."""
    # Set WAL dir to tmp_path for this test
    wal_dir = tmp_path / "ops" / "wal"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)
    
    rid = "test-hash-mismatch"
    
    # Create valid chain
    wal.append({"rid": rid, "event": "first"})
    wal.append({"rid": rid, "event": "second"})
    
    # Manually corrupt the WAL file by changing record content but keeping old hash
    wal_file = wal_dir / f"{pathlib.Path().cwd().name.replace('Olimp_v1', '')}2025-01-25.jsonl"
    if not wal_file.exists():
        import datetime
        today = datetime.date.today().strftime("%Y-%m-%d")
        wal_file = wal_dir / f"{today}.jsonl"
    
    with open(wal_file, 'r') as f:
        lines = f.readlines()
    
    # Corrupt second event's content but keep the hash
    event2 = json.loads(lines[1])
    event2["event"] = "modified"  # Change content
    # Keep the old hash - this will cause mismatch
    lines[1] = json.dumps(event2) + "\n"
    
    with open(wal_file, 'w') as f:
        f.writelines(lines)
    
    # Test replay - should detect hash mismatch
    monkeypatch.chdir(tmp_path)
    events, integrity_ok, merkle_root = replay_for_rid_with_integrity(rid, lambda e: None)
    
    assert len(events) == 2  # Both events loaded
    assert integrity_ok is False  # But integrity check failed due to hash mismatch
