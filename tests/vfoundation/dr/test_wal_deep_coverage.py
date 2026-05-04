import json
import os
import time
import sys
from pathlib import Path
from typing import Generator

import pytest
from unittest.mock import MagicMock, patch

from vfoundation.dr import wal

@pytest.fixture
def temp_wal_dir(tmp_path) -> Generator[Path, None, None]:
    old_dir = wal.WAL_DIR
    new_dir = tmp_path / "wal"
    wal.set_wal_dir(new_dir)
    wal.reset()
    yield new_dir
    wal.set_wal_dir(old_dir)

def test_wal_append_with_simulated_fcntl_lock(temp_wal_dir):
    """Test WAL append logic assuming fcntl is present and works (Unix path)."""
    mock_fcntl = MagicMock()
    mock_fcntl.LOCK_EX = 1
    mock_fcntl.LOCK_NB = 2
    mock_fcntl.LOCK_UN = 4
    
    # We need to patch sys.platform to NOT be win32, and fcntl to be present, and LOCK_AVAILABLE to be True
    with patch("vfoundation.dr.wal.fcntl", mock_fcntl), \
         patch("vfoundation.dr.wal.LOCK_AVAILABLE", True), \
         patch("sys.platform", "linux"):
        
        record = {"event": "TEST", "ts": 123}
        record_hash = wal.append(record)
        
        assert record_hash is not None
        # Verify flock was called
        assert mock_fcntl.flock.call_count >= 2

def test_wal_append_lock_timeout_unix(temp_wal_dir):
    """Test WAL append failure when lock cannot be acquired (Unix path)."""
    mock_fcntl = MagicMock()
    mock_fcntl.LOCK_EX = 1
    mock_fcntl.LOCK_NB = 2
    mock_fcntl.flock.side_effect = IOError("Locked")
    
    with patch("vfoundation.dr.wal.fcntl", mock_fcntl), \
         patch("vfoundation.dr.wal.LOCK_AVAILABLE", True), \
         patch("sys.platform", "linux"), \
         patch("time.time", side_effect=[100.0, 100.1, 105.0]): 
        
        record = {"event": "TIMEOUT_TEST"}
        res = wal.append(record, lock_timeout_s=1.0)
        assert res is None

def test_wal_recovery_with_corrupted_lines(temp_wal_dir):
    """Test recovery logic when WAL contains invalid JSON lines."""
    # Note: read_all takes no args, it reads from WAL_DIR
    wal_path = wal._wal_file_for_today()
    wal_path.parent.mkdir(parents=True, exist_ok=True)
    
    valid_record = {"rid": "r1", "op": "EVT"}
    corrupt_line = "THIS IS NOT JSON!!!!"
    
    with open(wal_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(valid_record) + "\n")
        f.write(corrupt_line + "\n")
        f.write(json.dumps(valid_record) + "\n")
        
    # Act: Recover
    recovered = wal.read_all()
    
    # Assert: only valid records recovered
    assert len(recovered) == 2
    assert recovered[0]["rid"] == "r1"

def test_wal_io_error_on_append(temp_wal_dir):
    """Test handling of unexpected I/O errors during write."""
    with patch("pathlib.Path.open", side_effect=PermissionError("Access denied")):
        with pytest.raises(PermissionError):
            wal.append({"data": 1})

def test_wal_reset_clears_metrics():
    """Test wal.reset() coverage."""
    wal._record_lock_timeout()
    assert wal.get_lock_metrics()["lock_timeouts"] > 0
    wal.reset()
    assert wal.get_lock_metrics()["lock_timeouts"] == 0

def test_wal_append_cas_success(temp_wal_dir):
    """Test CAS (Compare-And-Swap) append success."""
    h1 = wal.append({"step": 1})
    success, h2 = wal.append_cas({"step": 2}, expected_prev_hash=h1)
    assert success is True
    assert h2 is not None
    assert h2 != h1

def test_wal_append_cas_mismatch(temp_wal_dir):
    """Test CAS (Compare-And-Swap) append failure on hash mismatch."""
    wal.append({"step": 1})
    success, h2 = wal.append_cas({"step": 2}, expected_prev_hash="WRONG_HASH")
    assert success is False
    assert h2 is None
