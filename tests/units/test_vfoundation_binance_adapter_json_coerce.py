import asyncio
import pytest
from types import SimpleNamespace
from apps.reference.adapters import binance_adapter as ba


class DummyResp:
    def __init__(self, payload): self._p = payload
    def json(self): return self._p


@pytest.mark.anyio
async def test__coerce_json_variants():
    d = {"serverTime": 123}
    assert await ba._coerce_json(d) == d
    assert await ba._coerce_json(DummyResp(d)) == d
    assert await ba._coerce_json(b'{"serverTime": 123}') == d
    assert await ba._coerce_json('{"serverTime": 123}') == d
