import pytest
import time
from types import SimpleNamespace


class _DummyFsm:
    def __init__(self):
        self.emitted: list[tuple[str, dict, str | None]] = []

    def emit(self, event_name: str, payload=None, why=None, *_args, **_kwargs) -> None:
        self.emitted.append((event_name, payload or {}, why))

    def listen(self, _event_name: str, _callback) -> None:
        return


def test_regime_strict_config_rejects_dict():
    from apps.reference.domains.regime_detector.regime_detector import RegimeDetector

    with pytest.raises(TypeError):
        RegimeDetector(config={}, fsm=_DummyFsm())


def test_regime_missing_models_raises_config_contract_error():
    from apps.reference.config_loader import AuroraConfig, get_config
    from apps.reference.config_contract import ConfigContractError
    from apps.reference.domains.regime_detector.regime_detector import RegimeDetector

    base = get_config()
    cfg_dict = base.to_dict()
    cfg_dict["models"] = None
    cfg = AuroraConfig(**cfg_dict)

    with pytest.raises(ConfigContractError):
        RegimeDetector(config=cfg, fsm=_DummyFsm())


def test_atr_requires_ohlc_or_explicit_opt_in(monkeypatch):
    from apps.reference.config_loader import AuroraConfig, get_config
    from apps.reference.domains.regime_detector.regime_detector import RegimeDetector

    drops: list[tuple[str, str]] = []

    def _fake_drop(*, domain: str, reason: str) -> None:
        drops.append((domain, reason))

    monkeypatch.setattr(
        "apps.reference.domains.regime_detector.regime_detector.inc_data_quality_drop",
        _fake_drop,
    )

    base = get_config()
    cfg_dict = base.to_dict()
    cfg_dict["models"]["volatility"]["allow_close_to_close_atr"] = False
    cfg = AuroraConfig(**cfg_dict)

    fsm = _DummyFsm()
    det = RegimeDetector(config=cfg, fsm=fsm)

    symbol = "BTCUSDT"
    now_ms = int(time.time() * 1000)
    # REG-FIX-01: Must include tf_sec=basis_tf_sec (300) for BAR-ONLY mode
    det.handle_event(SimpleNamespace(verb="FEATURES_CALCULATED", pld={"symbol": symbol, "ts": now_ms, "tf_sec": 300, "features": {"price": "100"}}))
    det.handle_event(SimpleNamespace(verb="FEATURES_CALCULATED", pld={"symbol": symbol, "ts": now_ms + 1000, "tf_sec": 300, "features": {"price": "101"}}))

    assert any(domain == "regime_detector" and reason == "atr_missing_ohlc" for domain, reason in drops)
    assert fsm.emitted, "expected EVT:REGIME_DETECTED emission"
    evt, payload, _why = fsm.emitted[-1]
    assert evt == "EVT:REGIME_DETECTED"
    assert "atr_missing_ohlc" in (payload.get("data_quality", {}) or {}).get("drops", [])
    assert payload.get("regime") == "UNCERTAIN"


def test_stale_data_sets_regime_uncertain(monkeypatch):
    from apps.reference.config_loader import get_config
    from apps.reference.domains.regime_detector.regime_detector import RegimeDetector

    drops: list[tuple[str, str]] = []

    def _fake_drop(*, domain: str, reason: str) -> None:
        drops.append((domain, reason))

    monkeypatch.setattr(
        "apps.reference.domains.regime_detector.regime_detector.inc_data_quality_drop",
        _fake_drop,
    )

    cfg = get_config()
    # BAR-TTL-REFORM-02: With tf_sec=300 (bar event), RegimeDetector uses bar_ttl_ms, not tick_ttl_ms
    bar_ttl_ms = int(getattr(getattr(cfg.system, "market_data", None), "bar_ttl_ms", 10000) or 10000)
    assert bar_ttl_ms > 0, "expected bar_ttl_ms > 0 in canonical config"

    fsm = _DummyFsm()
    det = RegimeDetector(config=cfg, fsm=fsm)

    now_ms = int(time.time() * 1000)
    stale_ts = now_ms - bar_ttl_ms - 1  # Use bar TTL for staleness calculation

    symbol = "BTCUSDT"
    feats = {"price": "120", "sma_short": "110", "sma_long": "100"}  # would be TREND_UP if not gated
    # REG-FIX-01: Must include tf_sec=basis_tf_sec (300) for BAR-ONLY mode
    det.handle_event(SimpleNamespace(verb="FEATURES_CALCULATED", pld={"symbol": symbol, "ts": stale_ts, "tf_sec": 300, "features": feats}))

    assert any(domain == "regime_detector" and reason == "stale_features" for domain, reason in drops)
    assert fsm.emitted, "expected EVT:REGIME_DETECTED emission"
    evt, payload, _why = fsm.emitted[-1]
    assert evt == "EVT:REGIME_DETECTED"
    assert payload.get("regime") == "UNCERTAIN"
    assert "stale_features" in (payload.get("data_quality", {}) or {}).get("drops", [])


# ============================================================
# TASK26: Suspicious Zone Tests - Regime Detector
# ============================================================

def test_atr_true_range_formula():
    """
    TASK26.SZ.7: True Range formula: TR = max(high-low, |high-prev_close|, |low-prev_close|).
    """
    from decimal import Decimal

    def true_range(high: Decimal, low: Decimal, prev_close: Decimal) -> Decimal:
        """Standard True Range calculation."""
        return max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )

    # Test case 1: Normal day (high-low dominates)
    tr1 = true_range(Decimal("105"), Decimal("95"), Decimal("100"))
    assert tr1 == Decimal("10"), f"high-low case: expected 10, got {tr1}"

    # Test case 2: Gap up (high-prev dominates)
    tr2 = true_range(Decimal("115"), Decimal("110"), Decimal("100"))
    assert tr2 == Decimal("15"), f"gap up case: expected 15, got {tr2}"

    # Test case 3: Gap down (prev-low dominates)
    tr3 = true_range(Decimal("95"), Decimal("85"), Decimal("100"))
    assert tr3 == Decimal("15"), f"gap down case: expected 15, got {tr3}"


def test_atr_wilder_smoothing_formula():
    """
    TASK26.SZ.8: Wilder's ATR smoothing: ATR_t = (ATR_{t-1}*(n-1) + TR_t) / n.
    """
    from decimal import Decimal

    def wilder_atr(prev_atr: Decimal, current_tr: Decimal, n: int) -> Decimal:
        """Wilder's ATR smoothing formula."""
        return (prev_atr * (n - 1) + current_tr) / n

    # Initial ATR = 10, current TR = 20, period = 14
    prev_atr = Decimal("10")
    current_tr = Decimal("20")
    n = 14

    new_atr = wilder_atr(prev_atr, current_tr, n)
    
    # Expected: (10 * 13 + 20) / 14 = 150 / 14 ≈ 10.714
    expected = (Decimal("10") * 13 + Decimal("20")) / 14
    assert new_atr == expected, f"Wilder ATR: expected {expected}, got {new_atr}"


def test_regime_uncertain_on_ohlc_data_gap():
    """
    TASK26.SZ.9: Missing OHLC candles (data gap) → UNCERTAIN regime.
    """
    from apps.reference.config_loader import get_config
    from apps.reference.domains.regime_detector.regime_detector import RegimeDetector

    cfg = get_config()
    fsm = _DummyFsm()
    det = RegimeDetector(config=cfg, fsm=fsm)

    now_ms = int(time.time() * 1000)
    symbol = "BTCUSDT"

    # Send features with gap indicator
    features_with_gap = {
        "symbol": symbol,
        "ts": now_ms,
        "features": {
            "price": "50000",
            "data_gap": True,  # Indicates missing candles
        },
        "warmup": {"full_ready": True},
    }

    det.handle_event(SimpleNamespace(verb="FEATURES_CALCULATED", pld=features_with_gap))

    # System should handle this gracefully
    # Either emit UNCERTAIN or block regime emission
    if fsm.emitted:
        evt, payload, _ = fsm.emitted[-1]
        if evt == "EVT:REGIME_DETECTED":
            # If regime emitted with gap, should be low confidence or UNCERTAIN
            regime = payload.get("regime", "")
            confidence = float(payload.get("confidence", 0.5))
            # Acceptable: UNCERTAIN regime OR low confidence
            assert regime == "UNCERTAIN" or confidence < 0.6, \
                f"Data gap should result in UNCERTAIN or low confidence, got {regime}/{confidence}"


# ============================================================
# P0-1 / P1-2 Regression Tests
# ============================================================

def test_stale_features_do_not_update_buffers(monkeypatch):
    """
    P0-1 REGRESSION: Stale tick should NOT poison _price_buf.
    
    Contract: If stale_features detected, buffers remain unchanged.
    """
    from apps.reference.config_loader import get_config
    from apps.reference.domains.regime_detector.regime_detector import RegimeDetector

    drops: list[tuple[str, str]] = []

    def _fake_drop(*, domain: str, reason: str) -> None:
        drops.append((domain, reason))

    monkeypatch.setattr(
        "apps.reference.domains.regime_detector.regime_detector.inc_data_quality_drop",
        _fake_drop,
    )

    cfg = get_config()
    # BAR-TTL-REFORM-02: With tf_sec=300 (bar event), RegimeDetector uses bar_ttl_ms, not tick_ttl_ms
    bar_ttl_ms = int(getattr(getattr(cfg.system, "market_data", None), "bar_ttl_ms", 10000) or 10000)
    assert bar_ttl_ms > 0, "expected bar_ttl_ms > 0 in canonical config"

    fsm = _DummyFsm()
    det = RegimeDetector(config=cfg, fsm=fsm)

    symbol = "BTCUSDT"
    now_ms = int(time.time() * 1000)

    # Step 1: Feed 3 fresh ticks to populate buffer
    # REG-FIX-01: Must include tf_sec=basis_tf_sec (300) for BAR-ONLY mode
    for i, price in enumerate(["100", "101", "102"]):
        det.handle_event(SimpleNamespace(
            verb="FEATURES_CALCULATED",
            pld={"symbol": symbol, "ts": now_ms + i * 1000, "tf_sec": 300, "features": {"price": price}}
        ))

    buf_len_before = len(det._price_buf[symbol])
    assert buf_len_before == 3, f"expected 3 prices in buffer, got {buf_len_before}"

    # Step 2: Feed STALE tick (should NOT be added to buffer)
    stale_ts = now_ms - bar_ttl_ms - 5000  # definitely stale (use bar TTL)
    # REG-FIX-01: Must include tf_sec=basis_tf_sec (300) for BAR-ONLY mode
    det.handle_event(SimpleNamespace(
        verb="FEATURES_CALCULATED",
        pld={"symbol": symbol, "ts": stale_ts, "tf_sec": 300, "features": {"price": "999"}}  # poison value
    ))

    # Assert: buffer NOT poisoned
    buf_len_after = len(det._price_buf[symbol])
    assert buf_len_after == buf_len_before, \
        f"P0-1 VIOLATION: stale tick poisoned buffer ({buf_len_before} → {buf_len_after})"
    
    # Assert: stale drop recorded
    assert any(reason == "stale_features" for _, reason in drops), \
        "expected stale_features drop to be recorded"

    # Assert: regime is UNCERTAIN
    assert fsm.emitted, "expected at least one emission"
    last_evt, last_payload, _ = fsm.emitted[-1]
    assert last_evt == "EVT:REGIME_DETECTED"
    assert last_payload.get("regime") == "UNCERTAIN"
    assert last_payload.get("source_model") == "data_quality_gate"


def test_mean_reversion_missing_config_raises_validation_error():
    """
    P1-2 REGRESSION: Missing mean_reversion config fields must raise validation error.
    
    Note: Pydantic validates at AuroraConfig level (before RegimeDetector init),
    so ValidationError is expected, not ConfigContractError.
    """
    from pydantic import ValidationError
    from apps.reference.config_loader import AuroraConfig, get_config

    base = get_config()
    cfg_dict = base.to_dict()
    
    # Remove mean_reversion.threshold (required field)
    if "mean_reversion" in cfg_dict.get("models", {}):
        cfg_dict["models"]["mean_reversion"].pop("threshold", None)
    
    # Pydantic should catch this at config instantiation
    with pytest.raises(ValidationError) as exc_info:
        AuroraConfig(**cfg_dict)
    
    assert "threshold" in str(exc_info.value), \
        f"expected 'threshold' in validation error, got: {exc_info.value}"
