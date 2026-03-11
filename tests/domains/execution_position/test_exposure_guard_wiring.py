import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal
from apps.reference.domains.execution_position.exposure_guard import ExposureGuard
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.soft_clip import (
    RegimeAdaptationConfig,
    SoftLimitConfigModel,
    SoftLimitConfig,
)
from apps.reference.core.types.regime_types import ExecutionRegimeBucket
from vfoundation.core.protocol import Message
from pydantic import ValidationError

class MockFSM:
    def __init__(self):
        self.listeners = {}
        self.order_index = MagicMock()
    def listen(self, evt, cb):
        self.listeners[evt] = cb
    def emit(self, *args, **kwargs): pass

@pytest.fixture
def mock_config():
    """EP-01: Mock config for ExecPosFSM that provides regime_adaptation for ExposureGuard."""
    cfg = MagicMock()
    
    # trading.risk (dict path for ExposureGuard._load_soft_limit_config)
    cfg.trading.risk = {
        "soft_limits": {
            "mode": "clip",
            "clip_min_notional_usdt": 10.0,
            "directional_ratio_max": 3.0,
            "side_exposure_usdt": 600.0,
            "margin_exposure_usdt": 1000.0,
        },
        "regime_adaptation": {
            "trend_up_delta": 0.5,
            "trend_down_delta": 0.5, 
            "flat_delta": -0.5, 
            "bounds": [1.0, 5.0]
        }
    }
    
    # trading.execution
    exec_cfg = MagicMock()
    exec_cfg.exposure.count_pending_orders = True
    exec_cfg.exposure.exclude_reduce_only = True
    exec_cfg.cooldown_after_close_ms = 1000
    cfg.trading.execution = exec_cfg
    
    # domains.execution_position
    dom_ep = MagicMock()
    dom_ep.idempotent_cancel.max_retries = 3
    dom_ep.event_dedup.max_size = 100
    dom_ep.event_dedup.ttl_ms = 1000
    # P1: Add fallback config (required by exposure_guard)
    dom_ep.fallback.policy = "fail_closed"
    dom_ep.fallback.risk_reduction_pct = "0.5"
    dom_ep.fallback.backoff_ms = [200, 500, 1000]
    cfg.domains.execution_position = dom_ep
    
    # watchdog defaults
    cfg.trading.watchdog.ack_ttl_ms = 500
    cfg.trading.watchdog.fill_ttl_ms = 1000
    
    # Explicitly disable root guardian config to prevent MagicMock leakage
    cfg.guardian = None
    
    return cfg

def test_exposure_guard_wiring(mock_config):
    fsm_core = MockFSM()
    
    # Patch DomainConfigResolver to bypass complex config resolution and provide valid values
    with patch("apps.reference.domains.execution_position.exposure_guard.DomainConfigResolver") as MockResolver:
        mock_resolver_inst = MockResolver.return_value
        eg_mock = MagicMock()
        # Provide float/int values which _to_dec handles (str(val))
        eg_mock.max_equity_utilization_pct = 100.0
        eg_mock.max_portfolio_fraction = 1.0
        eg_mock.max_long_utilization_pct = 100.0
        eg_mock.max_short_utilization_pct = 100.0
        eg_mock.max_concentration_pct = 100.0
        # Use 3.0 to match SoftLimits config
        eg_mock.max_directional_ratio = 3.0
        eg_mock.directional_ratio_max = 3.0
        
        eg_mock.pending_ttl_sec = 60
        eg_mock.post_fill_ttl_sec = 60
        eg_mock.stale_ttl_sec = 60
        
        mock_resolver_inst.get_exposure_guard.return_value = eg_mock
        
        # Init FSM (shadow_mode=True to skip adapter)
        ep_fsm = ExecPosFSM(mock_config, fsm_core, shadow_mode=True)
        
        # Spy on ExposureGuard
        orig_method = ep_fsm.exposure_guard.on_regime_changed
        ep_fsm.exposure_guard.on_regime_changed = MagicMock(side_effect=orig_method)
        
        # Verify initial state matches our mocks
        assert ep_fsm.exposure_guard.max_directional_ratio == Decimal("3.0")
        
        # Scenario: structural regime event should NOT mutate global exposure ratio
        payload = {
            "symbol": "BTCUSDT",
            "regime": "MEAN_REVERSION",
            "confidence": 0.9,
            "regime_layer": "structural",
            "regime_scope": "per_symbol",
            "regime_clock": "bar",
        }
        msg = Message(op="EVT", verb="REGIME_DETECTED", pld=payload, src="rd", dst="ep")
        
        # Trigger Listener manually (simulating bus)
        listener = fsm_core.listeners.get("EVT:REGIME_DETECTED")
        assert listener is not None, "ExecPosFSM must subscribe to EVT:REGIME_DETECTED"
        
        listener(msg)
        
        ep_fsm.exposure_guard.on_regime_changed.assert_not_called()
        assert ep_fsm.exposure_guard.max_directional_ratio == Decimal("3.0")

        # Scenario: explicit global execution-micro regime may adapt exposure
        payload_trend = {
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
            "confidence": 0.9,
            "regime_layer": "execution_micro",
            "regime_scope": "global",
            "regime_clock": "event_driven",
        }
        msg_trend = Message(op="EVT", verb="REGIME_DETECTED", pld=payload_trend, src="rd", dst="ep")
        listener(msg_trend)
        
        ep_fsm.exposure_guard.on_regime_changed.assert_called_with(ExecutionRegimeBucket.TREND_UP)
        assert ep_fsm.exposure_guard.max_directional_ratio == Decimal("3.5")

def test_config_strictness(mock_config):
    """Verify that configuration prohibits unknown keys (Fail Fast)."""
    with pytest.raises(ValidationError) as excinfo:
        RegimeAdaptationConfig(
            trend_up_delta=0.1, 
            trend_down_delta=0.1, 
            flat_delta=0.1, 
            bounds=[2.0, 4.0],
            ghost_key="I SHOULD NOT BE HERE" # Forbidden
        )
    assert "Extra inputs are not permitted" in str(excinfo.value)
    assert "ghost_key" in str(excinfo.value)
