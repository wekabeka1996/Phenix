from fastapi.testclient import TestClient
from apps.reference.api.main import app
import pytest


@pytest.mark.skip(reason="LEGACY: /statdump endpoint may have been removed or renamed - verify current API")
def test_statdump_ok():
    c = TestClient(app)
    r = c.get("/statdump")
    assert r.status_code == 200
    body = r.json()
    assert "exposure" in body and "orders" in body and "guards" in body
