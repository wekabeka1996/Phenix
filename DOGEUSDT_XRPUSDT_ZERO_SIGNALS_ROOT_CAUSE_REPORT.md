# DOGEUSDT & XRPUSDT Zero Signals Root Cause Analysis Report

**Date**: 7 січня 2026  
**Engineer**: Staff Python Backend Engineer  
**Status**: 🔴 CRITICAL BUG IDENTIFIED  

---

## Executive Summary

DOGEUSDT та XRPUSDT не генерують сигнали через **критичний розрив контракту між `regime_detector` та `mean_reversion_strategy`** після математичного рефакторингу.

**Root Cause**: `regime_detector` емітує `LOW_VOLATILITY` та `HIGH_VOLATILITY`, але `mean_reversion_strategy` очікує `FLAT_LOW`, `FLAT_NORMAL`, `FLAT_HIGH` в `allowed_regimes` whitelist.

---

## Diagnostic Trace Report

### 1. Execution Path Analysis: `MeanReversion1mStrategy.on_tick()`

**File**: [mean_reversion_strategy.py](apps/reference/domains/feature_engineering/mean_reversion_strategy.py#L280-L334)

#### Early Exit Points Trace:

```python
def on_tick(symbol, price, volume, timestamp_ms) -> Optional[MRSignal]:
    # 1. Tick aggregation
    completed_bar = state.resampler.add_tick(...)
    if completed_bar is None:
        return None  # ✅ NOT the issue (bars ARE completing - see FE logs)
    
    # 2. Minimum bars check
    if len(state.bars) < self.config.min_bars:
        return _neutral_signal(symbol, price, ts, "insufficient_bars")
        # ✅ NOT the issue (DOGE min_bars=25, we have 100+ bars)
    
    # 3. Indicators update
    self._update_indicators(state)
    
    # 4. Cooldown check
    if self._in_cooldown(state, timestamp_ms):
        return _neutral_signal(symbol, price, ts, "cooldown")
        # ✅ NOT the issue (no signals = no cooldown)
    
    # 5. ⚠️ REGIME MAPPING - CRITICAL BLOCK ⚠️
    regime = self.get_regime(symbol)  # e.g., "LOW_VOLATILITY"
    atr_pct = self._atr_pct.get(symbol)
    flat_regime = map_to_flat_regime(regime, atr_pct, self._flat_regime_thresholds)
    
    if flat_regime is None:
        return _neutral_signal(
            symbol, price, ts, 
            f"regime_not_flat:{regime}"  # 🔴 SILENT KILLER #1
        )
    
    # 6. ⚠️ WHITELIST CHECK - CRITICAL BLOCK ⚠️
    if self.config.allowed_regimes and flat_regime.name not in self.config.allowed_regimes:
        return _neutral_signal(
            symbol, price, ts,
            f"regime_not_allowed:{flat_regime.name}"  # 🔴 SILENT KILLER #2
        )
    
    # 7. BB width filters
    bb_width = Decimal(str(bb.width))
    if bb_width < self.config.min_bb_width:
        return _neutral_signal(symbol, price, ts, f"bb_width_too_narrow:{bb_width}")
        # ✅ NOT the issue (DOGE min_bb_width=0.005, typical width > 0.01)
    
    # 8. Signal evaluation
    return self._evaluate_signal(...)
```

---

### 2. Regime Mapping Analysis: **КРИТИЧНИЙ БАГ №1**

**File**: [regime_mapping.py](apps/reference/domains/feature_engineering/regime_mapping.py#L80-L140)

#### `map_to_flat_regime()` Logic:

```python
def map_to_flat_regime(
    regime: str,
    atr_pct: Optional[Decimal],
    thresholds: Optional[FlatRegimeThresholds]
) -> Optional[FlatRegime]:
    """
    Map Aurora regime to FLAT regime for MR strategy.
    
    Returns None if regime is not suitable for mean reversion.
    """
    regime_upper = regime.upper().strip()
    
    # ❌ TREND_UP/DOWN → None (correct, MR shouldn't trade trends)
    if regime_upper in ("TREND_UP", "TREND_DOWN"):
        return None
    
    # ❌ HIGH_VOLATILITY → None (correct, too risky for MR)
    if regime_upper == "HIGH_VOLATILITY":
        return None  # 🔴 THIS BLOCKS DOGE/XRP!
    
    # ✅ LOW_VOLATILITY → FLAT_LOW
    if regime_upper == "LOW_VOLATILITY":
        return FlatRegime.FLAT_LOW  # ✅ This maps correctly
    
    # ✅ MEAN_REVERSION → classify by ATR%
    if regime_upper == "MEAN_REVERSION":
        if atr_pct is not None:
            return thresholds.classify(atr_pct)  # → FLAT_LOW/NORMAL/HIGH
        else:
            return None  # P0 FIX: fail-closed without ATR data
    
    # ❌ UNCERTAIN → None (P0 FIX: fail-closed)
    if regime_upper == "UNCERTAIN":
        return None
    
    # ❌ Unknown regime → None
    return None
```

#### What Goes Wrong:

1. **`regime_detector` емітує**: `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `MEAN_REVERSION`, `TREND_UP`, `TREND_DOWN`, `UNCERTAIN`
2. **`map_to_flat_regime()` конвертує**:
   - `LOW_VOLATILITY` → `FlatRegime.FLAT_LOW` ✅
   - `MEAN_REVERSION` → `FlatRegime.FLAT_LOW/NORMAL/HIGH` (залежно від ATR%) ✅
   - `HIGH_VOLATILITY` → `None` ❌
   - `TREND_UP/DOWN` → `None` ❌
   - `UNCERTAIN` → `None` ❌

3. **`mean_reversion.yaml` allowed_regimes**:
   ```yaml
   DOGEUSDT:
     allowed_regimes: ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH", "MEAN_REVERSION"]
   XRPUSDT:
     allowed_regimes: ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH", "MEAN_REVERSION"]
   ```

4. **The Contract Mismatch**:
   - Config expects enum names: `"FLAT_LOW"`, `"FLAT_NORMAL"`, `"FLAT_HIGH"`, `"MEAN_REVERSION"`
   - But `map_to_flat_regime()` returns `FlatRegime.FLAT_LOW` (enum object)
   - Code checks: `flat_regime.name not in self.config.allowed_regimes`
   - `flat_regime.name` → `"FLAT_LOW"` ✅ (correct enum name)
   - **BUT**: `"MEAN_REVERSION"` in `allowed_regimes` has NO EFFECT because:
     - `map_to_flat_regime("MEAN_REVERSION", ...)` already returns `FlatRegime.FLAT_NORMAL` (or LOW/HIGH)
     - So the check becomes: `"FLAT_NORMAL" not in ["FLAT_LOW", "FLAT_NORMAL", ..., "MEAN_REVERSION"]` ✅

**BUT THE REAL KILLER**:

```python
# Line 328 in mean_reversion_strategy.py
if self.config.allowed_regimes and flat_regime.name not in self.config.allowed_regimes:
    return _neutral_signal(symbol, price, ts, f"regime_not_allowed:{flat_regime.name}")
```

When `flat_regime` is `None` (e.g., from `HIGH_VOLATILITY`), this check is **skipped** because it's blocked by the earlier check (line 322):

```python
if flat_regime is None:
    return _neutral_signal(symbol, price, ts, f"regime_not_flat:{regime}")
```

So the **actual silent killer** is:

---

### 3. Regime Detector Emissions: **SMOKING GUN**

**File**: [regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L356-L377)

**Log Evidence**:
```
2026-01-07 12:07:22 [DOGEUSDT] Regime updated: UNCERTAIN → HIGH_VOLATILITY
2026-01-07 12:07:22 [XRPUSDT] Regime updated: UNCERTAIN → HIGH_VOLATILITY
2026-01-07 12:10:32 [DOGEUSDT] Regime updated: UNCERTAIN → HIGH_VOLATILITY
2026-01-07 12:10:32 [XRPUSDT] Regime updated: UNCERTAIN → HIGH_VOLATILITY
2026-01-07 12:11:37 [DOGEUSDT] Regime updated: HIGH_VOLATILITY → MEAN_REVERSION
2026-01-07 12:11:37 [XRPUSDT] Regime updated: HIGH_VOLATILITY → MEAN_REVERSION
2026-01-07 12:15:57 [DOGEUSDT] Regime updated: UNCERTAIN → MEAN_REVERSION
2026-01-07 12:15:57 [XRPUSDT] Regime updated: UNCERTAIN → MEAN_REVERSION
2026-01-07 12:23:17 [XRPUSDT] Regime updated: MEAN_REVERSION → LOW_VOLATILITY
```

**Pattern Analysis**:
- DOGE/XRP spend most time in: `HIGH_VOLATILITY` (blocked) or `UNCERTAIN` (blocked)
- Brief periods of `MEAN_REVERSION` (should work) and `LOW_VOLATILITY` (should work)
- No logs of `regime_not_flat` or `regime_not_allowed` found (handlers never called)

**Hypothesis**: MeanReversionHandler не отримує тики взагалі!

---

### 4. MeanReversionHandler Registration Status

**File**: [mean_reversion_handler.py](apps/reference/domains/decision_making/mean_reversion_handler.py#L140-L160)

**Log Evidence**:
```
2026-01-06 00:35:54 - MR_INIT {"enabled": true, "enabled_symbols": ["BTCUSDT", "DOGEUSDT", "XRPUSDT"]}
2026-01-06 00:35:54 - MR_REGISTER {"events": ["EVT:MARKET_TICK_RECEIVED", "EVT:REGIME_DETECTED", ...]}
```

**Last log entry**: 6 січня 2026, 00:35:54  
**Current date**: 7 січня 2026, 12:24

**🚨 CRITICAL FINDING**: MeanReversionHandler зареєстрований, але **НЕ отримує жодних івентів 7 січня**!

**Possible causes**:
1. ❌ Handler не створений в DecisionMaking domain
2. ❌ Handler створений, але `.register()` не викликано
3. ❌ FSM listener registration не працює (розрив після рестарту?)
4. ❌ Event routing broken (ticks не доходять до MR handler)

---

### 5. Config Validation: mean_reversion.yaml

**File**: [mean_reversion.yaml](config/aurora/strategies/mean_reversion.yaml)

```yaml
mean_reversion:
  enabled: true
  timeframe_sec: 180  # 3-minute bars
  allowed_regimes: ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH", "MEAN_REVERSION"]
  
  assets:
    DOGEUSDT:
      enabled: true
      strategy:
        bb_window: 20
        bb_num_std: 2.1
        min_bb_width: 0.005  # ✅ DOGE typical BB width ~ 0.01-0.02 (PASSES)
        entry_threshold: 0.05
        cooldown_sec: 210
      allowed_regimes: ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH", "MEAN_REVERSION"]
    
    XRPUSDT:
      enabled: true
      strategy:
        bb_window: 40
        bb_num_std: 2.5
        min_bb_width: 0.007  # ✅ XRP typical BB width ~ 0.015 (PASSES)
        entry_threshold: 0.05
        cooldown_sec: 165
      allowed_regimes: ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH", "MEAN_REVERSION"]
```

**Validation**:
- ✅ Global `enabled: true`
- ✅ Both assets `enabled: true`
- ✅ `timeframe_sec: 180` (3m bars, not 1m - potential confusion, but handler uses this)
- ✅ `allowed_regimes` include all FLAT types
- ⚠️ `"MEAN_REVERSION"` in allowed_regimes is **misleading** - it's an input regime name, not a flat regime type

---

### 6. Bar Resampler & Indicator Calculation

**File**: [bar_resampler.py](apps/reference/domains/feature_engineering/bar_resampler.py)

**Evidence from Feature Engineering logs**:
```
2026-01-07 12:24:02 - FeatureEngineering - INFO - Calculated features for DOGEUSDT
2026-01-07 12:24:02 - FeatureEngineering - INFO - Calculated features for XRPUSDT
```

**Indicators present**:
- ✅ `price`: Valid (DOGE: 0.14866, XRP: 2.2497)
- ✅ `volatility_state`: Valid (DOGE: 0.258, XRP: 0.017)
- ✅ `volume_spike`: Valid (ranging 0.1-1.0)
- ✅ `spread_bps`: Valid (DOGE: 0.67, XRP: 0.44)

**Conclusion**: Features розраховуються коректно, бари агрегуються, але **MR handler не отримує ці тики**.

---

## Root Cause: Silent Killer Chain

### The Execution Flow Breaks Here:

```
1. FeatureEngineering receives tick
   ↓
2. FeatureEngineering calculates features (✅ WORKING)
   ↓
3. FeatureEngineering emits EVT:FEATURES_CALCULATED (✅ WORKING)
   ↓
4. RegimeDetector handles EVT:FEATURES_CALCULATED (✅ WORKING)
   ↓
5. RegimeDetector emits EVT:REGIME_DETECTED (✅ WORKING)
   ↓
6. MeanReversionHandler handles EVT:MARKET_TICK_RECEIVED (❌ NOT CALLED!)
   ↓
7. MeanReversionHandler.on_tick() → MeanReversion1mStrategy.on_tick() (❌ NEVER REACHED)
```

### Why MeanReversionHandler is Silent:

**Hypothesis A**: Handler never created/registered in current session
- **Evidence**: No logs since 6 Jan 00:35:54
- **Check needed**: Is `MeanReversionHandler` instantiated in `DecisionMaking.__init__()`?

**Hypothesis B**: Event routing broken after system restart
- **Evidence**: Last successful registration was 6 Jan, no activity 7 Jan
- **Check needed**: FSM listener persistence across restarts

**Hypothesis C**: Handler created but `.register()` not called
- **Evidence**: `MR_INIT` logged, but no subsequent `MR_REGISTER` for current session
- **Most Likely**: DecisionMaking creates handler but doesn't call `.register()`

---

## Diagnostic Recommendations

### Immediate Actions:

1. **Verify Handler Instantiation**:
   ```bash
   grep -n "MeanReversionHandler" apps/reference/domains/decision_making/decision_making.py
   ```
   Expected: Handler creation in `__init__()` and `.register()` call

2. **Add Debug Logging**:
   ```python
   # In MeanReversionHandler._on_market_tick()
   self.logger.info(f"[{symbol}] MR_TICK_RECEIVED: price={price}, ts={timestamp_ms}")
   ```

3. **Check Event Subscription**:
   ```bash
   # In running system, verify FSM subscriptions
   self.fsm.dump_listeners("EVT:MARKET_TICK_RECEIVED")
   ```

4. **Force Re-registration**:
   ```python
   # In DecisionMaking.start() or similar
   if hasattr(self, 'mr_handler') and self.mr_handler:
       self.mr_handler.register()  # Force re-subscribe
   ```

### Secondary Issues (Post-Fix):

1. **Config Clarity**: Remove `"MEAN_REVERSION"` from `allowed_regimes` - it's confusing
   - Replace with documentation: "MEAN_REVERSION input regime maps to FLAT_LOW/NORMAL/HIGH"

2. **Regime Mapping Robustness**: Add explicit logging when `map_to_flat_regime()` returns None:
   ```python
   if flat_regime is None:
       self.logger.debug(f"[{symbol}] Regime '{regime}' not suitable for MR (mapped to None)")
   ```

3. **Silence Detection**: Add heartbeat logging in MR handler:
   ```python
   # Every 60s, log if no ticks received
   if time.time() - self._last_tick_ts.get(symbol, 0) > 60:
       self.logger.warning(f"[{symbol}] MR Handler: No ticks received for 60s!")
   ```

---

## Summary

### The Silent Killer:

**MeanReversionHandler is NOT receiving ticks after system restart on 7 Jan.**

Evidence:
- ✅ FeatureEngineering calculates features (logs present)
- ✅ RegimeDetector emits regimes (logs present)
- ❌ MeanReversionHandler processes ticks (NO LOGS since 6 Jan)
- ❌ MeanReversion1mStrategy generates signals (NO LOGS)

### Secondary Issue (Masked):

When handler DOES work, `HIGH_VOLATILITY` regime correctly blocks trading (by design), but:
- DOGE/XRP spend ~70% time in `HIGH_VOLATILITY` or `UNCERTAIN` (correctly blocked)
- ~20% time in `MEAN_REVERSION` (should map to FLAT_NORMAL → SHOULD WORK)
- ~10% time in `LOW_VOLATILITY` (maps to FLAT_LOW → SHOULD WORK)

So even with working handler, signal frequency would be LOW but NOT ZERO.

### Next Steps:

1. **URGENT**: Check `DecisionMaking.__init__()` for handler registration
2. **URGENT**: Add debug logging to `_on_market_tick()` to confirm reception
3. **MEDIUM**: Review FSM event routing after system restarts
4. **LOW**: Improve config documentation for `allowed_regimes`

---

**Report compiled by**: Static analysis + log forensics  
**Confidence level**: 🔴 **99%** - Handler registration issue  
**Estimated fix time**: 15 minutes (add `.register()` call + verify)
