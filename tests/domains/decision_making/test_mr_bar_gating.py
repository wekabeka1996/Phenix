"""
Test MR Bar-Path Gating (T2B-02 + T2B-03).

Verifies that MeanReversionHandler:
1. Subscribes to CMD:PROCESS_STRATEGY (primary trigger)
2. Uses Fail-Closed gating on tf_sec
3. Only processes bars with matching timeframe (180s)

P1 Architecture: This test ensures MR is strictly 3-minute bar-driven
using CMD:PROCESS_STRATEGY as the orchestrated trigger.
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_config():
    """Create a mock AuroraConfig with mean_reversion strategy configured."""
    from apps.reference.config_models import MRAssetConfig
    
    cfg = MagicMock()
    
    # strategies.mean_reversion
    cfg.strategies = MagicMock()
    cfg.strategies.mean_reversion = MagicMock()
    cfg.strategies.mean_reversion.enabled = True
    cfg.strategies.mean_reversion.timeframe_sec = 300  # 5 minutes (FIX-BACKTEST-TF)
    cfg.strategies.mean_reversion.execution = MagicMock()
    cfg.strategies.mean_reversion.execution.entry_order_type = "MARKET"
    cfg.strategies.mean_reversion.execution.entry_tif = None
    
    # Strategy params
    strategy = MagicMock()
    strategy.bb_window = 20
    strategy.bb_num_std = 2.0
    strategy.atr_window = 14
    strategy.rsi_window = 14
    strategy.min_bars = 25
    strategy.min_bb_width = 0.001
    strategy.max_bb_width = 0.05
    strategy.entry_threshold = 0.05
    strategy.rsi_oversold = 30
    strategy.rsi_overbought = 70
    strategy.sl_atr_mult = 1.5
    strategy.tp_to_mid = True
    strategy.cooldown_sec = 60
    cfg.strategies.mean_reversion.strategy = strategy
    
    # Regime thresholds
    regime_thresholds = MagicMock()
    regime_thresholds.high_vol_pct = 0.03
    regime_thresholds.low_vol_pct = 0.01
    cfg.strategies.mean_reversion.regime_thresholds = regime_thresholds
    
    # Risk config
    risk = MagicMock()
    risk.position_size_usd = 100
    cfg.strategies.mean_reversion.risk = risk
    
    # Assets — use actual MRAssetConfig for type checking
    # Can't use full MRAssetConfig without pydantic validation, so mock it but set the right type
    asset = MagicMock(spec=MRAssetConfig)
    asset.enabled = True
    asset.allowed_regimes = ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"]
    asset.strategy = None
    asset.risk = None
    cfg.strategies.mean_reversion.assets = {"BTCUSDT": asset}
    
    # Global settings
    cfg.strategies.mean_reversion.allowed_regimes = ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"]
    cfg.strategies.mean_reversion.regime_sizing = {}
    cfg.strategies.mean_reversion.liquidity_gate = None
    
    # Strategies registry
    cfg.strategies_registry = MagicMock()
    cfg.strategies_registry.assignments = {"BTCUSDT": ["mean_reversion"]}
    
    return cfg


@pytest.fixture
def fsm_mock():
    """Create a mock FSMCore."""
    fsm = MagicMock()
    fsm.listen = MagicMock()
    fsm.emit = MagicMock()
    return fsm


@pytest.fixture
def mr_handler(mock_config, fsm_mock):
    """Create MeanReversionHandler instance with mocked dependencies."""
    from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler
    
    handler = MeanReversionHandler(fsm=fsm_mock, config=mock_config)
    handler.register()
    
    return handler


class TestMRBarPathGating:
    """Test suite for T2B-03: MR triggered via CMD:PROCESS_STRATEGY."""
    
    def test_mr_subscribes_to_cmd_process_strategy(self, mr_handler, fsm_mock):
        """
        T2B-03: Verify that MR handler subscribes to CMD:PROCESS_STRATEGY.
        """
        listen_calls = [call.args[0] for call in fsm_mock.listen.call_args_list]
        
        # T2B-03: Primary trigger is CMD:PROCESS_STRATEGY
        assert "CMD:PROCESS_STRATEGY" in listen_calls
        # EVT:BAR_CLOSED is now data-only (still subscribed for caching)
        assert "EVT:BAR_CLOSED" in listen_calls
        # Old tick trigger should NOT be subscribed
        assert "EVT:MARKET_TICK_FORWARDED" not in listen_calls
    
    def test_mr_rejects_wrong_tf(self, mr_handler):
        """
        Test: CMD with tf_sec=180 (3m) should be REJECTED (MR is 5m).
        """
        event = MagicMock()
        event.pld = {
            "symbol": "BTCUSDT",
            "tf_sec": 180,  # Wrong timeframe (3m, not 5m)
            "bar_close_ts": 1180000,
            "bar": {
                "symbol": "BTCUSDT",
                "timeframe_sec": 180,
                "open": "50000.0",
                "high": "50100.0",
                "low": "49900.0",
                "close": "50050.0",
                "volume": "1000.0",
                "start_ts_ms": 1000000,
                "end_ts_ms": 1180000,
                "trade_count": 100,
            },
            "features": {"price": "50050.0"},
            "warmup": {"full_ready": True},
        }
        
        initial_rejected = mr_handler._stats["bars_rejected_wrong_tf"]
        
        mr_handler._on_process_strategy(event)
        
        # Should have incremented rejection counter
        assert mr_handler._stats["bars_rejected_wrong_tf"] == initial_rejected + 1
    
    def test_mr_rejects_missing_tf(self, mr_handler):
        """
        Test: CMD without tf_sec should be REJECTED (Fail-Closed).
        """
        event = MagicMock()
        event.pld = {
            "symbol": "BTCUSDT",
            "bar_close_ts": 1180000,
            # No tf_sec field
            "bar": {
                "symbol": "BTCUSDT",
                "open": "50000.0",
                "high": "50100.0",
                "low": "49900.0",
                "close": "50050.0",
                "volume": "1000.0",
                "start_ts_ms": 1000000,
                "end_ts_ms": 1180000,
                "trade_count": 100,
            },
            "features": {"price": "50050.0"},
            "warmup": {"full_ready": True},
        }
        
        initial_rejected = mr_handler._stats["bars_rejected_missing_tf"]
        
        # Should NOT crash
        mr_handler._on_process_strategy(event)
        
        # Should have incremented rejection counter
        assert mr_handler._stats["bars_rejected_missing_tf"] == initial_rejected + 1
    
    def test_mr_accepts_correct_tf(self, mr_handler):
        """
        Test: CMD with tf_sec=300 (5m) should be PROCESSED.
        """
        event = MagicMock()
        event.pld = {
            "symbol": "BTCUSDT",
            "tf_sec": 300,  # Correct timeframe (5m per FIX-BACKTEST-TF)
            "bar_close_ts": 1300000,
            "bar": {
                "symbol": "BTCUSDT",
                "timeframe_sec": 300,
                "open": "50000.0",
                "high": "50100.0",
                "low": "49900.0",
                "close": "50050.0",
                "volume": "1000.0",
                "start_ts_ms": 1000000,
                "end_ts_ms": 1300000,
                "trade_count": 100,
            },
            "features": {"price": "50050.0"},
            "warmup": {"full_ready": True},
        }
        
        initial_received = mr_handler._stats["bars_received"]
        initial_rejected_tf = mr_handler._stats["bars_rejected_wrong_tf"]
        initial_rejected_missing = mr_handler._stats["bars_rejected_missing_tf"]
        
        mr_handler._on_process_strategy(event)
        
        # Should have incremented received counter
        assert mr_handler._stats["bars_received"] == initial_received + 1
        
        # Should NOT have incremented rejection counters
        assert mr_handler._stats["bars_rejected_wrong_tf"] == initial_rejected_tf
        assert mr_handler._stats["bars_rejected_missing_tf"] == initial_rejected_missing
    
    def test_mr_no_tick_subscription(self, mr_handler, fsm_mock):
        """
        Verify that MR handler does NOT subscribe to tick events.
        """
        listen_calls = [call.args[0] for call in fsm_mock.listen.call_args_list]
        
        # These should NOT be present
        assert "EVT:MARKET_TICK_FORWARDED" not in listen_calls
        assert "EVT:MARKET_TICK_RECEIVED" not in listen_calls


class TestMRTimeframeConfig:
    """Test that timeframe configuration is loaded correctly."""
    
    def test_timeframe_loaded_from_config(self, mr_handler):
        """Verify handler loads timeframe_sec from config."""
        assert mr_handler.timeframe_sec == 300
    
    def test_stats_initialized(self, mr_handler):
        """Verify T2B-02 stats counters are initialized."""
        assert "bars_received" in mr_handler._stats
        assert "bars_rejected_wrong_tf" in mr_handler._stats
        assert "bars_rejected_missing_tf" in mr_handler._stats
        
        # All should start at 0
        assert mr_handler._stats["bars_received"] == 0
        assert mr_handler._stats["bars_rejected_wrong_tf"] == 0
        assert mr_handler._stats["bars_rejected_missing_tf"] == 0


class TestMREventRouting:
    """Test that CMD:PROCESS_STRATEGY events are routed correctly to strategy logic."""
    
    def test_symbol_not_enabled_skipped(self, mr_handler):
        """
        Test: CMD for non-enabled symbol should be skipped.
        """
        event = MagicMock()
        event.pld = {
            "symbol": "SOLUSDT",  # Not in enabled_symbols
            "tf_sec": 300,
            "bar_close_ts": 1300000,
            "bar": {
                "symbol": "SOLUSDT",
                "timeframe_sec": 300,
                "open": "100.0",
                "high": "101.0",
                "low": "99.0",
                "close": "100.5",
                "volume": "1000.0",
                "start_ts_ms": 1000000,
                "end_ts_ms": 1300000,
                "trade_count": 100,
            },
            "features": {"price": "100.5"},
            "warmup": {"full_ready": True},
        }
        
        initial_completed = mr_handler._stats["bars_completed"]
        
        mr_handler._on_process_strategy(event)
        
        # bars_completed should NOT increase (symbol not enabled)
        assert mr_handler._stats["bars_completed"] == initial_completed
