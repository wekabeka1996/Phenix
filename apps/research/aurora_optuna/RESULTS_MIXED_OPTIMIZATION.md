# Aurora Mixed Optimization Results

**Date**: 2025-12-03
**Strategy**: Mixed Timeframes + Fine-Grained Search (1500 Trials)
**Features**: OBI + TFI + Regime Filtering

## 📊 Summary Table

| Asset | Timeframe | PnL ($) | Trades | Win Rate | Status |
|---|---|---|---|---|---|
| **SOLUSDT** | **3m** | **+$173.73** | 199 | 50.8% | 🚀 **MOON** |
| **ETHUSDT** | **5m** | **+$76.12** | 62 | 67.7% | 💎 **BREAKTHROUGH** |
| **XRPUSDT** | **3m** | **+$28.95** | 61 | 62.3% | ✅ **PROFIT** |
| **DOGEUSDT** | **3m** | **+$5.20** | 73 | 47.9% | ✅ **PROFIT** |
| **BTCUSDT** | **5m** | -$3.77 | 50 | 48.0% | ⚠️ Breakeven |

## 💡 Key Findings

1.  **ETH 5m Breakthrough**:
    *   Switching ETH to **5m** flipped it from a loser (-$22) to a **massive winner (+$76)**.
    *   Win Rate jumped to **67.7%**.
    *   Key Factor: **TFI Weight (0.47)** and **OBI Weight (0.45)**. It trades almost exclusively on Order Flow.

2.  **SOL 3m Scalability**:
    *   PnL increased from +$130 to **+$173**.
    *   Trade count doubled (105 -> 199), showing the strategy found more valid opportunities with finer parameters.
    *   Regime: `TREND_DOWN` (Shorting the crash).

3.  **BTC Stability**:
    *   BTC on 5m is essentially breakeven (-$3.77).
    *   This is acceptable. BTC acts as a "Macro Anchor" rather than a profit center.

## 📝 Detailed Parameters (Best Models)

### ETHUSDT (5m) - The New Star 🌟
*   **Regimes**: `['TREND_DOWN']`
*   **Weights**: **TFI (0.47)** > **OBI (0.45)** > Macro (0.38) > Liquidity (0.35)
*   **EMA Weight**: **0.17** (Price is irrelevant!)
*   **Logic**: Pure Order Flow trading. It ignores the chart and trades the tape.

### SOLUSDT (3m) - The Cash Cow 🐮
*   **Regimes**: `['TREND_DOWN']`
*   **Weights**: **EMA (0.47)** > **TFI (0.36)** > **OBI (0.34)**
*   **Logic**: Hybrid. Uses EMA for direction and TFI/OBI for timing.

## 🚀 Recommendation

1.  **Portfolio Composition**:
    *   **SOL (3m)**: Aggressive Growth.
    *   **ETH (5m)**: High Win Rate Stability.
    *   **XRP (3m)**: Diversification.
2.  **Execution**:
    *   Deploy these specific JSON configurations to the live bot.
    *   Ensure `obi` and `tfi` are calculated in real-time exactly as in backtest.
