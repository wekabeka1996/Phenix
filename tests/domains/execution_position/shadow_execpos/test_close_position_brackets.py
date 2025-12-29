"""
Tests for closePosition bracket orders (TP/SL).

closePosition=true is used for Binance Futures SL/TP orders that should
close the ENTIRE position when triggered, regardless of the position size
at trigger time.

Key requirements:
1. quantity must NOT be sent to Binance when closePosition=true
2. ExecutionRequest must accept quantity=None
3. execution_service must not require quantity when close_position=True
4. BinanceAdapter must exclude quantity from API params when closePosition=true
"""
import logging
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from apps.reference.domains.execution_position.contracts import ExecutionRequest
from apps.reference.domains.execution_position.shadow_execpos.execution_service import (
    ExecutionService,
)
from apps.reference.adapters.binance_adapter import BinanceAdapter, ExchangeOrderParams


class TestExecutionRequestWithClosePosition:
    """Test that ExecutionRequest accepts quantity=None."""

    def test_execution_request_with_quantity(self):
        """Standard request with quantity should work."""
        req = ExecutionRequest(
            symbol="BTCUSDT",
            side="SELL",
            quantity=Decimal("0.01"),
            order_type="STOP_MARKET",
            stop_price=Decimal("90000"),
        )
        assert req.quantity == Decimal("0.01")
        assert req.symbol == "BTCUSDT"

    def test_execution_request_without_quantity(self):
        """Request without quantity (for closePosition) should work."""
        req = ExecutionRequest(
            symbol="BTCUSDT",
            side="SELL",
            quantity=None,
            order_type="STOP_MARKET",
            stop_price=Decimal("90000"),
        )
        assert req.quantity is None
        assert req.symbol == "BTCUSDT"
        assert req.stop_price == Decimal("90000")

    def test_execution_request_quantity_default_none(self):
        """Request with missing quantity should default to None."""
        req = ExecutionRequest(
            symbol="ETHUSDT",
            side="BUY",
            order_type="TAKE_PROFIT_MARKET",
            stop_price=Decimal("4000"),
        )
        assert req.quantity is None


class TestExecutionServiceClosePosition:
    """Test execution_service handles close_position correctly."""

    @pytest.fixture
    def mock_adapter(self):
        """Create mock adapter."""
        adapter = MagicMock()
        adapter.create_order = AsyncMock(return_value={
            "orderId": "123456",
            "clientOrderId": "test-client-id",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "origQty": "0",
            "executedQty": "0",
            "status": "NEW",
            "time": 1234567890000,
        })
        return adapter

    @pytest.fixture
    def exec_service(self, mock_adapter):
        """Create execution service with mock adapter."""
        return ExecutionService(mock_adapter)

    @pytest.mark.asyncio
    async def test_place_order_with_close_position_no_quantity(self, exec_service):
        """place_order should succeed with close_position=True and no quantity."""
        result = await exec_service.place_order(
            symbol="BTCUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            quantity=None,  # No quantity for closePosition
            stop_price="90000",
            client_order_id="test-sl-order",
            reduce_only=False,
            close_position=True,  # This is the key
        )

        # Should succeed, not fail with "Missing quantity"
        assert result.get("success") is True or result.get("order_id") is not None, \
            f"Expected success but got: {result}"

    @pytest.mark.asyncio
    async def test_place_order_without_close_position_requires_quantity(self, exec_service):
        """place_order should fail without quantity when close_position=False."""
        result = await exec_service.place_order(
            symbol="BTCUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            quantity=None,  # Missing quantity
            stop_price="90000",
            client_order_id="test-sl-order",
            reduce_only=False,
            # close_position not specified = False
        )

        # Should fail with missing quantity error
        assert result.get("success") is False
        assert "quantity" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_place_order_standard_with_quantity(self, exec_service):
        """Standard place_order with quantity should work."""
        result = await exec_service.place_order(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity="0.01",
            price="90000",
            client_order_id="test-limit-order",
            reduce_only=False,
        )

        # Should succeed
        assert result.get("success") is True or result.get(
            "order_id") is not None


class TestBinanceAdapterClosePosition:
    """Test BinanceAdapter handles closePosition correctly."""

    def test_exchange_order_params_with_close_position(self):
        """ExchangeOrderParams should accept close_position."""
        params = ExchangeOrderParams(
            symbol="SOLUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            quantity=None,  # No quantity for closePosition
            stop_price="140.00",
            close_position=True,
        )
        assert params.close_position is True
        assert params.quantity is None

    @pytest.mark.asyncio
    async def test_create_order_excludes_quantity_for_close_position(self):
        """create_order should NOT send quantity when closePosition=true."""
        # Mock the _request method to capture params
        captured_params = {}

        async def mock_request(method, path, params):
            captured_params.update(params)
            return {
                "orderId": "999",
                "clientOrderId": "test",
                "symbol": "SOLUSDT",
                "side": "SELL",
                "origQty": "1",
                "executedQty": "0",
                "status": "NEW",
                "time": 1234567890000,
            }

        adapter = BinanceAdapter.__new__(BinanceAdapter)
        adapter._request = mock_request
        adapter._exchange_info_cache = {}  # Precision normalization cache
        adapter.logger = logging.getLogger(__name__)

        params = ExchangeOrderParams(
            symbol="SOLUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            quantity=None,
            stop_price="140.00",
            close_position=True,
            client_order_id="test-sl",
        )

        await adapter.create_order(params)

        # Verify quantity NOT in params, but closePosition IS
        assert "quantity" not in captured_params, \
            f"quantity should NOT be sent for closePosition=true, got: {captured_params}"
        assert captured_params.get("closePosition") == "true", \
            f"closePosition should be 'true', got: {captured_params}"
        # stopPrice is normalized (trailing zeros removed)
        assert Decimal(captured_params.get("stopPrice")) == Decimal("140.00")

    @pytest.mark.asyncio
    async def test_create_order_includes_quantity_for_regular_order(self):
        """create_order SHOULD send quantity for regular orders."""
        captured_params = {}

        async def mock_request(method, path, params):
            captured_params.update(params)
            return {
                "orderId": "999",
                "clientOrderId": "test",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "origQty": "0.01",
                "executedQty": "0",
                "status": "NEW",
                "time": 1234567890000,
            }

        adapter = BinanceAdapter.__new__(BinanceAdapter)
        adapter._request = mock_request
        adapter._exchange_info_cache = {}  # Precision normalization cache
        adapter.logger = logging.getLogger(__name__)

        params = ExchangeOrderParams(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity="0.01",
            price="90000",
            time_in_force="GTC",
            close_position=False,
            client_order_id="test-limit",
        )

        await adapter.create_order(params)

        # Verify quantity IS in params
        assert captured_params.get("quantity") == "0.01", \
            f"quantity should be sent for regular orders, got: {captured_params}"
        assert "closePosition" not in captured_params, \
            f"closePosition should NOT be sent when False, got: {captured_params}"


class TestBracketOrderFlow:
    """Integration tests for the full bracket order flow."""

    @pytest.mark.asyncio
    async def test_stop_loss_bracket_command(self):
        """Test SL bracket command flows correctly with closePosition."""
        from apps.reference.domains.execution_position.shadow_execpos.execution_service import (
            ExecutionService,
        )

        # Track what adapter receives
        received_params = None

        async def mock_create_order(params):
            nonlocal received_params
            received_params = params
            return MagicMock(
                to_dict=lambda: {
                    "orderId": "12345",
                    "clientOrderId": params.client_order_id,
                    "symbol": params.symbol,
                    "side": params.side,
                    "origQty": "0",
                    "executedQty": "0",
                    "status": "NEW",
                    "time": 1234567890000,
                }
            )

        mock_adapter = MagicMock()
        mock_adapter.create_order = mock_create_order

        service = ExecutionService(mock_adapter)

        # Simulate bracket SL placement from runtime
        result = await service.place_order(
            symbol="ETHUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            quantity=None,  # closePosition doesn't need qty
            stop_price="2900.00",
            client_order_id="AUR-ETHUSDT-LONG-PLACE_SL-C0-0.1",
            reduce_only=False,
            close_position=True,
        )

        # Verify success
        assert result.get("success") is True or result.get("order_id"), \
            f"SL bracket should succeed: {result}"

        # Verify adapter received correct params
        assert received_params is not None, "Adapter should have been called"
        assert received_params.close_position is True
        assert received_params.quantity is None or received_params.quantity == "None"

    @pytest.mark.asyncio
    async def test_take_profit_bracket_command(self):
        """Test TP bracket command flows correctly with closePosition."""
        from apps.reference.domains.execution_position.shadow_execpos.execution_service import (
            ExecutionService,
        )

        received_params = None

        async def mock_create_order(params):
            nonlocal received_params
            received_params = params
            return MagicMock(
                to_dict=lambda: {
                    "orderId": "12346",
                    "clientOrderId": params.client_order_id,
                    "symbol": params.symbol,
                    "side": params.side,
                    "origQty": "0",
                    "executedQty": "0",
                    "status": "NEW",
                    "time": 1234567890000,
                }
            )

        mock_adapter = MagicMock()
        mock_adapter.create_order = mock_create_order

        service = ExecutionService(mock_adapter)

        # Simulate bracket TP placement from runtime
        result = await service.place_order(
            symbol="ETHUSDT",
            side="SELL",
            order_type="TAKE_PROFIT_MARKET",
            quantity=None,
            stop_price="3200.00",
            client_order_id="AUR-ETHUSDT-LONG-PLACE_TP-C0-0.1",
            reduce_only=False,
            close_position=True,
        )

        assert result.get("success") is True or result.get("order_id"), \
            f"TP bracket should succeed: {result}"

        assert received_params is not None
        assert received_params.close_position is True


class TestSymbolExecutorGatekeeper:
    """Test SymbolExecutorV2 correctly uses GateDecision TypedDict."""

    def test_validate_and_round_with_dict_gatekeeper(self):
        """SymbolExecutorV2 should handle GateDecision as TypedDict (dict)."""
        from apps.reference.domains.execution_position.shadow_execpos.symbol_executor import (
            SymbolExecutorV2,
        )

        # Create a mock gatekeeper that returns GateDecision (TypedDict = dict)
        class MockGatekeeper:
            def validate_order(self, symbol, qty, price):
                # GateDecision is a TypedDict, so it's a dict!
                return {
                    "allowed": True,
                    "reason": "OK",
                    "modified_params": {
                        "quantity": "0.5",
                        "price": "100.00",
                    },
                    "metadata": {"symbol": symbol}
                }

            def get_instrument_specs(self, symbol):
                return {
                    "symbol": symbol,
                    "step_size": "0.01",
                    "tick_size": "0.01",
                    "min_qty": "0.01",
                    "min_notional": "5.0",
                }

        mock_adapter = MagicMock()
        mock_gatekeeper = MockGatekeeper()

        # V2: No sl_pct/tp_rr - BracketService is single source of truth
        executor = SymbolExecutorV2(
            symbol="TESTUSDT",
            adapter=mock_adapter,
            gatekeeper=mock_gatekeeper,
        )

        # This should NOT raise "'dict' object has no attribute 'allowed'"
        rounded_qty, rounded_price, error = executor._validate_and_round(
            quantity="0.5123",
            price="100.123"
        )

        assert error is None, f"Should not have error: {error}"
        assert rounded_qty == "0.5"
        assert rounded_price == "100.00"

    def test_validate_and_round_rejected(self):
        """SymbolExecutorV2 handles rejected GateDecision correctly."""
        from apps.reference.domains.execution_position.shadow_execpos.symbol_executor import (
            SymbolExecutorV2,
        )

        class MockGatekeeper:
            def validate_order(self, symbol, qty, price):
                return {
                    "allowed": False,
                    "reason": "MIN_QTY_VIOLATION",
                    "modified_params": {},
                    "metadata": {"symbol": symbol}
                }

        mock_adapter = MagicMock()
        mock_gatekeeper = MockGatekeeper()

        # V2: No sl_pct/tp_rr - BracketService is single source of truth
        executor = SymbolExecutorV2(
            symbol="TESTUSDT",
            adapter=mock_adapter,
            gatekeeper=mock_gatekeeper,
        )

        rounded_qty, rounded_price, error = executor._validate_and_round(
            quantity="0.00001",  # Too small
            price="100.00"
        )

        assert rounded_qty is None
        assert rounded_price is None
        assert "MIN_QTY_VIOLATION" in error
