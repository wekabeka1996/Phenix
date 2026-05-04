"""
P0 Guard Tests: Fail-Closed Config Validation

These tests verify that critical FSM classes reject None config
and ExposureGuard rejects missing leverage defaults + invalid sides.

TDD: These tests should FAIL before implementation and PASS after.
"""
import pytest
from unittest.mock import MagicMock
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.flows.open.fsm_open import OpenFlowFSM
from apps.reference.domains.execution_position.flows.manage.fsm_manage import ManageFlowFSM
from apps.reference.domains.execution_position.guards.exposure_guard import ExposureGuard
from apps.reference.config_contract import ConfigContractError


class TestFailClosedConfig:
    """P0: Verify fail-closed config validation logic."""

    def test_execpos_fsm_rejects_none_config(self):
        """ExecPosFSM must crash if config is None."""
        with pytest.raises(ValueError, match="requires valid AuroraConfig"):
            ExecPosFSM(config=None, fsm=MagicMock())

    def test_openflow_rejects_none_config(self):
        """OpenFlowFSM must crash if config is None."""
        with pytest.raises(ValueError, match="requires valid AuroraConfig"):
            OpenFlowFSM(config=None)

    def test_manageflow_rejects_none_config(self):
        """ManageFlowFSM must crash if config is None."""
        with pytest.raises(ValueError, match="requires valid AuroraConfig"):
            ManageFlowFSM(config=None)

    def test_exposure_guard_rejects_missing_default_leverage(self):
        """ExposureGuard must crash if __default__ leverage is missing."""
        # Mock config with missing leverage defaults
        mock_config = MagicMock()
        
        # Setup ExposureGuard domain config (required for __init__)
        eg_config = MagicMock()
        eg_config.max_equity_utilization_pct = 100
        eg_config.max_portfolio_fraction = 1.0
        eg_config.max_long_utilization_pct = 100
        eg_config.max_short_utilization_pct = 100
        eg_config.max_concentration_pct = 50
        eg_config.max_directional_ratio = 5.0
        eg_config.pending_ttl_sec = 60
        eg_config.post_fill_ttl_sec = 30
        eg_config.stale_ttl_sec = 300
        mock_config.domains.execution_position.exposure_guard = eg_config
        
        # P1: Add fallback config (required after P1 config extraction)
        mock_fallback = MagicMock()
        mock_fallback.policy = "fail_closed"
        mock_fallback.risk_reduction_pct = "0.5"
        mock_fallback.backoff_ms = [200, 500, 1000]
        mock_config.domains.execution_position.fallback = mock_fallback
        
        # Setup exposure config with EMPTY leverage_defaults (missing __default__)
        mock_config.trading.execution.exposure.leverage_defaults = {}
        mock_config.trading.execution.exposure.count_pending_orders = True
        mock_config.trading.execution.exposure.exclude_reduce_only = False
        
        # Setup trading.risk with complete soft_limits (required by soft_clip loader)
        mock_config.trading.risk = {
            "soft_limits": {
                "mode": "clip",
                "clip_min_notional_usdt": 5,
                "directional_ratio_max": 3.0,
                "side_exposure_usdt": 10000,
                "margin_exposure_usdt": 5000,
            }
        }
        
        # instruments fallback also failing
        mock_config.instruments = {}
        
        guard = ExposureGuard(fsm_core=MagicMock(), config=mock_config)
        
        with pytest.raises(ConfigContractError, match=r"Symbol BTCUSDT not found|Default leverage is mandatory"):
            guard.resolve_symbol_leverage("BTCUSDT")

    def test_exposure_guard_rejects_invalid_side(self):
        """ExposureGuard must crash on invalid side (typo protection)."""
        mock_config = MagicMock()
        
        # Setup ExposureGuard domain config (required for __init__)
        eg_config = MagicMock()
        eg_config.max_equity_utilization_pct = 100
        eg_config.max_portfolio_fraction = 1.0
        eg_config.max_long_utilization_pct = 100
        eg_config.max_short_utilization_pct = 100
        eg_config.max_concentration_pct = 50
        eg_config.max_directional_ratio = 5.0
        eg_config.pending_ttl_sec = 60
        eg_config.post_fill_ttl_sec = 30
        eg_config.stale_ttl_sec = 300
        mock_config.domains.execution_position.exposure_guard = eg_config
        
        # P1: Add fallback config (required after P1 config extraction)
        mock_fallback = MagicMock()
        mock_fallback.policy = "fail_closed"
        mock_fallback.risk_reduction_pct = "0.5"
        mock_fallback.backoff_ms = [200, 500, 1000]
        mock_config.domains.execution_position.fallback = mock_fallback
        
        # Setup valid leverage so resolve_symbol_leverage passes
        mock_config.trading.execution.exposure.leverage_defaults = {"__default__": 20}
        mock_config.trading.execution.exposure.count_pending_orders = True
        mock_config.trading.execution.exposure.exclude_reduce_only = False
        
        # Setup trading.risk with complete soft_limits (required by soft_clip loader)
        mock_config.trading.risk = {
            "soft_limits": {
                "mode": "clip",
                "clip_min_notional_usdt": 5,
                "directional_ratio_max": 3.0,
                "side_exposure_usdt": 10000,
                "margin_exposure_usdt": 5000,
            }
        }
        
        # instruments
        mock_config.instruments = {}
        
        guard = ExposureGuard(fsm_core=MagicMock(), config=mock_config)
        
        # Inject state to allow checks to proceed to side validation
        guard.state.reservations = {}
        guard.state.pending_exposure = {}
        
        # Calling reserve with invalid side "SELLL"
        with pytest.raises(ValueError, match="Invalid order side"):
            guard.reserve("test_key", 100, symbol="BTCUSDT", side="SELLL")
