# Aurora 3m Optimization Results

**Date**: 2025-12-03
**Timeframe**: 3m (180s)
**Trials**: 600 per asset

## 📊 Summary Table

| Asset | PnL ($) | Trades | Win Rate | Best Regime | Status |
|---|---|---|---|---|---|
| **DOGEUSDT** | **+$3.04** | 77 | 44.2% | `LOW_VOLATILITY` | ✅ **PROFIT** |
| **SOLUSDT** | **+$0.10** | 164 | 48.2% | `TREND_DOWN`, `LOW_VOL` | ✅ **PROFIT** |
| **BTCUSDT** | -$20.89 | 51 | 43.1% | `TREND_UP` | ⚠️ Reduced Loss |
| **ETHUSDT** | -$23.39 | 51 | 33.3% | `LOW_VOLATILITY` | ❌ Loss |
| **XRPUSDT** | -$16.11 | 58 | 41.4% | `LOW_VOLATILITY` | ❌ Loss |

## 💡 Key Findings

1.  **3m Timeframe Works Better**:
    *   **DOGE** and **SOL** flipped to **POSITIVE PnL**.
    *   **BTC** loss reduced from -$284 (1m) to -$20 (3m).
    *   Trade counts are much healthier (50-160 vs 2000+).

2.  **The "Low Volatility" Anomaly**:
    *   Both profitable assets (DOGE, SOL) and 2 losers (ETH, XRP) selected `LOW_VOLATILITY` as the primary regime.
    *   This suggests Aurora features (EMA Bias, Volume Spike) might actually work best as **Mean Reversion** signals in quiet markets, rather than trend following in active ones.

3.  **Trend Following Fails**:
    *   BTC explicitly selected `TREND_UP` and lost money (-$20).
    *   This confirms that simple EMA crossovers on 3m are still too lagging or noisy for profitable trend following without order flow confirmation.

## 📝 Detailed Parameters (Best Models)

### DOGEUSDT (+$3.04)
*   **Regimes**: `['LOW_VOLATILITY']`
*   **EMA**: Short=9, Long=17
*   **Volume**: Window=300s, SMA=3, Cap=3.75
*   **Weights**: Macro (0.37) > Volume (0.29) > EMA (0.24)
*   **Risk**: SL=0.94%, MaxHold=600s

### SOLUSDT (+$0.10)
*   **Regimes**: `['TREND_DOWN', 'LOW_VOLATILITY']`
*   **EMA**: Short=10, Long=13
*   **Volume**: Window=150s, SMA=18, Cap=4.58
*   **Weights**: EMA (0.50) > Liquidity (0.38) > Volume (0.34)
*   **Risk**: SL=1.39%, MaxHold=300s

## 🚀 Recommendation

1.  **Focus on DOGE/SOL**: Further refine the `LOW_VOLATILITY` logic for these assets.
2.  **Hybrid Approach**: Consider running Aurora (Mean Reversion mode) in Low Volatility and a different strategy (e.g., Breakout) in High Volatility.
3.  **Expand Timeframe**: 3m is better than 1m. Consider testing 5m or 15m to see if trend following becomes viable.
