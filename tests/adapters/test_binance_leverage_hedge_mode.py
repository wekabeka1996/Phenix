"""
TASK47c-B-FIX: Hedge Mode / Margin Type Tests.

Tests for fail-closed behavior on Hedge mode inconsistencies
and stable marginType mapping.
"""
import pytest
from unittest.mock import AsyncMock, patch

pytest.importorskip("httpx")


class TestAdapterHedgeModeFailClosed:
    """Tests for Hedge mode determinism in binance_adapter."""
    
    @pytest.mark.asyncio
    async def test_get_leverage_one_way_mode_success(self):
        """One-way mode (BOTH) with single entry should succeed."""
        from apps.reference.adapters.binance_adapter import BinanceAdapter
        
        adapter = BinanceAdapter(api_key="test", api_secret="test")
        
        # Mock single BOTH entry
        mock_response = [
            {"symbol": "BTCUSDT", "positionSide": "BOTH", "leverage": "20", "marginType": "isolated"}
        ]
        adapter._request = AsyncMock(return_value=mock_response)
        
        leverage = await adapter.get_current_leverage("BTCUSDT")
        assert leverage == 20
        
    @pytest.mark.asyncio
    async def test_get_leverage_hedge_mode_consistent_success(self):
        """Hedge mode with consistent leverage across LONG/SHORT should succeed."""
        from apps.reference.adapters.binance_adapter import BinanceAdapter
        
        adapter = BinanceAdapter(api_key="test", api_secret="test")
        
        # Mock Hedge mode with consistent leverage
        mock_response = [
            {"symbol": "BTCUSDT", "positionSide": "LONG", "leverage": "20", "marginType": "cross"},
            {"symbol": "BTCUSDT", "positionSide": "SHORT", "leverage": "20", "marginType": "cross"},
        ]
        adapter._request = AsyncMock(return_value=mock_response)
        
        leverage = await adapter.get_current_leverage("BTCUSDT")
        assert leverage == 20
        
    @pytest.mark.asyncio
    async def test_get_leverage_hedge_mode_inconsistent_fails(self):
        """Hedge mode with INCONSISTENT leverage should fail-closed (NRR-024)."""
        from apps.reference.adapters.binance_adapter import BinanceAdapter, BinanceAPIError
        
        adapter = BinanceAdapter(api_key="test", api_secret="test")
        
        # Mock Hedge mode with DIFFERENT leverage on each side
        mock_response = [
            {"symbol": "BTCUSDT", "positionSide": "LONG", "leverage": "20", "marginType": "cross"},
            {"symbol": "BTCUSDT", "positionSide": "SHORT", "leverage": "10", "marginType": "cross"},
        ]
        adapter._request = AsyncMock(return_value=mock_response)
        
        with pytest.raises(BinanceAPIError) as exc:
            await adapter.get_current_leverage("BTCUSDT")
        
        assert "Inconsistent leverage" in str(exc.value)
        assert exc.value.nrr_code == "NRR-024"
        
    @pytest.mark.asyncio
    async def test_get_margin_mode_hedge_mode_inconsistent_fails(self):
        """Hedge mode with INCONSISTENT margin mode should fail-closed (NRR-024)."""
        from apps.reference.adapters.binance_adapter import BinanceAdapter, BinanceAPIError
        
        adapter = BinanceAdapter(api_key="test", api_secret="test")
        
        # Mock Hedge mode with DIFFERENT margin mode on each side (edge case)
        mock_response = [
            {"symbol": "BTCUSDT", "positionSide": "LONG", "leverage": "20", "marginType": "ISOLATED"},
            {"symbol": "BTCUSDT", "positionSide": "SHORT", "leverage": "20", "marginType": "CROSSED"},
        ]
        adapter._request = AsyncMock(return_value=mock_response)
        
        with pytest.raises(BinanceAPIError) as exc:
            await adapter.get_margin_mode("BTCUSDT")
        
        assert "Inconsistent margin mode" in str(exc.value)
        assert exc.value.nrr_code == "NRR-024"


class TestAdapterMarginTypeMapping:
    """Tests for stable marginType normalization."""
    
    @pytest.mark.asyncio
    async def test_margin_type_cross_lowercase(self):
        """marginType: 'cross' should return 'cross'."""
        from apps.reference.adapters.binance_adapter import BinanceAdapter
        
        adapter = BinanceAdapter(api_key="test", api_secret="test")
        mock_response = [
            {"symbol": "BTCUSDT", "positionSide": "BOTH", "leverage": "20", "marginType": "cross"}
        ]
        adapter._request = AsyncMock(return_value=mock_response)
        
        mode = await adapter.get_margin_mode("BTCUSDT")
        assert mode == "cross"
        
    @pytest.mark.asyncio
    async def test_margin_type_crossed_uppercase(self):
        """marginType: 'CROSSED' should return 'cross'."""
        from apps.reference.adapters.binance_adapter import BinanceAdapter
        
        adapter = BinanceAdapter(api_key="test", api_secret="test")
        mock_response = [
            {"symbol": "BTCUSDT", "positionSide": "BOTH", "leverage": "20", "marginType": "CROSSED"}
        ]
        adapter._request = AsyncMock(return_value=mock_response)
        
        mode = await adapter.get_margin_mode("BTCUSDT")
        assert mode == "cross"
        
    @pytest.mark.asyncio
    async def test_margin_type_isolated_uppercase(self):
        """marginType: 'ISOLATED' should return 'isolated'."""
        from apps.reference.adapters.binance_adapter import BinanceAdapter
        
        adapter = BinanceAdapter(api_key="test", api_secret="test")
        mock_response = [
            {"symbol": "BTCUSDT", "positionSide": "BOTH", "leverage": "20", "marginType": "ISOLATED"}
        ]
        adapter._request = AsyncMock(return_value=mock_response)
        
        mode = await adapter.get_margin_mode("BTCUSDT")
        assert mode == "isolated"
        
    @pytest.mark.asyncio
    async def test_margin_type_isolated_boolean_true(self):
        """isolated: true (boolean) should return 'isolated' as fallback."""
        from apps.reference.adapters.binance_adapter import BinanceAdapter
        
        adapter = BinanceAdapter(api_key="test", api_secret="test")
        # Empty marginType but isolated=true
        mock_response = [
            {"symbol": "BTCUSDT", "positionSide": "BOTH", "leverage": "20", "marginType": "", "isolated": True}
        ]
        adapter._request = AsyncMock(return_value=mock_response)
        
        mode = await adapter.get_margin_mode("BTCUSDT")
        assert mode == "isolated"
        
    @pytest.mark.asyncio
    async def test_margin_type_isolated_boolean_false(self):
        """isolated: false (boolean) should return 'cross' as fallback."""
        from apps.reference.adapters.binance_adapter import BinanceAdapter
        
        adapter = BinanceAdapter(api_key="test", api_secret="test")
        # Empty marginType but isolated=false
        mock_response = [
            {"symbol": "BTCUSDT", "positionSide": "BOTH", "leverage": "20", "marginType": "", "isolated": False}
        ]
        adapter._request = AsyncMock(return_value=mock_response)
        
        mode = await adapter.get_margin_mode("BTCUSDT")
        assert mode == "cross"
        
    @pytest.mark.asyncio
    async def test_margin_type_unknown_fails_closed(self):
        """Unknown marginType with no fallback should fail-closed."""
        from apps.reference.adapters.binance_adapter import BinanceAdapter, BinanceAPIError
        
        adapter = BinanceAdapter(api_key="test", api_secret="test")
        # Unknown marginType and no isolated field
        mock_response = [
            {"symbol": "BTCUSDT", "positionSide": "BOTH", "leverage": "20", "marginType": "UNKNOWN_MODE"}
        ]
        adapter._request = AsyncMock(return_value=mock_response)
        
        with pytest.raises(BinanceAPIError) as exc:
            await adapter.get_margin_mode("BTCUSDT")
        
        assert "Unknown marginType" in str(exc.value)
        assert exc.value.nrr_code == "NRR-024"
