import json
import os
import time
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict
from unittest import mock

import jsonschema

from vfoundation.config import config


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


class OrderLoggerV1:
    """L1 Order Logger - Unified order lifecycle logging with schema validation."""

    def __init__(self, log_file: str = "logs/order_log_v1.jsonl"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Load schema
        schema_path = Path("apps/reference/schemas/order_logger_v1.json")
        with open(schema_path, 'r', encoding='utf-8') as f:
            self.schema = json.load(f)

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
order_logger = OrderLoggerV1()
