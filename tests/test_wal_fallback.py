"""Tests for WAL fallback scenarios and edge cases"""

import tempfile
from pathlib import Path
from vfoundation.dr import wal


def test_wal_no_lock_fallback():
    """Test WAL append when file locking is not available"""
    with tempfile.TemporaryDirectory() as temp_dir:
        wal.set_wal_dir(Path(temp_dir))

        # Mock LOCK_AVAILABLE to False
        original_lock_available = wal.LOCK_AVAILABLE
        try:
            wal.LOCK_AVAILABLE = False

            # Should still work without locking (single-threaded fallback)
            record = {"rid": "test-no-lock", "op": "DEC", "verb": "TEST"}
            hash_val = wal.append(record)

            assert hash_val is not None
            assert len(hash_val) == 64  # SHA256 hex digest

        finally:
            wal.LOCK_AVAILABLE = original_lock_available


def test_wal_read_last_hash_empty_file():
    """Test read_last_hash on empty/nonexistent file"""
    with tempfile.TemporaryDirectory() as temp_dir:
        wal.set_wal_dir(Path(temp_dir))

        # Should return None for nonexistent file
        last_hash = wal.read_last_hash()
        assert last_hash is None


def test_wal_read_last_hash_with_data():
    """Test read_last_hash retrieves last record hash"""
    with tempfile.TemporaryDirectory() as temp_dir:
        wal.set_wal_dir(Path(temp_dir))

        # Append some records
        hash1 = wal.append({"rid": "r1", "seq": 1})
        hash2 = wal.append({"rid": "r2", "seq": 2})
        hash3 = wal.append({"rid": "r3", "seq": 3})

        # Should get the last hash
        last_hash = wal.read_last_hash()
        assert last_hash == hash3
        assert last_hash != hash1
        assert last_hash != hash2


def test_wal_append_cas_no_expected_hash():
    """Test append_cas without expected_prev_hash (should always succeed)"""
    with tempfile.TemporaryDirectory() as temp_dir:
        wal.set_wal_dir(Path(temp_dir))

        # First record
        wal.append({"rid": "r1", "data": "first"})

        # CAS without expected hash should succeed
        success, hash_val = wal.append_cas(
            {"rid": "r2", "data": "second"}, expected_prev_hash=None
        )

        assert success is True
        assert hash_val is not None
        assert len(hash_val) == 64


def test_wal_append_cas_hash_mismatch():
    """Test append_cas fails when expected hash doesn't match"""
    with tempfile.TemporaryDirectory() as temp_dir:
        wal.set_wal_dir(Path(temp_dir))

        # Append first record
        wal.append({"rid": "r1", "data": "first"})

        # Try CAS with wrong expected hash
        wrong_hash = "a" * 64
        success, hash_val = wal.append_cas(
            {"rid": "r2", "data": "second"}, expected_prev_hash=wrong_hash
        )

        assert success is False
        assert hash_val is None


def test_wal_verify_chain_empty():
    """Test verify_chain on empty list"""
    result = wal.verify_chain([])
    assert result is True  # Empty chain is valid


def test_wal_verify_chain_single_record():
    """Test verify_chain with single record"""
    import hashlib
    import json

    # Create valid single record
    record = {"_prev": "0" * 64, "data": "test"}
    actual_hash = hashlib.sha256(
        json.dumps(record, sort_keys=True).encode()
    ).hexdigest()
    record["_hash"] = actual_hash

    records = [record]

    # Should pass with valid hash
    result = wal.verify_chain(records)
    assert result is True


def test_wal_calculate_merkle_root_empty():
    """Test calculate_merkle_root on empty hash list"""
    root = wal.calculate_merkle_root([])
    assert root == "0" * 64  # Default root for empty


def test_wal_calculate_merkle_root_single():
    """Test calculate_merkle_root with single hash"""
    hashes = ["a" * 64]
    root = wal.calculate_merkle_root(hashes)
    assert root == "a" * 64  # Single hash is the root


def test_wal_calculate_merkle_root_two():
    """Test calculate_merkle_root with two hashes"""
    import hashlib

    hash1 = "a" * 64
    hash2 = "b" * 64

    # Expected: hash(hash1 + hash2)
    expected = hashlib.sha256((hash1 + hash2).encode()).hexdigest()

    root = wal.calculate_merkle_root([hash1, hash2])
    assert root == expected


def test_wal_get_lock_metrics():
    """Test get_lock_metrics returns expected structure"""
    metrics = wal.get_lock_metrics()

    assert "lock_contention" in metrics
    assert "lock_wait_ms" in metrics
    assert "lock_timeouts" in metrics

    assert isinstance(metrics["lock_contention"], int)
    assert isinstance(metrics["lock_wait_ms"], (int, float))
    assert isinstance(metrics["lock_timeouts"], int)
