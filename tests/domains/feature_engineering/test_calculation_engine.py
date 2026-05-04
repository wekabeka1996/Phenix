import pytest
import decimal
from unittest.mock import MagicMock
import collections

from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
from apps.reference.domains.feature_engineering.types import FeatureEngineeringConfig, HotState, ColdState, PillarState

class MockPillarsNested:
    def __init__(self, enabled):
        self.enabled = enabled
        self.tactician = MagicMock(enabled=True, min_bars=2, roc_period=14, sensitivity=1.0)
        self.operator = MagicMock(enabled=True, min_bars=2, linreg_period=14, adx_period=14, sensitivity=1.0)
        self.strategist = MagicMock(enabled=True, min_bars=2, sma_period=200, sensitivity=1.0)
        self.weights = MagicMock(tactician=0.33, operator=0.33, strategist=0.34)

@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.feature_sanity_enabled = True
    cfg.feature_sanity_nan_inf_behavior = "neutral_and_not_ready"
    cfg.neutral_value = decimal.Decimal("0.0")
    cfg.feature_sanity_bounds = {}
    
    cfg.spread_health_gate_enabled = True
    cfg.spread_health_window_sec = 10
    cfg.spread_health_max_age_sec = 30
    cfg.spread_health_min_update_events = 5
    cfg.spread_health_min_trades_count = 2
    
    cfg.ema_bias_clamp_min = decimal.Decimal("-0.05")
    cfg.ema_bias_clamp_max = decimal.Decimal("0.05")
    
    cfg.macro_resid_enabled = True
    cfg.macro_resid_beta_window = 60
    cfg.macro_resid_mad_window = 30
    cfg.macro_resid_winsor_percentile = 0.05
    cfg.macro_resid_var_floor = 1e-7
    cfg.macro_resid_scale_floor = 1e-4
    cfg.macro_resid_clip = 3.0
    cfg.macro_resid_neutral = 0.0
    
    cfg.absorption_mode = "proxy"
    cfg.absorption_dedup_enabled = True
    cfg.absorption_neutral = 0.0
    cfg.absorption_proxy_window = 10
    cfg.absorption_proxy_eps = 1e-6
    cfg.absorption_dedup_window = 10
    cfg.absorption_dedup_threshold = 0.5
    cfg.absorption_clip = 1.0
    
    cfg.depth_imbalance_use_laplace_smoothing = True
    cfg.depth_half = decimal.Decimal("0.5")
    
    cfg.ms_per_sec = 1000
    cfg.volume_sma_length = 10
    cfg.volume_spike_eps = decimal.Decimal("0.001")
    cfg.volume_spike_cap = decimal.Decimal("5.0")
    cfg.volume_zscore_clip_sigma = 5.0
    
    cfg.volatility_window_ms = 14000
    cfg.volatility_sma_length = 10
    cfg.volatility_tick_floor = decimal.Decimal("0.0001")
    cfg.volatility_division_eps = decimal.Decimal("1e-9")
    cfg.volatility_state_cap = decimal.Decimal("5.0")
    
    cfg.macro_sync_enabled = True
    cfg.macro_sync_anchors = ["BTCUSDT"]
    cfg.macro_sync_time_diff_threshold_ms = 1000
    cfg.macro_sync_min_buffer = 3
    cfg.macro_sync_align_mode = "strict_len"
    cfg.macro_sync_ttl_ms = 5000
    cfg.macro_sync_window = 10
    
    cfg.funding_extreme_threshold = decimal.Decimal("0.01")
    
    cfg._cfg = MagicMock()
    cfg._cfg.pillars = MockPillarsNested(True)
    return cfg

@pytest.fixture
def engine(config):
    return FeatureCalculationEngine(config)

@pytest.fixture
def hot_state():
    return HotState(
        ema_short_alpha=0.1,
        ema_long_alpha=0.05
    )

@pytest.fixture
def cold_state():
    return ColdState()

@pytest.fixture
def pillar_state():
    return PillarState()

# --- SANITY FIREWALL TESTS ---

def test_sanitize_feature_success(engine):
    val, is_ready, reason = engine.sanitize_feature("price", 50000.0)
    assert is_ready
    assert not reason
    assert val == decimal.Decimal("50000.0")

def test_sanitize_feature_nan(engine):
    val, is_ready, reason = engine.sanitize_feature("price", float('nan'))
    assert not is_ready
    assert reason == "nan_inf:price"
    assert val == engine.cfg.neutral_value

def test_sanitize_feature_bounds(engine):
    engine.cfg.feature_sanity_bounds = {"price": {"min": 0, "max": 100000}}
    val, is_ready, reason = engine.sanitize_feature("price", 150000.0)
    assert not is_ready
    assert "out_of_range:price" in reason
    assert val == decimal.Decimal("100000.0")

def test_sanitize_feature_macro_resid_sentinel(engine):
    val, is_ready, reason = engine.sanitize_feature("macro_resid", None)
    assert not is_ready
    assert not reason # Should not append artificial reason
    assert val == engine.cfg.neutral_value

def test_sanitize_features_dict(engine):
    features = {"price": "50000", "invalid": "nan"}
    sanitized, updates, reasons = engine.sanitize_features_dict(features)
    assert updates["price"] is True
    assert updates["invalid"] is False
    assert len(reasons) == 1

# --- SPREAD HEALTH GATE TESTS ---

def test_update_and_check_book_health(engine):
    # STEP 1: No activity yet
    is_healthy, reason = engine.check_book_health("BTC", 1000)
    assert not is_healthy
    assert reason == "no_book_updates_received"
    
    # STEP 2: Activity but stale
    engine.update_book_health("BTC", 1000, is_book_update=True)
    is_healthy, reason = engine.check_book_health("BTC", 35000) # age 34000ms > max 30000ms
    assert not is_healthy
    assert "book_stale" in reason
    
    # STEP 3: Active but insufficient counts
    engine.update_book_health("BTC", 10000, is_book_update=True) # count = 1
    is_healthy, reason = engine.check_book_health("BTC", 11000)
    assert not is_healthy
    assert "insufficient_activity" in reason
    
    # STEP 4: Active and sufficient updates
    for i in range(5):
        engine.update_book_health("BTC", 10000, is_book_update=True)
    is_healthy, reason = engine.check_book_health("BTC", 11000)
    assert is_healthy
    assert not reason

# --- EMA CALCULATIONS ---

def test_ema_bias(engine, hot_state):
    # initial setup
    engine.update_ema(hot_state, decimal.Decimal("100"))
    assert hot_state.ema_short == decimal.Decimal("100")
    
    # Next update
    engine.update_ema(hot_state, decimal.Decimal("110"))
    assert hot_state.ema_short > decimal.Decimal("100")
    assert hot_state.ema_short > hot_state.ema_long # alpha_short > alpha_long
    
    bias_phi = engine.compute_ema_bias(hot_state)
    assert bias_phi > decimal.Decimal("0.5")
    assert bias_phi <= decimal.Decimal("1")

def test_ema_bias_clamp(engine, hot_state):
    engine.update_ema(hot_state, decimal.Decimal("100"))
    engine.update_ema(hot_state, decimal.Decimal("1000000")) # huge jump
    bias_phi = engine.compute_ema_bias(hot_state)
    assert bias_phi == decimal.Decimal("1.0")

# --- MACRO RESID ---

def test_macro_resid_insufficient(engine, hot_state):
    val, is_ready, reason = engine.compute_macro_resid(hot_state)
    assert not is_ready
    assert "insufficient_samples" in reason

def test_macro_resid_success(engine, hot_state):
    # Feed enough data to pass beta_window (60) AND mad_window (30)
    for i in range(100):
        engine.update_macro_resid(hot_state, 0.01 * (i % 2), 0.02 * (i % 2))
        engine.compute_macro_resid(hot_state)
    
    val, is_ready, reason = engine.compute_macro_resid(hot_state)
    assert is_ready
    assert not reason
    assert isinstance(val, decimal.Decimal)

def test_macro_resid_disabled(engine, hot_state):
    engine.cfg.macro_resid_enabled = False
    val, is_ready, reason = engine.compute_macro_resid(hot_state)
    assert is_ready
    assert val == engine.cfg.neutral_value

# --- ABSORPTION ---

def test_absorption_disabled(engine, hot_state):
    engine.cfg.absorption_mode = "disabled"
    val, is_ready, reason = engine.compute_absorption(hot_state)
    assert not is_ready
    assert reason == "mode_disabled"

def test_absorption_insufficient(engine, hot_state):
    val, is_ready, reason = engine.compute_absorption(hot_state)
    assert not is_ready
    assert "insufficient_samples" in reason

def test_absorption_success(engine, hot_state):
    for i in range(30):
        engine.update_absorption(hot_state, 100.0, 50.0, 0.1)
    
    val, is_ready, reason = engine.compute_absorption(hot_state)
    assert is_ready
    assert val > 0 # Buy dominated

def test_absorption_dedup_muted(engine, hot_state):
    for i in range(50):
        # Setup variation so proxy is not constant
        engine.update_absorption(hot_state, float(100 + i*10), float(50), float(i))
    
    # Trigger proxy calculation to fill proxy_buffer (needs dedup_window=10)
    for i in range(50):
        engine.update_absorption(hot_state, float(100 + i*10), float(50), float(i))
        engine.compute_absorption(hot_state)
        
    val, is_ready, reason = engine.compute_absorption(hot_state)
    # Dedup triggers muted -> ready is True, but reason presents
    assert is_ready
    assert "dedup_muted_telemetry" in reason
    assert val == engine.cfg.neutral_value

# --- VOLUME SPIKE & ZSCORE ---

def test_volume_spike_and_zscore(engine, hot_state):
    # bad dt
    engine.update_volume_spike(hot_state, volume=decimal.Decimal("100"), time_diff_ms=0)
    assert hot_state.volume_spike_not_ready_reason == "bad_dt"
    
    for i in range(5):
        engine.update_volume_spike(hot_state, volume=decimal.Decimal("100"), time_diff_ms=1000)
    
    assert engine.compute_volume_spike(hot_state) == decimal.Decimal("0.2") # phi = spike(1.0) / cap_max(5.0)
    assert isinstance(engine.compute_volume_zscore(hot_state), decimal.Decimal)

def test_compute_spread_bps(engine):
    bps = engine.compute_spread_bps(decimal.Decimal("100"), decimal.Decimal("101"), decimal.Decimal("100.5"))
    assert bps == decimal.Decimal("99.50") # (1 / 100.5) * 10000

def test_compute_depth_imbalance(engine):
    phi1 = engine.compute_depth_imbalance(decimal.Decimal("100"), decimal.Decimal("100"))
    assert phi1 == decimal.Decimal("0.5") # balanced
    
    phi2 = engine.compute_depth_imbalance(decimal.Decimal("0"), decimal.Decimal("100"))
    assert phi2 > decimal.Decimal("0.5") # ask dominated
    
# --- MACRO SYNC ---

def test_macro_sync(engine, hot_state):
    engine.update_macro_sync_buffer(hot_state, decimal.Decimal("100"), 100) # no return
    engine.update_macro_sync_buffer(hot_state, decimal.Decimal("101"), 100) # return 1
    engine.update_macro_sync_buffer(hot_state, decimal.Decimal("103"), 100) # return 2
    engine.update_macro_sync_buffer(hot_state, decimal.Decimal("105"), 100) # return 3
    
    anchor_prices = {"BTCUSDT": collections.deque([100, 101, 103, 105])}
    anchor_last_ts_ms = {"BTCUSDT": 1000}
    current_ts_ms = 1000
    
    phi = engine.compute_macro_sync(hot_state, anchor_prices, anchor_last_ts_ms=anchor_last_ts_ms, current_ts_ms=current_ts_ms)
    assert isinstance(phi, decimal.Decimal)
    assert hot_state.macro_sync_ready

def test_compute_funding_and_oi(engine, cold_state):
    engine.update_funding(cold_state, decimal.Decimal("0.001"))
    assert engine.compute_funding_normalized(cold_state) == decimal.Decimal("0.1000") # 0.001 / 0.01 threshold
    
    engine.update_open_interest(cold_state, decimal.Decimal("100"), 1000)
    engine.update_open_interest(cold_state, decimal.Decimal("110"), 2000)
    assert engine.compute_oi_delta_pct(cold_state) == decimal.Decimal("10.00")

# --- PILLARS ---
def test_pillars(engine, pillar_state):
    # Valid M15 append
    res1 = engine.update_pillar_candle(pillar_state, "m15", 100.0, bar_ts_ms=1000)
    assert res1 is True
    
    # Duplicate M15 append
    res2 = engine.update_pillar_candle(pillar_state, "m15", 101.0, bar_ts_ms=1000)
    assert res2 is False
    
    # Feed enough to trigger compute
    engine.update_pillar_candle(pillar_state, "m15", 100.0, bar_ts_ms=2000)
    engine.update_pillar_candle(pillar_state, "h4", 100.0, 105.0, 95.0, bar_ts_ms=3000)
    engine.update_pillar_candle(pillar_state, "h4", 102.0, 106.0, 96.0, bar_ts_ms=4000)
    engine.update_pillar_candle(pillar_state, "d1", 100.0, bar_ts_ms=5000)
    engine.update_pillar_candle(pillar_state, "d1", 103.0, bar_ts_ms=6000)
    
    res = engine.compute_pillars(pillar_state)
    assert "pillar_sum" in res
    
def test_pillars_disabled(engine, pillar_state):
    engine.cfg._cfg.pillars.enabled = False
    res = engine.compute_pillars(pillar_state)
    assert res["reason"] == "pillars_disabled"

# --- VOLATILITY ---

def test_volatility_state(engine, hot_state):
    # Need to cross volatility_window_ms (14000) twice to get 2 samples for Welford
    engine.update_volatility_state(hot_state, decimal.Decimal("100"), {"ts": 1000000000})
    engine.update_volatility_state(hot_state, decimal.Decimal("110"), {"ts": 1000000000 + 15000}) # pushes 1 sample
    engine.update_volatility_state(hot_state, decimal.Decimal("120"), {"ts": 1000000000 + 30000}) # pushes 1 sample
    
    phi = engine.compute_volatility_state(hot_state)
    assert isinstance(phi, decimal.Decimal)
    assert hot_state.volatility_state_ready
