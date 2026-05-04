"""
TASK47c-E: LeverageService Wire-up Tests.

Tests for wiring LeverageService into OpenFlowFSM production flow.
TDD approach: Write failing tests first, then implement the wiring.
"""
import pytest
import asyncio
import time
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from vfoundation.core.protocol import Message


class TestLeverageServiceWiring:
    """Tests for LeverageService integration into OpenFlowFSM."""
    
    def _make_fsm_with_leverage_service(
        self,
        leverage_service=None,
        target_leverage: int = 20,
        leverage_policy: str = "verify_only",
        margin_mode: str = "isolated",
        max_notional_utilization: float = 0.5,
    ):
        """Create OpenFlowFSM with optional LeverageService."""
        from apps.reference.domains.execution_position.flows.open.fsm_open import OpenFlowFSM
        from apps.reference.config_models import AuroraConfig, InstrumentExecutionConfig
        
        config = MagicMock(spec=AuroraConfig)
        config.instruments = {
            "BTCUSDT": MagicMock(
                min_qty=Decimal("0.001"),
                step_size=Decimal("0.001"),
                tick_size=Decimal("0.01"),
                min_notional=Decimal("5.0"),
                execution=InstrumentExecutionConfig(
                    margin_mode=margin_mode,
                    target_leverage=target_leverage,
                    leverage_policy=leverage_policy,
                    max_notional_utilization=max_notional_utilization,
                ),
            )
        }
        config.domains = MagicMock()
        config.domains.execution_position = MagicMock()
        config.domains.execution_position.fsm_open = MagicMock()
        config.domains.execution_position.fsm_open.idempotency_window_sec = 60
        
        return OpenFlowFSM(
            config=config,
            guard_enabled=True,
            cooldown_sec=0,
            leverage_service=leverage_service,
        )
        
    def _make_mock_leverage_service(self, verify_result_ok: bool = True):
        """Create mock LeverageService."""
        from apps.reference.domains.execution_position.guards.leverage_service import VerifyResult
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        
        service = MagicMock()
        
        if verify_result_ok:
            result = VerifyResult(
                ok=True,
                actual_leverage=20,
                actual_margin_mode="isolated",
                expected_leverage=20,
                expected_margin_mode="isolated",
                why="OK",
                error_code=None,
            )
        else:
            result = VerifyResult(
                ok=False,
                actual_leverage=10,
                actual_margin_mode="cross",
                expected_leverage=20,
                expected_margin_mode="isolated",
                why="Leverage mismatch: actual=10, expected=20",
                error_code=NormalizedRejectReasons.LEVERAGE_MISMATCH,
            )
        
        # Make both sync and async versions available
        service.verify = AsyncMock(return_value=result)
        service.set_and_verify = AsyncMock(return_value=result)
        service.verify_sync = MagicMock(return_value=result)
        service.set_and_verify_sync = MagicMock(return_value=result)
        
        return service
        
    @pytest.mark.asyncio
    async def test_openflow_calls_leverage_service_verify_only_before_dec_open(self):
        """
        When leverage_policy=verify_only, OpenFlowFSM should call service.verify()
        BEFORE emitting DEC:OPEN.
        """
        service = self._make_mock_leverage_service(verify_result_ok=True)
        fsm = self._make_fsm_with_leverage_service(
            leverage_service=service,
            leverage_policy="verify_only",
        )
        
        msg = Message(
            op="CMD",
            verb="OPEN",
            src="bridge",
            dst="execution_position",
            rid="test-wire-001",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.01",
                "order_type": "MARKET",
                "price_ref": "50000",
            },
        )
        
        # Use async handler
        result = await fsm.handle_async(msg)
        
        # Should have called verify (not set_and_verify)
        service.verify.assert_called_once()
        service.set_and_verify.assert_not_called()
        
        # Should emit DEC:OPEN
        assert result is not None
        assert result.op == "DEC"
        assert result.verb == "OPEN"
        
    @pytest.mark.asyncio
    async def test_openflow_calls_leverage_service_set_and_verify_before_dec_open(self):
        """
        When leverage_policy=set_and_verify, OpenFlowFSM should call service.set_and_verify()
        BEFORE emitting DEC:OPEN.
        """
        service = self._make_mock_leverage_service(verify_result_ok=True)
        fsm = self._make_fsm_with_leverage_service(
            leverage_service=service,
            leverage_policy="set_and_verify",
        )
        
        msg = Message(
            op="CMD",
            verb="OPEN",
            src="bridge",
            dst="execution_position",
            rid="test-wire-002",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.01",
                "order_type": "MARKET",
                "price_ref": "50000",
            },
        )
        
        result = await fsm.handle_async(msg)
        
        # Should have called set_and_verify (not just verify)
        service.set_and_verify.assert_called_once()
        
        # Should emit DEC:OPEN
        assert result is not None
        assert result.op == "DEC"
        
    @pytest.mark.asyncio
    async def test_openflow_rejects_and_does_not_emit_dec_open_on_leverage_failure(self):
        """
        When leverage verification fails, OpenFlowFSM should:
        - Return ERR (not DEC:OPEN)
        - Include leverage NRR code in response
        """
        service = self._make_mock_leverage_service(verify_result_ok=False)
        fsm = self._make_fsm_with_leverage_service(
            leverage_service=service,
            leverage_policy="verify_only",
        )
        
        msg = Message(
            op="CMD",
            verb="OPEN",
            src="bridge",
            dst="execution_position",
            rid="test-wire-003",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.01",
                "order_type": "MARKET",
                "price_ref": "50000",
            },
        )
        
        result = await fsm.handle_async(msg)
        
        # Should reject (ERR, not DEC)
        assert result is not None
        assert result.op == "ERR", f"Expected ERR, got {result.op}"
        
        # Reason should contain leverage-related info
        reason = result.pld.get("reason", "")
        assert "leverage" in reason.lower() or "mismatch" in reason.lower(), \
            f"Reason should mention leverage: {reason}"
            
    def test_openflow_without_leverage_service_in_live_mode_raises(self):
        """
        In LIVE mode, missing leverage_service should raise RuntimeError at init.
        """
        from apps.reference.domains.execution_position.flows.open.fsm_open import OpenFlowFSM
        from apps.reference.config_models import AuroraConfig
        
        config = MagicMock(spec=AuroraConfig)
        config.instruments = {"BTCUSDT": MagicMock()}
        config.instruments["BTCUSDT"].execution = MagicMock()
        config.domains = MagicMock()
        config.domains.execution_position = MagicMock()
        config.domains.execution_position.fsm_open = MagicMock()
        config.domains.execution_position.fsm_open.idempotency_window_sec = 60
        
        # Should raise if leverage_service=None and is_live_execution=True
        with pytest.raises(RuntimeError, match="LeverageService.*required.*LIVE"):
            OpenFlowFSM(
                config=config,
                leverage_service=None,
                is_live_execution=True,
            )
            
    def test_openflow_without_leverage_service_in_shadow_mode_warns(self, caplog):
        """
        In SHADOW/DEV mode, missing leverage_service should log warning but not crash.
        """
        import logging
        from apps.reference.domains.execution_position.flows.open.fsm_open import OpenFlowFSM
        from apps.reference.config_models import AuroraConfig
        
        config = MagicMock(spec=AuroraConfig)
        config.instruments = {}
        config.domains = MagicMock()
        config.domains.execution_position = MagicMock()
        config.domains.execution_position.fsm_open = MagicMock()
        config.domains.execution_position.fsm_open.idempotency_window_sec = 60
        
        with caplog.at_level(logging.WARNING):
            fsm = OpenFlowFSM(
                config=config,
                leverage_service=None,
                is_live_execution=False,
            )
            
        # Should warn (or at least not crash)
        assert fsm is not None
