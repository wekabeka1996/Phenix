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
    logger.info(f"Found latest snapshot: {latest.name} (modified: {datetime.fromtimestamp(latest.stat().st_mtime)})")
    return latest


def replay_wal_after(wal_dir: str, start_timestamp_utc: str, target_fsm, config: Optional[dict] = None) -> int:
    """
    Replays WAL entries created after a given timestamp.
    
    Args:
        wal_dir: Directory containing WAL files (*.jsonl)
        start_timestamp_utc: ISO format timestamp to replay from
        target_fsm: FSM domain object with event handler methods
        config: Configuration dictionary containing critical_verbs list
        
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
        start_dt = datetime.fromisoformat(start_timestamp_utc.replace('Z', '+00:00'))
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
    
    # Get critical verbs from config, default to current hardcoded values
    critical_verbs = config.get('critical_verbs', ["TRADE_EXECUTED", "ACCOUNT_UPDATE_RECEIVED"]) if config else ["TRADE_EXECUTED", "ACCOUNT_UPDATE_RECEIVED"]
    
    # Define verb-to-handler mapping
    verb_handlers = {
        "TRADE_EXECUTED": lambda msg: target_fsm.on_trade_executed(msg),
        "ACCOUNT_UPDATE_RECEIVED": lambda msg: target_fsm.on_account_update(msg),
    }
    
    # Allow config to override or extend handlers
    if config and 'verb_handlers' in config:
        verb_handlers.update(config['verb_handlers'])
    
    logger.info(f"Critical verbs for replay: {critical_verbs}")
    logger.info(f"Available verb handlers: {list(verb_handlers.keys())}")
    
    replayed_count = 0
    skipped_count = 0
    error_count = 0
    
    for file_path in wal_files:
        logger.debug(f"Scanning WAL file: {file_path.name}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        msg_dict = json.loads(line)
                        
                        # Extract timestamp (stored in microseconds in 'timestamp' field or 'ts' in payload)
                        timestamp_us = msg_dict.get("timestamp")
                        if timestamp_us is None:
                            # Fallback to payload timestamp
                            timestamp_us = msg_dict.get("pld", {}).get("ts")
                        
                        if timestamp_us is None:
                            logger.warning(f"No timestamp found in {file_path.name}:{line_num}, skipping")
                            skipped_count += 1
                            continue
                        
                        # Convert microseconds to datetime
                        msg_ts = datetime.fromtimestamp(timestamp_us / 1_000_000, tz=timezone.utc)
                        
                        # Skip events before snapshot
                        if msg_ts <= start_dt:
                            skipped_count += 1
                            continue
                        
                        # Replay only position-tracking events
                        verb = msg_dict.get("verb")
                        if verb in critical_verbs:
                            # Reconstruct Message object
                            msg = Message(
                                op=msg_dict.get("op"),
                                verb=verb,
                                pld=msg_dict.get("pld", {}),
                                src=msg_dict.get("src"),
                                dst=msg_dict.get("dst"),
                                rid=msg_dict.get("rid"),
                                why=msg_dict.get("why", "WAL replay"),
                                timestamp=timestamp_us
                            )
                            
                            # Dispatch to appropriate handler
                            if verb in verb_handlers:
                                verb_handlers[verb](msg)
                                replayed_count += 1
                            else:
                                logger.warning(f"No handler defined for verb '{verb}', skipping event")
                                skipped_count += 1
                            
                            if replayed_count % 100 == 0:
                                logger.debug(f"Replayed {replayed_count} events so far...")
                        
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(f"Failed to parse line {line_num} in {file_path.name}: {e}")
                        error_count += 1
                        continue
                    
        except Exception as e:
            logger.error(f"Failed to read WAL file {file_path.name}: {e}")
            error_count += 1
            continue
    
    logger.info(f"WAL Replay Summary: {replayed_count} replayed, {skipped_count} skipped (before snapshot), {error_count} errors")
    return replayed_count
