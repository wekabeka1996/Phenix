# Aurora 1m Optimization Results (600 Trials)

**Date**: 2025-12-03  
**Strategy**: Aurora Existing Features (40% core)  
**Timeframe**: 1m  
**Period**: January 2024  
**Trials**: 600 per asset  

---

## 📊 Results Summary

| Asset | PnL ($) | Trades | Win Rate | Calmar | Status |
|---|---|---|---|---|---|
| **ETHUSDT** | **+$8.79** | 24 | 50.0% | 1.00 | ✅ Only Profitable |
| **BTCUSDT** | **-$10.89** | 20 | 40.0% | -0.64 | ❌ Negative |
| **SOLUSDT** | **-$49.76** | 112 | 45.5% | -0.66 | ❌ Negative |
| **XRPUSDT** | **-$387.25** | 470 | 27.9% | -0.99 | ❌ Heavy Loss |
| **DOGEUSDT** | **-$547.09** | 676 | 23.7% | -1.00 | ❌ Worst |

**Total Portfolio PnL**: **-$975.29** ❌❌❌

---

## 🔍 Analysis

### ⚠️ Critical Issues:

1. **Over-Trading on Altcoins**:
   - XRP: 470 trades (23x more than ETH!)
   - DOGE: 676 trades (28x more than ETH!)
   - **Problem**: Low win rate (24-28%) = чистий збиток

2. **Low Win Rates**:
   - DOGE: 23.7%
   - XRP: 27.9%
   - **Issue**: Aurora features generate false signals without proper regime filtering

3. **ETH - Єдиний profitable**:
   - **Чому**: Мало trades (24), консервативні пороги
   - Win Rate 50% - break-even level
   - Calmar 1.0 - стабільний

### 🤔 Що Пішло Не Так?

**Aurora Features (40% core) недостатньо для 1m directional trading**:

```python
# Наш backtest:
signal = weighted_avg(ema_bias, volume_spike, macro_sync, liquidity)

# Проблема: Немає regime awareness!
if regime == "TREND":
    # Aurora features працюють
elif regime == "FLAT":
    # Генеруються false signals → losses
```

**Mean Reversion (наша попередня стратегія) працювала краще** (+$203/міс), тому що:
- ✅ Фільтрувала по FLAT regimes
- ✅ Чекала BB extremes
- ✅ Мала clear exit (повернення до mean)

---

## 🎯 Features Optimized (40% Aurora Core)

1. **EMA Bias**: Trend direction (period_short, period_long)
2. **Volume Spike**: Unusual volume activity (window, SMA length, cap)
3. **Macro Sync**: BTC-ETH correlation (your feature!)
4. **Liquidity Kappa**: Market depth proxy
5. **Risk Score**: Composite risk metric

---

## ⚙️ Optimal Parameters

### BTCUSDT
```json
{
  "params": "TBD",
  "metrics": {
    "pnl": "TBD",
    "trades": "TBD",
    "win_rate": "TBD",
    "calmar": "TBD"
  }
}
```

---

## 📈 Analysis

*To be updated with results*

---

## 🚀 Next Steps

1. Compile full results
2. Compare with Mean Reversion 1m baseline
3. Update Aurora config with optimal parameters
4. Walk-forward validation (Feb-Mar 2024)
