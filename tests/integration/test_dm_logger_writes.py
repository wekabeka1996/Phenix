import os
import json
import tempfile
import shutil
import logging
from logging.handlers import RotatingFileHandler
from apps.reference.domains.decision_making.dm_log_adapter import (
    DecisionLog,
    LOGGER_NAME,
)


def test_dm_log_writes_line():
    d = tempfile.mkdtemp()
    os.environ["DM_LOG_DIR"] = d
    try:
        lg = DecisionLog()
        lg.write(
            "DECISION_SKIP", "rid-1", {"symbol": "ETHUSDT",
                                       "reason": "RISK_DISALLOWED"}
        )
        p = os.path.join(d, "domain_decision_making.log")
        assert os.path.exists(p)
        lines = open(p, "r", encoding="utf-8").read().strip().splitlines()
        assert lines
        rec = json.loads(lines[-1].split(" | ", 2)[-1])
        assert rec["event"] == "DECISION_SKIP"
        assert rec["reason"] == "RISK_DISALLOWED"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_dm_log_uses_root_owned_file_handler_without_local_duplicate():
    d = tempfile.mkdtemp()
    os.environ["DM_LOG_DIR"] = d
    p = os.path.join(d, "domain_decision_making.log")
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
        # Ensure stale local handlers from other tests do not affect this case.
        for h in lg.handlers[:]:
            lg.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass

        dlog = DecisionLog()
        dlog.write(
            "PORTFOLIO_RX",
            "rid-2",
            {"symbol": "BTCUSDT", "positions_count": 0},
        )

        # Critical assertion for WinError 32 fix:
        # DecisionLog must not keep a second RotatingFileHandler on same file.
        assert not any(isinstance(h, RotatingFileHandler) for h in dlog._lg.handlers)

        root_h.flush()
        assert os.path.exists(p)
        lines = open(p, "r", encoding="utf-8").read().strip().splitlines()
        assert lines
        rec = json.loads(lines[-1].split(" | ", 2)[-1])
        assert rec["event"] == "PORTFOLIO_RX"
        assert rec["symbol"] == "BTCUSDT"
    finally:
        root.removeHandler(root_h)
        try:
            root_h.close()
        except Exception:
            pass
        shutil.rmtree(d, ignore_errors=True)
