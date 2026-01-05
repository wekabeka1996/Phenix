# Аналіз блокування ордерів XRP та DOGE

**Дата:** 4 січня 2026 р.  
**Час аналізу:** ~16:00-16:02 UTC  
**Статус:** Всі спроби відкриття ордерів XRP та DOGE були **ЗАБЛОКОВАНІ**

---

## Резюме про причини блокування

Виявлено **5 основних причин** (в порядку частоти):

| Код | Причина | Кількість | Статус |
|-----|---------|-----------|--------|
| **NRR-026** | Trend = UNKNOWN (недостатня підтвердження тренду) | ⭐⭐⭐ частий | **КРИТИЧНА** |
| **ARBITRATION_REJECT** | Strategy not assigned to symbol | ⭐⭐ часто | **КРИТИЧНА** |
| **NRR-011** | Trading not allowed by risk manager | ⭐ рідко | Вторинна |
| **QoS: rate_limit** | Перевищено лімітом інтентів у вікні | ⭐ рідко | Вторинна |
| **QoS: cooldown** | Символ у cooldown (3s) | ⭐ рідко | Вторинна |

---

## Деталь 1: NRR-026 (INSUFFICIENT_TREND_CONFIRMATION) — Trend = UNKNOWN

### Описання
Directional Sanity Gate блокує LONG ордери, коли:
- `trend_dir = "UNKNOWN"` (неможливо визначити напрямок)
- Параметри конфігу в `config/aurora/domains.yaml`:
  ```yaml
  directional_sanity:
    enabled: true
    min_abs_delta_price: 0.0      # будь-який delta_price
    min_confidence: 0.0            # будь-яка confidence
    consecutive_bars: 2            # потрібно 2 послідовні бари
  ```

### Проблема
Features приходять **нормально** (delta_price є дані), але:
- Логи Feature Engineering показують delta_price для XRP та DOGE в кожному тику
- Приклад: `"delta_price": "-0.00001"` для DOGE, `"delta_price": "-0.0004"` для XRP
- Але в decision_making тренд залишається `UNKNOWN`

**Ймовірна причина:** `_delta_price_hist` не накопичує дані достатньо швидко, або є баг у логіці накопичення історії.

### Логи
```
16:00:09,651 - [XRPUSDT] SAFETY_GATES: DENY LONG trend=UNKNOWN reason=NRR-026
16:00:14,626 - [DOGEUSDT] SAFETY_GATES: DENY LONG trend=UNKNOWN reason=NRR-026
16:00:19,637 - [XRPUSDT] SAFETY_GATES: DENY LONG trend=UNKNOWN reason=NRR-026
16:01:39,641 - [DOGEUSDT] SAFETY_GATES: DENY LONG trend=UNKNOWN reason=NRR-026
```

---

## Деталь 2: ARBITRATION_REJECT — Strategy not assigned to symbol

### Описання
CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION перевіряє:
- чи призначена якась **стратегія** до символу XRP/DOGE
- якщо нема стратегії → блокування з кодом `strategy_not_assigned_to_symbol`

### Проблема
**Жодна стратегія не назначена до XRP та DOGE**

Для порівняння:
- BTCUSDT, ETHUSDT, SOLUSDT → інтенти проходять успішно
- XRPUSDT, DOGEUSDT → інтенти блокуються на arbitration

### Логи
```
16:01:19,634 - [DOGEUSDT] TRADE_INTENT_BLOCKED: Strategy arbitration rejected: 
                          ARBITRATION_REJECT:strategy_not_assigned_to_symbol
16:01:44,645 - [DOGEUSDT] TRADE_INTENT_BLOCKED: Strategy arbitration rejected: 
                          ARBITRATION_REJECT:strategy_not_assigned_to_symbol
16:01:49,640 - [XRPUSDT] TRADE_INTENT_BLOCKED: Strategy arbitration rejected: 
                          ARBITRATION_REJECT:strategy_not_assigned_to_symbol
```

---

## Деталь 3: NRR-011 (Risk Manager Rejection)

### Описання
Risk Manager блокує ордери з причиною **"Trading not allowed by risk manager"**

### Логи
```
16:01:54,665 - Trade intent for DOGEUSDT rejected: Trading not allowed by risk manager (NRR: NRR-011)
16:01:54,670 - Trade intent for XRPUSDT rejected: Trading not allowed by risk manager (NRR: NRR-011)
```

Це може бути:
- `_precheck_exposure_cache()` — перевищена `max_exposure_usd` по символу
- Або інша hard gate у Risk Management

---

## Деталь 4: QoS Rejection — Rate Limit & Cooldown

### Rate Limit Exceeded
```
16:01:19,636 - [XRPUSDT] QoS REJECT: rate_limit_exceeded_10_intents_in_window
16:01:24,635 - [DOGEUSDT] QoS REJECT: rate_limit_exceeded_12_intents_in_window
```

**Причина:** Система генерує занадто багато інтентів занадто швидко для одного символу.

### Symbol Cooldown
```
16:01:19,633 - [DOGEUSDT] QoS REJECT: symbol_cooldown_active_3.0s_remaining_limit=3s
16:01:19,637 - [XRPUSDT] QoS REJECT: symbol_cooldown_active_3.0s_remaining_limit=3s
```

**Причина:** Символ у cooldown-стані (3 секунди) після попередньої спроби.

---

## Потік даних — де все обривається

### ✅ Що працює:
1. **Feature Engineering** генерує фічи з delta_price
2. **Decision Making** запускає `_make_decision_for_symbol()`
3. Signal Score > threshold
4. **INTENT_PROPOSED** емітується успішно

### ❌ Де блокується:

```
DECISION_EVAL (signal OK)
    ↓
INTENT_PROPOSED (емітується)
    ↓
Risk Manager + Arbitration Gate
    ↓
┌─────────────────────────────────────────┐
│ XRPUSDT / DOGEUSDT:                     │
│ ❌ NRR-026 (trend=UNKNOWN)              │
│ ❌ ARBITRATION_REJECT (no strategy)     │
│ ❌ NRR-011 (trading not allowed)        │
│ ❌ QoS rate limit                       │
│ ❌ QoS cooldown                         │
└─────────────────────────────────────────┘
    ↓
❌ Order BLOCKED
```

---

## Рекомендації для усунення

### 1️⃣ Невідкладно: Assign Strategy to XRP & DOGE
**Файл:** `config/aurora/strategies.yaml` або `config/aurora/domains.yaml`

Додати маршрутизацію:
```yaml
strategies:
  mean_reversion:
    symbols:
      - BTCUSDT
      - ETHUSDT
      - SOLUSDT
      - DOGEUSDT    # ← ДОДАТИ
      - XRPUSDT     # ← ДОДАТИ
```

**Приоритет:** 🔴 **КРИТИЧНА** (ARBITRATION_REJECT блокує абсолютно всі ордери)

---

### 2️⃣ Високий: Debug `_delta_price_hist` accumulation

**Файл:** `apps/reference/domains/decision_making/decision_making.py` (строки ~3217-3240)

Добавити логування:
```python
# DM-DIR-FORENSIC-02: Debug trend_dir computation
self.logger.debug(
    f"[{symbol}] delta_price_hist_debug: len={len(hist) if hist else 0}, "
    f"values={list(hist)[-5:] if hist else []}, "
    f"consecutive={consecutive}, trend_dir={trend_dir}"
)
```

**Гіпотеза:** Історія `_delta_price_hist` не накопичує дані достатньо швидко для заповнення `consecutive_bars=2`.

**Приоритет:** 🟠 **ВИСОКА** (NRR-026 — друга за частотою причина)

---

### 3️⃣ Середній: Review Risk Manager exposure cache

**Файл:** `apps/reference/domains/decision_making/decision_making.py` (метод `_precheck_exposure_cache`)

Перевірити:
- Чи правильно обчислюється `current_exposure_usd` для XRP/DOGE?
- Чи `max_exposure_usd` занадто низький?

**Приоритет:** 🟡 **СЕРЕДНЯ** (NRR-011 виникає рідко, можливо вже розв'язана)

---

### 4️⃣ Низький: Adjust QoS thresholds

**Файл:** `config/aurora/domains.yaml`

Додати per-symbol QoS конфіг:
```yaml
qos_gates:
  rate_limit:
    window_sec: 5
    max_intents_per_symbol: 20  # XRP/DOGE генерують багато інтентів
  cooldown:
    symbol_cooldown_sec: 1      # зменшити з 3s
```

**Приоритет:** 🟡 **НИЗЬКА** (QoS — побічна причина)

---

## Таблиця покроково до усунення

| Крок | Дія | Файл | Очікуваний результат |
|------|-----|------|----------------------|
| 1 | Add XRP/DOGE to strategy routing | `config/aurora/strategies.yaml` | ARBITRATION_REJECT зникає |
| 2 | Debug `_delta_price_hist` логіка | `decision_making.py:3220+` | trend_dir отримує UP/DOWN |
| 3 | Перевірити risk exposure | `decision_making.py:_precheck_exposure_cache` | NRR-011 розв'язується |
| 4 | Опціонально: tune QoS | `config/aurora/domains.yaml` | QoS limit узгоджується |

---

## Додаток: Порівняння з успішними символами

### BTCUSDT (✅ Працює)
```
16:01:34 - DECISION_EVAL: signal_score=0.456, threshold=0.105 ✅
16:01:34 - INTENT_PROPOSED: qty=0.004, price=91300.5 ✅
```

### DOGEUSDT (❌ Блокується)
```
16:01:39 - DECISION_EVAL: signal_score=0.552, threshold=0.09 ✅ (PASSED!)
16:01:39 - INTENT_PROPOSED: qty=1513, price=0.15157 ✅ (PASSED!)
16:01:44 - TRADE_INTENT_BLOCKED: ARBITRATION_REJECT ❌ (FAILED!)
```

**Висновок:** DOGE проходить decision_making, але падає на arbitration.

---

## Висновок

**Головна проблема:** ARBITRATION_REJECT (strategy_not_assigned_to_symbol)

**Вторинні проблеми:** 
- NRR-026 (trend=UNKNOWN) — можливий баг у накопичуванні історії
- NRR-011 (risk_manager) — можливо вже розв'язана або низька exposure

**Рекомендована послідовність усунення:**
1. ✅ Добавити XRP/DOGE до стратегій (навмисне блокування)
2. ✅ Debug `_delta_price_hist` (можливий баг)
3. ✅ Перевірити risk exposure limits
