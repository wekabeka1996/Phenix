import json
import logging
import os
import threading
from datetime import datetime
from typing import Any, Dict, Optional

LOGGER_NAME = "domain.decision_making"
_WRITE_LOCK = threading.Lock()


def _ensure_dir(p: str) -> None:
    d = os.path.dirname(p)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _get_log_path() -> str:
    log_dir = os.environ["DM_LOG_DIR"] if "DM_LOG_DIR" in os.environ else "logs"
    return os.path.join(log_dir, "domain_decision_making.log")


def _format_line(message: str) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"{timestamp} | INFO | {message}\n"


def _append_line(path: str, line: str) -> None:
    _ensure_dir(path)
    with _WRITE_LOCK:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line)


class DecisionLog:
    def __init__(self, logger: Optional[logging.Logger] = None, *, clock: Optional["Clock"] = None) -> None:
        self._lg = logger
        self._log_path = _get_log_path()
        from apps.reference.core.time.clock import LiveClock
        self._clock = clock or LiveClock()

    def write(self, event: str, rid: Optional[str], payload: Dict[str, Any]) -> None:
        rec = {
            "ts": int(self._clock.now_ms()),
            "event": event,
            "rid": rid,
            **payload,
        }
        message = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
        if self._lg is not None:
            self._lg.info(message)
            for h in self._lg.handlers:
                try:
                    h.flush()
                except Exception:
                    pass
            return

        _append_line(self._log_path, _format_line(message))
