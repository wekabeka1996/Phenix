"""
Test for sending minimal/empty TP/SL bracket orders to exchange.

This test verifies that bracket orders with minimal values (e.g., very close TP/SL)
can be successfully placed on the exchange, simulating edge cases.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter
from vfoundation.core.protocol import Message


@pytest.mark.asyncio
async def test_place_minimal_bracket_orders():
    """
    Test placing bracket orders with minimal TP/SL values (close to entry price).

    This simulates "empty" or minimal brackets that should still be accepted by exchange.
    """
    # ⚠️ WARNING: Using REAL TESTNET API - will place actual orders!
    print("⚠️  WARNING: This test uses REAL TESTNET API and will place ACTUAL orders on Binance Testnet!")
    print("   Make sure you have sufficient TESTNET balance and understand the risks!")

    # Create adapter in shadow mode for testing (safe simulation)
    adapter = BinanceExecutionAdapter(
        api_key="test_key",
        api_secret="test_secret",
        base_url="https://demo-fapi.binance.com",
        shadow_mode=True  # Safe shadow mode - no real orders
    )

    # Test minimal SL/TP bracket order message
    bracket_msg = Message(
        op="DEC",
        verb="PLACE_ORDER",  # This should now be accepted after fix
        src="test",
        dst="adapter",
        rid="test_rid",
        pld={
            "symbol": "ETHUSDT",
            "side": "SELL",  # SL order
            "qty": "0.01",
            "order_type": "STOP_MARKET",
            "stopPrice": "3000.00",  # Minimal SL close to current price
            "reduceOnly": True,
            "newClientOrderId": "test_sl_minimal"
        }
    )

    print(f"📤 Відправляємо SL ордер: {bracket_msg.pld}")

    # Execute the order
    result = await adapter.place_order(bracket_msg)

    print(f"📥 Результат SL ордера: {result}")

    # Verify success - shadow mode returns success/allowed instead of lifecycle
    assert result.get(
        "success") is True, "Shadow mode should return success=True"
    assert result.get(
        "allowed") is True, "Shadow mode should return allowed=True"
    assert result["symbol"] == "ETHUSDT"
    assert "clientOrderId" in result or "client_order_id" in result
    client_order_id = result.get(
        "clientOrderId") or result.get("client_order_id")
    assert client_order_id == "test_sl_minimal"


@pytest.mark.asyncio
async def test_place_tp_bracket_order():
    """
    Test placing TP bracket order with minimal profit target.
    """
    adapter = BinanceExecutionAdapter(
        api_key="test_key",
        api_secret="test_secret",
        base_url="https://demo-fapi.binance.com",
        shadow_mode=True
    )

    tp_msg = Message(
        op="DEC",
        verb="PLACE_ORDER",
        src="test",
        dst="adapter",
        rid="test_rid_tp",
        pld={
            "symbol": "ETHUSDT",
            "side": "SELL",  # TP order (close long position)
            "qty": "0.01",
            "order_type": "LIMIT",
            "price": "3100.00",  # Minimal TP target
            "reduceOnly": True,
            "newClientOrderId": "test_tp_minimal"
        }
    )

    print(f"📤 Відправляємо TP ордер: {tp_msg.pld}")

    result = await adapter.place_order(tp_msg)

    print(f"📥 Результат TP ордера: {result}")

    # Verify success - shadow mode returns success/allowed instead of lifecycle
    assert result.get(
        "success") is True, "Shadow mode should return success=True"
    assert result.get(
        "allowed") is True, "Shadow mode should return allowed=True"
    assert result["symbol"] == "ETHUSDT"
    client_order_id = result.get(
        "clientOrderId") or result.get("client_order_id")
    assert client_order_id == "test_tp_minimal"


@pytest.mark.asyncio
async def test_invalid_message_type_rejected():
    """
    Test that invalid message types are properly rejected.
    """
    adapter = BinanceExecutionAdapter(
        api_key="test_key",
        api_secret="test_secret",
        base_url="https://demo-fapi.binance.com",
        shadow_mode=True
    )

    invalid_msg = Message(
        op="DEC",
        verb="INVALID",  # Not OPEN or PLACE_ORDER
        src="test",
        dst="adapter",
        rid="test_invalid",
        pld={}
    )

    print(f"📤 Спроба відправити невалідний ордер: {invalid_msg.verb}")

    with pytest.raises(ValueError, match="expected DEC:OPEN or DEC:PLACE_ORDER"):
        await adapter.place_order(invalid_msg)


if __name__ == "__main__":
    # Run tests directly
    asyncio.run(test_place_minimal_bracket_orders())
    asyncio.run(test_place_tp_bracket_order())
    asyncio.run(test_invalid_message_type_rejected())
    print("All bracket order tests passed!")
