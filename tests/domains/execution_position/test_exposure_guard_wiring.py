import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal
from apps.reference.domains.execution_position.exposure_guard import ExposureGuard
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.config_models import AuroraConfig, TradingConfig, TradingRiskConfig, RegimeAdaptationConfig, SoftLimitConfigModel
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
    # Construct strictly typed config for Risk
    risk_real = TradingRiskConfig(
        soft_limits=SoftLimitConfigModel(
             mode="clip",
             clip_min_notional_usdt=10.0,
             directional_ratio_max=3.0,
             side_exposure_usdt=600.0,
             margin_exposure_usdt=1000.0
        ),
        regime_adaptation=RegimeAdaptationConfig(
            trend_up_delta=0.5,
            trend_down_delta=0.5, 
            flat_delta=-0.5, 
            bounds=[1.0, 5.0]
        )
    )
    
    cfg = MagicMock()
    
    # Config structure mocking
    # trading.risk
    cfg.trading.risk = risk_real
    
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
        
        # Scenario: Regime detected as MEAN_REVERSION
        payload = {"regime": "MEAN_REVERSION", "confidence": 0.9}
        msg = Message(op="EVT", verb="REGIME_DETECTED", pld=payload, src="rd", dst="ep")
        
        # Trigger Listener manually (simulating bus)
        listener = fsm_core.listeners.get("EVT:REGIME_DETECTED")
        assert listener is not None, "ExecPosFSM must subscribe to EVT:REGIME_DETECTED"
        
        listener(msg)
        
        # Assert Wiring
        ep_fsm.exposure_guard.on_regime_changed.assert_called_with(ExecutionRegimeBucket.FLAT)
        
        # Assert Logic Calculation
        # Base 3.0 + Flat Delta (-0.5) = 2.5
        assert ep_fsm.exposure_guard.max_directional_ratio == Decimal("2.5")
        
        # Scenario: Regime detected as TREND_UP
        payload_trend = {"regime": "TREND_UP", "confidence": 0.9}
        msg_trend = Message(op="EVT", verb="REGIME_DETECTED", pld=payload_trend, src="rd", dst="ep")
        listener(msg_trend)
        
        # Base (Persistent 3.0) + Trend Delta (0.5) = 3.5
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
