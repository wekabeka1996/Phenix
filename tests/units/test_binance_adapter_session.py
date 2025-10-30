import asyncio
import pytest
import httpx

from vfoundation.adapters.binance_adapter import BinanceAdapter

@pytest.mark.asyncio
async def test_adapter_exposes_session_and_uses_request(monkeypatch):
    calls = {}

    class DummyResponse:
        def __init__(self, status_code=200, json_data=None):
            self.status_code = status_code
            self._json_data = json_data or {"ok": True}

        def json(self):
            return self._json_data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("Error", request=None, response=self)

    class DummyClient(httpx.AsyncClient):
        async def request(self, method, url, **kw):
            calls["method"] = method
            calls["url"] = url

            # Mock different endpoints
            if "/fapi/v1/time" in url:
                return DummyResponse(json_data={"serverTime": 1234567890000})
            elif "/fapi/v2/balance" in url:
                return DummyResponse(json_data={"ok": True})
            else:
                return DummyResponse(json_data={"ok": True})

    client = DummyClient(base_url="https://fapi.binance.com")
    ad = BinanceAdapter(api_key="k", api_secret="s", session=client)

    assert hasattr(ad, "session"), "Adapter must expose .session"
    resp = await ad.get_account_balance()
    assert resp == {"ok": True}
    assert calls["method"] == "GET"
    assert "/fapi/v2/balance" in calls["url"]

    await ad.aclose()
