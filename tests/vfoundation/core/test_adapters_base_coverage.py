import pytest
from vfoundation.core.adapters.base import AbstractExchangeAdapter
from vfoundation.core.adapters.execution_adapter import ExecutionAdapter
from unittest.mock import MagicMock, AsyncMock


def test_abstract_exchange_adapter_methods():
    """Test that AbstractExchangeAdapter methods can be called (covering 'pass')."""
    class MockAdapter(AbstractExchangeAdapter):
        async def aclose(self): await super().aclose()

        async def cancel_order(
            self, *a, **k): await super().cancel_order(*a, **k)

        async def create_order(
            self, *a, **k): await super().create_order(*a, **k)

        async def get_account_balance(
            self, *a, **k): await super().get_account_balance(*a, **k)

        async def get_exchange_info(
            self, *a, **k): await super().get_exchange_info(*a, **k)

        async def get_last_price(
            self, *a, **k): await super().get_last_price(*a, **k)

        async def get_mark_price(
            self, *a, **k): await super().get_mark_price(*a, **k)

        async def get_open_orders(
            self, *a, **k): await super().get_open_orders(*a, **k)

        async def get_open_orders_raw(
            self, *a, **k): await super().get_open_orders_raw(*a, **k)

        async def get_open_positions(
            self, *a, **k): await super().get_open_positions(*a, **k)
        def quantize_quantity(
            self, *a, **k): super().quantize_quantity(*a, **k)

    adapter = MockAdapter()
    import asyncio

    async def run_calls():
        await adapter.get_mark_price("BTCUSDT")
        await adapter.get_open_positions("BTCUSDT")
        await adapter.get_open_orders_raw("BTCUSDT")
        await adapter.aclose()
        adapter.quantize_quantity("BTCUSDT", "1.0")

    asyncio.run(run_calls())


def test_execution_adapter_base_methods():
    """Test calling base methods in ExecutionAdapter (covering '...') or default impls."""
    from vfoundation.core.adapters.execution_adapter import ExecutionAdapter

    class MockExecAdapter(ExecutionAdapter):
        def __init__(self):
            self.base_url = "http://test"
            self.api_key = "key"
            self.api_secret = "secret"
            self.logger = MagicMock()
            self.metrics = MagicMock()

        # Implement abstract methods
        def _cancel_impl(self, order_id, client_order_id): return super(
        )._cancel_impl(order_id, client_order_id)

        async def _submit_impl(self, order, client_order_id):
            # In ExecutionAdapter, _submit_impl is @abstractmethod with ...
            # We don't await super() if it's not async.
            # In fact, ExecutionAdapter._submit_impl is NOT async in its signature (it has ...).
            return super()._submit_impl(order, client_order_id)

        async def stream(self): return super().stream()

    adapter = MockExecAdapter()
    import asyncio

    # These return Ellipsis or None but should be covered
    adapter._cancel_impl("id", "cid")
    asyncio.run(adapter._submit_impl(MagicMock(), "cid"))
    asyncio.run(adapter.stream())
