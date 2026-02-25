"""
Tests for vfoundation.obs.debug_api.

Covers: require_admin RBAC, router timing metrics, drift report storage,
debug_rid, metrics() aggregation, FastAPI route stubs.

IMPORTANT: autouse fixture resets 4 module-level globals before each test
to prevent state leakage across tests (xdist-safe).
"""
from __future__ import annotations

from typing import Any, Dict, Generator
from unittest.mock import MagicMock, patch

import pytest

import vfoundation.obs.debug_api as api
from vfoundation.obs.debug_api import (
    HTTPException,
    add_drift_report,
    debug_rid,
    get_p95_router_time,
    get_timeout_rate,
    metrics,
    record_router_timing,
    record_timeout,
    require_admin,
)


# ─────────────────────────────────────────────────────────────────────────────
# Autouse fixture: reset all module-level mutable state before each test
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_debug_api_globals() -> Generator[None, None, None]:
    """
    Reset all 4 mutable module-level globals in debug_api before each test.
    This ensures full test isolation (xdist-safe).
    """
    api._router_timings_ms.clear()
    api._drift_reports.clear()
    api._total_requests = 0
    api._timeout_count = 0
    yield
    # clean up after test too
    api._router_timings_ms.clear()
    api._drift_reports.clear()
    api._total_requests = 0
    api._timeout_count = 0


# ─────────────────────────────────────────────────────────────────────────────
# TestRequireAdmin
# ─────────────────────────────────────────────────────────────────────────────


class TestRequireAdmin:
    """Tests for require_admin RBAC guard."""

    def test_valid_bearer_token_dev_returns_true(self) -> None:
        """Valid token 'dev' with Bearer scheme should return True."""
        result = require_admin("Bearer dev")
        assert result is True

    def test_valid_bearer_token_dev_token_123(self) -> None:
        """Valid token 'dev-token-123' should return True."""
        result = require_admin("Bearer dev-token-123")
        assert result is True

    def test_no_authorization_raises_403(self) -> None:
        """Missing authorization header should raise HTTPException 403."""
        with pytest.raises(HTTPException) as exc_info:
            require_admin(None)
        assert exc_info.value.status_code == 403

    def test_empty_authorization_raises_403(self) -> None:
        """Empty string authorization should raise HTTPException 403."""
        with pytest.raises(HTTPException) as exc_info:
            require_admin("")
        assert exc_info.value.status_code == 403

    def test_wrong_scheme_raises_403(self) -> None:
        """Non-Bearer scheme should raise HTTPException 403."""
        with pytest.raises(HTTPException) as exc_info:
            require_admin("Basic dev")
        assert exc_info.value.status_code == 403

    def test_invalid_token_raises_403(self) -> None:
        """Unknown token should raise HTTPException 403."""
        with pytest.raises(HTTPException) as exc_info:
            require_admin("Bearer wrong-token-xyz")
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "forbidden"


# ─────────────────────────────────────────────────────────────────────────────
# TestRouterMetrics
# ─────────────────────────────────────────────────────────────────────────────


class TestRouterMetrics:
    """Tests for record_router_timing, record_timeout, get_p95_router_time, get_timeout_rate."""

    def test_record_router_timing_appends(self) -> None:
        """record_router_timing should append latency and increment total_requests."""
        assert api._total_requests == 0
        record_router_timing(5.0)
        assert api._total_requests == 1
        assert len(api._router_timings_ms) == 1

    def test_record_router_timing_multiple(self) -> None:
        """Multiple calls should accumulate in _router_timings_ms."""
        for ms in [1.0, 2.0, 3.0]:
            record_router_timing(ms)
        assert len(api._router_timings_ms) == 3
        assert api._total_requests == 3

    def test_get_p95_empty_returns_zero(self) -> None:
        """p95 with no samples should return 0.0."""
        result = get_p95_router_time()
        assert result == 0.0, f"expected 0.0 for empty timings, got {result}"

    def test_get_p95_single_sample(self) -> None:
        """p95 with a single sample should return that value."""
        record_router_timing(42.0)
        result = get_p95_router_time()
        assert result == pytest.approx(42.0)

    def test_get_p95_with_many_samples(self) -> None:
        """p95 with 100 samples should return value near the 95th percentile."""
        for i in range(100):
            record_router_timing(float(i))  # 0..99
        p95 = get_p95_router_time()
        assert 90 <= p95 <= 99, f"expected p95 in [90, 99], got {p95}"

    def test_record_timeout_increments_counts(self) -> None:
        """record_timeout should increment both _total_requests and _timeout_count."""
        record_timeout()
        assert api._total_requests == 1
        assert api._timeout_count == 1

    def test_get_timeout_rate_zero_when_no_requests(self) -> None:
        """timeout_rate with no requests should return 0.0."""
        assert get_timeout_rate() == 0.0

    def test_get_timeout_rate_calculation(self) -> None:
        """timeout_rate should be timeout_count / total_requests."""
        record_router_timing(1.0)   # 1 normal request
        record_timeout()             # 1 timeout
        rate = get_timeout_rate()
        assert rate == pytest.approx(0.5), f"expected 0.5, got {rate}"

    def test_router_timings_capped_at_5000(self) -> None:
        """_router_timings_ms should roll off oldest entries after 5000 samples."""
        for i in range(6000):
            api._router_timings_ms.append(float(i))
            api._total_requests += 1
        # Trigger cap by appending one more
        record_router_timing(9999.0)
        assert len(api._router_timings_ms) <= 5001, (
            f"expected timings capped, got {len(api._router_timings_ms)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TestDriftReportStorage
# ─────────────────────────────────────────────────────────────────────────────


class TestDriftReportStorage:
    """Tests for add_drift_report drift storage."""

    def _make_drift_report(self, rid: str = "test-rid") -> Dict[str, Any]:
        """Create a minimal drift report dict."""
        return {
            "mismatches": [{"rid": rid, "field": "price"}],
            "confusion": {"tp": 1, "fp": 0, "fn": 0, "tn": 0, "drift_pct": 0.0, "accuracy": 1.0},
        }

    def test_add_dict_report(self) -> None:
        """add_drift_report with dict input should append to _drift_reports."""
        add_drift_report(self._make_drift_report())
        assert len(api._drift_reports) == 1

    def test_add_model_dump_report(self) -> None:
        """add_drift_report with object having model_dump() should convert and store."""
        class FakeReport:
            def model_dump(self) -> Dict[str, Any]:
                return {"mismatches": [], "confusion": {}}

        add_drift_report(FakeReport())
        assert len(api._drift_reports) == 1

    def test_add_to_dict_report(self) -> None:
        """add_drift_report with object having dict() method should store correctly."""
        class OldReport:
            def dict(self) -> Dict[str, Any]:
                return {"mismatches": [], "confusion": {}}

        add_drift_report(OldReport())
        assert len(api._drift_reports) == 1

    def test_drift_reports_capped_at_100(self) -> None:
        """_drift_reports should roll off oldest after 100 entries."""
        for i in range(105):
            add_drift_report({"mismatches": [], "confusion": {}, "index": i})
        assert len(api._drift_reports) <= 100, (
            f"expected at most 100 drift reports, got {len(api._drift_reports)}"
        )

    def test_metrics_aggregation_from_drift_reports(self) -> None:
        """metrics() should aggregate TP/FP/FN/TN from drift reports."""
        report = {
            "mismatches": [],
            "confusion": {"tp": 5, "fp": 2, "fn": 1, "tn": 10, "drift_pct": 0.2, "accuracy": 0.9},
        }
        add_drift_report(report)
        m = metrics()
        assert m["confusion_tp_total"] >= 5
        assert m["confusion_fp_total"] >= 2
        assert m["accuracy_last"] == pytest.approx(0.9)
        assert m["drift_pct_last"] == pytest.approx(0.2)


# ─────────────────────────────────────────────────────────────────────────────
# TestDebugRid
# ─────────────────────────────────────────────────────────────────────────────


class TestDebugRid:
    """Tests for debug_rid function."""

    def test_debug_rid_requires_auth(self) -> None:
        """debug_rid with no auth should raise HTTPException 403."""
        with pytest.raises(HTTPException) as exc_info:
            debug_rid("some-rid", authorization=None)
        assert exc_info.value.status_code == 403

    def test_debug_rid_valid_returns_dict(self) -> None:
        """debug_rid with valid auth should return dict with rid, count, events."""
        mock_events = [{"rid": "r1", "op": "ASK"}]
        mock_why = [{"rid": "r1", "why": "test"}]
        with patch("vfoundation.obs.debug_api.wal.read_by_rid") as mock_read:
            mock_read.return_value = (mock_events, mock_why, True)
            result = debug_rid("r1", authorization="Bearer dev")
        assert result["rid"] == "r1"
        assert result["count"] == len(mock_events)
        assert result["integrity_ok"] is True
        assert "events" in result
        assert "why_chain" in result

    def test_debug_rid_includes_drift_when_present(self) -> None:
        """debug_rid should include drift_report key if relevant drift exists."""
        rid = "drift-test-rid"
        drift = {
            "mismatches": [{"rid": rid, "field": "price"}],
            "confusion": {"tp": 1, "fp": 0, "fn": 0, "tn": 0},
        }
        add_drift_report(drift)
        with patch("vfoundation.obs.debug_api.wal.read_by_rid") as mock_read:
            mock_read.return_value = ([], [], True)
            result = debug_rid(rid, authorization="Bearer dev")
        assert "drift_report" in result, "expected drift_report in result when drift exists for rid"

    def test_debug_rid_no_drift_when_not_present(self) -> None:
        """debug_rid should NOT include drift_report when no matching drift exists."""
        with patch("vfoundation.obs.debug_api.wal.read_by_rid") as mock_read:
            mock_read.return_value = ([], [], True)
            result = debug_rid("unknown-rid", authorization="Bearer dev")
        assert "drift_report" not in result


# ─────────────────────────────────────────────────────────────────────────────
# TestMetrics
# ─────────────────────────────────────────────────────────────────────────────


class TestMetrics:
    """Tests for metrics() aggregation function."""

    def test_metrics_structure(self) -> None:
        """metrics() should return all required keys."""
        result = metrics()
        required_keys = [
            "router_p95_ms", "timeout_rate", "queue_depth",
            "confusion_tp_total", "confusion_fp_total",
            "confusion_fn_total", "confusion_tn_total",
            "drift_pct_last", "accuracy_last",
        ]
        for key in required_keys:
            assert key in result, f"expected '{key}' in metrics() output"

    def test_metrics_empty_state(self) -> None:
        """metrics() with no data should return zeroes."""
        result = metrics()
        assert result["router_p95_ms"] == 0.0
        assert result["timeout_rate"] == 0.0
        assert result["drift_pct_last"] == 0.0
        assert result["accuracy_last"] == 0.0

    def test_metrics_with_timing(self) -> None:
        """metrics() should reflect recorded router timings."""
        for ms in [10.0, 20.0, 30.0]:
            record_router_timing(ms)
        result = metrics()
        assert result["router_p95_ms"] > 0, "expected non-zero p95 after recording timings"

    def test_metrics_multiple_drift_reports_aggregate(self) -> None:
        """metrics() should sum TP/FP/FN/TN across all drift reports."""
        for _ in range(3):
            add_drift_report({
                "mismatches": [],
                "confusion": {"tp": 2, "fp": 1, "fn": 0, "tn": 3},
            })
        result = metrics()
        assert result["confusion_tp_total"] == 6, f"expected 6 TP, got {result['confusion_tp_total']}"
        assert result["confusion_fp_total"] == 3, f"expected 3 FP, got {result['confusion_fp_total']}"
