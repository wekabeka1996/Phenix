import json, logging, logging.handlers, os
from datetime import datetime
from typing import Any, Dict, Optional

LOGGER_NAME = "domain.decision_making"


def _ensure_dir(p: str) -> None:
    d = os.path.dirname(p)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _get_log_path() -> str:
    log_dir = os.environ.get("DM_LOG_DIR", "logs")
    return os.path.join(log_dir, "domain_decision_making.log")


def _get_logger() -> logging.Logger:
    lg = logging.getLogger(LOGGER_NAME)
    lg.setLevel(logging.INFO)
    # Always recreate handler to respect DM_LOG_DIR changes
    # Remove existing handlers
    for h in lg.handlers[:]:
        if isinstance(h, logging.handlers.RotatingFileHandler):
            lg.removeHandler(h)

    # Create new handler with current log path
    log_path = _get_log_path()
    _ensure_dir(log_path)
    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5_000_000, backupCount=5, encoding="utf-8", delay=False
    )
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)
    lg.addHandler(fh)
    lg.propagate = False
    return lg


class DecisionLog:
    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._lg = logger or _get_logger()

    def write(self, event: str, rid: Optional[str], payload: Dict[str, Any]) -> None:
        rec = {
            "ts": int(datetime.utcnow().timestamp() * 1000),
            "event": event,
            "rid": rid,
            **payload,
        }
        self._lg.info(json.dumps(rec, ensure_ascii=False, separators=(",", ":")))
        for h in self._lg.handlers:
            try:
                h.flush()
            except Exception:
                pass
