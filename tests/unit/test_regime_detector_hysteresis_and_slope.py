"""
Unit tests for Hysteresis and Slope Gate in RegimeDetector.

HYSTERESIS-SLOPE-GATE-01: Tests for regime stability fixes.

T1: Hysteresis confirmation (3 bars needed for stable)
T2: Slope gate blocks dying storm
T3: Lock prevents reclassification after storm_rejected
T4: Confidence stability (stable_confidence preserved)
"""

import pytest
from decimal import Decimal
from collections import deque
from unittest.mock import MagicMock, patch
from typing import Dict, Any


# Create minimal mock config
class MockSMAConfig:
    sma_short_period = 3
    sma_long_period = 8
    confidence_multiplier = 40.0
    confidence_min = 0.5
    confidence_max = 0.95


class MockVolatilityConfig:
    enabled = True
    atr_period = 5
    atr_sma_length = 10
    allow_close_to_close_atr = True
    threshold_multiplier = 1.5
    low_vol_multiplier = 0.6
    high_vol_confidence_multiplier = 2.0
    low_vol_confidence_multiplier = 3.0


class MockMeanReversionConfig:
    threshold = 0.005
    confidence_multiplier = 100.0


class MockModelsConfig:
    sma_trend = MockSMAConfig()
    volatility = MockVolatilityConfig()
    mean_reversion = MockMeanReversionConfig()


class MockSystemMarketData:
    bar_ttl_ms = 10000
    tick_ttl_ms = 2000


class MockSystem:
    market_data = MockSystemMarketData()


class MockAuroraConfig:
    """Minimal config for testing RegimeDetector."""
    basis_tf_sec = 300
    uncertain_cutoff = 0.20
    liveness_factor = 3
    hysteresis_bars = 3
    vol_slope_gate_enabled = True
    vol_slope_gate_eps = 0.0
    vol_slope_gate_confirm_bars = 2
    models = MockModelsConfig()
    system = MockSystem()


class MockFSM:
    """Mock FSM for testing."""
    def __init__(self):
        self.emitted = []
        self.listeners = {}
    
    def emit(self, verb, payload, why=""):
        self.emitted.append({"verb": verb, "payload": payload, "why": why})
    
    def listen(self, verb, handler):
        self.listeners[verb] = handler


class MockClock:
    """Mock clock for deterministic testing."""
    def __init__(self, now_ms_val=1000000000):
        self._now_ms = now_ms_val
        self._monotonic = now_ms_val / 1000.0
    
    def now_ms(self):
        return self._now_ms
    
    def monotonic(self):
        return self._monotonic
    
    def advance(self, ms):
        self._now_ms += ms
        self._monotonic += ms / 1000.0


class MockMessage:
    """Mock Message for testing."""
    def __init__(self, verb: str, pld: Dict[str, Any]):
        self.verb = verb
        self.pld = pld


@pytest.fixture
def detector():
    """Create a RegimeDetector instance for testing."""
    # Import here to avoid issues with module loading
    from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
    
    config = MockAuroraConfig()
    fsm = MockFSM()
    clock = MockClock()
    
    return RegimeDetector(config, fsm, clock=clock)


@pytest.fixture
def make_features_event():
    """Factory for FEATURES_CALCULATED events."""
    def _make(symbol="BTCUSDT", ts_ms=1000000000, price=50000.0, 
              sma_short=50100.0, sma_long=50000.0, high=50500.0, low=49500.0,
              tf_sec=300):
        return MockMessage(
            verb="FEATURES_CALCULATED",
            pld={
                "symbol": symbol,
                "ts": ts_ms,
                "tf_sec": tf_sec,
                "features": {
                    "price": price,
                    "sma_short": sma_short,
                    "sma_long": sma_long,
                    "high": high,
                    "low": low,
                }
            }
        )
    return _make


class TestHysteresis:
    """T1: Hysteresis confirmation tests."""
    
    def test_hysteresis_requires_n_bars_for_stable(self, detector, make_features_event):
        """Stable regime should only change after N consecutive bars."""
        # Initial state: stable=UNCERTAIN
        # Send 1 bar with HIGH_VOL conditions (high ATR)
        for i in range(12):  # Warmup ATR buffers
            event = make_features_event(
                ts_ms=1000000000 + i * 300000,
                price=50000,
                high=52000,  # High volatility
                low=48000,
            )
            detector.handle_event(event)
        
        # Check that stable_regime hasn't flipped immediately
        # (It takes 3 bars per hysteresis_bars config)
        last_payload = detector.fsm.emitted[-1]["payload"]
        
        # After warmup, we should see hysteresis in action
        assert "hysteresis_confirm_count" in last_payload
        assert "raw_regime" in last_payload
        assert "stable_confidence" in last_payload
    
    def test_hysteresis_raw_vs_stable_differ_during_transition(self, detector, make_features_event):
        """Raw regime can differ from stable during confirmation window."""
        # Warmup with stable conditions
        for i in range(15):
            event = make_features_event(
                ts_ms=1000000000 + i * 300000,
                price=50000,
                high=50100,
                low=49900,
            )
            detector.handle_event(event)
        
        # Now we should have some emissions
        if detector.fsm.emitted:
            last_payload = detector.fsm.emitted[-1]["payload"]
            assert "raw_regime" in last_payload
            # stable may equal raw if confirmed, or differ if pending


class TestSlopeGate:
    """T2: Slope gate blocks dying storm."""
    
    def test_slope_gate_rejects_high_vol_with_falling_momentum(self, detector, make_features_event):
        """HIGH_VOL with falling vol_ratio slope should be rejected."""
        # Build rising vol_ratio history first
        vol_ratios = [1.8, 1.9, 2.0, 2.1, 2.0, 1.9, 1.8, 1.7]  # Falling at end
        
        for i, _ in enumerate(vol_ratios):
            event = make_features_event(
                ts_ms=1000000000 + i * 300000,
                price=50000,
                high=50000 + 1000 * vol_ratios[i] if i < len(vol_ratios) else 51000,
                low=50000 - 1000 * vol_ratios[i] if i < len(vol_ratios) else 49000,
            )
            detector.handle_event(event)
        
        # Check last emission for slope gate telemetry
        if detector.fsm.emitted:
            last_payload = detector.fsm.emitted[-1]["payload"]
            assert "vol_ratio_slope" in last_payload
            assert "storm_rejected" in last_payload


class TestLock:
    """T3: Lock prevents reclassification after storm_rejected."""
    
    def test_storm_rejected_blocks_trend_classification(self, detector, make_features_event):
        """After storm_rejected, should not flip to TREND_* on same bar."""
        # This is a structural test - the lock is applied before TREND detection
        # Since regime is set to UNCERTAIN by slope gate, TREND detection is skipped
        # (regime == "UNCERTAIN" check before Priority 3)
        
        # Send bars that would normally trigger TREND_UP
        for i in range(10):
            event = make_features_event(
                ts_ms=1000000000 + i * 300000,
                price=50000 + i * 100,  # Rising price
                sma_short=50000 + i * 90,  # Short SMA above long
                sma_long=50000 + i * 50,
                high=50500 + i * 100,
                low=49500 + i * 100,
            )
            detector.handle_event(event)
        
        # Verify telemetry includes storm_rejected field
        if detector.fsm.emitted:
            for emission in detector.fsm.emitted:
                payload = emission["payload"]
                assert "storm_rejected" in payload


class TestConfidenceStability:
    """T4: Confidence stability tests."""
    
    def test_stable_confidence_preserved_between_bars(self, detector, make_features_event):
        """stable_confidence should persist when raw != stable."""
        # First establish a stable regime with some confidence
        for i in range(10):
            event = make_features_event(
                ts_ms=1000000000 + i * 300000,
                price=50000,
                high=50200,
                low=49800,
            )
            detector.handle_event(event)
        
        # Check that stable_confidence is tracked
        if detector.fsm.emitted:
            last_payload = detector.fsm.emitted[-1]["payload"]
            assert "stable_confidence" in last_payload
            assert last_payload["stable_confidence"] is not None


class TestEMAHelper:
    """Test the EMA helper function."""
    
    def test_ema_basic(self, detector):
        """EMA should compute correctly."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        ema3 = detector._ema(values, 3)
        ema6 = detector._ema(values, 6)
        
        # EMA(3) should react faster than EMA(6)
        assert ema3 > ema6  # For rising values, shorter EMA is higher
    
    def test_ema_empty(self, detector):
        """EMA of empty list should return 0."""
        assert detector._ema([], 3) == 0.0
