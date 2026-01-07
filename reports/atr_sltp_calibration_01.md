# ATR-SLTP Calibration Report

**Generated:** 2026-01-07T21:41:29.562468+00:00

**Data Source:** Binance USD-M Futures OHLCV (5m candles)

**Symbols:** BTCUSDT, ETHUSDT, SOLUSDT, DOGEUSDT, XRPUSDT

**Horizon:** 45 minutes (9 bars)

**ATR Period:** 14

**Regime Thresholds:** LOW <= q50, MID <= q80, HIGH > q80

---

## Calibration Results by Symbol and Regime

### BTCUSDT

| Regime | ATR Frac (median) | k_sl_q90 | k_sl_q95 | k_tp_q50 | k_tp_q60 | k_tp_q70 | Samples |
|--------|-------------------|----------|----------|----------|----------|----------|----------|
| LOW | 0.000800 | 4.36 | 6.02 | 1.38 | 1.79 | 2.32 | 4309 |
| MID | 0.001471 | 3.86 | 5.73 | 1.25 | 1.57 | 1.99 | 2584 |
| HIGH | 0.002664 | 3.25 | 4.49 | 1.07 | 1.38 | 1.73 | 1722 |

### ETHUSDT

| Regime | ATR Frac (median) | k_sl_q90 | k_sl_q95 | k_tp_q50 | k_tp_q60 | k_tp_q70 | Samples |
|--------|-------------------|----------|----------|----------|----------|----------|----------|
| LOW | 0.001179 | 4.13 | 5.76 | 1.28 | 1.65 | 2.14 | 4307 |
| MID | 0.002101 | 3.88 | 5.17 | 1.22 | 1.55 | 1.98 | 2583 |
| HIGH | 0.003845 | 3.32 | 4.32 | 1.06 | 1.34 | 1.70 | 1725 |

### SOLUSDT

| Regime | ATR Frac (median) | k_sl_q90 | k_sl_q95 | k_tp_q50 | k_tp_q60 | k_tp_q70 | Samples |
|--------|-------------------|----------|----------|----------|----------|----------|----------|
| LOW | 0.001579 | 3.87 | 5.15 | 1.38 | 1.73 | 2.16 | 4311 |
| MID | 0.002450 | 3.75 | 5.18 | 1.23 | 1.53 | 1.93 | 2579 |
| HIGH | 0.004110 | 3.37 | 4.57 | 1.08 | 1.42 | 1.80 | 1725 |

### DOGEUSDT

| Regime | ATR Frac (median) | k_sl_q90 | k_sl_q95 | k_tp_q50 | k_tp_q60 | k_tp_q70 | Samples |
|--------|-------------------|----------|----------|----------|----------|----------|----------|
| LOW | 0.001605 | 4.02 | 5.65 | 1.32 | 1.72 | 2.16 | 4314 |
| MID | 0.002613 | 3.79 | 5.45 | 1.26 | 1.61 | 2.03 | 2577 |
| HIGH | 0.004327 | 3.41 | 4.44 | 1.07 | 1.36 | 1.72 | 1724 |

### XRPUSDT

| Regime | ATR Frac (median) | k_sl_q90 | k_sl_q95 | k_tp_q50 | k_tp_q60 | k_tp_q70 | Samples |
|--------|-------------------|----------|----------|----------|----------|----------|----------|
| LOW | 0.001370 | 4.07 | 5.69 | 1.38 | 1.75 | 2.18 | 4312 |
| MID | 0.002250 | 3.61 | 4.84 | 1.20 | 1.53 | 1.95 | 2587 |
| HIGH | 0.003783 | 3.20 | 4.48 | 1.12 | 1.41 | 1.75 | 1716 |

---

## Recommended Defaults per Symbol

### BTCUSDT

**TREND/HIGH regime:**
- `k_sl = 4.49` (q95 MAE)
- `k_tp = 1.38` - `1.73` (q60-q70 MFE)

**FLAT/LOW regime:**
- `k_sl = 4.36` (q90 MAE)
- `k_tp = 1.38` - `1.79` (q50-q60 MFE)

### ETHUSDT

**TREND/HIGH regime:**
- `k_sl = 4.32` (q95 MAE)
- `k_tp = 1.34` - `1.70` (q60-q70 MFE)

**FLAT/LOW regime:**
- `k_sl = 4.13` (q90 MAE)
- `k_tp = 1.28` - `1.65` (q50-q60 MFE)

### SOLUSDT

**TREND/HIGH regime:**
- `k_sl = 4.57` (q95 MAE)
- `k_tp = 1.42` - `1.80` (q60-q70 MFE)

**FLAT/LOW regime:**
- `k_sl = 3.87` (q90 MAE)
- `k_tp = 1.38` - `1.73` (q50-q60 MFE)

### DOGEUSDT

**TREND/HIGH regime:**
- `k_sl = 4.44` (q95 MAE)
- `k_tp = 1.36` - `1.72` (q60-q70 MFE)

**FLAT/LOW regime:**
- `k_sl = 4.02` (q90 MAE)
- `k_tp = 1.32` - `1.72` (q50-q60 MFE)

### XRPUSDT

**TREND/HIGH regime:**
- `k_sl = 4.48` (q95 MAE)
- `k_tp = 1.41` - `1.75` (q60-q70 MFE)

**FLAT/LOW regime:**
- `k_sl = 4.07` (q90 MAE)
- `k_tp = 1.38` - `1.75` (q50-q60 MFE)

---

## Notes

- **MAE (Maximum Adverse Excursion):** Maximum price movement against the position
- **MFE (Maximum Favorable Excursion):** Maximum price movement in favor of the position
- **k_sl, k_tp:** Multipliers to apply to ATR for SL/TP distances
- **ATR Frac:** ATR / entry_price (median)
- **Regime Proxy:** Based on rolling volatility quantiles (15m-equivalent window)
- **Horizon:** Forward-looking window for MAE/MFE computation

