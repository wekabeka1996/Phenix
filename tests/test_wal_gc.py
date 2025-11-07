import pytest
import time
from pathlib import Path
from unittest.mock import patch
from vfoundation.dr.wal_gc import WALGarbageCollector


@pytest.fixture
def temp_wal_dir(tmp_path):
    """Create a temporary WAL directory for testing."""
    wal_dir = tmp_path / "wal"
    wal_dir.mkdir()
    return wal_dir


@pytest.fixture
def gc_instance(temp_wal_dir):
    """Create a WALGarbageCollector instance for testing."""
    return WALGarbageCollector(
        wal_dir=temp_wal_dir,
        retention_days=7,
        max_file_size_mb=1,  # Small for testing
        logger=None
    )


def test_cleanup_old_wals(gc_instance, temp_wal_dir):
    """Test that old WAL files are cleaned up."""
    import os

    # Create a fresh WAL file (today)
    today_file = temp_wal_dir / f"{time.strftime('%Y-%m-%d')}.jsonl"
    today_file.write_text('{"test": "data"}')

    # Create an old WAL file (8 days ago)
    old_date = time.strftime(
        '%Y-%m-%d', time.localtime(time.time() - 8 * 86400))
    old_file = temp_wal_dir / f"{old_date}.jsonl"
    old_file.write_text('{"old": "data"}')

    # ✅ ВИПРАВКА: Установити mtime файлу на 8 днів тому
    old_mtime = time.time() - (8 * 86400)
    os.utime(old_file, (old_mtime, old_mtime))

    # Run cleanup
    removed = gc_instance.cleanup_old_wals()

    # Check results
    assert removed == 1
    assert not old_file.exists()
    assert today_file.exists()


def test_rotate_current_wal(gc_instance, temp_wal_dir):
    """Test WAL file rotation when size exceeds limit."""
    # Create a current WAL file that's too large
    today_file = temp_wal_dir / f"{time.strftime('%Y-%m-%d')}.jsonl"
    large_content = "x" * (2 * 1024 * 1024)  # 2MB content (exceeds 1MB limit)
    today_file.write_text(large_content)

    # Run rotation
    rotated = gc_instance.rotate_current_wal()

    # Check results
    assert rotated is True, f"Expected rotation to succeed, but got {rotated}"
    assert not today_file.exists(), "Current WAL file should be rotated away"

    # Should have created a rotated file with timestamp
    rotated_files = list(temp_wal_dir.glob(
        f"{time.strftime('%Y-%m-%d')}*.jsonl"))
    assert len(rotated_files) == 1
    assert rotated_files[0].name != f"{time.strftime('%Y-%m-%d')}.jsonl"


def test_get_stats(gc_instance, temp_wal_dir):
    """Test getting WAL directory statistics."""
    # Create some test files
    file1 = temp_wal_dir / "test1.jsonl"
    file1.write_text("x" * 1000)  # 1000 bytes

    file2 = temp_wal_dir / "test2.jsonl"
    file2.write_text("x" * 2000)  # 2000 bytes

    stats = gc_instance.get_stats()

    assert stats['file_count'] == 2
    assert abs(stats['total_size_mb'] - 0.0029) < 0.001  # ~3KB


def test_gc_thread_lifecycle(gc_instance):
    """Test starting and stopping the GC thread."""
    # Start GC thread
    thread = gc_instance.start_background_gc(interval_sec=1)

    assert thread.is_alive()

    # Stop GC
    gc_instance.stop()
    thread.join(timeout=2)

    assert not thread.is_alive()


def test_no_files_to_cleanup(gc_instance):
    """Test cleanup when no files exist."""
    removed = gc_instance.cleanup_old_wals()
    assert removed == 0


def test_no_rotation_needed(gc_instance, temp_wal_dir):
    """Test rotation when file is small."""
    today_file = temp_wal_dir / f"{time.strftime('%Y-%m-%d')}.jsonl"
    today_file.write_text("small content")

    rotated = gc_instance.rotate_current_wal()
    assert rotated is False
    assert today_file.exists()
