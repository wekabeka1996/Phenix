"""
Tests for ExecutionService._call_adapter method.

Ensures proper async/sync handling and error propagation.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from apps.reference.domains.execution_position.shadow_execpos.execution_service import ExecutionService


class TestCallAdapterAsync:
    """Test _call_adapter with async adapter methods."""

    @pytest.fixture
    def mock_adapter_async(self):
        """Create mock adapter with async create_order."""
        adapter = MagicMock()

        async def mock_create_order(params):
            return {"orderId": 12345, "status": "NEW", "symbol": params.symbol}

        adapter.create_order = mock_create_order
        return adapter

    @pytest.fixture
    def service_with_async_adapter(self, mock_adapter_async):
        return ExecutionService(adapter=mock_adapter_async)

    @pytest.mark.asyncio
    async def test_call_adapter_calls_async_method(self, service_with_async_adapter):
        """_call_adapter should await async methods."""
        params = MagicMock()
        params.symbol = "BNBUSDT"

        result = await service_with_async_adapter._call_adapter(
            "create_order", params=params
        )

        assert result is not None
        assert result["orderId"] == 12345
        assert result["symbol"] == "BNBUSDT"

    @pytest.mark.asyncio
    async def test_call_adapter_no_adapter_returns_none(self):
        """_call_adapter should return None if no adapter."""
        service = ExecutionService(adapter=None)
        result = await service._call_adapter("create_order", params=MagicMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_call_adapter_method_not_found_returns_none(self):
        """_call_adapter should return None if method not found on adapter without MagicMock auto-create."""
        adapter = MagicMock(spec=['create_order'])  # Only has create_order

        async def mock_create_order(params):
            return {"orderId": 1}
        adapter.create_order = mock_create_order

        service = ExecutionService(adapter=adapter)
        result = await service._call_adapter("nonexistent_method")
        assert result is None

    @pytest.mark.asyncio
    async def test_call_adapter_propagates_exception(self):
        """_call_adapter should propagate exceptions from adapter."""
        adapter = MagicMock()

        async def mock_create_order_raises(params):
            raise ValueError("Test error from adapter")

        adapter.create_order = mock_create_order_raises
        service = ExecutionService(adapter=adapter)

        with pytest.raises(ValueError, match="Test error from adapter"):
            await service._call_adapter("create_order", params=MagicMock())


class TestCallAdapterSync:
    """Test _call_adapter with sync adapter methods."""

    @pytest.fixture
    def mock_adapter_sync(self):
        """Create mock adapter with sync method."""
        adapter = MagicMock()
        adapter.get_status = MagicMock(return_value="healthy")
        return adapter

    @pytest.fixture
    def service_with_sync_adapter(self, mock_adapter_sync):
        return ExecutionService(adapter=mock_adapter_sync)

    @pytest.mark.asyncio
    async def test_call_adapter_handles_sync_method(self, service_with_sync_adapter, mock_adapter_sync):
        """_call_adapter should handle sync methods."""
        result = await service_with_sync_adapter._call_adapter("get_status")
        assert result == "healthy"
        mock_adapter_sync.get_status.assert_called_once()


class TestCallAdapterWithRealParams:
    """Test _call_adapter with ExchangeOrderParams-like objects."""

    @pytest.fixture
    def mock_adapter_with_validation(self):
        """Create mock adapter that validates params."""
        adapter = MagicMock()

        async def mock_create_order(params):
            # Simulate validation
            if not hasattr(params, 'symbol'):
                raise ValueError("Missing symbol")
            if not hasattr(params, 'side'):
                raise ValueError("Missing side")
            return {
                "orderId": 99999,
                "symbol": params.symbol,
                "side": params.side,
                "status": "NEW"
            }

        adapter.create_order = mock_create_order
        return adapter

    @pytest.mark.asyncio
    async def test_call_adapter_passes_params_correctly(self, mock_adapter_with_validation):
        """Params should be passed to adapter method correctly."""
        service = ExecutionService(adapter=mock_adapter_with_validation)

        params = MagicMock()
        params.symbol = "SOLUSDT"
        params.side = "SELL"
        params.order_type = "STOP_MARKET"
        params.stop_price = "135.05"

        result = await service._call_adapter("create_order", params=params)

        assert result["symbol"] == "SOLUSDT"
        assert result["side"] == "SELL"


class TestExecutePlace:
    """Test _execute_place method integration."""

    @pytest.fixture
    def mock_adapter_create_order(self):
        """Create adapter that returns successful order."""
        adapter = MagicMock()

        async def mock_create_order(params):
            return MagicMock(
                to_dict=lambda: {
                    "orderId": 123456,
                    "symbol": params.symbol,
                    "status": "NEW",
                    "side": params.side,
                }
            )

        adapter.create_order = mock_create_order
        return adapter

    @pytest.mark.asyncio
    async def test_execute_place_calls_create_order(self, mock_adapter_create_order):
        """_execute_place should call adapter.create_order."""
        service = ExecutionService(adapter=mock_adapter_create_order)

        cmd = {
            "verb": "PLACE",
            "symbol": "BNBUSDT",
            "side": "SELL",
            "order_type": "STOP_MARKET",
            "stop_price": "878.08",
            "quantity": None,
            "extra_params": {"close_position": True},
        }

        result = await service._execute_place(cmd)

        assert result["success"] is True
        assert str(result["order_id"]) == "123456"  # order_id may be str

    @pytest.mark.asyncio
    async def test_execute_place_handles_adapter_error(self):
        """_execute_place should handle adapter errors gracefully."""
        adapter = MagicMock()

        async def mock_create_order_fails(params):
            raise ConnectionError("Network timeout")

        adapter.create_order = mock_create_order_fails
        service = ExecutionService(adapter=adapter)

        cmd = {
            "verb": "PLACE",
            "symbol": "BNBUSDT",
            "side": "SELL",
            "order_type": "STOP_MARKET",
            "stop_price": "878.08",
            "extra_params": {"close_position": True},
        }

        result = await service._execute_place(cmd)

        assert result["success"] is False
        assert "Network timeout" in result.get("error", "")


class TestPlaceOrderIntegration:
    """Integration tests for place_order convenience method."""

    @pytest.fixture
    def successful_adapter(self):
        """Adapter that returns successful order."""
        adapter = MagicMock()

        async def mock_create_order(params):
            return MagicMock(
                to_dict=lambda: {
                    "orderId": 999,
                    "status": "NEW",
                    "symbol": params.symbol,
                }
            )

        adapter.create_order = mock_create_order
        return adapter

    @pytest.mark.asyncio
    async def test_place_order_stop_market_with_close_position(self, successful_adapter):
        """place_order for STOP_MARKET with closePosition should work."""
        service = ExecutionService(adapter=successful_adapter)

        result = await service.place_order(
            symbol="SOLUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            quantity=None,
            stop_price="135.05",
            close_position=True,
        )

        assert result["success"] is True
        assert str(result["order_id"]) == "999"  # order_id may be str

    @pytest.mark.asyncio
    async def test_place_order_take_profit_market(self, successful_adapter):
        """place_order for TAKE_PROFIT_MARKET should work."""
        service = ExecutionService(adapter=successful_adapter)

        result = await service.place_order(
            symbol="ETHUSDT",
            side="SELL",
            order_type="TAKE_PROFIT_MARKET",
            quantity=None,
            stop_price="3200.00",
            close_position=True,
        )

        assert result["success"] is True


class TestAdapterTypeDetection:
    """Test that adapter type is correctly detected."""

    @pytest.mark.asyncio
    async def test_asyncio_iscoroutinefunction_detects_async(self):
        """asyncio.iscoroutinefunction should detect async def."""
        async def async_func():
            pass

        def sync_func():
            pass

        assert asyncio.iscoroutinefunction(async_func) is True
        assert asyncio.iscoroutinefunction(sync_func) is False

    @pytest.mark.asyncio
    async def test_adapter_create_order_is_async(self):
        """BinanceAdapter.create_order should be detected as async."""
        # This tests that our detection logic would work
        from apps.reference.adapters.binance_adapter import BinanceAdapter

        adapter = BinanceAdapter(shadow_mode=True)

        # create_order should be async
        assert asyncio.iscoroutinefunction(adapter.create_order) is True
