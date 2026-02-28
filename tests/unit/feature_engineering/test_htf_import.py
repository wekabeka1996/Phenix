import pytest
from unittest.mock import MagicMock, patch
from backtest_engine.data_processing.htf_provider import HTFHistoryProvider
from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
from vfoundation.core.protocol import Message
from apps.reference.config_loader import AuroraConfig

from apps.reference.config_models import AuroraConfig
from apps.reference.domain_config import DomainConfigResolver

from apps.reference.config_models import AuroraConfig

@pytest.fixture
def mock_fsm():
    fsm = MagicMock()
    return fsm

@pytest.fixture
def mock_config():
    cfg = MagicMock(spec=AuroraConfig)
    
    # Needs to match what DomainConfigResolver(cfg).get_decision_making() returns
    dm_mock = MagicMock()
    dm_mock.price_motion_sanity = "dummy_price_motion_sanity"
    
    domains_mock = MagicMock()
    domains_mock.decision_making = dm_mock
    cfg.domains = domains_mock
    
    return cfg

def test_on_htf_bars_imported_hydrates_pillar_state(mock_fsm, mock_config):
    with patch("apps.reference.domains.feature_engineering.feature_engineering.FeatureEngineeringConfig") as mock_cfg:
        
        # Give the simulated config scalar values instead of nested MagicMocks
        cfg_instance = mock_cfg.return_value
        cfg_instance.macro_sync_window = 100
        cfg_instance.macro_sync_anchors = ["BTCUSDT"]
        cfg_instance.macro_sync_bin_ms = 1000
        cfg_instance.enabled_timeframes_sec = [300]
        cfg_instance.macro_sync_max_gap_bins = 5
        cfg_instance.macro_sync_min_buffer = 10
        cfg_instance.macro_sync_ttl_ms = 60000
        cfg_instance.macro_sync_eps = 1e-8
        cfg_instance.macro_sync_max_late_ms = 5000
        cfg_instance.futures_enabled = False
        
        with patch("apps.reference.domains.feature_engineering.feature_engineering.FeatureCalculationEngine"):
            fe = FeatureEngineering(mock_fsm, mock_config)
            
            # Setup calc_engine mock
            mock_calc_engine = MagicMock()
            fe.calc_engine = mock_calc_engine
            
            # Create HTF payload
            payload = {
                "symbol": "BTCUSDT",
                "tf_sec": 86400,
                "anchor_time_ms": 1700000000000,
                "bars": [
                    {
                        "open_ts": 1700000000000,
                        "o": 40000.0,
                        "h": 41000.0,
                        "l": 39000.0,
                        "c": 40500.0,
                        "v": 100.5
                    }
                ],
                "why": "htf_bootstrap"
            }
            msg = Message(op="EVT", verb="HTF_BARS_IMPORTED", src="test", dst="any", pld=payload, why="test")
            
            # Call handler
            fe._on_htf_bars_imported(msg)
            
            # Verify pillar state creation
            assert "BTCUSDT" in fe._pillar_states
            state = fe._pillar_states["BTCUSDT"]
            
            # Verify calc_engine was called
            # calc_engine.update_pillar_candle(state, timeframe="d1", close=40500.0, high=41000.0, low=39000.0, bar_ts_ms=...)
            mock_calc_engine.update_pillar_candle.assert_called_once()
            args, kwargs = mock_calc_engine.update_pillar_candle.call_args
            assert args[0] == state
            assert kwargs["timeframe"] == "d1"
            assert kwargs["close"] == 40500.0
            assert kwargs["high"] == 41000.0
            assert kwargs["low"] == 39000.0
            # expected close_ts = 1700000000000 + 86400*1000 - 1 = 1700086399999
            assert kwargs["bar_ts_ms"] == 1700086399999
