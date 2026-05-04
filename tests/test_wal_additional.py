"""Additional WAL edge case tests to reach 90% coverage."""

import pathlib
import json
from vfoundation.dr import wal


def test_wal_set_wal_dir(tmp_path):
    """Test set_wal_dir function"""
    custom_dir = tmp_path / "custom_wal"
    wal.set_wal_dir(custom_dir)

    # Verify directory is created on append
    record = {"rid": "test-set-dir", "data": "value"}
    hash_val = wal.append(record)

    assert custom_dir.exists()
    assert hash_val is not None

    # Reset to default
    wal.set_wal_dir(pathlib.Path("ops/wal"))


def test_wal_read_last_hash_with_multiple_records(tmp_path):
    """Test read_last_hash with multiple records"""
    wal_dir = tmp_path / "wal_multi"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)

    # Append multiple records
    hash1 = wal.append({"rid": "r1", "data": "first"})
    hash2 = wal.append({"rid": "r2", "data": "second"})
    hash3 = wal.append({"rid": "r3", "data": "third"})

    # Read last hash
    last_hash = wal.read_last_hash()
    assert last_hash == hash3
    assert last_hash != hash1
    assert last_hash != hash2

    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))


def test_wal_append_cas_with_hash_mismatch(tmp_path):
    """Test append_cas with incorrect expected_prev_hash"""
    wal_dir = tmp_path / "wal_cas_mismatch"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)

    # Append first record
    wal.append({"rid": "r1", "data": "first"})

    # Try to append with wrong expected hash
    wrong_hash = "0" * 64
    success, result_hash = wal.append_cas(
        {"rid": "r2", "data": "second"}, expected_prev_hash=wrong_hash
    )

    # Should fail due to hash mismatch
    assert not success
    assert result_hash is None

    # Verify second record was NOT appended
    file_content = list((wal_dir).glob("*.jsonl"))[0].read_text()
    lines = file_content.strip().split("\n")
    assert len(lines) == 1  # Only first record present

    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))


def test_wal_append_cas_with_correct_hash(tmp_path):
    """Test append_cas with correct expected_prev_hash"""
    wal_dir = tmp_path / "wal_cas_correct"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)

    # Append first record
    hash1 = wal.append({"rid": "r1", "data": "first"})

    # Append with correct expected hash
    success, result_hash = wal.append_cas(
        {"rid": "r2", "data": "second"}, expected_prev_hash=hash1
    )

    # Should succeed
    assert success
    assert result_hash is not None

    # Verify both records present
    file_content = list((wal_dir).glob("*.jsonl"))[0].read_text()
    lines = file_content.strip().split("\n")
    assert len(lines) == 2

    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))


def test_wal_verify_chain_with_broken_chain(tmp_path):
    """Test verify_chain detects broken hash chain"""
    wal_dir = tmp_path / "wal_broken"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)

    # Append records
    wal.append({"rid": "r1", "data": "first"})
    wal.append({"rid": "r2", "data": "second"})

    # Read events
    wal_file = list(wal_dir.glob("*.jsonl"))[0]
    lines = wal_file.read_text().strip().split("\n")
    events = [json.loads(line) for line in lines]

    # Break the chain by modifying second event's _prev_hash
    events[1]["_prev_hash"] = "0" * 64

    # Verify chain should fail
    integrity_ok = wal.verify_chain(events)
    assert not integrity_ok

    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))


def test_wal_calculate_merkle_root_odd_count(tmp_path):
    """Test merkle root calculation with odd number of hashes"""
    hash1 = "a" * 64
    hash2 = "b" * 64
    hash3 = "c" * 64

    # Odd number of hashes
    root = wal.calculate_merkle_root([hash1, hash2, hash3])
    assert root is not None
    assert len(root) == 64

    # Should differ from even count
    root_even = wal.calculate_merkle_root([hash1, hash2])
    assert root != root_even


def test_wal_calculate_merkle_root_large_set(tmp_path):
    """Test merkle root with larger set of hashes"""
    hashes = [str(i).zfill(64) for i in range(10)]

    root = wal.calculate_merkle_root(hashes)
    assert root is not None
    assert len(root) == 64

    # Different input should produce different root
    hashes_modified = hashes[::-1]  # Reverse order
    root_modified = wal.calculate_merkle_root(hashes_modified)
    assert root != root_modified
