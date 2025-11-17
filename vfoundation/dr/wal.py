from __future__ import annotations
import json
import os
import time
import hashlib
import pathlib
import sys
import threading
import logging
import decimal
import datetime
from collections.abc import Mapping, Sequence
from typing import Dict, Any, Optional
from contextlib import contextmanager

from ..config import config

_logger = logging.getLogger(__name__)

# Cross-platform file locking
if sys.platform == "win32":
    LOCK_AVAILABLE = True
    # On Windows, use a global lock instead of file-level locks
    # due to msvcrt.locking() limitations with concurrent access
    _GLOBAL_WAL_LOCK = threading.Lock()
    fcntl = None
else:
    try:
        import fcntl

        LOCK_AVAILABLE = True
        _GLOBAL_WAL_LOCK = None  # Not needed on Unix
    except ImportError:
        LOCK_AVAILABLE = False
        _GLOBAL_WAL_LOCK = None
        fcntl = None  # type: ignore

WAL_DIR = config.wal_dir
WAL_FSYNC_ENABLED = True
WAL_SHARED_HANDLES_ENABLED = True
_wal_dir_initialized = False
_shared_wal_handles: dict[pathlib.Path, Any] = {}
_shared_handle_lock = threading.Lock()
_last_hash_file: Optional[pathlib.Path] = None
_last_wal_size: int = 0

# Global state for performance optimization
_last_hash: Optional[str] = None
_last_hash_lock = threading.Lock()

_JSON_SAFE_PRIMITIVES = (str, int, float, bool, type(None))


def _sanitize_for_json(value: Any, path: str = "record") -> Any:
    """Best-effort conversion of nested WAL payloads into JSON-safe structures."""
    if isinstance(value, _JSON_SAFE_PRIMITIVES):
        return value

    if isinstance(value, decimal.Decimal):
        return str(value)

    if isinstance(value, (datetime.datetime, datetime.date)):
        try:
            return value.isoformat()
        except Exception:
            return str(value)

    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, sub_value in value.items():
            if isinstance(key, str):
                safe_key = key
            else:
                safe_key = str(key)
                _logger.warning(
                    "WAL sanitize: coerced non-string key at %s (type=%s)",
                    path,
                    type(key).__name__,
                )
            sanitized[safe_key] = _sanitize_for_json(
                sub_value, f"{path}.{safe_key}"
            )
        return sanitized

    if isinstance(value, set):
        ordered_items = sorted(value, key=lambda item: repr(item))
        return [
            _sanitize_for_json(item, f"{path}[{idx}]")
            for idx, item in enumerate(ordered_items)
        ]

    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [
            _sanitize_for_json(item, f"{path}[{idx}]")
            for idx, item in enumerate(value)
        ]

    if isinstance(value, (bytes, bytearray)):
        try:
            decoded = value.decode("utf-8")
        except Exception:
            decoded = value.decode("utf-8", errors="replace")
        _logger.warning("WAL sanitize: decoded bytes at %s", path)
        return decoded

    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        pass

    sanitized_str = str(value)
    _logger.warning(
        "WAL sanitize: coerced non-JSON value at %s (type=%s)",
        path,
        type(value).__name__,
    )
    return sanitized_str


def _sanitize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize top-level WAL record before hashing/serialization."""
    sanitized = _sanitize_for_json(record, path="record")
    if not isinstance(sanitized, dict):
        raise TypeError("WAL append expects a dictionary record")
    return sanitized


def _should_disable_fsync(new_dir: pathlib.Path) -> bool:
    """Detect if WAL should skip fsync (e.g., when pointing to temp dirs for tests)."""
    try:
        import tempfile

        temp_root = pathlib.Path(tempfile.gettempdir()).resolve()
        new_dir_resolved = new_dir.resolve()

        try:
            return new_dir_resolved.is_relative_to(temp_root)
        except AttributeError:
            # Python < 3.9 fallback (should not trigger, but kept for safety)
            return str(new_dir_resolved).startswith(str(temp_root))
    except Exception:
        return False


def set_wal_dir(path: pathlib.Path) -> None:
    """Set custom WAL directory (useful for testing)"""
    global WAL_DIR, _last_hash, WAL_FSYNC_ENABLED, _last_hash_file, _last_wal_size, _wal_dir_initialized, WAL_SHARED_HANDLES_ENABLED
    WAL_DIR = path
    # Clear cache when directory changes
    with _last_hash_lock:
        _last_hash = None
        _last_hash_file = None
        _last_wal_size = 0
    _wal_dir_initialized = False
    _close_shared_handles()
    # Auto disable fsync + shared handles for temp directories used in tests
    disable_features = _should_disable_fsync(path)
    WAL_FSYNC_ENABLED = not disable_features
    WAL_SHARED_HANDLES_ENABLED = not disable_features


def _get_wal_file_path() -> pathlib.Path:
    """Get current WAL file path (exposed for testing)"""
    return _wal_file_for_today()


def read_last_hash() -> Optional[str]:
    """Read the hash of the last record in WAL (for CAS operations)"""
    # Fast path: check cache first
    global _last_hash, _last_hash_file, _last_wal_size
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
    why_chain = []
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

                            # Collect WHY information
                            why = record.get("why") or record.get(
                                "pld", {}).get("why")
                            if why:
                                if isinstance(why, list):
                                    why_chain.extend(why)
                                else:
                                    why_chain.append(why)

                            # Also check data_ref for WHY chain
                            data_ref = record.get("pld", {}).get("data_ref")
                            if data_ref and isinstance(data_ref, list):
                                why_chain.extend(data_ref)

                    except Exception:
                        continue  # Skip malformed lines
        except Exception:
            continue  # Skip files that can't be read

    # Verify integrity of the chain
    integrity_ok = verify_chain(events) if events else True

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


@contextmanager
def _file_lock(file_handle: Any, timeout_s: float = 5.0) -> Any:
    """
    Cross-platform exclusive file lock context manager.

    Args:
        file_handle: Open file handle
        timeout_s: Maximum time to wait for lock (seconds)

    Raises:
        TimeoutError: If lock cannot be acquired within timeout
    """
    if not LOCK_AVAILABLE:
        # Fallback: no locking available, just proceed
        yield
        return

    # On Windows, use global threading lock instead of msvcrt.locking
    # due to Permission denied issues with concurrent file access
    if sys.platform == "win32" and _GLOBAL_WAL_LOCK:
        start_time = time.time()
        locked = _GLOBAL_WAL_LOCK.acquire(timeout=timeout_s)

        if not locked:
            _record_lock_timeout()
            raise TimeoutError(
                "Could not acquire WAL global lock within timeout")

        try:
            wait_ms = (time.time() - start_time) * 1000
            if wait_ms > 0.1:
                _record_lock_wait(wait_ms)
            yield
        finally:
            _GLOBAL_WAL_LOCK.release()
        return

    # Unix: fcntl.flock with LOCK_EX | LOCK_NB
    if not fcntl:
        # fcntl not available, just proceed without locking
        yield
        return

    start_time = time.time()
    locked = False

    try:
        end_time = start_time + timeout_s
        while time.time() < end_time:
            try:
                fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX |
                            fcntl.LOCK_NB)  # type: ignore
                locked = True
                break
            except (IOError, OSError):
                time.sleep(0.001)  # 1ms retry interval

        if not locked:
            _record_lock_timeout()
            raise TimeoutError(
                "Could not acquire WAL file lock within timeout")

        # Record lock wait time
        wait_ms = (time.time() - start_time) * 1000
        if wait_ms > 0.1:  # Only record if we actually waited
            _record_lock_wait(wait_ms)

        yield

    finally:
        if locked:
            try:
                fcntl.flock(file_handle.fileno(),
                            fcntl.LOCK_UN)  # type: ignore
            except Exception:
                pass  # Best effort unlock


def _wal_file_for_today() -> pathlib.Path:
    global _wal_dir_initialized
    if not _wal_dir_initialized:
        WAL_DIR.mkdir(parents=True, exist_ok=True)
        _wal_dir_initialized = True

    d = time.strftime("%Y-%m-%d")
    return WAL_DIR / f"{d}.jsonl"


def _close_shared_handles() -> None:
    with _shared_handle_lock:
        for handle in _shared_wal_handles.values():
            try:
                handle.close()
            except Exception:
                pass
        _shared_wal_handles.clear()


def _get_shared_handle(path: pathlib.Path) -> Any:
    with _shared_handle_lock:
        handle = _shared_wal_handles.get(path)
        if handle is None or handle.closed:
            handle = path.open("ab+")
            _shared_wal_handles[path] = handle
        return handle


class _SharedHandleContext:
    """Context manager that keeps shared handles open across appends."""

    def __init__(self, handle: Any) -> None:
        self._handle = handle

    def __enter__(self) -> Any:
        return self._handle

    def __exit__(self, exc_type, exc, tb) -> bool:
        # Do not close shared handle; errors propagate normally
        return False


def _read_last_record_from_handle(handle: Any) -> Optional[Dict[str, Any]]:
    """Read the last JSONL record using an existing binary file handle."""
    current_pos = handle.tell()
    handle.seek(0, os.SEEK_END)
    file_size = handle.tell()

    if file_size == 0:
        handle.seek(current_pos, os.SEEK_SET)
        return None

    chunk_size = 4096
    chunks: list[bytes] = []
    newline_count = 0

    while file_size > 0:
        read_size = min(chunk_size, file_size)
        file_size -= read_size
        handle.seek(file_size)
        chunk = handle.read(read_size)
        chunks.append(chunk)
        newline_count += chunk.count(b"\n")

        if newline_count >= 2:
            break

    data = b"".join(reversed(chunks)).strip()
    handle.seek(0, os.SEEK_END)

    if not data:
        return None

    last_line = data.splitlines()[-1].strip()
    if not last_line:
        return None

    try:
        return json.loads(last_line.decode("utf-8"))
    except Exception:
        return None


def _read_last_record_fast(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    """Efficiently read the last JSONL record without scanning entire file."""
    if not path.exists():
        return None

    with path.open("rb") as handle:
        return _read_last_record_from_handle(handle)


def append(record: Dict[str, Any], lock_timeout_s: Optional[float] = None) -> Optional[str]:
    """
    Atomically append a record to WAL with file locking.

    Args:
        record: Record to append
        lock_timeout_s: Maximum time to wait for file lock (uses config default if None)

    Returns:
        Hash of the appended record, or None if lock timeout occurred
    """
    if lock_timeout_s is None:
        lock_timeout_s = config.wal_lock_timeout_sec

    global _last_hash, _last_hash_file, _last_wal_size
    path = _wal_file_for_today()

    line_size = 0
    current_size = 0

    if WAL_SHARED_HANDLES_ENABLED:
        file_context = _SharedHandleContext(_get_shared_handle(path))
    else:
        file_context = path.open("ab+")

    try:
        with file_context as f:
            with _file_lock(f, timeout_s=lock_timeout_s):
                current_size = path.stat().st_size if path.exists() else 0

                prev_hash: Optional[str] = None
                with _last_hash_lock:
                    if (
                        _last_hash is not None
                        and _last_hash_file == path
                        and _last_wal_size == current_size
                    ):
                        prev_hash = _last_hash

                if not prev_hash:
                    last_record = _read_last_record_from_handle(f)
                    if last_record and last_record.get("_hash"):
                        prev_hash = last_record.get("_hash", "0" * 64)
                    else:
                        prev_hash = "0" * 64

                sanitized_record = _sanitize_record(record)
                payload = {**sanitized_record, "_prev": prev_hash}
                record_hash = _calculate_record_hash(payload)
                payload["_hash"] = record_hash

                line_bytes = (json.dumps(
                    payload, ensure_ascii=False) + "\n").encode("utf-8")
                line_size = len(line_bytes)
                f.write(line_bytes)
                if WAL_FSYNC_ENABLED:
                    f.flush()
                    os.fsync(f.fileno())
                else:
                    f.flush()

    except TimeoutError:
        return None

    with _last_hash_lock:
        _last_hash = record_hash
        _last_hash_file = path
        _last_wal_size = current_size + line_size

    return record_hash


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
        return (True, h)

    global _last_hash, _last_hash_file, _last_wal_size
    path = _wal_file_for_today()
    current_size = 0
    line_size = 0

    if WAL_SHARED_HANDLES_ENABLED:
        file_context = _SharedHandleContext(_get_shared_handle(path))
    else:
        file_context = path.open("ab+")

    with file_context as f:
        with _file_lock(f, timeout_s=lock_timeout_s):
            current_size = path.stat().st_size if path.exists() else 0

            prev_hash: Optional[str] = None
            with _last_hash_lock:
                if (
                    _last_hash is not None
                    and _last_hash_file == path
                    and _last_wal_size == current_size
                ):
                    prev_hash = _last_hash

            if not prev_hash:
                last_record = _read_last_record_from_handle(f)
                if last_record and last_record.get("_hash"):
                    prev_hash = last_record.get("_hash", "0" * 64)
                else:
                    prev_hash = "0" * 64

            if prev_hash != expected_prev_hash:
                return (False, None)

            sanitized_record = _sanitize_record(record)
            payload = {**sanitized_record, "_prev": prev_hash}
            record_hash = _calculate_record_hash(payload)
            payload["_hash"] = record_hash

            line_bytes = (json.dumps(
                payload, ensure_ascii=False) + "\n").encode("utf-8")
            line_size = len(line_bytes)
            f.write(line_bytes)
            if WAL_FSYNC_ENABLED:
                f.flush()
                os.fsync(f.fileno())
            else:
                f.flush()

    with _last_hash_lock:
        _last_hash = record_hash
        _last_hash_file = path
        _last_wal_size = current_size + line_size

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
    global _lock_metrics, _last_hash, _last_hash_file, _last_wal_size, _wal_dir_initialized, WAL_FSYNC_ENABLED, WAL_SHARED_HANDLES_ENABLED
    with _lock_metrics_lock:
        _lock_metrics = {
            "lock_contention_count": 0,
            "lock_wait_total_ms": 0.0,
            "lock_timeout_count": 0,
        }
    _last_hash = None
    _last_hash_file = None
    _last_wal_size = 0
    _wal_dir_initialized = False
    _close_shared_handles()
    disable_features = _should_disable_fsync(WAL_DIR)
    WAL_FSYNC_ENABLED = not disable_features
    WAL_SHARED_HANDLES_ENABLED = not disable_features
