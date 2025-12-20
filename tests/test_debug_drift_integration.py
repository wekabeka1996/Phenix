"""
Tests for drift_report integration in /debug/{rid} endpoint.
"""

import pathlib
import tempfile
from vfoundation.dr import wal
from apps.monitoring.drift_monitor import (
    DriftReport,
    ConfusionMatrix,
    Mismatch,
)
from vfoundation.obs.debug_api import (
    debug_rid,
    add_drift_report,
    _drift_reports,
    _drift_lock,
)
import pytest
import time
import sys
from pathlib import Path
from unittest.mock import patch

# Add vfoundation to path
sys.path.insert(0, str(Path(__file__).parent.parent / "vfoundation"))


@pytest.fixture(autouse=True)
def setup_wal_and_clear_drift():
    """Setup temporary WAL dir and clear drift reports"""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal.set_wal_dir(pathlib.Path(tmpdir))

        with _drift_lock:
            _drift_reports.clear()

        yield

        with _drift_lock:
            _drift_reports.clear()


def test_debug_without_drift_report():
    """Test /debug/{rid} returns normal response without drift_report when no match"""
    rid = "test-rid-no-drift"

    # Write a WAL entry for this RID
    wal.append({"rid": rid, "op": "ASK", "verb": "TEST", "why": "test message"})

    # Call debug endpoint (mock authorization)
    with patch("vfoundation.obs.debug_api.require_admin", return_value=True):
        result = debug_rid(rid, authorization="Bearer dev-token-123")

    assert result["rid"] == rid
    assert result["count"] >= 1
    assert "events" in result
    assert "why_chain" in result
    assert "integrity_ok" in result
    # ✅ ВИДАЛЕНО: merkle_root більше не включається у відповідь (schema evolution)

    # No drift_report should be present
    assert "drift_report" not in result


def test_debug_with_matching_drift_report():
    """Test /debug/{rid} includes drift_report when RID matches a mismatch"""
    rid = "test-rid-with-drift"

    # Write WAL entry
    wal.append({"rid": rid, "op": "DEC", "verb": "OPEN", "why": "shadow open"})

    # Create drift report with mismatch for this RID
    mismatch = Mismatch(
        rid=rid,
        symbol="BTCUSDT",
        type="FP",
        decision_verb="OPEN",
        event_verb=None,
        timestamp=time.time(),
    )

    confusion = ConfusionMatrix(tp=10, fp=1, fn=0, tn=0)
    report = DriftReport(
        confusion=confusion, mismatches=[mismatch], records_processed=11
    )

    add_drift_report(report)

    # Call debug endpoint
    with patch("vfoundation.obs.debug_api.require_admin", return_value=True):
        result = debug_rid(rid, authorization="Bearer dev-token-123")

    assert result["rid"] == rid
    assert "drift_report" in result

    drift = result["drift_report"]
    assert "confusion" in drift
    assert drift["confusion"]["tp"] == 10
    assert drift["confusion"]["fp"] == 1
    assert drift["confusion"]["fn"] == 0
    assert drift["confusion"]["tn"] == 0

    assert "mismatches" in drift
    assert len(drift["mismatches"]) == 1
    assert drift["mismatches"][0]["rid"] == rid
    assert drift["mismatches"][0]["type"] == "FP"
    assert drift["mismatches"][0]["decision_verb"] == "OPEN"

    assert "computed_at" in drift
    assert "records_processed" in drift
    assert drift["records_processed"] == 11


def test_debug_with_multiple_reports_finds_matching():
    """Test /debug/{rid} finds correct report when multiple exist"""
    rid1 = "rid-one"
    rid2 = "rid-two"

    # WAL entries
    wal.append({"rid": rid1, "op": "DEC", "verb": "OPEN", "why": "open one"})
    wal.append({"rid": rid2, "op": "DEC", "verb": "CLOSE", "why": "close two"})

    # Report 1 with mismatch for rid1
    mismatch1 = Mismatch(rid=rid1, symbol="BTCUSDT",
                         type="FP", decision_verb="OPEN")
    confusion1 = ConfusionMatrix(tp=5, fp=1, fn=0, tn=0)
    report1 = DriftReport(
        confusion=confusion1, mismatches=[mismatch1], records_processed=6
    )

    # Report 2 with mismatch for rid2
    mismatch2 = Mismatch(rid=rid2, symbol="ETHUSDT",
                         type="FN", event_verb="CANCELLED")
    confusion2 = ConfusionMatrix(tp=10, fp=0, fn=1, tn=0)
    report2 = DriftReport(
        confusion=confusion2, mismatches=[mismatch2], records_processed=11
    )

    add_drift_report(report1)
    add_drift_report(report2)

    # Debug for rid1 should find report1
    with patch("vfoundation.obs.debug_api.require_admin", return_value=True):
        result1 = debug_rid(rid1, authorization="Bearer dev-token-123")
    assert "drift_report" in result1
    assert result1["drift_report"]["confusion"]["tp"] == 5
    assert result1["drift_report"]["confusion"]["fp"] == 1

    # Debug for rid2 should find report2
    with patch("vfoundation.obs.debug_api.require_admin", return_value=True):
        result2 = debug_rid(rid2, authorization="Bearer dev-token-123")
    assert "drift_report" in result2
    assert result2["drift_report"]["confusion"]["tp"] == 10
    assert result2["drift_report"]["confusion"]["fn"] == 1


def test_debug_limits_mismatches_to_5():
    """Test /debug/{rid} drift_report limits mismatches to 5"""
    rid = "rid-many-mismatches"

    wal.append({"rid": rid, "op": "DEC", "verb": "OPEN", "why": "test"})

    # Create report with 10 mismatches (all for same RID)
    mismatches = [
        Mismatch(rid=rid, symbol=f"SYM{i}", type="FP", decision_verb="OPEN")
        for i in range(10)
    ]

    confusion = ConfusionMatrix(tp=0, fp=10, fn=0, tn=0)
    report = DriftReport(
        confusion=confusion, mismatches=mismatches, records_processed=10
    )

    add_drift_report(report)

    with patch("vfoundation.obs.debug_api.require_admin", return_value=True):
        result = debug_rid(rid, authorization="Bearer dev-token-123")

    assert "drift_report" in result
    # Should limit to 5 mismatches
    assert len(result["drift_report"]["mismatches"]) == 5


def test_debug_requires_rbac_token():
    """Test /debug/{rid} enforces RBAC (covered by test_security_xai_tighten.py)"""
    # This test ensures integration doesn't break RBAC
    rid = "test-rid-rbac"

    with pytest.raises(Exception):  # HTTPException 403
        debug_rid(rid, authorization="Bearer invalid-token")
