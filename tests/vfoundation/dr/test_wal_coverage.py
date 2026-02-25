
import pytest
import os
import json
import time
import pathlib
from vfoundation.dr import wal

def test_wal_directory_custom(tmp_path):
    wal.set_wal_dir(tmp_path)
    assert wal.WAL_DIR == tmp_path
    
def test_wal_basic_append_and_read(tmp_path):
    wal.set_wal_dir(tmp_path)
    wal.reset()
    
    record1 = {"data": "first"}
    hash1 = wal.append(record1)
    assert hash1 is not None
    
    entries = wal.read_all()
    assert len(entries) == 1
    assert entries[0]["data"] == "first"
    assert entries[0]["_prev"] == "0" * 64
    
    record2 = {"data": "second"}
    hash2 = wal.append(record2)
    assert hash2 is not None
    
    entries = wal.read_all()
    assert len(entries) == 2
    assert entries[1]["_prev"] == hash1

def test_wal_read_last_hash_slow_path(tmp_path):
    wal.set_wal_dir(tmp_path)
    wal.reset() 
    # _last_hash is None initially
    
    h1 = wal.append({"a": 1})
    wal.reset() # Clear cache to force slow path (Line 62)
    assert wal.read_last_hash() == h1

def test_wal_read_last_hash_empty(tmp_path):
    wal.set_wal_dir(tmp_path)
    wal.reset()
    assert wal.read_last_hash() is None

def test_wal_read_last_hash_malformed(tmp_path):
    wal.set_wal_dir(tmp_path)
    wal.reset()
    path = wal._get_wal_file_path()
    path.write_text("not json\n")
    assert wal.read_last_hash() is None # Hits Line 79-80

def test_wal_read_by_rid(tmp_path):
    wal.set_wal_dir(tmp_path)
    wal.reset()
    
    wal.append({"rid": "r1", "pld": {"why": "reason1"}, "ts": 1000, "data_ref": ["d1"]})
    wal.append({"pld": {"rid": "r1", "why_chain": ["c1", "c2"]}, "ts": 2000})
    # Cover line 184 (fallback message why)
    wal.append({"rid": "r1", "why": "msg_why", "ts": 1500})
    
    events, why_chain, integrity = wal.read_by_rid("r1")
    assert len(events) == 3
    assert "reason1" in why_chain
    assert "c1" in why_chain
    assert "msg_why" in why_chain
    assert integrity is True

def test_wal_integrity_failure(tmp_path):
    wal.set_wal_dir(tmp_path)
    wal.reset()
    
    wal.append({"rid": "r1"})
    path = wal._get_wal_file_path()
    
    # Tamper with the file (broken hash)
    with open(path, "a") as f:
        f.write('{"rid": "r1", "_hash": "badhash"}\n')
        
    events, why_chain, integrity = wal.read_by_rid("r1")
    assert integrity is False

def test_wal_cas_success(tmp_path):
    wal.set_wal_dir(tmp_path)
    wal.reset()
    
    h1 = wal.append({"a": 1})
    success, h2 = wal.append_cas({"b": 2}, expected_prev_hash=h1)
    assert success is True
    assert h2 is not None

def test_wal_cas_failure(tmp_path):
    wal.set_wal_dir(tmp_path)
    wal.reset()
    
    wal.append({"a": 1})
    success, h2 = wal.append_cas({"b": 2}, expected_prev_hash="wrong_hash")
    assert success is False
    assert h2 is None

def test_wal_merkle_root():
    hashes = ["a" * 64, "b" * 64, "c" * 64]
    wal.calculate_merkle_root(hashes)
    assert wal.calculate_merkle_root([]) == "0" * 64
    assert wal.calculate_merkle_root(["foo"]) == "foo"

def test_wal_verify_chain():
    wal.reset()
    r1 = {"a": 1, "_prev": "0" * 64}
    r1["_hash"] = wal._calculate_record_hash(r1)
    
    r2 = {"b": 2, "_prev": r1["_hash"]}
    r2["_hash"] = wal._calculate_record_hash(r2)
    
    assert wal.verify_chain([r1, r2]) is True
    
    # Break chain
    r2["_prev"] = "wrong"
    assert wal.verify_chain([r1, r2]) is False

def test_wal_lock_metrics():
    wal.reset()
    metrics = wal.get_lock_metrics()
    assert metrics["lock_contention"] == 0
    
    # Manually trigger metric recording
    wal._record_lock_wait(10.5)
    wal._record_lock_timeout()
    
    metrics = wal.get_lock_metrics()
    assert metrics["lock_contention"] == 1
    assert metrics["lock_wait_ms"] == 10.5
    assert metrics["lock_timeouts"] == 1

def test_wal_read_malformed(tmp_path):
    wal.set_wal_dir(tmp_path)
    path = wal._get_wal_file_path()
    with open(path, "w") as f:
        f.write("not json\n")
        f.write('{"valid": true, "_id": 1}\n') # Missing hash
    
    entries = wal.read_all()
    assert len(entries) == 1
