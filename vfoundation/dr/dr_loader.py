"""
Disaster Recovery Loader Module

Provides utilities for loading snapshots and replaying WAL entries
to restore system state after a failure.

WHY: Enable automatic state restoration from snapshot + WAL replay [FSMP-RESILIENCE-T04A]
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from vfoundation.core.protocol import Message

logger = logging.getLogger(__name__)

def _normalize_epoch_to_ms(raw_ts) -> Optional[int]:
    """
    Normalize a timestamp to epoch milliseconds.

    Accepts:
    - seconds (float/int): ~1e9
    - milliseconds (int): ~1e12
    - microseconds (int): ~1e15
    - nanoseconds (int): ~1e18
    """
    if raw_ts is None:
        return None

    try:
        ts = float(raw_ts)
    except (TypeError, ValueError):
        return None

    if ts <= 0:
        return None

    # Heuristic by magnitude.
    if ts >= 1e18:  # ns
        return int(ts / 1_000_000)
    if ts >= 1e15:  # us
        return int(ts / 1_000)
    if ts >= 1e12:  # ms
        return int(ts)
    # Assume seconds
    return int(ts * 1_000)


def _strip_evt_prefix(verb: Optional[str]) -> Optional[str]:
    if not verb:
        return verb
    if verb.startswith("EVT:"):
        return verb[len("EVT:") :]
    return verb


def find_latest_snapshot(snapshot_dir: str = "ops/snapshots") -> Optional[Path]:
    """
    Finds the most recent snapshot file in the directory.

    Args:
        snapshot_dir: Directory containing snapshot files

    Returns:
        Path to the latest snapshot file, or None if no snapshots found
    """
    path = Path(snapshot_dir)
    if not path.exists():
        logger.debug(f"Snapshot directory does not exist: {snapshot_dir}")
        return None

    files = list(path.glob("*.json"))
    if not files:
        logger.debug(f"No snapshot files found in: {snapshot_dir}")
        return None

    latest = max(files, key=lambda f: f.stat().st_mtime)
    logger.info(
        f"Found latest snapshot: {latest.name} (modified: {datetime.fromtimestamp(latest.stat().st_mtime)})"
    )
    return latest


def replay_wal_after(wal_dir: str, start_timestamp_utc: str, target_fsm) -> int:
    """
    Replays WAL entries created after a given timestamp.

    Args:
        wal_dir: Directory containing WAL files (*.jsonl)
        start_timestamp_utc: ISO format timestamp to replay from
        target_fsm: FSM domain object with event handler methods

    Returns:
        Number of events replayed

    WHY: Restore state changes that occurred after snapshot creation
    """
    wal_path = Path(wal_dir)
    if not wal_path.exists():
        logger.warning(f"WAL directory does not exist: {wal_dir}")
        return 0

    try:
        # Parse start timestamp
        start_dt = datetime.fromisoformat(start_timestamp_utc.replace("Z", "+00:00"))
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError) as e:
        logger.error(f"Invalid timestamp format: {start_timestamp_utc}, error: {e}")
        return 0

    # Find all WAL files (sorted by date)
    wal_files = sorted(wal_path.glob("*.jsonl"))
    if not wal_files:
        logger.info("No WAL files found for replay")
        return 0

    logger.info(f"Found {len(wal_files)} WAL file(s) to scan for replay")
    logger.info(f"Replaying events after: {start_dt.isoformat()}")

    replayed_count = 0
    skipped_count = 0
    error_count = 0

    for file_path in wal_files:
        logger.debug(f"Scanning WAL file: {file_path.name}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        msg_dict = json.loads(line)

                        # Extract timestamp (supports seconds/ms/us/ns across producers)
                        raw_ts = msg_dict.get("timestamp")
                        if raw_ts is None:
                            raw_ts = msg_dict.get("event_ts_ms")
                        if raw_ts is None:
                            raw_ts = msg_dict.get("pld", {}).get("ts")

                        timestamp_ms = _normalize_epoch_to_ms(raw_ts)
                        if timestamp_ms is None:
                            logger.warning(
                                f"No timestamp found in {file_path.name}:{line_num}, skipping"
                            )
                            skipped_count += 1
                            continue

                        msg_ts = datetime.fromtimestamp(timestamp_ms / 1_000, tz=timezone.utc)

                        # Skip events before snapshot
                        if msg_ts <= start_dt:
                            skipped_count += 1
                            continue

                        # Replay only position-tracking events
                        verb = _strip_evt_prefix(msg_dict.get("verb"))
                        if verb in ["TRADE_EXECUTED", "ACCOUNT_UPDATE_RECEIVED"]:
                            # Reconstruct Message object
                            msg = Message(
                                op=msg_dict.get("op"),
                                verb=verb,
                                pld=msg_dict.get("pld", {}),
                                src=msg_dict.get("src"),
                                dst=msg_dict.get("dst"),
                                rid=msg_dict.get("rid"),
                                why=msg_dict.get("why", "WAL replay"),
                                ts=timestamp_ms,
                            )

                            # Dispatch to appropriate handler
                            if verb == "TRADE_EXECUTED":
                                target_fsm.on_trade_executed(msg)
                            elif verb == "ACCOUNT_UPDATE_RECEIVED":
                                target_fsm.on_account_update(msg)

                            replayed_count += 1

                            if replayed_count % 100 == 0:
                                logger.debug(
                                    f"Replayed {replayed_count} events so far..."
                                )

                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(
                            f"Failed to parse line {line_num} in {file_path.name}: {e}"
                        )
                        error_count += 1
                        continue

        except Exception as e:
            logger.error(f"Failed to read WAL file {file_path.name}: {e}")
            error_count += 1
            continue

    logger.info(
        f"WAL Replay Summary: {replayed_count} replayed, {skipped_count} skipped (before snapshot), {error_count} errors"
    )
    return replayed_count
