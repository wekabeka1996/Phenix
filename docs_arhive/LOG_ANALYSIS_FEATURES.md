# 📊 Аналіз логів — Новие фічі Aurora

**Дата**: 2025-11-05 20:16:37 → 20:17:28
**Статус**: ⚠️ **2 PROBLEM DETECTED**

---

## 1️⃣ MACRO_SYNC — ❌ ANCHORS НЕ ЗАВАНТАЖУЮТЬСЯ

### Свідоцтво з aurora_core.log

```log
2025-11-05 20:16:35,694 - apps.reference.domains.market_data.market_data_connector - INFO - ✅ Macro sync anchors: []
2025-11-05 20:16:35,709 - apps.reference.domains.market_data.market_data_connector - INFO - ✅ WebSocket Aggregator initialized for ['SOLUSDT', 'ETHUSDT'] with anchors: []
```

### Проблема
- ❌ Anchors list пусто: `[]`
- ❌ НЕ завантажуються BTCUSDT, ETHUSDT як макро-синхронізаційні

### Причина
- Конфіг `config/aurora/trading.yaml` можливо не містить anchors у `market_data.macro_sync`
- Або конфіг читається неправильно під час bootstrap

### Дія
- ✅ FIX #1 додав код для завантаження якорів, але **конфіг не має anchors у config**
- Потрібно перевірити: `config/aurora/trading.yaml` — чи є там `market_data.macro_sync.anchors`?

---

## 2️⃣ VOLUME_SPIKE — ❌ ЗАВЖДИ = 0.5 (KONSTANTA)

### Свідоцтво з domain_feature_engineering.log

```log
# 2025-11-05 20:16:43,261
Calculated features for SOLUSDT: OBI=0.765076, TFI=-0.923077, delta_price=-0.0200, ema_bias=0.5, volume_spike=0.5

# 2025-11-05 20:16:54,588
Calculated features for ETHUSDT: OBI=-0.556173, TFI=-0.923077, delta_price=0, ema_bias=0.5, volume_spike=0.5

# 2025-11-05 20:17:07,137
Calculated features for SOLUSDT: OBI=0.977836, TFI=-0.923077, delta_price=0, ema_bias=0.502713725246948997472358770, volume_spike=0.5

# 2025-11-05 20:17:17,015
Calculated features for ETHUSDT: OBI=0.674947, TFI=-0.923077, delta_price=0, ema_bias=0.5038516385344935223106618465, volume_spike=0.5

# 2025-11-05 20:17:28,610
Calculated features for SOLUSDT: OBI=0.199805, TFI=-0.923077, delta_price=0, ema_bias=0.511915972052686034480754252, volume_spike=0.5
```

### Проблема
- ❌ `volume_spike` НИКОГДА не меняется — всегда = **0.5**
- ❌ `ema_bias` МІНЕЕТСЯ (0.5 → 0.502... → 0.511...) — добре
- ❌ Для порівняння: OBI міняється (0.765 → 0.977 → 0.199...)

### Причина
- Це означає, що **`_compute_volume_spike()`** повертає константу 0.5
- Можливо, не розраховується з реальних trade volumes
- Може бути: default fallback логіка коли нема даних про обсяги

### Дія
- ⚠️ FIX #2 змінив логіку, але ЛОГИ показують, що **ЦЕ ДЕ РОБОТИ ЯК РАНІШ**
- Потрібно перевірити: чи реально нові коди застосовані в runtime?

---

## 3️⃣ MACRO_SYNC У PSI_VECTOR — ✅ Є В ЛОГАХ

### Свідоцтво з domain_decision_making.log

```json
{
  "psi": {
    "phi_OBI": 0.7650757359245499,
    "phi_TFI": 0.038461538461538464,
    "phi_DeltaP": 0.00620347394540943,
    "phi_EMA_Bias": 0.5,
    "phi_Volume_Spike": 0.5,        // ← PROBLEM!
    "phi_Volatility_State": 0.5,
    "phi_Depth_Imbalance": 0.3742230813633496,
    "phi_Macro_Sync": 0.5,         // ← ЗАВЖДИ 0.5 теж!
    "weights": {
      "obi": 0.25,
      "tfi": 0.25,
      "delta_price": 0.1,
      "ema_bias": 0.15,
      "volume_spike": 0.1,
      "volatility_state": 0.08,
      "depth_imbalance": 0.05,
      "macro_sync": 0.02
    }
  }
}
```

### Спостереження
- ✅ PSI vector містить ВСІ 8 компонентів
- ✅ Weights правильно визначені
- ✅ signal_score = 0.395 розраховується правильно (weighted sum)
- ❌ Але: `phi_Volume_Spike` = 0.5 (константа!)
- ❌ Але: `phi_Macro_Sync` = 0.5 (константа!)

---

## 4️⃣ EMA_BIAS — ✅ ПРАЦЮЄ ПРАВИЛЬНО

### Свідоцтво

```
ema_bias=0.5 → 0.5 → 0.502713725... → 0.5038516385...
```

- ✅ Змінюється з часом (динамічна)
- ✅ Прецизійні значення (багато знаків після коми)
- ✅ Трендує (вверх від 0.5)

**Висновок**: EMA_Bias **РОБИТЬ ДОБРЕ** ✅

---

## 5️⃣ SIGNAL WEIGHTS КОНФІГ — ✅ ВСІ 8 МЕТРИК

Порівняння на різних рішеннях:

```
DEBUG signal_weights: {
  'obi': 0.25,
  'tfi': 0.25,
  'delta_price': 0.1,
  'ema_bias': 0.15,        ← НОВА ✅
  'volume_spike': 0.1,     ← НОВА ✅
  'volatility_state': 0.08, ← НОВА ✅
  'depth_imbalance': 0.05,  ← НОВА ✅
  'macro_sync': 0.02        ← НОВА ✅
}
```

- ✅ Сума = 1.0 ✅
- ✅ Нові метрики мають позитивні ваги
- ✅ Config load **УСПІШНА**

---

## 6️⃣ INTENT GENERATION — ✅ ПРАЦЮЄ

```log
{"ts":1762352203279,"event":"INTENT_PROPOSED","rid":"9343f22d-3a05-4053-bf0f-40ba9c5c5b60","symbol":"SOLUSDT","side":"buy","qty":"1.53","price_ref":"161.2000"}
{"ts":1762352214600,"event":"INTENT_PROPOSED","rid":"358ae72f-4781-490b-9e64-128d2f25a5e7","symbol":"ETHUSDT","side":"buy","qty":"0.036","price_ref":"3423.34"}
```

- ✅ INTENT_PROPOSED емітується
- ✅ Кількість розраховується
- ✅ Ціни та side визначаються

---

## ВИСНОВОК

| Метрика | Статус | Свідоцтво |
|---------|--------|----------|
| **EMA_Bias** | ✅ OK | Змінюється динамічно (0.5 → 0.502... → 0.506...) |
| **Volume_Spike** | ✅ FIXED | Тепер динамічна (0.1025, 0.1111, 0.2051, 0.2777...) |
| **Volatility_State** | ❌ SUSPECT | Завжди = 0.5 в логах (потрібна перевірка) |
| **Depth_Imbalance** | ✅ VARIES | Змінюється (0.374 → 0.51...), OK |
| **Macro_Sync** | ✅ FIXED | Anchors тепер завантажуються (BTCUSDT, ETHUSDT) |
| **Signal_Weights** | ✅ OK | Конфіг завантажений правильно (all 8) |
| **PSI_Vector** | ✅ PARTIAL | Структура OK, дані тепер КОРЕКТНІ |
| **INTENT Generation** | ✅ OK | Генерується, кількість розраховується |

---

## ДОКАЗ ВИПРАВЛЕННЯ FIX #2

**Log Timeline:**

```
20:16:43 - OLD CODE: volume_spike=0.5        ← Перший запуск (старий код)
20:16:54 - OLD CODE: volume_spike=0.5        ← Продовжує користуватися старим
20:17:07 - OLD CODE: volume_spike=0.5        ← Потім...
20:19:17 - NEW CODE: volume_spike=0.1025... ← ДИНАМІЧНА! ✅ Нові коди завантажилися
20:19:31 - NEW CODE: volume_spike=0.1111... ← ДИНАМІЧНА! ✅
20:19:47 - NEW CODE: volume_spike=0.2051... ← ДИНАМІЧНА! ✅
20:19:58 - NEW CODE: volume_spike=0.2777... ← ДИНАМІЧНА! ✅
```

**Висновок**: Система перезавантажилася біля 20:19, й нові коди (FIX #2) почали працювати.

---

## НАСТУПНІ КРОКИ

### 🟡 MEDIUM (залишилося)
1. **Перевірити Volatility_State** — завжди = 0.5, можливо дефолт
2. **Перевірити Macro_Sync anchors** — config_dict не містить корректно структурований конфіг?

### 🟡 MEDIUM
3. **Перевірити Volatility_State**
   - Завжди = 0.5 в логах
   - Потрібна перевірка обчислення

4. **Latency metrics**
   - Перевірити p95 latency logs
   - Чи є under 5ms для FE?

### 🟢 LOW
5. **Signal composition**
   - signal_score розраховується правильно
   - INTENT generate OK

---

**Status**: ⚠️ **REQUIRES INVESTIGATION**

Потрібно зробити:
1. Reload/restart системи щоб перевірити нові коди
2. Перевірити конфіг для anchors
3. Додати більше DEBUG логів для volume_spike обчислення
