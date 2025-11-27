"""
TASK 2: Test that ExecutionService NEVER logs SUCCESS on timeout.

Critical invariant: If adapter returns timeout error OR raises timeout exception,
the log must contain ONLY SHADOW_EXEC_POS_PLACE_FAILED, never SUCCESS.

This prevents the bug where log showed:
- SHADOW_EXEC_POS_PLACE_SUCCESS
- [BinanceAdapter] Order execution failed: ConnectTimeout
"""
from decimal import Decimal
from typing import Any, Dict
from unittest.mock import MagicMock
import pytest

try:
    import httpx
except ImportError:
    httpx = None

from apps.reference.domains.execution_position.shadow_execpos.execution_service import (
    ExecutionService,
)


# ============================================================================
# TEST FIXTURES
# ============================================================================

class TimeoutAdapter:
    """Adapter that simulates ConnectTimeout exception."""

    def __init__(self):
        self.place_order_calls = []

    async def place_order_v2(self, **kwargs):
        self.place_order_calls.append(kwargs)
        if httpx:
            raise httpx.ConnectTimeout("Connection timed out")
        else:
            raise TimeoutError("Connection timed out")


class TimeoutResponseAdapter:
    """Adapter that returns timeout error in response (not exception)."""

    def __init__(self):
        self.place_order_calls = []

    async def place_order_v2(self, **kwargs):
        self.place_order_calls.append(kwargs)
        return {
            "success": False,
            "error": "ConnectTimeout: Connection timed out",
            "error_kind": "ADAPTER_ERROR_TIMEOUT",
            "order_id": None,
        }


class MixedTimeoutAdapter:
    """
    Adapter that first returns success for one symbol,
    then timeout for another - simulating the BNB brackets scenario.
    """

    def __init__(self):
        self.call_count = 0
        self.place_order_calls = []

    async def place_order_v2(self, **kwargs):
        self.place_order_calls.append(kwargs)
        self.call_count += 1

        # First call succeeds (e.g., one bracket)
        if self.call_count == 1:
            return {
                "success": True,
                "orderId": "12345",
                "order_id": "12345",
                "status": "NEW",
            }

        # Second call times out
        if httpx:
            raise httpx.ConnectTimeout("Connection timed out on second call")
        else:
            raise TimeoutError("Connection timed out on second call")


@pytest.fixture
def timeout_exception_adapter():
    return TimeoutAdapter()


@pytest.fixture
def timeout_response_adapter():
    return TimeoutResponseAdapter()


@pytest.fixture
def mixed_adapter():
    return MixedTimeoutAdapter()


# ============================================================================
# CORE INVARIANT TEST: NO SUCCESS LOG ON TIMEOUT
# ============================================================================

@pytest.mark.asyncio
async def test_timeout_exception_never_logs_success(timeout_exception_adapter, caplog):
    """
    CRITICAL TEST: When adapter raises timeout exception,
    logs must contain FAILED and NEVER contain SUCCESS.
    """
    service = ExecutionService(timeout_exception_adapter)

    cmd = {
        "verb": "PLACE",
        "symbol": "BNBUSDT",
        "side": "BUY",
        "order_type": "STOP_MARKET",
        "quantity": "0.76",
        "stop_price": "909.64",
        "reduce_only": True,
        "client_order_id": "AUR-BNBUSDT-SHORT-PLACE_SL-C0-0",
    }

    import logging
    with caplog.at_level(logging.DEBUG):
        result = await service.execute_command(cmd)

    # Result must be failure
    assert result["success"] is False
    assert result.get("is_timeout") is True

    # Extract all log messages
    all_messages = [r.getMessage() for r in caplog.records]
    all_text = " ".join(all_messages)

    # INVARIANT: No SUCCESS log
    assert "SHADOW_EXEC_POS_PLACE_SUCCESS" not in all_text, \
        f"SUCCESS should NEVER appear on timeout! Logs: {all_messages}"

    # Must have FAILED log
    assert "SHADOW_EXEC_POS_PLACE_FAILED" in all_text, \
        f"FAILED should appear on timeout. Logs: {all_messages}"


@pytest.mark.asyncio
async def test_timeout_response_never_logs_success(timeout_response_adapter, caplog):
    """
    CRITICAL TEST: When adapter returns timeout in response dict,
    logs must contain FAILED and NEVER contain SUCCESS.
    """
    service = ExecutionService(timeout_response_adapter)

    cmd = {
        "verb": "PLACE",
        "symbol": "BNBUSDT",
        "side": "BUY",
        "order_type": "TAKE_PROFIT_MARKET",
        "quantity": "0.76",
        "stop_price": "856.13",
        "reduce_only": True,
        "client_order_id": "AUR-BNBUSDT-SHORT-PLACE_TP-C0-0",
    }

    import logging
    with caplog.at_level(logging.DEBUG):
        result = await service.execute_command(cmd)

    # Result must be failure
    assert result["success"] is False

    # Extract all log messages
    all_messages = [r.getMessage() for r in caplog.records]
    all_text = " ".join(all_messages)

    # INVARIANT: No SUCCESS log
    assert "SHADOW_EXEC_POS_PLACE_SUCCESS" not in all_text, \
        f"SUCCESS should NEVER appear on timeout! Logs: {all_messages}"

    # Must have FAILED log
    assert "SHADOW_EXEC_POS_PLACE_FAILED" in all_text, \
        f"FAILED should appear on timeout. Logs: {all_messages}"


@pytest.mark.asyncio
async def test_mixed_success_then_timeout_correct_logs(mixed_adapter, caplog):
    """
    Test scenario from real log:
    - First call (SL) succeeds → log SUCCESS
    - Second call (TP) times out → log FAILED, NOT SUCCESS

    This ensures we don't leak SUCCESS from previous call.
    """
    service = ExecutionService(mixed_adapter)

    # First command - SL - should succeed
    cmd_sl = {
        "verb": "PLACE",
        "symbol": "BNBUSDT",
        "side": "BUY",
        "order_type": "STOP_MARKET",
        "quantity": "0.76",
        "stop_price": "909.64",
        "reduce_only": True,
        "client_order_id": "AUR-SL-001",
    }

    # Second command - TP - should timeout
    cmd_tp = {
        "verb": "PLACE",
        "symbol": "BNBUSDT",
        "side": "BUY",
        "order_type": "TAKE_PROFIT_MARKET",
        "quantity": "0.76",
        "stop_price": "856.13",
        "reduce_only": True,
        "client_order_id": "AUR-TP-001",
    }

    import logging
    with caplog.at_level(logging.DEBUG):
        result_sl = await service.execute_command(cmd_sl)
        caplog.clear()  # Clear logs between calls
        result_tp = await service.execute_command(cmd_tp)

    # SL succeeded
    assert result_sl["success"] is True

    # TP failed with timeout
    assert result_tp["success"] is False
    assert result_tp.get("is_timeout") is True

    # Check logs for TP call only (caplog was cleared)
    all_messages = [r.getMessage() for r in caplog.records]
    all_text = " ".join(all_messages)

    # INVARIANT: No SUCCESS in TP logs
    assert "SHADOW_EXEC_POS_PLACE_SUCCESS" not in all_text, \
        f"SUCCESS should NOT appear for timeout call! Logs: {all_messages}"

    # FAILED must be present
    assert "SHADOW_EXEC_POS_PLACE_FAILED" in all_text


# ============================================================================
# ERROR KIND VERIFICATION
# ============================================================================

@pytest.mark.asyncio
async def test_timeout_has_correct_error_kind(timeout_exception_adapter):
    """
    Verify that timeout errors have error_kind=ADAPTER_ERROR_TIMEOUT.
    """
    service = ExecutionService(timeout_exception_adapter)

    cmd = {
        "verb": "PLACE",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": "0.001",
        "price": "95000.00",
        "client_order_id": "test-timeout-kind",
    }

    result = await service.execute_command(cmd)

    assert result["success"] is False
    assert result.get("error_kind") == "ADAPTER_ERROR_TIMEOUT"
    assert result.get("is_timeout") is True


@pytest.mark.asyncio
async def test_timeout_response_has_correct_error_kind(timeout_response_adapter):
    """
    Verify that timeout responses pass through error_kind correctly.
    """
    service = ExecutionService(timeout_response_adapter)

    cmd = {
        "verb": "PLACE",
        "symbol": "ETHUSDT",
        "side": "SELL",
        "order_type": "MARKET",
        "quantity": "0.01",
        "client_order_id": "test-timeout-response-kind",
    }

    result = await service.execute_command(cmd)

    assert result["success"] is False
    assert result.get("error_kind") == "ADAPTER_ERROR_TIMEOUT"


# ============================================================================
# should_retry FLAG
# ============================================================================

@pytest.mark.asyncio
async def test_timeout_has_should_retry_false(timeout_exception_adapter):
    """
    Verify that timeout errors have should_retry=False.

    Timeouts are "unknown state" - we don't know if order reached exchange,
    so retrying could create duplicates.
    """
    service = ExecutionService(timeout_exception_adapter)

    cmd = {
        "verb": "PLACE",
        "symbol": "SOLUSDT",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": "1.0",
        "price": "140.00",
        "client_order_id": "test-no-retry",
    }

    result = await service.execute_command(cmd)

    assert result["success"] is False
    # should_retry should be False for timeouts (unknown state)
    assert result.get("should_retry") is False


# ============================================================================
# LOG LEVEL VERIFICATION
# ============================================================================

@pytest.mark.asyncio
async def test_timeout_logs_at_error_level(timeout_exception_adapter, caplog):
    """
    Verify timeout is logged at ERROR level (not WARNING or INFO).

    Timeouts are serious - they indicate network issues or exchange problems.
    """
    service = ExecutionService(timeout_exception_adapter)

    cmd = {
        "verb": "PLACE",
        "symbol": "BNBUSDT",
        "side": "SELL",
        "order_type": "STOP_MARKET",
        "quantity": "0.5",
        "stop_price": "900.00",
        "reduce_only": True,
        "client_order_id": "test-error-level",
    }

    import logging
    with caplog.at_level(logging.DEBUG):
        await service.execute_command(cmd)

    # Find PLACE_FAILED log
    failed_logs = [
        r for r in caplog.records if "PLACE_FAILED" in r.getMessage()]
    assert len(failed_logs) > 0

    # Should be logged at ERROR level
    for log_record in failed_logs:
        assert log_record.levelno >= logging.ERROR, \
            f"Timeout PLACE_FAILED should be ERROR level, got {log_record.levelname}"
