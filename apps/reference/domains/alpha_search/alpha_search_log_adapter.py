import json
import logging
import logging.handlers
import os
from datetime import datetime
from typing import Any, Dict, Optional

LOGGER_NAME = "domain.alpha_search"


def _ensure_dir(p: str) -> None:
    d = os.path.dirname(p)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _get_log_path() -> str:
    log_dir = os.environ.get("ALPHA_SEARCH_LOG_DIR", "logs")
    return os.path.join(log_dir, "domain_alpha_search.log")


def _get_logger() -> logging.Logger:
    lg = logging.getLogger(LOGGER_NAME)
    lg.setLevel(logging.INFO)
    # Remove existing rotating handlers to respect env changes
    for h in lg.handlers[:]:
        if isinstance(h, logging.handlers.RotatingFileHandler):
            lg.removeHandler(h)

    log_path = _get_log_path()
    _ensure_dir(log_path)
    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5_000_000, backupCount=5, encoding="utf-8", delay=False
    )
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)
    lg.addHandler(fh)
    lg.propagate = False
    return lg


class AlphaSearchLog:
    """Dedicated structured log for alpha_search domain.

    Writes JSON records to logs/domain_alpha_search.log with provider_id
    and symbol as top-level fields for easy filtering.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._lg = logger or _get_logger()

    def write(
        self,
        event: str,
        provider_id: str,
        symbol: str,
        payload: Dict[str, Any],
        signal_id: Optional[str] = None,
    ) -> None:
        rec = {
            "ts": int(datetime.utcnow().timestamp() * 1000),
            "event": event,
            "provider_id": provider_id,
            "symbol": symbol,
            "signal_id": signal_id,
            **payload,
        }
        self._lg.info(json.dumps(
            rec, ensure_ascii=False, separators=(",", ":")))
        for h in self._lg.handlers:
            try:
                h.flush()
            except Exception:
                pass
