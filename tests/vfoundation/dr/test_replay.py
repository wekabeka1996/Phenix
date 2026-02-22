"""Tests for vfoundation.dr.replay — Phase 1.11."""
from __future__ import annotations

import json
import pathlib
import time
from typing import Any, Dict, List

import pytest

from vfoundation.dr import wal, replay


@pytest.fixture()
def tmp_wal(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """Redirect WAL_DIR and replay's WAL_DIR reference to a temp directory."""
    wal_dir = tmp_path / "wal"
    wal_dir.mkdir()
    wal.set_wal_dir(wal_dir)
    monkeypatch.setattr(replay.wal, "WAL_DIR", wal_dir)
    return wal_dir


def _write_chained_records(
    wal_dir: pathlib.Path, records: List[Dict[str, Any]]
) -> None:
    """Write records with proper hash-chain to a JSONL file."""
    today = time.strftime("%Y-%m-%d")
    path = wal_dir / f"{today}.jsonl"
    prev_hash = "0" * 64
    with path.open("a", encoding="utf-8") as f:
        for rec in records:
            payload = {**rec, "_prev": prev_hash}
            record_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            import hashlib
            record_hash = hashlib.sha256(record_json.encode("utf-8")).hexdigest()
            payload["_hash"] = record_hash
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            prev_hash = record_hash


# ─── replay_for_rid ──────────────────────────────────────────────────

class TestReplayForRid:
    def test_returns_events_for_matching_rid(self, tmp_wal: pathlib.Path) -> None:
        records = [
            {"rid": "r1", "op": "CMD", "verb": "OPEN", "ts": 1000},
            {"rid": "r2", "op": "EVT", "verb": "FILLED", "ts": 2000},
            {"rid": "r1", "op": "EVT", "verb": "PLACED", "ts": 3000},
        ]
        _write_chained_records(tmp_wal, records)

        collected: List[Dict[str, Any]] = []
        result = replay.replay_for_rid("r1", lambda e: collected.append(e))
        assert len(result) == 2
        assert all(e["rid"] == "r1" for e in result)
        assert len(collected) == 2

    def test_returns_empty_for_unknown_rid(self, tmp_wal: pathlib.Path) -> None:
        _write_chained_records(tmp_wal, [{"rid": "x", "op": "EVT", "verb": "OK", "ts": 1}])
        result = replay.replay_for_rid("missing", lambda e: None)
        assert result == []

    def test_returns_empty_when_no_wal_dir(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        no_dir = tmp_path / "nonexistent"
        monkeypatch.setattr(replay.wal, "WAL_DIR", no_dir)
        result = replay.replay_for_rid("r1", lambda e: None)
        assert result == []


# ─── replay_for_rid_with_integrity ───────────────────────────────────

class TestReplayWithIntegrity:
    def test_valid_chain_returns_true(self, tmp_wal: pathlib.Path) -> None:
        records = [
            {"rid": "r1", "op": "CMD", "verb": "OPEN", "ts": 1},
            {"rid": "r1", "op": "EVT", "verb": "ACK", "ts": 2},
        ]
        _write_chained_records(tmp_wal, records)
        events, ok, merkle = replay.replay_for_rid_with_integrity("r1", lambda e: None)
        assert ok is True
        assert len(events) == 2
        assert len(merkle) == 64  # sha256 hex

    def test_tampered_hash_returns_false(self, tmp_wal: pathlib.Path) -> None:
        records = [
            {"rid": "r1", "op": "CMD", "verb": "OPEN", "ts": 1},
            {"rid": "r1", "op": "EVT", "verb": "ACK", "ts": 2},
        ]
        _write_chained_records(tmp_wal, records)

        # Tamper with the hash of the second record
        today = time.strftime("%Y-%m-%d")
        path = tmp_wal / f"{today}.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        obj = json.loads(lines[1])
        obj["_hash"] = "f" * 64  # corrupt
        lines[1] = json.dumps(obj, ensure_ascii=False)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        _, ok, _ = replay.replay_for_rid_with_integrity("r1", lambda e: None)
        assert ok is False

    def test_empty_wal_is_valid(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        empty = tmp_path / "empty_wal"
        empty.mkdir()
        monkeypatch.setattr(replay.wal, "WAL_DIR", empty)
        events, ok, merkle = replay.replay_for_rid_with_integrity("any", lambda e: None)
        assert events == []
        assert ok is True
        assert merkle == "0" * 64


# ─── replay_from_wal ────────────────────────────────────────────────

class TestReplayFromWal:
    def test_replays_all_events(self, tmp_wal: pathlib.Path) -> None:
        _write_chained_records(tmp_wal, [
            {"rid": "a", "op": "EVT", "verb": "X", "ts": 100},
            {"rid": "b", "op": "EVT", "verb": "Y", "ts": 200},
        ])
        collected: List[Dict[str, Any]] = []
        replay.replay_from_wal(lambda e: collected.append(e))
        assert len(collected) == 2

    def test_from_ts_filter(self, tmp_wal: pathlib.Path) -> None:
        _write_chained_records(tmp_wal, [
            {"rid": "a", "op": "EVT", "verb": "X", "ts": 100},
            {"rid": "b", "op": "EVT", "verb": "Y", "ts": 200},
            {"rid": "c", "op": "EVT", "verb": "Z", "ts": 300},
        ])
        collected: List[Dict[str, Any]] = []
        replay.replay_from_wal(lambda e: collected.append(e), from_ts=200)
        assert len(collected) == 2
        assert all(e["ts"] >= 200 for e in collected)

    def test_no_wal_dir_does_nothing(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(replay.wal, "WAL_DIR", tmp_path / "nope")
        collected: List[Dict[str, Any]] = []
        replay.replay_from_wal(lambda e: collected.append(e))
        assert collected == []
