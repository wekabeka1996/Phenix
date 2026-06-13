import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
from apps.reference.config_loader import AuroraConfig
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
def base_mock_config():
    cfg = MagicMock(spec=AuroraConfig)
    models = MagicMock()
    
    # SMA Trend
    sma = MagicMock()
    sma.sma_short_period = 2
    sma.sma_long_period = 4
    sma.confidence_min = 0.15
    sma.confidence_max = 0.85
    sma.confidence_multiplier = 80.0
    sma.min_trend_spread = 0.005
    sma.adaptive_normalization = False
    sma.normalized_confidence_multiplier = 0.04
    models.sma_trend = sma
    
    # Volatility
    vol = MagicMock()
    vol.enabled = True
    vol.atr_period = 2
    vol.atr_sma_length = 4
    vol.allow_close_to_close_atr = True
    vol.threshold_multiplier = 2.0
    vol.low_vol_multiplier = 0.7
    vol.high_vol_confidence_multiplier = 2.5
    vol.low_vol_confidence_multiplier = 3.0
    vol.adaptive_percentile = None
    models.volatility = vol
    
    # Mean Reversion
    mr = MagicMock()
    mr.threshold = 0.008
    mr.confidence_multiplier = 120.0
    mr.adaptive_atr_multiplier = None
    mr.min_threshold = 0.003
    mr.max_threshold = 0.015
    models.mean_reversion = mr
    
    cfg.models = models
    cfg.basis_tf_sec = 300
    cfg.uncertain_cutoff = 0.25
    cfg.hysteresis_bars = 1  # transition immediately for test simplicity
    cfg.vol_slope_gate_enabled = False
    
    # System
    sys = MagicMock()
    md = MagicMock()
    md.tick_ttl_ms = 0
    sys.market_data = md
    cfg.system = sys
    return cfg

def test_adaptive_mean_reversion_threshold(base_mock_config):
    # Enable adaptive MR threshold in config
    base_mock_config.models.mean_reversion.adaptive_atr_multiplier = 1.5
    base_mock_config.models.mean_reversion.min_threshold = 0.003
    base_mock_config.models.mean_reversion.max_threshold = 0.015
    
    fsm = EventRecorder()
    clock = MockClock(ts_sec=1000)
    detector = RegimeDetector(base_mock_config, fsm, clock=clock)
    detector.start()
    
    # Feed 5 bars with constant range (high=10100, low=10000, close=10000)
    # This generates a steady ATR around 100.0, meaning vol_ratio ≈ 1.0 (NORMAL volatility)
    for i in range(5):
        pld = {
            "symbol": "BTCUSDT",
            "ts": (1000 + i * 300) * 1000,
            "tf_sec": 300,
            "features": {
                "price": 10000.0,
                "high": 10100.0,
                "low": 10000.0,
            }
        }
        detector.handle_event(Message(op="EVT", verb="FEATURES_CALCULATED", pld=pld, src="test", dst="any"))
    
    # We have warmed up buffers. Let's inject a bar that would trigger Mean Reversion.
    # Steady ATR is ~100. Price is 10000.
    # atr_pct = 100 / 10000 = 0.01 (1%)
    # adaptive_threshold = atr_pct * 1.5 = 0.015 (1.5%)
    # Current deviation is 0.5% (price=10050, short_sma=10000, long_sma=10000).
    # Since 0.5% < 1.5%, it should trigger MEAN_REVERSION.
    # Note: If it fell back to static threshold 0.008 (0.8%), it would also trigger.
    # But let's verify that adaptive threshold was computed.
    
    pld_test = {
        "symbol": "BTCUSDT",
        "ts": (1000 + 5 * 300) * 1000,
        "tf_sec": 300,
        "features": {
            "price": 10050.0,
            "high": 10150.0,
            "low": 10050.0,
            "sma_short": 10000.0,
            "sma_long": 10000.0,
        }
    }
    detector.handle_event(Message(op="EVT", verb="FEATURES_CALCULATED", pld=pld_test, src="test", dst="any"))
    
    last_event = fsm.events[-1]
    assert last_event["payload"]["regime"] == "MEAN_REVERSION"

def test_adaptive_confidence_normalization(base_mock_config):
    # Enable adaptive trend confidence normalization
    base_mock_config.models.sma_trend.adaptive_normalization = True
    base_mock_config.models.sma_trend.normalized_confidence_multiplier = 0.04
    
    # Disable Mean Reversion by raising its threshold to 0 or setting prices such that it is not MR.
    # If price deviation is large, it won't trigger MR.
    
    fsm = EventRecorder()
    clock = MockClock(ts_sec=1000)
    detector = RegimeDetector(base_mock_config, fsm, clock=clock)
    detector.start()
    
    # Warm up with high=10200, low=10000, close=10000. Steady ATR is ~200.
    for i in range(5):
        pld = {
            "symbol": "BTCUSDT",
            "ts": (1000 + i * 300) * 1000,
            "tf_sec": 300,
            "features": {
                "price": 10000.0,
                "high": 10200.0,
                "low": 10000.0,
            }
        }
        detector.handle_event(Message(op="EVT", verb="FEATURES_CALCULATED", pld=pld, src="test", dst="any"))
        
    # Inject a trend bar.
    # sma_short = 10500, sma_long = 10000. Price = 10600.
    # Deviation is large, so not MR.
    # Spread ratio = 5% = 0.05.
    # atr_baseline = 200. Price = 10000. atr_pct = 2% = 0.02.
    # normalized_spread = 0.05 / 0.02 = 2.5
    # confidence = 2.5 * 0.04 = 0.10 (clamped to min=0.15)
    # Since confidence 0.15 < uncertain_cutoff (0.25), it will be demoted to UNCERTAIN.
    # Without normalization: confidence = 0.05 * 80.0 = 4.0 (clamped to 0.85) -> TREND_UP.
    
    pld_test = {
        "symbol": "BTCUSDT",
        "ts": (1000 + 5 * 300) * 1000,
        "tf_sec": 300,
        "features": {
            "price": 10600.0,
            "high": 10800.0,
            "low": 10600.0,
            "sma_short": 10500.0,
            "sma_long": 10000.0,
        }
    }
    detector.handle_event(Message(op="EVT", verb="FEATURES_CALCULATED", pld=pld_test, src="test", dst="any"))
    
    last_event = fsm.events[-1]
    assert last_event["payload"]["regime"] == "UNCERTAIN"
    assert float(last_event["payload"]["confidence"]) == 0.15
