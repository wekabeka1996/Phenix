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
    cfg.domains.execution_position.fsm_open.idempotency_window_sec = 60
    
    # Brackets config for ManageFlow
    cfg.trading.execution.manage.auto = True
    cfg.trading.execution.manage.brackets.enable = True
    cfg.trading.execution.manage.brackets.oco_emulation = True
    cfg.trading.execution.manage.brackets.sl.fixed_bps = 50
    cfg.trading.execution.manage.brackets.tp.fixed_bps = 100
    cfg.trading.execution.manage.brackets.offset_bps = 5
    
    # Mock instrument specs for BTCUSDT
    btc_spec = MagicMock()
    btc_spec.tick_size = Decimal("0.01")
    btc_spec.step_size = Decimal("0.001")
    btc_spec.min_qty = Decimal("0.001")
    btc_spec.min_notional = Decimal("5.0")
    
    # Dict-like access for instruments
    instruments_dict = {"BTCUSDT": btc_spec}
    cfg.instruments.get.side_effect = lambda k, default=None: instruments_dict.get(k, default)
    
    # Mock strategies.aurora.assets (per-symbol strategy overrides)
    # Production-like config required for fail-closed policy
    btc_asset_config = MagicMock()
    btc_asset_config.exit = MagicMock()
    btc_asset_config.exit.sl_pct = 0.02  # 2%
    btc_asset_config.exit.max_hold_sec = 600
    btc_asset_config.take_profit = MagicMock()
    btc_asset_config.take_profit.tp_low_ratio = 0.5
    btc_asset_config.take_profit.tp_high_ratio = 1.0
    btc_asset_config.take_profit.partial_exit_pct = 0.5
    btc_asset_config.trailing_stop = MagicMock()
    btc_asset_config.trailing_stop.enabled = False
    btc_asset_config.trailing_stop.activation_pct = 0.02
    btc_asset_config.trailing_stop.trail_pct = 0.01
    btc_asset_config.trailing_stop.min_update_interval_sec = 5
    
    cfg.strategies.aurora.assets = {"BTCUSDT": btc_asset_config}
    cfg.strategies.aurora.decision.bar_gating = None
    
    # Mock domains.execution_position.exposure_guard fields
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

    # Exposure leverage defaults are required by ExposureGuard.resolve_symbol_leverage()
    cfg.trading.execution.exposure.leverage_defaults = {"__default__": 20, "BTCUSDT": 20}
    
    # Risk Soft Limits
    cfg.trading.risk = {
        "soft_limits": {
            "mode": "clip",
            "clip_min_notional_usdt": "10.0",
            "directional_ratio_max": "3.0",
            "side_exposure_usdt": "600.0",
            "margin_exposure_usdt": "1100.0"
        }
    }
    
    # Mock ops.storage for OrderLedger
    storage_mock = MagicMock()
    storage_mock.order_history_db = ":memory:"
    cfg.ops.storage = storage_mock

    # Ensure ExecPosFSM stays in shadow_mode for this harness.
    # These tests exercise internal event-ordering logic and must not
    # initialize a real HTTP client.
    cfg.binance_api.testnet.api_key = ""
    cfg.binance_api.testnet.api_secret = ""
    cfg.binance_api.testnet.rest_url = ""
    cfg.binance_api.live.api_key = ""
    cfg.binance_api.live.api_secret = ""
    cfg.binance_api.live.rest_url = ""

    return cfg

@pytest.fixture
def fsm_harness(fsm_config):
    """
    Harness to inject ExecPosFSM with mocked dependencies to avoid DB/Network calls.
    Patches OrderGuardian to avoid sqlite3 initialization.
    """
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    
    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian") as mock_guardian_cls:
        # Configure the mock guardian instance
        mock_guardian = mock_guardian_cls.return_value
        mock_guardian.is_duplicate.return_value = False
        
        bus = FakeBus()
        fsm = ExecPosFSM(config=fsm_config, fsm=bus)
        
        # Inject standard mocks to sub-components if needed
        fsm.order_guardian = mock_guardian
        
        yield fsm, bus, fsm_config
