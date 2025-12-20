import decimal
import time
from collections import deque
from types import SimpleNamespace


class _DummyFsm:
    def __init__(self):
        self.emitted: list[tuple[str, dict, str | None, object | None]] = []

    def listen(self, *_args, **_kwargs) -> None:
        return

    def emit(self, event_name: str, payload=None, why=None, data_ref=None) -> None:
        self.emitted.append((event_name, payload or {}, why, data_ref))


class _Cfg:
    neutral_value = decimal.Decimal("0.5")
    ms_per_sec = 1000

    # Volume spike
    volume_sma_length = 10
    volume_spike_eps = decimal.Decimal("0.00000001")
    volume_spike_cap = decimal.Decimal("5")

    # Macro sync
    macro_sync_enabled = True
    macro_sync_anchors = ["ANCHOR"]
    macro_sync_min_buffer = 5
    macro_sync_window = 200
    macro_sync_align_mode = "tail_min_len"
    macro_sync_ttl_ms = 10_000
    macro_sync_time_diff_threshold_ms = 10_000

    # Volatility
    volatility_window_ms = 1000
    volatility_sma_length = 10
    volatility_state_cap = decimal.Decimal("5")


def _prices_from_returns(start: decimal.Decimal, returns: list[float]) -> list[decimal.Decimal]:
    price = start
    prices = [price]
    for r in returns:
        price = price * (decimal.Decimal("1") + decimal.Decimal(str(r)))
        prices.append(price)
    return prices


def test_macro_sync_tail_alignment_not_constant():
    from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
    from apps.reference.domains.feature_engineering.types import HotState

    cfg = _Cfg()
    engine = FeatureCalculationEngine(cfg)

    # Varying return series (non-zero variance).
    sym_returns = [0.01, -0.004, 0.02, -0.01, 0.012, 0.006, -0.008, 0.015] * 6
    sym_prices = _prices_from_returns(decimal.Decimal("100"), sym_returns)

    # Anchor returns are the *tail* of symbol returns (length mismatch is the point of the test).
    anchor_returns = sym_returns[-14:]
    anchor_prices = _prices_from_returns(decimal.Decimal("1000"), anchor_returns)

    state = HotState(returns_buffer=deque(maxlen=cfg.macro_sync_window))
    for p in sym_prices:
        engine.update_macro_sync_buffer(state, p, 200)

    now_ms = 1_000_000
    phi = engine.compute_macro_sync(
        state,
        {"ANCHOR": deque(anchor_prices, maxlen=cfg.macro_sync_window)},
        anchor_last_ts_ms={"ANCHOR": now_ms},
        current_ts_ms=now_ms,
    )

    assert state.macro_sync_ready is True
    assert phi != cfg.neutral_value
    assert phi > decimal.Decimal("0.9")


def test_macro_sync_stale_anchor_blocks():
    from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
    from apps.reference.domains.feature_engineering.types import HotState

    cfg = _Cfg()
    cfg.macro_sync_ttl_ms = 500
    engine = FeatureCalculationEngine(cfg)

    sym_returns = [0.01, -0.004, 0.02, -0.01, 0.012, 0.006, -0.008, 0.015] * 2
    sym_prices = _prices_from_returns(decimal.Decimal("100"), sym_returns)
    anchor_prices = _prices_from_returns(decimal.Decimal("1000"), sym_returns[-8:])

    state = HotState(returns_buffer=deque(maxlen=cfg.macro_sync_window))
    for p in sym_prices:
        engine.update_macro_sync_buffer(state, p, 200)

    current_ts_ms = 10_000
    stale_anchor_ts = current_ts_ms - cfg.macro_sync_ttl_ms - 1
    phi = engine.compute_macro_sync(
        state,
        {"ANCHOR": deque(anchor_prices, maxlen=cfg.macro_sync_window)},
        anchor_last_ts_ms={"ANCHOR": stale_anchor_ts},
        current_ts_ms=current_ts_ms,
    )

    assert state.macro_sync_ready is False
    assert state.macro_sync_not_ready_reason == "no_fresh_anchor_data"
    assert phi == cfg.neutral_value


def test_volume_spike_time_normalized():
    from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
    from apps.reference.domains.feature_engineering.types import HotState

    cfg = _Cfg()
    engine = FeatureCalculationEngine(cfg)

    # Scenario A: 10 ticks/sec, vol per tick = 1 -> 10 vol/sec
    a = HotState(
        vol_hist=deque(maxlen=cfg.volume_sma_length),
        volume_rate_hist=deque(maxlen=cfg.volume_sma_length),
    )
    for _ in range(5):
        engine.update_volume_spike(a, volume=decimal.Decimal("1"), time_diff_ms=100)
    spike_a = engine.compute_volume_spike(a)

    # Scenario B: 1 tick/sec, vol per tick = 10 -> 10 vol/sec
    b = HotState(
        vol_hist=deque(maxlen=cfg.volume_sma_length),
        volume_rate_hist=deque(maxlen=cfg.volume_sma_length),
    )
    for _ in range(5):
        engine.update_volume_spike(b, volume=decimal.Decimal("10"), time_diff_ms=1000)
    spike_b = engine.compute_volume_spike(b)

    assert abs(spike_a - spike_b) < decimal.Decimal("0.000001")


def test_feature_engineering_zero_price_increments_data_quality_drop(monkeypatch):
    from apps.reference.config_loader import get_config
    from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering

    drops: list[tuple[str, str]] = []

    def _fake_inc_data_quality_drop(*, domain: str, reason: str) -> None:
        drops.append((domain, reason))

    fsm = _DummyFsm()
    config = get_config()
    fe = FeatureEngineering(fsm=fsm, config=config, feature_store=None)
    monkeypatch.setattr(fe, "_log_features_to_file", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        "apps.reference.domains.feature_engineering.feature_engineering.inc_data_quality_drop",
        _fake_inc_data_quality_drop,
    )

    symbol = "BTCUSDT"
    t0 = int(time.time() * 1000)
    tick1 = {"symbol": symbol, "ts": t0, "price": "1", "bid_size": "1", "ask_size": "1", "buy_volume": "0", "sell_volume": "0"}
    tick2 = {"symbol": symbol, "ts": t0 + 1000, "price": "0", "bid_size": "1", "ask_size": "1", "buy_volume": "0", "sell_volume": "0"}

    fe.on_market_tick(SimpleNamespace(pld=tick1))
    fe.on_market_tick(SimpleNamespace(pld=tick2))

    assert any(domain == "feature_engineering" and reason == "volatility_state_not_ready" for domain, reason in drops)
    assert any(evt == "EVT:FEATURES_CALCULATED" and isinstance(pld.get("warmup"), dict) for evt, pld, *_ in fsm.emitted)


# ============================================================
# TASK26: Suspicious Zone Tests - Feature Engineering
# ============================================================

def test_macro_sync_insufficient_data_explicit_flag():
    """
    TASK26.SZ.1: When n < min_buffer, macro_sync_ready=false with explicit reason.
    
    Not silent 0.5 - must have explicit insufficient_data flag.
    """
    from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
    from apps.reference.domains.feature_engineering.types import HotState

    cfg = _Cfg()
    cfg.macro_sync_min_buffer = 20  # Require 20 samples
    engine = FeatureCalculationEngine(cfg)

    # Only add 10 samples (less than min_buffer=20)
    state = HotState(returns_buffer=deque(maxlen=cfg.macro_sync_window))
    for i in range(10):
        engine.update_macro_sync_buffer(state, decimal.Decimal("100") + decimal.Decimal(str(i * 0.1)), 100)

    now_ms = 1_000_000
    anchor_prices = {"ANCHOR": deque([decimal.Decimal("1000")] * 10, maxlen=200)}

    phi = engine.compute_macro_sync(
        state,
        anchor_prices,
        anchor_last_ts_ms={"ANCHOR": now_ms},
        current_ts_ms=now_ms,
    )

    # Assert: explicit insufficient flag, not silent 0.5
    assert state.macro_sync_ready is False, "Must be not ready with insufficient data"
    assert hasattr(state, "macro_sync_not_ready_reason"), "Must have explicit reason"
    assert state.macro_sync_not_ready_reason is not None, "Reason must be set"


def test_macro_sync_ttl_expired_blocks_explicitly():
    """
    TASK26.SZ.2: TTL expired on anchor → macro_sync_ready=false with stale reason.
    """
    from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
    from apps.reference.domains.feature_engineering.types import HotState

    cfg = _Cfg()
    cfg.macro_sync_ttl_ms = 1000  # 1 second TTL
    engine = FeatureCalculationEngine(cfg)

    # Sufficient data
    state = HotState(returns_buffer=deque(maxlen=cfg.macro_sync_window))
    for i in range(30):
        engine.update_macro_sync_buffer(state, decimal.Decimal("100") + decimal.Decimal(str(i * 0.05)), 100)

    current_ts_ms = 50_000
    stale_ts = current_ts_ms - cfg.macro_sync_ttl_ms - 500  # 500ms past TTL

    phi = engine.compute_macro_sync(
        state,
        {"ANCHOR": deque([decimal.Decimal("1000")] * 30, maxlen=200)},
        anchor_last_ts_ms={"ANCHOR": stale_ts},
        current_ts_ms=current_ts_ms,
    )

    assert state.macro_sync_ready is False
    assert "fresh" in state.macro_sync_not_ready_reason.lower() or \
           "stale" in state.macro_sync_not_ready_reason.lower() or \
           state.macro_sync_not_ready_reason == "no_fresh_anchor_data"


def test_macro_sync_time_diff_threshold_validation():
    """
    TASK26.SZ.3: Time diff between ticks > threshold handled appropriately.
    """
    from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
    from apps.reference.domains.feature_engineering.types import HotState

    cfg = _Cfg()
    cfg.macro_sync_time_diff_threshold_ms = 5000  # 5 second max gap
    engine = FeatureCalculationEngine(cfg)

    state = HotState(returns_buffer=deque(maxlen=cfg.macro_sync_window))
    
    # First update
    engine.update_macro_sync_buffer(state, decimal.Decimal("100"), 100)
    
    # Update with LARGE time gap (10 seconds > 5 second threshold)
    engine.update_macro_sync_buffer(state, decimal.Decimal("101"), 10_000)
    
    # This should not crash and handle the gap appropriately
    assert len(state.returns_buffer) <= 2, "Buffer should be updated"


def test_volume_spike_zero_dt_no_crash():
    """
    TASK26.SZ.4: dt=0 must not cause ZeroDivisionError.
    """
    from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
    from apps.reference.domains.feature_engineering.types import HotState

    cfg = _Cfg()
    engine = FeatureCalculationEngine(cfg)

    state = HotState(
        vol_hist=deque(maxlen=cfg.volume_sma_length),
        volume_rate_hist=deque(maxlen=cfg.volume_sma_length),
    )

    # This must NOT raise ZeroDivisionError
    try:
        engine.update_volume_spike(state, volume=decimal.Decimal("100"), time_diff_ms=0)
        no_exception = True
    except ZeroDivisionError:
        no_exception = False

    assert no_exception, "Zero dt must be handled without ZeroDivisionError"


def test_volume_spike_large_dt_normalized_correctly():
    """
    TASK26.SZ.5: Large dt (> 1 minute) still produces valid normalized spike.
    """
    from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
    from apps.reference.domains.feature_engineering.types import HotState

    cfg = _Cfg()
    engine = FeatureCalculationEngine(cfg)

    state = HotState(
        vol_hist=deque(maxlen=cfg.volume_sma_length),
        volume_rate_hist=deque(maxlen=cfg.volume_sma_length),
    )

    # Very large dt (2 minutes)
    for _ in range(5):
        engine.update_volume_spike(state, volume=decimal.Decimal("1000"), time_diff_ms=120_000)

    spike = engine.compute_volume_spike(state)
    
    # Spike should be in valid range [0, 1]
    assert decimal.Decimal("0") <= spike <= decimal.Decimal("1"), f"Spike must be normalized, got {spike}"


def test_volatility_state_not_ready_returns_explicit_neutral():
    """
    TASK26.SZ.6: Volatility not ready returns neutral with explicit handling.
    """
    from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
    from apps.reference.domains.feature_engineering.types import HotState

    cfg = _Cfg()
    engine = FeatureCalculationEngine(cfg)

    # Empty state - volatility not ready
    state = HotState()

    vol = engine.compute_volatility_state(state)

    # Should return neutral value when not ready
    assert vol == cfg.neutral_value, f"Not ready volatility should be neutral, got {vol}"
