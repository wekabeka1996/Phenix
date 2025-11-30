# FTR-09: Investigation Report — Missing V2/Futures Features in Logs

**Date:** 2025-11-30  
**Author:** Debug Agent  
**Status:** Investigation Complete (No Code Changes Applied)

---

## 🎯 Summary

| Question | Answer |
|----------|--------|
| **Logging Mechanism filtering keys?** | ✅ **YES** — Manual f-string formatting excludes V2 keys |
| **Futures features disabled by config?** | ✅ **YES** — `futures.enabled: false` in `features.yaml` |
| **Why are V2 metrics missing from logs?** | Logger f-string, NOT calculation |
| **Are V2 features computed?** | ✅ **YES** — Added to `features` dict correctly |

---

## 1️⃣ Logging Mechanism Analysis

### Root Cause: Manual F-String Formatting

**File:** `apps/reference/domains/feature_engineering/feature_engineering.py`  
**Lines:** 438-441

```python
self.logger.info(
    f"Calculated features for {symbol}: OBI={obi:.6f}, TFI={tfi:.6f}, "
    f"delta_price={delta_price}, ema_bias={features.get('ema_bias', 'N/A')}, "
    f"volume_spike={features.get('volume_spike', 'N/A')}"
)
```

**Problem:** The log message explicitly lists only 5 features:
- `OBI` ✅
- `TFI` ✅  
- `delta_price` ✅
- `ema_bias` ✅
- `volume_spike` ✅

**Missing from log (but present in `features` dict):**
- `volume_zscore` ❌
- `large_trade_imbalance` ❌
- `spread_bps` ❌
- `volatility_state` ❌
- `depth_imbalance` ❌
- `macro_sync` ❌

### Evidence: V2 Features ARE Computed

Lines 403-413 in the same file correctly add V2 features to the dictionary:

```python
# V2 FEATURES (FTR-03: Additive)
features["volume_zscore"] = str(self._compute_volume_zscore(symbol))
features["large_trade_imbalance"] = str(self._compute_large_trade_imbalance(current_tick))
# ...
features["spread_bps"] = str(self._compute_spread_bps(best_bid, best_ask, mid_price))
```

**Conclusion:** V2 features are computed and added to `features_payload`, which is emitted via `EVT:FEATURES_CALCULATED`. The **only** issue is visibility in logs.

---

## 2️⃣ Configuration Status — Futures Features

### Config File Analysis

**File:** `config/aurora/features.yaml`  
**Lines:** 119-129

```yaml
futures:
  enabled: false    # <-- MASTER SWITCH IS OFF
  
  funding:
    extreme_threshold: 0.001
```

**Code Check** (`types.py`, lines 282-286):

```python
@property
def futures_enabled(self) -> bool:
    try:
        return getattr(self._cfg, 'futures', None) is not None and self._cfg.futures.enabled
    except AttributeError:
        return False
```

### Result

| Feature | Status | Reason |
|---------|--------|--------|
| `funding_rate_normalized` | ❌ Not computed | `futures.enabled = false` |
| `oi_delta_pct` | ❌ Not computed | `futures.enabled = false` |

**Startup Log Confirms:**
```
INFO - FeatureEngineering initialized: new_metrics=True, ema=3/7, macro_sync=True, futures=False
```

---

## 3️⃣ Data Flow Verification — V2 Features

### Calculation Engine Methods

All V2 methods are correctly implemented in `calculation_engine.py`:

| Method | Lines | Status |
|--------|-------|--------|
| `compute_volume_zscore` | 152-169 | ✅ Implemented (Welford + tanh) |
| `compute_spread_bps` | 241-265 | ✅ Implemented (basis points) |
| `compute_large_trade_imbalance` | 267-306 | ✅ Implemented (avg trade size) |

### No Silent Exceptions

The main try/except in `_calculate_and_emit_features` (lines 320-459) logs all errors:

```python
except Exception as e:
    self.logger.error(f"Error calculating features for {symbol}: {e}")
    import traceback
    self.logger.debug(f"Traceback: {traceback.format_exc()}")
```

**No silent failures detected.**

---

## 4️⃣ Proposed Fix Plan

### Fix 1: Update Logger F-String (Immediate)

**File:** `apps/reference/domains/feature_engineering/feature_engineering.py`  
**Line:** 438-441

**Current:**
```python
self.logger.info(
    f"Calculated features for {symbol}: OBI={obi:.6f}, TFI={tfi:.6f}, "
    f"delta_price={delta_price}, ema_bias={features.get('ema_bias', 'N/A')}, "
    f"volume_spike={features.get('volume_spike', 'N/A')}"
)
```

**Proposed (Option A — Add V2 Features):**
```python
self.logger.info(
    f"Calculated features for {symbol}: OBI={obi:.6f}, TFI={tfi:.6f}, "
    f"delta_price={delta_price}, ema_bias={features.get('ema_bias', 'N/A')}, "
    f"volume_spike={features.get('volume_spike', 'N/A')}, "
    f"volume_zscore={features.get('volume_zscore', 'N/A')}, "
    f"spread_bps={features.get('spread_bps', 'N/A')}"
)
```

**Proposed (Option B — Log All Features as JSON):**
```python
import json
self.logger.info(f"Calculated features for {symbol}: {json.dumps(features, default=str)}")
```

**Recommendation:** Option B is more maintainable — no manual updates when adding new features.

### Fix 2: Enable Futures Features (Optional)

**File:** `config/aurora/features.yaml`  
**Line:** 120

**Change:**
```yaml
futures:
  enabled: true   # Was: false
```

**Note:** This also requires:
1. Data source emitting `EVT:FUNDING_UPDATE` and `EVT:OI_UPDATE` events
2. Exchange API supporting futures data endpoints

---

## 5️⃣ Verification Steps (Post-Fix)

After applying fixes:

1. **Check logs for V2 features:**
   ```bash
   grep "volume_zscore\|spread_bps" logs/domain_feature_engineering.log
   ```

2. **Check EVT:FEATURES_CALCULATED payload:**
   ```bash
   grep "EVT:FEATURES_CALCULATED" logs/event_chain.log | head -5 | jq '.payload.features'
   ```

3. **Run unit tests:**
   ```bash
   pytest apps/reference/domains/feature_engineering/tests/ -v
   ```

---

## 📋 Appendix: File Locations

| Component | Path |
|-----------|------|
| Main Handler | `apps/reference/domains/feature_engineering/feature_engineering.py` |
| Calculation Engine | `apps/reference/domains/feature_engineering/calculation_engine.py` |
| Types/Config | `apps/reference/domains/feature_engineering/types.py` |
| Config YAML | `config/aurora/features.yaml` |
| Log Output | `logs/domain_feature_engineering.log` |

---

**Action Required:** Apply Fix 1 (logging) to restore visibility. Fix 2 is optional based on deployment target (spot vs futures).
