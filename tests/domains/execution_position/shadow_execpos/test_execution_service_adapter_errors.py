"""
Tests for ExecutionService adapter error handling (EP-ADAPTER-DEMO-CONNECTIVITY-S19).

Verifies that:
1. Adapter exceptions (ConnectTimeout, BinanceAPIError) → ExecutionService returns FAILED, no PLACE_SUCCESS
2. Adapter returns error feedback dict → ExecutionService returns FAILED, no PLACE_SUCCESS
3. Successful operations remain unchanged (backward compatibility)
"""
import pytest
import logging
from unittest.mock import AsyncMock

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


class FakeAdapterRaisesConnectTimeout:
    """Adapter that raises httpx.ConnectTimeout."""

    async def place_order_v2(self, **kwargs):
        if httpx:
            raise httpx.ConnectTimeout(
                "Connection to demo-fapi.binance.com timed out after 20.0s")
        else:
            raise TimeoutError("Connection timeout")


class FakeAdapterReturnsErrorDict:
    """Adapter that returns error feedback dict (like real BinanceExecutionAdapter)."""

    async def place_order_v2(self, **kwargs):
        # Simulate _create_error_feedback() output
        return {
            "success": False,
            "error": "ConnectTimeout: Connection timed out",
            "instrument": kwargs.get("symbol", "UNKNOWN"),
            "order_id": "error-12345",
            "lifecycle": "rejected",
            "why": ["EXEC_EXCEPTION", "ConnectTimeout"],
        }


class FakeAdapterReturnsErrorDictNoSuccessField:
    """Adapter that returns error dict WITHOUT success field (old behavior)."""

    async def place_order_v2(self, **kwargs):
        # Old behavior: no 'success' or 'error' fields, only lifecycle="rejected"
        return {
            "instrument": kwargs.get("symbol", "UNKNOWN"),
            "order_id": "error-12345",
            "lifecycle": "rejected",
            "why": ["EXEC_EXCEPTION", "Some error"],
        }


class FakeAdapterReturnsSuccess:
    """Adapter that returns successful feedback dict."""

    async def place_order_v2(self, **kwargs):
        return {
            "success": True,
            "instrument": kwargs.get("symbol", "UNKNOWN"),
            "order_id": "12345",
            "clientOrderId": kwargs.get("client_order_id", "test-oid"),
            "lifecycle": "filled",
            "why": ["VALID_ENTRY"],
        }


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
async def test_place_order_adapter_connect_timeout_marked_failed(execution_command, caplog):
    """
    Adapter raises httpx.ConnectTimeout → ExecutionService:
    - Returns success=False, status=FAILED, error_kind=ADAPTER_ERROR_TIMEOUT
    - Logs SHADOW_EXEC_POS_PLACE_FAILED
    - Does NOT log SHADOW_EXEC_POS_PLACE_SUCCESS
    """
    if httpx is None:
        pytest.skip("httpx not installed")

    service = ExecutionService(adapter=FakeAdapterRaisesConnectTimeout())

    with caplog.at_level(logging.ERROR):
        result = await service.execute_command(execution_command)

    # Verify result
    assert result["success"] is False, "ConnectTimeout should result in success=False"
    assert result["status"] == ExecutionStatus.FAILED
    assert result["order_id"] is None
    assert result.get("error_kind") == "ADAPTER_ERROR_TIMEOUT", \
        f"Expected ADAPTER_ERROR_TIMEOUT, got {result.get('error_kind')}"
    assert "timeout" in result["error"].lower(
    ) or "ADAPTER_ERROR" in result["error"]

    # Verify logs
    log_messages = [record.message for record in caplog.records]
    assert any("SHADOW_EXEC_POS_PLACE_FAILED" in msg for msg in log_messages), \
        "Expected PLACE_FAILED log on ConnectTimeout"
    assert not any("SHADOW_EXEC_POS_PLACE_SUCCESS" in msg for msg in log_messages), \
        "❌ CRITICAL BUG: PLACE_SUCCESS logged on ConnectTimeout!"


@pytest.mark.asyncio
async def test_place_order_adapter_returns_error_dict_marked_failed(execution_command, caplog):
    """
    Adapter returns error feedback dict with success=False → ExecutionService:
    - Returns success=False, status=FAILED
    - Logs SHADOW_EXEC_POS_PLACE_FAILED
    - Does NOT log SHADOW_EXEC_POS_PLACE_SUCCESS
    """
    service = ExecutionService(adapter=FakeAdapterReturnsErrorDict())

    with caplog.at_level(logging.ERROR):
        result = await service.execute_command(execution_command)

    # Verify result
    assert result["success"] is False, "Error dict should result in success=False"
    assert result["status"] == ExecutionStatus.FAILED
    assert result["order_id"] is None
    assert "ConnectTimeout" in result["error"]

    # Verify logs
    log_messages = [record.message for record in caplog.records]
    assert any("SHADOW_EXEC_POS_PLACE_FAILED" in msg for msg in log_messages), \
        "Expected PLACE_FAILED log on error dict"
    assert not any("SHADOW_EXEC_POS_PLACE_SUCCESS" in msg for msg in log_messages), \
        "❌ CRITICAL BUG: PLACE_SUCCESS logged on error dict!"


@pytest.mark.asyncio
async def test_place_order_adapter_old_error_dict_lifecycle_rejected_marked_failed(execution_command, caplog):
    """
    Adapter returns error dict WITHOUT success field but lifecycle='rejected' → ExecutionService:
    - Returns success=False, status=FAILED (thanks to lifecycle check)
    - Logs SHADOW_EXEC_POS_PLACE_FAILED
    - Does NOT log SHADOW_EXEC_POS_PLACE_SUCCESS

    This covers backward compatibility with old error dicts.
    """
    service = ExecutionService(
        adapter=FakeAdapterReturnsErrorDictNoSuccessField())

    with caplog.at_level(logging.ERROR):
        result = await service.execute_command(execution_command)

    # Verify result
    assert result["success"] is False, "lifecycle='rejected' should result in success=False"
    assert result["status"] == ExecutionStatus.FAILED
    assert result["order_id"] is None

    # Verify logs
    log_messages = [record.message for record in caplog.records]
    assert any("SHADOW_EXEC_POS_PLACE_FAILED" in msg for msg in log_messages), \
        "Expected PLACE_FAILED log on lifecycle='rejected'"
    assert not any("SHADOW_EXEC_POS_PLACE_SUCCESS" in msg for msg in log_messages), \
        "❌ CRITICAL BUG: PLACE_SUCCESS logged on lifecycle='rejected'!"


@pytest.mark.asyncio
async def test_place_order_success_path_unchanged(execution_command, caplog):
    """
    Adapter returns success dict with success=True → ExecutionService:
    - Returns success=True, status=SUBMITTED
    - Logs SHADOW_EXEC_POS_PLACE_SUCCESS
    - Does NOT log SHADOW_EXEC_POS_PLACE_FAILED

    This verifies backward compatibility with successful operations.
    """
    service = ExecutionService(adapter=FakeAdapterReturnsSuccess())

    with caplog.at_level(logging.INFO):
        result = await service.execute_command(execution_command)

    # Verify result
    assert result["success"] is True, "Success dict should result in success=True"
    assert result["status"] == ExecutionStatus.SUBMITTED
    assert result["order_id"] == "12345"
    assert result["error"] is None

    # Verify logs
    log_messages = [record.message for record in caplog.records]
    assert any("SHADOW_EXEC_POS_PLACE_SUCCESS" in msg for msg in log_messages), \
        "Expected PLACE_SUCCESS log on success"
    assert not any("SHADOW_EXEC_POS_PLACE_FAILED" in msg for msg in log_messages), \
        "Should NOT log PLACE_FAILED on success"


@pytest.mark.asyncio
async def test_place_order_adapter_returns_dict_no_order_id_defaults_failed(execution_command, caplog):
    """
    Adapter returns dict with NO success field, NO error field, NO lifecycle='rejected', NO order_id → ExecutionService:
    - SAFETY: Defaults to success=False (no order ID = failure)
    - Returns success=False, status=FAILED
    - Logs SHADOW_EXEC_POS_PLACE_FAILED

    This verifies the improved error detection that uses absence of orderId as failure indicator.
    """
    class FakeAdapterNoOrderId:
        async def place_order_v2(self, **kwargs):
            # Ambiguous dict with no explicit success/error/lifecycle/orderId indicators
            return {
                "instrument": kwargs.get("symbol", "UNKNOWN"),
                "why": ["SOME_REASON"],
                "metadata": {"note": "No order ID provided"},
            }

    service = ExecutionService(adapter=FakeAdapterNoOrderId())

    with caplog.at_level(logging.ERROR):
        result = await service.execute_command(execution_command)

    # Verify result: No orderId = failure
    assert result["success"] is False, \
        "Dict without orderId should be treated as failure"
    assert result["status"] == ExecutionStatus.FAILED

    # Verify logs
    log_messages = [record.message for record in caplog.records]
    assert not any("SHADOW_EXEC_POS_PLACE_SUCCESS" in msg for msg in log_messages), \
        "❌ CRITICAL BUG: PLACE_SUCCESS logged on dict without orderId!"
