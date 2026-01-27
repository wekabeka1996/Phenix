"""
Binance Adapter Hardening Tests

P0: Verify specific error handling for leverage/margin operations.

Error Codes Tested:
- -4161: LeverageReductionError (ISOLATED + reduce leverage with position)
- -2027: MaxLeverageExceededError (notional exceeds bracket)
- -4047: MarginChangeError (open orders exist)
- -4048: MarginChangeError (position exists)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Mock httpx before importing BinanceAdapter
import sys
mock_httpx = MagicMock()
mock_httpx.AsyncClient = MagicMock
sys.modules['httpx'] = mock_httpx

from apps.reference.adapters.binance_adapter import (
    BinanceAdapter,
    BinanceAPIError,
    LeverageReductionError,
    MaxLeverageExceededError,
    MarginChangeError,
)


@pytest.fixture
def mock_adapter() -> BinanceAdapter:
    """Create adapter with mocked config and httpx."""
    with patch.object(BinanceAdapter, '__init__', lambda self, *args, **kwargs: None):
        adapter = BinanceAdapter.__new__(BinanceAdapter)
        adapter.api_key = "test_key"
        adapter.api_secret = b"test_secret"
        adapter.base_url = "https://testnet.binancefuture.com"
        adapter.config = {}
        adapter._timeout = 10.0
        adapter.logger = MagicMock()
        adapter._time_offset_ms = 0
        adapter._recv_window_ms = 20000
        adapter.session = MagicMock()
        return adapter


class TestSetLeverageHardening:
    """Test set_leverage error handling."""

    @pytest.mark.asyncio
    async def test_leverage_reduction_error_4161(self, mock_adapter: BinanceAdapter):
        """
        -4161: Leverage reduction is not supported in Isolated Margin Mode
        with open positions.
        """
        mock_adapter._request = AsyncMock(
            side_effect=BinanceAPIError(
                code=-4161,
                msg="Leverage reduction is not supported in Isolated Margin Mode with open positions",
            )
        )

        with pytest.raises(LeverageReductionError) as exc_info:
            await mock_adapter.set_leverage("BTCUSDT", 10)

        assert exc_info.value.code == -4161
        assert "reduction" in exc_info.value.msg.lower() or "ISOLATED" in exc_info.value.msg

    @pytest.mark.asyncio
    async def test_max_leverage_exceeded_error_2027(self, mock_adapter: BinanceAdapter):
        """
        -2027: Exceeded the maximum allowable position at current leverage.
        (notional > bracket cap)
        """
        mock_adapter._request = AsyncMock(
            side_effect=BinanceAPIError(
                code=-2027,
                msg="Exceeded the maximum allowable position at current leverage",
            )
        )

        with pytest.raises(MaxLeverageExceededError) as exc_info:
            await mock_adapter.set_leverage("BTCUSDT", 125)

        assert exc_info.value.code == -2027

    @pytest.mark.asyncio
    async def test_set_leverage_success(self, mock_adapter: BinanceAdapter):
        """Normal success case."""
        mock_adapter._request = AsyncMock(
            return_value={"leverage": 50, "maxNotionalValue": "1000000", "symbol": "BTCUSDT"}
        )

        result = await mock_adapter.set_leverage("BTCUSDT", 50)
        assert result is True

    @pytest.mark.asyncio
    async def test_set_leverage_other_error_reraises(self, mock_adapter: BinanceAdapter):
        """Unknown errors should reraise as BinanceAPIError."""
        mock_adapter._request = AsyncMock(
            side_effect=BinanceAPIError(code=-9999, msg="Unknown error")
        )

        with pytest.raises(BinanceAPIError) as exc_info:
            await mock_adapter.set_leverage("BTCUSDT", 50)

        assert exc_info.value.code == -9999
        # Should NOT be a subclass error
        assert type(exc_info.value) is BinanceAPIError


class TestSetMarginModeHardening:
    """Test set_margin_mode error handling."""

    @pytest.mark.asyncio
    async def test_margin_change_error_open_orders_4047(self, mock_adapter: BinanceAdapter):
        """
        -4047: Margin type cannot be changed if there exists open orders.
        """
        mock_adapter._request = AsyncMock(
            side_effect=BinanceAPIError(
                code=-4047,
                msg="Margin type cannot be changed if there exists open orders",
            )
        )

        with pytest.raises(MarginChangeError) as exc_info:
            await mock_adapter.set_margin_mode("BTCUSDT", "isolated")

        assert exc_info.value.code == -4047
        assert "orders" in exc_info.value.msg.lower()

    @pytest.mark.asyncio
    async def test_margin_change_error_position_exists_4048(self, mock_adapter: BinanceAdapter):
        """
        -4048: Margin type cannot be changed if there exists position.
        """
        mock_adapter._request = AsyncMock(
            side_effect=BinanceAPIError(
                code=-4048,
                msg="Margin type cannot be changed if there exists position",
            )
        )

        with pytest.raises(MarginChangeError) as exc_info:
            await mock_adapter.set_margin_mode("BTCUSDT", "cross")

        assert exc_info.value.code == -4048
        assert "position" in exc_info.value.msg.lower()

    @pytest.mark.asyncio
    async def test_margin_mode_idempotent_4046(self, mock_adapter: BinanceAdapter):
        """
        -4046: No need to change margin type (already set).
        Should return True (idempotent success).
        """
        mock_adapter._request = AsyncMock(
            side_effect=BinanceAPIError(
                code=-4046,
                msg="No need to change margin type",
            )
        )

        result = await mock_adapter.set_margin_mode("BTCUSDT", "isolated")
        assert result is True

    @pytest.mark.asyncio
    async def test_margin_mode_success(self, mock_adapter: BinanceAdapter):
        """Normal success case."""
        mock_adapter._request = AsyncMock(return_value={"code": 200, "msg": "success"})

        result = await mock_adapter.set_margin_mode("BTCUSDT", "isolated")
        assert result is True

    @pytest.mark.asyncio
    async def test_margin_mode_other_error_reraises(self, mock_adapter: BinanceAdapter):
        """Unknown errors should reraise as BinanceAPIError."""
        mock_adapter._request = AsyncMock(
            side_effect=BinanceAPIError(code=-9999, msg="Unknown error")
        )

        with pytest.raises(BinanceAPIError) as exc_info:
            await mock_adapter.set_margin_mode("BTCUSDT", "isolated")

        assert exc_info.value.code == -9999
        # Should NOT be a MarginChangeError
        assert type(exc_info.value) is BinanceAPIError


class TestExceptionHierarchy:
    """Verify exception class hierarchy."""

    def test_leverage_reduction_error_is_binance_api_error(self):
        """LeverageReductionError should inherit from BinanceAPIError."""
        err = LeverageReductionError(code=-4161, msg="test")
        assert isinstance(err, BinanceAPIError)

    def test_max_leverage_exceeded_error_is_binance_api_error(self):
        """MaxLeverageExceededError should inherit from BinanceAPIError."""
        err = MaxLeverageExceededError(code=-2027, msg="test")
        assert isinstance(err, BinanceAPIError)

    def test_margin_change_error_is_binance_api_error(self):
        """MarginChangeError should inherit from BinanceAPIError."""
        err = MarginChangeError(code=-4048, msg="test")
        assert isinstance(err, BinanceAPIError)
