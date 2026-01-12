# REG-FORENSIC-02: Regime Labels Audit

**Date:** 2026-01-12  
**Status:** COMPLETED ✅  
**Priority:** P0

---

# REG-FIX-01: BAR-ONLY SSOT Implementation

**Status:** COMPLETED ✅

## Changes Made

### Phase 1: Forensic (COMPLETED)
- Identified all regime labels in code
- Found missing Pydantic fields (basis_tf_sec, uncertain_cutoff)
- Located double-clocking issue (no tf_sec filter)

### Phase 2: Implementation (COMPLETED)

#### 1. Pydantic Config (config_models.py)
Added required fields to `AuroraConfig`:
```python
basis_tf_sec: int = Field(...)  # REQUIRED, no default
uncertain_cutoff: float = Field(ge=0.0, le=1.0, ...)  # REQUIRED, no default
```

#### 2. BAR-ONLY Filter (regime_detector.py)
```python
# REG-FIX-01: BAR-ONLY filter - ignore non-basis timeframes
tf_sec = pld.get("tf_sec")
if tf_sec != self._basis_tf_sec:
    return  # Ignore tick-level and non-basis bars
```

#### 3. Clock Migration (regime_detector.py)
- Removed `import time`
- Added `from apps.reference.core.time.clock import Clock, LiveClock`
- `__init__` accepts `clock: Optional[Clock] = None`
- `now_ms = self._clock.now_ms()` instead of `int(time.time() * 1000)`

#### 4. Uncertain Cutoff (regime_detector.py)
```python
# Demote low-confidence regimes to UNCERTAIN
if regime != "UNCERTAIN" and float(confidence) < self._uncertain_cutoff:
    regime = "UNCERTAIN"
    source_model = "uncertain_cutoff_gate"
```

### Phase 3: Tests (COMPLETED)

Created `tests/domains/regime_detector/test_reg_fix_01_bar_only.py`:

| Test | Description | Status |
|------|-------------|--------|
| `test_regime_updates_only_on_basis_bar` | tf_sec=0 ignored, tf_sec=300 processed | ✅ |
| `test_no_double_clocking_at_bar_close` | One emission per bar | ✅ |
| `test_different_tf_sec_ignored` | Non-basis tf_sec ignored | ✅ |
| `test_uncertain_cutoff_demotes_low_confidence_trend` | Low confidence → UNCERTAIN | ✅ |
| `test_missing_basis_tf_sec_fails_config_load` | Required field validated | ✅ |
| `test_uses_injected_clock` | Clock DI works | ✅ |
| `test_no_time_module_in_regime_detector` | No time.time() in code | ✅ |

---

## 1. Regime Labels SSOT

### 1.1 Canonical Enum (SSOT)
**File:** [apps/reference/core/types/regime_types.py](apps/reference/core/types/regime_types.py#L1-L35)

```python
class RegimeLabel(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    MEAN_REVERSION = "MEAN_REVERSION"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    UNCERTAIN = "UNCERTAIN"
```

### 1.2 Execution Buckets (Simplified)
**File:** [apps/reference/core/types/regime_types.py](apps/reference/core/types/regime_types.py#L13-L35)

```python
class ExecutionRegimeBucket(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    FLAT = "FLAT"           # Maps MEAN_REVERSION, LOW_VOLATILITY
    UNCERTAIN = "UNCERTAIN"
```

### 1.3 FlatRegime (MR Strategy)
**File:** [apps/reference/domains/feature_engineering/regime_mapping.py](apps/reference/domains/feature_engineering/regime_mapping.py#L32-L36)

```python
class FlatRegime(Enum):
    FLAT_LOW = auto()      # Low volatility - tight stops
    FLAT_NORMAL = auto()   # Normal volatility - standard MR
    FLAT_HIGH = auto()     # High volatility - wider stops
```

## 2. Regime Detection Logic

### 2.1 RegimeDetector Output Labels
**File:** [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L322-L378)

| Priority | Condition | Output Label | Model |
|----------|-----------|--------------|-------|
| 1 | vol_ratio > threshold_multiplier | `HIGH_VOLATILITY` | volatility_v2 |
| 1 | vol_ratio < low_vol_multiplier | `LOW_VOLATILITY` | volatility_v2 |
| 2 | SMA spread + price deviation < threshold | `MEAN_REVERSION` | mean_reversion_v2 |
| 3 | sma_short > sma_long AND price > sma_short | `TREND_UP` | sma_trend_v1 |
| 3 | sma_short < sma_long AND price < sma_short | `TREND_DOWN` | sma_trend_v1 |
| fallback | data_quality issues OR no match | `UNCERTAIN` | data_quality_gate |

### 2.2 Label→Policy Mapping

| Label | Bucket | MR Strategy | Allowed? |
|-------|--------|-------------|----------|
| TREND_UP | TREND_UP | None | Aurora only |
| TREND_DOWN | TREND_DOWN | None | Aurora only |
| MEAN_REVERSION | FLAT | FLAT_NORMAL (default) | ✅ MR active |
| LOW_VOLATILITY | FLAT | FLAT_LOW | ✅ MR active |
| HIGH_VOLATILITY | UNCERTAIN | None (skip MR) | Aurora only |
| UNCERTAIN | UNCERTAIN | FLAT_NORMAL (fallback) | ⚠️ Conservative |

## 3. Configuration Keys (regime.yaml)

**File:** [config/aurora/regime.yaml](config/aurora/regime.yaml)

| Section | Key | Current Value | Pydantic Status |
|---------|-----|---------------|-----------------|
| root | `basis_tf_sec` | 300 | ❌ NOT IN PYDANTIC |
| root | `uncertain_cutoff` | 0.35 | ❌ NOT IN PYDANTIC |
| hmm | K, sticky_kappa, etc. | various | ⚠️ Optional |
| models.sma_trend | sma_short_period | 10 | ✅ Typed |
| models.sma_trend | sma_long_period | 50 | ✅ Typed |
| models.volatility | threshold_multiplier | 2.0 | ✅ Typed |
| models.mean_reversion | threshold | 0.005 | ✅ Typed |

## 4. Event Flow

```
EVT:FEATURES_CALCULATED (tf_sec=0 OR 300)
        ↓
  RegimeDetector.handle_event()    ← NO tf_sec filter!
        ↓
  EVT:REGIME_DETECTED
        ↓
  ├── DecisionMaking._per_symbol_regimes[symbol]
  ├── MeanReversionHandler._per_symbol_regime[symbol]
  ├── AuroraHandler.on_regime_detected()
  └── FeatureEngineering.on_regime_detected() (cache)
```

## 5. CRITICAL ISSUES FOUND

### 5.1 ❌ No tf_sec Filter in RegimeDetector
**Problem:** RegimeDetector processes ALL `EVT:FEATURES_CALCULATED` events (both tf=0 ticks and tf=300 bars).  
**Impact:** Double-clocking on bar boundaries, inconsistent regime detection.  
**Location:** [regime_detector.py#L107](apps/reference/domains/regime_detector/regime_detector.py#L107)

### 5.2 ❌ basis_tf_sec / uncertain_cutoff NOT IN Pydantic
**Problem:** These keys exist in YAML but `RegimeDetectorConfig` doesn't define them.  
**Impact:** Tests fail with `pydantic_core.ValidationError: extra_forbidden`  
**Location:** [config_models.py#L816-L820](apps/reference/config_models.py#L816-L820)

### 5.3 ⚠️ Regime Read from Cache, Not CMD Payload
**Problem:** MR reads regime from `_per_symbol_regime` cache instead of receiving it in CMD:PROCESS_STRATEGY.  
**Impact:** Potential race conditions, stale regime data.

## 6. RECOMMENDATIONS (REG-FIX-01)

1. **Add Pydantic fields:**
   - `basis_tf_sec: int` (required, no default)
   - `uncertain_cutoff: float` (required, no default)

2. **BAR-ONLY filter in RegimeDetector:**
   ```python
   if pld.get("tf_sec") != self.config.regime.basis_tf_sec:
       return  # Ignore non-basis timeframes
   ```

3. **Inject regime block into CMD:PROCESS_STRATEGY:**
   ```python
   "regime": {
       "label": "MEAN_REVERSION",
       "confidence": 0.75,
       "ts_ms": 1234567890123,
       "basis_tf_sec": 300
   }
   ```

4. **Clock migration for RegimeDetector**
