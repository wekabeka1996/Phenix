"""Tests for vfoundation.dr.wal — WAL append, CAS, chain verify, merkle, metrics."""

from __future__ import annotations

import json
import multiprocessing as mp
import pathlib
import threading

import pytest

from vfoundation.dr import wal


def _multiprocess_append_worker(wal_dir: str, worker_id: int, count: int) -> None:
    wal.set_wal_dir(pathlib.Path(wal_dir))
    wal.reset()
    for index in range(count):
        record_hash = wal.append(
            {
                "op": "EVT",
                "verb": "MP_APPEND",
                "rid": f"worker-{worker_id}",
                "worker_id": worker_id,
                "seq": index,
            },
            lock_timeout_s=10.0,
        )
        if record_hash is None:
            raise RuntimeError(
                f"append returned None for worker={worker_id} seq={index}"
            )


@pytest.fixture(autouse=True)
def _isolated_wal(tmp_path: pathlib.Path):
    """Give each test an isolated WAL directory and reset state."""
    wal.set_wal_dir(tmp_path)
    wal.reset()
    yield
    wal.reset()


# ── append ────────────────────────────────────────────────────────────────


class TestAppend:
    def test_append_returns_hash(self) -> None:
        h = wal.append({"op": "EVT", "verb": "EVAL", "rid": "r1"})
        assert h is not None and len(h) == 64

    def test_append_creates_file(self, tmp_path: pathlib.Path) -> None:
        wal.append({"x": 1})
        files = list(tmp_path.glob("*.jsonl"))
        assert len(files) == 1

    def test_appended_record_has_hash_and_prev(self, tmp_path: pathlib.Path) -> None:
        wal.append({"x": 1})
        records = wal.read_all()
        assert len(records) == 1
        assert "_hash" in records[0]
        assert "_prev" in records[0]

    def test_two_appends_chain(self) -> None:
        h1 = wal.append({"a": 1})
        h2 = wal.append({"b": 2})
        records = wal.read_all()
        assert records[1]["_prev"] == h1
        assert records[1]["_hash"] == h2

    def test_malformed_tail_returns_none(self) -> None:
        path = wal._get_wal_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("NOT JSON\n", encoding="utf-8")

        result = wal.append({"op": "EVT", "verb": "AFTER_BAD_TAIL"})

        assert result is None


# ── read_all ──────────────────────────────────────────────────────────────


class TestReadAll:
    def test_empty_wal_returns_empty(self) -> None:
        assert wal.read_all() == []

    def test_reads_all_records(self) -> None:
        for i in range(5):
            wal.append({"i": i})
        assert len(wal.read_all()) == 5

    def test_skips_malformed_lines(self, tmp_path: pathlib.Path) -> None:
        wal.append({"ok": True})
        # Inject a bad line
        path = wal._get_wal_file_path()
        with path.open("a", encoding="utf-8") as f:
            f.write("NOT JSON\n")
        records = wal.read_all()
        assert len(records) == 1  # only the valid record


# ── read_last_hash ────────────────────────────────────────────────────────


class TestReadLastHash:
    def test_none_on_empty(self) -> None:
        assert wal.read_last_hash() is None

    def test_returns_last_hash(self) -> None:
        wal.append({"a": 1})
        h = wal.append({"b": 2})
        assert wal.read_last_hash() == h

    def test_cache_cleared_on_set_wal_dir(self, tmp_path: pathlib.Path) -> None:
        wal.append({"x": 1})
        assert wal.read_last_hash() is not None
        # Switch to new dir → cache cleared
        new_dir = tmp_path / "new_wal"
        new_dir.mkdir()
        wal.set_wal_dir(new_dir)
        assert wal.read_last_hash() is None


# ── append_cas ────────────────────────────────────────────────────────────


class TestAppendCas:
    def test_cas_none_always_succeeds(self) -> None:
        ok, h = wal.append_cas({"x": 1}, expected_prev_hash=None)
        assert ok is True
        assert h is not None

    def test_cas_matching_hash_succeeds(self) -> None:
        h1 = wal.append({"a": 1})
        ok, h2 = wal.append_cas({"b": 2}, expected_prev_hash=h1)
        assert ok is True
        assert h2 is not None

    def test_cas_wrong_hash_fails(self) -> None:
        wal.append({"a": 1})
        ok, h = wal.append_cas({"b": 2}, expected_prev_hash="bad_hash")
        assert ok is False
        assert h is None

    def test_cas_empty_file_expects_zeros(self) -> None:
        ok, h = wal.append_cas({"first": True}, expected_prev_hash="0" * 64)
        assert ok is True
        assert h is not None

    def test_cas_malformed_tail_fails(self) -> None:
        path = wal._get_wal_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("NOT JSON\n", encoding="utf-8")

        ok, h = wal.append_cas({"x": 1}, expected_prev_hash="0" * 64)

        assert ok is False
        assert h is None


# ── verify_chain ──────────────────────────────────────────────────────────


class TestVerifyChain:
    def test_empty_chain_valid(self) -> None:
        assert wal.verify_chain([]) is True

    def test_valid_chain(self) -> None:
        for i in range(5):
            wal.append({"i": i})
        records = wal.read_all()
        assert wal.verify_chain(records) is True

    def test_tampered_hash_detected(self) -> None:
        for i in range(3):
            wal.append({"i": i})
        records = wal.read_all()
        records[1]["_hash"] = "bad" + records[1]["_hash"][3:]
        assert wal.verify_chain(records) is False

    def test_tampered_prev_detected(self) -> None:
        for i in range(3):
            wal.append({"i": i})
        records = wal.read_all()
        records[1]["_prev"] = "wrong"
        assert wal.verify_chain(records) is False

    def test_tampered_payload_detected(self) -> None:
        for i in range(3):
            wal.append({"i": i})
        records = wal.read_all()
        records[1]["i"] = 999  # modify data — hash won't match
        assert wal.verify_chain(records) is False


# ── calculate_merkle_root ─────────────────────────────────────────────────


class TestMerkleRoot:
    def test_empty_returns_zeros(self) -> None:
        assert wal.calculate_merkle_root([]) == "0" * 64

    def test_single_hash_returned(self) -> None:
        assert wal.calculate_merkle_root(["abc"]) == "abc"

    def test_two_hashes_combined(self) -> None:
        import hashlib
        h1, h2 = "a" * 64, "b" * 64
        expected = hashlib.sha256((h1 + h2).encode()).hexdigest()
        assert wal.calculate_merkle_root([h1, h2]) == expected

    def test_odd_hashes_duplicates_last(self) -> None:
        import hashlib
        h1, h2, h3 = "a" * 64, "b" * 64, "c" * 64
        # Level 1: combine(h1,h2), combine(h3,h3)
        left = hashlib.sha256((h1 + h2).encode()).hexdigest()
        right = hashlib.sha256((h3 + h3).encode()).hexdigest()
        root = hashlib.sha256((left + right).encode()).hexdigest()
        assert wal.calculate_merkle_root([h1, h2, h3]) == root

    def test_deterministic(self) -> None:
        hashes = ["h1", "h2", "h3", "h4"]
        r1 = wal.calculate_merkle_root(hashes)
        r2 = wal.calculate_merkle_root(hashes)
        assert r1 == r2


# ── read_by_rid ───────────────────────────────────────────────────────────


class TestReadByRid:
    def test_empty_returns_no_events(self) -> None:
        events, chain, ok = wal.read_by_rid("nonexistent")
        assert events == []
        assert chain == []
        assert ok is True  # vacuously true

    def test_filters_by_rid(self) -> None:
        wal.append({"rid": "r1", "why": "reason-a"})
        wal.append({"rid": "r2", "why": "reason-b"})
        wal.append({"rid": "r1", "why": "reason-c"})
        events, chain, ok = wal.read_by_rid("r1")
        assert len(events) == 2
        assert ok is True

    def test_why_chain_collected(self) -> None:
        wal.append({"rid": "r1", "pld": {"why": "step1"}, "ts": 1})
        wal.append({"rid": "r1", "pld": {"why": "step2"}, "ts": 2})
        events, chain, _ = wal.read_by_rid("r1")
        assert "step1" in chain
        assert "step2" in chain

    def test_integrity_check_fails_on_tampered(self, tmp_path: pathlib.Path) -> None:
        wal.append({"rid": "r1", "ts": 1})
        # Tamper with file directly
        path = wal._get_wal_file_path()
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        record = json.loads(lines[0])
        record["_hash"] = "tampered"
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        events, chain, ok = wal.read_by_rid("r1")
        assert ok is False


# ── Lock metrics ──────────────────────────────────────────────────────────


class TestLockMetrics:
    def test_initial_metrics_zero(self) -> None:
        m = wal.get_lock_metrics()
        assert m["lock_contention"] == 0
        assert m["lock_wait_ms"] == 0.0
        assert m["lock_timeouts"] == 0

    def test_reset_clears_metrics(self) -> None:
        wal._record_lock_wait(5.0)
        wal.reset()
        m = wal.get_lock_metrics()
        assert m["lock_contention"] == 0

    def test_lock_wait_accumulates(self) -> None:
        wal._record_lock_wait(1.0)
        wal._record_lock_wait(2.0)
        m = wal.get_lock_metrics()
        assert m["lock_contention"] == 2
        assert m["lock_wait_ms"] == 3.0


class TestMultiProcessAppend:
    def test_multi_process_append_preserves_chain_integrity(self, tmp_path: pathlib.Path) -> None:
        wal_dir = tmp_path / "wal_mp"
        wal_dir.mkdir()
        wal.set_wal_dir(wal_dir)
        wal.reset()

        ctx = mp.get_context("spawn")
        process_count = 3
        records_per_process = 20
        processes = [
            ctx.Process(
                target=_multiprocess_append_worker,
                args=(str(wal_dir), worker_id, records_per_process),
            )
            for worker_id in range(process_count)
        ]

        for process in processes:
            process.start()
        for process in processes:
            process.join()

        exit_codes = [process.exitcode for process in processes]
        assert exit_codes == [0, 0, 0]

        records = wal.read_all()
        assert len(records) == process_count * records_per_process
        assert all("_prev" in record and "_hash" in record for record in records)
        assert wal.verify_chain(records) is True


# ── _calculate_record_hash ────────────────────────────────────────────────


class TestCalculateRecordHash:
    def test_deterministic(self) -> None:
        record = {"op": "EVT", "verb": "EVAL"}
        h1 = wal._calculate_record_hash(record)
        h2 = wal._calculate_record_hash(record)
        assert h1 == h2

    def test_different_records_different_hash(self) -> None:
        h1 = wal._calculate_record_hash({"a": 1})
        h2 = wal._calculate_record_hash({"a": 2})
        assert h1 != h2

    def test_key_order_independent(self) -> None:
        """sort_keys=True makes it canonical."""
        h1 = wal._calculate_record_hash({"a": 1, "b": 2})
        h2 = wal._calculate_record_hash({"b": 2, "a": 1})
        assert h1 == h2
