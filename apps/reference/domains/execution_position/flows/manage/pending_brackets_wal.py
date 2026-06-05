"""
Pending Brackets WAL Persistence (PHASE4-LIMIT-BRACKETS-PERSISTENCE)

Persists _pending_brackets state to WAL for LIMIT entry orders.
Allows rehydration on restart to prevent naked positions.

Records:
- PENDING_BRACKETS_STORED: When LIMIT entry placed, brackets deferred
- PENDING_BRACKETS_CLEARED: When brackets placed or entry cancelled
"""
from __future__ import annotations

from dataclasses import dataclass, field
import glob
import json
import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from vfoundation.core.protocol import Message, truncate_why
from vfoundation.dr import wal
from apps.reference.core.time.clock import get_clock

LOG = logging.getLogger(
    "apps.reference.domains.execution_position.pending_brackets_wal"
)

# Verb constants
VERB_STORED = "PENDING_BRACKETS_STORED"
VERB_CLEARED = "PENDING_BRACKETS_CLEARED"
PENDING_BRACKETS_WAL_FILENAME = "execution_position_pending_brackets_v1.jsonl"
_LOCK_RETRY_INTERVAL_S = 0.01
_LOCK_TIMEOUT_S = 5.0
_MALFORMED_WAL_REPORT_HINT = (
    "reports/runtime/WAL_MALFORMED_ROW_FORENSIC_HARDENING_REPORT.md"
)


class CriticalStartupError(RuntimeError):
    """Fail-closed startup error for unrecoverable execution_position restore state."""


@dataclass(frozen=True)
class MalformedWalRowForensicRecord:
    line_number: int
    error_type: str
    error_message: str
    preview: str
    byte_offset: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "line_number": int(self.line_number),
            "error_type": str(self.error_type),
            "error_message": str(self.error_message),
            "preview": str(self.preview),
        }
        if self.byte_offset is not None:
            data["byte_offset"] = int(self.byte_offset)
        return data


@dataclass(frozen=True)
class MalformedWalForensicSummary:
    wal_path: str
    total_lines_scanned: int
    malformed_count: int
    first_malformed_line: Optional[int]
    last_malformed_line: Optional[int]
    malformed_rows: list[MalformedWalRowForensicRecord] = field(
        default_factory=list)
    truncated: bool = False
    max_rows_retained: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "wal_path": str(self.wal_path),
            "total_lines_scanned": int(self.total_lines_scanned),
            "malformed_count": int(self.malformed_count),
            "first_malformed_line": self.first_malformed_line,
            "last_malformed_line": self.last_malformed_line,
            "malformed_rows": [row.to_dict() for row in self.malformed_rows],
            "truncated": bool(self.truncated),
            "max_rows_retained": int(self.max_rows_retained),
        }


def _pending_brackets_wal_path() -> Path:
    from vfoundation.config import config

    wal_dir = config.wal_dir
    wal_dir.mkdir(parents=True, exist_ok=True)
    return wal_dir / PENDING_BRACKETS_WAL_FILENAME


@contextmanager
def _pending_brackets_lock(lock_path: Path):
    deadline = time.time() + _LOCK_TIMEOUT_S
    lock_fd: Optional[int] = None

    while lock_fd is None:
        try:
            lock_fd = os.open(str(lock_path), os.O_CREAT |
                              os.O_EXCL | os.O_RDWR)
        except FileExistsError:
            if time.time() >= deadline:
                raise TimeoutError(
                    f"pending brackets WAL lock timeout for {lock_path}"
                )
            time.sleep(_LOCK_RETRY_INTERVAL_S)

    try:
        yield
    finally:
        try:
            os.close(lock_fd)
        except OSError:
            pass
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _append_pending_brackets_record(record: Dict[str, Any]) -> None:
    wal_path = _pending_brackets_wal_path()
    lock_path = wal_path.with_suffix(f"{wal_path.suffix}.lock")

    with _pending_brackets_lock(lock_path):
        with wal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def _append_daily_wal_record(record: Dict[str, Any]) -> None:
    entry_order_id = ""
    payload = record.get("pld") if isinstance(record.get("pld"), dict) else {}
    if isinstance(payload, dict):
        entry_order_id = str(payload.get("entry_order_id") or "").strip()

    daily_record = dict(record)
    daily_record["dst"] = "observability"

    try:
        appended_hash = wal.append(daily_record)
    except Exception as exc:
        LOG.warning(
            "[WAL] secondary daily append failed verb=%s entry_order_id=%s error=%s",
            daily_record.get("verb"),
            entry_order_id,
            exc,
        )
        return

    if not appended_hash:
        LOG.warning(
            "[WAL] secondary daily append returned no hash verb=%s entry_order_id=%s",
            daily_record.get("verb"),
            entry_order_id,
        )


def _pending_brackets_replay_key(record: Dict[str, Any]) -> Optional[tuple[Any, ...]]:
    verb = str(record.get("verb") or "").strip()
    payload = record.get("pld") if isinstance(record.get("pld"), dict) else {}

    if verb == VERB_STORED:
        return (
            verb,
            str(payload.get("entry_order_id") or "").strip(),
            str(payload.get("symbol") or "").strip().upper(),
            str(payload.get("side") or "").strip().upper(),
            str(record.get("rid") or payload.get("rid") or "").strip(),
            str(payload.get("idem_key") or "").strip(),
            payload.get("ts_ms"),
        )

    if verb == VERB_CLEARED:
        return (
            verb,
            str(payload.get("entry_order_id") or "").strip(),
            str(payload.get("symbol") or "").strip().upper(),
            str(payload.get("reason") or "").strip(),
            str(record.get("rid") or payload.get("rid") or "").strip(),
            payload.get("ts_ms"),
        )

    return None


def scan_malformed_wal_rows(
    file_path: Path,
    *,
    preview_chars: int = 180,
    max_rows: int = 64,
) -> MalformedWalForensicSummary:
    preview_chars = max(0, int(preview_chars))
    max_rows = max(0, int(max_rows))

    malformed_rows: list[MalformedWalRowForensicRecord] = []
    malformed_count = 0
    total_lines_scanned = 0
    first_malformed_line: Optional[int] = None
    last_malformed_line: Optional[int] = None
    byte_offset = 0

    with file_path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            total_lines_scanned += 1
            line_byte_offset = byte_offset
            byte_offset += len(raw_line)

            try:
                text = raw_line.decode("utf-8").rstrip("\r\n")
            except UnicodeDecodeError as exc:
                preview = raw_line.decode(
                    "utf-8", errors="replace").rstrip("\r\n")
                malformed_count += 1
                if first_malformed_line is None:
                    first_malformed_line = line_number
                last_malformed_line = line_number
                if len(malformed_rows) < max_rows:
                    malformed_rows.append(
                        MalformedWalRowForensicRecord(
                            line_number=line_number,
                            error_type=type(exc).__name__,
                            error_message=str(exc),
                            preview=preview[:preview_chars],
                            byte_offset=line_byte_offset,
                        )
                    )
                continue

            if not text.strip():
                continue

            try:
                json.loads(text)
            except json.JSONDecodeError as jde:
                malformed_count += 1
                if first_malformed_line is None:
                    first_malformed_line = line_number
                last_malformed_line = line_number
                if len(malformed_rows) < max_rows:
                    malformed_rows.append(
                        MalformedWalRowForensicRecord(
                            line_number=line_number,
                            error_type=type(jde).__name__,
                            error_message=str(jde),
                            preview=text[:preview_chars],
                            byte_offset=line_byte_offset,
                        )
                    )

    return MalformedWalForensicSummary(
        wal_path=str(file_path),
        total_lines_scanned=total_lines_scanned,
        malformed_count=malformed_count,
        first_malformed_line=first_malformed_line,
        last_malformed_line=last_malformed_line,
        malformed_rows=malformed_rows,
        truncated=malformed_count > len(malformed_rows),
        max_rows_retained=max_rows,
    )


def _format_malformed_wal_corruption_message(
    summary: MalformedWalForensicSummary,
) -> str:
    first_row = summary.malformed_rows[0] if summary.malformed_rows else None
    if first_row is None:
        return (
            f"pending brackets WAL corruption in {summary.wal_path} "
            f"(malformed_rows={summary.malformed_count})"
        )

    preview = first_row.preview if first_row.preview else ""
    byte_offset = (
        f", byte_offset={first_row.byte_offset}"
        if first_row.byte_offset is not None
        else ""
    )
    truncated = (
        f"; retained_rows={len(summary.malformed_rows)}/{summary.malformed_count}"
        if summary.truncated
        else ""
    )
    return (
        f"pending brackets WAL corruption in {summary.wal_path}:{first_row.line_number}"
        f"{byte_offset} (malformed_rows={summary.malformed_count})"
        f"{truncated}: {first_row.error_type}: {first_row.error_message}; "
        f"preview={preview!r}; report={_MALFORMED_WAL_REPORT_HINT}"
    )


def _log_malformed_wal_summary(summary: MalformedWalForensicSummary) -> None:
    first_row = summary.malformed_rows[0] if summary.malformed_rows else None
    LOG.critical(
        "[WAL] DEF-E08 forensic scan: malformed pending brackets WAL detected "
        "file=%s malformed_count=%s first_line=%s last_line=%s byte_offset=%s "
        "error_type=%s error=%s preview=%r",
        summary.wal_path,
        summary.malformed_count,
        summary.first_malformed_line,
        summary.last_malformed_line,
        None if first_row is None else first_row.byte_offset,
        None if first_row is None else first_row.error_type,
        None if first_row is None else first_row.error_message,
        None if first_row is None else first_row.preview,
    )


def _apply_pending_brackets_record(
    record: Dict[str, Any], pending: Dict[str, Dict[str, Any]]
) -> None:
    verb = str(record.get("verb") or "")
    pld = record.get("pld") if isinstance(record.get("pld"), dict) else {}

    if verb == VERB_STORED:
        entry_order_id = pld.get("entry_order_id")
        if entry_order_id:
            pending[entry_order_id] = {
                "symbol": pld.get("symbol"),
                "side": pld.get("side"),
                "sl": pld.get("sl"),
                "tp": pld.get("tp"),
                "qty": pld.get("qty"),
                "rid": pld.get("rid"),
                "idem_key": pld.get("idem_key"),
                "tick_size": pld.get("tick_size"),
                "corr_id": pld.get("corr_id"),
                "oco_group_id": pld.get("oco_group_id"),
                "entry_client_order_id": pld.get("entry_client_order_id"),
                "strategy_id": pld.get("strategy_id"),
                "strategy_source": pld.get("strategy_source"),
                "owner_status": pld.get("owner_status"),
                "owner_detail": pld.get("owner_detail"),
                "assigned_strategies": pld.get("assigned_strategies"),
                "placement_path": pld.get("placement_path") or "deferred_pending",
                "created_at": pld.get("ts_ms", 0) / 1000.0,
            }
        return

    if verb == VERB_CLEARED:
        entry_order_id = pld.get("entry_order_id")
        if entry_order_id and entry_order_id in pending:
            del pending[entry_order_id]


def _replay_pending_brackets_file(
    *,
    file_path: Path,
    pending: Dict[str, Dict[str, Any]],
    fail_closed_on_any_corrupt_line: bool,
    seen_record_keys: set[tuple[Any, ...]],
) -> None:
    candidate_tokens = (VERB_STORED, VERB_CLEARED)

    with file_path.open("r", encoding="utf-8") as handle:
        for _line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            if (
                not fail_closed_on_any_corrupt_line
                and not any(token in line for token in candidate_tokens)
            ):
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as jde:
                malformed_summary = scan_malformed_wal_rows(file_path)
                _log_malformed_wal_summary(malformed_summary)
                raise CriticalStartupError(
                    _format_malformed_wal_corruption_message(malformed_summary)
                ) from jde

            if not isinstance(record, dict):
                continue

            replay_key = _pending_brackets_replay_key(record)
            if replay_key is not None:
                if replay_key in seen_record_keys:
                    continue
                seen_record_keys.add(replay_key)

            _apply_pending_brackets_record(record, pending)


def write_pending_brackets_stored(
    *,
    entry_order_id: str,
    symbol: str,
    side: str,
    sl: float,
    tp: float,
    qty: float,
    rid: str,
    idem_key: str,
    tick_size: float,
    corr_id: Optional[str] = None,
    oco_group_id: Optional[str] = None,
    entry_client_order_id: Optional[str] = None,
    strategy_id: Optional[str] = None,
    strategy_source: Optional[str] = None,
    owner_status: Optional[str] = None,
    owner_detail: Optional[str] = None,
    assigned_strategies: Optional[list[str]] = None,
    placement_path: Optional[str] = None,
) -> None:
    """
    Write PENDING_BRACKETS_STORED to WAL when LIMIT entry defers TP/SL.

    This record allows rehydration on restart.
    """
    ts_ms = get_clock().now_ms()

    payload: Dict[str, Any] = {
        "ts_ms": ts_ms,
        "entry_order_id": str(entry_order_id),
        "symbol": str(symbol),
        "side": str(side),
        "sl": float(sl) if sl is not None else None,
        "tp": float(tp) if tp is not None else None,
        "qty": float(qty),
        "rid": str(rid),
        "idem_key": str(idem_key),
        "tick_size": float(tick_size),
    }

    if corr_id is not None:
        payload["corr_id"] = str(corr_id)
    if oco_group_id is not None:
        payload["oco_group_id"] = str(oco_group_id)
    if entry_client_order_id is not None:
        payload["entry_client_order_id"] = str(entry_client_order_id)
    if strategy_id is not None:
        payload["strategy_id"] = str(strategy_id)
    if strategy_source is not None:
        payload["strategy_source"] = str(strategy_source)
    if owner_status is not None:
        payload["owner_status"] = str(owner_status)
    if owner_detail is not None:
        payload["owner_detail"] = str(owner_detail)
    if assigned_strategies is not None:
        payload["assigned_strategies"] = [
            str(item) for item in assigned_strategies if str(item or "").strip()
        ]
    if placement_path is not None:
        payload["placement_path"] = str(placement_path)

    msg = Message(
        op="EVT",
        verb=VERB_STORED,
        src="execution_position",
        dst="wal",
        rid=str(rid),
        ts=ts_ms,
        why=truncate_why(f"limit_entry_deferred_brackets:{symbol}"),
        pld=payload,
    )

    _append_pending_brackets_record(msg.model_dump())
    _append_daily_wal_record(msg.model_dump())
    LOG.debug(f"[WAL] {VERB_STORED}: {entry_order_id} for {symbol}")


def write_pending_brackets_cleared(
    *,
    entry_order_id: str,
    symbol: str,
    reason: str,
    rid: Optional[str] = None,
) -> None:
    """
    Write PENDING_BRACKETS_CLEARED to WAL when brackets are placed or entry cancelled.

    Reasons:
    - "filled": LIMIT entry filled, brackets placed
    - "cancelled": Entry order cancelled (regime change, TTL, user)
    - "expired": Entry order expired
    """
    ts_ms = get_clock().now_ms()

    payload: Dict[str, Any] = {
        "ts_ms": ts_ms,
        "entry_order_id": str(entry_order_id),
        "symbol": str(symbol),
        "reason": str(reason),
    }

    msg = Message(
        op="EVT",
        verb=VERB_CLEARED,
        src="execution_position",
        dst="wal",
        rid=str(rid) if rid else f"clear:{entry_order_id}:{ts_ms}",
        ts=ts_ms,
        why=truncate_why(f"brackets_cleared:{reason}"),
        pld=payload,
    )

    _append_pending_brackets_record(msg.model_dump())
    _append_daily_wal_record(msg.model_dump())
    LOG.debug(f"[WAL] {VERB_CLEARED}: {entry_order_id} reason={reason}")


def read_pending_brackets_from_wal() -> Dict[str, Dict[str, Any]]:
    """
    Read pending brackets from WAL for rehydration on startup.

    Reconstructs state by replaying STORED/CLEARED events.
    Only returns brackets that were STORED but not yet CLEARED.

    Returns:
        Dict[entry_order_id, bracket_data]
    """
    from vfoundation.config import config

    pending: Dict[str, Dict[str, Any]] = {}
    seen_record_keys: set[tuple[Any, ...]] = set()
    wal_dir = config.wal_dir
    dedicated_wal = _pending_brackets_wal_path()

    if dedicated_wal.exists():
        _replay_pending_brackets_file(
            file_path=dedicated_wal,
            pending=pending,
            fail_closed_on_any_corrupt_line=True,
            seen_record_keys=seen_record_keys,
        )

    wal_pattern = str(wal_dir / "*.jsonl")
    shared_wal_files = [
        Path(candidate)
        for candidate in sorted(glob.glob(wal_pattern))
        if Path(candidate) != dedicated_wal
    ]

    for wal_file in shared_wal_files:
        try:
            _replay_pending_brackets_file(
                file_path=wal_file,
                pending=pending,
                fail_closed_on_any_corrupt_line=False,
                seen_record_keys=seen_record_keys,
            )
        except CriticalStartupError:
            raise
        except Exception as exc:
            LOG.warning(f"Error reading WAL file {wal_file}: {exc}")
            continue

    LOG.info(f"[WAL] Rehydrated {len(pending)} pending brackets from WAL")
    return pending


def gc_old_bracket_records(max_age_days: int = 7) -> int:
    """
    Garbage collect old bracket WAL records (optional maintenance).

    Note: WAL files are date-based, so old files can simply be deleted.
    This function is for in-file cleanup if needed.

    Returns:
        Number of records considered for cleanup
    """
    # WAL files are rotated daily, so GC is handled by file deletion
    # This is a placeholder for future in-file compaction if needed
    return 0
