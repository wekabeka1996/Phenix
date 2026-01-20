import json
import os
import time
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional, Union
from unittest import mock

import jsonschema


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


class OrderLoggerV1:
    """L1 Order Logger - Unified order lifecycle logging with schema validation."""

    def __init__(self, log_file: str = "logs/order_log_v1.jsonl"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Load schema
        with open(_schema_path(), 'r', encoding='utf-8') as f:
            self.schema = json.load(f)

        # Write boot record to mark session start (observability marker)
        self._write_boot_record()

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
        with open(self.log_file, 'a', encoding='utf-8') as f:
            json.dump(boot_record, f, ensure_ascii=False)
            f.write('\n')

    def write(self, entry: Dict[str, Any]) -> None:
        """Write order log entry with optional schema validation."""
        entry = _to_jsonable(entry)
        # Add timestamp if not provided
        if "timestamp" not in entry:
            entry["timestamp"] = int(time.time() * 1000)  # milliseconds

        # Validate schema in DEBUG/TEST modes
        env = os.getenv("ENV", "").upper()
        if env in ("DEBUG", "TEST"):
            try:
                jsonschema.validate(instance=entry, schema=self.schema)
            except jsonschema.ValidationError as e:
                raise ValueError(f"Schema validation failed: {e}") from e

        # Write to JSONL file
        with open(self.log_file, 'a', encoding='utf-8') as f:
            json.dump(entry, f, ensure_ascii=False)
            f.write('\n')


# Global instance
_order_logger_instance: Optional[OrderLoggerV1] = None


def get_order_logger(log_file: Optional[Union[str, Path]] = None) -> OrderLoggerV1:
    """Return a singleton OrderLoggerV1, initialized lazily."""
    global _order_logger_instance
    if _order_logger_instance is None:
        if log_file is None:
            _order_logger_instance = OrderLoggerV1()
        else:
            _order_logger_instance = OrderLoggerV1(log_file=str(log_file))
    elif log_file is not None:
        _order_logger_instance.log_file = Path(log_file)
    return _order_logger_instance


class _LazyOrderLogger:
    """Proxy that defers OrderLoggerV1 creation until first use."""

    def __init__(self) -> None:
        self._log_file_override: Optional[Path] = None

    @property
    def log_file(self) -> Path:
        if _order_logger_instance is None:
            return self._log_file_override or Path("logs/order_log_v1.jsonl")
        return get_order_logger().log_file

    @log_file.setter
    def log_file(self, value: Union[str, Path]) -> None:
        if _order_logger_instance is None:
            self._log_file_override = Path(value)
            return
        get_order_logger().log_file = Path(value)

    def write(self, entry: Dict[str, Any]) -> None:
        logger = get_order_logger(log_file=self._log_file_override)
        self._log_file_override = None
        logger.write(entry)

    def __getattr__(self, name: str) -> Any:
        logger = get_order_logger(log_file=self._log_file_override)
        self._log_file_override = None
        return getattr(logger, name)


order_logger = _LazyOrderLogger()
