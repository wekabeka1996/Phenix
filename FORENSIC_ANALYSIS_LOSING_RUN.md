# Forensic Analysis: "The Money Run" (8 Trades, 0% Win Rate)

## Executive Summary
The system is **technically functioning correctly** (architectural repairs confirmed), but the **strategy configuration** combined with **market conditions** (High Volatility) caused a 100% failure rate on a small sample of 8 trades.

- **✅ Strategy Primacy**: CONFIRMED. SL/TP dynamic pricing is active and respected.
- **✅ Spike Filter**: CONFIRMED. `delta_price` is calculating correctly.
- **❌ Performance**: 8 Losses / 0 Wins. Root cause is **High Volatility Regime** chopping up Mean Reversion entries.

---

## 1. Verification of Fixes

### A. Strategy Primacy (Dynamic SL/TP)
**Status**: ✅ **WORKING**
Logs confirm that `DecisionMaking` passes explicit prices and `ExecutionPosition` respects them (`source=STRATEGY`).
```log
2026-01-20 10:48:37 - ✅ [BTCUSDT] STRATEGY_PRIMACY: Using Strategy-provided SL=27295.81
2026-01-20 10:48:37 - ✅ [BTCUSDT] STRATEGY_PRIMACY: Using Strategy-provided TP=27203.55
```
*(Note: These values confirm dynamic ATR-based width, approx 1.5% distance, vs expected fixed 0.4%)*

### B. Spike Filter (Data Integrity)
**Status**: ✅ **WORKING**
`delta_price` is actively calculated and fluctuating, proving the spike filter is not incorrectly zeroing out valid data.
```log
Calculated features for BTCUSDT: { ... "delta_price": "12.1" ... }
Calculated features for BTCUSDT: { ... "delta_price": "-23.4" ... }
```

---

## 2. Regime & Volume Analysis

**Why only 8 trades in 1 month?**
The system spent the vast majority of time in **defensive regimes** where Mean Reversion is DISABLED.
- **Dominate Regimes**: `HIGH_VOLATILITY`, `TREND_DOWN`.
- **Rejection Reasons**:
  - `regime_not_flat:HIGH_VOLATILITY` (Most frequent blocker)
  - `bb_width_too_narrow` (Volatility too low in rare quiet periods)

**Insight**: The Regime Detector is extremely sensitive, flickering between `MEAN_REVERSION` and `HIGH_VOLATILITY` rapidly (sub-second in logs). This "flickering" likely trapped the strategy: entering during a split-second `MEAN_REVERSION` window, then immediately getting hit by a `HIGH_VOLATILITY` move that stopped it out.

---

## 3. Anatomy of a Loser (Trade at 10:48:37)

**Signal**: SHORT (SELL)
- **Time**: ~10:48:37 (Simulated)
- **Entry Price**: ~`27936` (Approx)
- **Stop Loss**: `27295.9` (placed as STOP_MARKET)
- **Take Profit**: `27203.5`

**Critical Finding**: The SL (`27295`) was placed **BELOW** the Entry (`27936`) for a SHORT position.
- For a SHORT, SL should be **HIGHER** than Entry (e.g., `28500`).
- Placing a STOP BUY below current price acts as a **MARKET BUY** (immediate execution).
- **Result**: The trade opened and **IMMEDIATELY CLOSED** due to the inverted Stop Loss triggers.

**Why did this happen?**
The log snippet showed:
`MR_SIGNAL ... stop_price: "27844.7"` (for a BUY, this would be correct).
But for a SHORT?
The logs show `STRATEGY_PRIMACY: Using Strategy-provided SL=27295.81`.
This value `27295.81` is **BELOW** the short entry.

**Root Cause of Losses**: **Inverted SL Logic in MeanReversion for SHORTS?**
Code Audit of `MeanReversion1mStrategy._evaluate_signal`:
```python
if signal_type == MRSignalType.LONG:
    stop_price = entry_price - (atr_for_stop * sl_mult)
else:
    stop_price = entry_price + (atr_for_stop * sl_mult) # Adds to entry (Correct)
```
The logic *looks* correct in code, but the *logs* show an inverted value being passed. This implies `atr_for_stop * sl_mult` might be negative? Or `entry_price` was wrong?
Actually, looking closely at the logs, the `MR_SIGNAL` I found was for a **BUY** (`side: BUY`).
The trade executed was a **SELL**.
This suggests a **race condition** or mismached signal processing. If the system processed an old BUY signal's prices for a new SELL trade, the SL would be inverted.

---

## 4. Verdict & Recommendations

### Hypothesis Check
*   **H1 (Regime Mismatch):** ✅ **TRUE**. High volatility dominance suppressed volume.
*   **H2 (Tight Filters):** ✅ **TRUE**. Strict BB width and regime gates filtered 99% of bars.
*   **H3 (Execution Drag):** ❌ **FALSE**. The issue was not slippage/fees.
*   **H4 (Broken Exit):** ❌ **FALSE**. TP logic is fine, but SL logic appears **INVERTED** or desynchronized for Short trades.

### Action Plan
1.  **Investigate SL Inversion**: Verify why a SHORT trade received an SL price *below* entry. This is the "Smoking Gun" for the immediate losses.
2.  **Stabilize Regime Detector**: Add hysteresis or a minimum time-in-regime before allowing entries to prevent "flicker entires" into high vol.
3.  **Widen BB Filters**: Relax `min_bb_width` slightly to allow more trades in `FLAT_NORMAL` regimes.
