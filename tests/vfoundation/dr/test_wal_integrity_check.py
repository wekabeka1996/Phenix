"""Tests for vfoundation.dr.wal.check_daily_wal_integrity (P11-B1 Package A)."""

from __future__ import annotations

import json
import hashlib
import pathlib
import time
from typing import Any, Dict, List

import pytest

from vfoundation.dr import wal
from vfoundation.dr.wal import check_daily_wal_integrity, WalChainIntegrityResult


@pytest.fixture(autouse=True)
def _isolated_wal(tmp_path: pathlib.Path):
    wal.set_wal_dir(tmp_path)
    wal.reset()
    yield
    wal.reset()


def _write_chained(wal_dir: pathlib.Path, records: List[Dict[str, Any]]) -> None:
    """Write records with a valid hash chain to today's WAL file."""
    today = time.strftime("%Y-%m-%d")
    path = wal_dir / f"{today}.jsonl"
    prev_hash = "0" * 64
    with path.open("a", encoding="utf-8") as f:
        for rec in records:
            payload = {**rec, "_prev": prev_hash}
            record_json = json.dumps(
                payload, sort_keys=True, ensure_ascii=False)
            record_hash = hashlib.sha256(
                record_json.encode("utf-8")).hexdigest()
            payload["_hash"] = record_hash
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            prev_hash = record_hash


def _inject_break(wal_dir: pathlib.Path, at_index: int) -> None:
    """Corrupt the _prev pointer at a specific record index to create a chain break."""
    today = time.strftime("%Y-%m-%d")
    path = wal_dir / f"{today}.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[at_index])
    record["_prev"] = "deadbeef" + "0" * 56  # wrong _prev
    lines[at_index] = json.dumps(record, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestWalChainIntegrityResult:
    def test_dataclass_fields(self) -> None:
        r = WalChainIntegrityResult(
            file_path="/tmp/wal/2026-05-10.jsonl",
            chain_ok=True,
            record_count=42,
            first_bad_index=None,
            checked_at_ms=1234567890000,
        )
        assert r.chain_ok is True
        assert r.record_count == 42
        assert r.first_bad_index is None
        assert r.checked_at_ms == 1234567890000

    def test_chain_break_fields(self) -> None:
        r = WalChainIntegrityResult(
            file_path="/tmp/wal/2026-05-10.jsonl",
            chain_ok=False,
            record_count=100,
            first_bad_index=42,
            checked_at_ms=1234567890001,
        )
        assert r.chain_ok is False
        assert r.first_bad_index == 42


class TestCheckDailyWalIntegrityEmpty:
    def test_no_file_returns_ok(self, tmp_path: pathlib.Path) -> None:
        result = check_daily_wal_integrity()
        assert isinstance(result, WalChainIntegrityResult)
        assert result.chain_ok is True
        assert result.record_count == 0
        assert result.first_bad_index is None
        assert result.checked_at_ms > 0

    def test_empty_file_returns_ok(self, tmp_path: pathlib.Path) -> None:
        today = time.strftime("%Y-%m-%d")
        (tmp_path / f"{today}.jsonl").write_text("", encoding="utf-8")
        result = check_daily_wal_integrity()
        assert result.chain_ok is True
        assert result.record_count == 0


class TestCheckDailyWalIntegrityValid:
    def test_single_record_ok(self, tmp_path: pathlib.Path) -> None:
        wal.append({"verb": "TRADE_EXECUTED", "rid": "r1"})
        result = check_daily_wal_integrity()
        assert result.chain_ok is True
        assert result.record_count == 1
        assert result.first_bad_index is None

    def test_multiple_records_ok(self, tmp_path: pathlib.Path) -> None:
        for i in range(5):
            wal.append({"verb": "EVT", "rid": f"r{i}"})
        result = check_daily_wal_integrity()
        assert result.chain_ok is True
        assert result.record_count == 5
        assert result.first_bad_index is None

    def test_file_path_populated(self, tmp_path: pathlib.Path) -> None:
        wal.append({"x": 1})
        result = check_daily_wal_integrity()
        assert str(tmp_path) in result.file_path
        assert result.file_path.endswith(".jsonl")

    def test_checked_at_ms_is_recent(self) -> None:
        wal.append({"x": 1})
        before_ms = int(time.time() * 1000)
        result = check_daily_wal_integrity()
        after_ms = int(time.time() * 1000)
        assert before_ms <= result.checked_at_ms <= after_ms + 100


class TestCheckDailyWalIntegrityBroken:
    def test_chain_break_detected_at_index_0(self, tmp_path: pathlib.Path) -> None:
        _write_chained(tmp_path, [
            {"verb": "A", "rid": "r1"},
            {"verb": "B", "rid": "r2"},
        ])
        _inject_break(tmp_path, at_index=0)
        result = check_daily_wal_integrity()
        assert result.chain_ok is False
        assert result.first_bad_index == 0
        assert result.record_count == 2

    def test_chain_break_detected_at_index_1(self, tmp_path: pathlib.Path) -> None:
        _write_chained(tmp_path, [
            {"verb": "A", "rid": "r1"},
            {"verb": "B", "rid": "r2"},
            {"verb": "C", "rid": "r3"},
        ])
        _inject_break(tmp_path, at_index=1)
        result = check_daily_wal_integrity()
        assert result.chain_ok is False
        assert result.first_bad_index == 1

    def test_valid_chain_before_break_does_not_flag_early(self, tmp_path: pathlib.Path) -> None:
        # 10 valid records then a break at index 7
        records = [{"verb": "X", "rid": f"r{i}"} for i in range(10)]
        _write_chained(tmp_path, records)
        _inject_break(tmp_path, at_index=7)
        result = check_daily_wal_integrity()
        assert result.chain_ok is False
        assert result.first_bad_index == 7
        assert result.record_count == 10

    def test_chain_break_does_not_raise(self, tmp_path: pathlib.Path) -> None:
        _write_chained(tmp_path, [{"verb": "A", "rid": "r1"}])
        _inject_break(tmp_path, at_index=0)
        # Must never raise
        result = check_daily_wal_integrity()
        assert isinstance(result, WalChainIntegrityResult)

    def test_corrupted_hash_detected(self, tmp_path: pathlib.Path) -> None:
        # Corrupt the _hash field (not _prev) of a record to simulate hash mismatch
        wal.append({"verb": "A", "rid": "r1"})
        today = time.strftime("%Y-%m-%d")
        path = tmp_path / f"{today}.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        record = json.loads(lines[0])
        record["_hash"] = "aaaa" + "0" * 60  # tampered hash
        lines[0] = json.dumps(record, ensure_ascii=False)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = check_daily_wal_integrity()
        assert result.chain_ok is False
        assert result.first_bad_index == 0
