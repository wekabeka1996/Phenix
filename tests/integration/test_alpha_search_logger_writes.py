import json
import logging
import os
import shutil
import tempfile
from logging.handlers import RotatingFileHandler

from apps.reference.domains.alpha_search.alpha_search_log_adapter import (
    AlphaSearchLog,
    LOGGER_NAME,
)


def _drop_handlers(logger: logging.Logger) -> None:
    for h in logger.handlers[:]:
        logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass


def test_alpha_search_log_writes_line():
    d = tempfile.mkdtemp()
    os.environ["ALPHA_SEARCH_LOG_DIR"] = d
    lg = logging.getLogger(LOGGER_NAME)
    _drop_handlers(lg)
    try:
        dlog = AlphaSearchLog()
        dlog.write(
            "SCORE_EMITTED",
            "aurora",
            "SOLUSDT",
            {"score": 0.42, "threshold": 0.13, "shadow": True},
            signal_id="sig-1",
        )
        p = os.path.join(d, "domain_alpha_search.log")
        assert os.path.exists(p)
        lines = open(p, "r", encoding="utf-8").read().strip().splitlines()
        assert lines
        rec = json.loads(lines[-1].split(" | ", 2)[-1])
        assert rec["event"] == "SCORE_EMITTED"
        assert rec["provider_id"] == "aurora"
        assert rec["symbol"] == "SOLUSDT"
        assert rec["score"] == 0.42
    finally:
        _drop_handlers(lg)
        shutil.rmtree(d, ignore_errors=True)


def test_alpha_search_log_uses_root_owned_file_handler_without_local_duplicate():
    d = tempfile.mkdtemp()
    os.environ["ALPHA_SEARCH_LOG_DIR"] = d
    p = os.path.join(d, "domain_alpha_search.log")

    lg = logging.getLogger(LOGGER_NAME)
    root = logging.getLogger()
    root_h = RotatingFileHandler(
        p,
        maxBytes=10_000_000,
        backupCount=100,
        encoding="utf-8",
    )
    root_h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    root.addHandler(root_h)
    try:
        _drop_handlers(lg)
        dlog = AlphaSearchLog()
        dlog.write(
            "SCORE_EMITTED",
            "aurora",
            "BTCUSDT",
            {"score": 1.0, "threshold": 0.19, "shadow": True},
            signal_id="sig-2",
        )

        # Critical assertion for Windows rollover: no duplicate local file sink.
        assert not any(isinstance(h, RotatingFileHandler) for h in dlog._lg.handlers)

        root_h.flush()
        assert os.path.exists(p)
        lines = open(p, "r", encoding="utf-8").read().strip().splitlines()
        assert lines
        rec = json.loads(lines[-1].split(" | ", 2)[-1])
        assert rec["event"] == "SCORE_EMITTED"
        assert rec["symbol"] == "BTCUSDT"
    finally:
        root.removeHandler(root_h)
        try:
            root_h.close()
        except Exception:
            pass
        _drop_handlers(lg)
        shutil.rmtree(d, ignore_errors=True)


def test_alpha_search_log_closes_old_handler_when_log_dir_changes():
    d1 = tempfile.mkdtemp()
    d2 = tempfile.mkdtemp()
    lg = logging.getLogger(LOGGER_NAME)
    _drop_handlers(lg)
    try:
        os.environ["ALPHA_SEARCH_LOG_DIR"] = d1
        first = AlphaSearchLog()
        old = next(
            h
            for h in first._lg.handlers
            if isinstance(h, RotatingFileHandler)
        )
        assert getattr(old, "stream", None) is not None

        # Force path change; old handler must be removed and closed.
        os.environ["ALPHA_SEARCH_LOG_DIR"] = d2
        AlphaSearchLog()

        old_stream = getattr(old, "stream", None)
        assert old_stream is None or old_stream.closed
    finally:
        _drop_handlers(lg)
        shutil.rmtree(d1, ignore_errors=True)
        shutil.rmtree(d2, ignore_errors=True)
