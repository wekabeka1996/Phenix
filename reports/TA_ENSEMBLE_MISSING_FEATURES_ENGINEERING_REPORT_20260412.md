# ENGINEERING REPORT -- ta_ensemble Provider "Missing Required Features" Root Cause Analysis

**Date**: 2026-04-12
**Severity**: HIGH -- ta_ensemble provider is 100% non-functional in live runtime
**Symptom**: `[BTCUSDT] Provider ta_ensemble skipped: missing required features: price_momentum_1h,price_momentum_1d,volume_momentum_5m,macd_signal,atr_14,atr_ratio,realized_volatility_1h,realized_volatility_1d`
**Frequency**: 91 skips across all 7 symbols (13 per symbol), zero successful scores ever produced
**Source**: `apps/reference/domains/alpha_search/backtest_plugin.py:616`

---

## 1. Executive Summary

The `ta_ensemble` provider has **never successfully produced a single alpha score** in live runtime. Every evaluation across all 7 symbols is skipped due to 8 missing features. The root cause is a **two-layer structural mismatch**:

1. **Producer gap**: The TA Features domain produces only 8 of the 19 required features. The remaining 11 are expected from FE, but FE only provides them in backtest mode (when a BacktestEngine pre-injects TA columns into bar payloads). In live mode, those augmented keys are never injected, so they are never passed through.

2. **Nesting gap**: FE's volatility features (`atr_14`, `atr_pct`, `range_pct`) are nested under `features["volatility"]` as a sub-dict, not as flat top-level keys. The alpha_search cache stores features as-is without flattening, so the alias bridge never sees `atr_pct` at the top level and cannot derive `atr_ratio`.

Neither gap is a bug in isolation -- each component works correctly within its own contract. The problem is that **no component bridges the full feature vocabulary from live producers to the ta_ensemble consumer**.

---

## 2. Architecture and Data Flow

```
EVT:BAR_CLOSED
  ├──> [TA Features domain]
  │      Produces: 8 features (bb_position, bb_width, rsi_14,
  │                price_sma_20_deviation, volume_sma_ratio, stoch_k,
  │                stoch_d, price_momentum_5m)
  │      Emits: EVT:TA_FEATURES_CALCULATED
  │
  └──> [Feature Engineering domain]
         Produces: ~25 features (volume_spike, volatility_state, pillars, etc.)
         Nested:   features["volatility"] = {atr_14, atr_pct, range_pct, ...}
         Augmented pass-through (BACKTEST ONLY): macd_signal, momentum_1h/1d,
                                                 volume_momentum_5m, stochastic_k/d, etc.
         Emits: EVT:FEATURES_CALCULATED → CMD:PROCESS_STRATEGY
                          │
                          v
              [AlphaSearchBacktestPlugin]
                Cache merges FE + TA by (symbol, tf_sec, bar_close_ts)
                          │
                          v
              ta_ensemble (EnsembleModel)
                ├── MeanReversionAlphaModel  (7 features needed)
                ├── MomentumAlphaModel       (6 features needed)
                └── VolatilityAlphaModel     (8 features needed)
                    Total union: 19 unique features required
```

---

## 3. Feature Gap Matrix

### 3.1 What TA Features Domain Produces

Source: `apps/reference/domains/ta_features/contracts.py:TA_FEATURE_NAMES`

| Feature | Produced | Live? |
|---|---|---|
| `bb_position` | YES | YES |
| `bb_width` | YES | YES |
| `rsi_14` | YES | YES |
| `price_sma_20_deviation` | YES | YES |
| `volume_sma_ratio` | YES | YES |
| `stoch_k` | YES | YES |
| `stoch_d` | YES | YES |
| `price_momentum_5m` | YES | YES |

### 3.2 What Each Model Requires vs. What Exists

#### MeanReversionAlphaModel (`models/mean_reversion.py:31`)

| Required Feature | TA Features? | FE Feature? | Alias Source | Status |
|---|---|---|---|---|
| `bb_position` | YES | -- | -- | **OK** |
| `bb_width` | YES | -- | -- | **OK** |
| `rsi_14` | YES | -- | -- | **OK** |
| `price_sma_20_deviation` | YES | -- | -- | **OK** |
| `volume_sma_ratio` | YES | -- | -- | **OK** |
| `stoch_k` | YES | -- | -- | **OK** |
| `stoch_d` | YES | -- | -- | **OK** |

**Result: 7/7 satisfied. This model would work if evaluated alone.**

#### MomentumAlphaModel (`models/momentum.py:28`)

| Required Feature | TA Features? | FE Live? | Alias Source | Status |
|---|---|---|---|---|
| `price_momentum_5m` | YES | -- | -- | **OK** |
| `price_momentum_1h` | NO | Backtest-only pass-through | `momentum_60` | **MISSING** |
| `price_momentum_1d` | NO | Backtest-only pass-through | `momentum_1440` | **MISSING** |
| `volume_momentum_5m` | NO | Backtest-only pass-through | `volume_momentum` | **MISSING** |
| `rsi_14` | YES | -- | -- | **OK** |
| `macd_signal` | NO | Backtest-only pass-through | `macd_histogram` | **MISSING** |

**Result: 2/6 satisfied. 4 features missing because FE aug_keys pass-through only works when BacktestEngine injects them into bar payloads.**

#### VolatilityAlphaModel (`models/volatility.py:30`)

| Required Feature | TA Features? | FE Live? | Alias Source | Status |
|---|---|---|---|---|
| `atr_14` | NO | Nested at `features.volatility.atr_14` | None (not flattened) | **MISSING** |
| `atr_ratio` | NO | NO | `atr_pct` (nested, unreachable) | **MISSING** |
| `bb_width` | YES | -- | -- | **OK** |
| `bb_width_change` | NO | NO | Hardcoded `0.0` fallback | **OK** (fallback) |
| `realized_volatility_1h` | NO | NO | `realized_volatility` (never produced) | **MISSING** |
| `realized_volatility_1d` | NO | NO | `realized_volatility` (never produced) | **MISSING** |
| `volume_volatility_ratio` | NO | NO | Falls back to `volume_sma_ratio` | **OK** (fallback) |
| `price_range_ratio` | NO | NO | `range_pct` (nested, unreachable) | **MISSING-but-counted-as-OK** |

**Result: 2/8 satisfied, 2 get fallbacks, 4 truly missing.**

### 3.3 The 8 Missing Features in the Warning

The warning truncates to 8 (`missing_required[:8]`). The full missing set is:

| # | Feature | Required By | Root Cause |
|---|---|---|---|
| 1 | `price_momentum_1h` | momentum | TA doesn't compute; FE pass-through is backtest-only |
| 2 | `price_momentum_1d` | momentum | TA doesn't compute; FE pass-through is backtest-only |
| 3 | `volume_momentum_5m` | momentum | TA doesn't compute; FE pass-through is backtest-only |
| 4 | `macd_signal` | momentum | TA doesn't compute; FE pass-through is backtest-only |
| 5 | `atr_14` | volatility | FE computes but nests under `features["volatility"]` -- not flat |
| 6 | `atr_ratio` | volatility | FE computes `atr_pct` (nested) -- alias bridge can't reach it |
| 7 | `realized_volatility_1h` | volatility | No producer anywhere in live pipeline |
| 8 | `realized_volatility_1d` | volatility | No producer anywhere in live pipeline |

---

## 4. Root Cause Detail

### Root Cause 1: FE Augmented Pass-Through is Backtest-Only

**Files**:
- `feature_engineering.py:928-938` (bar-mode pass-through)
- `feature_engineering.py:1576-1586` (tick-mode pass-through)

Both pass-through blocks extract `aug_keys` from `bar_data` or `current_tick`:

```python
aug_keys = [
    "macd_line", "macd_signal", "macd_histogram",
    "stochastic_k", "stochastic_d",
    "price_momentum_5m", "price_momentum_1h", "price_momentum_1d",
    "volume_momentum_5m", "rsi_14", "bb_percent_b", "is_candidate",
]
for k in aug_keys:
    v = bar_get(k, seed_tick.get(k))
    if v is not None:
        bar_tick[k] = v
```

In backtest mode, a BacktestEngine pre-injects these columns from historical CSV data into bar payloads. In live mode, Binance WS price/kline data does NOT contain `macd_signal`, `momentum_1h`, etc. -- these keys are simply absent from the raw market data, so the pass-through finds nothing and the features never enter the pipeline.

**Impact**: `price_momentum_1h`, `price_momentum_1d`, `volume_momentum_5m`, `macd_signal` (and their alias sources `momentum_60`, `momentum_1440`, `volume_momentum`, `macd_histogram`) are never available in live mode.

### Root Cause 2: FE Volatility Features Are Nested, Not Flat

**File**: `feature_engineering.py:2207-2215`

```python
features["volatility"] = {
    "bar_range": str(bar_range),
    "bar_body": str(bar_body),
    "true_range": str(true_range),
    "atr_14": vol_state.last_atr,
    "range_pct": range_pct,
    "atr_pct": atr_pct,
    "atr_ready": vol_state.atr_ready,
}
```

The alpha_search plugin caches `dict(features)` at `backtest_plugin.py:431`, preserving the nested structure. When the alias bridge checks `"atr_pct" in normalized`, it finds nothing because `atr_pct` lives at `normalized["volatility"]["atr_pct"]`, not at the top level.

**Impact**: `atr_14` and `atr_ratio` (via `atr_pct`) are unreachable even though FE computes them.

### Root Cause 3: No Producer for `realized_volatility`

Neither TA Features nor FE produce a feature called `realized_volatility`, `realized_volatility_1h`, or `realized_volatility_1d`. The alias bridge checks for `realized_volatility` as a source, but it never exists:

```python
if "realized_volatility_1h" not in normalized and "realized_volatility" in normalized:
    normalized["realized_volatility_1h"] = normalized["realized_volatility"]
```

This was presumably planned but never implemented.

**Impact**: `realized_volatility_1h` and `realized_volatility_1d` have no source at all.

---

## 5. Impact Assessment

| Dimension | Impact |
|---|---|
| **ta_ensemble scoring** | 100% broken in live mode. Zero scores ever produced. |
| **MeanReversion sub-model** | Would work standalone (all 7 features present from TA) |
| **Momentum sub-model** | 100% broken (4/6 features missing) |
| **Volatility sub-model** | 100% broken (4/8 features missing, 2 absent everywhere) |
| **Current behavior** | fail_closed: emits neutral/zero scores for all bars |
| **System safety** | No risk -- provider is skipped cleanly, no stale scores leak |
| **Noise** | 91 warnings in aurora_core.log per runtime window, 13 per symbol |

---

## 6. Sub-Model Readiness Summary

| Sub-model | Features OK | Features Missing | Feasibility to Fix |
|---|---|---|---|
| `mean_reversion_v1` | 7/7 | 0 | **Ready now** -- could run standalone |
| `momentum_v1` | 2/6 | 4 (`price_momentum_1h/1d`, `volume_momentum_5m`, `macd_signal`) | **Medium** -- TA domain needs to compute multi-timeframe momentum + MACD |
| `volatility_v1` | 2/8 | 4-6 (`atr_14`, `atr_ratio`, `realized_volatility_1h/1d`, `price_range_ratio`) | **Medium-High** -- flatten FE volatility + add realized_volatility compute |

---

## 7. Fix Options

### Option A: Expand TA Features Domain (Recommended)

Add the 10 missing computed features to `ta_features.py` so that `EVT:TA_FEATURES_CALCULATED` carries the full 18-feature vocabulary:

| Feature to Add | Computation |
|---|---|
| `price_momentum_1h` | `(close - close_12_bars_ago) / close_12_bars_ago` at tf=300s (12 bars = 1h) |
| `price_momentum_1d` | `(close - close_288_bars_ago) / close_288_bars_ago` at tf=300s (288 bars = 1d) |
| `volume_momentum_5m` | `(volume - volume_1_bar_ago) / volume_1_bar_ago` |
| `macd_signal` | MACD signal line (EMA-9 of MACD line; MACD = EMA-12 - EMA-26) |
| `atr_14` | Average True Range over 14 bars |
| `atr_ratio` | `atr_14 / close` (normalized ATR as percentage) |
| `realized_volatility_1h` | Std of log-returns over 12 bars (1h at 5m tf) |
| `realized_volatility_1d` | Std of log-returns over 288 bars (1d at 5m tf) |
| `price_range_ratio` | `(high - low) / close` for current bar |
| `bb_width_change` | Delta of `bb_width` vs previous bar |

**Pros**: Single source of truth. All features computed from same bar buffer. Clean contract.
**Cons**: Requires warmup bar expansion (288 bars for 1d lookback vs current 50 buffer_max).

### Option B: Flatten FE Volatility + Add FE-Only Computation

Flatten `features["volatility"]` sub-dict to top-level in FE emission, and add the momentum/MACD features as native FE computations.

**Pros**: No new domain changes needed.
**Cons**: Mixes TA responsibility into FE. FE is already complex. Momentum/MACD are fundamentally TA indicators.

### Option C: Split the Ensemble -- Enable mean_reversion_v1 Standalone

Disable `momentum_v1` and `volatility_v1` sub-models in config. The `mean_reversion_v1` sub-model has all features present and would work immediately.

**Pros**: Immediate unblock with zero code changes -- config only.
**Cons**: Ensemble degraded to a single-model provider. Loses momentum and volatility signal contribution.

### Option D: Hybrid -- Option C Now, Option A in Next Sprint

1. Immediately: Disable broken sub-models via config to unblock `mean_reversion_v1`.
2. Next: Expand TA Features to produce the full vocabulary.

**Pros**: Immediate partial value + clean path to full ensemble.
**Cons**: Two-step work.

---

## 8. Key Files Reference

| File | Role | Key Lines |
|---|---|---|
| `apps/reference/domains/alpha_search/backtest_plugin.py` | Cache, normalize, validate, score | 616 (warning), 658-715 (alias bridge), 738-760 (validation) |
| `apps/reference/domains/alpha_search/models/momentum.py` | Momentum model | 28-36 (`get_required_features`) |
| `apps/reference/domains/alpha_search/models/mean_reversion.py` | MR model | 30-39 (`get_required_features`) |
| `apps/reference/domains/alpha_search/models/volatility.py` | Volatility model | 30-40 (`get_required_features`) |
| `apps/reference/domains/ta_features/contracts.py` | TA feature names | 7-16 (`TA_FEATURE_NAMES`) |
| `apps/reference/domains/ta_features/ta_features.py` | TA computation | 188-206 (`_compute_features`) |
| `apps/reference/domains/feature_engineering/feature_engineering.py` | FE aug pass-through + volatility nesting | 928-938 (aug_keys), 2207-2215 (volatility nest) |
| `config/alpha_search.yaml` | ta_ensemble config | 104-122 (provider definition) |
| `config/aurora/domains.yaml` | TA Features config | 388-396 (ta_features section) |

---

## 9. FACT / INFERENCE / UNKNOWN

### FACTS
1. `ta_ensemble` has produced 0 successful alpha scores in all live runtime observed.
2. 91 skip warnings across 7 symbols (13 each) in the current log window.
3. The same 8 features are missing for every symbol, every bar.
4. TA Features domain emits exactly 8 features (`TA_FEATURE_NAMES`).
5. FE aug_keys pass-through requires BacktestEngine pre-injection, which does not exist in live mode.
6. FE volatility features are nested at `features["volatility"]`, not flat.
7. `realized_volatility` has no producer anywhere in the live pipeline.
8. The `mean_reversion_v1` sub-model's 7 required features are all present from TA Features.
9. The alias bridge at `backtest_plugin.py:658-715` is correctly coded but its source features are absent.

### INFERENCES
1. The ta_ensemble was designed for backtest mode where augmented bar data carries precomputed TA columns.
2. When moved to live runtime, the implicit dependency on BacktestEngine injection was not replaced with a live producer.
3. The nesting issue (`features["volatility"]`) was not a problem in backtest because the backtest path constructs flat feature dicts.

### UNKNOWNS
1. Whether the 50-bar buffer max in TA Features config is sufficient for 1d lookback (288 bars at 5m tf).
2. Whether realized_volatility was ever planned as a TA Features computation or was always expected from an external source.
3. Whether the ensemble weights/thresholds were calibrated with all three sub-models or only with mean_reversion.
