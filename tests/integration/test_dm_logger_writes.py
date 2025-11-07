import os
import json
import tempfile
import shutil
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
