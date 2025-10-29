from __future__ import annotations
import json
from typing import Dict, Any, Callable, List, Tuple
from . import wal
from .wal import calculate_merkle_root

def replay_for_rid(rid: str, handler: Callable[[Dict[str, Any]], None]) -> List[Dict[str, Any]]:
    events, _, _ = replay_for_rid_with_integrity(rid, handler)
    return events

def replay_for_rid_with_integrity(
    rid: str, 
    handler: Callable[[Dict[str, Any]], None]
) -> Tuple[List[Dict[str, Any]], bool, str]:
    """
    Replay events for RID and return (events, integrity_ok, merkle_root)
    
    Performs hash-chain integrity verification during replay (AURORA_HARDENING_V1).
    """
    wal_dir = wal.WAL_DIR  # Use WAL_DIR from wal module
    events: List[Dict[str, Any]] = []
    if not wal_dir.exists():
        return events, True, "0" * 64
    
    for file in sorted(wal_dir.glob("*.jsonl")):
        for line in file.read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("rid") == rid:
                events.append(obj)
                handler(obj)
    
    # Enhanced hash-chain integrity verification (AURORA_HARDENING_V1)
    integrity_ok = _verify_wal_hash_chain_integrity(events)
    
    # Calculate merkle root
    hashes = [event.get("_hash", "") for event in events if event.get("_hash")]
    merkle_root = calculate_merkle_root(hashes)
    
    return events, integrity_ok, merkle_root

def _verify_wal_hash_chain_integrity(events: List[Dict[str, Any]]) -> bool:
    """
    Verify WAL hash-chain integrity for a sequence of events (AURORA_HARDENING_V1).
    
    Checks that each event's previous_record_hash matches the hash of the previous event.
    
    Args:
        events: List of WAL events in chronological order
        
    Returns:
        True if hash chain is valid, False otherwise
    """
    if not events:
        return True
    
    # Sort events by timestamp to ensure chronological order
    sorted_events = sorted(events, key=lambda x: x.get("ts", 0))
    
    expected_previous_hash = "0" * 64  # For first event (genesis hash)
    
    for event in sorted_events:
        # Check previous record hash
        previous_hash_in_record = event.get("_prev", "")
        if previous_hash_in_record != (expected_previous_hash or ""):
            import logging
            LOG = logging.getLogger(__name__)
            LOG.critical(f"WAL integrity check failed: Previous hash mismatch in event {event.get('rid', 'unknown')}. Expected: {expected_previous_hash}, Found: {previous_hash_in_record}")
            return False
        
        # Verify record hash integrity
        record_for_hash = {k: v for k, v in event.items() if k != "_hash"}
        expected_hash = wal._calculate_record_hash(record_for_hash)
        actual_hash = event.get("_hash", "")
        
        if actual_hash != expected_hash:
            import logging
            LOG = logging.getLogger(__name__)
            LOG.critical(f"WAL integrity check failed: Record hash mismatch in event {event.get('rid', 'unknown')}. Expected: {expected_hash}, Found: {actual_hash}")
            return False
        
        # Update expected previous hash for next event
        expected_previous_hash = actual_hash
    
    return True


def replay_from_wal(handler: Callable[[Dict[str, Any]], None], from_ts: int = 0) -> None:
    """
    Replay all events from WAL that occurred after from_ts.
    """
    wal_dir = wal.WAL_DIR
    if not wal_dir.exists():
        return
    
    for file in sorted(wal_dir.glob("*.jsonl")):
        for line in file.read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(line)
                # Filter by timestamp if from_ts is specified
                if from_ts > 0 and obj.get("ts", 0) < from_ts:
                    continue
                handler(obj)
            except Exception:
                continue
