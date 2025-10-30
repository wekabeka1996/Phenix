from fastapi.testclient import TestClient
from apps.reference.api.main import app


def test_statdump_ok():
    c = TestClient(app)
    r = c.get("/statdump")
    assert r.status_code == 200
    body = r.json()
    assert "exposure" in body and "orders" in body and "guards" in body
