"""
Test BUG-P1-002: Verify the new BinanceAdapter preserves Decimal precision on API responses.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
import aiohttp

from apps.reference.adapters.binance_adapter import BinanceAdapter

# Mock API response with high-precision numbers as strings
MOCK_API_RESPONSE = [
    {
        "symbol": "BTCUSDT",
        "positionAmt": "0.123456789012345678",
        "entryPrice": "50000.123456789012345678",
        "markPrice": "51000.987654321098765432",
        "unRealizedProfit": "123.45678901",
        "liquidationPrice": "40000.00000001",
    }
]


@pytest.mark.asyncio
async def test_decimal_precision_is_preserved_on_response():
    """
    Verify that the BinanceAdapter correctly parses high-precision numbers
    from a mocked API JSON response without losing precision.
    """
    # Mock aiohttp.ClientSession to return precise data
    with patch("httpx.AsyncClient") as mock_client_class:
        # Create mock session instance
        mock_session = AsyncMock()
        mock_client_class.return_value = mock_session

        # Create mock response
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value=MOCK_API_RESPONSE)
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        # Set up session.request to return the mock response
        mock_session.request = AsyncMock(return_value=mock_response)

        # Initialize the adapter
        adapter = BinanceAdapter(
            api_key="test_key",
            api_secret="test_secret",
            rest_url="https://testnet.binancefuture.com",
        )

        # Mock _sync_time to avoid time sync issues
        adapter._sync_time = AsyncMock()

        # Call the method that makes the API request (mocked)
        positions = await adapter.get_open_positions()

        # Assert that the precision is preserved in the parsed data
        assert len(positions) == 1
        position = positions[0]

        # The adapter should return the precise string from the JSON (as ExchangePosition object)
        # Note: ExchangePosition uses snake_case attributes
        assert position.position_amount == "0.123456789012345678"
        assert position.entry_price == "50000.123456789012345678"

        # Verify that converting it to Decimal in the test works as expected
        assert Decimal(position.position_amount) == Decimal(
            "0.123456789012345678")
        assert Decimal(position.entry_price) == Decimal(
            "50000.123456789012345678")
