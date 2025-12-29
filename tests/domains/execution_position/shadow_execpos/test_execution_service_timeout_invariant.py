"""
Tests for ExecutionService Timeout Invariant (EP-EXEC-SHADOW-TIMEOUT-INVARIANT-S22).

Invariant:
"If an adapter call times out (exception or timeout response), ExecutionService MUST log SHADOW_EXEC_POS_PLACE_FAILED
and MUST NOT log SHADOW_EXEC_POS_PLACE_SUCCESS."

This ensures that timeouts are never mistaken for successful placements in the logs,
preventing false positives in monitoring.
"""
import pytest
import logging
from unittest.mock import Mock, AsyncMock
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


class FakeAdapterWithTimeout:
    """Adapter that raises ConnectTimeout."""

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

    async def place_order_v2(self, **kwargs):
        if httpx:
            raise httpx.ConnectTimeout("Timeout connecting to exchange")
        else:
            raise TimeoutError("Timeout connecting to exchange")

    async def place_order(self, **kwargs):
        return await self.place_order_v2(**kwargs)


class FakeAdapterWithTimeoutResponse:
    """Adapter that returns a timeout-like error response (no exception)."""

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

    async def place_order_v2(self, **kwargs):
        return {
            "success": False,
            "error": "Timeout waiting for response",
            "error_kind": "ADAPTER_ERROR_TIMEOUT",
            "orderId": None,
        }

    async def place_order(self, **kwargs):
        return await self.place_order_v2(**kwargs)


class FakeAdapterMixed:
    """Adapter that succeeds for SL, times out for TP."""

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

    async def place_order_v2(self, **kwargs):
        cid = kwargs.get("client_order_id", "")
        if "TP" in cid:
            if httpx:
                raise httpx.ConnectTimeout("Timeout on TP")
            else:
                raise TimeoutError("Timeout on TP")
        return {
            "success": True,
            "orderId": "success-123",
            "clientOrderId": cid,
            "status": "NEW",
        }

    async def place_order(self, **kwargs):
        return await self.place_order_v2(**kwargs)


@pytest.fixture
def sl_command() -> ExecutionCommand:
    return {
        "verb": "PLACE",
        "symbol": "BNBUSDT",
        "side": "BUY",
        "order_type": "STOP_MARKET",
        "quantity": "0.76",
        "stop_price": "909.64",
        "reduce_only": True,
        "client_order_id": "AUR-BNBUSDT-SHORT-PLACE_SL-C0-0",
        "extra_params": {},
    }


@pytest.fixture
def tp_command() -> ExecutionCommand:
    return {
        "verb": "PLACE",
        "symbol": "BNBUSDT",
        "side": "BUY",
        "order_type": "TAKE_PROFIT_MARKET",
        "quantity": "0.76",
        "stop_price": "856.13",
        "reduce_only": True,
        "client_order_id": "AUR-BNBUSDT-SHORT-PLACE_TP-C0-0",
        "extra_params": {},
    }


@pytest.mark.asyncio
async def test_timeout_exception_never_logs_success(sl_command, caplog):
    """
    Scenario: Adapter raises ConnectTimeout.
    Invariant Check: Log MUST contain FAILED, MUST NOT contain SUCCESS.
    """
    if httpx is None:
        pytest.skip("httpx not installed")

    service = ExecutionService(adapter=FakeAdapterWithTimeout())

    with caplog.at_level(logging.INFO):
        result = await service.execute_command(sl_command)

    # 1. Verify result is failed
    assert result["success"] is False
    assert result.get("is_timeout") is True

    # 2. Verify logs
    log_messages = [record.message for record in caplog.records]
    all_text = " ".join(log_messages)

    assert "SHADOW_EXEC_POS_PLACE_FAILED" in all_text, \
        f"FAILED should appear on timeout. Logs: {log_messages}"
    assert "SHADOW_EXEC_POS_PLACE_SUCCESS" not in all_text, \
        f"SUCCESS must NOT appear on timeout. Logs: {log_messages}"


@pytest.mark.asyncio
async def test_timeout_response_never_logs_success(tp_command, caplog):
    """
    Scenario: Adapter returns error_kind=ADAPTER_ERROR_TIMEOUT (no exception).
    Invariant Check: Log MUST contain FAILED, MUST NOT contain SUCCESS.
    """
    service = ExecutionService(adapter=FakeAdapterWithTimeoutResponse())

    with caplog.at_level(logging.INFO):
        result = await service.execute_command(tp_command)

    # 1. Verify result is failed
    assert result["success"] is False
    assert result.get("error_kind") == "ADAPTER_ERROR_TIMEOUT"

    # 2. Verify logs
    log_messages = [record.message for record in caplog.records]
    all_text = " ".join(log_messages)

    assert "SHADOW_EXEC_POS_PLACE_FAILED" in all_text, \
        f"FAILED should appear on timeout. Logs: {log_messages}"
    assert "SHADOW_EXEC_POS_PLACE_SUCCESS" not in all_text, \
        f"SUCCESS must NOT appear on timeout. Logs: {log_messages}"


@pytest.mark.asyncio
async def test_mixed_success_then_timeout_correct_logs(caplog):
    """
    Scenario: SL succeeds, TP times out.
    Invariant Check:
    - SL logs SUCCESS
    - TP logs FAILED
    - TP does NOT log SUCCESS
    """
    if httpx is None:
        pytest.skip("httpx not installed")

    service = ExecutionService(adapter=FakeAdapterMixed())

    cmd_sl = {
        "verb": "PLACE",
        "symbol": "BNBUSDT",
        "side": "BUY",
        "order_type": "STOP_MARKET",
        "quantity": "0.76",
        "stop_price": "909.64",
        "reduce_only": True,
        "client_order_id": "AUR-SL-001",
        "extra_params": {},
    }

    cmd_tp = {
        "verb": "PLACE",
        "symbol": "BNBUSDT",
        "side": "BUY",
        "order_type": "TAKE_PROFIT_MARKET",
        "quantity": "0.76",
        "stop_price": "856.13",
        "reduce_only": True,
        "client_order_id": "AUR-TP-001",
        "extra_params": {},
    }

    with caplog.at_level(logging.INFO):
        # 1. Run SL (Success)
        result_sl = await service.execute_command(cmd_sl)
        # 2. Run TP (Timeout)
        result_tp = await service.execute_command(cmd_tp)

    # Verify results
    assert result_sl["success"] is True
    assert result_tp["success"] is False
    assert result_tp.get("is_timeout") is True

    # Verify logs
    log_messages = [record.message for record in caplog.records]
    all_text = " ".join(log_messages)

    # SL should have SUCCESS (somewhere in the logs)
    assert "SHADOW_EXEC_POS_PLACE_SUCCESS" in all_text, \
        "SL should log SUCCESS"

    # TP should have FAILED (somewhere in the logs)
    assert "SHADOW_EXEC_POS_PLACE_FAILED" in all_text, \
        "TP should log FAILED"

    # To be stricter, we'd need to correlate log lines, but for this invariant test,
    # ensuring SUCCESS appears (for SL) and FAILED appears (for TP) is a good baseline.
    # The critical check is that we don't have *two* SUCCESS logs if one failed.
    # But we can't easily count them without parsing.

    # Let's check that we have at least one SUCCESS and at least one FAILED.
    success_count = sum(1 for m in log_messages if "SHADOW_EXEC_POS_PLACE_SUCCESS" in m)
    failed_count = sum(1 for m in log_messages if "SHADOW_EXEC_POS_PLACE_FAILED" in m)

    assert success_count == 1, f"Expected exactly 1 SUCCESS log, got {success_count}"
    assert failed_count == 1, f"Expected exactly 1 FAILED log, got {failed_count}"
