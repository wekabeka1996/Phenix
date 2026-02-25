# Testing - Feature Engineering Domain

**Last Updated:** 2026-01-27
**Test Status:** ✅ 100% Forensic Coverage (12 Files Audited)
**See:** `FORENSIC_CODE_AUDIT_FEATURE_ENGINEERING.md`

---

## Test Summary

```
pytest tests/domains/test_feature_engineering.py \
       tests/units/test_feature_math_basic.py \
       tests/units/test_features_payload_validation.py \
       tests/test_feature_engineering_domain_integration.py --tb=short -v

============================= test session starts ==============================
collected 8 items

tests/domains/test_feature_engineering.py::test_no_symbol_no_emit PASSED
tests/domains/test_feature_engineering.py::test_first_tick_only_stored PASSED
tests/domains/test_feature_engineering.py::test_calculate_and_emit_features_basic PASSED
tests/domains/test_feature_engineering.py::test_delta_price_suppressed_when_time_diff_large PASSED
tests/domains/test_feature_engineering.py::test_feature_engineering_consumes_tick_and_emits_features PASSED
tests/units/test_feature_math_basic.py::test_obi_tfi_basic PASSED
tests/units/test_features_payload_validation.py::test_symbol_upper_and_required_fields PASSED
tests/test_feature_engineering_domain_integration.py::...test_feature_engineering_uses_domains_config PASSED

============================== 8 passed in 0.38s ===============================
```

---

## Audited Files (Forensic Scope)

| File | Type | LOC (Approx) | Status |
|------|------|--------------|--------|
| `feature_engineering.py` | FSM | 1254 | ✅ Audited |
| `calculation_engine.py` | Logic | 800+ | ✅ Audited |
| `mean_reversion_strategy.py` | Strategy | 700+ | ⚠️ Zombie Logic |
| `bar_resampler.py` | Util | 400+ | ✅ Audited |
| `types.py` | Data | 800+ | ✅ Audited |
| `indicators.py` | Math | 300+ | ✅ Audited |
| ... and 6 others | - | - | ✅ Audited |

---

## Test Details

### 1. test_no_symbol_no_emit
**Purpose:** Verify that events without symbol are silently ignored.

```python
def test_no_symbol_no_emit(fsm, config):
    fe = FeatureEngineering(fsm=fsm, config=config)
    msg = Message(op="EVT", verb="MARKET_TICK_RECEIVED", 
                  src="test", dst="fe", pld={})
    fe.on_market_tick(msg)
    assert len(fsm.emitted) == 0
```

**Coverage:** Error handling, input validation

---

### 2. test_first_tick_only_stored
**Purpose:** First tick for a symbol is stored but doesn't emit features (need delta).

```python
def test_first_tick_only_stored(fsm, config):
    fe = FeatureEngineering(fsm=fsm, config=config)
    tick = make_tick()
    msg = Message(op="EVT", verb="MARKET_TICK_RECEIVED", 
                  src="test", dst="fe", pld=tick)
    fe.on_market_tick(msg)
    assert len(fsm.emitted) == 0  # No emission on first tick
```

**Coverage:** State initialization, first-tick handling

---

### 3. test_calculate_and_emit_features_basic
**Purpose:** Verify correct calculation of OBI, TFI, delta_price.

```python
def test_calculate_and_emit_features_basic(fsm, config):
    # Setup: two ticks with known values
    last = make_tick(ts=ts0, bid_size="10", ask_size="8", 
                     buy_volume="50", sell_volume="30")
    current = make_tick(ts=ts0+500, bid_size="12", ask_size="6",
                        buy_volume="60", sell_volume="20", price="50050.00")
    
    fe.last_tick_data["BTCUSDT"] = last
    fe.on_market_tick(msg)
    
    # Verify calculations
    features = fsm.emitted[0][1]["features"]
    assert float(features["obi"]) == pytest.approx(0.333, rel=1e-3)  # (12-6)/18
    assert float(features["tfi"]) == pytest.approx(0.5, rel=1e-6)    # (60-20)/80
    assert float(features["delta_price"]) == pytest.approx(50.0)     # 50050-50000
```

**Coverage:** Core feature calculation logic

---

### 4. test_delta_price_suppressed_when_time_diff_large
**Purpose:** Delta price is zeroed when time gap > 5 seconds.

```python
def test_delta_price_suppressed_when_time_diff_large(fsm, config):
    last = make_tick(ts=ts0, price="50000.00")
    current = make_tick(ts=ts0 + 5100, price="50050.00")  # 5.1s gap
    
    fe.last_tick_data["BTCUSDT"] = last
    fe.on_market_tick(msg)
    
    features = fsm.emitted[0][1]["features"]
    assert float(features["delta_price"]) == pytest.approx(0.0)  # Suppressed!
```

**Coverage:** Spike filtering, edge case handling

---

### 5. test_feature_engineering_consumes_tick_and_emits_features
**Purpose:** End-to-end flow: tick → features → emission.

**Coverage:** Full integration within domain

---

### 6. test_obi_tfi_basic
**Purpose:** Mathematical correctness of OBI/TFI formulas.

```python
def test_obi_tfi_basic():
    # Mock feature engineering calculation
    current_tick = {
        "bid_size": "100", "ask_size": "50",
        "buy_volume": "30", "sell_volume": "20"
    }
    
    obi, tfi = mock_fe._calculate_and_emit_features("BTCUSDT", current_tick, last_tick)
    
    assert obi > 0  # More bids → positive
    assert tfi > 0  # More buys → positive
```

**Coverage:** Core math formulas

---

### 7. test_symbol_upper_and_required_fields
**Purpose:** Payload validation against schema.

**Coverage:** Event contract compliance

---

### 8. test_feature_engineering_uses_domains_config
**Purpose:** Config loading from `domains.feature_engineering` path.

```python
def test_feature_engineering_uses_domains_config(self):
    config = AuroraConfig.from_yaml(...)
    domains = config.domains
    
    assert domains.feature_engineering.ema.period_short == 3
    assert domains.feature_engineering.ema.period_long == 7
    assert domains.feature_engineering.volume.sma_length == 5
    assert domains.feature_engineering.volume.window_sec == 60
    assert domains.feature_engineering.volatility.sma_length == 10
    assert domains.feature_engineering.liquidity.depth_half == 1000
```

**Coverage:** Configuration integration

---

## Test Fixtures

### FSMCoreMock
```python
class FSMCoreMock:
    def __init__(self):
        self.listeners = {}
        self.emitted = []

    def listen(self, event_name: str, callback):
        self.listeners.setdefault(event_name, []).append(callback)

    def emit(self, event_name: str, payload: dict, why: str = ""):
        self.emitted.append((event_name, payload, why))
```

### make_tick Helper
```python
def make_tick(
    ts=None,
    price="50000.00",
    bid_size="10",
    ask_size="8",
    buy_volume="50",
    sell_volume="30",
):
    if ts is None:
        ts = int(time.time() * 1000)
    return {
        "ts": ts,
        "symbol": "BTCUSDT",
        "price": decimal.Decimal(price),
        "bid_size": decimal.Decimal(bid_size),
        "ask_size": decimal.Decimal(ask_size),
        "buy_volume": decimal.Decimal(buy_volume),
        "sell_volume": decimal.Decimal(sell_volume),
    }
```

---

## Missing Test Coverage

### Phase 1 Features (Not Tested)
| Feature | Status | Priority |
|---------|--------|----------|
| `ema_bias` calculation | ❌ | P1 |
| `volume_spike` calculation | ❌ | P1 |
| `volatility_state` calculation | ❌ | P1 |
| `depth_imbalance` calculation | ❌ | P2 |
| `macro_sync` correlation | ❌ | P2 |

### Edge Cases (Not Tested)
- Zero depth / zero volume
- Negative values
- Very large values (overflow)
- Symbol with special characters
- Concurrent multi-symbol processing

### Integration Tests
- End-to-end with real `market_data` domain
- Feature store integration
- Performance under load

---

## Recommended Additional Tests

### 1. EMA Bias Test
```python
def test_ema_bias_calculation():
    fe = FeatureEngineering(fsm, {"trading": {"feature_engineering": {"enable_new_metrics": True}}})
    
    # Warm up EMA with stable price
    for _ in range(10):
        fe.on_market_tick(make_msg(price="50000"))
    
    # Price increase should make ema_bias > 0.5
    fe.on_market_tick(make_msg(price="50500"))
    features = fsm.emitted[-1][1]["features"]
    assert float(features["ema_bias"]) > 0.5
```

### 2. Volume Spike Test
```python
def test_volume_spike_detection():
    # Normal volume window
    for _ in range(5):
        fe.on_market_tick(make_msg(buy_volume="100", sell_volume="100"))
    
    # Spike window (3x normal)
    fe.on_market_tick(make_msg(buy_volume="300", sell_volume="300"))
    
    features = fsm.emitted[-1][1]["features"]
    assert float(features["volume_spike"]) > 0.9  # Near max (capped at 1.0)
```

### 3. Property-Based Test
```python
from hypothesis import given, strategies as st

@given(
    bid_size=st.floats(min_value=0, max_value=1e6),
    ask_size=st.floats(min_value=0, max_value=1e6)
)
def test_obi_always_in_range(bid_size, ask_size):
    depth = bid_size + ask_size
    if depth > 0:
        obi = (bid_size - ask_size) / depth
        assert -1 <= obi <= 1
```

---

## Running Tests

```bash
# Run all feature_engineering tests
pytest tests/ -k "feature_engineering" -v

# Run with coverage
pytest tests/domains/test_feature_engineering.py --cov=apps.reference.domains.feature_engineering --cov-report=term-missing

# Run specific test
pytest tests/domains/test_feature_engineering.py::test_calculate_and_emit_features_basic -v
```
