"""Unit tests for PriceService."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from vfoundation.services.price_service import (
    PriceService,
    PriceQuote,
    FallbackExhaustedError,
)


@pytest.fixture
def mock_adapter():
    adapter = MagicMock()
    adapter.get_mark_price = AsyncMock(return_value=100.5)
    adapter.get_last_price = AsyncMock(return_value=100.3)
    return adapter


@pytest.fixture
def price_service(mock_adapter):
    return PriceService(mock_adapter, max_cache_size=10)


@pytest.mark.asyncio
async def test_get_mark_cache_miss(price_service, mock_adapter):
    quote = await price_service.get_mark("BTCUSDT", ttl_ms=250)
    assert quote.symbol == "BTCUSDT"
    assert quote.mark == 100.5
    assert quote.source == "MARK"
    mock_adapter.get_mark_price.assert_called_once_with("BTCUSDT")


@pytest.mark.asyncio
async def test_get_mark_cache_hit(price_service, mock_adapter):
    await price_service.get_mark("BTCUSDT", ttl_ms=1000)
    mock_adapter.get_mark_price.reset_mock()
    quote = await price_service.get_mark("BTCUSDT", ttl_ms=1000)
    assert quote.mark == 100.5
    mock_adapter.get_mark_price.assert_not_called()


@pytest.mark.asyncio
async def test_cache_expiration(price_service, mock_adapter):
    await price_service.get_mark("BTCUSDT", ttl_ms=10)
    await asyncio.sleep(0.02)
    mock_adapter.get_mark_price.reset_mock()
    await price_service.get_mark("BTCUSDT", ttl_ms=10)
    mock_adapter.get_mark_price.assert_called_once()


@pytest.mark.asyncio
async def test_force_refresh(price_service, mock_adapter):
    await price_service.get_mark("BTCUSDT", ttl_ms=1000)
    mock_adapter.get_mark_price.reset_mock()
    await price_service.get_mark("BTCUSDT", ttl_ms=0)
    mock_adapter.get_mark_price.assert_called_once()


@pytest.mark.asyncio
async def test_get_current_fallback_chain(price_service, mock_adapter):
    mock_adapter.get_mark_price = AsyncMock(return_value=None)
    mock_adapter.get_last_price = AsyncMock(return_value=100.3)
    quote = await price_service.get_current("BTCUSDT", working_type="MARK")
    assert quote.source == "LAST"
    assert quote.last == 100.3


@pytest.mark.asyncio
async def test_fallback_exhausted(price_service, mock_adapter):
    mock_adapter.get_mark_price = AsyncMock(return_value=None)
    mock_adapter.get_last_price = AsyncMock(return_value=None)
    with pytest.raises(FallbackExhaustedError):
        await price_service.get_current("BTCUSDT")


@pytest.mark.asyncio
async def test_concurrent_access(price_service, mock_adapter):
    tasks = [price_service.get_mark("BTCUSDT", ttl_ms=1000) for _ in range(10)]
    results = await asyncio.gather(*tasks)
    assert all(r.mark == 100.5 for r in results)
    assert mock_adapter.get_mark_price.call_count == 1


@pytest.mark.asyncio
async def test_lru_eviction(price_service, mock_adapter):
    for i in range(12):
        await price_service.get_mark(f"SYM{i}", ttl_ms=10000)
    assert len(price_service._cache) == 10


@pytest.mark.asyncio
async def test_stale_while_revalidate(price_service, mock_adapter):
    await price_service.get_mark("BTCUSDT", ttl_ms=10)
    await asyncio.sleep(0.02)
    mock_adapter.get_mark_price = AsyncMock(
        side_effect=Exception("Network error"))
    quote = await price_service.get_mark("BTCUSDT", ttl_ms=10)
    assert quote.mark == 100.5
