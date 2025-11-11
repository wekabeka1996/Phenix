"""
Test for BinanceExecutionAdapter get_open_positions and get_open_orders methods.
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter


class TestBinanceExecutionAdapter:
    """Test BinanceExecutionAdapter methods."""

    @pytest.fixture
    def adapter(self):
        """Create test adapter instance."""
        config = {"trading_env": "test"}
        adapter = BinanceExecutionAdapter(
            fsm=None, config=config, shadow_mode=True)
        return adapter

    @pytest.mark.asyncio
    async def test_get_open_positions_shadow_mode(self, adapter):
        """Test get_open_positions in shadow mode."""
        result = await adapter.get_open_positions()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_open_orders_shadow_mode(self, adapter):
        """Test get_open_orders in shadow mode."""
        result = await adapter.get_open_orders()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_open_positions_with_symbol_filter(self, adapter):
        """Test get_open_positions with symbol filter."""
        # Mock the httpx client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"symbol": "BTCUSDT", "positionAmt": "1.0"},
            {"symbol": "ETHUSDT", "positionAmt": "2.0"}
        ]

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

            # Override shadow mode for this test
            adapter.shadow_mode = False
            adapter.api_key = "test_key"
            adapter.api_secret = "test_secret"

            result = await adapter.get_open_positions(symbol="BTCUSDT")

            # Should filter to only BTCUSDT
            assert len(result) == 1
            assert result[0]["symbol"] == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_get_open_orders_with_symbol_filter(self, adapter):
        """Test get_open_orders with symbol filter."""
        # Mock the httpx client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"symbol": "BTCUSDT", "orderId": "1"},
            {"symbol": "ETHUSDT", "orderId": "2"}
        ]

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

            # Override shadow mode for this test
            adapter.shadow_mode = False
            adapter.api_key = "test_key"
            adapter.api_secret = "test_secret"

            result = await adapter.get_open_orders(symbol="BTCUSDT")

            # Should filter to only BTCUSDT
            assert len(result) == 1
            assert result[0]["symbol"] == "BTCUSDT"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
