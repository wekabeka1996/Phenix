from __future__ import annotations

import threading
from typing import Any

try:
    from fastapi import FastAPI, Header, HTTPException
except ImportError:  # pragma: no cover
    FastAPI = None  # type: ignore
    Header = None  # type: ignore

    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

from vfoundation.dr import wal


if FastAPI is not None:
    app = FastAPI(
        title="Aurora Core Debug API",
        description="Development-only debug endpoints (imported when TRADING_ENV != 'production').",
        version="0.1.0",
    )
else:
    app = None  # type: ignore


# =============================================================================
# RBAC / AUTH (minimal)
# =============================================================================

_DEV_TOKENS = {"dev-token-123", "dev"}


def require_admin(authorization: str | None) -> bool:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=403, detail="forbidden")
    token = authorization.split(" ", 1)[1].strip()
    if token not in _DEV_TOKENS:
        raise HTTPException(status_code=403, detail="forbidden")
    return True


# =============================================================================
# ROUTER PERFORMANCE METRICS
# =============================================================================

_metrics_lock = threading.Lock()
_router_timings_ms: list[float] = []
_total_requests = 0
_timeout_count = 0


def record_router_timing(ms: float) -> None:
    global _total_requests
    with _metrics_lock:
        _total_requests += 1
        _router_timings_ms.append(float(ms))
        if len(_router_timings_ms) > 5000:
            del _router_timings_ms[:1000]


def record_timeout() -> None:
    global _total_requests, _timeout_count
    with _metrics_lock:
        _total_requests += 1
        _timeout_count += 1


def get_p95_router_time() -> float:
    with _metrics_lock:
        if not _router_timings_ms:
            return 0.0
        arr = sorted(_router_timings_ms)
        idx = int(len(arr) * 0.95)
        if idx >= len(arr):
            idx = len(arr) - 1
        return float(arr[idx])


def get_timeout_rate() -> float:
    with _metrics_lock:
        if _total_requests <= 0:
            return 0.0
        return float(_timeout_count / _total_requests)


# =============================================================================
# DRIFT REPORT STORAGE (ExecutionPosition drift monitor)
# =============================================================================

_drift_lock = threading.Lock()
_drift_reports: list[dict[str, Any]] = []


def add_drift_report(report: Any) -> None:
    """
    Store a DriftReport (apps/reference/domains/execution_position/drift_monitor.py).
    Keeps only last 100 reports.
    """
    if hasattr(report, "to_dict"):
        payload = report.to_dict()
    elif hasattr(report, "model_dump"):
        payload = report.model_dump()
    elif hasattr(report, "dict"):
        payload = report.dict()
    else:
        payload = dict(report)

    with _drift_lock:
        _drift_reports.append(payload)
        if len(_drift_reports) > 100:
            _drift_reports[:] = _drift_reports[-100:]


def _find_drift_report_for_rid(rid: str) -> dict[str, Any] | None:
    with _drift_lock:
        reports = list(_drift_reports)
    for report in reversed(reports):
        mismatches = report.get("mismatches") or []
        for mm in mismatches:
            if (mm or {}).get("rid") == rid:
                return report
    return None


# =============================================================================
# DEBUG ENDPOINT IMPLEMENTATIONS
# =============================================================================


def metrics() -> dict[str, Any]:
    with _drift_lock:
        reports = list(_drift_reports)

    tp_total = fp_total = fn_total = tn_total = 0
    drift_pct_last = 0.0
    accuracy_last = 0.0

    for r in reports:
        c = (r or {}).get("confusion") or {}
        tp_total += int(c.get("tp", 0) or 0)
        fp_total += int(c.get("fp", 0) or 0)
        fn_total += int(c.get("fn", 0) or 0)
        tn_total += int(c.get("tn", 0) or 0)

    if reports:
        last_conf = (reports[-1] or {}).get("confusion") or {}
        drift_pct_last = float(last_conf.get("drift_pct", 0.0) or 0.0)
        accuracy_last = float(last_conf.get("accuracy", 0.0) or 0.0)

    return {
        "router_p95_ms": get_p95_router_time(),
        "timeout_rate": get_timeout_rate(),
        "queue_depth": 0,
        "confusion_tp_total": tp_total,
        "confusion_fp_total": fp_total,
        "confusion_fn_total": fn_total,
        "confusion_tn_total": tn_total,
        "drift_pct_last": drift_pct_last,
        "accuracy_last": accuracy_last,
    }


def debug_rid(rid: str, authorization: str | None = None) -> dict[str, Any]:
    require_admin(authorization)
    events, why_chain, integrity_ok = wal.read_by_rid(rid)
    result: dict[str, Any] = {
        "rid": rid,
        "count": len(events),
        "events": events,
        "why_chain": why_chain,
        "integrity_ok": integrity_ok,
    }
    drift = _find_drift_report_for_rid(rid)
    if drift:
        result["drift_report"] = drift
    return result


# =============================================================================
# FastAPI routes
# =============================================================================

if FastAPI is not None:  # pragma: no cover
    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "healthy", "service": "aurora-core"}

    @app.get("/metrics/json")
    def metrics_json() -> dict[str, Any]:
        return metrics()

    @app.get("/debug/{rid}")
    def debug_rid_http(rid: str, authorization: str | None = Header(None)) -> dict[str, Any]:
        return debug_rid(rid, authorization=authorization)
