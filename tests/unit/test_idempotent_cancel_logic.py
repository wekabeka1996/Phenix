import pytest
from unittest.mock import AsyncMock, MagicMock
from apps.reference.domains.execution_position.idempotent_cancel import IdempotentCancelHelper
from apps.reference.adapters.binance_adapter import BinanceAPIError

@pytest.mark.asyncio
class TestIdempotentCancelLogic:
    async def test_cancel_order_idempotent_success(self):
        """Test successful cancellation."""
        helper = IdempotentCancelHelper()
        
        # Mock get_order_func to return NEW order
        get_order_mock = AsyncMock(return_value={"status": "NEW", "orderId": "123"})
        
        # Mock cancel_func to return CANCELED status
        cancel_mock = AsyncMock(return_value={"status": "CANCELED", "orderId": "123"})
        
        result = await helper.cancel_order_idempotent(
            symbol="BTCUSDT",
            order_id="123",
            cancel_func=cancel_mock,
            get_order_func=get_order_mock,
            max_retries=2
        )
        
        assert result.success is True
        assert result.reason == "CANCEL_SUCCESS"
        assert result.order_status_after == "CANCELED"
        
        get_order_mock.assert_called_once()
        cancel_mock.assert_called_once()

    async def test_cancel_order_idempotent_pre_check_terminal(self):
        """Test pre-check finding terminal state."""
        helper = IdempotentCancelHelper()
        
        # Mock get_order_func to return FILLED order
        get_order_mock = AsyncMock(return_value={"status": "FILLED", "orderId": "123"})
        cancel_mock = AsyncMock()
        
        result = await helper.cancel_order_idempotent(
            symbol="BTCUSDT",
            order_id="123",
            cancel_func=cancel_mock,
            get_order_func=get_order_mock
        )
        
        assert result.success is True
        assert result.reason == "PRE_CHECK_TERMINAL_FILLED"
        assert result.order_status_before == "FILLED"
        
        get_order_mock.assert_called_once()
        cancel_mock.assert_not_called()

    async def test_cancel_order_idempotent_2011_absorption(self):
        """Test absorption of -2011 error."""
        helper = IdempotentCancelHelper()
        
        # Mock get_order_func to return NEW order (or fail, but let's say it returns NEW then disappears)
        get_order_mock = AsyncMock(return_value={"status": "NEW", "orderId": "123"})
        
        # Mock cancel_func to return -2011 error
        cancel_mock = AsyncMock(return_value={"code": -2011, "msg": "Unknown order"})
        
        result = await helper.cancel_order_idempotent(
            symbol="BTCUSDT",
            order_id="123",
            cancel_func=cancel_mock,
            get_order_func=get_order_mock
        )
        
        assert result.success is True
        assert result.reason == "IDEMPOTENT_-2011_ABSORBED"
        assert result.error_code == -2011
        
        cancel_mock.assert_called_once()

    async def test_double_cancel_is_idempotent_success(self):
        """Second cancel returning -2011 must be treated as success."""
        helper = IdempotentCancelHelper()

        get_order_mock = AsyncMock(return_value={"status": "NEW", "orderId": "123"})

        cancel_mock = AsyncMock(side_effect=[
            {"status": "CANCELED", "orderId": "123"},
            {"code": -2011, "msg": "Unknown order"},
        ])

        r1 = await helper.cancel_order_idempotent(
            symbol="BTCUSDT",
            order_id="123",
            cancel_func=cancel_mock,
            get_order_func=get_order_mock,
            max_retries=1,
        )
        r2 = await helper.cancel_order_idempotent(
            symbol="BTCUSDT",
            order_id="123",
            cancel_func=cancel_mock,
            get_order_func=get_order_mock,
            max_retries=1,
        )

        assert r1.success is True
        assert r1.reason == "CANCEL_SUCCESS"
        assert r2.success is True
        assert r2.reason == "IDEMPOTENT_-2011_ABSORBED"

    async def test_cancel_order_idempotent_retries(self):
        """Test retry logic on transient errors."""
        helper = IdempotentCancelHelper()
        
        get_order_mock = AsyncMock(return_value={"status": "NEW", "orderId": "123"})
        
        # Mock cancel_func to fail twice then succeed
        # Note: The helper catches Exception, not just returns error dict for exceptions
        cancel_mock = AsyncMock(side_effect=[
            Exception("Network error"),
            {"status": "CANCELED"}
        ])
        
        # We need to mock _backoff_wait to speed up test
        helper._backoff_wait = AsyncMock()
        
        result = await helper.cancel_order_idempotent(
            symbol="BTCUSDT",
            order_id="123",
            cancel_func=cancel_mock,
            get_order_func=get_order_mock,
            max_retries=3
        )
        
        assert result.success is True
        assert result.reason == "CANCEL_SUCCESS"
        assert cancel_mock.call_count == 2
        helper._backoff_wait.assert_called_once_with(0)

    async def test_cancel_order_idempotent_max_retries_exceeded(self):
        """Test failure after max retries."""
        helper = IdempotentCancelHelper()
        
        get_order_mock = AsyncMock(return_value={"status": "NEW", "orderId": "123"})
        cancel_mock = AsyncMock(side_effect=Exception("Persistent error"))
        
        helper._backoff_wait = AsyncMock()
        
        result = await helper.cancel_order_idempotent(
            symbol="BTCUSDT",
            order_id="123",
            cancel_func=cancel_mock,
            get_order_func=get_order_mock,
            max_retries=2
        )
        
        assert result.success is False
        assert "EXCEPTION_AFTER_2_RETRIES" in result.reason
        assert cancel_mock.call_count == 2

    async def test_cancel_2011_exception_absorbed_as_success(self):
        """-2011 BinanceAPIError exception must be absorbed as idempotent success."""
        helper = IdempotentCancelHelper()

        get_order_mock = AsyncMock(return_value={"status": "NEW", "orderId": "123"})
        cancel_mock = AsyncMock(
            side_effect=BinanceAPIError(code=-2011, msg="Unknown order sent.")
        )
        helper._backoff_wait = AsyncMock()

        result = await helper.cancel_order_idempotent(
            symbol="BTCUSDT",
            order_id="123",
            cancel_func=cancel_mock,
            get_order_func=get_order_mock,
            max_retries=2,
        )

        assert result.success is True
        assert result.reason == "IDEMPOTENT_-2011_ABSORBED_EXC"
        assert result.is_idempotent_success is True
        assert result.error_code == -2011
        assert cancel_mock.call_count == 1
        helper._backoff_wait.assert_not_called()

    async def test_cancel_2013_exception_absorbed_as_success(self):
        """-2013 BinanceAPIError exception must be absorbed as idempotent success."""
        helper = IdempotentCancelHelper()

        get_order_mock = AsyncMock(return_value={"status": "NEW", "orderId": "123"})
        cancel_mock = AsyncMock(
            side_effect=BinanceAPIError(code=-2013, msg="Order does not exist.")
        )
        helper._backoff_wait = AsyncMock()

        result = await helper.cancel_order_idempotent(
            symbol="BTCUSDT",
            order_id="123",
            cancel_func=cancel_mock,
            get_order_func=get_order_mock,
            max_retries=2,
        )

        assert result.success is True
        assert result.reason == "IDEMPOTENT_-2013_ABSORBED_EXC"
        assert result.is_idempotent_success is True
        assert result.error_code == -2013
        assert cancel_mock.call_count == 1
        helper._backoff_wait.assert_not_called()
