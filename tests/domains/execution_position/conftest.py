
import pytest
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from vfoundation.core.protocol import Message
try:
    from apps.reference.config_models import AuroraConfig
except ImportError:
    AuroraConfig = MagicMock

# --- Shared Harness ---

@dataclass
class MockProtocolMessage(Message):
    """Protocol message compatible with Message protocol"""
    pass

class FakeBus:
    def __init__(self):
        self.events = []
    
    def emit(self, topic, *args, **kwargs):
        # Handle both (topic, payload) and (topic, msg=...) patterns
        self.events.append((topic, args, kwargs))

    def listen(self, topic, handler):
        pass

@pytest.fixture
def fsm_config():
    """Mock configuration to satisfy FSM requirements"""
    cfg = MagicMock()
    # Mock defaults for accessors
    cfg.trading.execution.watchdog.ack_ttl_ms = 5000
    cfg.trading.execution.watchdog.fill_ttl_ms = 5000
    cfg.trading.execution.anti_race_close_ms = 800
    cfg.trading.execution.cooldown_after_close_ms = 10_000
    cfg.domains.execution_position.fsm_open.idempotency_window_sec = 60
    
    # Event deduplication config
    event_dedup = MagicMock()
    event_dedup.max_size = 100000
    event_dedup.ttl_ms = 86400000
    warm_state = MagicMock()
    warm_state.enabled = True
    warm_state.storage_path = "logs/test_execution_terminal_identity_cache.json"
    warm_state.max_entries = 2000
    event_dedup.warm_state = warm_state
    cfg.domains.execution_position.event_dedup = event_dedup
    
    # Idempotent cancel config
    idempotent_cancel = MagicMock()
    idempotent_cancel.max_retries = 2
    cfg.domains.execution_position.idempotent_cancel = idempotent_cancel
    
    # Emergency config
    emergency = MagicMock()
    emergency.enabled = False
    emergency.wait_mode_bars = 2
    emergency.emergency_sl_bps = 100
    cfg.trading.execution.manage.emergency = emergency
    
    # Trailing defaults
    trailing = MagicMock()
    trailing.activation_pct = 0.003
    trailing.trail_pct = 0.006
    trailing.min_update_interval_sec = 5
    cfg.trailing = trailing
    
    # Brackets config (enabled for functionality)
    cfg.trading.execution.manage.auto = True
    cfg.trading.execution.manage.brackets.enable = True
    cfg.trading.execution.manage.brackets.oco_emulation = True
    cfg.trading.execution.manage.brackets.sl.fixed_bps = 40
    cfg.trading.execution.manage.brackets.tp.fixed_bps = 80
    cfg.trading.execution.manage.brackets.offset_bps = 5
    
    # Mock instrument specs
    btc_spec = MagicMock()
    btc_spec.tick_size = Decimal("0.01")
    btc_spec.step_size = Decimal("0.001")
    btc_spec.min_qty = Decimal("0.001")
    btc_spec.min_notional = Decimal("5.0")
    btc_spec.execution = MagicMock()
    btc_spec.execution.target_leverage = 20
    
    class InstrumentsDict(dict):
        pass
    
    instruments_dict = InstrumentsDict({"BTCUSDT": btc_spec})
    cfg.instruments = instruments_dict
    
    # Strategies Assets
    btc_asset_config = MagicMock()
    btc_asset_config.exit = MagicMock()
    btc_asset_config.exit.sl_pct = 0.02
    btc_asset_config.exit.max_hold_sec = 600
    btc_asset_config.take_profit = MagicMock()
    btc_asset_config.take_profit.tp_low_ratio = 0.5
    btc_asset_config.take_profit.tp_high_ratio = 1.0
    btc_asset_config.take_profit.partial_exit_pct = 0.5
    btc_asset_config.trailing_stop = MagicMock()
    btc_asset_config.trailing_stop.enabled = False
    
    cfg.strategies.aurora.assets = {"BTCUSDT": btc_asset_config}
    cfg.strategies.aurora.decision.bar_gating = None
    
    # ExposureGuard config
    eg = cfg.domains.execution_position.exposure_guard
    eg.max_equity_utilization_pct = "95.0"
    eg.max_portfolio_fraction = "1.0"
    eg.max_long_utilization_pct = "100.0"
    eg.max_short_utilization_pct = "100.0"
    eg.max_directional_ratio = "5.0"
    eg.max_concentration_pct = "20.0"
    eg.pending_ttl_sec = 5
    eg.post_fill_ttl_sec = 5
    eg.stale_ttl_sec = 10
    
    fb = cfg.domains.execution_position.fallback
    fb.policy = "fail_closed"
    fb.risk_reduction_pct = "0.5"
    fb.backoff_ms = [200, 500, 1000]

    cfg.trading.execution.exposure.leverage_defaults = {"__default__": 20, "BTCUSDT": 20}
    cfg.trading.execution.exposure.count_pending_orders = True
    cfg.trading.execution.exposure.exclude_reduce_only = True
    
    cfg.trading.risk = {
        "soft_limits": {
            "mode": "clip",
            "clip_min_notional_usdt": "10.0",
            "directional_ratio_max": "3.0",
            "side_exposure_usdt": "600.0",
            "margin_exposure_usdt": "1100.0",
        }
    }
    
    storage_mock = MagicMock()
    storage_mock.order_history_db = ":memory:"
    cfg.ops.storage = storage_mock

    # Mock API keys to keep shadow mode
    cfg.binance_api.testnet.api_key = ""
    cfg.binance_api.testnet.api_secret = ""
    cfg.binance_api.testnet.rest_url = ""
    cfg.binance_api.live.api_key = ""
    cfg.binance_api.live.api_secret = ""
    cfg.binance_api.live.rest_url = ""

    # NEW: Support get_domain_mode
    cfg.get_domain_mode.return_value = "testnet"
    cfg.trading.mode = "testnet"

    return cfg

@pytest.fixture
def fsm_harness(fsm_config):
    """
    Harness to inject ExecPosFSM with mocked dependencies.
    """
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    
    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian") as mock_guardian_cls:
        mock_guardian = mock_guardian_cls.return_value
        mock_guardian.is_duplicate.return_value = False
        
        bus = FakeBus()
        fsm = ExecPosFSM(config=fsm_config, fsm=bus)
        fsm.order_guardian = mock_guardian
        
        yield fsm, bus, fsm_config
