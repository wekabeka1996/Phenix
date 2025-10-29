"""Additional tests for wal.py to improve coverage to 90%"""

import json


from vfoundation.dr.wal import (
    append,
    append_cas,
    calculate_merkle_root,
    get_lock_metrics,
    read_all,
    read_last_hash,
    reset,
    set_wal_dir,
    verify_chain,
)


class TestWalCoverage:
    """Tests to improve wal.py coverage from 71% to 90%"""

    def test_read_last_hash_file_reading_path(self, tmp_path):
        """Test read_last_hash when cache miss requires file reading"""
        # Setup custom WAL directory
        wal_dir = tmp_path / "test_wal"
        set_wal_dir(wal_dir)

        # Create a WAL file with today's date
        import time
        today = time.strftime("%Y-%m-%d")
        wal_file = wal_dir / f"{today}.jsonl"
        wal_dir.mkdir(parents=True, exist_ok=True)

        records = [
            {"data": "first", "_prev": "0" * 64, "_hash": "hash1"},
            {"data": "second", "_prev": "hash1", "_hash": "hash2"},
        ]

        with wal_file.open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

        # Clear cache to force file reading
        reset()

        # Test reading last hash from file
        result = read_last_hash()
        assert result == "hash2"

    def test_read_all_nonexistent_file(self, tmp_path):
        """Test read_all when WAL file doesn't exist"""
        wal_dir = tmp_path / "test_wal"
        set_wal_dir(wal_dir)

        # Don't create the file
        result = read_all()
        assert result == []

    def test_read_all_malformed_json(self, tmp_path):
        """Test read_all with malformed JSON lines"""
        wal_dir = tmp_path / "test_wal"
        set_wal_dir(wal_dir)

        # Create a WAL file with today's date
        import time
        today = time.strftime("%Y-%m-%d")
        wal_file = wal_dir / f"{today}.jsonl"
        wal_dir.mkdir(parents=True, exist_ok=True)

        with wal_file.open("w", encoding="utf-8") as f:
            f.write('{"valid": "record1"}\n')
            f.write("not json\n")
            f.write('{"valid": "record2"}\n')

        result = read_all()
        # Should skip malformed lines and return valid records
        assert len(result) == 2
        assert result[0]["valid"] == "record1"
        assert result[1]["valid"] == "record2"

    def test_append_timeout_error(self, tmp_path, monkeypatch):
        """Test append when lock timeout occurs"""
        wal_dir = tmp_path / "test_wal"
        set_wal_dir(wal_dir)

        # Mock _file_lock to raise TimeoutError
        def mock_file_lock(*args, **kwargs):
            raise TimeoutError("Lock timeout")

        # Import the wal module to patch it
        from vfoundation.dr import wal as wal_module
        monkeypatch.setattr(wal_module, "_file_lock", mock_file_lock)

        result = append({"test": "data"})
        assert result is None  # Should return None on timeout

    def test_append_cas_empty_file_hash_calculation(self, tmp_path):
        """Test append_cas hash calculation for empty file"""
        wal_dir = tmp_path / "test_wal"
        set_wal_dir(wal_dir)

        # Ensure file doesn't exist initially
        success, hash_val = append_cas({"test": "data"})
        assert success is True
        assert hash_val is not None
        assert len(hash_val) == 64  # SHA256 hex length

    def test_append_cas_with_prev_hash_mismatch(self, tmp_path):
        """Test append_cas with expected prev hash that doesn't match"""
        wal_dir = tmp_path / "test_wal"
        set_wal_dir(wal_dir)

        # First append to establish a hash
        success1, hash1 = append_cas({"first": "record"})
        assert success1 is True

        # Try to append with wrong expected hash
        success2, hash2 = append_cas({"second": "record"}, expected_prev_hash="wronghash")
        assert success2 is False
        assert hash2 is None

    def test_get_lock_metrics_functionality(self):
        """Test get_lock_metrics returns expected structure"""
        reset()  # Reset metrics

        metrics = get_lock_metrics()
        expected_keys = {"lock_contention", "lock_wait_ms", "lock_timeouts"}

        assert set(metrics.keys()) == expected_keys
        assert all(isinstance(v, (int, float)) for v in metrics.values())

    def test_calculate_merkle_root_edge_cases(self):
        """Test calculate_merkle_root with various inputs"""
        # Empty list
        assert calculate_merkle_root([]) == "0" * 64

        # Single hash
        single_hash = "a" * 64
        assert calculate_merkle_root([single_hash]) == single_hash

        # Multiple hashes
        hashes = ["a" * 64, "b" * 64, "c" * 64]
        result = calculate_merkle_root(hashes)
        assert len(result) == 64
        assert result != "0" * 64

    def test_verify_chain_empty_list(self):
        """Test verify_chain with empty list"""
        assert verify_chain([]) is True

    def test_verify_chain_broken_hash_chain(self):
        """Test verify_chain detects broken hash chain"""
        # Create records with broken _prev link
        record1 = {"_prev": "0" * 64, "data": "first", "_hash": "hash1"}
        record2 = {"_prev": "wrong_prev_hash", "data": "second", "_hash": "hash2"}

        assert verify_chain([record1, record2]) is False

    def test_wal_directory_creation(self, tmp_path):
        """Test that WAL directory is created automatically"""
        wal_dir = tmp_path / "new_wal_dir"
        set_wal_dir(wal_dir)

        # Trigger directory creation by attempting append
        append({"test": "data"})

        assert wal_dir.exists()
        assert wal_dir.is_dir()

    def test_hash_cache_invalidation_on_directory_change(self, tmp_path):
        """Test that hash cache is cleared when WAL directory changes"""
        # Set initial directory and create cache
        wal_dir1 = tmp_path / "wal1"
        set_wal_dir(wal_dir1)
        append({"test": "data1"})
        hash1 = read_last_hash()

        # Change directory
        wal_dir2 = tmp_path / "wal2"
        set_wal_dir(wal_dir2)

        # Cache should be invalidated
        hash2 = read_last_hash()
        assert hash2 != hash1  # Should be None or different