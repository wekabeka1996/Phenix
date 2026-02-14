
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
from apps.reference.core.time.clock import Clock
from vfoundation.core.protocol import Message

class MockClock(Clock):
    def __init__(self, ts_sec=1000):
        self._now = ts_sec
    def now_sec(self):
        return self._now
    def now_ms(self):
        return int(self._now * 1000)
    def monotonic(self):
        return self._now
    def sleep_sec(self, seconds):
        self._now += seconds
    def sleep_ms(self, milliseconds):
        self._now += milliseconds / 1000.0

class EventRecorder:
    def __init__(self):
        self.events = []
    def emit(self, event_name, payload, why, **kwargs):
        self.events.append({"event": event_name, "payload": payload, "why": why})
    def listen(self, event, callback):
        pass

@pytest.fixture
def mock_config():
    cfg = SimpleNamespace()
    models = MagicMock()
    
    # SMA Trend
    sma = MagicMock()
    sma.sma_short_period = 10
    sma.sma_long_period = 20
    sma.snr_center = 1.0
    sma.snr_sigmoid_a = 2.0
    sma.snr_noise_floor = 0.001
    sma.persistence_window = 5
    sma.persistence_min_ratio = 0.6
    sma.confidence_min = 0.1
    sma.confidence_max = 0.95
    sma.confidence_multiplier = 20.0
    models.sma_trend = sma
    
    # Volatility
    vol = MagicMock()
    vol.enabled = True
    vol.atr_period = 14
    vol.atr_sma_length = 5
    vol.allow_close_to_close_atr = False
    vol.threshold_multiplier = 1.5
    vol.low_vol_multiplier = 0.5
    vol.high_vol_confidence_multiplier = 1.0
    vol.low_vol_confidence_multiplier = 1.0
    models.volatility = vol
    
    cfg.models = models
    
    # REG-FIX-01: Direct config attributes for BAR-ONLY mode
    cfg.basis_tf_sec = 300
    cfg.uncertain_cutoff = 0.25
    cfg.hysteresis_bars = 3
    cfg.vol_slope_gate_enabled = False
    cfg.vol_slope_gate_eps = -0.005
    cfg.vol_slope_gate_confirm_bars = 3
    
    # System
    sys = MagicMock()
    md = MagicMock()
    md.tick_ttl_ms = 0
    sys.market_data = md
    cfg.system = sys
    return cfg

def test_regime_updates_only_on_basis_bar(mock_config):
    fsm = EventRecorder()
    clock = MockClock()
    detector = RegimeDetector(mock_config, fsm, clock=clock)
    detector.start()
    
    # 1. Send TICK (tf_sec missing or 0)
    pld_tick = {
        "symbol": "BTCUSDT", "ts": 1000000, 
        "features": {"price": 100},
        # Missing tf_sec implies 0
    }
    msg_tick = Message(op="EVT", verb="FEATURES_CALCULATED", pld=pld_tick, src="test", dst="any")
    detector.handle_event(msg_tick)
    
    assert len(fsm.events) == 0, "Tick should be ignored"
    
    # 2. Send BAR (tf_sec=300) MATCHES basis
    pld_bar = {
        "symbol": "BTCUSDT", "ts": 1000000, 
        "features": {"price": 100},
        "tf_sec": 300
    }
    msg_bar = Message(op="EVT", verb="FEATURES_CALCULATED", pld=pld_bar, src="test", dst="any")
    detector.handle_event(msg_bar)
    
    assert len(fsm.events) == 1, "Bar should trigger regime"
    assert fsm.events[0]["event"] == "EVT:REGIME_DETECTED"
    
    # 3. Send BAR (tf_sec=60) MISMATCH
    pld_bar_1m = {
        "symbol": "BTCUSDT", "ts": 1000000, 
        "features": {"price": 100},
        "tf_sec": 60
    }
    msg_1m = Message(op="EVT", verb="FEATURES_CALCULATED", pld=pld_bar_1m, src="test", dst="any")
    detector.handle_event(msg_1m)
    assert len(fsm.events) == 1, "1m bar should be ignored (1 != 1)"

def test_no_double_clocking(mock_config):
    """Ensure strictly one update per basis bar (with fresh data)."""
    fsm = EventRecorder()
    clock = MockClock(ts_sec=1)  # Set clock to match event timestamps
    detector = RegimeDetector(mock_config, fsm, clock=clock)
    detector.start()
    
    # Sequence of events in a single cycle
    # 1. Features (Tick) -> filters (tf_sec=0 ignored by REG-FIX-01)
    # 2. Features (Bar) -> accepts (tf_sec=300 matches basis)
    
    # Use ts in ms matching clock (1000ms = 1sec)
    msg_tick = Message(op="EVT", verb="FEATURES_CALCULATED", pld={"symbol":"S", "ts":1000, "features":{"price":1}, "tf_sec":0}, src="t", dst="a")
    msg_bar = Message(op="EVT", verb="FEATURES_CALCULATED", pld={"symbol":"S", "ts":1000, "features":{"price":1}, "tf_sec":300}, src="t", dst="a")
    
    detector.handle_event(msg_tick)
    detector.handle_event(msg_bar)
    
    assert len(fsm.events) == 1
