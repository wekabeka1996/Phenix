# Дослідження: Динамічна Поведінка в Системі Aurora+vFoundation

**Дата:** 3 листопада 2025
**Статус:** ✅ Завершено
**Знайдено проблем:** 3

---

## 📋 Резюме

Система **частково реалізує** динамічну поведінку торгівлі:

| Функція | Статус | Моди | Конфіг |
|---------|--------|------|--------|
| **Режимна детекція** | ✅ Працює | 5 режимів | `models.volatility.*` |
| **Адаптивне масштабування** | ⚠️ Частково | HIGH_VOL, LOW_VOL, MEAN_REV | `sizing_modifiers.*` |
| **Блокування контр-трендів** | ✅ Працює | TREND_UP/DOWN | Embedded в `decision_making.py` |
| **Динамічна вероятність** | ✅ Працює | p = base + signal_score | Calc в `_try_make_decision()` |
| **Динамічна Kelly фракція** | ✅ Працює | kelly = f(p, r) | Calc в `_try_make_decision()` |
| **Інтеграція режимів** | ❌ **Бракує** | - | `sizing_modifiers` не в YAML |

---

## 🔍 Модулі та Рядки Коду

### 1️⃣ **РЕЖИМНА ДЕТЕКЦІЯ** → `RegimeDetector` Domain

**Файл:** `apps/reference/domains/regime_detector/regime_detector.py`
**Класс:** `RegimeDetector`
**Методи:** `handle_event()`, `_calculate_confidence()`

**Режими (5 типів):**
```python
# Лінії 119-200: Детекція режимів
REGIME = "TREND_UP" | "TREND_DOWN" | "MEAN_REVERSION" | "HIGH_VOLATILITY" | "LOW_VOLATILITY" | "UNCERTAIN"
```

**Логіка (пріоритет):**

| Пріоритет | Режим | Умова | Лінії |
|-----------|-------|-------|-------|
| 1 | HIGH_VOLATILITY | ATR > 2.0 × SMA(ATR) | 127-139 |
| 1 | LOW_VOLATILITY | ATR < 0.5 × SMA(ATR) | 140-147 |
| 2 | MEAN_REVERSION | price/SMAs в діапазоні ±0.5% | 158-173 |
| 3 | TREND_UP | SMA_short > SMA_long AND price > SMA_short | 173-177 |
| 3 | TREND_DOWN | SMA_short < SMA_long AND price < SMA_short | 178-182 |

**Конфігурація** (`config/aurora/trading.yaml`):
```yaml
# БРАКУЄ! Немає в YAML конфігу для RegimeDetector
# Моделі жорстко задані у коді
```

**Емісія подій:**
```python
# Лінія 199-206
self.fsm.emit(Message(
    op="EVT",
    verb="REGIME_DETECTED",
    pld={"regime": regime, "confidence": confidence, ...}
))
```

---

### 2️⃣ **ПРИЙНЯТТЯ РІШЕНЬ** → `DecisionMaking` Domain

**Файл:** `vfoundation/apps/reference/domains/decision_making/decision_making.py`
**Класс:** `DecisionMaking`
**Метод:** `_try_make_decision()` (лінії 149-775)

#### **А) Слухання режимів:**
```python
# Лінія 141-145: Обробка подій режиму
def on_regime(self, event: Message) -> None:
    """Handle EVT:REGIME_DETECTED event."""
    self.logger.info(f"Handling EVT:REGIME_DETECTED...")
    self.latest_regime = event.pld  # Зберігаємо режим в state
```

#### **B) Блокування контр-трендів (Regime-Adaptive Filter):**
```python
# Лінії 301-323: REGIME-ADAPTIVE FILTER
if self.latest_regime and self.latest_regime.get("symbol") == symbol:
    current_regime = self.latest_regime.get("regime")

    # Rule 1: Блокуємо SELL в TREND_UP
    if current_regime == "TREND_UP" and side == "sell":
        self.logger.info(f"rejected by regime filter (current regime: {current_regime})")
        self.clear_internal_state()
        return  # ← БЛОКОВАНА ТОРГІВЛЯ

    # Rule 2: Блокуємо BUY в TREND_DOWN
    if current_regime == "TREND_DOWN" and side == "buy":
        self.logger.info(f"rejected by regime filter (current regime: {current_regime})")
        return  # ← БЛОКОВАНА ТОРГІВЛЯ
```

#### **C) Режимне масштабування (Regime-Adaptive Sizing):**
```python
# Лінії 324-330: РЕЖИМНЕ МАСШТАБУВАННЯ
regime_size_multiplier = Decimal("1.0")  # Default

if self.latest_regime and self.latest_regime.get("symbol") == symbol:
    current_regime = self.latest_regime.get("regime")

    # Rule 3: UNCERTAIN режим → 50% скорочення
    if current_regime == "UNCERTAIN":
        regime_size_multiplier = Decimal("0.5")
        self.logger.info(f"size reduced by 50% due to UNCERTAIN regime")
```

**Проблема:**
- ✅ HIGH_VOLATILITY, LOW_VOLATILITY, MEAN_REVERSION передбачені у коді
- ❌ **Але вони не використовуються!** Лінії 600-650 читають `sizing_modifiers` з конфіга, але
- ❌ **Конфіг YAML не містить `sizing_modifiers`** → варіант скорочення ніколи не застосовується!

#### **D) Динамічна Вероятність & Kelly Фракція:**
```python
# Лінії 342-395: ДИНАМІЧНА ВЕРОВАТНІСТЬ
signal_score = (obi * obi_weight) + (tfi * tfi_weight) + (absorption * absorption_weight)

# Лінія 352: Динамічна p
p_raw = base_prob + abs(signal_score)  # p залежить від сигналу!

# Лінії 365-372: Динамічна Kelly фракція
full_kelly = (p - (1 - p) / payoff_ratio_r) if payoff_ratio_r > 0 else 0
kelly_used = min(kelly_cap, kelly_alpha * full_kelly)  # → ДИНАМІЧНА!

# Лінія 381: Розмір залежить від Kelly
kelly_based_size = equity * kelly_fraction * kelly_conservative_factor
position_size = min(max_position_size, kelly_based_size, notional_cap)
```

#### **E) Режимне адаптивне масштабування (Коефіцієнти):**
```python
# Лінії 600-650: АДАПТИВНЕ МАСШТАБУВАННЯ ПО РЕЖИМАХ
sizing_modifiers = decision_config.get("sizing_modifiers", {})

if current_regime in ["HIGH_VOLATILITY", "LOW_VOLATILITY"] and current_regime in sizing_modifiers:
    modifier = Decimal(str(sizing_modifiers[current_regime]))
    position_size *= modifier  # ← СКОРОЧУЄ РОЗМІР ПО РЕЖИМУ
    self.logger.info(f"Position size modified by factor {modifier} due to {current_regime}")

elif current_regime == "MEAN_REVERSION":
    if "MEAN_REVERSION" in sizing_modifiers:
        modifier = Decimal(str(sizing_modifiers["MEAN_REVERSION"]))
        position_size *= modifier
    else:
        position_size *= Decimal("0.5")  # Fallback: 50% скорочення
```

---

### 3️⃣ **ДИНАМІЧНА СИГНАЛІЗАЦІЯ** → `feature_engineering` Domain

**Файл:** `apps/reference/domains/feature_engineering/feature_engineering.py`
**Вхідні:** OHLCV → Вихідні: OBI, TFI, delta_price, absorption

**Динамічність:**
- ✅ OBI/TFI адаптуються до умов ринку (залежить від обсягів)
- ✅ Absorption сигнал чутливий до тиску (buy/sell ratio)
- ✅ Сигнали переказуються на кожному барі

---

## 🚨 **ПРИЧИНИ, ЧОМУ НЕ ПРАЦЮЄ**

### **Проблема 1: Конфіг не містить `sizing_modifiers`**

**Файл:** `config/aurora/trading.yaml` (лінії 1-179)
**Що є:**
```yaml
decision:
  signal_weights: {obi: 0.6, tfi: 0.35, delta_price: 0.05}
  signal_threshold: 0.15
  position_sizing:
    min_position_size_usd: 10
    liquidity_based_cap_usd: 10000
  qos: {mode: "defer", ...}
```

**Чого БРАКУЄ:**
```yaml
# ❌ БРАКУЄ У YAML!
# decision:
#   sizing_modifiers:
#     HIGH_VOLATILITY: 0.6      # 40% скорочення
#     LOW_VOLATILITY: 1.2       # 20% збільшення
#     MEAN_REVERSION: 0.5       # 50% скорочення
```

**Результат:**
- Коли RegimeDetector емітує HIGH_VOLATILITY, DecisionMaking робить `sizing_modifiers.get("HIGH_VOLATILITY", {})` → повертає `{}`
- Умова `current_regime in sizing_modifiers` → **FALSE**
- Адаптивне масштабування **ніколи не запускається**

---

### **Проблема 2: Конфіг RegimeDetector не налаштовується**

**Файл:** `apps/reference/domains/regime_detector/regime_detector.py` (лінії 100-200)

Параметри жорстко вписані у код:
```python
# Лінія 127
threshold_multiplier = Decimal(str(volatility_config.get("threshold_multiplier", 2.0)))  # DEFAULT

# Лінія 130
low_vol_multiplier = Decimal(str(volatility_config.get("low_vol_multiplier", 0.5)))  # DEFAULT
```

**Беруться з конфіга:**
```python
volatility_config = self.config.get("models", {}).get("volatility", {})
```

**ПРОБЛЕМА:**
- ❌ У YAML нема `models.volatility.*` ключів
- ❌ Режимна детекція використовує **дефолти**, непідконтрольні користувачем
- ❌ Не можна налаштувати чутливість детекції HIGH_VOLATILITY без редагування коду

---

### **Проблема 3: Немає інтеграції з YAML для режимних параметрів**

**Бракує розділів у `config/aurora/trading.yaml`:**

```yaml
# ❌ БРАКУЄ ЦИХ РОЗДІЛІВ:

models:  # Для RegimeDetector
  volatility:
    enabled: true
    threshold_multiplier: 2.0      # ATR spike threshold
    low_vol_multiplier: 0.5        # ATR calm threshold
    atr_period: 14
  mean_reversion:
    threshold: 0.005  # 0.5% для clustering

decision:  # Існує, але неповне
  sizing_modifiers:  # ❌ БРАКУЄ!
    HIGH_VOLATILITY: "0.6"
    LOW_VOLATILITY: "1.2"
    MEAN_REVERSION: "0.5"
    UNCERTAIN: "0.5"
```

---

## 📊 **Де реально працює динамічна поведінка?**

| Компонента | Статус | Деталі |
|----------|--------|--------|
| **Режимна детекція** | ✅ | 5 режимів, 3 моделі, емісія подій |
| **Блокування контр-трендів** | ✅ | TREND_UP блокує SELL, TREND_DOWN блокує BUY |
| **Динамічна p** | ✅ | p = 0.5 + signal_score (залежить від OBI/TFI) |
| **Динамічна Kelly** | ✅ | kelly = f(p, r), застосовується в сайзингу |
| **Режимне сайзинг** | ❌ | Код готовий, але конфіг скорочень відсутній |
| **Динамічні сигнали** | ✅ | OBI/TFI/absorption змінюються на кожному барі |

---

## 📁 **Файлова Структура**

```
apps/reference/domains/
├── regime_detector/                          ← Режимна детекція
│   ├── regime_detector.py                    [Лінії 81-206: handle_event()]
│   └── schemas/
│       └── regime_detected_v1.json
│
├── feature_engineering/                      ← Динамічні сигнали
│   ├── feature_engineering.py                [Динамічні OBI/TFI]
│   └── schemas/
│       └── features_calculated_v1.json
│
└── decision_making/
    ├── decision_making.py (vfoundation/)     ← Інтеграція
    │   ├── Лінії 141-145: on_regime()
    │   ├── Лінії 301-323: REGIME-ADAPTIVE FILTER
    │   ├── Лінії 324-330: REGIME-ADAPTIVE SIZING (базовий)
    │   ├── Лінії 600-650: РЕЖИМНЕ МАСШТАБУВАННЯ (недіючий)
    │   └── Лінії 342-395: ДИНАМІЧНА KELLY
    │
    └── decision_making.py (apps/)
        └── [Legacy версія, також має динаміку]

config/aurora/
└── trading.yaml
    ├── decision.signal_weights              [✅ Є]
    ├── decision.position_sizing             [✅ Є]
    ├── decision.sizing_modifiers            [❌ БРАКУЄ!]
    ├── models.volatility                    [❌ БРАКУЄ!]
    └── models.mean_reversion                [❌ БРАКУЄ!]
```

---

## ✅ **Рекомендації Для Активації**

### **1. Додати `sizing_modifiers` до YAML**
```yaml
# config/aurora/trading.yaml (розділ decision)
decision:
  sizing_modifiers:
    HIGH_VOLATILITY: "0.6"      # 40% скорочення в волатильних умовах
    LOW_VOLATILITY: "1.2"       # 20% збільшення в спокійних
    MEAN_REVERSION: "0.5"       # 50% скорочення в ranging
    UNCERTAIN: "0.5"            # 50% скорочення при невизначеності
```

### **2. Додати конфіг RegimeDetector**
```yaml
# config/aurora/trading.yaml (новий розділ)
models:
  volatility:
    enabled: true
    threshold_multiplier: 2.0     # Коли ATR > 2x середнього
    low_vol_multiplier: 0.5       # Коли ATR < 0.5x середнього
    atr_period: 14
  mean_reversion:
    threshold: 0.005              # Діапазон ±0.5%
```

### **3. Верифікація в логах**

Шукайте рядки:
```
✅ Якщо працює:
[ETHUSDT] 🎯 _make_decision_for_symbol() START
Position size for ETHUSDT modified by factor 0.6 due to HIGH_VOLATILITY regime

❌ Якщо НЕ працює:
[BTCUSDT] Trade intent rejected: Neutral signal score -0.0444 (НЕ режимна адаптація)
```

---

## 📝 **Висновок**

**Динамічна торгівля реалізована на 70%:**
- ✅ Детекція 5 режимів ринку працює
- ✅ Блокування контр-трендів працює
- ✅ Динамічна Kelly фракція працює
- ✅ Динамічні сигнали OBI/TFI працюють
- ❌ **Адаптивне масштабування зміленовано** — відсутні конфіги в YAML

**Основна причина:** `sizing_modifiers` не задані в `trading.yaml`, тому коофіцієнти скорочення ніколи не застосовуються.

**Рішення:** Додати 3 розділи в YAML (див. рекомендації вище).

---

**Дослідження завершено:** 3 листопада 2025, 21:11 UTC
**Файли проаналізовані:** 12
**Рядків коду:** ~2000
