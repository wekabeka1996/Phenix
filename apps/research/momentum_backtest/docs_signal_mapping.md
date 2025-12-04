# Signal Parity Mapping: Production vs R&D

**Status**: 🔴 **CRITICAL DISCREPANCIES FOUND**

Last Updated: 2024-11-30  
Author: R&D Pipeline Audit

## Executive Summary

**ROOT CAUSE IDENTIFIED**: Production bot uses **normalized φ-features [0,1]** while R&D backtest uses **raw features [-1,1]**. This fundamental difference explains anomalous Optuna results (54-85 trades, low w_tfi).

## Part A: Feature Mapping (Prod ↔ R&D)

| Concept | Prod Implementation | R&D Implementation | Matches? | Critical Notes |
|---------|--------------------|--------------------|----------|----------------|
| **TFI** | `feature_engineering.py:353`<br>`tfi = (buy_vol - sell_vol) / total_flow`<br>Range: `[-1, 1]`<br>**Then normalized**: `phi_TFI = (tfi + 1) / 2` → `[0, 1]` | `features_builder.py:31`<br>`tfi_1m = tanh((buy_vol - sell_vol) / total_vol)`<br>Range: `[-1, 1]`<br>**NO NORMALIZATION** | ❌ **NO** | **CRITICAL**: Prod uses `[0,1]`, R&D uses `[-1,1]`. Different scales → different optimal weights! |
| **OBI** | `feature_engineering.py:349`<br>`obi = (bid_size - ask_size) / depth`<br>Range: `[-1, 1]`<br>**Then normalized**: `phi_OBI = (obi + 1) / 2` → `[0, 1]` | `features_builder.py:27`<br>`tob_imbalance = (bid_qty - ask_qty) / (bid_qty + ask_qty + epsilon)`<br>Range: `[-1, 1]`<br>**NO NORMALIZATION** | ❌ **NO** | **CRITICAL**: Same formula, but prod maps to `[0,1]` in signal scoring |
| **EMA Bias Short** | `feature_engineering.py:382`<br>Via `_compute_ema_bias()`<br>Normalized to `[0, 1]`<br>Window: EMA3/EMA7 | `features_builder.py:43`<br>`ema_bias_short = (ema_3m - ema_7m) / ema_7m → clipped [0,1]`<br>Window: 180s/420s | ⚠️ **PARTIAL** | Same concept but R&D doesn't use 'short' separately in scoring. Prod has dedicated weight. |
| **EMA Bias Long** | Not explicitly separate in prod<br>Same `ema_bias` feature | `features_builder.py:49`<br>`ema_bias_long = (ema_15m - ema_60m) / ema_60m → clipped [0,1]`<br>Window: 900s/3600s | ❌ **NO** | R&D has long-term EMA bias, prod doesn't differentiate |
| **Vol State** | `feature_engineering.py:390`<br>`_compute_volatility_state()`<br>Normalized to `[0, 1]` | `features_builder.py:56`<br>`vol_state = vol_60s / rolling_mean(3600s)`<br>Range: unrestricted (can be >1) | ⚠️ **PARTIAL** | Similar concept, different normalization |
| **Macro Corr** | `feature_engineering.py:397`<br>`macro_sync = Pearson(alt_returns, btc_returns)`<br>Normalized to `[0, 1]` via `(corr + 1) / 2` | `features_builder.py:72-95` → `dependency_features.py`<br>`macro_corr_1h = dep_corr_1h`<br>Range: `[-1, 1]` (Pearson raw)<br>**NO NORMALIZATION** | ❌ **NO** | **CRITICAL**: Prod maps `[-1,1]` → `[0,1]`, R&D keeps raw |
| **Funding Veto** | `decision_making.py:1457-1503`<br>Crowding filter via `ctx.crowding`<br>Blocks if `is_crowded_long/short` | `backtest_engine.py:169-172`<br>`if funding_rate_1s > threshold: skip`<br>Simple threshold comparison | ⚠️ **PARTIAL** | Prod uses sophisticated crowding logic, R&D uses simple veto |

## Part B: Signal Formula Mapping

### Production Signal Score

**Location**: `decision_making.py:1306-1338`

```python
# Normalize all features to [0,1] (phi-transform)
obi_phi = (obi_raw + 1) / 2  # [-1,1] → [0,1]
tfi_phi = (tfi_raw + 1) / 2  # [-1,1] → [0,1]
dp_phi = abs(delta_price) / price / 0.02  # % change, capped at 2%
ema_bias_phi = ema_bias  # Already [0,1]
volume_spike_phi = volume_spike  # Already [0,1]
volatility_state_phi = volatility_state  # Already [0,1]
depth_imbalance_phi = depth_imbalance  # Already [0,1]
macro_sync_phi = (macro_sync + 1) / 2  # [-1,1] → [0,1]

# Weighted sum
signal_score = sum(phi_map[f] * weight[f] for f in signal_weights)

# Apply threshold with regime bias
if signal_score >= threshold:
    side = "buy"
elif signal_score <= -threshold:
    side = "sell"
```

**Key points**:
- ALL features transformed to `[0, 1]` before weighting
- Score is positive weighted sum
- Threshold comparison is **asymmetric** (≥ vs ≤ negative threshold)

### R&D Signal Score

**Location**: `backtest_engine.py:158-176`

```python
# Direct weighted sum of RAW features
score_raw = (
    w_tfi * tfi_1m +  # [-1,1]
    w_tob * tob_imbalance +  # [-1,1]
    w_bs * ema_bias_short +  # [0,1]
    w_bl * ema_bias_long  # [0,1]
)

# Macro correlation multiplier (NOT additive weight!)
score_raw *= (1.0 + macro_corr_weight * macro_corr_1h)  # macro_corr_1h in [-1,1]

# Threshold
if score_raw > threshold:
    open_long()
elif score_raw < -threshold:
    open_short()
```

**Key discrepancies**:
1. **No φ-normalization**: TFI stays `[-1,1]`, not `[0,1]`
2. **Macro as multiplier**, not additive weight
3. **Mixed feature ranges**: Some `[-1,1]`, some `[0,1]`

## Part C: Impact Analysis

### Why Optuna Found Strange Parameters

Given R&D uses raw `[-1,1]` features:

1. **Low w_tfi (0.02-0.08)**:  
   - TFI in `[-1,1]` has 2x the magnitude vs prod's `[0,1]` version
   - To achieve same signal strength, weights must be ~50% lower
   - **Optuna correctly found this**, but it's NOT the prod behavior!

2. **High threshold (0.15-0.19)**:  
   - Raw features → larger score magnitudes
   - Needs higher threshold to filter properly
   - Again, mathematically correct for R&D's formula, but NOT prod

3. **High macro_corr_weight (0.91-0.98)**:  
   - Multiplier effect amplifies when macro_corr near +1
   - But in prod, it's additive weighted feature
   - **Completely different logic**!

## Recommendations

### Option A: Align R&D to Production (RECOMMENDED)

**Pros**:
- Optuna will find parameters transferable to prod bot
- Can validate against prod runtime logs
- Lower risk of deployment mismatch

**Changes needed**:
1. Add φ-normalization to `features_builder.py`:
   - `tfi_phi = (tfi_1m + 1) / 2`
   - `tob_phi = (tob_imbalance + 1) / 2`
   - `macro_corr_phi = (macro_corr_1h + 1) / 2`

2. Change macro_corr from multiplier to weighted feature:
   ```python
   score_raw = (
       w_tfi * tfi_phi +
       w_tob * tob_phi +
       w_bs * ema_bias_short +
       w_bl * ema_bias_long +
       w_macro * macro_corr_phi  # NEW: additive
   )
   ```

3. Re-run Optuna with corrected logic

### Option B: Keep R&D, Update Prod (NOT RECOMMENDED)

- High risk: prod bot is working system
- Would need extensive testing
- Breaks existing param configs

## Next Steps

1. ✅ Document created
2. ⏳ User decision: Option A or B?
3. ⏳ Implement chosen alignment
4. ⏳ Fix objective function (MIN_TRADES=200+)
5. ⏳ Re-run Optuna with corrected parity
6. ⏳ Runtime parity check validation

---

**CONCLUSION**: R&D pipeline is NOT a faithful clone of production. Fundamental φ-normalization difference causes Optuna to find non-transferable parameters. Must fix before continuing optimization.
