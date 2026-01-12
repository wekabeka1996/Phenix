"""
Test Aurora Tick-Path Gating (T2B-01).

Verifies that AuroraHandler correctly rejects tick-path events
and only processes bar events with matching tf_sec.

P0 CRITICAL: This test ensures Aurora is strictly 5-minute bar-driven.
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_config():
    """Create a mock AuroraConfig with aurora strategy configured."""
    cfg = MagicMock()
    
    # strategies.aurora
    cfg.strategies = MagicMock()
    cfg.strategies.aurora = MagicMock()
    cfg.strategies.aurora.timeframe_sec = 300  # 5 minutes
    
    # Decision config
    decision = MagicMock()
    decision.signal_threshold = 0.1
    decision.neutral_threshold = 0.05
    decision.side_bias_window_sec = 420
    decision.side_bias_target_ratio = 0.72
    decision.side_bias_penalty_factor = 0.25
    decision.side_bias_min_intents = 18
    decision.regime_threshold_multipliers = {"DEFAULT": 1.0}
    decision.direction_strength_scoring = None
    decision.signals = None
    decision.holding_period = None
    decision.reentry_cooldown_sec = None
    decision.gates = None
    decision.anti_churn = None
    cfg.strategies.aurora.decision = decision
    
    # Assets with explicit None for optional fields
    cfg.strategies.aurora.assets = {
        "BTCUSDT": MagicMock(
            enabled=True, 
            signal_threshold=None, 
            neutral_threshold=None,
            reentry_cooldown_sec=None,
            holding_period=None
        )
    }
    
    return cfg


@pytest.fixture
def aurora_handler(mock_config):
    """Create AuroraHandler instance with mocked dependencies."""
    from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
    
    emit_mock = MagicMock()
    monotonic_mock = MagicMock(return_value=1000.0)
    wall_time_mock = MagicMock(return_value=1000.0)
    
    handler = AuroraHandler(
        config=mock_config,
        emit_fn=emit_mock,
        monotonic_fn=monotonic_mock,
        wall_time_fn=wall_time_mock,
    )
    
    # Mock the scoring kernel to prevent actual computation
    handler.scoring_kernel_cls = MagicMock()
    handler.scoring_kernel_cls.compute = MagicMock(
        return_value=MagicMock(side="BUY", score=Decimal("0.5"), deferred=False, defer_reason=None)
    )
    
    return handler


class TestAuroraTickPathGating:
    """Test suite for T2B-01: Kill Phantom Tick-Path."""
    
    def test_tick_path_rejected_tf_sec_zero(self, aurora_handler):
        """
        Test A: Event with tf_sec=0 (tick-path) should be REJECTED.
        
        Verifies that Aurora does NOT process tick-level feature events.
        """
        event = {
            "symbol": "BTCUSDT",
            "tf_sec": 0,  # Tick-path
            "features": {
                "price": "50000.0",
                "obi": "0.5",
                "tfi": "0.3",
            },
            "warmup": {"full_ready": True},
        }
        
        initial_rejections = aurora_handler._tick_path_rejections
        
        aurora_handler.on_features_calculated(event)
        
        # Should have incremented rejection counter
        assert aurora_handler._tick_path_rejections == initial_rejections + 1
        
        # Scoring kernel should NOT have been called
        aurora_handler.scoring_kernel_cls.compute.assert_not_called()
    
    def test_tick_path_rejected_tf_sec_missing(self, aurora_handler):
        """
        Test C: Event without tf_sec attribute should be REJECTED.
        
        Verifies fail-closed behavior when tf_sec is missing entirely.
        """
        event = {
            "symbol": "BTCUSDT",
            # No tf_sec field at all
            "features": {
                "price": "50000.0",
                "obi": "0.5",
            },
            "warmup": {"full_ready": True},
        }
        
        initial_rejections = aurora_handler._tick_path_rejections
        
        # Should NOT crash
        aurora_handler.on_features_calculated(event)
        
        # Should have incremented rejection counter
        assert aurora_handler._tick_path_rejections == initial_rejections + 1
        
        # Scoring kernel should NOT have been called
        aurora_handler.scoring_kernel_cls.compute.assert_not_called()
    
    def test_tick_path_rejected_tf_sec_none(self, aurora_handler):
        """
        Test C (variant): Event with tf_sec=None should be REJECTED.
        """
        event = {
            "symbol": "BTCUSDT",
            "tf_sec": None,
            "features": {"price": "50000.0"},
            "warmup": {"full_ready": True},
        }
        
        initial_rejections = aurora_handler._tick_path_rejections
        
        aurora_handler.on_features_calculated(event)
        
        assert aurora_handler._tick_path_rejections == initial_rejections + 1
        aurora_handler.scoring_kernel_cls.compute.assert_not_called()
    
    def test_valid_bar_event_processed(self, aurora_handler):
        """
        Test B: Event with tf_sec=300 (matching 5m bar) should be PROCESSED.
        
        Verifies that Aurora correctly processes bar events.
        """
        # Set up warmup state for the symbol
        aurora_handler._symbol_states["BTCUSDT"].warmup_full_ready = True
        
        event = {
            "symbol": "BTCUSDT",
            "tf_sec": 300,  # Matches handler.timeframe_sec
            "features": {
                "price": "50000.0",
                "obi": "0.5",
                "tfi": "0.3",
            },
            "warmup": {"full_ready": True, "ready": {}},
        }
        
        initial_rejections = aurora_handler._tick_path_rejections
        
        aurora_handler.on_features_calculated(event)
        
        # Rejection counter should NOT have been incremented
        assert aurora_handler._tick_path_rejections == initial_rejections
        
        # Scoring kernel SHOULD have been called
        aurora_handler.scoring_kernel_cls.compute.assert_called_once()
    
    def test_wrong_timeframe_rejected(self, aurora_handler):
        """
        Test: Event with tf_sec=60 (1m bar, not 5m) should be REJECTED.
        
        Verifies that Aurora only processes its configured timeframe.
        """
        event = {
            "symbol": "BTCUSDT",
            "tf_sec": 60,  # 1m bar, but Aurora is 5m (300)
            "features": {"price": "50000.0"},
            "warmup": {"full_ready": True},
        }
        
        aurora_handler.on_features_calculated(event)
        
        # Scoring kernel should NOT have been called (wrong timeframe)
        aurora_handler.scoring_kernel_cls.compute.assert_not_called()
    
    def test_multiple_tick_rejections_counted(self, aurora_handler):
        """
        Test: Multiple tick-path events should all be counted.
        
        Verifies telemetry counter accuracy.
        """
        tick_event = {
            "symbol": "BTCUSDT",
            "tf_sec": 0,
            "features": {"price": "50000.0"},
            "warmup": {"full_ready": True},
        }
        
        initial_count = aurora_handler._tick_path_rejections
        
        # Send 10 tick events
        for _ in range(10):
            aurora_handler.on_features_calculated(tick_event)
        
        # Should have rejected all 10
        assert aurora_handler._tick_path_rejections == initial_count + 10


class TestAuroraTimeframeConfig:
    """Test that timeframe configuration is loaded correctly."""
    
    def test_timeframe_loaded_from_config(self, aurora_handler):
        """Verify handler loads timeframe_sec from config."""
        assert aurora_handler.timeframe_sec == 300
    
    def test_missing_timeframe_raises_error(self, mock_config):
        """Verify handler fails if timeframe_sec is missing."""
        from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
        
        # Remove timeframe_sec from config
        mock_config.strategies.aurora.timeframe_sec = None
        
        with pytest.raises(Exception):  # Should raise ConfigContractError
            AuroraHandler(
                config=mock_config,
                emit_fn=MagicMock(),
            )
