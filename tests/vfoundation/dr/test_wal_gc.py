"""Tests for vfoundation.dr.wal_gc — WALGarbageCollector."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from vfoundation.dr.wal_gc import WALGarbageCollector


@pytest.fixture
def wal_dir(tmp_path: Path) -> Path:
    """Create a temporary WAL directory with sample files."""
    return tmp_path


class TestCleanupOldWals:
    def test_removes_old_files(self, wal_dir: Path) -> None:
        gc = WALGarbageCollector(wal_dir, retention_days=1)
        old_file = wal_dir / "2020-01-01.jsonl"
        old_file.write_text('{"old": true}\n')
        # Backdate mtime to 10 days ago
        import os
        old_ts = time.time() - 86400 * 10
        os.utime(old_file, (old_ts, old_ts))

        removed = gc.cleanup_old_wals()
        assert removed == 1
        assert not old_file.exists()

    def test_keeps_recent_files(self, wal_dir: Path) -> None:
        gc = WALGarbageCollector(wal_dir, retention_days=7)
        recent = wal_dir / "2099-12-31.jsonl"
        recent.write_text('{"new": true}\n')
        removed = gc.cleanup_old_wals()
        assert removed == 0
        assert recent.exists()

    def test_keeps_today_file(self, wal_dir: Path) -> None:
        gc = WALGarbageCollector(wal_dir, retention_days=0)
        today = time.strftime("%Y-%m-%d")
        today_file = wal_dir / f"{today}.jsonl"
        today_file.write_text('{"today": true}\n')
        removed = gc.cleanup_old_wals()
        assert removed == 0


class TestRotateCurrentWal:
    def test_rotates_oversized(self, wal_dir: Path) -> None:
        gc = WALGarbageCollector(wal_dir, max_file_size_mb=0)  # 0 MB → always rotate
        today = time.strftime("%Y-%m-%d")
        today_file = wal_dir / f"{today}.jsonl"
        today_file.write_text("x" * 100)
        result = gc.rotate_current_wal()
        assert result is True
        assert not today_file.exists()
        # Rotated file should exist
        rotated = list(wal_dir.glob(f"{today}_*.jsonl"))
        assert len(rotated) == 1

    def test_no_rotation_needed(self, wal_dir: Path) -> None:
        gc = WALGarbageCollector(wal_dir, max_file_size_mb=100)
        today = time.strftime("%Y-%m-%d")
        today_file = wal_dir / f"{today}.jsonl"
        today_file.write_text("x")
        result = gc.rotate_current_wal()
        assert result is False

    def test_no_current_wal(self, wal_dir: Path) -> None:
        gc = WALGarbageCollector(wal_dir)
        assert gc.rotate_current_wal() is False


class TestGetStats:
    def test_empty_dir(self, wal_dir: Path) -> None:
        gc = WALGarbageCollector(wal_dir)
        stats = gc.get_stats()
        assert stats["file_count"] == 0
        assert stats["total_size_mb"] == 0.0

    def test_with_files(self, wal_dir: Path) -> None:
        gc = WALGarbageCollector(wal_dir)
        (wal_dir / "a.jsonl").write_text("x" * 1024)
        (wal_dir / "b.jsonl").write_text("y" * 1024)
        stats = gc.get_stats()
        assert stats["file_count"] == 2
        assert stats["total_size_mb"] > 0


class TestStopEvent:
    def test_stop(self, wal_dir: Path) -> None:
        gc = WALGarbageCollector(wal_dir)
        gc.stop()
        assert gc._stop_event.is_set()
