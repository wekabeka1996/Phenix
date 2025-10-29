from __future__ import annotations
import json
import time
import sys
import logging
import logging.handlers
from typing import Any
from pathlib import Path
from datetime import datetime


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Create timestamp in ISO 8601 format with microseconds
        dt = datetime.fromtimestamp(record.created)
        timestamp = dt.isoformat() + 'Z'

        # Create base log entry
        log_entry = {
            "ts": timestamp,
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage()
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields if any
        if hasattr(record, '__dict__'):
            for key, value in record.__dict__.items():
                if key not in ('name', 'msg', 'args', 'levelname', 'levelno',
                             'pathname', 'filename', 'module', 'exc_info',
                             'exc_text', 'stack_info', 'lineno', 'funcName',
                             'created', 'msecs', 'relativeCreated', 'thread',
                             'threadName', 'processName', 'process', 'message'):
                    log_entry[key] = value

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(config: Any) -> None:
    """Setup centralized logging configuration.

    Args:
        config: Configuration object with logging section
    """
    # Get logging config from system section
    logging_config = config.system.get('logging', {})

    # Default values
    log_level = logging_config.get('level', 'INFO').upper()
    log_file = logging_config.get('file', 'logs/aurora_core.log')
    logging_config.get('format', 'json')
    rotation_config = logging_config.get('rotation', {})
    max_bytes = rotation_config.get('max_bytes', 10 * 1024 * 1024)  # 10 MB
    backup_count = rotation_config.get('backup_count', 5)

    # Create logs directory if it doesn't exist
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Clear existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Set log level
    root_logger.setLevel(getattr(logging, log_level))

    # Console handler with text format
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(getattr(logging, log_level))
    root_logger.addHandler(console_handler)

    # File handler with JSON format
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    json_formatter = JsonFormatter()
    file_handler.setFormatter(json_formatter)
    file_handler.setLevel(getattr(logging, log_level))
    root_logger.addHandler(file_handler)


def log_event(**fields: Any) -> None:
    """Legacy log event function for backward compatibility."""
    base = {
        "ts": int(time.time()*1000),
    }
    base.update(fields)
    sys.stdout.write(json.dumps(base, ensure_ascii=False) + "\n")
