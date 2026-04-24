"""
TASK47c-B: LeverageService TDD Tests.

Tests for leverage/margin verification with mock adapter.
TDD approach: Write failing tests first, then implement the service.
"""
import pytest
from dataclasses import dataclass
from typing import Optional
from unittest.mock import AsyncMock, MagicMock
import time


# Mocked data classes for testing (will match real implementation)
@dataclass
class VerifyResult:
    """Result of leverage/margin verification."""
    ok: bool
    actual_leverage: Optional[int]
    actual_margin_mode: Optional[str]  # "isolated" | "cross" | None
    expected_leverage: int
    expected_margin_mode: str  # "isolated" | "cross"
    why: str  # Max 80 chars
    error_code: Optional[str]  # NRR code or None


class TestLeverageServiceVerify:
    """Tests for LeverageService.verify() method."""
    
    @pytest.mark.asyncio
    async def test_verify_only_rejects_on_leverage_mismatch(self):
        """When actual leverage != expected, verify returns ok=False with LEV_MISMATCH."""
        from apps.reference.domains.execution_position.leverage_service import LeverageService
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        
        # Mock adapter returns mismatched leverage
        adapter = AsyncMock()
        adapter.get_current_leverage = AsyncMock(return_value=10)  # Expected: 20
        adapter.get_margin_mode = AsyncMock(return_value="isolated")
        
        service = LeverageService(adapter=adapter, clock=time.time)
        result = await service.verify("BTCUSDT", expected_leverage=20, expected_margin_mode="isolated")
        
        assert result.ok is False
        assert result.actual_leverage == 10
        assert result.expected_leverage == 20
        assert result.error_code == NormalizedRejectReasons.LEVERAGE_MISMATCH
        assert "mismatch" in result.why.lower() or "10" in result.why
        
    @pytest.mark.asyncio
    async def test_verify_only_rejects_on_margin_mode_mismatch(self):
        """When actual margin mode != expected, verify returns ok=False with MARGIN_MODE_MISMATCH."""
        from apps.reference.domains.execution_position.leverage_service import LeverageService
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        
        # Mock adapter returns mismatched margin mode
        adapter = AsyncMock()
        adapter.get_current_leverage = AsyncMock(return_value=20)
        adapter.get_margin_mode = AsyncMock(return_value="cross")  # Expected: isolated
        
        service = LeverageService(adapter=adapter, clock=time.time)
        result = await service.verify("BTCUSDT", expected_leverage=20, expected_margin_mode="isolated")
        
        assert result.ok is False
        assert result.actual_margin_mode == "cross"
        assert result.expected_margin_mode == "isolated"
        assert result.error_code == NormalizedRejectReasons.MARGIN_MODE_MISMATCH
        
    @pytest.mark.asyncio
    async def test_verify_returns_ok_when_all_match(self):
        """When leverage and margin mode match, verify returns ok=True."""
        from apps.reference.domains.execution_position.leverage_service import LeverageService
        
        adapter = AsyncMock()
        adapter.get_current_leverage = AsyncMock(return_value=20)
        adapter.get_margin_mode = AsyncMock(return_value="isolated")
        
        service = LeverageService(adapter=adapter, clock=time.time)
        result = await service.verify("BTCUSDT", expected_leverage=20, expected_margin_mode="isolated")
        
        assert result.ok is True
        assert result.error_code is None
        assert result.actual_leverage == 20
        assert result.actual_margin_mode == "isolated"


class TestLeverageServiceSetAndVerify:
    """Tests for LeverageService.set_and_verify() method."""
    
    @pytest.mark.asyncio
    async def test_set_and_verify_calls_setters_then_verifies_success(self):
        """set_and_verify should call set methods, then verify they took effect."""
        from apps.reference.domains.execution_position.leverage_service import LeverageService
        
        call_order = []

        async def _set_margin_mode(*args, **kwargs):
            call_order.append("set_margin_mode")
            return True

        async def _set_leverage(*args, **kwargs):
            call_order.append("set_leverage")
            return True

        async def _get_current_leverage(*args, **kwargs):
            call_order.append("get_current_leverage")
            return 20

        async def _get_margin_mode(*args, **kwargs):
            call_order.append("get_margin_mode")
            return "isolated"

        adapter = AsyncMock()
        adapter.set_margin_mode = AsyncMock(side_effect=_set_margin_mode)
        adapter.set_leverage = AsyncMock(side_effect=_set_leverage)
        adapter.get_current_leverage = AsyncMock(side_effect=_get_current_leverage)
        adapter.get_margin_mode = AsyncMock(side_effect=_get_margin_mode)
        
        service = LeverageService(adapter=adapter, clock=time.time)
        result = await service.set_and_verify("BTCUSDT", expected_leverage=20, expected_margin_mode="isolated")
        
        # Verify setters were called
        adapter.set_margin_mode.assert_called_once_with("BTCUSDT", "isolated")
        adapter.set_leverage.assert_called_once_with("BTCUSDT", 20)

        # Order must be: margin mode first (Binance requirement), then leverage, then verification.
        assert call_order[:2] == ["set_margin_mode", "set_leverage"]
        assert "get_current_leverage" in call_order
        assert "get_margin_mode" in call_order
        assert call_order.index("set_leverage") < call_order.index("get_current_leverage")
        
        # Result should be OK
        assert result.ok is True
        
    @pytest.mark.asyncio
    async def test_set_and_verify_rejects_when_set_leverage_fails(self):
        """When set_leverage fails, set_and_verify returns failure with LEV_SET_FAILED."""
        from apps.reference.domains.execution_position.leverage_service import LeverageService
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        
        adapter = AsyncMock()
        adapter.set_margin_mode = AsyncMock(return_value=True)
        adapter.set_leverage = AsyncMock(side_effect=Exception("API Error"))
        
        service = LeverageService(adapter=adapter, clock=time.time)
        result = await service.set_and_verify("BTCUSDT", expected_leverage=20, expected_margin_mode="isolated")
        
        assert result.ok is False
        assert result.error_code == NormalizedRejectReasons.LEVERAGE_SET_FAILED
        
    @pytest.mark.asyncio
    async def test_set_and_verify_rejects_when_set_margin_fails(self):
        """When set_margin_mode fails, set_and_verify returns failure."""
        from apps.reference.domains.execution_position.leverage_service import LeverageService
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        
        adapter = AsyncMock()
        adapter.set_margin_mode = AsyncMock(side_effect=Exception("API Error"))
        
        service = LeverageService(adapter=adapter, clock=time.time)
        result = await service.set_and_verify("BTCUSDT", expected_leverage=20, expected_margin_mode="isolated")
        
        assert result.ok is False
        assert result.error_code == NormalizedRejectReasons.MARGIN_MODE_SET_FAILED


class TestLeverageServiceIdempotency:
    """Tests for LeverageService idempotency window."""
    
    @pytest.mark.asyncio
    async def test_idempotency_window_skips_redundant_set_calls(self):
        """Within idempotency window, set_and_verify should not call setters again."""
        from apps.reference.domains.execution_position.leverage_service import LeverageService
        
        current_time = 1000.0
        clock = MagicMock(return_value=current_time)
        
        adapter = AsyncMock()
        adapter.set_margin_mode = AsyncMock(return_value=True)
        adapter.set_leverage = AsyncMock(return_value=True)
        adapter.get_current_leverage = AsyncMock(return_value=20)
        adapter.get_margin_mode = AsyncMock(return_value="isolated")
        
        service = LeverageService(adapter=adapter, clock=clock, idempotency_window_sec=60)
        
        # First call - should set
        await service.set_and_verify("BTCUSDT", expected_leverage=20, expected_margin_mode="isolated")
        assert adapter.set_leverage.call_count == 1
        assert adapter.set_margin_mode.call_count == 1
        
        # Reset mocks but keep state
        adapter.set_leverage.reset_mock()
        adapter.set_margin_mode.reset_mock()
        
        # Second call within window - should skip setters
        clock.return_value = current_time + 30  # 30 seconds later, still within window
        await service.set_and_verify("BTCUSDT", expected_leverage=20, expected_margin_mode="isolated")
        
        # Setters should NOT be called again (idempotent)
        adapter.set_leverage.assert_not_called()
        adapter.set_margin_mode.assert_not_called()
        
    @pytest.mark.asyncio
    async def test_idempotency_expires_after_window(self):
        """After idempotency window expires, set_and_verify should call setters again."""
        from apps.reference.domains.execution_position.leverage_service import LeverageService
        
        current_time = 1000.0
        clock = MagicMock(return_value=current_time)
        
        adapter = AsyncMock()
        adapter.set_margin_mode = AsyncMock(return_value=True)
        adapter.set_leverage = AsyncMock(return_value=True)
        adapter.get_current_leverage = AsyncMock(return_value=20)
        adapter.get_margin_mode = AsyncMock(return_value="isolated")
        
        service = LeverageService(adapter=adapter, clock=clock, idempotency_window_sec=60)
        
        # First call
        await service.set_and_verify("BTCUSDT", expected_leverage=20, expected_margin_mode="isolated")
        adapter.set_leverage.reset_mock()
        adapter.set_margin_mode.reset_mock()
        
        # Call after window expires
        clock.return_value = current_time + 120  # 2 minutes later, window expired
        await service.set_and_verify("BTCUSDT", expected_leverage=20, expected_margin_mode="isolated")
        
        # Setters SHOULD be called again
        adapter.set_leverage.assert_called_once()
        adapter.set_margin_mode.assert_called_once()


class TestLeverageServiceFailClosed:
    """Tests for fail-closed behavior on adapter errors."""
    
    @pytest.mark.asyncio
    async def test_fail_closed_on_adapter_get_leverage_error(self):
        """When get_current_leverage fails, verify returns failure with VERIFY_FAILED."""
        from apps.reference.domains.execution_position.leverage_service import LeverageService
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        
        adapter = AsyncMock()
        adapter.get_current_leverage = AsyncMock(side_effect=Exception("Network Error"))
        
        service = LeverageService(adapter=adapter, clock=time.time)
        result = await service.verify("BTCUSDT", expected_leverage=20, expected_margin_mode="isolated")
        
        assert result.ok is False
        assert result.error_code == NormalizedRejectReasons.LEVERAGE_VERIFY_FAILED
        assert "error" in result.why.lower() or "failed" in result.why.lower()
        
    @pytest.mark.asyncio
    async def test_fail_closed_on_adapter_get_margin_error(self):
        """When get_margin_mode fails, verify returns failure with VERIFY_FAILED."""
        from apps.reference.domains.execution_position.leverage_service import LeverageService
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        
        adapter = AsyncMock()
        adapter.get_current_leverage = AsyncMock(return_value=20)
        adapter.get_margin_mode = AsyncMock(side_effect=Exception("Network Error"))
        
        service = LeverageService(adapter=adapter, clock=time.time)
        result = await service.verify("BTCUSDT", expected_leverage=20, expected_margin_mode="isolated")
        
        assert result.ok is False
        assert result.error_code == NormalizedRejectReasons.LEVERAGE_VERIFY_FAILED
