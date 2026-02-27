import json
import logging
import logging.handlers
import os
from datetime import datetime
from typing import Any, Dict, Optional

LOGGER_NAME = "apps.reference.domains.decision_making.dm_log_adapter"
_DM_MAX_BYTES = 10_000_000
_DM_BACKUP_COUNT = 100  # backupCount=100 (policy assertion in tests)


def _ensure_dir(p: str) -> None:
    d = os.path.dirname(p)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _get_log_path() -> str:
    log_dir = os.environ["DM_LOG_DIR"] if "DM_LOG_DIR" in os.environ else "logs"
    return os.path.join(log_dir, "domain_decision_making.log")


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _handler_targets_path(handler: logging.Handler, log_path: str) -> bool:
    base = getattr(handler, "baseFilename", None)
    if not isinstance(base, str):
        return False
    return _same_path(base, log_path)


def _root_has_handler_for_path(log_path: str) -> bool:
    root = logging.getLogger()
    return any(_handler_targets_path(h, log_path) for h in root.handlers)


def _drop_local_rotating_handlers(lg: logging.Logger) -> None:
    for h in lg.handlers[:]:
        if isinstance(h, logging.handlers.RotatingFileHandler):
            lg.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass


def _get_logger() -> logging.Logger:
    lg = logging.getLogger(LOGGER_NAME)
    lg.setLevel(logging.INFO)
    log_path = os.path.abspath(_get_log_path())
    _ensure_dir(log_path)

    # If centralized logging already owns this file, do not open a second handler.
    # Windows cannot rename an in-use file during RotatingFileHandler rollover.
    if _root_has_handler_for_path(log_path):
        _drop_local_rotating_handlers(lg)
        lg.propagate = True
        return lg

    # Fallback mode (tests/standalone): keep local rotating file sink.
    _drop_local_rotating_handlers(lg)
    fh = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=_DM_MAX_BYTES,
        backupCount=_DM_BACKUP_COUNT,
        encoding="utf-8",
        delay=False,
    )
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)
    lg.addHandler(fh)
    lg.propagate = False
    return lg


class DecisionLog:
    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._lg = logger or _get_logger()

    def write(self, event: str, rid: Optional[str], payload: Dict[str, Any]) -> None:
        # Handle late logging setup: if root starts owning DM log path, drop local file handler.
        # This avoids duplicate file handles on Windows rollover.
        if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in self._lg.handlers):
            if _root_has_handler_for_path(os.path.abspath(_get_log_path())):
                self._lg = _get_logger()

        rec = {
            "ts": int(datetime.utcnow().timestamp() * 1000),
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
