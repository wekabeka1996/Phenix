import json
import os
import time
from pathlib import Path
from typing import Any, Dict

import jsonschema

from vfoundation.config import config


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
