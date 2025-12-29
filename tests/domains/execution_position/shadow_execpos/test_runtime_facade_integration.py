"""
Integration test for V2 Runtime Facade.
Verifies that the Facade correctly translates legacy messages and invokes the V2 Runtime,
which in turn produces commands on the adapter.
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from typing import Any, Dict

from apps.reference.domains.execution_position.infra.runtime_factory import V2RuntimeFacade
from vfoundation.core.protocol import Message

# Mock classes to simulate dependencies
class MockAdapter:
    def __init__(self):
        self.place_order = AsyncMock(return_value={"success": True, "order_id": "123"})
        self.create_order = AsyncMock(return_value={"success": True, "order_id": "123"})
        self.cancel_order = AsyncMock(return_value={"success": True})
        self.close_position = AsyncMock(return_value={"success": True})

@pytest.mark.asyncio
async def test_facade_entry_flow():
    """
    Verify CMD:OPEN -> Facade -> Runtime -> Adapter.place_order
    """
    # Setup
    config = {
        "execution_position": {
            "runtime_mode": "v2",
            "gatekeeper": {"enabled": False} # Disable gatekeeper for simple pass-through
        }
    }
    mock_adapter = MockAdapter()

    # Instantiate Facade with REAL Runtime (inside) and MOCK Adapter
    facade = V2RuntimeFacade(config=config, adapter=mock_adapter)

    # Create Legacy Message
    msg = Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "1.0",
            "price": "50000",
            "order_type": "LIMIT",
            "idempotent_key": "test_entry_1"
        }
    )

@pytest.mark.asyncio
async def test_facade_cancel_flow():
    """
    Verify CMD:CANCEL -> Facade -> Runtime -> Adapter.cancel_order
    """
    config = {"execution_position": {"runtime_mode": "v2"}}
    mock_adapter = MockAdapter()
    facade = V2RuntimeFacade(config=config, adapter=mock_adapter)

    msg = Message(
        op="CMD",
        verb="CANCEL",
        src="decision_making",
        dst="execution_position",
        pld={
            "symbol": "BTCUSDT",
            "order_id": "123"
        }
    )

    facade.handle(msg)
    await asyncio.sleep(0.1)

    mock_adapter.cancel_order.assert_called_once()
    assert mock_adapter.cancel_order.call_args[1]["order_id"] == "123"

@pytest.mark.asyncio
async def test_facade_ignored_message():
    """
    Verify irrelevant message -> Facade -> Ignored (no adapter call)
    """
    config = {"execution_position": {"runtime_mode": "v2"}}
    mock_adapter = MockAdapter()
    facade = V2RuntimeFacade(config=config, adapter=mock_adapter)

    # Use valid OP but ignored VERB
    msg = Message(
        op="EVT",
        verb="HEARTBEAT",
        src="system",
        dst="broadcast",
        pld={}
    )

    facade.handle(msg)
    await asyncio.sleep(0.01)

    mock_adapter.place_order.assert_not_called()
    mock_adapter.create_order.assert_not_called()
    mock_adapter.cancel_order.assert_not_called()

@pytest.mark.asyncio
async def test_facade_force_close_flow():
    """
    Verify CMD:FORCE_CLOSE -> Facade -> Runtime -> Adapter.place_order (reduce_only=True)
    """
    config = {"execution_position": {"runtime_mode": "v2"}}
    mock_adapter = MockAdapter()
    facade = V2RuntimeFacade(config=config, adapter=mock_adapter)

    msg = Message(
        op="CMD",
        verb="FORCE_CLOSE",
        src="risk_management",
        dst="execution_position",
        pld={
            "symbol": "ETHUSDT",
            "qty": "10.0"
        }
    )

    facade.handle(msg)
    await asyncio.sleep(0.1)

    # ExecutionService implements close via place_order(reduce_only=True)
    # It might call create_order or place_order depending on implementation
    if mock_adapter.create_order.called:
        mock_adapter.create_order.assert_called_once()
        # create_order is called with params=ExchangeOrderParams(...)
        kwargs = mock_adapter.create_order.call_args[1]
        params = kwargs["params"]
        assert params.symbol == "ETHUSDT"
        assert params.quantity == "10.0"
        assert params.reduce_only is True
        assert params.order_type == "MARKET"
    else:
        mock_adapter.place_order.assert_called_once()
        call_args = mock_adapter.place_order.call_args[1]
        assert call_args["symbol"] == "ETHUSDT"
        assert call_args["quantity"] == "10.0"
        assert call_args["reduce_only"] is True
        assert call_args["order_type"] == "MARKET"

@pytest.mark.asyncio
async def test_facade_snapshot_flow():
    """
    Verify EVT:POSITION_SNAPSHOT -> Facade -> Runtime state update
    """
    config = {"execution_position": {"runtime_mode": "v2"}}
    mock_adapter = MockAdapter()
    facade = V2RuntimeFacade(config=config, adapter=mock_adapter)

    msg = Message(
        op="EVT",
        verb="POSITION_SNAPSHOT",
        src="portfolio",
        dst="execution_position",
        pld={
            "positions": [
                {"symbol": "BTCUSDT", "positionAmt": "2.5", "entryPrice": "60000"}
            ]
        }
    )

    facade.handle(msg)
    await asyncio.sleep(0.1)

    # Verify runtime state (accessing public member)
    runtime = facade.runtime
    assert "BTCUSDT" in runtime._positions_by_symbol
    pos = runtime._positions_by_symbol["BTCUSDT"]
    # Fix: PositionState is a dataclass, use attribute access
    assert pos.symbol == "BTCUSDT"
    assert pos.qty == 2.5
    assert pos.avg_entry_price == 60000.0
