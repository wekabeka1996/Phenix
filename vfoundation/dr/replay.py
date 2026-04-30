from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from . import wal
from .replay_boundary import W5_CANDIDATE_REPLAY_EVENT_NAMES
from .wal import calculate_merkle_root


@dataclass
class BoundedReplaySymbolSummary:
    symbol: str
    accepted_records: int = 0
    duplicate_records: int = 0
    unresolved_records: int = 0
    event_counts: Dict[str, int] = field(default_factory=dict)
    identity_keys: List[str] = field(default_factory=list)
    unresolved_reasons: List[str] = field(default_factory=list)


@dataclass
class BoundedReplaySummary:
    boundary_name: str = "W5"
    source_kind: str = "canonical_wal"
    attempted: bool = True
    completed: bool = False
    scan_state: str = "not_attempted"
    symbols_considered: List[str] = field(default_factory=list)
    symbol_records: List[BoundedReplaySymbolSummary] = field(
        default_factory=list)
    symbol_count: int = 0
    records_seen: int = 0
    records_accepted: int = 0
    records_duplicate: int = 0
    records_unresolved: int = 0
    records_ignored_by_boundary: int = 0
    event_counts: Dict[str, int] = field(default_factory=dict)
    unresolved_reasons: List[str] = field(default_factory=list)
    restore_boundary_separation: str = "report_only"
    authoritative_mutation_attempted: bool = False
    failure_reason: Optional[str] = None


_REPLAY_IDENTITY_FIELDS: Dict[str, Tuple[str, ...]] = {
    "EVT:ORDER_PLACED": (
        "order_id",
        "exchange_order_id",
        "client_order_id",
        "corr_id",
    ),
    "EVT:ORDER_REJECTED": (
        "order_id",
        "exchange_order_id",
        "client_order_id",
        "corr_id",
    ),
    "EVT:TRADE_EXECUTED": (
        "order_id",
        "exchange_order_id",
        "client_order_id",
    ),
    "EVT:PENDING_BRACKETS_STORED": (
        "entry_order_id",
    ),
    "EVT:PENDING_BRACKETS_CLEARED": (
        "entry_order_id",
    ),
}


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _record_value(record: Dict[str, Any], key: str) -> Any:
    value = record.get(key)
    if value is not None:
        return value
    payload = record.get("pld")
    if isinstance(payload, dict):
        return payload.get(key)
    return None


def _normalize_symbol(record: Dict[str, Any]) -> str:
    return _normalize_text(_record_value(record, "symbol")).upper()


def _normalize_event_name(record: Dict[str, Any]) -> str:
    event_name = _normalize_text(record.get("event_name"))
    if event_name:
        return event_name
    event_type = _normalize_text(record.get("event_type"))
    if event_type:
        return event_type if event_type.startswith("EVT:") else f"EVT:{event_type}"
    op = _normalize_text(record.get("op"))
    verb = _normalize_text(record.get("verb"))
    if op and verb:
        return f"{op}:{verb}"
    return ""


def _record_ts_ms(record: Dict[str, Any]) -> int:
    for key in ("ts_ms", "ts", "timestamp", "event_ts_ms"):
        value = record.get(key)
        if value is None:
            value = _record_value(record, key)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return 0


def _identity_key_for_record(event_name: str, record: Dict[str, Any]) -> tuple[Optional[str], List[str]]:
    identity_fields = _REPLAY_IDENTITY_FIELDS.get(event_name, ())
    reasons: List[str] = []

    rid = _normalize_text(_record_value(record, "rid"))
    if not rid:
        reasons.append("missing_rid")

    symbol = _normalize_symbol(record)
    if not symbol:
        reasons.append("missing_symbol")

    if not identity_fields:
        reasons.append("unrecognized_event_identity")
        return None, reasons

    identity_name = ""
    identity_value = ""
    for candidate_field in identity_fields:
        candidate_value = _normalize_text(
            _record_value(record, candidate_field))
        if candidate_value:
            identity_name = candidate_field
            identity_value = candidate_value
            break

    if not identity_name:
        reasons.append(f"missing_identity:{'|'.join(identity_fields)}")

    if reasons:
        return None, reasons

    return "|".join((event_name, symbol, rid, identity_name, identity_value)), []


def _load_wal_records() -> Iterable[Dict[str, Any]]:
    wal_dir = wal.WAL_DIR
    if not wal_dir.exists():
        return []

    records: List[Dict[str, Any]] = []
    for file in sorted(wal_dir.glob("*.jsonl")):
        try:
            with file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:
            continue
    return records


def replay_w5_bounded_startup_subset(
    *,
    symbols_considered: Iterable[str],
) -> BoundedReplaySummary:
    summary = BoundedReplaySummary()
    normalized_symbols = sorted(
        {
            _normalize_text(symbol).upper()
            for symbol in symbols_considered
            if _normalize_text(symbol)
        }
    )
    summary.symbols_considered = normalized_symbols
    summary.symbol_count = len(normalized_symbols)
    summary.attempted = True

    if not normalized_symbols:
        summary.completed = True
        summary.scan_state = "completed"
        return summary

    seen_identity_keys: set[str] = set()
    symbol_records: Dict[str, BoundedReplaySymbolSummary] = {}
    unresolved_reasons_seen: set[str] = set()

    try:
        for record in _load_wal_records():
            event_name = _normalize_event_name(record)
            if event_name not in W5_CANDIDATE_REPLAY_EVENT_NAMES:
                summary.records_ignored_by_boundary += 1
                continue

            summary.records_seen += 1

            symbol = _normalize_symbol(record)
            if not symbol:
                summary.records_unresolved += 1
                reason = f"{event_name}:missing_symbol"
                if reason not in unresolved_reasons_seen:
                    unresolved_reasons_seen.add(reason)
                    summary.unresolved_reasons.append(reason)
                continue

            if symbol not in normalized_symbols:
                summary.records_ignored_by_boundary += 1
                continue

            symbol_record = symbol_records.setdefault(
                symbol,
                BoundedReplaySymbolSummary(symbol=symbol),
            )

            identity_key, reasons = _identity_key_for_record(
                event_name, record)
            if reasons:
                summary.records_unresolved += 1
                symbol_record.unresolved_records += 1
                reason = f"{event_name}:{'|'.join(reasons)}"
                if reason not in unresolved_reasons_seen:
                    unresolved_reasons_seen.add(reason)
                    summary.unresolved_reasons.append(reason)
                if reason not in symbol_record.unresolved_reasons:
                    symbol_record.unresolved_reasons.append(reason)
                continue

            if identity_key in seen_identity_keys:
                summary.records_duplicate += 1
                symbol_record.duplicate_records += 1
                continue

            seen_identity_keys.add(identity_key)
            summary.records_accepted += 1
            symbol_record.accepted_records += 1
            symbol_record.identity_keys.append(identity_key)
            symbol_record.event_counts[event_name] = (
                symbol_record.event_counts.get(event_name, 0) + 1
            )
            summary.event_counts[event_name] = summary.event_counts.get(
                event_name, 0) + 1

        summary.symbol_records = [
            symbol_records[symbol]
            for symbol in sorted(symbol_records)
        ]
        summary.completed = True
        summary.scan_state = "completed"
        return summary
    except Exception as exc:
        summary.completed = False
        summary.scan_state = "failed"
        summary.failure_reason = type(exc).__name__
        return summary


def replay_for_rid(rid: str, handler: Callable[[Dict[str, Any]], None]) -> List[Dict[str, Any]]:
    events, _, _ = replay_for_rid_with_integrity(rid, handler)
    return events


def replay_for_rid_with_integrity(
    rid: str, handler: Callable[[Dict[str, Any]], None]
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
            LOG.critical(
                f"WAL integrity check failed: Previous hash mismatch in event {event.get('rid', 'unknown')}. Expected: {expected_previous_hash}, Found: {previous_hash_in_record}"
            )
            return False

        # Verify record hash integrity
        record_for_hash = {k: v for k, v in event.items() if k != "_hash"}
        expected_hash = wal._calculate_record_hash(record_for_hash)
        actual_hash = event.get("_hash", "")

        if actual_hash != expected_hash:
            import logging

            LOG = logging.getLogger(__name__)
            LOG.critical(
                f"WAL integrity check failed: Record hash mismatch in event {event.get('rid', 'unknown')}. Expected: {expected_hash}, Found: {actual_hash}"
            )
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
