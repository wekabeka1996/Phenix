"""
Test Orchestrated Cycle via CMD:PROCESS_STRATEGY (T2B-03).

Verifies the unified bar-driven decision loop:
1. CMD:PROCESS_STRATEGY is emitted only after bar-features (tf_sec >= 60)
2. No CMD is emitted for tick-features (tf_sec = 0)
3. Aurora runs only on CMD with tf_sec = 300
4. MR runs only on CMD with tf_sec = 180
5. Strategies don't execute on wrong timeframes

P1 Architecture: This test ensures the orchestrated decision cycle.
"""

import pytest
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch, call


class TestCMDProcessStrategyEmission:
    """Test that FE emits CMD:PROCESS_STRATEGY correctly."""
    
    def test_cmd_emitted_only_after_bar_features(self):
        """
        Test 1: When tf_sec >= 60 and bar_close_ts > 0, CMD:PROCESS_STRATEGY is emitted.
        
        Instead of instantiating full FE, we test the emission logic directly.
        """
        # The emission happens in _calculate_and_emit_features_for_tf after emit(FEATURES_CALCULATED)
        # We verify by checking the code path exists in feature_engineering.py
        
        # Read the source to verify CMD emission is present
        import inspect
        from apps.reference.domains.feature_engineering import feature_engineering
        
        source = inspect.getsource(feature_engineering.FeatureEngineering._calculate_and_emit_features_for_tf)
        
        # Verify CMD:PROCESS_STRATEGY emission is in the code
        assert "CMD:PROCESS_STRATEGY" in source, "CMD:PROCESS_STRATEGY emission should be in _calculate_and_emit_features_for_tf"
        # REC-01-FIX: Changed from tf_sec > 0 to tf_sec >= 60 for fail-closed
        assert "tf_sec < 60" in source or "tf_sec >= 60" in source, "Should check tf_sec >= 60 before CMD emission (REC-01-FIX)"
        assert "bar_close_ts" in source, "Should include bar_close_ts in CMD payload"
    
    def test_no_cmd_for_tick_features(self):
        """
        Test 2: Verify that CMD is only emitted when tf_sec > 0 and bar_data exists.
        
        The code should have a guard: `if bar_data and tf_sec and tf_sec > 0:`
        """
        import inspect
        from apps.reference.domains.feature_engineering import feature_engineering
        
        source = inspect.getsource(feature_engineering.FeatureEngineering._calculate_and_emit_features_for_tf)
        
        # Verify the guard exists
        # REC-01-FIX: Changed from tf_sec > 0 to if-elif chain with tf_sec < 60 check
        assert "tf_sec < 60" in source, \
            "CMD emission should be guarded by tf_sec >= 60 check (REC-01-FIX)"
        
        # Verify tick-path (tf_sec=0) in _calculate_and_emit_features
        tick_source = inspect.getsource(feature_engineering.FeatureEngineering._calculate_and_emit_features)
        assert "tf_sec=0" in tick_source, "Tick-path should call with tf_sec=0"


class TestAuroraRunsOnCMD:
    """Test that Aurora only runs on CMD:PROCESS_STRATEGY with tf_sec=300."""
    
    @pytest.fixture
    def mock_config(self):
        """Create mock config for Aurora."""
        cfg = MagicMock()
        cfg.strategies = MagicMock()
        cfg.strategies.aurora = MagicMock()
        cfg.strategies.aurora.timeframe_sec = 300
        # SCORCHED-EARTH-2026-01-27: legacy_tick_path_enabled removed (migration complete)
        cfg.strategies.aurora.execution = MagicMock()
        cfg.strategies.aurora.execution.entry_order_type = "LIMIT"
        cfg.strategies.aurora.execution.entry_tif = "GTX"
        
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
        
        cfg.strategies.aurora.assets = {
            "BTCUSDT": MagicMock(
                enabled=True, 
                signal_threshold=None, 
                neutral_threshold=None,
                reentry_cooldown_sec=None,
                holding_period=None
            )
        }
        
        cfg.strategies_registry = MagicMock()
        cfg.strategies_registry.assignments = {"BTCUSDT": ["aurora"]}
        
        return cfg
    
    def test_aurora_runs_only_on_cmd_300(self, mock_config):
        """
        Test 3: CMD(tf_sec=300) → Aurora executes.
                CMD(tf_sec=180) → Aurora does NOT execute.
        """
        from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
        
        emit_mock = MagicMock()
        handler = AuroraHandler(
            config=mock_config,
            emit_fn=emit_mock,
            strategy_id="aurora",
        )
        
        # Mock scoring kernel
        handler.scoring_kernel_cls = MagicMock()
        handler.scoring_kernel_cls.compute = MagicMock(
            return_value=MagicMock(side="BUY", score=Decimal("0.5"), deferred=False)
        )
        
        # Test: CMD with tf_sec=300 (should execute)
        cmd_300 = {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1000000,
            "bar": {"close": "50000.0", "open": "50000.0", "high": "50100.0", "low": "49900.0", "volume": "100"},
            "features": {"price": "50000.0", "obi": "0.5", "tfi": "0.3"},
            "warmup": {"full_ready": True, "ready": {}},
        }
        
        handler._symbol_states["BTCUSDT"].warmup_full_ready = True
        # DM-CRITICAL-PATCHES-02: Inject heartbeat
        handler._symbol_states["BTCUSDT"].last_regime_heartbeat_ms = int(time.time() * 1000)
        
        handler.on_process_strategy(cmd_300)
        
        # Scoring should have been called
        handler.scoring_kernel_cls.compute.assert_called()
        
        # Reset
        handler.scoring_kernel_cls.reset_mock()
        
        # Test: CMD with tf_sec=180 (should NOT execute)
        cmd_180 = {
            "symbol": "BTCUSDT",
            "tf_sec": 180,
            "bar_close_ts": 1000000,
            "features": {"price": "50000.0"},
            "warmup": {"full_ready": True},
        }
        
        handler.on_process_strategy(cmd_180)
        
        # Scoring should NOT have been called
        handler.scoring_kernel_cls.compute.assert_not_called()


class TestMRRunsOnCMD:
    """Test that MR only runs on CMD:PROCESS_STRATEGY with tf_sec=180."""
    
    @pytest.fixture
    def mock_config(self):
        """Create mock config for MR."""
        from apps.reference.config_models import MRAssetConfig
        
        cfg = MagicMock()
        cfg.strategies = MagicMock()
        cfg.strategies.mean_reversion = MagicMock()
        cfg.strategies.mean_reversion.enabled = True
        cfg.strategies.mean_reversion.timeframe_sec = 180
        cfg.strategies.mean_reversion.execution = MagicMock()
        cfg.strategies.mean_reversion.execution.entry_order_type = "MARKET"
        cfg.strategies.mean_reversion.execution.entry_tif = None
        
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
        strategy.confidence_base = 0.5
        strategy.confidence_bb_slope = 2.0
        strategy.confidence_rsi_bonus = 0.2
        cfg.strategies.mean_reversion.strategy = strategy
        
        regime_thresholds = MagicMock()
        regime_thresholds.high_vol_pct = 0.03
        regime_thresholds.low_vol_pct = 0.01
        cfg.strategies.mean_reversion.regime_thresholds = regime_thresholds
        
        risk = MagicMock()
        risk.position_size_usd = 100
        cfg.strategies.mean_reversion.risk = risk
        
        asset = MagicMock(spec=MRAssetConfig)
        asset.enabled = True
        asset.allowed_regimes = ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"]
        asset.strategy = None
        asset.risk = None
        cfg.strategies.mean_reversion.assets = {"BTCUSDT": asset}
        
        cfg.strategies.mean_reversion.allowed_regimes = ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"]
        cfg.strategies.mean_reversion.regime_sizing = {}
        cfg.strategies.mean_reversion.liquidity_gate = None
        
        cfg.strategies_registry = MagicMock()
        cfg.strategies_registry.assignments = {"BTCUSDT": ["mean_reversion"]}
        
        return cfg
    
    @pytest.fixture
    def fsm_mock(self):
        fsm = MagicMock()
        fsm.listen = MagicMock()
        fsm.emit = MagicMock()
        return fsm
    
    @pytest.fixture
    def mr_handler(self, mock_config, fsm_mock):
        from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler
        handler = MeanReversionHandler(fsm=fsm_mock, config=mock_config)
        handler.register()
        return handler
    
    def test_mr_runs_only_on_cmd_180(self, mr_handler):
        """
        Test 4: CMD(tf_sec=180) → MR executes.
                CMD(tf_sec=300) → MR does NOT execute.
        """
        # Test: CMD with tf_sec=180 (should execute)
        cmd_180 = MagicMock()
        cmd_180.pld = {
            "symbol": "BTCUSDT",
            "tf_sec": 180,
            "bar_close_ts": 1000000,
            "features": {"price": "50000.0"},
            "warmup": {"full_ready": True},
        }
        
        initial_completed = mr_handler._stats["bars_completed"]
        initial_rejected = mr_handler._stats["bars_rejected_wrong_tf"]
        
        mr_handler._on_process_strategy(cmd_180)
        
        # Should have processed (bars_completed might not increment if insufficient bars, but rejection should not)
        assert mr_handler._stats["bars_rejected_wrong_tf"] == initial_rejected
        
        # Test: CMD with tf_sec=300 (should NOT execute)
        cmd_300 = MagicMock()
        cmd_300.pld = {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1000000,
            "features": {"price": "50000.0"},
            "warmup": {"full_ready": True},
        }
        
        mr_handler._on_process_strategy(cmd_300)
        
        # Should have been rejected due to wrong tf_sec
        assert mr_handler._stats["bars_rejected_wrong_tf"] == initial_rejected + 1
    
    def test_mr_subscribes_to_cmd_process_strategy(self, mr_handler, fsm_mock):
        """
        Verify that MR handler subscribes to CMD:PROCESS_STRATEGY.
        """
        listen_calls = [c.args[0] for c in fsm_mock.listen.call_args_list]
        
        assert "CMD:PROCESS_STRATEGY" in listen_calls
        # BAR_CLOSED is now data-only (still present but not trigger)
        assert "EVT:BAR_CLOSED" in listen_calls
        # Tick trigger should NOT be present
        assert "EVT:MARKET_TICK_FORWARDED" not in listen_calls


class TestNoDoubleExecution:
    """Test idempotency - same bar_close_ts should not execute twice."""
    
    @pytest.fixture
    def mock_config(self):
        """Create mock config for Aurora."""
        cfg = MagicMock()
        cfg.strategies = MagicMock()
        cfg.strategies.aurora = MagicMock()
        cfg.strategies.aurora.timeframe_sec = 300
        
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
        
        cfg.strategies.aurora.assets = {
            "BTCUSDT": MagicMock(
                enabled=True, 
                signal_threshold=None, 
                neutral_threshold=None,
                reentry_cooldown_sec=None,
                holding_period=None
            )
        }
        
        cfg.strategies_registry = MagicMock()
        cfg.strategies_registry.assignments = {"BTCUSDT": ["aurora"]}
        
        return cfg
    
    def test_duplicate_cmd_handling(self, mock_config):
        """
        Test 5: Duplicate CMD with same bar_close_ts should be handled gracefully.
        
        Note: Current implementation does NOT have explicit dedup. 
        This test documents the behavior - signal may be emitted twice.
        Future enhancement: Add bar_close_ts dedup using LRU cache.
        """
        from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
        
        emit_mock = MagicMock()
        handler = AuroraHandler(
            config=mock_config,
            emit_fn=emit_mock,
            strategy_id="aurora",
        )
        
        handler.scoring_kernel_cls = MagicMock()
        handler.scoring_kernel_cls.compute = MagicMock(
            return_value=MagicMock(side="BUY", score=Decimal("0.5"), deferred=False, defer_reason=None)
        )
        handler._symbol_states["BTCUSDT"].warmup_full_ready = True
        handler._symbol_states["BTCUSDT"].last_regime_heartbeat_ms = int(time.time() * 1000)
        
        cmd = {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1000000,
            "features": {"price": "50000.0"},
            "warmup": {"full_ready": True, "ready": {}},
        }
        
        # Send same CMD twice
        handler.on_process_strategy(cmd)
        call_count_first = handler.scoring_kernel_cls.compute.call_count
        
        handler.on_process_strategy(cmd)
        call_count_second = handler.scoring_kernel_cls.compute.call_count
        
        # Document current behavior: scoring is called twice
        # (no dedup implemented yet)
        assert call_count_second == call_count_first + 1, \
            "Currently no dedup - consider adding bar_close_ts LRU cache in future"


class TestCMDIncludesFullBar:
    """T2B-05: Test that CMD includes full OHLCV bar."""
    
    def test_cmd_includes_bar_field(self):
        """
        Test: CMD payload code includes 'bar' field.
        """
        import inspect
        from apps.reference.domains.feature_engineering import feature_engineering
        
        source = inspect.getsource(feature_engineering.FeatureEngineering._calculate_and_emit_features_for_tf)
        
        # Verify bar is included in CMD payload
        assert '"bar":' in source or "'bar':" in source, \
            "CMD:PROCESS_STRATEGY should include 'bar' in payload (T2B-05)"
        assert "bar_dict" in source or "bar_data" in source, \
            "CMD should reference bar data"
    
    def test_cmd_bar_has_ohlcv_fields(self):
        """
        Test: CMD payload should include 'bar' field with OHLCV data.
        
        Note: FE passes bar_data from BarResampler directly, so we verify
        that the CMD emission includes the 'bar' field in payload.
        """
        import inspect
        from apps.reference.domains.feature_engineering import feature_engineering
        
        source = inspect.getsource(feature_engineering.FeatureEngineering._calculate_and_emit_features_for_tf)
        
        # Verify CMD payload includes bar field
        assert '"bar": bar_data' in source or "'bar': bar_data" in source, \
            "CMD payload should include 'bar' field with bar_data"
        
        # Verify bar_data is used in CMD emission (T2B-05 pattern)
        assert "CMD:PROCESS_STRATEGY" in source, "Should emit CMD:PROCESS_STRATEGY"
        assert "bar_data" in source, "Should reference bar_data for CMD"


class TestMRRejectsCMDWithoutBar:
    """T2B-05: Test that MR rejects CMD without bar."""
    
    @pytest.fixture
    def mock_config(self):
        """Create mock config for MR."""
        from apps.reference.config_models import MRAssetConfig
        
        cfg = MagicMock()
        cfg.strategies = MagicMock()
        cfg.strategies.mean_reversion = MagicMock()
        cfg.strategies.mean_reversion.enabled = True
        cfg.strategies.mean_reversion.timeframe_sec = 180
        
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
        strategy.confidence_base = 0.5
        strategy.confidence_bb_slope = 2.0
        strategy.confidence_rsi_bonus = 0.2
        cfg.strategies.mean_reversion.strategy = strategy
        
        regime_thresholds = MagicMock()
        regime_thresholds.high_vol_pct = 0.03
        regime_thresholds.low_vol_pct = 0.01
        cfg.strategies.mean_reversion.regime_thresholds = regime_thresholds
        
        risk = MagicMock()
        risk.position_size_usd = 100
        cfg.strategies.mean_reversion.risk = risk
        
        asset = MagicMock(spec=MRAssetConfig)
        asset.enabled = True
        asset.allowed_regimes = ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"]
        asset.strategy = None
        asset.risk = None
        cfg.strategies.mean_reversion.assets = {"BTCUSDT": asset}
        
        cfg.strategies.mean_reversion.allowed_regimes = ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"]
        cfg.strategies.mean_reversion.regime_sizing = {}
        cfg.strategies.mean_reversion.liquidity_gate = None
        
        cfg.strategies_registry = MagicMock()
        cfg.strategies_registry.assignments = {"BTCUSDT": ["mean_reversion"]}
        
        return cfg
    
    @pytest.fixture
    def fsm_mock(self):
        fsm = MagicMock()
        fsm.listen = MagicMock()
        fsm.emit = MagicMock()
        return fsm
    
    @pytest.fixture
    def mr_handler(self, mock_config, fsm_mock):
        from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler
        handler = MeanReversionHandler(fsm=fsm_mock, config=mock_config)
        handler.register()
        return handler
    
    def test_mr_rejects_cmd_without_bar(self, mr_handler):
        """
        T2B-05: CMD without 'bar' field should be REJECTED.
        """
        cmd_no_bar = MagicMock()
        cmd_no_bar.pld = {
            "symbol": "BTCUSDT",
            "tf_sec": 180,
            "bar_close_ts": 1000000,
            # No 'bar' field!
            "features": {"price": "50000.0"},
            "warmup": {"full_ready": True},
        }
        
        initial_rejected = mr_handler._stats.get("bars_rejected_missing_bar", 0)
        
        mr_handler._on_process_strategy(cmd_no_bar)
        
        # Should increment missing_bar counter
        assert mr_handler._stats["bars_rejected_missing_bar"] == initial_rejected + 1
    
    def test_mr_accepts_cmd_with_bar(self, mr_handler):
        """
        T2B-05: CMD with 'bar' field should be ACCEPTED.
        """
        cmd_with_bar = MagicMock()
        cmd_with_bar.pld = {
            "symbol": "BTCUSDT",
            "tf_sec": 180,
            "bar_close_ts": 1000000,
            "bar": {
                "symbol": "BTCUSDT",
                "timeframe_sec": 180,
                "open": "50000.0",
                "high": "50100.0",
                "low": "49900.0",
                "close": "50050.0",
                "volume": "100.0",
                "trade_count": 500,
                "start_ts_ms": 820000,
                "end_ts_ms": 1000000,
            },
            "features": {"price": "50050.0"},
            "warmup": {"full_ready": True},
        }
        
        initial_completed = mr_handler._stats["bars_completed"]
        initial_rejected = mr_handler._stats.get("bars_rejected_missing_bar", 0)
        
        mr_handler._on_process_strategy(cmd_with_bar)
        
        # Should NOT increment missing_bar counter
        assert mr_handler._stats.get("bars_rejected_missing_bar", 0) == initial_rejected
        # bars_completed might increment if processing succeeded
    
    def test_mr_uses_real_ohlcv(self, mr_handler):
        """
        T2B-05: MR should use real OHLCV from bar, not synthetic.
        
        Verify that code uses bar data from CMD payload.
        """
        import inspect
        from apps.reference.domains.decision_making import mean_reversion_handler
        
        source = inspect.getsource(mean_reversion_handler.MeanReversionHandler._on_process_strategy)
        
        # Should NOT have synthetic bar creation pattern
        assert "open=price" not in source, \
            "Should not create synthetic bar with open=price"
        assert "high=price" not in source, \
            "Should not create synthetic bar with high=price"
        
        # Should have bar_data.get patterns for OHLCV
        assert 'bar_data.get("open"' in source or "bar_data.get('open'" in source, \
            "Should get 'open' from bar_data"
        assert 'bar_data.get("close"' in source or "bar_data.get('close'" in source, \
            "Should get 'close' from bar_data"
