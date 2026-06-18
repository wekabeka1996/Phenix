import json
import os
import threading
import time
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional, Union
from unittest import mock

import jsonschema


DEFAULT_ORDER_LOG_FILE = Path("logs") / "order_log_v1.jsonl"


def _to_jsonable(value: Any, *, _seen: set[int] | None = None, _depth: int = 0) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, mock.Mock):
        # Mock objects (MagicMock/AsyncMock) are often self-referential; stringify to avoid recursion/hangs.
        return str(value)
    if _seen is None:
        _seen = set()
    if _depth > 20:
        return str(value)
    obj_id = id(value)
    if obj_id in _seen:
        return "<cycle>"
    _seen.add(obj_id)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v, _seen=_seen, _depth=_depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v, _seen=_seen, _depth=_depth + 1) for v in value]
    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        try:
            maybe = value.to_dict()
            if isinstance(maybe, dict):
                return _to_jsonable(maybe, _seen=_seen, _depth=_depth + 1)
        except Exception:
            pass
    if is_dataclass(value):
        try:
            return _to_jsonable(asdict(value), _seen=_seen, _depth=_depth + 1)
        except Exception:
            pass
    return str(value)


def _schema_path() -> Path:
    base_dir = Path(__file__).resolve().parent.parent
    return base_dir / "schemas" / "order_logger_v1.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_log_file(log_file: Optional[Union[str, Path]] = None) -> Path:
    candidate = DEFAULT_ORDER_LOG_FILE if log_file is None else Path(log_file)
    if candidate.is_absolute():
        return candidate
    return _repo_root() / candidate


class OrderLoggerV1:
    """L1 Order Logger - Unified order lifecycle logging with schema validation."""

    def __init__(self, log_file: Union[str, Path] = DEFAULT_ORDER_LOG_FILE):
        self.log_file = _resolve_log_file(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()
        self.rotation_max_bytes = max(
            1, int(os.getenv("ORDER_LOG_ROTATE_BYTES", str(50 * 1024 * 1024))))
        self.retention_days = max(
            30, int(os.getenv("ORDER_LOG_RETENTION_DAYS", "30")))
        self._active_day = self._file_utc_day(self.log_file)

        # Load schema
        with open(_schema_path(), 'r', encoding='utf-8') as f:
            self.schema = json.load(f)

        # Write boot record to mark session start (observability marker)
        self._write_boot_record()

    @staticmethod
    def _file_utc_day(path: Path) -> str:
        if not path.exists():
            return time.strftime("%Y%m%d", time.gmtime())
        return time.strftime("%Y%m%d", time.gmtime(path.stat().st_mtime))

    def _rotated_files(self) -> list[Path]:
        return sorted(self.log_file.parent.glob(
            f"{self.log_file.stem}.*{self.log_file.suffix}"))

    def _purge_expired_rotations(self, now_s: float) -> None:
        cutoff = now_s - (self.retention_days * 86400)
        for path in self._rotated_files():
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except FileNotFoundError:
                continue

    def _rotate_if_needed(self, now_ms: int) -> None:
        if not self.log_file.exists() or self.log_file.stat().st_size == 0:
            self._active_day = time.strftime(
                "%Y%m%d", time.gmtime(now_ms / 1000.0))
            return
        current_day = time.strftime("%Y%m%d", time.gmtime(now_ms / 1000.0))
        size_exceeded = self.log_file.stat().st_size >= self.rotation_max_bytes
        if not size_exceeded and current_day == self._active_day:
            return
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now_ms / 1000.0))
        sequence = 0
        while True:
            rotated = self.log_file.with_name(
                f"{self.log_file.stem}.{stamp}.{sequence:03d}{self.log_file.suffix}")
            if not rotated.exists():
                break
            sequence += 1
        os.replace(self.log_file, rotated)
        self._active_day = current_day
        self._purge_expired_rotations(now_ms / 1000.0)

    def _append(self, entry: Dict[str, Any]) -> None:
        with self._write_lock:
            self._rotate_if_needed(int(time.time() * 1000))
            with open(self.log_file, 'a', encoding='utf-8') as f:
                json.dump(entry, f, ensure_ascii=False)
                f.write('\n')

    def _write_boot_record(self) -> None:
        """Write a BOOT record to mark session start.

        This is a system marker (not an order event), so it bypasses schema validation.
        Enables observability: if order_log has BOOT but no ORDER_* events,
        we know the system ran but no orders were placed.
        """
        boot_record = {
            "event_type": "BOOT",
            "timestamp": int(time.time() * 1000),
            "source_fsm": "OrderLoggerV1",
            "rid": f"boot-{int(time.time() * 1000)}",
            "symbol": "_SYSTEM_",
            "why": "order_logger session start marker",
        }
        # Write directly without schema validation (BOOT is a system event)
        self._append(boot_record)

    def write(self, entry: Dict[str, Any]) -> None:
        """Write order log entry with optional schema validation."""
        entry = _to_jsonable(entry)
        # Add timestamp if not provided — prefer simulated clock in backtest
        if "timestamp" not in entry:
            try:
                from apps.reference.core.time import get_clock
                entry["timestamp"] = int(get_clock().now_ms())
            except Exception:
                entry["timestamp"] = int(time.time() * 1000)

        # Validate schema in DEBUG/TEST modes
        env = os.getenv("ENV", "").upper()
        if env in ("DEBUG", "TEST"):
            try:
                jsonschema.validate(instance=entry, schema=self.schema)
            except jsonschema.ValidationError as e:
                raise ValueError(f"Schema validation failed: {e}") from e

        # Write to JSONL file
        self._append(entry)


def iter_order_log_files(log_file: Optional[Union[str, Path]] = None) -> list[Path]:
    """Return retained rotations followed by the active order log."""
    active = _resolve_log_file(log_file)
    rotated = sorted(active.parent.glob(f"{active.stem}.*{active.suffix}"))
    return [*rotated, active]


# Global instance
_order_logger_instance: Optional[OrderLoggerV1] = None


def get_order_logger(log_file: Optional[Union[str, Path]] = None) -> OrderLoggerV1:
    """Return a singleton OrderLoggerV1, initialized lazily."""
    global _order_logger_instance
    if _order_logger_instance is None:
        _order_logger_instance = OrderLoggerV1(
            _resolve_log_file(
                log_file) if log_file is not None else DEFAULT_ORDER_LOG_FILE
        )
    elif log_file is not None:
        resolved = _resolve_log_file(log_file)
        if resolved != _order_logger_instance.log_file:
            _order_logger_instance.log_file = resolved
            resolved.parent.mkdir(parents=True, exist_ok=True)
            _order_logger_instance._active_day = \
                _order_logger_instance._file_utc_day(resolved)
    return _order_logger_instance


class _LazyOrderLogger:
    """Proxy that defers OrderLoggerV1 creation until first use."""

    def __init__(self) -> None:
        self._log_file_override: Optional[Path] = None

    @property
    def log_file(self) -> Path:
        if _order_logger_instance is None:
            return self._log_file_override or _resolve_log_file()
        return get_order_logger().log_file

    @log_file.setter
    def log_file(self, value: Union[str, Path]) -> None:
        if _order_logger_instance is None:
            self._log_file_override = _resolve_log_file(value)
            return
        get_order_logger().log_file = _resolve_log_file(value)

    def write(self, entry: Dict[str, Any]) -> None:
        logger = get_order_logger(log_file=self._log_file_override)
        self._log_file_override = None
        logger.write(entry)

    def __getattr__(self, name: str) -> Any:
        logger = get_order_logger(log_file=self._log_file_override)
        self._log_file_override = None
        return getattr(logger, name)


order_logger = _LazyOrderLogger()
