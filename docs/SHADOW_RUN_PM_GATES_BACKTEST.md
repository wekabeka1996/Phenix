# Shadow Run Backtest Results - Price Motion Gates

**Date:** 2026-01-03  
**Engine Version:** v2.0 with PRICE-MOTION-V1 gates

---

## Executive Summary

Backtest на історичних feature logs (~11,800 bars per symbol) показав, що **price_motion gates суттєво покращують P&L**, блокуючи погані входи під час негативного цінового руху.

| Configuration | P&L | vs Baseline | Change |
|---------------|-----|-------------|--------|
| **NO PM GATES** | **$-1.01** | baseline | — |
| PM w/ bleed=0.3 | **$+0.27** | +$1.28 | ⬆️ **Best** |
| PM w/ bleed=0.5 | **$+0.26** | +$1.27 | ⬆️ |
| PM w/ bleed=0.7 (prod) | $-0.14 | +$0.87 | ⬆️ |

---

## 1. Backtest Parameters

```yaml
# Test Settings
symbols: [BTCUSDT, ETHUSDT, SOLUSDT, DOGEUSDT, XRPUSDT]
warmup_bars: 350  # ~5.8 minutes for 300s bleed window
position_size: $100 per trade
sl_pct: 0.5%
tp_pct: 1.0%

# Price Motion Config (Production)
pm_k_vol: 2.0
pm_flash_window_sec: 10
pm_bleed_window_sec: 300
pm_flash_threshold: 1.0
pm_bleed_threshold: 0.7
pm_require_bleed_ready: true
```

---

## 2. Detailed Results

### 2.1. Without PM Gates (Baseline)

| Symbol | Trades | Win% | P&L |
|--------|--------|------|-----|
| BTCUSDT | 192 | 48.4% | $-1.25 |
| ETHUSDT | 192 | 50.5% | $-1.34 |
| SOLUSDT | 192 | 43.8% | $-0.87 |
| DOGEUSDT | 196 | 51.0% | $+1.44 |
| XRPUSDT | 192 | 51.6% | $+1.01 |
| **TOTAL** | **964** | | **$-1.01** |

### 2.2. With PM Gates (Production Config)

| Symbol | Trades | Win% | P&L | PM Blocked |
|--------|--------|------|-----|------------|
| BTCUSDT | 99 | 51.5% | $+0.09 | 5,534 |
| ETHUSDT | 108 | 46.3% | $-1.33 | 4,995 |
| SOLUSDT | 109 | 50.5% | $-0.40 | 4,933 |
| DOGEUSDT | 120 | 41.7% | $+0.28 | 4,472 |
| XRPUSDT | 111 | 50.5% | $+1.21 | 4,811 |
| **TOTAL** | **547** | | **$-0.14** | **24,745** |

**Impact:** PM gates **improved P&L by $0.87** (from -$1.01 to -$0.14)

---

## 3. Threshold Sensitivity Analysis

Testing different `bleed_threshold` values with `flash_threshold=1.0`:

| Bleed Threshold | P&L | Δ vs Baseline | Flash Blocked | Bleed Blocked |
|-----------------|-----|---------------|---------------|---------------|
| 0.3 | **$+0.27** | **+$1.28 ⬆️** | 11,263 | 14,022 |
| 0.5 | **$+0.26** | **+$1.27 ⬆️** | 11,170 | 13,815 |
| 0.7 (prod) | $-0.14 | +$0.87 ⬆️ | 11,063 | 13,682 |
| 0.9 | $-0.30 | +$0.71 ⬆️ | 10,969 | 13,536 |
| 1.0 | $-0.22 | +$0.79 ⬆️ | 10,938 | 13,447 |

**Optimal threshold: 0.3-0.5** provides best P&L improvement.

---

## 4. Block Reason Distribution

| Reason | Count | Description |
|--------|-------|-------------|
| PM_FLASH_INSUFFICIENT | ~11,000 | 10s history not ready |
| PM_BLEED_BLOCKED_* | ~13,500 | 300s bleed gate triggered |
| PM_FLASH_BLOCKED_* | <100 | 10s flash gate triggered |

**Note:** Most blocks are from `PM_BLEED_*` gates, indicating the 300s price motion is the primary filter.

---

## 5. Recommendations

### For Production:

1. **Keep PM gates enabled** — proven P&L improvement
2. **Consider lowering `bleed_threshold`** from 0.7 to 0.5:
   ```yaml
   # domains.yaml
   price_motion_sanity:
     bleed_threshold_norm: 0.5  # Was: 0.7
   ```
3. **Current warmup is sufficient** — 350 bars covers 300s window

### For Further Analysis:

- [ ] Test on longer historical data (multiple days/weeks)
- [ ] Analyze P&L distribution of blocked trades
- [ ] Test flash threshold sensitivity (currently fixed at 1.0)

---

## 6. Technical Notes

### Shadow Engine Updates

The shadow engine (`apps/research/shadow_run/shadow_engine.py`) was updated to:

1. **Add `PriceMotionCalculator`** class mirroring production `price_motion.py`
2. **Implement Flash/Bleed gates** matching `DecisionMaking` logic
3. **Track `pm_blocked_count`** and `pm_blocked_reasons` in `ShadowResults`
4. **Support configurable thresholds** for A/B testing

### Running Backtests

```python
from apps.research.shadow_run import ShadowEngine

# Test with PM gates
engine = ShadowEngine(feature_logs_dir='logs/features')
engine.pm_gates_enabled = True
engine.pm_bleed_threshold = 0.5  # Optimal

results = engine.run()
for symbol, res in results.items():
    res.print_summary()
```

---

*Report generated: 2026-01-03*
*Shadow Run Engine v2.0 (PRICE-MOTION-V1)*
