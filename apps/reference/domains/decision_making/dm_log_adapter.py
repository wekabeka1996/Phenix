"""Dedicated decision-domain file logger.

This adapter exists alongside the central logging stack because the decision
domain still has a small set of direct forensic writes that need a predictable
JSON payload and an overridable file location during tests.
"""

import json
import logging
import logging.handlers
import os
from typing import Any, Dict, Optional

from apps.reference.logging_setup import WinSafeRotatingFileHandler

LOGGER_NAME = "domain.decision_making"


def _ensure_dir(p: str) -> None:
    """Create the parent directory for a log file path if needed."""
    d = os.path.dirname(p)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _get_log_path() -> str:
    """Resolve the decision log path, honoring the test override env var."""
    log_dir = os.environ["DM_LOG_DIR"] if "DM_LOG_DIR" in os.environ else "logs"
    return os.path.join(log_dir, "domain_decision_making.log")


def _get_logger() -> logging.Logger:
    """Return a dedicated logger bound to the current decision log file.

    The handler is rebuilt on each call so tests and harnesses that mutate
    DM_LOG_DIR get a fresh sink without reusing a stale file handle.
    """
    lg = logging.getLogger(LOGGER_NAME)
    lg.setLevel(logging.INFO)

    # Rebuild only rotating-file handlers owned by this adapter so a changed
    # DM_LOG_DIR takes effect immediately.
    for h in lg.handlers[:]:
        if isinstance(h, logging.handlers.RotatingFileHandler):
            try:
                h.close()
            except Exception:
                pass
            lg.removeHandler(h)

    # Create new handler with current log path
    log_path = _get_log_path()
    _ensure_dir(log_path)
    fh = WinSafeRotatingFileHandler(
        log_path, maxBytes=5_000_000, backupCount=5, encoding="utf-8", delay=False
    )
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)
    lg.addHandler(fh)
    lg.propagate = False
    return lg


class DecisionLog:
    """Write structured decision-domain records to a dedicated rotating file."""

    def __init__(self, logger: Optional[logging.Logger] = None, *, clock: Optional["Clock"] = None) -> None:
        self._lg = logger or _get_logger()
        from apps.reference.core.time.clock import LiveClock
        self._clock = clock or LiveClock()

    def write(self, event: str, rid: Optional[str], payload: Dict[str, Any]) -> None:
        """Append a single JSON record and flush handlers best-effort."""
        rec = {
            "ts": int(self._clock.now_ms()),
            "event": event,
            "rid": rid,
            **payload,
        }
        self._lg.info(json.dumps(
            rec, ensure_ascii=False, separators=(",", ":")))
        for h in self._lg.handlers:
            try:
                h.flush()
            except Exception:
                pass
