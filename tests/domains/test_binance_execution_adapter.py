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


def test_generate_signature_matches_manual():
    secret = "mysecret"
    cfg = {"binance_ro_api_secret": secret, "binance_ro_api_key": "k"}
    adapter = BinanceExecutionAdapter(fsm=None, config=cfg, shadow_mode=True)
    params = {"b": "2", "a": "1"}
    sig = adapter._generate_signature(params)

    # manual signature
    qs = "&".join([f"{key}={params[key]}" for key in sorted(params.keys())])
    expected = hmac.new(
        secret.encode("utf-8"), qs.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert sig == expected


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
    assert res["lifecycle"] == "filled"


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
    assert result["lifecycle"] == "filled"
    assert "shadow" in result["order_id"]
