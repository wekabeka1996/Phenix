from __future__ import annotations
import json
import logging
import os
import time
import hashlib
import pathlib
import sys
import threading
from dataclasses import dataclass
from typing import Dict, Any, Optional
from contextlib import contextmanager

from ..config import config

# Cross-platform file locking
if sys.platform == "win32":
    import msvcrt

    LOCK_AVAILABLE = True
    fcntl = None
else:
    try:
        import fcntl

        LOCK_AVAILABLE = True
    except ImportError:
        LOCK_AVAILABLE = False
        fcntl = None  # type: ignore

    msvcrt = None  # type: ignore

_GLOBAL_WAL_LOCK = threading.Lock()

WAL_DIR = config.wal_dir
LOG = logging.getLogger("vfoundation.dr.wal")

# Global state for performance optimization
_last_hash: Optional[str] = None
_last_hash_lock = threading.Lock()


@dataclass
class WalChainIntegrityResult:
    """Result of daily WAL hash-chain integrity scan. Observational only."""

    file_path: str
    chain_ok: bool
    record_count: int
    first_bad_index: Optional[int]
    checked_at_ms: int


def set_wal_dir(path: pathlib.Path) -> None:
    """Set custom WAL directory (useful for testing)"""
    global WAL_DIR, _last_hash
    WAL_DIR = path
    # Clear cache when directory changes
    with _last_hash_lock:
        _last_hash = None


def _get_wal_file_path() -> pathlib.Path:
    """Get current WAL file path (exposed for testing)"""
    return _wal_file_for_today()


def read_last_hash() -> Optional[str]:
    """Read the hash of the last record in WAL (for CAS operations)"""
    # Fast path: check cache first
    global _last_hash
    with _last_hash_lock:
        if _last_hash is not None:
            return _last_hash

    # Slow path: read from file
    path = _wal_file_for_today()
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as f:
        last_line = None
        for line in f:
            last_line = line

        if last_line:
            try:
                record = json.loads(last_line)
                hash_val = record.get("_hash")
                # Update cache
                with _last_hash_lock:
                    _last_hash = hash_val
                return str(hash_val) if hash_val else None
            except Exception:
                pass

    return None


def read_all() -> list[Dict[str, Any]]:
    """Read all WAL entries from today's file"""
    path = _wal_file_for_today()
    if not path.exists():
        return []

    entries = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass  # Skip malformed lines

    return entries


def read_by_rid(rid: str) -> tuple[list[Dict[str, Any]], list[str], bool]:
    """
    Read all WAL entries for a specific RID across all WAL files.

    Returns:
        (events, why_chain, integrity_ok)
    """
    import glob

    events = []
    all_hashes = []

    # Get all WAL files (current and historical)
    wal_pattern = str(WAL_DIR / "*.jsonl")
    wal_files = sorted(glob.glob(wal_pattern), reverse=True)  # Newest first

    for wal_file in wal_files:
        try:
            with open(wal_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        record = json.loads(line)
                        record_rid = record.get("rid") or record.get(
                            "pld", {}).get("rid")

                        if record_rid == rid:
                            events.append(record)
                            all_hashes.append(record.get("_hash", ""))

                    except Exception:
                        continue  # Skip malformed lines
        except Exception:
            continue  # Skip files that can't be read

    # Present events in chronological order for debugging.
    def _event_ts(obj: Dict[str, Any]) -> int:
        ts = obj.get("ts")
        if isinstance(ts, int):
            return ts
        pld = obj.get("pld") if isinstance(obj.get("pld"), dict) else {}
        ts_ms = pld.get("ts_ms")
        if isinstance(ts_ms, int):
            return ts_ms
        timestamp = obj.get("timestamp")
        if isinstance(timestamp, int):
            return timestamp
        return 0

    events.sort(key=_event_ts)

    # Build WHY chain evidence from payload + message-level fields (chronological).
    why_chain: list[str] = []

    def _extend_chain(val: Any) -> None:
        if not val:
            return
        if isinstance(val, list):
            for item in val:
                s = str(item)
                if s:
                    why_chain.append(s)
        else:
            s = str(val)
            if s:
                why_chain.append(s)

    for record in events:
        before_len = len(why_chain)

        pld = record.get("pld") if isinstance(record.get("pld"), dict) else {}
        # DecisionMaking trade_intent payloads
        _extend_chain(pld.get("why"))
        _extend_chain(pld.get("why_chain"))  # explicit why_chain payloads
        _extend_chain(record.get("data_ref"))  # message-level audit chain

        # Hot-path WHY tag as fallback only (avoid polluting an existing chain).
        if len(why_chain) == before_len:
            _extend_chain(record.get("why"))

    # Verify record integrity (per-record hash), not rid-subset chain order.
    integrity_ok = True
    for record in events:
        try:
            rec_hash = record.get("_hash")
            if not isinstance(rec_hash, str) or not rec_hash:
                integrity_ok = False
                break
            record_for_hash = {k: v for k, v in record.items() if k != "_hash"}
            if _calculate_record_hash(record_for_hash) != rec_hash:
                integrity_ok = False
                break
        except Exception:
            integrity_ok = False
            break

    # Remove duplicates from why_chain while preserving order
    seen = set()
    unique_why_chain = []
    for item in why_chain:
        if item not in seen:
            seen.add(item)
            unique_why_chain.append(item)

    return events, unique_why_chain, integrity_ok


# Metrics for lock contention
_lock_metrics = {"lock_contention_count": 0,
                 "lock_wait_total_ms": 0.0, "lock_timeout_count": 0}
_lock_metrics_lock = threading.Lock()


def get_lock_metrics() -> Dict[str, Any]:
    """Get current lock metrics for /metrics endpoint"""
    with _lock_metrics_lock:
        return {
            "lock_contention": _lock_metrics["lock_contention_count"],
            "lock_wait_ms": _lock_metrics["lock_wait_total_ms"],
            "lock_timeouts": _lock_metrics["lock_timeout_count"],
        }


def _record_lock_wait(wait_ms: float) -> None:
    """Record lock wait time for metrics"""
    with _lock_metrics_lock:
        _lock_metrics["lock_contention_count"] += 1
        _lock_metrics["lock_wait_total_ms"] += wait_ms


def _record_lock_timeout() -> None:
    """Record lock timeout for metrics"""
    with _lock_metrics_lock:
        _lock_metrics["lock_timeout_count"] += 1


def _wal_append_lock_path() -> pathlib.Path:
    WAL_DIR.mkdir(parents=True, exist_ok=True)
    return WAL_DIR / ".wal_append.lock"


def _ensure_lock_file_initialized(lock_handle: Any) -> None:
    lock_handle.seek(0, os.SEEK_END)
    if lock_handle.tell() == 0:
        lock_handle.write(b"0")
        lock_handle.flush()
        os.fsync(lock_handle.fileno())
    lock_handle.seek(0)


def _read_tail_hash_locked(file_handle: Any) -> str:
    file_handle.seek(0, os.SEEK_END)
    file_size = file_handle.tell()
    if file_size == 0:
        return "0" * 64

    file_handle.seek(0)
    last_non_empty_line: Optional[str] = None
    for raw_line in file_handle:
        if raw_line.strip():
            last_non_empty_line = raw_line

    if last_non_empty_line is None:
        raise ValueError(
            "WAL tail is non-empty but contains no valid JSON line")

    try:
        prev_record = json.loads(last_non_empty_line)
    except Exception as exc:
        raise ValueError("WAL tail is malformed JSON") from exc

    prev_hash = prev_record.get("_hash")
    if not isinstance(prev_hash, str) or len(prev_hash) != 64:
        raise ValueError("WAL tail record has missing or invalid _hash")

    return prev_hash


@contextmanager
def _append_operation_lock(timeout_s: float = 5.0) -> Any:
    """
    Cross-platform exclusive lock for WAL append critical sections.

    Args:
        timeout_s: Maximum time to wait for lock (seconds)

    Raises:
        TimeoutError: If lock cannot be acquired within timeout
    """
    if not LOCK_AVAILABLE:
        # Fallback: no locking available, just proceed
        yield
        return

    start_time = time.time()
    deadline = start_time + timeout_s
    thread_locked = False
    process_locked = False
    lock_path = _wal_append_lock_path()

    try:
        remaining = max(0.0, deadline - time.time())
        thread_locked = _GLOBAL_WAL_LOCK.acquire(timeout=remaining)
        if not thread_locked:
            _record_lock_timeout()
            raise TimeoutError(
                "Could not acquire WAL append thread lock within timeout")

        with lock_path.open("a+b") as lock_handle:
            _ensure_lock_file_initialized(lock_handle)

            while time.time() < deadline:
                try:
                    if sys.platform == "win32":
                        if msvcrt is None:
                            raise TimeoutError(
                                "msvcrt unavailable for WAL append lock")
                        lock_handle.seek(0)
                        msvcrt.locking(lock_handle.fileno(),
                                       msvcrt.LK_NBLCK, 1)
                    else:
                        if not fcntl:
                            raise TimeoutError(
                                "fcntl unavailable for WAL append lock")
                        # type: ignore[arg-type]
                        fcntl.flock(lock_handle.fileno(),
                                    fcntl.LOCK_EX | fcntl.LOCK_NB)

                    process_locked = True
                    break
                except (IOError, OSError):
                    time.sleep(0.001)

            if not process_locked:
                _record_lock_timeout()
                raise TimeoutError(
                    "Could not acquire WAL append process lock within timeout")

            wait_ms = (time.time() - start_time) * 1000
            if wait_ms > 0.1:
                _record_lock_wait(wait_ms)

            try:
                yield
            finally:
                try:
                    if process_locked:
                        if sys.platform == "win32":
                            lock_handle.seek(0)
                            msvcrt.locking(lock_handle.fileno(),
                                           msvcrt.LK_UNLCK, 1)
                        elif fcntl:
                            # type: ignore[arg-type]
                            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass

    finally:
        if thread_locked:
            _GLOBAL_WAL_LOCK.release()


def _wal_file_for_today() -> pathlib.Path:
    d = time.strftime("%Y-%m-%d")
    WAL_DIR.mkdir(parents=True, exist_ok=True)
    return WAL_DIR / f"{d}.jsonl"


def append(record: Dict[str, Any], lock_timeout_s: Optional[float] = None) -> Optional[str]:
    """
    Atomically append a record to WAL with thread + process-level locking.

    Args:
        record: Record to append
        lock_timeout_s: Maximum time to wait for file lock (uses config default if None)

    Returns:
        Hash of the appended record, or None if the append lock times out or
        the current WAL tail is malformed.
    """
    if lock_timeout_s is None:
        lock_timeout_s = config.wal_lock_timeout_sec

    global _last_hash
    path = _wal_file_for_today()

    try:
        with _append_operation_lock(timeout_s=lock_timeout_s):
            with path.open("a+", encoding="utf-8") as f:
                prev_hash = _read_tail_hash_locked(f)

                payload = {**record, "_prev": prev_hash}
                record_hash = _calculate_record_hash(payload)
                payload["_hash"] = record_hash

                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())

        # Update cache with new hash (outside lock for performance)
        with _last_hash_lock:
            _last_hash = record_hash

        return record_hash
    except TimeoutError:
        return None
    except ValueError as exc:
        LOG.warning(
            "[WAL] append aborted due to malformed tail path=%s error=%s", path, exc)
        return None


def append_cas(
    record: Dict[str, Any],
    expected_prev_hash: Optional[str] = None,
    lock_timeout_s: Optional[float] = None,
) -> tuple[bool, Optional[str]]:
    """
    CAS (Compare-And-Swap) append: only append if expected_prev_hash matches actual tail.

    Args:
        record: Record to append
        expected_prev_hash: Expected hash of current tail (None to skip check)
        lock_timeout_s: Maximum time to wait for file lock (uses config default if None)

    Returns:
        (success: bool, hash: Optional[str])
        - If expected_prev_hash matches or is None: (True, new_hash)
        - If mismatch: (False, None)

    Raises:
        TimeoutError: If file lock cannot be acquired within timeout
    """
    if lock_timeout_s is None:
        lock_timeout_s = config.wal_lock_timeout_sec

    if expected_prev_hash is None:
        # No CAS check, just normal append
        h = append(record, lock_timeout_s=lock_timeout_s)
        return (h is not None, h)

    path = _wal_file_for_today()

    try:
        with _append_operation_lock(timeout_s=lock_timeout_s):
            with path.open("a+", encoding="utf-8") as f:
                actual_prev_hash = _read_tail_hash_locked(f)

                if actual_prev_hash != expected_prev_hash:
                    return (False, None)

                payload = {**record, "_prev": actual_prev_hash}
                record_hash = _calculate_record_hash(payload)
                payload["_hash"] = record_hash

                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
    except TimeoutError as exc:
        raise exc
    except ValueError as exc:
        LOG.warning(
            "[WAL] append_cas aborted due to malformed tail path=%s error=%s", path, exc)
        return (False, None)

    # Update cache with new hash
    global _last_hash
    with _last_hash_lock:
        _last_hash = record_hash

    return (True, record_hash)


def _calculate_record_hash(record: Dict[str, Any]) -> str:
    """
    Calculate SHA256 hash of a WAL record (AURORA_HARDENING_V1).

    Args:
        record: Record dictionary (without _hash field)

    Returns:
        Hexadecimal SHA256 hash string
    """
    # Create canonical JSON representation for consistent hashing
    record_json = json.dumps(record, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(record_json.encode("utf-8")).hexdigest()


def verify_chain(records: list[Dict[str, Any]]) -> bool:
    """Verify integrity of WAL chain by checking hash links"""
    if not records:
        return True

    prev_hash = "0" * 64
    for record in records:
        expected_prev = record.get("_prev", "")
        if expected_prev != prev_hash:
            return False

        # Recalculate hash without _hash field
        record_for_hash = {k: v for k, v in record.items() if k != "_hash"}
        expected_hash = _calculate_record_hash(record_for_hash)

        if record.get("_hash") != expected_hash:
            return False

        prev_hash = record.get("_hash", "")

    return True


def check_daily_wal_integrity() -> WalChainIntegrityResult:
    """Scan today's WAL file for hash-chain breaks. Observational only — never raises.

    Returns a typed result with the first bad record index when chain_ok=False.
    Historical chain breaks may still exist from pre-hardening multi-process
    append races and should be logged but never block startup.
    """
    checked_at_ms = int(time.time() * 1000)
    path = _wal_file_for_today()

    if not path.exists():
        return WalChainIntegrityResult(
            file_path=str(path),
            chain_ok=True,
            record_count=0,
            first_bad_index=None,
            checked_at_ms=checked_at_ms,
        )

    records = read_all()

    if not records:
        return WalChainIntegrityResult(
            file_path=str(path),
            chain_ok=True,
            record_count=0,
            first_bad_index=None,
            checked_at_ms=checked_at_ms,
        )

    prev_hash = "0" * 64
    first_bad_index: Optional[int] = None

    for idx, record in enumerate(records):
        expected_prev = record.get("_prev", "")
        if expected_prev != prev_hash:
            first_bad_index = idx
            break

        record_for_hash = {k: v for k, v in record.items() if k != "_hash"}
        expected_hash = _calculate_record_hash(record_for_hash)

        if record.get("_hash") != expected_hash:
            first_bad_index = idx
            break

        prev_hash = record.get("_hash", "")

    return WalChainIntegrityResult(
        file_path=str(path),
        chain_ok=(first_bad_index is None),
        record_count=len(records),
        first_bad_index=first_bad_index,
        checked_at_ms=checked_at_ms,
    )


def calculate_merkle_root(hashes: list[str]) -> str:
    """Calculate merkle root from list of hashes"""
    if not hashes:
        return "0" * 64

    if len(hashes) == 1:
        return hashes[0]

    # Simple merkle tree implementation
    current_level = hashes[:]
    while len(current_level) > 1:
        next_level = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i + 1] if i + \
                1 < len(current_level) else left
            combined = hashlib.sha256((left + right).encode()).hexdigest()
            next_level.append(combined)
        current_level = next_level

    return current_level[0]


def reset() -> None:
    """Reset WAL state for testing purposes - clears metrics and hash tracking"""
    global _lock_metrics, _last_hash
    with _lock_metrics_lock:
        _lock_metrics = {
            "lock_contention_count": 0,
            "lock_wait_total_ms": 0.0,
            "lock_timeout_count": 0,
        }
    _last_hash = None
