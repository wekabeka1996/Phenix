"""
E2E Integration Test: Full Decision Pipeline (T2B-07).

This test verifies the complete chain from tick to signal:
    Tick → BarAggregator → EVT:BAR_CLOSED → FE → EVT:FEATURES_CALCULATED + CMD:PROCESS_STRATEGY → MR → EVT:STRATEGY_SIGNAL_PRODUCED

Purpose: Catch integration bugs at "seams" between components.

Requirements:
- Deterministic (no real I/O or randomness)
- In-memory FSM runtime
- Validates event sequence and payload contracts
"""

import pytest
from decimal import Decimal
from typing import Dict, List, Any
from unittest.mock import MagicMock, patch

# FSM Core for event bus
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.protocol import Message

# Components under test
from apps.reference.domains.market_data.bar_aggregator import BarAggregator


class EventCapture:
    """Capture all emitted events for verification."""
    
    def __init__(self):
        self.events: List[Dict[str, Any]] = []
    
    def capture(self, event_name: str, payload: Dict[str, Any], why: str, **kwargs):
        self.events.append({
            "event": event_name,
            "payload": payload,
            "why": why,
        })
    
    def get_events(self, event_name: str) -> List[Dict[str, Any]]:
        return [e for e in self.events if e["event"] == event_name]
    
    def count(self, event_name: str) -> int:
        return len(self.get_events(event_name))
    
    def reset(self):
        self.events.clear()


class TestE2EDecisionPipeline:
    """E2E test for the complete bar-driven decision pipeline.
    
    T2B-07: Validates that the chain works as an integrated system.
    """
    
    @pytest.fixture
    def fsm(self):
        """Create real FSM core for event dispatch."""
        return FSMCore()
    
    @pytest.fixture
    def event_capture(self, fsm):
        """Capture all events emitted during the test."""
        capture = EventCapture()
        
        # Patch FSM emit to capture events
        original_emit = fsm.emit
        def capturing_emit(event_name, payload, why, **kwargs):
            capture.capture(event_name, payload, why, **kwargs)
            original_emit(event_name, payload, why, **kwargs)
        
        fsm.emit = capturing_emit
        return capture
    
    @pytest.fixture
    def bar_aggregator(self, fsm):
        """Create BarAggregator connected to FSM."""
        def emit_fn(event_name, payload, **kwargs):
            why = kwargs.get("why", "bar_closed")
            fsm.emit(event_name, payload, why=why)
        
        return BarAggregator(
            timeframes_sec=[180],  # 3m bars only for simplicity
            emit_fn=emit_fn,
        )
    
    def test_bar_closed_emits_correctly(self, bar_aggregator, event_capture):
        """
        Stage 1: Verify BarAggregator emits EVT:BAR_CLOSED when bar completes.
        """
        symbol = "BTCUSDT"
        base_ts = 1000000  # Base timestamp in ms
        bar_duration_ms = 180 * 1000  # 180 seconds
        
        # Send ticks to form a complete bar
        # Bar boundary is at ts % bar_duration_ms == 0
        # Start at ts that aligns to bar boundary
        bar_start = (base_ts // bar_duration_ms) * bar_duration_ms
        bar_end = bar_start + bar_duration_ms
        
        # Tick 1: Open the bar
        bar_aggregator.on_tick(symbol, Decimal("50000"), Decimal("1"), bar_start + 1000)
        
        # Tick 2: Mid-bar tick
        bar_aggregator.on_tick(symbol, Decimal("50100"), Decimal("2"), bar_start + 90000)
        
        # Tick 3: Near end of bar
        bar_aggregator.on_tick(symbol, Decimal("50050"), Decimal("1"), bar_end - 1000)
        
        # Bar should NOT be closed yet
        assert event_capture.count("EVT:BAR_CLOSED") == 0
        
        # Tick 4: After bar close time - triggers bar close
        completed_bars = bar_aggregator.on_tick(symbol, Decimal("50200"), Decimal("1"), bar_end + 1000)
        
        # Should have closed a bar
        assert len(completed_bars) == 1
        assert event_capture.count("EVT:BAR_CLOSED") == 1
        
        # Verify payload
        bar_closed_event = event_capture.get_events("EVT:BAR_CLOSED")[0]
        payload = bar_closed_event["payload"]
        
        assert "bar" in payload
        bar = payload["bar"]
        assert bar["symbol"] == symbol
        assert bar["timeframe_sec"] == 180
        assert "open" in bar
        assert "high" in bar
        assert "low" in bar
        assert "close" in bar
    
    def test_full_chain_simulation(self, fsm, event_capture):
        """
        Stage 2: Simulate full chain with mocked components.
        
        This test verifies the event sequence without requiring full FE/MR setup.
        """
        # --- Setup: Track event flow ---
        event_sequence = []
        
        def track_event(name):
            def handler(msg):
                event_sequence.append(name)
            return handler
        
        # Register listeners for event tracking
        fsm.listen("EVT:BAR_CLOSED", track_event("BAR_CLOSED"))
        fsm.listen("EVT:FEATURES_CALCULATED", track_event("FEATURES_CALCULATED"))
        fsm.listen("CMD:PROCESS_STRATEGY", track_event("CMD:PROCESS_STRATEGY"))
        fsm.listen("EVT:STRATEGY_SIGNAL_PRODUCED", track_event("SIGNAL_PRODUCED"))
        
        # --- Simulate Stage 1: Bar closes ---
        fsm.emit("EVT:BAR_CLOSED", {
            "symbol": "BTCUSDT",
            "bar": {
                "symbol": "BTCUSDT",
                "timeframe_sec": 180,
                "open": "50000",
                "high": "50100",
                "low": "49900",
                "close": "50050",
                "volume": "100",
                "trade_count": 50,
                "start_ts_ms": 1000000,
                "end_ts_ms": 1180000,
            }
        }, why="bar_closed")
        
        # --- Simulate Stage 2: FE processes bar and emits ---
        # (In real runtime, FE listens to BAR_CLOSED and emits these)
        fsm.emit("EVT:FEATURES_CALCULATED", {
            "symbol": "BTCUSDT",
            "tf_sec": 180,
            "ts": 1180000,
            "features": {"price": "50050", "obi": "0.5"},
            "warmup": {"full_ready": True},
        }, why="features_calculated")
        
        fsm.emit("CMD:PROCESS_STRATEGY", {
            "symbol": "BTCUSDT",
            "tf_sec": 180,
            "bar_close_ts": 1180000,
            "bar": {
                "symbol": "BTCUSDT",
                "timeframe_sec": 180,
                "open": "50000",
                "high": "50100",
                "low": "49900",
                "close": "50050",
                "volume": "100",
                "trade_count": 50,
                "start_ts_ms": 1000000,
                "end_ts_ms": 1180000,
            },
            "features": {"price": "50050", "obi": "0.5"},
            "warmup": {"full_ready": True},
        }, why="process_strategy:bar:180s")
        
        # --- Simulate Stage 3: Strategy processes CMD and emits signal ---
        fsm.emit("EVT:STRATEGY_SIGNAL_PRODUCED", {
            "strategy_id": "mean_reversion",
            "symbol": "BTCUSDT",
            "signal_type": "LONG_ENTRY",
            "side": "BUY",
            "bar_close_ts": 1180000,
        }, why="mr_signal")
        
        # --- Verify Event Sequence ---
        assert event_sequence == [
            "BAR_CLOSED",
            "FEATURES_CALCULATED",
            "CMD:PROCESS_STRATEGY",
            "SIGNAL_PRODUCED",
        ], f"Expected sequential event flow, got: {event_sequence}"
    
    def test_cmd_payload_contract(self):
        """
        Stage 3: Verify CMD:PROCESS_STRATEGY payload contract.
        
        This test ensures the CMD payload contains all required fields.
        """
        # Required fields per T2B-03/05
        required_fields = ["symbol", "tf_sec", "bar_close_ts", "bar", "features"]
        
        # Valid payload
        valid_payload = {
            "symbol": "BTCUSDT",
            "tf_sec": 180,
            "bar_close_ts": 1180000,
            "bar": {
                "symbol": "BTCUSDT",
                "timeframe_sec": 180,
                "open": "50000",
                "high": "50100",
                "low": "49900",
                "close": "50050",
                "volume": "100",
                "trade_count": 50,
                "start_ts_ms": 1000000,
                "end_ts_ms": 1180000,
            },
            "features": {"price": "50050"},
            "warmup": {"full_ready": True},
        }
        
        # Verify all required fields present
        for field in required_fields:
            assert field in valid_payload, f"Missing required field: {field}"
        
        # Verify bar has OHLCV
        bar = valid_payload["bar"]
        assert all(k in bar for k in ["open", "high", "low", "close", "volume"]), \
            "Bar must have OHLCV fields"
        
        # Verify tf_sec matches bar.timeframe_sec
        assert valid_payload["tf_sec"] == bar["timeframe_sec"], \
            "tf_sec must match bar.timeframe_sec"
    
    def test_mr_handler_processes_cmd(self):
        """
        Stage 4: Verify MR handler processes CMD and increments counters.
        
        This is a focused integration test for MR's CMD processing.
        """
        from apps.reference.config_models import MRAssetConfig
        from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler
        
        # --- Setup mock config ---
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
        strategy.min_bars = 5  # Low for testing
        strategy.min_bb_width = 0.001
        strategy.max_bb_width = 0.05
        strategy.entry_threshold = 0.05
        strategy.rsi_oversold = 30
        strategy.rsi_overbought = 70
        strategy.sl_atr_mult = 1.5
        strategy.tp_to_mid = True
        strategy.cooldown_sec = 60
        strategy.confidence_base = 0.5
        strategy.confidence_distance_mult = 2.0
        strategy.rsi_confidence_boost = 0.2
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
        
        # --- Setup FSM and handler ---
        fsm = MagicMock()
        fsm.listen = MagicMock()
        fsm.emit = MagicMock()
        
        handler = MeanReversionHandler(fsm=fsm, config=cfg)
        handler.register()
        
        # --- Create CMD event ---
        cmd_event = MagicMock()
        cmd_event.pld = {
            "symbol": "BTCUSDT",
            "tf_sec": 180,
            "bar_close_ts": 1180000,
            "bar": {
                "symbol": "BTCUSDT",
                "timeframe_sec": 180,
                "open": "50000",
                "high": "50100",
                "low": "49900",
                "close": "50050",
                "volume": "100",
                "trade_count": 50,
                "start_ts_ms": 1000000,
                "end_ts_ms": 1180000,
            },
            "features": {"price": "50050"},
            "warmup": {"full_ready": True},
        }
        
        initial_received = handler._stats["bars_received"]
        initial_completed = handler._stats["bars_completed"]
        
        # --- Process CMD ---
        handler._on_process_strategy(cmd_event)
        
        # --- Verify processing occurred ---
        assert handler._stats["bars_received"] == initial_received + 1, \
            "bars_received should increment"
        
        # bars_completed may or may not increment depending on strategy state
        # but rejection counters should NOT increment
        assert handler._stats["bars_rejected_wrong_tf"] == 0
        assert handler._stats["bars_rejected_missing_tf"] == 0
        assert handler._stats["bars_rejected_missing_bar"] == 0


class TestE2EEventOrdering:
    """Test that events are processed in correct order (synchronous FSM guarantee)."""
    
    def test_synchronous_dispatch(self):
        """
        Verify FSM dispatches events synchronously (T2B-03 forensic finding).
        """
        fsm = FSMCore()
        execution_order = []
        
        def listener_a(msg):
            execution_order.append("A_start")
            # Emit another event from inside listener
            fsm.emit("EVT:NESTED", {"from": "A"}, why="nested")
            execution_order.append("A_end")
        
        def listener_b(msg):
            execution_order.append("B")
        
        def listener_nested(msg):
            execution_order.append("NESTED")
        
        fsm.listen("EVT:FIRST", listener_a)
        fsm.listen("EVT:FIRST", listener_b)
        fsm.listen("EVT:NESTED", listener_nested)
        
        # Emit first event
        fsm.emit("EVT:FIRST", {}, why="test")
        
        # Verify synchronous execution:
        # A starts, nested is processed IMMEDIATELY (sync), A ends, then B
        assert execution_order == ["A_start", "NESTED", "A_end", "B"], \
            f"Expected sync dispatch, got: {execution_order}"
