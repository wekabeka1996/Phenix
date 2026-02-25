# Forensic Code Audit: Feature Engineering Domain

**Date:** 2026-01-26
**Auditor:** AntiGravity (Principal Senior Architect)
**Scope:** `apps/reference/domains/feature_engineering/` (100% File Coverage)
**Objective:** Identify all Architectural Debt, Magic Numbers, Silent Fallbacks, and Logic Violations.

---

## 1. Executive Summary

The `feature_engineering` domain exhibits **Critical Architectural Fragility**. While individual mathematical kernels are often sound, the orchestration layer is riddled with "Silent Fallbacks" and "Magic Heuristics" that compromise data integrity and system observability.

**Primary Risks:**
1.  **Silent Data Corruption**: The widespread use of `try/except` blocks that return `neutral_value` (usually `0.0`) without raising alarms means the system can fail silently, feeding bad data to strategies.
2.  **Causality Violations**: Timestamp manipulation hacks (`ts - 1ms`) and wallclock time leakages (`time.time()`) threaten backtest integrity.
3.  **Zombie Logic**: The `MeanReversion1mStrategy` maintains two parallel, conflicting implementations of signal generation (`on_tick` vs `on_bar`), creating a "Split-Brain" risk.
4.  **Shadow Configuration**: Critical parameters (thresholds, multipliers, window sizes) are hardcoded in Python classes, bypassing the YAML configuration layer and making the system behavior opaque.

---

## 2. Systemic Anti-Patterns

### 2.1. The "Magic Timestamp" Heuristic
Multiple files rely on a hardcoded magic number to guess timestamp units:
```python
if ts < 1_000_000_000_000:  # 1e12
    return ts * 1000
```
**Risk**: If valid millisecond timestamps fall below this threshold (e.g., historical data or alternative epochs), they will be multiplied by 1000, corrupting time.

### 2.2. The "Silent Fallback" Epidemic
The domain adheres to a dangerous "Fail-Neutral" philosophy:
```python
except Exception:
    return (self.cfg.neutral_value, False, "crash_masked")
```
**Risk**: Math errors, type errors, and logic bugs are swallowed. The system reports "healthy but not ready" or "neutral value" instead of failing, making debugging impossible during live trading.

### 2.3. Shadow Configuration
Critical business logic is hardcoded in data classes or method signatures, disconnected from the central config:
-   `MeanReversion1mStrategy`: `confidence` scoring weights (`0.5`, `2`, `0.2`).
-   `RegimeMapping`: Multipliers `0.8`, `1.5`, `1.2`.
-   `PriceMotion`: Window sizes `(10, 60, 300, 900)`.

---

## 3. File-by-File Forensic Analysis

### 3.1. `feature_engineering.py` (Core FSM)
**Role:** Domain Entry Point & Event Orchestrator.

**Critical Findings:**
1.  **Causality Hack (`_create_synthetic_tick_for_bar_close`)**:
    -   **Code**: `synthetic_tick["ts"] = bar_ts - 1`
    -   **Verdict**: **CRITICAL**. Falsifies event time to bypass downstream checks. If `bar_ts` correlates with another event, this -1ms shift breaks causal ordering.
2.  **Wallclock Leak (`_emit_heartbeat`)**:
    -   **Code**: `time.time_ns()` is used for heartbeat timestamps.
    -   **Verdict**: **VIOLATION**. Breaks "Exchange Time SSOT". Backtests will have non-deterministic heartbeats.
3.  **Silent Drifts**:
    -   `_on_config_updated`: Re-initializes everything but doesn't validate if new config is compatible with hot state.

**Magic Numbers:**
-   `ts - 1`: Synthetic tick timestamp offset.

### 3.2. `calculation_engine.py` (Math Kernel)
**Role:** Numerical computation of features.

**Critical Findings:**
1.  **Timestamp Heuristic**:
    -   **Code**: `if ts < 1_000_000_000_000:`
    -   **Verdict**: **HIGH RISK**. See Section 2.1.
2.  **Inefficient Winsorization**:
    -   **Code**: `sorted(data)` inside `_winsorize`.
    -   **Verdict**: **PERFORMANCE**. $O(N \log N)$ sort on every tick for every window. Should use selection algorithm or incremental structure.
3.  **Sanity Firewall masking**:
    -   **Code**: `sanitize_feature` catches `ValueError` and returns `neutral_value`.
    -   **Verdict**: **OBSERVABILITY**. Masks meaningful data corruption (e.g., `NaN` propagation).

**Magic Numbers:**
-   `1_000_000_000_000`: Timestamp heuristic.
-   `0.01`: `delta_price` neutral check epsilon.

### 3.3. `mean_reversion_strategy.py` (Logic)
**Role:** Signal generation logic.

**Critical Findings:**
1.  **Zombie Logic (Split-Brain)**:
    -   **Code**: `on_tick` (L359) and `on_bar` (L287) duplicate the entire signal generation pipeline.
    -   **Verdict**: **CRITICAL**. If the system invokes both (e.g., during migration T2B-02), state updates will double-count or conflict. `on_tick` is marked deprecated but is fully functional and dangerous.
    -   **Status**: **Use of `on_tick` is DEAD CODE** (Confirmed via `mean_reversion_handler.py` audit). The system uses `on_bar` exclusively.
2.  **Hardcoded Scoring Model**:
    -   **Code**: `confidence = 0.5 + ... * 2` and `confidence += 0.2`.
    -   **Verdict**: **SHADOW CONFIG**. Trading logic is hardcoded. Cannot tune confidence without code deploy.
3.  **ATR Fallback Magic**:
    -   **Code**: `(bb.upper - bb.lower) / 4` logic if ATR is missing.
    -   **Verdict**: **STATISTICAL INVALIDITY**. Assumes normal distribution ($4\sigma \approx 95\%$) which is often false in crypto.

**Magic Numbers:**
-   `1000`: `MAX_BARS_PER_SYMBOL`.
-   `0.5`, `2`, `0.2`: Confidence scoring weights.
-   `4`: ATR fallback divisor.

### 3.4. `bar_resampler.py` (Aggregation)
**Role:** Ticks to OHLCV bars.

**Critical Findings:**
1.  **Gap Logic Distortion**:
    -   **Code**: `gap_bars_skipped` calculated, but **NO FILLER BARS** are created.
    -   **Verdict**: **DATA INTEGRITY**. Downstream indicators (SMA, BB) will calculation on time-discontinuous series as if they were continuous, invalidating frequency assumptions.
2.  **Wallclock Fallback**:
    -   **Code**: `time.time() * 1000` in `force_close`.
    -   **Verdict**: **VIOLATION**. Exchange Time SSOT violation.

**Magic Numbers:**
-   `1000`: `max_bars` default.

### 3.5. `indicators.py` (Math Lib)
**Role:** Statistical functions.

**Critical Findings:**
1.  **Performance Check Failure**:
    -   **Code**: `values[-window:]` array slicing.
    -   **Verdict**: **PERFORMANCE**. Creates copy of list on every feature calculation ($O(N)$).
2.  **Precision Loss**:
    -   **Code**: `Decimal(str(math.sqrt(float(variance))))`.
    -   **Verdict**: **ACCURACY**. Round-trip to float and string destroys Decimal precision benefits.

**Magic Numbers:**
-   `0.5`: `pct_b` default when bandwidth is zero.
-   `100` / `0`: RSI bounds.

### 3.6. `macro_sync_resampler.py` (Complex Feature)
**Role:** Cross-asset correlation.

**Critical Findings:**
1.  **Complexity Bomb**:
    -   **Code**: `bins.insert(i, ...)` inside `update`.
    -   **Verdict**: **PERFORMANCE**. $O(N)$ insertion. In high-volatility, high-tick scenarios (late arrivals), this turns feature calculation into $O(N^2)$ effectively.
2.  **Silent Correlation Failure**:
    -   **Code**: `_pearson` returns `None` if small variance.
    -   **Verdict**: **AMBIGUITY**. Distinguish between "flat line" (undefined correlation) and "uncorrelated" (0.0).

**Magic Numbers:**
-   `0.5`: Default `phi` (neutral).
-   `1.0`: `phi` calculation offset.

### 3.7. `price_motion.py` (Complex Feature)
**Role:** Volatility and momentum.

**Critical Findings:**
1.  **Heuristic Duplication**:
    -   **Code**: `ts < 1e12` check duplicated here.
    -   **Verdict**: **DRY VIOLATION**.
2.  **Linear Scan**:
    -   **Code**: `reversed(history)` search for `p_then`.
    -   **Verdict**: **PERFORMANCE**. Should use binary search.

**Magic Numbers:**
-   `10`, `60`, `300`, `900`: Hardcoded window sizes ($10s \to 15m$).
-   `10.0`: `clip_abs` default.

### 3.8. `large_trade_imbalance.py` (Complex Feature)
**Role:** Order flow imbalance.

**Critical Findings:**
1.  **Blind Ready State**:
    -   **Code**: Returns `ready=False` for almost all errors.
    -   **Verdict**: **OBSERVABILITY**. Impossible to distinguish "not enough trades" from "malformed data" without deep log inspection.

**Magic Numbers:**
-   `0`/`1`: Clamp bounds.

### 3.9. `regime_mapping.py` (Config Support)
**Role:** Mapping external regime to internal params.

**Critical Findings:**
1.  **Hardcoded Matrix**:
    -   **Code**: `_DEFAULT_SIZING_MULTIPLIERS`, `_DEFAULT_STOP_MULTIPLIERS`.
    -   **Verdict**: **FLEXIBILITY**. Changing trading aggression requires code change.
2.  **Blind Fallback**:
    -   **Code**: Returns `FLAT_NORMAL` if `atr_pct` missing.
    -   **Verdict**: **SAFETY**. If volatility data is missing, we default to "Normal" risk taking, which might be suicide in a high-vol environment.

**Magic Numbers:**
-   `0.8`, `1.0`, `0.7`: Sizing multipliers.
-   `0.6`, `1.5`: Stop multipliers.
-   `0.8`, `1.2`: Target multipliers.

### 3.10. `types.py` & `contracts.py` (Data)
**Critical Findings:**
1.  **Shadow Config Default**:
    -   **Code**: `FeatureEngineeringConfig` properties have hardcoded defaults if config is missing.
    -   **Verdict**: **CONSISTENCY**. Config from YAML and config from Code-Defaults can diverge.

---

## 4. Remediation Plan

**Phase 1: Safety & Integrity (Immediate)**
1.  **Kill Zombie Logic**: Delete `on_tick` in `mean_reversion_strategy.py`.
2.  **Fix Timestamp Heuristics**: Replace `1e12` checks with strict configuration of expected time units.
3.  **Strict Time**: Remove all `time.time()` calls; inject `clock` or enforce `ts_ms` from events.

**Phase 2: Observability & Transparency**
1.  **Expose Shadow Config**: Move all hardcoded multipliers/windows to `feature_engineering.yaml`.
2.  **Fix Silent Fallbacks**:
    -   Implement `SanityResult` (Ok/Warn/Fail).
    -   Emit `ERROR` logs on fallbacks, not just debug/warnings.

**Phase 3: Performance**
1.  **Optimize Math**: Replace list slicing with `deque` or `numpy` circular buffers.
2.  **Optimize Search**: Use `bisect` for timestamp lookups.
3.  **Fix Sort**: Optimize Winsorization.

**Phase 4: Architecture**
1.  **Centralize Time**: Create `TimeContext` object passed to all calculators, banning loose integer timestamps.
