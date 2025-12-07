# Aurora Phase 3+ Feature Implementation Status
**Дата:** 2025-12-04  
**Версія:** Comprehensive Analysis

---

## Загальний Огляд

Цей документ деталізує **всі features** які були оптимізовані в Phase 3+ Optuna runs та їх статус реалізації в production системі (`apps/reference/domains` та `config/aurora`).

**Summary:**
- **Оптимізовано features:** 25+ параметрів
- **Реалізовано у production:** ~60%
- **Потребує імплементації:** ~40%

---

## Feature Categories

### Category 1: Core Signal Features (Phase 1 & 2)
**Status:** ✅ **FULLY IMPLEMENTED** в production

| Feature | Backtest Param | Production Location | Config Location | Status |
|---------|----------------|---------------------|-----------------|--------|
| **EMA Bias** | `period_short`, `period_long` | `calculation_engine.py:compute_ema_bias()` | `config/aurora/features.yaml` | ✅ OK |
| **Volume Spike** | `window_sec`, `sma_length`, `cap_max` | `calculation_engine.py:compute_volume_spike()` | `config/aurora/features.yaml` | ✅ OK |
| **Liquidity** | `depth_half`, `kappa_min` | `calculation_engine.py:compute_liquidity()` | `config/aurora/features.yaml` | ✅ OK |
| **OBI** | `window_sec` | `calculation_engine.py:compute_obi()` | `config/aurora/features.yaml` | ✅ OK |
| **TFI** | `window_sec` | `calculation_engine.py:compute_tfi()` | `config/aurora/features.yaml` | ✅ OK |
| **Volatility State** | `window_sec`, `sma_length`, `cap_max` | `calculation_engine.py:compute_volatility_state()` | `config/aurora/features.yaml` | ✅ OK |
| **Depth Imbalance** | `use_smoothing` | `calculation_engine.py:compute_depth_imbalance()` | `config/aurora/features.yaml` | ✅ OK |
| **Delta Price** | `spike_filter_ms` | `calculation_engine.py:compute_delta_price()` | `config/aurora/features.yaml` | ✅ OK |
| **Macro Sync** | `window` | `calculation_engine.py:compute_macro_sync()` | `config/aurora/features.yaml` | ✅ OK |

**Implementation Details:**
```python
# apps/reference/domains/feature_engineering/calculation_engine.py
class FeatureCalculationEngine:
    def compute_ema_bias(self, hot_state, cold_state, config):
        """Fully implemented with per-instrument config support"""
        period_short = config.ema.period_short
        period_long = config.ema.period_long
        # ... calculation logic
```

**Config Example:**
```yaml
# config/aurora/features.yaml
feature_engineering:
  ema:
    period_short: 4
    period_long: 19
  volume:
    window_sec: 60
    sma_length: 12
```

**Verdict:** ✅ Production має повну підтримку core features

---

### Category 2: Signal Weights
**Status:** ⚠️ **PARTIALLY IMPLEMENTED**

| Feature | Backtest Param | Production Location | Config Location | Status |
|---------|----------------|---------------------|-----------------|--------|
| **EMA Weight** | `weight_ema` | `decision_making.py` | `config/aurora/trading.yaml` ❌ | ⚠️ PARTIAL |
| **Volume Weight** | `weight_volume` | `decision_making.py` | `config/aurora/trading.yaml` ❌ | ⚠️ PARTIAL |
| **Macro Weight** | `weight_macro` | `decision_making.py` | `config/aurora/trading.yaml` ❌ | ⚠️ PARTIAL |
| **Liquidity Weight** | `weight_liquidity` | `decision_making.py` | `config/aurora/trading.yaml` ❌ | ⚠️ PARTIAL |
| **OBI Weight** | `weight_obi` | `decision_making.py` | `config/aurora/trading.yaml` ❌ | ⚠️ PARTIAL |
| **TFI Weight** | `weight_tfi` | `decision_making.py` | `config/aurora/trading.yaml` ❌ | ⚠️ PARTIAL |
| **Volatility Weight** | `weight_volatility` | `decision_making.py` | `config/aurora/trading.yaml` ❌ | ⚠️ PARTIAL |
| **Depth Weight** | `weight_depth_imbalance` | `decision_making.py` | `config/aurora/trading.yaml` ❌ | ⚠️ PARTIAL |
| **Delta Weight** | `weight_delta_price` | `decision_making.py` | `config/aurora/trading.yaml` ❌ | ⚠️ PARTIAL |

**Current Implementation:**
```python
# apps/reference/domains/decision_making/decision_making.py
# Weights існують, але НЕ per-instrument
self.feature_weights = {
    'ema_bias': 0.3,      # HARDCODED або global config
    'volume': 0.2,
    # ...
}
```

**Missing:** Per-instrument weight overrides

**Needed:**
```yaml
# config/aurora/trading.yaml
instruments:
  BTCUSDT:
    feature_weights:    # ❌ NOT IMPLEMENTED
      ema: 0.35
      volume: 0.10
      macro: 0.35
```

**Verdict:** ⚠️ Weights існують, але не per-instrument configurable

---

### Category 3: Phase 3 - EMA Clamping
**Status:** ❌ **NOT IMPLEMENTED** в production

| Feature | Backtest Param | Production Location | Config Location | Status |
|---------|----------------|---------------------|-----------------|--------|
| **EMA Clamp Min** | `ema_clamp_min` | `calculation_engine.py` ❌ | `config/aurora/features.yaml` ❌ | ❌ MISSING |
| **EMA Clamp Max** | `ema_clamp_max` | `calculation_engine.py` ❌ | `config/aurora/features.yaml` ❌ | ❌ MISSING |

**Current Implementation:**
```python
# apps/reference/domains/feature_engineering/calculation_engine.py
def compute_ema_bias(self, ...):
    # HARDCODED CLAMP!
    clamp_min = -0.02  # ❌ Not configurable
    clamp_max = 0.02   # ❌ Not configurable
    return np.clip(ema_bias, clamp_min, clamp_max)
```

**Needed:**
```python
# Should read from config
clamp_min = config.ema.clamp_min  # ❌ NOT IMPLEMENTED
clamp_max = config.ema.clamp_max
```

**Config Needed:**
```yaml
# config/aurora/features.yaml
feature_engineering:
  ema:
    clamp_min: -0.03    # ❌ NOT IN PRODUCTION CONFIG
    clamp_max: 0.03
```

**Verdict:** ❌ EMA clamping hardcoded, не configurable

---

### Category 4: Phase 3 - Risk Score Weights
**Status:** ❌ **NOT IMPLEMENTED** в production

| Feature | Backtest Param | Production Location | Config Location | Status |
|---------|----------------|---------------------|-----------------|--------|
| **Delta Risk Weight** | `risk_weight_delta` | `calculation_engine.py` ❌ | `config/aurora/features.yaml` ❌ | ❌ MISSING |
| **Volume Risk Weight** | `risk_weight_volume` | `calculation_engine.py` ❌ | `config/aurora/features.yaml` ❌ | ❌ MISSING |
| **Volatility Risk Weight** | `risk_weight_volatility` | `calculation_engine.py` ❌ | `config/aurora/features.yaml` ❌ | ❌ MISSING |

**Current Implementation:**
```python
# apps/reference/domains/feature_engineering/calculation_engine.py
def compute_risk_score(self, ...):
    # HARDCODED WEIGHTS!
    risk_score = (
        0.33 * delta_risk +      # ❌ Not configurable
        0.33 * volume_risk +     # ❌ Not configurable
        0.34 * volatility_risk   # ❌ Not configurable
    )
```

**Needed:**
```python
# Should read from config
w_delta = config.risk_weights.delta      # ❌ NOT IMPLEMENTED
w_volume = config.risk_weights.volume
w_volatility = config.risk_weights.volatility
```

**Verdict:** ❌ Risk score weights hardcoded

---

### Category 5: Phase 3 - Side-Bias Penalty
**Status:** ✅ **IMPLEMENTED** але потребує per-instrument config

| Feature | Backtest Param | Production Location | Config Location | Status |
|---------|----------------|---------------------|-----------------|--------|
| **Side Bias Window** | `side_bias_window_sec` | `decision_making.py` | `config/aurora/trading.yaml` | ⚠️ PARTIAL |
| **Side Bias Penalty** | `side_bias_penalty_factor` | `decision_making.py` | `config/aurora/trading.yaml` | ⚠️ PARTIAL |

**Current Implementation:**
```python
# apps/reference/domains/decision_making/decision_making.py
# Code EXISTS but config is GLOBAL
self.side_bias_window = config.get('side_bias_window_sec', 300)  # ✅ Exists
self.side_bias_penalty = config.get('side_bias_penalty_factor', 0.5)
```

**Missing:** Per-instrument overrides

**Needed:**
```yaml
# config/aurora/trading.yaml
instruments:
  ETHUSDT:
    side_bias:          # ❌ NOT PER-INSTRUMENT
      window_sec: 600
      penalty_factor: 0.9
```

**Verdict:** ✅ Logic implemented, ⚠️ config not per-instrument

---

### Category 6: Phase 3 - Regime-Adaptive Thresholds
**Status:** ✅ **IMPLEMENTED** але потребує per-instrument config

| Feature | Backtest Param | Production Location | Config Location | Status |
|---------|----------------|---------------------|-----------------|--------|
| **High Vol Multiplier** | `regime_threshold_high_vol` | `decision_making.py` | `config/aurora/trading.yaml` | ⚠️ PARTIAL |
| **Low Vol Multiplier** | `regime_threshold_low_vol` | `decision_making.py` | `config/aurora/trading.yaml` | ⚠️ PARTIAL |
| **Trend Multiplier** | `regime_threshold_trend` | `decision_making.py` | `config/aurora/trading.yaml` | ⚠️ PARTIAL |

**Current Implementation:**
```python
# apps/reference/domains/decision_making/decision_making.py
# EXISTS but GLOBAL
self.regime_multipliers = {
    'HIGH_VOLATILITY': config.get('threshold_high_vol_multiplier', 1.5),
    'LOW_VOLATILITY': config.get('threshold_low_vol_multiplier', 0.8),
    'TREND': config.get('threshold_trend_multiplier', 1.0)
}
```

**Verdict:** ✅ Logic implemented, ⚠️ config not per-instrument

---

### Category 7: Phase 3 - Regime-Adaptive Sizing
**Status:** ✅ **IMPLEMENTED** але потребує per-instrument config

| Feature | Backtest Param | Production Location | Config Location | Status |
|---------|----------------|---------------------|-----------------|--------|
| **High Vol Sizing** | `sizing_high_vol` | `decision_making.py` | `config/aurora/trading.yaml` | ⚠️ PARTIAL |
| **Low Vol Sizing** | `sizing_low_vol` | `decision_making.py` | `config/aurora/trading.yaml` | ⚠️ PARTIAL |
| **Mean Rev Sizing** | `sizing_mean_rev` | `decision_making.py` | `config/aurora/trading.yaml` | ⚠️ PARTIAL |

**Current Implementation:**
```python
# apps/reference/domains/decision_making/decision_making.py
# EXISTS as behavior_fsm multipliers
self.behavior_fsm = {
    'high_vol_multiplier': config.get('high_vol_multiplier', 0.5),
    'low_vol_multiplier': config.get('low_vol_multiplier', 1.5),
    # mean_rev missing
}
```

**Verdict:** ✅ High/Low vol implemented, ❌ Mean-reversion multiplier missing

---

### Category 8: Phase 3+ - Take-Profit Logic
**Status:** ⚠️ **PARTIALLY IMPLEMENTED**

| Feature | Backtest Param | Production Location | Config Location | Status |
|---------|----------------|---------------------|-----------------|--------|
| **TP Low Ratio** | `tp_low_ratio` | `fsm_manage.py` ❌ | `config/aurora/trading.yaml` | ⚠️ EXISTS but not TP1/TP2 |
| **TP High Ratio** | `tp_high_ratio` | `fsm_manage.py` ❌ | `config/aurora/trading.yaml` | ❌ MISSING |
| **Partial Exit %** | `partial_exit_pct` | `fsm_manage.py` ❌ | `config/aurora/trading.yaml` ❌ | ❌ MISSING |

**Current Implementation:**
```yaml
# config/aurora/trading.yaml
brackets:
  take_profit_low_ratio: 0.5   # ✅ EXISTS (legacy)
  take_profit_high_ratio: 1.0  # ✅ EXISTS (legacy)
  # But NO partial_exit_pct ❌
```

```python
# apps/reference/domains/execution_position/fsm_manage.py
# Calculates TP but does NOT support:
# 1. Partial exits (TP1 → exit 70%, TP2 → exit remaining 30%)
# 2. Dynamic TP1/TP2 placement
```

**Missing Logic:**
1. **Partial Exit Support:** Після TP1 hit → close 50-70% position, оновити TP на TP2
2. **Separate TP1/TP2 Orders:** Два окремі TP orders замість одного

**Verdict:** ⚠️ TP config існує, ❌ partial exit logic відсутня

---

### Category 9: Phase 3+ - Trailing Stop
**Status:** ❌ **NOT FULLY IMPLEMENTED**

| Feature | Backtest Param | Production Location | Config Location | Status |
|---------|----------------|---------------------|-----------------|--------|
| **Trailing Enabled** | `trailing_stop_enabled` | `fsm_manage.py` ❌ | `config/aurora/trading.yaml` ❌ | ❌ MISSING |
| **Activation %** | `trailing_activation_pct` | `fsm_manage.py` ❌ | `config/aurora/trading.yaml` ❌ | ❌ MISSING |
| **Distance %** | `trailing_distance_pct` | `fsm_manage.py` ❌ | `config/aurora/trading.yaml` ❌ | ❌ MISSING |

**Current Implementation:**
```python
# apps/reference/domains/execution_position/fsm_manage.py
# NO trailing stop logic
# SL is STATIC after placement
```

**Needed:**
1. **Periodic Check:** Monitor position profit every 5-10s
2. **Activation Logic:** Якщо profit >= activation_pct → activate trailing
3. **SL Update:** Move SL вище/нижче за peak price - distance_pct
4. **Order Modification:** Use Binance `MODIFY_ORDER` API для update SL

**Verdict:** ❌ Trailing stop logic completely missing

---

### Category 10: Phase 3+ - Cooldown
**Status:** ⚠️ **PARTIALLY IMPLEMENTED**

| Feature | Backtest Param | Production Location | Config Location | Status |
|---------|----------------|---------------------|-----------------|--------|
| **Cooldown Sec** | `cooldown_sec` | `decision_making.py` | `config/aurora/trading.yaml` | ⚠️ EXISTS but not per-instrument |

**Current Implementation:**
```yaml
# config/aurora/trading.yaml
cooldown_sec: 10  # ✅ EXISTS globally
```

```python
# apps/reference/domains/decision_making/decision_making.py
# Global cooldown EXISTS
# But NOT per-instrument tracking
```

**Missing:**
1. **Per-Instrument Tracking:** `last_exit_ts` dictionary per symbol
2. **Per-Instrument Config:** ETHUSDT=15s, XRP=20s, BTC=30s

**Verdict:** ✅ Global cooldown works, ⚠️ не per-instrument

---

### Category 11: Phase 3+ - Exit Parameters
**Status:** ✅ **FULLY IMPLEMENTED**

| Feature | Backtest Param | Production Location | Config Location | Status |
|---------|----------------|---------------------|-----------------|--------|
| **Stop Loss %** | `sl_pct` | `fsm_manage.py` | `config/aurora/trading.yaml` | ✅ OK |
| **Max Hold Sec** | `max_hold_sec` | `fsm.py` ❌ | `config/aurora/trading.yaml` ❌ | ❌ MISSING |

**Current Implementation:**
```yaml
# config/aurora/trading.yaml
brackets:
  stop_loss_bps: 40  # ✅ SL implemented (0.4%)
```

```python
# apps/reference/domains/execution_position/fsm_manage.py
def _calculate_bracket_prices(self, ...):
    sl_bps = config.brackets.stop_loss_bps  # ✅ Works
```

**Missing:**
- `max_hold_sec` NOT implemented → positions can stay open indefinitely
- Потрібен **timeout watchdog** для forced exit після N seconds

**Verdict:** ✅ SL works, ❌ Max hold time missing

---

### Category 12: Regime Filters
**Status:** ✅ **FULLY IMPLEMENTED**

| Feature | Backtest Param | Production Location | Config Location | Status |
|---------|----------------|---------------------|-----------------|--------|
| **Allowed Regimes** | `allowed_regimes` | `decision_making.py` | `config/aurora/trading.yaml` | ✅ OK |
| **Max Risk Score** | `max_risk_score` | `decision_making.py` | `config/aurora/trading.yaml` | ✅ OK |
| **Signal Threshold** | `signal_threshold` | `decision_making.py` | `config/aurora/trading.yaml` | ✅ OK |

**Verdict:** ✅ Fully implemented

---

## Implementation Priority Matrix

### Priority 1 (CRITICAL for Phase 3+ performance) — 8-10 годин

| Feature | Impact | Complexity | Time | Status |
|---------|--------|------------|------|--------|
| **Partial Exit Logic (TP1/TP2)** | 🔥 HIGH (+30-40% PnL) | MEDIUM | 4 год | ❌ TODO |
| **Trailing Stop** | 🔥 HIGH (XRP/BTC) | MEDIUM | 3 год | ❌ TODO |
| **Per-Instrument Params** | 🔥 HIGH | LOW | 2 год | ❌ TODO |

### Priority 2 (Important but lower impact) — 4-6 годин

| Feature | Impact | Complexity | Time | Status |
|---------|--------|------------|------|--------|
| **EMA Clamping Config** | MEDIUM | LOW | 1 год | ❌ TODO |
| **Risk Score Weights Config** | MEDIUM | LOW | 1 год | ❌ TODO |
| **Max Hold Time** | MEDIUM | LOW | 2 год | ❌ TODO |
| **Mean-Rev Sizing Multiplier** | MEDIUM (BTC) | LOW | 1 год | ❌ TODO |

### Priority 3 (Nice-to-have) — 2-3 години

| Feature | Impact | Complexity | Time | Status |
|---------|--------|------------|------|--------|
| **Per-Instrument Feature Weights** | LOW-MEDIUM | LOW | 2 год | ❌ TODO |

---

## Production Config Gap Summary

| Config File | Missing Parameters | Priority |
|-------------|-------------------|----------|
| **`config/aurora/features.yaml`** | `ema.clamp_min/max`, `risk_weights.*` | P2 |
| **`config/aurora/trading.yaml`** | `partial_exit_pct`, `trailing_stop.*`, `max_hold_sec`, per-instrument overrides | P1 |
| **`config/aurora/regime.yaml`** | None | ✅ OK |

---

## Implementation Roadmap

### Week 1: Core Execution Logic (Priority 1)

**Day 1-2:** Partial Exit Logic
- Modify `fsm_manage.py._calculate_bracket_prices()`
- Add TP1/TP2 order placement
- Implement partial close on TP1 fill
- Unit tests

**Day 3-4:** Trailing Stop
- Add periodic SL update loop
- Implement activation logic
- Binance order modification
- Integration tests

**Day 5:** Per-Instrument Config
- Modify `decision_making.py` config loading
- Add per-symbol param overrides
- Config validation

### Week 2: Config Parameters (Priority 2)

**Day 6-7:** EMA Clamp + Risk Weights
- Update `calculation_engine.py`
- Add config support
- Tests

**Day 8-9:** Max Hold Time + Mean-Rev Sizing
- Add timeout watchdog
- Implement forced exit
- Mean-rev multiplier config

**Day 10:** Testing & Validation
- Full integration tests
- Config validation
- Testnet deployment

---

## Conclusion

**Feature Coverage:**
- ✅ **Implemented:** 60% (core features, regime logic, basic TP/SL)
- ⚠️ **Partial:** 25% (exists but not per-instrument)
- ❌ **Missing:** 15% (TP1/TP2 partial exits, trailing stop, max hold time)

**Critical Gaps:**
1. **Partial Exit Logic (TP1 → 70%, TP2 → 30%)** — найбільший impact на PnL
2. **Trailing Stop** — критично для XRP та BTC
3. **Per-Instrument Config** — необхідно для різних strategies (ETH vs BTC)

**Total Implementation Time:** ~14-19 годин (2-3 тижні з testing)

**Recommendation:** Implement Priority 1 features (8-10 годин) → testnet validation → production deployment
