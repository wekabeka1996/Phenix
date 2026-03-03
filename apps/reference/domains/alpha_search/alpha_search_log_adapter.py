import json
import logging
import logging.handlers
import os
import shutil
import threading
from datetime import datetime
from typing import Any, Dict, Optional

LOGGER_NAME = "domain.alpha_search"
_ALPHA_MAX_BYTES = 10_000_000
_ALPHA_BACKUP_COUNT = 100  # backupCount=100 (policy assertion in tests)
_LOGGER_INIT_LOCK = threading.Lock()


class SafeRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """
    Windows-friendly rotating handler.

    On Windows, `os.rename()` can fail with WinError 32 when another process
    keeps the base log file open. As a fallback, use copy+truncate ("copytruncate")
    to avoid renaming the active file.
    """

    def rotate(self, source: str, dest: str) -> None:
        try:
            os.rename(source, dest)
            return
        except PermissionError:
            pass

        # Fallback: copy current contents to dest and truncate source in-place.
        # This avoids renaming the active file, which requires delete-sharing.
        try:
            if self.stream:
                try:
                    self.stream.flush()
                except Exception:
                    pass

            shutil.copyfile(source, dest)

            if self.stream:
                self.stream.seek(0)
                self.stream.truncate(0)
                try:
                    self.stream.flush()
                except Exception:
                    pass
        except Exception:
            # Preserve the original semantics: rotation failure should raise.
            raise


def _ensure_dir(p: str) -> None:
    d = os.path.dirname(p)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _get_log_path() -> str:
    log_dir = os.environ.get("ALPHA_SEARCH_LOG_DIR", "logs")
    return os.path.join(log_dir, "domain_alpha_search.log")


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


def _close_handler(handler: logging.Handler) -> None:
    try:
        handler.close()
    except Exception:
        pass


def _drop_local_rotating_handlers(lg: logging.Logger) -> None:
    for h in lg.handlers[:]:
        if isinstance(h, logging.handlers.RotatingFileHandler):
            lg.removeHandler(h)
            _close_handler(h)


def _sync_local_rotating_handler(lg: logging.Logger, log_path: str) -> None:
    keeper = None
    for h in lg.handlers[:]:
        if isinstance(h, logging.handlers.RotatingFileHandler):
            if keeper is None and _handler_targets_path(h, log_path):
                keeper = h
                continue
            lg.removeHandler(h)
            _close_handler(h)

    if keeper is not None:
        return

    fh = SafeRotatingFileHandler(
        log_path,
        maxBytes=_ALPHA_MAX_BYTES,
        backupCount=_ALPHA_BACKUP_COUNT,
        encoding="utf-8",
        delay=False,
    )
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)
    lg.addHandler(fh)


def _get_logger() -> logging.Logger:
    lg = logging.getLogger(LOGGER_NAME)
    lg.setLevel(logging.INFO)
    log_path = os.path.abspath(_get_log_path())
    _ensure_dir(log_path)

    with _LOGGER_INIT_LOCK:
        # If centralized logging already owns this file, avoid a duplicate handle.
        if _root_has_handler_for_path(log_path):
            _drop_local_rotating_handlers(lg)
            lg.propagate = True
            return lg

        _sync_local_rotating_handler(lg, log_path)
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
        # Handle late centralized logging setup without duplicate file ownership.
        if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in self._lg.handlers):
            if _root_has_handler_for_path(os.path.abspath(_get_log_path())):
                self._lg = _get_logger()

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
