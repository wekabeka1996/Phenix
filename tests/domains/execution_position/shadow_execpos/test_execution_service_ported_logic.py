"""
Tests for ExecutionService Ported Logic
=======================================

Tests the complete adapter logic ported from fsm._execute_decision.
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from apps.reference.domains.execution_position.shadow_execpos.execution_service import (
    ExecutionService,
    ERROR_UNKNOWN_ORDER,
    ERROR_WOULD_TRIGGER,
    ERROR_DUPLICATE_ID
)
from apps.reference.domains.execution_position.shadow_execpos.types import ExecutionStatus

@pytest.fixture
def mock_adapter():
    """Mock adapter with async methods."""
    adapter = MagicMock()
    adapter.place_order = AsyncMock()
    adapter.cancel_order = AsyncMock()
    adapter.get_open_orders = AsyncMock()
    return adapter

@pytest.fixture
def service(mock_adapter):
    """ExecutionService with mocked adapter."""
    return ExecutionService(mock_adapter)

# --- PLACE ORDER TESTS ---

@pytest.mark.asyncio
async def test_place_order_success(service, mock_adapter):
    """Test successful order placement."""
    # Mock adapter response
    mock_adapter.place_order.return_value = {
        "orderId": "12345",
        "symbol": "BTCUSDT",
        "status": "NEW"
    }
    
    result = await service.place_order(
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="0.1",
        price="50000"
    )
    
    assert result["success"] is True
    assert result["status"] == ExecutionStatus.SUBMITTED
    assert result["order_id"] == "12345"
    assert result["error"] is None
    
    # Verify adapter was called
    mock_adapter.place_order.assert_called_once()

@pytest.mark.asyncio
async def test_place_order_missing_params(service):
    """Test place_order with missing required parameters."""
    result = await service.place_order(
        symbol="BTCUSDT",
        side=None,  # Missing
        order_type="MARKET",
        quantity="0.1"
    )
    
    assert result["success"] is False
    assert result["status"] == ExecutionStatus.FAILED
    assert "Missing required parameters" in result["error"]

@pytest.mark.asyncio
async def test_place_order_would_trigger_error(service, mock_adapter):
    """Test place_order with -2021 error (would immediately trigger)."""
    # Mock adapter to raise error with -2021 code
    mock_adapter.place_order.side_effect = Exception(f"APIError: code={ERROR_WOULD_TRIGGER}, msg=stopPrice would trigger immediately")
    
    result = await service.place_order(
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        quantity="0.1",
        price="45000"
    )
    
    assert result["success"] is False
    assert result["status"] == ExecutionStatus.FAILED
    assert result["error"] == "WOULD_TRIGGER"

@pytest.mark.asyncio
async def test_place_order_duplicate_id_error(service, mock_adapter):
    """Test place_order with -4116 error (duplicate client order ID)."""
    mock_adapter.place_order.side_effect = Exception(f"APIError: code={ERROR_DUPLICATE_ID}, msg=Duplicate clientOrderId")
    
    result = await service.place_order(
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="0.1",
        price="50000",
        client_order_id="test_id_123"
    )
    
    assert result["success"] is False
    assert result["error"] == "DUPLICATE_ID"

# --- CANCEL ORDER TESTS ---

@pytest.mark.asyncio
async def test_cancel_order_success(service, mock_adapter):
    """Test successful order cancellation."""
    mock_adapter.cancel_order.return_value = {
        "orderId": "12345",
        "status": "CANCELED"
    }
    
    result = await service.cancel_order(
        symbol="BTCUSDT",
        order_id="12345"
    )
    
    assert result["success"] is True
    assert result["status"] == ExecutionStatus.SUCCESS
    assert result["order_id"] == "12345"
    assert result["error"] is None

@pytest.mark.asyncio
async def test_cancel_order_unknown_idempotent(service, mock_adapter):
    """Test cancel_order with -2011 error (unknown order) - should treat as success."""
    # Mock adapter to raise -2011 error
    mock_adapter.cancel_order.side_effect = Exception(f"APIError: code={ERROR_UNKNOWN_ORDER}, msg=Unknown order sent")
    
    result = await service.cancel_order(
        symbol="BTCUSDT",
        order_id="99999"  # Non-existent order
    )
    
    # Should be treated as SUCCESS (idempotent)
    assert result["success"] is True
    assert result["status"] == ExecutionStatus.SUCCESS
    assert result["error"] == "UNKNOWN_ORDER"
    assert result["metadata"]["idempotent"] is True

@pytest.mark.asyncio
async def test_cancel_order_missing_identifier(service):
    """Test cancel_order without order ID or client_order_id."""
    result = await service.cancel_order(
        symbol="BTCUSDT",
        order_id=None,
        client_order_id=None
    )
    
    assert result["success"] is False
    assert result["status"] == ExecutionStatus.FAILED
    assert "Missing symbol or order identifier" in result["error"]

# --- CLOSE POSITION TESTS ---

@pytest.mark.asyncio
async def test_close_position_success(service, mock_adapter):
    """Test successful position close."""
    mock_adapter.place_order.return_value = {
        "orderId": "67890",
        "status": "FILLED"
    }
    
    result = await service.close_position(
        symbol="ETHUSDT",
        quantity="1.0"
    )
    
    assert result["success"] is True
    assert result["status"] == ExecutionStatus.SUBMITTED
    assert result["order_id"] == "67890"
    
    # Verify reduce_only MARKET order was placed
    call_kwargs = mock_adapter.place_order.call_args[1]
    assert call_kwargs["reduce_only"] is True
    assert call_kwargs["order_type"] == "MARKET"

@pytest.mark.asyncio
async def test_close_position_missing_symbol(service):
    """Test close_position without symbol."""
    result = await service.close_position(symbol=None)
    
    assert result["success"] is False
    assert "Missing symbol for CLOSE" in result["error"]

# --- EXECUTE_COMMAND TESTS ---

@pytest.mark.asyncio
async def test_execute_command_place(service, mock_adapter):
    """Test execute_command with PLACE verb."""
    mock_adapter.place_order.return_value = {"orderId": "111"}
    
    cmd = {
        "verb": "PLACE",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": "0.1",
        "price": "50000",
        "order_type": "LIMIT",
        "client_order_id": None,
        "reduce_only": False,
        "extra_params": {}
    }
    
    result = await service.execute_command(cmd)
    
    assert result["success"] is True
    assert result["order_id"] == "111"

@pytest.mark.asyncio
async def test_execute_command_cancel(service, mock_adapter):
    """Test execute_command with CANCEL verb."""
    mock_adapter.cancel_order.return_value = {"status": "CANCELED"}
    
    cmd = {
        "verb": "CANCEL",
        "symbol": "BTCUSDT",
        "side": None,
        "quantity": None,
        "price": None,
        "order_type": None,
        "client_order_id": None,
        "reduce_only": False,
        "extra_params": {"order_id": "12345"}
    }
    
    result = await service.execute_command(cmd)
    
    assert result["success"] is True
    assert result["status"] == ExecutionStatus.SUCCESS

@pytest.mark.asyncio
async def test_execute_command_unsupported_verb(service):
    """Test execute_command with unsupported verb."""
    cmd = {
        "verb": "INVALID_VERB",
        "symbol": "BTCUSDT",
        "side": None,
        "quantity": None,
        "price": None,
        "order_type": None,
        "client_order_id": None,
        "reduce_only": False,
        "extra_params": {}
    }
    
    result = await service.execute_command(cmd)
    
    assert result["success"] is False
    assert "Unsupported verb" in result["error"]

# --- _call_adapter TESTS ---

@pytest.mark.asyncio
async def test_call_adapter_async_function(service, mock_adapter):
    """Test _call_adapter with async function."""
    mock_adapter.get_balance = AsyncMock(return_value={"BTC": "1.5"})
    
    result = await service._call_adapter("get_balance")
    
    assert result == {"BTC": "1.5"}

@pytest.mark.asyncio
async def test_call_adapter_sync_function(service, mock_adapter):
    """Test _call_adapter with sync function that returns a value."""
    mock_adapter.get_status = MagicMock(return_value="active")
    
    result = await service._call_adapter("get_status")
    
    assert result == "active"

@pytest.mark.asyncio
async def test_call_adapter_nonexistent_method(service, mock_adapter):
    """Test _call_adapter with nonexistent method."""
    # Configure mock to raise AttributeError for unknown methods
    # We need to replace the adapter on the service with one that respects specs
    # or just manually delete the attribute if it exists (but MagicMock auto-creates)
    
    # Better approach: Mock the adapter to raise AttributeError when accessing 'nonexistent_method'
    # But getattr() on MagicMock returns a new Mock.
    # So we must ensure getattr(adapter, "nonexistent_method") raises AttributeError
    # or returns None if the service handles it.
    
    # If ExecutionService uses getattr(..., None), then MagicMock returns a Mock, not None.
    # We can simulate a "real" object behavior by using spec.
    
    real_adapter_mock = MagicMock(spec=["place_order", "cancel_order"]) 
    service.adapter = real_adapter_mock
    
    result = await service._call_adapter("nonexistent_method")
    
    assert result is None

# --- ERROR NORMALIZATION TESTS ---

def test_normalize_error_unknown_order(service):
    """Test error normalization for -2011."""
    exc = Exception(f"APIError: code={ERROR_UNKNOWN_ORDER}, msg=Unknown order")
    normalized = service._normalize_error(exc)
    
    assert normalized == "UNKNOWN_ORDER"

def test_normalize_error_would_trigger(service):
    """Test error normalization for -2021."""
    exc = Exception(f"Stop price would trigger immediately. code={ERROR_WOULD_TRIGGER}")
    normalized = service._normalize_error(exc)
    
    assert normalized == "WOULD_TRIGGER"

def test_normalize_error_generic(service):
    """Test error normalization for unknown error."""
    exc = Exception("Some random error message")
    normalized = service._normalize_error(exc)
    
    assert "ADAPTER_ERROR" in normalized

def test_is_unknown_order_error(service):
    """Test detection of -2011 errors."""
    exc_2011 = Exception(f"code={ERROR_UNKNOWN_ORDER}")
    exc_other = Exception("Some other error")
    
    assert service._is_unknown_order_error(exc_2011) is True
    assert service._is_unknown_order_error(exc_other) is False
