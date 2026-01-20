# Regime Warmup Log Forensics Report (REGIME-WARMUP-LOG-FORENSICS-02)

## Executive Summary

**Root Cause Identified**: RegimeDetector uses `tick_ttl_ms` (2000ms) to check freshness of BAR features, but bar events naturally arrive 4-5 seconds after `bar_close_ts`, causing ALL bar-level features to be marked as **STALE** and triggering early returns with `full_ready=False`.

**Result**: Zero `EVT:REGIME_DETECTED` events emitted in ~1 hour of runtime. All trade intents blocked by `WARMUP_NOT_READY`.

---

## 1. Artifact Analysis

### 1.1 RegimeDetector Logs (`logs/domain_regime_detector.log`)
```
2026-01-13 10:58:58,575 - INFO - RegimeDetector: basis_tf_sec=300, uncertain_cutoff=0.35
2026-01-13 10:58:58,575 - INFO - RegimeDetector initialized with model: sma_trend_v1
2026-01-13 10:58:58,575 - INFO - RegimeDetector subscribed to EVT:FEATURES_CALCULATED
```
**ONLY 3 lines in 1+ hour** - No regime updates logged!

### 1.2 BAR_CLOSED Events (WAL)
Bars ARE being generated correctly:
- `EVT:BAR_CLOSED` for all 5 symbols at `tf_sec=300`
- Example: `bar:SOLUSDT:300:1768305899999` at `ts=1768305904512`
- **Delivery lag**: `ts - bar_close_ts = 4513ms` (>2000ms tick_ttl)

### 1.3 Feature Engineering Bar Emissions
```
12:05:04,735 - INFO - 📊 on_bar_closed: emitting bar-features for SOLUSDT tf_sec=300
12:05:04,835 - INFO - 📊 on_bar_closed: emitting bar-features for ETHUSDT tf_sec=300
12:05:04,881 - INFO - 📊 on_bar_closed: emitting bar-features for BTCUSDT tf_sec=300
12:05:04,999 - INFO - 📊 on_bar_closed: emitting bar-features for DOGEUSDT tf_sec=300
12:05:05,157 - INFO - 📊 on_bar_closed: emitting bar-features for XRPUSDT tf_sec=300
```
**Bars ARE emitted with correct `tf_sec=300`**.

---

## 2. RegimeDetector Forensics

### 2.1 Basis TF Verification
- **Config**: `basis_tf_sec: 300` ✓
- **Code Filter**: Line 210 `if tf_sec != self._basis_tf_sec: return` ✓

### 2.2 Stale Check Bug (THE ROOT CAUSE)

**File**: `apps/reference/domains/regime_detector/regime_detector.py`
**Lines 237-246**:
```python
tick_ttl_ms = int(self.config.system.market_data.tick_ttl_ms)  # = 2000ms
...
if tick_ttl_ms > 0 and (now_ms - ts_ms) > tick_ttl_ms:
    data_drops.append("stale_features")
    is_stale = True
```

**Lines 261-284**: If `is_stale`, early return with `full_ready=False`.

**Lines 458**:
```python
"full_ready": all(warmup_ready_map.values()) and (not data_drops),
```

**Problem**: Bar events have `ts` = `bar_close_ts` which is ~4.5s in the past when processed. Since 4500 > 2000 (tick_ttl_ms), ALL bar events are marked STALE!

---

## 3. Warmup Ticks Analysis

| Time | Ticks | full_ready | Reason |
|------|-------|------------|--------|
| 11:10:03 | 3 | False | regime_not_ready |
| 11:20:03 | 5 | False | regime_not_ready |
| 11:35:04 | 7 | False | regime_not_ready |
| 11:40:04 | 8 | False | regime_not_ready |
| 11:49:04 | 9 | False | regime_not_ready |
| 11:50:39 | 10 | False | regime_not_ready |
| 11:55:34 | 11 | False | regime_not_ready |
| 12:00:39 | 12 | False | regime_not_ready |

**Counter IS incrementing**, but `full_ready` NEVER becomes True.
**Analysis**: Warmup data comes from `_per_symbol_regimes` which is only populated when RegimeDetector emits `EVT:REGIME_DETECTED`. Since bars are marked stale (early return at line 284), no events are emitted, so DM's `_per_symbol_regimes` stays empty/stale.

---

## 4. Bad DT / Out-of-Order Analysis

| Metric | Count |
|--------|-------|
| time_diff=0 (duplicates) | 233 |
| time_diff<0 (out-of-order) | 0 |
| Total drops | 233 in ~1 hour |
| Drop rate | ~6/min |

**Impact**: `macro_sync:gap_too_large` causes FE `full_ready` to oscillate True↔False every 5 seconds. This is a secondary issue but complicates debugging.

---

## 5. Trade Block Analysis

### 5.1 Counts
| Metric | Count |
|--------|-------|
| WARMUP_NOT_READY total | 25 |
| INTENT_PROPOSED | 0 |
| CMD:OPEN | 0 |

### 5.2 Reason Breakdown
| Reason | Count |
|--------|-------|
| regime_not_ready | 13 |
| features_stale | 12 |

### 5.3 Root Cause Chain
```
DecisionMaking._warmup_gate_before_trade_intent (line ~2300)
  → checks _per_symbol_regimes[symbol]["warmup"]["full_ready"]
  → this is populated from EVT:REGIME_DETECTED
  → RegimeDetector NEVER emits because bars are marked stale
  → _per_symbol_regimes stays stale or empty
  → full_ready = False
  → TRADE BLOCKED
```

---

## 6. Minimal Fix Plan

### Priority 1: Config Fix (RegimeDetector TTL)
**Problem**: RegimeDetector uses `tick_ttl_ms` for bar validation.
**Solution**: Create `regime_bar_ttl_ms` config or reuse `bar_ttl_ms`.

**Immediate Workaround** (No code change):
Increase `tick_ttl_ms` in `system.yaml` to cover bar delivery:
```yaml
# system.yaml
system:
  market_data:
    tick_ttl_ms: 10000  # was 2000 - temporary workaround
```
**Risk**: This relaxes tick freshness for other components.

### Priority 2: Code Fix (APPLIED ✓)
**File**: `apps/reference/domains/regime_detector/regime_detector.py`
**Change**: Lines 237-252

```python
# BAR-TTL-REFORM-02: Use bar_ttl_ms for bar events, tick_ttl_ms for ticks
sys_md = self.config.system.market_data if self.config.system else None
if tf_sec and tf_sec > 0:
    # Bar event - use lenient bar TTL
    ttl_ms = int(getattr(sys_md, "bar_ttl_ms", 10000)) if sys_md else 10000
else:
    # Tick event - use strict tick TTL
    ttl_ms = int(sys_md.tick_ttl_ms) if sys_md else 0
```

**Status**: Applied at 12:08 UTC. Requires application restart to take effect.

### Priority 3: Observability Fix
Add heartbeat log in RegimeDetector:
```python
if self._ticks_seen[symbol] % 10 == 0:
    self.logger.info(f"[{symbol}] RegimeDetector heartbeat: ticks={self._ticks_seen[symbol]}, stale={is_stale}")
```

---

## 7. Conclusion

> **Root cause trade-block = `regime_not_ready` (13/25 intents blocked)**
> **Source**: `decision_making.py:~2340` (`_warmup_gate_before_trade_intent`)  
> **Trigger**: `RegimeDetector` never emits `EVT:REGIME_DETECTED` because ALL bar-level `EVT:FEATURES_CALCULATED` events are rejected as "stale" using incorrect `tick_ttl_ms` (2000ms) instead of `bar_ttl_ms` (10000ms).

### Recommended Next Step
Apply the **Priority 2 code fix** to `regime_detector.py` to use `bar_ttl_ms` for bar events, mirroring the existing fix in `decision_making.py`.
