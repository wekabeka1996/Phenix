# Cross-Asset Baseline Report

**Date**: 2025-12-02
**Period**: Jan 2024
**Strategy**: 5s Sniper + Regime Filters

---

## Summary

Extended 5s Sniper + Regime pipeline to 5 major crypto assets.
Used Jan 2024 data for baseline performance comparison.

## Results Table

| Symbol | PnL ($) | Trades | Calmar | Best Value | Regimes |
| --- | --- | --- | --- | --- | --- |
| BTCUSDT | -316.02 | 1407 | -52.1490 | 41.9176 | UP_NORMAL,UP_LOW,DOWN_NORMAL,FLAT_NORMAL,FLAT_LOW |
| ETHUSDT | -340.39 | 1481 | -52.1448 | 44.3789 | UP_HIGH,UP_NORMAL,UP_LOW,DOWN_LOW,FLAT_NORMAL,FLAT_LOW |
| SOLUSDT | -346.30 | 1449 | -52.0060 | 45.0567 | UP_LOW,FLAT_NORMAL,FLAT_LOW |
| XRPUSDT | -288.84 | 1194 | -52.1395 | 39.1729 | UP_NORMAL,DOWN_NORMAL,FLAT_LOW |
| DOGEUSDT | -311.87 | 1368 | -52.1216 | 41.4987 | UP_HIGH,UP_NORMAL,DOWN_LOW,FLAT_NORMAL,FLAT_LOW |


## Per-Symbol Analysis

### BTCUSDT

- **PnL**: $-316.02
- **Trades**: 1407
- **Allowed Regimes**: UP_NORMAL,UP_LOW,DOWN_NORMAL,FLAT_NORMAL,FLAT_LOW
- **Assessment**: ❌ Significant losses. No simple momentum alpha on this timeframe.

### ETHUSDT

- **PnL**: $-340.39
- **Trades**: 1481
- **Allowed Regimes**: UP_HIGH,UP_NORMAL,UP_LOW,DOWN_LOW,FLAT_NORMAL,FLAT_LOW
- **Assessment**: ❌ Significant losses. No simple momentum alpha on this timeframe.

### SOLUSDT

- **PnL**: $-346.30
- **Trades**: 1449
- **Allowed Regimes**: UP_LOW,FLAT_NORMAL,FLAT_LOW
- **Assessment**: ❌ Significant losses. No simple momentum alpha on this timeframe.

### XRPUSDT

- **PnL**: $-288.84
- **Trades**: 1194
- **Allowed Regimes**: UP_NORMAL,DOWN_NORMAL,FLAT_LOW
- **Assessment**: ❌ Significant losses. No simple momentum alpha on this timeframe.

### DOGEUSDT

- **PnL**: $-311.87
- **Trades**: 1368
- **Allowed Regimes**: UP_HIGH,UP_NORMAL,DOWN_LOW,FLAT_NORMAL,FLAT_LOW
- **Assessment**: ❌ Significant losses. No simple momentum alpha on this timeframe.

---

## Conclusions

**Final Sniper v1 Baseline Assessment:**

1. **High Activity, Negative Expectancy**: 
   - With `MIN_TRADES=100` and `MAX_TRADES=1500`, the optimizer found configurations with high activity (1200-1400 trades/week).
   - However, **all assets showed significant losses** (-$280 to -$350), primarily driven by spread and fees on a large number of break-even or slightly losing trades.

2. **Regime Filters Insufficient**:
   - Even with `DOWN_HIGH` and `FLAT_HIGH` blacklisted, the remaining regimes (including `FLAT_LOW` and `UP_NORMAL`) did not provide enough edge to overcome transaction costs on the 5s timeframe.

3. **Verdict**:
   - **Sniper v1 (5s Momentum + Basic Regimes)** is **NOT viable** as a standalone high-frequency strategy in its current form.
   - It functions effectively as a **baseline** to demonstrate infrastructure stability (execution, data pipeline), but lacks the predictive alpha required for profitability.
   - **Next Steps**: Future R&D should focus on:
     - **Higher Timeframes** (1m/5m) to capture larger moves and reduce fee impact.
     - **Mean Reversion** logic for the dominant "Flat" regimes.
     - **Advanced Features** (Order Flow Imbalance, Liquidity Gaps) to improve signal quality.
