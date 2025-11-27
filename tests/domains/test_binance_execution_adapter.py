from apps.reference.domains.execution_position.execution_adapter import (
    AbstractExecutionAdapter,
)
from unittest.mock import MagicMock
import hmac
import hashlib
import pytest
import asyncio
from apps.reference.domains.execution_position.binance_execution_adapter import (
    BinanceExecutionAdapter,
)
from vfoundation.core.protocol import Message


def test_adapt_symbol():
    cfg = {
        "trading_env": "test",
        "binance_ro_api_key": "k",
        "binance_ro_api_secret": "s",
    }
    adapter = BinanceExecutionAdapter(fsm=None, config=cfg, shadow_mode=True)

    # Test normal symbol
    assert adapter._adapt_symbol("BTCUSDT") == "BTCUSDT"

    # Test PERP symbol
    assert adapter._adapt_symbol("BTC-PERP") == "BTCUSDT"


def test_adapt_quantity():
    cfg = {
        "trading_env": "test",
        "binance_ro_api_key": "k",
        "binance_ro_api_secret": "s",
    }
    adapter = BinanceExecutionAdapter(fsm=None, config=cfg, shadow_mode=True)

    # Test quantity adaptation (removes trailing zeros)
    assert adapter._adapt_quantity("1.500") == "1.5"
    assert adapter._adapt_quantity("2.000") == "2"
    assert adapter._adapt_quantity("0.1234000") == "0.1234"


def test_build_signed_request_includes_signature():
    """Verify _build_signed_request generates valid HMAC signature."""
    secret = "mysecret"
    cfg = {"binance_ro_api_secret": secret, "binance_ro_api_key": "k"}
    adapter = BinanceExecutionAdapter(fsm=None, config=cfg, shadow_mode=True)
    params = {"b": "2", "a": "1"}

    signed_params, _, sign_target, sig = adapter._build_signed_request(params)

    # Verify signature is present and correct format (64 hex chars)
    assert "signature" in signed_params
    assert len(signed_params["signature"]) == 64

    # Verify manual signature calculation matches
    expected = hmac.new(
        secret.encode("utf-8"), sign_target.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert sig == expected
    assert signed_params["signature"] == expected

    # Verify timestamp was added by _get_signed_params
    assert "timestamp" in signed_params


@pytest.mark.asyncio
async def test_place_order_shadow_mode():
    cfg = {
        "binance_ro_api_secret": "s",
        "binance_ro_api_key": "k",
        "trading_env": "test",
    }
    adapter = BinanceExecutionAdapter(fsm=None, config=cfg, shadow_mode=True)
    msg = Message(
        op="DEC",
        verb="OPEN",
        src="t",
        dst="b",
        rid="r1",
        pld={"symbol": "ETHUSDT", "side": "BUY", "qty": "1"},
    )
    res = await adapter.place_order(msg)
    # New format uses 'success' and 'allowed' instead of 'lifecycle'
    assert res["success"] is True
    assert res["allowed"] is True
    assert "shadow" in res["order_id"]


"""
Unit tests for BinanceExecutionAdapter.
"""


@pytest.fixture
def mock_fsm():
    return MagicMock()


@pytest.fixture
def mock_config():
    return {
        "trading_env": "test",
        "binance_ro_api_key": "test_key",
        "binance_ro_api_secret": "test_secret",
    }


@pytest.fixture
def adapter_shadow(mock_fsm, mock_config):
    """Fixture for an adapter in shadow mode."""
    return BinanceExecutionAdapter(fsm=mock_fsm, config=mock_config, shadow_mode=True)


@pytest.mark.asyncio
async def test_inheritance(adapter_shadow):
    assert isinstance(adapter_shadow, AbstractExecutionAdapter)


@pytest.mark.asyncio
async def test_place_order_shadow_mode_success(adapter_shadow):
    dec_msg = Message(
        op="DEC",
        verb="OPEN",
        src="test",
        dst="test",
        pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "1"},
    )
    result = await adapter_shadow.place_order(dec_msg)
    # New format uses 'success' and 'allowed' instead of 'lifecycle'
    assert result["success"] is True
    assert result["allowed"] is True
    assert "shadow" in result["order_id"]
