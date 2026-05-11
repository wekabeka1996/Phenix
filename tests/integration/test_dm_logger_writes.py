import os
import json
import tempfile
import shutil
import logging
from logging.handlers import RotatingFileHandler
from apps.reference.domains.decision_making.dm_log_adapter import (
    DecisionLog,
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


def test_dm_log_coexists_with_rotating_handler_on_same_file():
    d = tempfile.mkdtemp()
    os.environ["DM_LOG_DIR"] = d
    logger = logging.getLogger("test.dm.shared_file")
    logger.handlers.clear()
    logger.propagate = False
    handler = None
    try:
        path = os.path.join(d, "domain_decision_making.log")
        handler = RotatingFileHandler(
            path,
            maxBytes=256,
            backupCount=1,
            encoding="utf-8",
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        dlog = DecisionLog()
        for idx in range(40):
            logger.info("root-line-%s", idx)
            dlog.write("PORTFOLIO_RX", f"rid-{idx}", {"symbol": "BTCUSDT", "seq": idx})

        for active_handler in logger.handlers:
            active_handler.flush()

        files = [name for name in os.listdir(d) if name.startswith("domain_decision_making.log")]
        assert files

        combined = []
        for name in sorted(files):
            with open(os.path.join(d, name), "r", encoding="utf-8") as handle:
                combined.extend(handle.read().splitlines())

        dm_lines = [line for line in combined if '"event":"PORTFOLIO_RX"' in line]
        assert dm_lines
    finally:
        if handler is not None:
            handler.close()
        logger.handlers.clear()
        os.environ.pop("DM_LOG_DIR", None)
        shutil.rmtree(d, ignore_errors=True)
