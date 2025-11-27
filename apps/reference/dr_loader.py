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
from typing import Optional, Union

from vfoundation.core.protocol import Message

logger = logging.getLogger(__name__)


def _coerce_timestamp_us(raw_timestamp: Union[str, int, float, None]) -> Optional[int]:
    """Convert assorted timestamp formats to microseconds since epoch."""

    if raw_timestamp is None:
        return None

    value: Optional[int] = None

    if isinstance(raw_timestamp, (int, float)):
        value = int(raw_timestamp)
    elif isinstance(raw_timestamp, str):
        candidate = raw_timestamp.strip()
        if not candidate:
            return None
        if candidate.isdigit():
            value = int(candidate)
        else:
            try:
                iso_dt = datetime.fromisoformat(
                    candidate.replace("Z", "+00:00"))
                value = int(iso_dt.timestamp() * 1_000_000)
            except ValueError:
                return None
    else:
        return None

    if value is None:
        return None

    # Heuristics: normalize seconds or milliseconds to microseconds
    if value < 1_000_000_000:  # < ~1970-04-26 in seconds
        value *= 1_000_000
    elif value < 1_000_000_000_000:  # treat as milliseconds
        value *= 1_000

    return value


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
        start_dt = datetime.fromisoformat(
            start_timestamp_utc.replace("Z", "+00:00"))
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError) as e:
        logger.error(
            f"Invalid timestamp format: {start_timestamp_utc}, error: {e}")
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
    no_timestamp_count = 0  # Aggregate counter to reduce log spam
    invalid_timestamp_count = 0  # Aggregate counter for invalid timestamps

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

                        # Extract timestamp (stored in microseconds in 'timestamp' field or 'ts' in payload)
                        timestamp_raw = msg_dict.get("timestamp")
                        if timestamp_raw is None:
                            timestamp_raw = msg_dict.get("pld", {}).get("ts")

                        if timestamp_raw is None:
                            # Aggregate instead of logging each line
                            no_timestamp_count += 1
                            skipped_count += 1
                            continue

                        timestamp_us = _coerce_timestamp_us(timestamp_raw)
                        if timestamp_us is None:
                            # Aggregate instead of logging each line
                            invalid_timestamp_count += 1
                            skipped_count += 1
                            continue

                        # Convert microseconds to datetime
                        msg_ts = datetime.fromtimestamp(
                            timestamp_us / 1_000_000, tz=timezone.utc
                        )

                        # Skip events before snapshot
                        if msg_ts <= start_dt:
                            skipped_count += 1
                            continue

                        # Replay only position-tracking events
                        verb = msg_dict.get("verb")
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
                                timestamp=timestamp_us,
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

    # Log aggregated timestamp issues only if there are any
    if no_timestamp_count > 0:
        logger.debug(
            f"WAL entries without timestamp: {no_timestamp_count} (skipped)")
    if invalid_timestamp_count > 0:
        logger.debug(
            f"WAL entries with invalid timestamp: {invalid_timestamp_count} (skipped)")

    logger.info(
        f"WAL Replay Summary: {replayed_count} replayed, {skipped_count} skipped (before snapshot), {error_count} errors"
    )
    return replayed_count
