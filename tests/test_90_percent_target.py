"""Final tests to reach exactly 90% coverage."""

import pathlib
import json
from vfoundation.dr import wal


def test_wal_record_lock_wait(tmp_path):
    """Test WAL internal lock metrics recording"""
    # This tests the internal _record_lock_wait function indirectly
    wal_dir = tmp_path / "wal_metrics"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)

    # Get baseline metrics
    wal.get_lock_metrics()

    # Multiple appends will trigger lock contention tracking
    for i in range(5):
        wal.append({"rid": f"r{i}", "data": "test"})

    # Metrics should be updated
    metrics_after = wal.get_lock_metrics()
    assert isinstance(metrics_after["lock_contention"], (int, float))
    assert isinstance(metrics_after["lock_wait_ms"], (int, float))
    assert isinstance(metrics_after["lock_timeouts"], (int, float))

    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))


def test_wal_append_cas_none_expected(tmp_path):
    """Test append_cas with None as expected_prev_hash"""
    wal_dir = tmp_path / "wal_cas_none"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)

    # Append first record
    wal.append({"rid": "r1", "data": "first"})

    # append_cas with None expected_prev_hash should always succeed
    success, result_hash = wal.append_cas(
        {"rid": "r2", "data": "second"}, expected_prev_hash=None
    )

    assert success
    assert result_hash is not None

    # Verify both records present
    file_content = list(wal_dir.glob("*.jsonl"))[0].read_text()
    lines = file_content.strip().split("\n")
    assert len(lines) == 2

    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))


def test_wal_verify_chain_with_missing_prev():
    """Test verify_chain with record missing _prev field"""
    import hashlib

    # Create record without _prev field
    record_data = {"rid": "test", "data": "value"}
    record_json = json.dumps(record_data, sort_keys=True)
    actual_hash = hashlib.sha256(record_json.encode()).hexdigest()

    record = {**record_data, "_hash": actual_hash}
    # Note: record has no _prev field

    # Should fail verification (missing _prev defaults to "")
    result = wal.verify_chain([record])
    assert not result


def test_wal_calculate_merkle_root_three_hashes():
    """Test merkle root with three hashes"""
    hash1 = "1" * 64
    hash2 = "2" * 64
    hash3 = "3" * 64

    root = wal.calculate_merkle_root([hash1, hash2, hash3])
    assert root is not None
    assert len(root) == 64

    # Order matters
    root_reversed = wal.calculate_merkle_root([hash3, hash2, hash1])
    assert root != root_reversed


def test_wal_calculate_merkle_root_four_hashes():
    """Test merkle root with four hashes (even, balanced tree)"""
    hashes = ["a" * 64, "b" * 64, "c" * 64, "d" * 64]

    root = wal.calculate_merkle_root(hashes)
    assert root is not None
    assert len(root) == 64


def test_wal_integration_full_cycle(tmp_path):
    """Full integration test: append, read, verify, merkle"""
    wal_dir = tmp_path / "wal_integration"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)

    # Append multiple records
    hashes = []
    for i in range(4):
        h = wal.append({"rid": f"integration-{i}", "data": f"value-{i}"})
        hashes.append(h)

    # Read last hash
    last_hash = wal.read_last_hash()
    assert last_hash == hashes[-1]

    # Read all records and verify chain
    wal_file = list(wal_dir.glob("*.jsonl"))[0]
    lines = wal_file.read_text().strip().split("\n")
    records = [json.loads(line) for line in lines]

    # Verify integrity
    integrity_ok = wal.verify_chain(records)
    assert integrity_ok

    # Calculate merkle root
    record_hashes = [r.get("_hash", "") for r in records if r.get("_hash")]
    merkle_root = wal.calculate_merkle_root(record_hashes)
    assert merkle_root is not None
    assert len(merkle_root) == 64

    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))


def test_wal_append_json_edge_cases(tmp_path):
    """Test WAL append with various JSON edge cases"""
    wal_dir = tmp_path / "wal_json_edge"
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal.set_wal_dir(wal_dir)

    # Unicode characters
    h1 = wal.append({"rid": "unicode", "data": "Привіт 世界 🚀"})
    assert h1 is not None

    # Nested structures
    h2 = wal.append(
        {
            "rid": "nested",
            "data": {"level1": {"level2": ["a", "b", "c"], "numbers": [1, 2, 3]}},
        }
    )
    assert h2 is not None

    # Empty values
    h3 = wal.append({"rid": "empty", "data": "", "list": []})
    assert h3 is not None

    # Reset
    wal.set_wal_dir(pathlib.Path("ops/wal"))
