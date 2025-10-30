# tests/integration/test_metrics_endpoint.py
from fastapi.testclient import TestClient
from apps.reference.api.main import app


def test_metrics_endpoint_ok():
    c = TestClient(app)
    r = c.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert "exposure_equity_usd" in body
    assert "fsm_guard_rejects_total" in body
