"""
Test ExecutionService ConnectTimeout Flow

This test suite verifies ExecutionService correctly categorizes and handles
ConnectTimeout errors from the adapter.

Purpose:
- Mock adapter to return ConnectTimeout-like errors
- Verify ExecutionService categorizes as ADAPTER_ERROR_TIMEOUT
- Verify SHADOW_EXEC_POS_ PLACE_FAILED logged (not SUCCESS)
- Document that runtime receives proper error indication

Reference: EXEC-V2-NET-ASYNC-AUDIT-S3
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from typing import Any, Dict

# Conditional httpx import
try:
    import httpx
except ImportError:
    httpx = None

from apps.reference.domains.execution_position.shadow_execpos.execution_service import (
    ExecutionService,
    ExecutionStatus,
)


class FakeAdapterWithTimeoutError:
    """
    Fake adapter that simulates httpx.ConnectTimeout.
    
    This adapter raises the actual httpx exception (like real BinanceAdapter does).
    """
    
    def __init__(self, should_timeout=True):
        self.should_timeout = should_timeout
        self.place_order_calls = []
        self.cancel_order_calls = []
    
    async def create_order(self, params=None, **kwargs):
        """Alias for place_order to support ExecutionService."""
        if params:
            return await self.place_order(
                symbol=params.symbol,
                side=params.side,
                order_type=params.order_type,
                quantity=params.quantity,
                price=params.price,
                client_order_id=params.client_order_id,
                reduce_only=params.reduce_only,
                tif=params.time_in_force,
                **kwargs
            )
        return await self.place_order(**kwargs)

    async def place_order(self, symbol=None, side=None, order_type=None, quantity=None, **kwargs):
        """Simulate place_order that raises ConnectTimeout."""
        self.place_order_calls.append({
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "kwargs": kwargs,
        })
        
        if self.should_timeout:
            # Raise actual httpx.ConnectTimeout if available
            if httpx:
                raise httpx.ConnectTimeout(f"Connection to {symbol} timed out after 20s")
            else:
                # Fallback for testing without httpx
                raise ConnectionError(f"Connection timeout: {symbol}")
        
        # Success case
        return {
            "success": True,
            "orderId": "99999",
            "clientOrderId": kwargs.get("client_order_id", "test_client_id"),
        }
    
    async def cancel_order(self, symbol, order_ref=None, **kwargs):
        """Simulate cancel_order."""
        self.cancel_order_calls.append({"symbol": symbol, "order_id": order_id})
        return {"allowed": True, "reason": "CANCEL_SUCCESS"}


@pytest.fixture
def fake_adapter_timeout():
    """Adapter that raises ConnectTimeout."""
    return FakeAdapterWithTimeoutError(should_timeout=True)


@pytest.fixture
def fake_adapter_success():
    """Adapter that succeeds."""
    return FakeAdapterWithTimeoutError(should_timeout=False)


@pytest.mark.asyncio
@pytest.mark.skipif(httpx is None, reason="httpx not installed")
async def test_execution_service_categorizes_timeout(fake_adapter_timeout):
    """
    Test: ExecutionService should categorize httpx.ConnectTimeout as ADAPTER_ERROR_TIMEOUT.
    
    Expected:
    - result["error_kind"] == "ADAPTER_ERROR_TIMEOUT"
    - result["success"] == False
    """
    # Arrange
    adapter = fake_adapter_timeout
    service = ExecutionService(adapter)
    
    cmd = {
        "verb": "PLACE",
        "symbol": "BNBUSDT",
        "side": "SELL",
        "order_type": "STOP_MARKET",
        "quantity": "10.0",
        "stop_price": "637.0",
        "reduce_only": True,
        "client_order_id": "sl_test_1",
    }
    
    # Act
    result = await service.execute_command(cmd)
    
    # Assert
    assert result["success"] is False, "Should return failure on timeout"
    assert result["status"] == ExecutionStatus.FAILED
    assert result.get("error_kind") == "ADAPTER_ERROR_TIMEOUT", "Should categorize as timeout"
    assert result.get("is_timeout") is True
    assert result.get("should_retry") is False
    assert "error" in result
    
    # Verify adapter was called once
    assert len(adapter.place_order_calls) == 1


@pytest.mark.asyncio
@pytest.mark.skipif(httpx is None, reason="httpx not installed")
async def test_execution_service_logs_place_failed(fake_adapter_timeout, caplog):
    """
    Test: Verify ExecutionService logs SHADOW_EXEC_POS_PLACE_FAILED on timeout.
    
    Expected log:
    - Level: ERROR
    - Message contains: "SHADOW_EXEC_POS_PLACE_FAILED"
    - Extra fields: error_kind=ADAPTER_ERROR_TIMEOUT
    """
    # Arrange
    adapter = fake_adapter_timeout
    service = ExecutionService(adapter)
    
    cmd = {
        "verb": "PLACE",
        "symbol": "BNBUSDT",
        "side": "SELL",
        "order_type": "TAKE_PROFIT_MARKET",
        "quantity": "10.0",
        "stop_price": "676.0",
        "reduce_only": True,
        "client_order_id": "tp_test_1",
    }
    
    # Act
    with caplog.at_level("ERROR"):
        result = await service.execute_command(cmd)
    
    # Assert
    assert result["success"] is False
    assert result.get("is_timeout") is True
    
    # Check logs
    failed_logs = [r for r in caplog.records if "PLACE_FAILED" in r.getMessage()]
    assert len(failed_logs) > 0, "Should log SHADOW_EXEC_POS_PLACE_FAILED"
    
    # Verify error_kind in log extra fields (if using structured logging)
    # Note: This depends on logging configuration


@pytest.mark.asyncio
@pytest.mark.skipif(httpx is None, reason="httpx not installed")
async def test_execution_service_returns_failure_result(fake_adapter_timeout):
    """
    Test: Verify ExecutionService returns proper ExecutionResult on timeout.
    
    Expected fields:
    - success: False
    - status: FAILED
    - error_kind: ADAPTER_ERROR_TIMEOUT
    - error: (error message)
    - order_id: None
    """
    # Arrange
    adapter = fake_adapter_timeout
    service = ExecutionService(adapter)
    
    cmd = {
        "verb": "PLACE",
        "symbol": "BNBUSDT",
        "side": "SELL",
        "order_type": "STOP_MARKET",
        "quantity": "10.0",
        "stop_price": "637.0",
        "reduce_only": True,
        "client_order_id": "sl_test_2",
    }
    
    # Act
    result = await service.execute_command(cmd)
    
    # Assert all required fields
    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["status"] == ExecutionStatus.FAILED
    assert result["error_kind"] == "ADAPTER_ERROR_TIMEOUT"
    assert result.get("is_timeout") is True
    assert result.get("should_retry") is False
    assert result["order_id"] is None
    assert result["client_order_id"] == "sl_test_2"
    assert "error" in result
    assert "timeout" in result["error"].lower() or "connection" in result["error"].lower()


@pytest.mark.asyncio
@pytest.mark.skipif(httpx is None, reason="httpx not installed")
async def test_timeout_does_not_trigger_automatic_retry(fake_adapter_timeout):
    """
    Audit test: Document that ExecutionService does NOT retry on timeout.
    
    Current behavior:
    - Single call to adapter
    - No retry within ExecutionService
    - Runtime must handle retry logic (if desired)
    
    This is consistent with ExecutionService being a thin facade.
    """
    # Arrange
    adapter = fake_adapter_timeout
    service = ExecutionService(adapter)
    
    cmd = {
        "verb": "PLACE",
        "symbol": "BNBUSDT",
        "side": "SELL",
        "order_type": "STOP_MARKET",
        "quantity": "10.0",
        "stop_price": "637.0",
        "reduce_only": True,
        "client_order_id": "sl_test_3",
    }
    
    # Act
    result = await service.execute_command(cmd)
    
    # Assert: Only ONE adapter call (no retry)
    assert len(adapter.place_order_calls) == 1
    assert result["success"] is False
    assert result.get("should_retry") is False
    
    # NOTE: If retry is desired, it should be at Runtime or Adapter level,
    # not in ExecutionService (which is just a facade).


@pytest.mark.asyncio
@pytest.mark.skipif(httpx is None, reason="httpx not installed")
async def test_runtime_receives_timeout_error_kind(fake_adapter_timeout):
    """
    Audit test: Verify that Runtime (via ExecutionService) can distinguish timeouts.
    
    Purpose:
    - Runtime needs to know if error was timeout vs other failure
    - Timeout  might request snapshot + block further brackets
    - Other error  different recovery strategy
    
    This test documents the error_kind propagation path.
    """
    # Arrange
    adapter = fake_adapter_timeout
    service = ExecutionService(adapter)
    
    cmd = {
        "verb": "PLACE",
        "symbol": "BNBUSDT",
        "side": "SELL",
        "order_type": "STOP_MARKET",
        "quantity": "10.0",
        "stop_price": "637.0",
        "reduce_only": True,
        "client_order_id": "sl_test_4",
    }
    
    # Act
    result = await service.execute_command(cmd)
    
    # Assert: Runtime can check error_kind
    if result.get("error_kind") == "ADAPTER_ERROR_TIMEOUT":
        # Runtime should:
        # 1. Mark orders snapshot as UNKNOWN
        # 2. Request fresh snapshot
        # 3. Block further bracket evaluations
        # (See EXEC-V2-P0-FIX-S2 recommendations)
        pass
    
    assert result["error_kind"] == "ADAPTER_ERROR_TIMEOUT"
    assert result["success"] is False
    assert result.get("is_timeout") is True
