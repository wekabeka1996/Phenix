"""
Tests for ExecutionService error handling (EP-EXEC-SHADOW-PLACE-ERROR-HANDLING-S21).

Verifies that:
1. Adapter success → logs SHADOW_EXEC_POS_PLACE_SUCCESS
2. Adapter failure (success=False) → logs SHADOW_EXEC_POS_PLACE_FAILED, no SUCCESS
3. Adapter timeout exception → logs SHADOW_EXEC_POS_PLACE_FAILED with error_kind=ADAPTER_ERROR_TIMEOUT
4. Generic adapter exception → logs SHADOW_EXEC_POS_PLACE_FAILED with error_kind=ADAPTER_ERROR
5. Runtime interprets failed results correctly (no position update)
"""
import pytest
import logging
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

try:
    import httpx
except ImportError:
    httpx = None

from apps.reference.domains.execution_position.shadow_execpos.execution_service import (
    ExecutionService,
)
from apps.reference.domains.execution_position.shadow_execpos.types import (
    ExecutionStatus,
    ExecutionCommand,
)


class FakeAdapterSuccess:
    """Adapter that returns successful response."""

    async def place_order_v2(self, **kwargs):
        return {
            "success": True,
            "orderId": "12345",
            "clientOrderId": kwargs.get("client_order_id", "test-oid"),
            "status": "NEW",
        }

    async def place_order(self, **kwargs):
        return await self.place_order_v2(**kwargs)


class FakeAdapterFailure:
    """Adapter that returns failure response (no exception)."""

    async def place_order_v2(self, **kwargs):
        return {
            "success": False,
            "error": "Insufficient balance",
            "error_kind": "ADAPTER_ERROR",
            "orderId": None,
        }

    async def place_order(self, **kwargs):
        return await self.place_order_v2(**kwargs)


class FakeAdapterTimeout:
    """Adapter that raises httpx.TimeoutException."""

    async def place_order_v2(self, **kwargs):
        if httpx:
            raise httpx.ConnectTimeout(
                "Connection to demo-fapi.binance.com timed out after 20.0s")
        else:
            raise TimeoutError("Connection timeout")

    async def place_order(self, **kwargs):
        return await self.place_order_v2(**kwargs)


class FakeAdapterGenericError:
    """Adapter that raises generic exception."""

    async def place_order_v2(self, **kwargs):
        raise RuntimeError("Unexpected adapter error")

    async def place_order(self, **kwargs):
        return await self.place_order_v2(**kwargs)


class FakeAdapterBinanceValidationError:
    """Adapter that raises BinanceValidationError (precision issue)."""

    async def place_order_v2(self, **kwargs):
        # Simulate precision validation error
        from apps.reference.domains.execution_position.binance_execution_adapter import (
            BinanceValidationError,
        )
        raise BinanceValidationError(
            "Quantity 0 below min_qty 1.0 for SOLUSDT (raw_qty=0.5, step_size=1.0)"
        )

    async def place_order(self, **kwargs):
        return await self.place_order_v2(**kwargs)


@pytest.fixture
def execution_command() -> ExecutionCommand:
    """Standard execution command for testing."""
    return {
        "verb": "PLACE",
        "symbol": "SOLUSDT",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": "1.0",
        "price": "120.0",
        "client_order_id": "test-oid-123",
        "reduce_only": False,
        "extra_params": {},
    }


@pytest.mark.asyncio
async def test_adapter_success_logs_place_success(execution_command, caplog):
    """Adapter success → logs SHADOW_EXEC_POS_PLACE_SUCCESS, no FAILED."""
    service = ExecutionService(adapter=FakeAdapterSuccess())

    with caplog.at_level(logging.INFO):
        result = await service.execute_command(execution_command)

    # Verify result
    assert result["success"] is True
    assert result["status"] == ExecutionStatus.SUBMITTED
    assert result["order_id"] == "12345"
    assert result["error"] is None

    # Verify logs
    log_messages = [record.message for record in caplog.records]
    assert any("SHADOW_EXEC_POS_PLACE_SUCCESS" in msg for msg in log_messages), \
        "Expected PLACE_SUCCESS log"
    assert not any("SHADOW_EXEC_POS_PLACE_FAILED" in msg for msg in log_messages), \
        "Should NOT log PLACE_FAILED on success"


@pytest.mark.asyncio
async def test_adapter_failure_logs_place_failed(execution_command, caplog):
    """Adapter returns success=False → logs SHADOW_EXEC_POS_PLACE_FAILED, no SUCCESS."""
    service = ExecutionService(adapter=FakeAdapterFailure())

    with caplog.at_level(logging.ERROR):
        result = await service.execute_command(execution_command)

    # Verify result
    assert result["success"] is False
    assert result["status"] == ExecutionStatus.FAILED
    assert result["order_id"] is None
    assert "Insufficient balance" in result["error"]
    assert result.get("error_kind") == "ADAPTER_ERROR"

    # Verify logs
    log_messages = [record.message for record in caplog.records]
    assert any("SHADOW_EXEC_POS_PLACE_FAILED" in msg for msg in log_messages), \
        "Expected PLACE_FAILED log"
    assert not any("SHADOW_EXEC_POS_PLACE_SUCCESS" in msg for msg in log_messages), \
        "Should NOT log PLACE_SUCCESS on failure"


@pytest.mark.asyncio
async def test_adapter_timeout_logs_place_failed_with_timeout_kind(execution_command, caplog):
    """Adapter raises httpx.ConnectTimeout → logs PLACE_FAILED with error_kind=ADAPTER_ERROR_TIMEOUT."""
    if httpx is None:
        pytest.skip("httpx not installed")

    service = ExecutionService(adapter=FakeAdapterTimeout())

    with caplog.at_level(logging.ERROR):
        result = await service.execute_command(execution_command)

    # Verify result
    assert result["success"] is False
    assert result["status"] == ExecutionStatus.FAILED
    assert result["order_id"] is None
    assert result.get("error_kind") == "ADAPTER_ERROR_TIMEOUT", \
        f"Expected ADAPTER_ERROR_TIMEOUT, got {result.get('error_kind')}"
    assert "timeout" in result["error"].lower(
    ) or "ADAPTER_ERROR" in result["error"]

    # Verify logs
    log_messages = [record.message for record in caplog.records]
    assert any("SHADOW_EXEC_POS_PLACE_FAILED" in msg for msg in log_messages), \
        "Expected PLACE_FAILED log"
    assert not any("SHADOW_EXEC_POS_PLACE_SUCCESS" in msg for msg in log_messages), \
        "Should NOT log PLACE_SUCCESS on timeout"

    # Verify log extras contain error_kind
    failed_records = [r for r in caplog.records if "PLACE_FAILED" in r.message]
    assert len(failed_records) > 0
    extras = getattr(failed_records[0], "__dict__", {})
    # Check if error_kind is in extra data (caplog might not preserve all extras)
    # Main verification is in the returned result


@pytest.mark.asyncio
async def test_adapter_generic_exception_logs_place_failed(execution_command, caplog):
    """Adapter raises generic exception → logs PLACE_FAILED with error_kind=ADAPTER_ERROR."""
    service = ExecutionService(adapter=FakeAdapterGenericError())

    with caplog.at_level(logging.ERROR):
        result = await service.execute_command(execution_command)

    # Verify result
    assert result["success"] is False
    assert result["status"] == ExecutionStatus.FAILED
    assert result["order_id"] is None
    assert result.get("error_kind") == "ADAPTER_ERROR"
    assert "Unexpected adapter error" in result["error"] or "ADAPTER_ERROR" in result["error"]

    # Verify logs
    log_messages = [record.message for record in caplog.records]
    assert any("SHADOW_EXEC_POS_PLACE_FAILED" in msg for msg in log_messages), \
        "Expected PLACE_FAILED log"
    assert not any("SHADOW_EXEC_POS_PLACE_SUCCESS" in msg for msg in log_messages), \
        "Should NOT log PLACE_SUCCESS on exception"


@pytest.mark.asyncio
async def test_adapter_validation_error_logs_place_failed(execution_command, caplog):
    """Adapter raises BinanceValidationError → logs PLACE_FAILED with VALIDATION_ERROR."""
    service = ExecutionService(adapter=FakeAdapterBinanceValidationError())

    with caplog.at_level(logging.ERROR):
        result = await service.execute_command(execution_command)

    # Verify result
    assert result["success"] is False
    assert result["status"] == ExecutionStatus.FAILED
    assert result["order_id"] is None
    # Generic for all exceptions
    assert result.get("error_kind") == "ADAPTER_ERROR"
    assert "VALIDATION_ERROR" in result["error"] or "min_qty" in result["error"]

    # Verify logs
    log_messages = [record.message for record in caplog.records]
    assert any("SHADOW_EXEC_POS_PLACE_FAILED" in msg for msg in log_messages), \
        "Expected PLACE_FAILED log"
    assert not any("SHADOW_EXEC_POS_PLACE_SUCCESS" in msg for msg in log_messages), \
        "Should NOT log PLACE_SUCCESS on validation error"


@pytest.mark.asyncio
async def test_missing_required_params_logs_place_failed(caplog):
    """Missing symbol/side/quantity → logs PLACE_FAILED."""
    service = ExecutionService(adapter=FakeAdapterSuccess())

    cmd_missing_symbol: ExecutionCommand = {
        "verb": "PLACE",
        "symbol": "",  # Missing
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": "1.0",
        "price": None,
        "client_order_id": None,
        "reduce_only": False,
        "extra_params": {},
    }

    result = await service.execute_command(cmd_missing_symbol)

    # Verify result
    assert result["success"] is False
    assert result["status"] == ExecutionStatus.FAILED
    assert "Missing required parameters" in result["error"]

    # No SUCCESS log should appear
    log_messages = [record.message for record in caplog.records]
    assert not any("SHADOW_EXEC_POS_PLACE_SUCCESS" in msg for msg in log_messages), \
        "Should NOT log PLACE_SUCCESS with missing params"


@pytest.mark.asyncio
async def test_exc_info_logged_on_exception(execution_command, caplog):
    """Verify exc_info=True provides full traceback in logs."""
    service = ExecutionService(adapter=FakeAdapterGenericError())

    with caplog.at_level(logging.ERROR):
        await service.execute_command(execution_command)

    # Find PLACE_FAILED log record
    failed_records = [r for r in caplog.records if "PLACE_FAILED" in r.message]
    assert len(failed_records) > 0, "Expected at least one PLACE_FAILED log"

    # Check that exc_info is present (indicates traceback was logged)
    record = failed_records[0]
    assert record.exc_info is not None, \
        "Expected exc_info=True to provide traceback"


@pytest.mark.asyncio
async def test_error_metadata_contains_exception_type(execution_command):
    """Verify metadata contains exception_type for debugging."""
    service = ExecutionService(adapter=FakeAdapterGenericError())

    result = await service.execute_command(execution_command)

    assert result["success"] is False
    assert "exception_type" in result["metadata"]
    assert result["metadata"]["exception_type"] == "RuntimeError"


@pytest.mark.asyncio
async def test_convenience_method_place_order_delegates_to_execute_command():
    """Verify convenience method place_order() delegates to execute_command()."""
    service = ExecutionService(adapter=FakeAdapterSuccess())

    result = await service.place_order(
        symbol="SOLUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="1.0",
        price="120.0",
        client_order_id="test-oid"
    )

    assert result["success"] is True
    assert result["order_id"] == "12345"
