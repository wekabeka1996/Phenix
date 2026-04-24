"""
TASK47c-B: fsm_open Integration Test for LeverageService.

Tests that the leverage verification flow is correctly triggered
before DEC:OPEN emission.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import time


class TestFsmOpenLeverageIntegration:
    """Tests for leverage verification integration with fsm_open."""
    
    @pytest.mark.asyncio
    async def test_leverage_verify_before_dec_open(self):
        """
        Integration test: LeverageService.verify() should be called before DEC:OPEN.
        
        This test verifies the integration pattern where leverage verification
        happens BEFORE the order is sent to the exchange.
        """
        from apps.reference.domains.execution_position.leverage_service import LeverageService, VerifyResult
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        
        # Mock adapter with successful leverage/margin settings
        adapter = AsyncMock()
        adapter.get_current_leverage = AsyncMock(return_value=20)
        adapter.get_margin_mode = AsyncMock(return_value="isolated")
        
        service = LeverageService(adapter=adapter, clock=time.time)
        
        # Simulate pre-DEC:OPEN verification
        result = await service.verify(
            symbol="BTCUSDT",
            expected_leverage=20,
            expected_margin_mode="isolated"
        )
        
        # Should pass — ready to emit DEC:OPEN
        assert result.ok is True
        assert result.error_code is None
        
    @pytest.mark.asyncio
    async def test_leverage_mismatch_blocks_dec_open(self):
        """
        Integration test: Leverage mismatch should block DEC:OPEN emission.
        """
        from apps.reference.domains.execution_position.leverage_service import LeverageService, VerifyResult
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        
        # Mock adapter with MISMATCHED leverage
        adapter = AsyncMock()
        adapter.get_current_leverage = AsyncMock(return_value=10)  # Expected: 20
        adapter.get_margin_mode = AsyncMock(return_value="isolated")
        
        service = LeverageService(adapter=adapter, clock=time.time)
        
        # Simulate pre-DEC:OPEN verification
        result = await service.verify(
            symbol="BTCUSDT",
            expected_leverage=20,
            expected_margin_mode="isolated"
        )
        
        # Should FAIL — block DEC:OPEN
        assert result.ok is False
        assert result.error_code == NormalizedRejectReasons.LEVERAGE_MISMATCH
        
    @pytest.mark.asyncio
    async def test_set_and_verify_fixes_mismatch(self):
        """
        Integration test: set_and_verify should fix mismatch and allow DEC:OPEN.
        """
        from apps.reference.domains.execution_position.leverage_service import LeverageService
        
        # Mock adapter that starts with wrong settings, then corrects them
        adapter = AsyncMock()
        adapter.set_margin_mode = AsyncMock(return_value=True)
        adapter.set_leverage = AsyncMock(return_value=True)
        # After set, return correct values
        adapter.get_current_leverage = AsyncMock(return_value=20)
        adapter.get_margin_mode = AsyncMock(return_value="isolated")
        
        service = LeverageService(adapter=adapter, clock=time.time)
        
        # Use set_and_verify to fix settings
        result = await service.set_and_verify(
            symbol="BTCUSDT",
            expected_leverage=20,
            expected_margin_mode="isolated"
        )
        
        # Should PASS after setting
        assert result.ok is True
        adapter.set_margin_mode.assert_called_once_with("BTCUSDT", "isolated")
        adapter.set_leverage.assert_called_once_with("BTCUSDT", 20)
