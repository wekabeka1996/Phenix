# OBI & TFI Integration Report

**Date**: 2025-12-03
**Status**: ✅ READY FOR OPTIMIZATION

---

## 1. Data Source Verification
*   **Source**: `*-60s-golden-*.csv` files.
*   **Confirmed Columns**:
    *   `tob_bid_qty_1s`, `tob_ask_qty_1s` -> Used for **OBI**.
    *   `buy_vol_1s`, `sell_vol_1s` -> Used for **TFI**.
*   **Resolution**: 1-minute data resampled to 3-minute bars.

## 2. Implementation Details

### Order Book Imbalance (OBI)
*   **Formula**: $\frac{BidQty - AskQty}{BidQty + AskQty}$
*   **Logic**: Measures passive supply/demand pressure.
    *   Positive = Strong Bids (Support)
    *   Negative = Strong Asks (Resistance)
*   **Smoothing**: Rolling mean over `obi_window_sec` (Optimizable).

### Trade Flow Imbalance (TFI)
*   **Formula**: $\frac{BuyVol - SellVol}{BuyVol + SellVol}$
*   **Logic**: Measures active market aggression.
    *   Positive = Aggressive Buying
    *   Negative = Aggressive Selling
*   **Smoothing**: Rolling mean over `tfi_window_sec` (Optimizable).

## 3. Optuna Configuration Changes
Added the following parameters to the search space:

| Parameter | Range | Description |
|---|---|---|
| `obi_window_sec` | 30 - 300s | Smoothing window for OBI |
| `tfi_window_sec` | 30 - 300s | Smoothing window for TFI |
| `weight_obi` | 0.1 - 0.5 | Weight of OBI in composite signal |
| `weight_tfi` | 0.1 - 0.5 | Weight of TFI in composite signal |

## 4. Strategy Review (Chief Engineer's View)
*   **Previous State**: "Blind" OHLCV strategy. Relied on price history (EMA) which lags.
*   **Current State**: "Hybrid" strategy. Combines Price Structure (EMA/Regime) with **Order Flow Pressure** (OBI/TFI).
*   **Expectation**:
    *   **OBI** will filter false breakouts (e.g., price goes up but order book is empty).
    *   **TFI** will confirm true momentum (e.g., price goes up AND buyers are aggressive).
    *   This significantly increases the probability of finding a robust alpha on 3m.

## 5. Next Steps
*   **Launch**: Run 600 trials for all 5 assets with new features.
*   **Target**: Validate if OBI/TFI improves Win Rate and PnL compared to the previous run.
