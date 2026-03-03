# 📋 PLAN ZMІН: Golden Run Settings для BTC

**Дата:** 2026-01-27  
**Мета:** Інтегрувати "Golden Run" налаштування в SSOT конфіг  
**Статус:** ⏳ АНАЛІЗ ЗАВЕРШЕНО — Чекаю твого рішення

---

## 📊 МАТРИЦЯ ЗМІН

| # | Поле | Файл | Рядки | Тип | Поточне | Рекомендоване | Тип Змін |
|---|---|---|---|---|---|---|---|
| 1 | `decision.flip.enabled` | domains.yaml | 44 | 🌍 Global | `false` | `true` | Anti-churn gate |
| 2 | `decision.flip.hysteresis_mult` | domains.yaml | 46 | 🌍 Global | `1.3` | `1.5` | Hysteresis increase |
| 3 | `decision.reentry_cooldown_sec` | aurora.yaml | 150 | 🌍 Global | `60` | `300` | Anti-ping-pong |
| 4 | `BTCUSDT.reentry_cooldown_sec` | aurora.yaml | 453 | 🟡 BTC-only | `45` | `300` | Override global |
| 5 | `BTCUSDT.regime_thresholds.*` | aurora.yaml | 466-471 | 🟡 BTC-only | Various | Kill-switch (99.0 for MR/UNCERTAIN) | Regime gates |
| 6 | `BTCUSDT.exit.sl_pct` | aurora.yaml | 479 | 🟡 BTC-only | `0.02` | `0.005` | Tighter SL (0.5%) |
| 7 | `BTCUSDT.exit.regime_tpsl.*` | aurora.yaml | 484-514 | 🟡 BTC-only | Various | See below | TP/SL multipliers |
| 8 | `BTCUSDT.take_profit.tp_low_ratio` | aurora.yaml | 516 | 🟡 BTC-only | `0.5` | `1.0` | Increase TP target |
| 9 | `BTCUSDT.take_profit.tp_high_ratio` | aurora.yaml | 517 | 🟡 BTC-only | `1.0` | `2.0` | Increase TP range |

---

## 🔍 ДЕТАЛЬНІ ЗМІНИ

### **GROUP 1: ГЛОБАЛЬНІ ЗМІНИ (Decision Policy)**

#### 1️⃣ Включити FLIP anti-churn gate
```yaml
# File: config/aurora/domains.yaml
# Line: 44-46

BEFORE:
  flip:
    enabled: false          ← CHANGE
    hysteresis_mult: 1.3    ← CHANGE

AFTER:
  flip:
    enabled: true           ← true (включити anti-churn)
    hysteresis_mult: 1.5    ← 1.5 (посилити hysteresis)
```

**Вплив:** ГЛОБАЛЬНИЙ — торкатиме усіх символів (BTC, ETH, SOL...)  
**Причина:** Reduce churning від marginal reversals  
**Ризик:** Може затримати вихід зі слабких позицій

---

#### 2️⃣ Встановити глобальний reentry_cooldown_sec = 300 сек (5 хвилин)
```yaml
# File: config/aurora/strategies/aurora.yaml
# Line: 150

BEFORE:
    # Re-entry Cooldown (Anti-Ping-Pong Gate)
    reentry_cooldown_sec: 60  # Global default: 60 seconds ← CHANGE

AFTER:
    # Re-entry Cooldown (Anti-Ping-Pong Gate)
    reentry_cooldown_sec: 300  # Global default: 300 seconds (5 mins)
```

**Вплив:** ГЛОБАЛЬНИЙ — торкатиме усіх символів  
**Причина:** Prevent ping-pong entries; wait 5 mins before re-entry  
**Ризик:** Може пропустити good re-entry opportunities

---

### **GROUP 2: BTC-СПЕЦИФІЧНІ ЗМІНИ**

#### 3️⃣ Override BTC reentry_cooldown_sec = 300
```yaml
# File: config/aurora/strategies/aurora.yaml
# Line: 453 (у BTCUSDT секції)

BEFORE:
    BTCUSDT:
      ...
      # Re-entry cooldown: faster for BTC due to high liquidity
      reentry_cooldown_sec: 45  ← CHANGE

AFTER:
    BTCUSDT:
      ...
      # Re-entry cooldown: 5 mins to prevent ping-pong
      reentry_cooldown_sec: 300
```

**Вплив:** ТІЛЬКИ для BTC  
**Причина:** Override global 300s з BTC's 45s (align з anti-churn policy)  
**Ризик:** BTC buys/sells будуть більш розріджені

---

#### 4️⃣ Встановити regime_thresholds для BTC (Kill-switch)
```yaml
# File: config/aurora/strategies/aurora.yaml
# Line: 466-471 (у BTCUSDT.regime_thresholds)

BEFORE:
    BTCUSDT:
      ...
      regime_thresholds:
        HIGH_VOLATILITY: 1.2
        LOW_VOLATILITY: 0.9
        MEAN_REVERSION: 1.05
        DEFAULT: 1.0

AFTER:
    BTCUSDT:
      ...
      regime_thresholds:
        MEAN_REVERSION: 99.0     # Blocked (kill-switch)
        UNCERTAIN: 99.0          # Blocked (kill-switch)
        HIGH_VOLATILITY: 0.1
        LOW_VOLATILITY: 0.09
        TREND_UP: 0.1
        TREND_DOWN: 0.1
        DEFAULT: 0.1
```

**Вплив:** ТІЛЬКИ для BTC  
**Причина:** Block MEAN_REVERSION & UNCERTAIN; allow TREND & VOL  
**Ризик:** Вимикатиме MR сигнали (які давали -20% ROI)

---

#### 5️⃣ Зменшити BTC base SL з 0.02 (2%) → 0.005 (0.5%)
```yaml
# File: config/aurora/strategies/aurora.yaml
# Line: 479 (у BTCUSDT.exit)

BEFORE:
      exit:
        sl_pct: 0.02  ← CHANGE (2%)
        max_hold_sec: 3000
        regime_tpsl:

AFTER:
      exit:
        sl_pct: 0.005  ← 0.005 (0.5%)
        max_hold_sec: 3000
        regime_tpsl:
```

**Вплив:** ТІЛЬКИ для BTC  
**Причина:** Tighter stop-loss (0.5% instead of 2%)  
**Ризик:** Більш tight SLs можуть спричинити false exits

---

#### 6️⃣ Оновити regime_tpsl multipliers для BTC
```yaml
# File: config/aurora/strategies/aurora.yaml
# Line: 495-514 (у BTCUSDT.exit.regime_tpsl)

ПЕРЕВІРИТИ поточні значення и переконатись що вони правильні:

Поточні SL multipliers (LOW_VOLATILITY: 0.75, HIGH_VOLATILITY: 1.35):
  ✓ Низька волатильність: 0.75 × 0.5% = 0.375%
  ✓ Висока волатильність: 1.35 × 0.5% = 0.675%

Поточні TP multipliers:
  ✓ LOW_VOLATILITY: 0.80 × tp_low_ratio (0.5) = 0.4
  ✓ HIGH_VOLATILITY: 1.05 × tp_low_ratio (0.5) = 0.525%

ПІСЛЯ змін tp_low_ratio:
  ✓ LOW_VOLATILITY: 0.80 × 1.0 = 0.80 (80 bps = 0.8%)
  ✓ HIGH_VOLATILITY: 1.05 × 1.0 = 1.05 (105 bps ≈ 1.0%)
```

**Статус:** Поточні мультиплікатори вже оптимальні; зміна буде у tp_low_ratio

---

#### 7️⃣ Підвищити tp_low_ratio для BTC з 0.5 → 1.0
```yaml
# File: config/aurora/strategies/aurora.yaml
# Line: 516 (у BTCUSDT.take_profit)

BEFORE:
      take_profit:
        tp_low_ratio: 0.5  ← CHANGE (50 bps)
        tp_high_ratio: 1.0
        partial_exit_pct: 0.5

AFTER:
      take_profit:
        tp_low_ratio: 1.0  ← 1.0 (100 bps = 1.0%)
        tp_high_ratio: 2.0
        partial_exit_pct: 0.5
```

**Вплив:** ТІЛЬКИ для BTC  
**Причина:** 
  - LOW_VOL: 0.80 × 1.0 = 0.8% TP (було 0.4%)
  - HIGH_VOL: 1.05 × 1.0 = 1.05% TP (було 0.525%)

**Ризик:** Вищі TP targets можуть бути пропущені

---

#### 8️⃣ Підвищити tp_high_ratio для BTC з 1.0 → 2.0
```yaml
# File: config/aurora/strategies/aurora.yaml
# Line: 517 (у BTCUSDT.take_profit)

BEFORE:
        tp_high_ratio: 1.0  ← CHANGE

AFTER:
        tp_high_ratio: 2.0  ← 2.0 (200 bps = 2.0%)
```

**Вплив:** ТІЛЬКИ для BTC  
**Причина:** Expand TP range для більш агресивних exits  
**Ризик:** Як вище

---

## 📍 ФАЙЛИ, ЯКІ ЗМІНЮВАТИМУТЬСЯ

```
1. config/aurora/domains.yaml
   - Line 44: flip.enabled: false → true
   - Line 46: flip.hysteresis_mult: 1.3 → 1.5

2. config/aurora/strategies/aurora.yaml
   - Line 150: reentry_cooldown_sec: 60 → 300 (GLOBAL)
   - Line 453: BTCUSDT.reentry_cooldown_sec: 45 → 300 (BTC-ONLY)
   - Line 466-471: BTCUSDT.regime_thresholds (BTC-ONLY, kill-switch for MR/UNCERTAIN)
   - Line 479: BTCUSDT.exit.sl_pct: 0.02 → 0.005 (BTC-ONLY)
   - Line 516: BTCUSDT.take_profit.tp_low_ratio: 0.5 → 1.0 (BTC-ONLY)
   - Line 517: BTCUSDT.take_profit.tp_high_ratio: 1.0 → 2.0 (BTC-ONLY)
```

---

## 🎯 ЗМІСТ ЗМІН

| Параметр | Глобальний? | BTC-Only? | Статус |
|---|---|---|---|
| flip.enabled | 🌍 **YES** | — | Anti-churn (all symbols) |
| flip.hysteresis_mult | 🌍 **YES** | — | Anti-churn (all symbols) |
| reentry_cooldown_sec (global) | 🌍 **YES** | — | Anti-ping-pong (all symbols) |
| reentry_cooldown_sec (BTCUSDT) | — | 🟡 **YES** | Override for BTC |
| regime_thresholds | — | 🟡 **YES** | Kill-switch for BTC (MR/UNCERTAIN) |
| exit.sl_pct | — | 🟡 **YES** | Tighter SL for BTC |
| regime_tpsl | — | 🟡 **YES** | (Already correct) |
| tp_low_ratio | — | 🟡 **YES** | Increase TP target for BTC |
| tp_high_ratio | — | 🟡 **YES** | Increase TP range for BTC |

---

## ⚠️ РИЗИКИ

1. **Глобальні anti-churn (flip + reentry_cooldown):**
   - ✅ Зменшать churn для усіх символів
   - ⚠️ Але можуть затримати good opportunities для ETH/SOL/DOGE

2. **BTC kill-switch на MR/UNCERTAIN:**
   - ✅ Заблокує MEAN_REVERSION (який давав -20%)
   - ⚠️ Але може пропустити rare valid MR сигнали

3. **BTC тисніший SL (0.5%):**
   - ✅ Менше ризику на позицію
   - ⚠️ Більш false exits на шумі

4. **BTC вищі TP targets:**
   - ✅ Більш гроші на winnings
   - ⚠️ Можуть бути пропущені (market не доходить до цілі)

---

## ✅ ГОТОВО

Маю план всіх змін з точними рядками, файлами та вплив.

**Що далі?**
- ✅ Ти розглядаєш план
- ⏳ Ти даєш ОК або пропонуєш зміни
- 🚀 Я виконую (або адаптую залежно від твого рішення)

**Твоя реакція?** 👇

---

**Document Version:** 1.0  
**Status:** ⏳ AWAITING YOUR DECISION
