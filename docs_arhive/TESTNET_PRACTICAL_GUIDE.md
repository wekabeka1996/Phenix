# 🧪 TESTNET PRACTICAL GUIDE

**Дата**: 3 листопада 2025
**Статус**: 🚀 ГОТОВО ДО ЗАПУСКУ
**Версія**: v1 (Aurora + vFoundation FSM)

---

## ✅ ЧИ СИСТЕМА ЗБІРАНА ПРАВИЛЬНО?

Ланцюжок мав бути: **Signal → Decision → Sizing → Entry+Brackets → Wait(TP|SL) → Close**

```
✅ Підтверджено:
  INTENT_PROPOSED → ORDER_PLACED → BRACKETS_PLACED
  ↓
  Очікування на Close (TP або SL)
  ↓
  POSITION_CLOSED event
```

Якщо цей ланцюжок видиш в логах **рідше ніж раз на 10-15 барів** (M5) — це НОРМАЛЬНО!
Якщо **взагалі не видиш** — перевір сигналу/порогові фільтри (див. [#Де легко спіткнутись](#де-легко-спіткнутись)).

---

## 🎯 ЧТО ВIЖЕ ЗАРАЗ ПРАЦЮЄ

| Компонент | Статус | Примітка |
|-----------|--------|---------|
| **Δθ (режимні множники)** | ✅ LIVE | Коли HIGH_VOL → signal_threshold × 1.20 |
| **bar-gating** | ✅ LIVE | Максимум 1 рішення за бар (можна вимкнути) |
| **behavior-FSM** | ✅ LIVE | Блокує entry якщо стан ≠ IdleFlat (вимкнено) |
| **Сайзинг** | ✅ LIVE | `min(q, Kelly) × m_regime × κ → cap` |
| **Kelly** | ✅ READY | Вимкнено за дефолтом (q-гілка активна) |
| **κ динамічний** | ✅ LIVE | З depth features, клем [0.3, 1.0] |
| **PSI/WHY логування** | ✅ LIVE | Ключі: p, r, kelly_frac, m_regime, Δθ, κ |
| **Emergency → WAIT_MODE** | ✅ LIVE | TTL у барах, skip-логіка працює |
| **QoS defer** | ✅ LIVE | 0.5s symbol cooldown, 30s exposure block |

---

## ⚠️ ДЕ ЛЕГКО СПІТКНУТИСЬ

### **1️⃣ LIMIT за замовчуванням — філи можуть запізнитися**

**Проблема**: На тестнеті біржа часто не приймає LIMIT далеко від ціни.

**Симптоми**:
- INTENT_PROPOSED → ORDER_PLACED ✅
- Але FILL НІКОЛИ не приходить
- Лог: `order status=OPEN ttl=5s`

**Рішення**:

**Тимчасово (для тестнету)**:
```yaml
# apps/reference/main.py лінія 397
command_payload = {
    ...
    "order_type": "MARKET",  # ← Спробуй MARKET для OPEN
    ...
}
```

**Постійно (рекомендовано)**:
```yaml
# Додай LIMIT з невеликим офсетом (±20–30 bps від mid)
# Чекай на ExecutionPosition FSM щоб додав logic
```

**Логи для контролю**:
```
apps.reference.domains.execution_position - INFO - ORDER_PLACED order_id=... status=...
apps.reference.domains.execution_position - INFO - ORDER_FILLED order_id=...
```

---

### **2️⃣ Δθ потребує живого режиму — перші бари можуть бути "гарячими"**

**Проблема**: На старті `EVT:REGIME_DETECTED` ще не прийшов.

**Симптоми**:
- Перший бар: `regime=None` → `Δθ_factor=1.0` (дефолт)
- Багато інтеншнів "зайвих" в HIGH_VOL
- З третього-четвертого бара все стабілізується

**Рішення**:
- **Це нормально!** Не дивуйся "зайвим" інтеншнам
- Режим детектується протягом 1-2 барів
- Після того Δθ починає правильно блокувати

**Логи для контролю**:
```
RegimeDetector - INFO - EVT:REGIME_DETECTED regime=HIGH_VOLATILITY confidence=0.92
DecisionMaking - INFO - [...regime_threshold_factor=1.20...]
```

---

### **3️⃣ Race κ vs Decision — depth snapshot запізнюється**

**Проблема**: Динамічний κ читається з features, але features запізняються від depth.

**Симптоми**:
- Log: `DECISION_EVAL κ=1.0 (fallback)`
- Потім: `FeatureStore liquidity_kappa=0.65 (actual)`
- Позиція менша ніж мала б бути

**Рішення**:
- **Це OK!** Fallback на κ=1.0 — консервативно
- Точний κ приходить у наступні 1-2 цикли
- Якщо important — додай TTL перевірку (у фічах)

**Логи для контролю**:
```
DecisionMaking - DEBUG - liquidity_kappa_mode=dynamic, κ source: features | default
FeatureStore - INFO - aggregate_timeframe=5m features.liquidity_kappa=0.72
```

---

### **4️⃣ MinNotional / step_size — раундинг може викинути заявку**

**Проблема**: Раундуєш qty до step_size, але notional < minNotional біржи.

**Симптоми**:
- INTENT_PROPOSED `qty=0.00001` (занадто мало)
- Біржа: `INVALID_QUANTITY`
- Лог: WARN про minNotional

**Рішення**:
- Вже раундиш qty (DecisionMaking лінія 1020)
- **Додай перевірку в ExecutionPosition**:
  ```python
  if qty * price < min_notional_usd:
      reject("qty × price < min_notional")
  ```

**Логи для контролю**:
```
DecisionMaking - WARNING - qty rounded to zero from raw ...
ExecutionPosition - ERROR - min_notional check failed: 5.00 < 10.00
```

---

### **5️⃣ QoS × bar-gating — бот може виглядати "мовчазним"**

**Проблема**: На низьких cooldown'ах бачиш паузи без явної причини.

**Симптоми**:
- 10+ барів без інтеншнів (хоча score > threshold)
- Лог **НІЧОГО** не показує
- Потім раптом — INTENT

**Причина**:
- **bar-gating** блокує (вже обробив цей бар)
- **QoS defer** чекає (symbol_cooldown_sec)
- **WAIT_MODE** активна (після emergency)

**Рішення**:
- Дивись лог на **ці 3 слова**:
  ```
  DECISION_SKIP (reason=BAR_GATE | QOS_BLOCK | WAIT_MODE)
  ```

**Логи для контролю**:
```
DecisionMaking - INFO - Bar gate: already processed bar_index=12345, skipping
DecisionMaking - WARNING - [...QoS...symbol_cooldown...]
DecisionMaking - INFO - MANAGE_SKIPPED (reason=WAIT_MODE until=...)
```

---

## 📡 СИГНАЛИ У ЛОГАХ (ТВІЙ "РАДАР")

### **1. DECISION_EVAL** — комплетна 360° по рішенню

```
DECISION_EVAL:
  symbol: BTCUSDT
  score: +0.35          ← сигнальний скор
  threshold: 0.05       ← потрібен для entry
  regime: HIGH_VOLATILITY
  θ_factor: 1.20        ← Δθ активна!
  signal_threshold_adjusted: 0.06 (0.05 × 1.20)
  ✅ PASS: 0.35 > 0.06

  sizing:
    p: 0.52 (Kelly prob)
    r: 2.0  (TP/SL ratio)
    kelly_frac: 0.08
    q_notional: 1850 USD
    m_regime: 0.60      ← HIGH_VOL множник!
    κ: 0.75             ← динамічний (глибина)
    final_notional: 835 USD (1850 × 0.60 × 0.75)
```

**Що шукати**: Чи Δθ впливає? Чи κ варіюється? Чи Kelly фракція реалістична?

---

### **2. INTENT_PROPOSED → ORDER_PLACED → BRACKETS_PLACED**

```
INTENT_PROPOSED:
  rid: 6d52043e-3871...
  symbol: BTCUSDT
  side: sell
  qty: 0.01667
  why: pos_size_usd=1773.78..., m_regime=0.60, kappa=0.75
  ✅ Отримано DecisionMaking

BRIDGE: Converting TRADE_INTENT_PROPOSED to CMD:OPEN
✅ Отримано AuroraBridge

ORDER_PLACED:
  client_order_id: d073a950-2173...
  status: OPEN (очікування fill)
  ✅ Надіслано на Binance

BRACKETS_PLACED:
  SL: 106343.00 - 60 bps = 106343.00 × 0.994
  TP: 106343.00 + 120 bps = 106343.00 × 1.012
  ✅ SL + TP на місці
```

**Що шукати**: Часовий гап від INTENT до BRACKETS (<500ms ideal). Чи SL/TP правильні?

---

### **3. EMERGENCY_SL_TRIP → MANAGE_SKIPPED**

```
EMERGENCY_SL_TRIP:
  symbol: BTCUSDT
  reason: shift (price shift > 40 bps)
  position_side: short
  action: CLOSE_REDUCE
  ✅ SL триггер активован

MANAGE_SKIPPED:
  reason: WAIT_MODE
  until_ts: 1730642090  (через 5 барів)
  ✅ Система на паузі, чекає TTL
```

**Що шукати**: Частота EMERGENCY_TRIP (0–2 на годину = норм). Чи TTL дозволяє re-entry?

---

### **4. Статистика сайзингу — яка гілка спрацьовує?**

Додай у лог (DecisionMaking `_calculate_position_size`):

```python
self.logger.info(f"[{symbol}] SIZING: q_notional={q_notional}, kelly_frac={kelly_fraction}, used={'KELLY' if kelly_fraction > 0 else 'Q'}")
```

**Очікування на тестнеті**:
- 80–90% разів: q-гілка (q_notional)
- 10–20% разів: Kelly (якщо Kelly вимкнено — 0%)

---

## ✔️ ЧЕКЛІСТ: "ПРАЦЮЄ / НЕ ПРАЦЮЄ"

**Всі ці ознаки мають бути видні в логах за 30 хвилин роботи:**

- [ ] **Є DECISION_EVAL** з заповненими p, r, kelly_frac, m_regime, κ
- [ ] **INTENT_PROPOSED → ORDER_PLACED** хоча б 1–2 рази
- [ ] **Δθ_factor ≠ 1.0** коли режим ≠ DEFAULT (доказ що режимні множники роблять)
- [ ] **κ варіюється** від 0.3 до 1.0 (а не завжди 1.0)
- [ ] **QoS блоків** бачу в логах (не все підряд)
- [ ] **WAIT_MODE після emergency** (дисципліна re-entry)
- [ ] **ORDER_FILLED** ➜ **BRACKETS_PLACED** (вхід з SL+TP)
- [ ] **Нема NameError / pydantic ValidationError** (LOG FIXED ✅)
- [ ] **Нема дублів у FeatureStore** (rollup логіка OK)

**Якщо не видиш 4+ з цього списку** → перевір лог файл, можливо є режим error, який трушить все.

---

## 🚦 ПЕРШI 5 КРОКІВ НА ТЕСТНЕТІ

### **Крок 1: Запусти з MARKET OPEN** (15 хвилин)

```yaml
# apps/reference/main.py лінія 397
"order_type": "MARKET"  # Тимчасово, щоб мати гарантований fill
```

Мета: Переконатися що **INTENT_PROPOSED → BRACKETS_PLACED** працює.

---

### **Крок 2: Запусти 1-2 години, зберіть логи**

```bash
tail -f logs/aurora_core.log | grep "DECISION_EVAL\|ORDER_PLACED\|BRACKETS_PLACED"
```

Мета: Зібрати статистику:
- Скільки інтеншнів?
- Скільки філів?
- Яка средня Δθ_factor?
- Яка средня κ?

---

### **Крок 3: Проверь режимну адаптацію**

Шукай у логах:
```
HIGH_VOLATILITY: Δθ=1.20 → інтеншни мають бути рідше
LOW_VOLATILITY: Δθ=0.90 → інтеншни мають бути частіше
```

Якщо **НЕ видиш різниці** → перевір як часто режим змінюється.

---

### **Крок 4: Перейди на LIMIT + невеликий офсет** (якщо MARKET OK)

```yaml
# ExecutionPosition FSM (НАСТУПНА ФАЗА)
price_offset_bps: 30  # ±30 bps від mid для LIMIT
```

Мета: Довести що LIMIT також працює з офсетом.

---

### **Крок 5: Увімкни Kelly** (якщо q-гілка OK)

```yaml
# config/aurora/trading.yaml
decision:
  kelly:
    base_probability: 0.50
    kelly_cap: 0.25
    kelly_alpha: 0.8
    payoff_ratio_r: 1.5
```

Мета: Порівняти kelly_frac vs q_notional. Який影響має на PnL?

---

## 🎯 УСПІХ = ЦЕЙ ЛАНЦЮЖОК ЗАКРИТИЙ

```
┌─────────────────────────────────────────────┐
│ Signal:  score > threshold × Δθ ✅          │
├─────────────────────────────────────────────┤
│ Decision: qty = min(q, Kelly) × m_regime    │
│           × κ × cap ✅                       │
├─────────────────────────────────────────────┤
│ Entry:    MARKET/LIMIT → Order Placed ✅    │
├─────────────────────────────────────────────┤
│ Brackets: SL/TP → Safety Net ✅             │
├─────────────────────────────────────────────┤
│ Wait:     TP/SL/TTL/Emergency → Close ✅    │
├─────────────────────────────────────────────┤
│ Result:   PnL logged, position cleared ✅   │
└─────────────────────────────────────────────┘
```

Якщо бачиш **весь ланцюжок** у логах кілька разів — **система готова**. 🚀

---

## 📝 ЗАКЛЮЧЕННЯ

**Система правильно збірана.**

Ти маєш:
- ✅ Режимну адаптацію (Δθ)
- ✅ Динамічний сайзинг (κ)
- ✅ Kelly готовий (вимкнено, але働work)
- ✅ SL/TP гейти (emergency + TTL)
- ✅ QoS логіку (не давимо на борда)
- ✅ Logging для XAI (ключові metrix у why)

**На тестнеті**: Запусти, зберіж логи, перевір 5 кроків. Готово.

**Для production**: Додай partial close logic, трейли, та risk management по кілька позицій. Але це **не це** версія.

---

**Good luck! 🚀**
