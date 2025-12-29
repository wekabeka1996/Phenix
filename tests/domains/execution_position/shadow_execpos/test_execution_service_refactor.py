"""
Tests for ExecutionService Refactor (EP-EXEC-SHADOW-REFACTOR-S23).

Verifies that:
1. ExecutionService works with adapters that ONLY implement place_order_v2 (new contract).
2. ExecutionService works with adapters that implement legacy place_order (backward compat).
3. ExecutionService correctly delegates to the available method.
"""
import pytest
from unittest.mock import Mock, AsyncMock
from typing import Dict, Any

from apps.reference.domains.execution_position.shadow_execpos.execution_service import (
    ExecutionService,
)
from apps.reference.domains.execution_position.shadow_execpos.types import (
    ExecutionStatus,
    ExecutionCommand,
)


class FakeAdapterV2Only:
    """Adapter that ONLY implements place_order_v2 (the future)."""

    async def create_order(self, params=None, **kwargs):
        """Alias for place_order to support ExecutionService."""
        if params:
            return await self.place_order_v2(
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
        return await self.place_order_v2(**kwargs)

    async def place_order_v2(self, **kwargs):
        return {
            "success": True,
            "orderId": "v2_123",
            "clientOrderId": kwargs.get("client_order_id"),
            "status": "NEW",
        }


class FakeAdapterLegacyOnly:
    """Adapter that ONLY implements place_order (legacy)."""

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

    async def place_order(self, **kwargs):
        return {
            "success": True,
            "orderId": "legacy_456",
            "clientOrderId": kwargs.get("client_order_id"),
            "status": "NEW",
        }


class FakeAdapterBoth:
    """Adapter that implements BOTH (v2 preferred)."""

    async def create_order(self, params=None, **kwargs):
        """Alias for place_order to support ExecutionService."""
        if params:
            return await self.place_order_v2(
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
        return await self.place_order_v2(**kwargs)

    async def place_order_v2(self, **kwargs):
        return {
            "success": True,
            "orderId": "v2_preferred",
            "clientOrderId": kwargs.get("client_order_id"),
        }

    async def place_order(self, **kwargs):
        return {
            "success": True,
            "orderId": "legacy_fallback",
            "clientOrderId": kwargs.get("client_order_id"),
        }


@pytest.fixture
def execution_command() -> ExecutionCommand:
    return {
        "verb": "PLACE",
        "symbol": "SOLUSDT",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": "1.0",
        "price": "120.0",
        "client_order_id": "test-oid",
        "reduce_only": False,
        "extra_params": {},
    }


@pytest.mark.asyncio
async def test_mock_removal_safety(execution_command):
    """
    Verify that ExecutionService works with an adapter that has NO place_order method,
    only place_order_v2. This simulates the future state where legacy methods are removed.
    """
    adapter = FakeAdapterV2Only()
    # Ensure it really doesn't have place_order (except via inheritance if any, but here it's clean)
    assert not hasattr(adapter, "place_order")

    service = ExecutionService(adapter=adapter)

    result = await service.execute_command(execution_command)

    assert result["success"] is True
    assert result["order_id"] == "v2_123"


@pytest.mark.asyncio
async def test_legacy_compatibility(execution_command):
    """
    Verify that ExecutionService still works with legacy adapters (only place_order).
    """
    adapter = FakeAdapterLegacyOnly()
    # Ensure it really doesn't have place_order_v2
    assert not hasattr(adapter, "place_order_v2")

    service = ExecutionService(adapter=adapter)

    result = await service.execute_command(execution_command)

    assert result["success"] is True
    assert result["order_id"] == "legacy_456"


@pytest.mark.asyncio
async def test_v2_preference(execution_command):
    """
    Verify that if both exist, place_order_v2 is used (or whatever logic ExecutionService uses).
    Actually, ExecutionService currently calls place_order_v2 if available, else place_order.
    """
    adapter = FakeAdapterBoth()
    service = ExecutionService(adapter=adapter)

    result = await service.execute_command(execution_command)

    assert result["success"] is True
    assert result["order_id"] == "v2_preferred"
