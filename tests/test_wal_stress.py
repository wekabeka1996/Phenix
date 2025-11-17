"""Stress tests for concurrent WAL operations"""

import threading
import time
from typing import List
import tempfile
from pathlib import Path
from vfoundation.dr.wal import (
    append,
    verify_chain,
    calculate_merkle_root,
    get_lock_metrics,
    set_wal_dir,
    reset,
)


def test_wal_concurrent_appends_integrity():
    """Test that 100 concurrent threads can safely append to WAL with chain integrity"""
    with tempfile.TemporaryDirectory() as temp_dir:
        set_wal_dir(Path(temp_dir))
        try:
            num_threads = 100
            records_per_thread = 5
            results: List[bool] = []
            errors: List[str] = []

            def append_records(thread_id: int):
                try:
                    for i in range(records_per_thread):
                        record = {
                            "rid": f"thread-{thread_id}-record-{i}",
                            "op": "DEC",
                            "verb": "TEST",
                            "thread_id": thread_id,
                            "sequence": i,
                        }
                        append(record)
                    results.append(True)
                except Exception as e:
                    errors.append(f"Thread {thread_id}: {str(e)}")
                    results.append(False)

            # Start all threads simultaneously
            threads = []
            for tid in range(num_threads):
                t = threading.Thread(target=append_records, args=(tid,))
                threads.append(t)
                t.start()

            # Wait for all threads to complete
            for t in threads:
                t.join()

            # Verify results
            assert len(results) == num_threads, (
                f"Expected {num_threads} results, got {len(results)}"
            )
            assert all(results), (
                f"Some threads failed: {errors[:5]}"
            )  # Show first 5 errors if any

            # Read all records from WAL and verify chain integrity
            wal_file = Path(temp_dir) / f"{time.strftime('%Y-%m-%d')}.jsonl"
            if wal_file.exists():
                import json

                records = []
                with open(wal_file, "r") as f:
                    for line in f:
                        if line.strip():
                            records.append(json.loads(line))

                # Verify we have all expected records
                expected_total = num_threads * records_per_thread
                assert len(records) == expected_total, (
                    f"Expected {expected_total} records, found {len(records)}"
                )

                # Verify chain integrity
                chain_ok = verify_chain(records)
                assert chain_ok, "WAL chain integrity check failed after concurrent writes"

                # Verify merkle root can be calculated
                hashes = [r["_hash"] for r in records if "_hash" in r]
                merkle_root = calculate_merkle_root(hashes)
                assert merkle_root, "Failed to calculate merkle root"
                assert len(merkle_root) == 64, (
                    f"Invalid merkle root length: {len(merkle_root)}"
                )

            # Check lock metrics
            lock_metrics = get_lock_metrics()
            print(f"\nLock metrics after {num_threads} threads:")
            print(f"  lock_contention: {lock_metrics['lock_contention']}")
            print(f"  lock_wait_ms: {lock_metrics['lock_wait_ms']:.2f}ms")
            print(f"  lock_timeouts: {lock_metrics['lock_timeouts']}")

            # With 100 threads, we expect some contention
            assert lock_metrics["lock_contention"] > 0, (
                "Expected some lock contention with 100 threads"
            )
            assert lock_metrics["lock_timeouts"] == 0, "No lock timeouts should occur"
        finally:
            reset()


def test_wal_append_cas_optimistic_concurrency():
    """Test append_cas() with optimistic concurrency control"""
    from vfoundation.dr.wal import append_cas, read_last_hash

    with tempfile.TemporaryDirectory() as temp_dir:
        set_wal_dir(Path(temp_dir))

        try:
            # Append first record
            record1 = {"rid": "r1", "op": "DEC", "verb": "FIRST"}
            append(record1)

            # Read last hash
            last_hash = read_last_hash()
            assert last_hash, "Failed to read last hash"

            # Two threads try to append with same expected_prev_hash
            # Only one should succeed
            success_count = [0]
            failure_count = [0]

            def try_cas_append(thread_id: int):
                try:
                    record = {
                        "rid": f"r{thread_id}",
                        "op": "DEC",
                        "verb": f"CAS-{thread_id}",
                    }
                    success, hash_val = append_cas(record, last_hash)
                    if success:
                        success_count[0] += 1
                    else:
                        failure_count[0] += 1
                except Exception as e:
                    print(f"Thread {thread_id} error: {e}")
                    failure_count[0] += 1

            threads = []
            for i in range(2, 4):  # 2 threads
                t = threading.Thread(target=try_cas_append, args=(i,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            # Exactly one should succeed
            assert success_count[0] == 1, f"Expected 1 success, got {success_count[0]}"
            assert failure_count[0] == 1, f"Expected 1 failure, got {failure_count[0]}"
        finally:
            reset()


def test_wal_lock_timeout_behavior():
    """Test that lock timeout returns False instead of hanging (Unix only)"""
    import sys
    import pytest

    if sys.platform == "win32":
        pytest.skip("Test requires Unix-like file locking (fcntl)")

    with tempfile.TemporaryDirectory() as temp_dir:
        set_wal_dir(Path(temp_dir))

        try:
            import fcntl
            from vfoundation.dr.wal import _get_wal_file_path

            # Manually acquire exclusive lock on WAL file
            wal_path = _get_wal_file_path()
            wal_path.parent.mkdir(parents=True, exist_ok=True)

            with open(wal_path, "a") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                # Try to append with short timeout - should fail gracefully
                record = {"rid": "timeout-test", "op": "DEC", "verb": "TEST"}

                # This should timeout and return False instead of hanging
                start = time.time()
                result = append(record, lock_timeout_s=0.1)
                elapsed = time.time() - start

                assert result is None, "Expected append to fail with timeout"
                assert elapsed < 0.5, f"Timeout took too long: {elapsed}s"

                # Verify lock_timeouts metric incremented
                metrics = get_lock_metrics()
                assert metrics["lock_timeouts"] >= 1, "Expected lock timeout to be recorded"
        finally:
            reset()


def test_wal_high_throughput():
    """Test WAL can handle high-throughput writes (performance benchmark)"""
    with tempfile.TemporaryDirectory() as temp_dir:
        set_wal_dir(Path(temp_dir))
        num_records = 1000
        start_time = time.time()

        try:
            for i in range(num_records):
                record = {
                    "rid": f"perf-{i}",
                    "op": "DEC",
                    "verb": "BENCHMARK",
                    "sequence": i,
                }
                append(record)
        finally:
            reset()

        elapsed = time.time() - start_time
        throughput = num_records / elapsed

        print("\nWAL Performance:")
        print(f"  {num_records} records in {elapsed:.2f}s")
        print(f"  Throughput: {throughput:.0f} records/sec")

        # Should handle at least 30 records/sec (reasonable for file-based WAL with integrity guarantees)
        assert throughput > 30, f"Throughput too low: {throughput:.0f} records/sec"

        # Verify all records written correctly
        wal_file = Path(temp_dir) / f"{time.strftime('%Y-%m-%d')}.jsonl"
        import json

        records = []
        with open(wal_file, "r") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))

        assert len(records) == num_records, (
            f"Expected {num_records} records, found {len(records)}"
        )

        # Verify chain integrity
        assert verify_chain(records), (
            "Chain integrity failed after high-throughput writes"
        )
