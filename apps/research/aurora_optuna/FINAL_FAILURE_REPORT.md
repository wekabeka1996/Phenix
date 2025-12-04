# Aurora Regime Filtering - Final Analysis

**Date**: 2025-12-03  
**Status**: FAILED  
**Recommendation**: **Abandon Aurora 1m, Deploy Mean Reversion**

---

## 🔍 Investigation Results

### 1. The "Catastrophic" Result (-$2,128)
- **Trades**: 2,577
- **Cause**: Optuna run likely included `LOW_VOLATILITY` regime (689 bars) + `TREND` regimes (1893 bars) = 2,582 bars.
- **Match**: 2,577 trades ≈ 2,582 allowed bars.
- **Finding**: The strategy traded on almost every allowed bar, losing spread/fees constantly.

### 2. The "Fixed" Result (Reproduction)
- **Trades**: 349 (Strict `TREND` filtering)
- **PnL**: **-$284.87**
- **Win Rate**: 35.8%
- **Finding**: Even with strict regime filtering, the strategy loses money.

### 3. Comparison with Mean Reversion

| Strategy | PnL ($) | Trades | Win Rate | Status |
|---|---|---|---|---|
| **Aurora 1m (Trend)** | -$284 | 349 | 36% | ❌ Fails |
| **Mean Reversion 1m** | **+$45** | 172 | 53% | ✅ Works |

---

## 🧠 Why Aurora Failed on 1m

1. **Signal Noise**: Aurora features (EMA bias, Volume spike) are too noisy on 1m timeframe without tick-level order flow (OBI, TFI).
2. **Lag**: 1m bars are too slow for "Volume Spike" arbitrage but too fast for EMA trend following.
3. **Execution**: Market orders (Taker) kill profitability. Mean Reversion used Limit orders (Maker).

## 🚀 Final Recommendation

1. **Stop** optimizing Aurora on 1m.
2. **Deploy** the Mean Reversion strategy (Alpha V3) which is already proven (+$203/month portfolio).
3. **Future**: Revisit Aurora only when full tick-level infrastructure (Order Book Imbalance, Trade Flow) is available.
