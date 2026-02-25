"""Compatibility shim for DR loader.

Canonical implementation now lives in ``vfoundation.dr.dr_loader``.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Optional

from vfoundation.dr.dr_loader import (
    find_latest_snapshot as _find_latest_snapshot,
)
from vfoundation.dr.dr_loader import replay_wal_after as _replay_wal_after

warnings.warn(
    "apps.reference.dr_loader is deprecated; use vfoundation.dr.dr_loader",
    DeprecationWarning,
    stacklevel=2,
)


def find_latest_snapshot(snapshot_dir: str = "ops/snapshots") -> Optional[Path]:
    """Deprecated wrapper around ``vfoundation.dr.dr_loader.find_latest_snapshot``."""
    return _find_latest_snapshot(snapshot_dir)


def replay_wal_after(wal_dir: str, start_timestamp_utc: str, target_fsm: Any) -> int:
    """Deprecated wrapper around ``vfoundation.dr.dr_loader.replay_wal_after``."""
    return _replay_wal_after(wal_dir, start_timestamp_utc, target_fsm)
