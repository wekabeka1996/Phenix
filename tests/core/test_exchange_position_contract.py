import types

import pytest

from apps.reference.adapters.binance_adapter import BinanceAdapter
from vfoundation.core.adapters.base import ExchangePosition


def test_exchange_position_from_payload_accepts_quantity_alias():
    payload = {
        "symbol": "SOLUSDT",
        "quantity": "1.25",
        "entryPrice": "100.5",
        "markPrice": "101.0",
        "unrealizedPnl": "0.5",
        "marginType": "isolated",
        "isolatedMargin": "25.0",
        "updateTime": 1700000000000,
        "positionSide": "BOTH",
    }

    position = ExchangePosition.from_payload(payload)

    assert position.symbol == "SOLUSDT"
    assert position.position_amount == "1.25"
    assert position.side == "LONG"
    assert position.entry_price == "100.5"
    assert position.unrealized_profit == "0.5"
    assert position.margin_type == "isolated"
    assert position.isolated_margin == 25.0
    assert position.update_time_ms == 1700000000000


@pytest.mark.asyncio
async def test_binance_adapter_get_open_positions_converts_payload(monkeypatch):
    adapter = BinanceAdapter(api_key="k", api_secret="secret")

    sample_response = [
        {
            "symbol": "SOLUSDT",
            "positionAmt": "2.0",
            "entryPrice": "100",
            "markPrice": "102",
            "unRealizedProfit": "4",
            "leverage": "20",
            "marginType": "cross",
            "isolatedMargin": "0",
            "updateTime": 1700000001000,
            "positionSide": "LONG",
        }
    ]

    async def fake_request(self, method, path, params):
        return sample_response

    adapter._request = types.MethodType(fake_request, adapter)
    adapter._get_fallback_backoff_ms = lambda: []

    positions = await adapter.get_open_positions()

    assert len(positions) == 1
    position = positions[0]
    assert isinstance(position, ExchangePosition)
    assert position.position_amount == "2.0"
    assert position.side == "LONG"
    assert position.entry_price == "100"
    assert position.leverage == 20
    assert position.margin_type.lower() == "cross"
