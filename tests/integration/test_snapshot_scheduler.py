"""Integration tests for SnapshotScheduler."""

import pytest
import os
import time
from pathlib import Path
from unittest.mock import MagicMock
from apps.reference.domains.snapshot_scheduler.snapshot_scheduler import SnapshotScheduler


def test_snapshot_scheduler_enabled(tmp_path):
    fsm = MagicMock()
    cfg = {"interval_sec": 1, "snapshot_dir": str(
        tmp_path), "domains": ["position_tracking"]}
    scheduler = SnapshotScheduler(fsm=fsm, config=cfg)
    assert scheduler is not None
    scheduler.start()
    # Give some time for snapshot to run
    time.sleep(2)
    scheduler.stop()
    files = list(tmp_path.glob("*.json"))
    assert len(files) >= 1
    # Verify wrapper contains integrity_hash and data
    with open(files[0], 'r', encoding='utf-8') as f:
        obj = f.read()
    assert "integrity_hash" in obj
    assert "data" in obj
