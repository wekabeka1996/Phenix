import pytest
import asyncio
import time
import json
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
import httpx

from apps.reference.adapters.binance_adapter import BinanceAdapter, BinanceAPIError, ExchangeOrderParams

# Mock config
MOCK_CONFIG = {
    "recv_window_ms": 5000,
    "trading": {
        "execution": {
            "fallback": {
                "backoff_ms": [10, 20]
            }
        }
    }
}

@pytest.fixture
def adapter():
    client = BinanceAdapter(
        api_key="test_key",
        api_secret="test_secret",
        base_url="https://testnet.binancefuture.com",
        config=MOCK_CONFIG
    )
    # Mock session
    client.session = AsyncMock()
    client.session.request = AsyncMock()
    return client

@pytest.mark.asyncio
async def test_init(adapter):
    assert adapter.api_key == "test_key"
    assert adapter.api_secret == b"test_secret"
    assert adapter._recv_window_ms == 5000

def test_norm_params(adapter):
    params = {
        "a": 1,
        "b": "str",
        "c": Decimal("1.23400"),
        "d": True,
        "e": None
    }
    norm = adapter._norm_params(params)
    assert norm == {
        "a": "1",
        "b": "str",
        "c": "1.234",
        "d": "true"
    }

@pytest.mark.asyncio
async def test_sign_build(adapter):
    params = {"symbol": "BTCUSDT", "side": "BUY"}
    with patch("time.time", return_value=1600000000.0):
        qs, final = adapter._sign_build(params)
        
    assert "signature" in final
    assert final["timestamp"] == "1600000000000"
    assert "recvWindow" in final

@pytest.mark.asyncio
async def test_request_success(adapter):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"id": 123})
    # Make json awaitable if needed (though MagicMock isn't by default, the adapter handles it)
    # But _coerce_json handles sync json() too.
    
    adapter.session.request.return_value = mock_response
    
    res = await adapter._request("GET", "/test")
    assert res == {"id": 123}
    adapter.session.request.assert_called_once()

@pytest.mark.asyncio
async def test_request_error_handling(adapter):
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"
    # Make json() return an awaitable that resolves to the dict
    mock_response.json = AsyncMock(return_value={"code": -1000, "msg": "Error"})
    
    adapter.session.request.return_value = mock_response
    
    with pytest.raises(BinanceAPIError) as exc:
        await adapter._request("GET", "/test")
    
    assert exc.value.code == -1000
    assert exc.value.msg == "Error"

@pytest.mark.asyncio
async def test_create_order(adapter):
    adapter._request = AsyncMock(return_value={
        "orderId": 12345,
        "clientOrderId": "cid_1",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "origQty": "1.0",
        "executedQty": "0.0",
        "price": "50000",
        "status": "NEW",
        "time": 1600000000000
    })
    
    params = ExchangeOrderParams(
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="1.0",
        price="50000",
        client_order_id="cid_1"
    )
    
    res = await adapter.create_order(params)
    
    assert res.order_id == "12345"
    assert res.client_order_id == "cid_1"
    assert res.status == "NEW"
    
    adapter._request.assert_called_with(
        "POST", 
        "/fapi/v1/order", 
        {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "quantity": "1.0",
            "price": "50000",
            "timeInForce": "GTC",
            "newClientOrderId": "cid_1"
        }
    )

@pytest.mark.asyncio
async def test_cancel_order(adapter):
    adapter._request = AsyncMock(return_value={
        "orderId": 12345,
        "status": "CANCELED"
    })
    
    await adapter.cancel_order("BTCUSDT", order_id="12345")
    
    adapter._request.assert_called_with(
        "DELETE",
        "/fapi/v1/order",
        {"symbol": "BTCUSDT", "orderId": "12345"},
        signed=True
    )

@pytest.mark.asyncio
async def test_get_open_positions(adapter):
    adapter._request = AsyncMock(return_value=[
        {
            "symbol": "BTCUSDT",
            "positionAmt": "0.5",
            "entryPrice": "50000",
            "markPrice": "51000",
            "unRealizedProfit": "500",
            "leverage": "10",
            "positionSide": "LONG"
        },
        {
            "symbol": "ETHUSDT",
            "positionAmt": "0.0", # Should be filtered
        }
    ])
    
    positions = await adapter.get_open_positions()
    
    assert len(positions) == 1
    assert positions[0].symbol == "BTCUSDT"
    assert positions[0].position_amount == "0.5"
    assert positions[0].side == "LONG"

@pytest.mark.asyncio
async def test_quantize_quantity(adapter):
    # Mock exchange info
    adapter.get_exchange_info = AsyncMock(return_value={
        "symbols": [{
            "symbol": "BTCUSDT",
            "filters": [
                {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                {"filterType": "MIN_NOTIONAL", "notional": "10.0"}
            ]
        }]
    })
    adapter.get_mark_price = AsyncMock(return_value=1000.0)
    
    # Simple quantization
    # 1.23456 -> 1.234
    qty = await adapter.quantize_quantity("BTCUSDT", 1.23456)
    assert qty == "1.234"
    
    # Min notional check
    # Price 1000. Min Notional 10. Min Qty = 0.01.
    # Input 0.005 (valid step 0.001). 0.005 * 1000 = 5 < 10.
    # Should bump to 0.01.
    qty_bump = await adapter.quantize_quantity("BTCUSDT", 0.005)
    assert qty_bump == "0.01"

def test_idempotency_ledger(adapter):
    adapter.register_clientorderid("cid_1", "oid_1", "BTCUSDT")
    
    # Immediate reuse
    reused = adapter.check_clientorderid_reuse("BTCUSDT", "cid_1")
    assert reused == "oid_1"
    
    # Wrong symbol
    reused_wrong = adapter.check_clientorderid_reuse("ETHUSDT", "cid_1")
    assert reused_wrong is None
    
    # Non-existent
    assert adapter.check_clientorderid_reuse("BTCUSDT", "cid_999") is None

