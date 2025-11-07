# 📊 TP/SL Tuning Guide - Як налаштувати Take Profit і Stop Loss

**Мета**: Зрозуміти, як розширювати чи звужувати відстані між позицією, TP та SL

---

## 🎯 КАРТИНА СИТУАЦІЇ

```
LONG позиція (приклад):

     TP (Take Profit) ↑  = 45230  (вище)
                           ↑
                      Різниця 230 BPS
                           ↓
    Entry Price ◄──────────► = 45000 (твоя позиція живе тут)
                           ↓
                      Різниця 50 BPS
                           ↑
     SL (Stop Loss)  ↓  = 44775  (нижче)


SHORT позиція (приклад):

     TP (Take Profit) ↓  = 44775  (нижче)
                           ↓
                      Різниця 230 BPS
                           ↑
    Entry Price ◄──────────► = 45000 (твоя позиція живе тут)
                           ↑
                      Різниця 50 BPS
                           ↓
     SL (Stop Loss)  ↑  = 45230  (вище)
```

---

## 🔧 ТРИ ОСНОВНІ ПАРАМЕТРИ ДЛЯ НАЛАШТУВАННЯ

### 1️⃣ **STOP LOSS (SL)** - Збиток, який ти готов прийняти
```yaml
# config/aurora/trading.yaml, лінія 151
execution:
  manage:
    brackets:
      stop_loss_bps: 50  # ← ГОЛОВНИЙ ПАРАМЕТР
```

| Значення | Теоретичний Збиток | Використання |
|----------|------------------|--------------|
| **20 bps** | -0.2% | Дуже консервативно (мікро) |
| **30 bps** | -0.3% | Консервативно |
| **50 bps** | -0.5% | **СЕРЕДНЄ (за замовчуванням)** |
| **75 bps** | -0.75% | Середньо-агресивно |
| **100 bps** | -1.0% | Агресивно |
| **150 bps** | -1.5% | Дуже агресивно |

**Як працює**:
- **50 bps** означає **0.5%** від entry price
- Якщо entry = 45000, то SL = 45000 - (45000 × 50 / 10000) = **44775**

**Мнемоніка**:
- ✅ **Менше = більше запасу**, але менше прибутку
- ✅ **Більше = менше запасу**, але більше можливості для коливань

---

### 2️⃣ **TAKE PROFIT (TP)** - Цільовий прибуток

**ДВА параметри для гнучкості**:

```yaml
# config/aurora/trading.yaml, лінії 152-153
execution:
  manage:
    brackets:
      take_profit_low_ratio: 0.6    # ← k₁ коефіцієнт
      take_profit_high_ratio: 1.0   # ← k₂ коефіцієнт
```

**Як це працює**:

```
TP обчислюється як:
TP = Entry Price + (SL_bps × ratio) × (Entry Price / 10000)

Приклад (LONG):
Entry = 45000
SL_bps = 50 bps

TP_low = 45000 + (50 × 0.6) × (45000 / 10000)
TP_low = 45000 + 30 × 4.5
TP_low = 45000 + 135 = 45135  (0.3% прибутку)

TP_high = 45000 + (50 × 1.0) × (45000 / 10000)
TP_high = 45000 + 50 × 4.5
TP_high = 45000 + 225 = 45225  (0.5% прибутку)
```

| Параметр | Коефіцієнт | Прибуток | Відзначення |
|----------|-----------|---------|-----------|
| **take_profit_low_ratio** | k₁ = 0.6 | 0.3% | Мінімальний прибуток |
| **take_profit_high_ratio** | k₂ = 1.0 | 0.5% | Максимальний прибуток |

**Мнемоніка**:
- ✅ **k₁** (низька) = консервативний сценарій
- ✅ **k₂** (висока) = оптимістичний сценарій
- ✅ Система проводить обидва розрахунки для різних умов

---

### 3️⃣ **PAYOFF RATIO** - Співвідношення TP / SL

```yaml
# config/aurora/trading.yaml, лінія 83
decision:
  kelly:
    payoff_ratio_r: 1.5  # ← Використовується для Kelly sizing
```

**Що це означає**:
```
Payoff Ratio = TP_bps / SL_bps = 1.5

Якщо SL = 50 bps, то TP повинна бути:
TP ≈ 50 × 1.5 = 75 bps
```

**Використання**:
- Визначає **очікуваний профіт** від торгівлі
- Використовується для **Kelly sizing** (розмір позиції)
- **Вища ratio = більша позиція** (більше прибутку потенціально)

---

## 🎚️ КАК ЗВУЖУВАТИ ЧИ РОЗШИРЮВАТИ ВІДСТАНІ

### СЦЕНАРІЙ 1: Ринок надто волатильний - РОЗШИРИТИ відстані

**Проблема**: SL часто хітає, TP далеко.

**Рішення**:

```yaml
# БУЛО (консервативно):
stop_loss_bps: 50

# СТАЛО (розширено):
stop_loss_bps: 75    # Більше місця для коливань (0.75% збиток)

# ТА ЗАРАЗОМ:
take_profit_low_ratio: 0.5   # Виглядає менш привабливо (40% від SL)
take_profit_high_ratio: 1.25  # Але більше чекаємо (93% від SL)
```

**Математика**:
```
OLD (SL=50):
  TP_low = 50 × 0.6 = 30 bps (0.3% вверх)
  TP_high = 50 × 1.0 = 50 bps (0.5% вверх)

NEW (SL=75):
  TP_low = 75 × 0.5 = 37.5 bps (0.37% вверх)
  TP_high = 75 × 1.25 = 93.75 bps (0.93% вверх)
```

**Результат**:
- ✅ Менше false-stops (SL даліше)
- ✅ Більше прибутку в разі запуску
- ❌ Більший збиток якщо все-таки упаде

---

### СЦЕНАРІЙ 2: Ринок спокійний - ЗВУЗИТИ відстані

**Проблема**: Чекаємо занадто довго, пропускаємо більше опортюнітетів.

**Рішення**:

```yaml
# БУЛО:
stop_loss_bps: 50

# СТАЛО (звужено):
stop_loss_bps: 30    # Менше місця для коливань (0.3% збиток)

# ТА ЗАРАЗОМ:
take_profit_low_ratio: 0.8   # Більш привабливий (0.24% вверх)
take_profit_high_ratio: 1.3   # Дуже привабливий (0.39% вверх)
```

**Математика**:
```
OLD (SL=50):
  TP_low = 50 × 0.6 = 30 bps (0.3%)
  TP_high = 50 × 1.0 = 50 bps (0.5%)

NEW (SL=30):
  TP_low = 30 × 0.8 = 24 bps (0.24%)
  TP_high = 30 × 1.3 = 39 bps (0.39%)
```

**Результат**:
- ✅ Швидше запускаються TP (менш очікування)
- ✅ Більше трейдів на день
- ❌ Менше буферу для коливань

---

### СЦЕНАРІЙ 3: Регулювання по РЕЖИМАХ РИНКУ

```yaml
# Автоматично під'їзджати параметри за регімом

decision:
  sizing_modifiers:
    HIGH_VOLATILITY: "0.60"     # Менший розмір позиції
    LOW_VOLATILITY: "1.20"      # Більший розмір позиції

models:
  volatility:
    atr_period: 14
    threshold_multiplier: 2.0    # Чим менше = частіше HIGH_VOL
    low_vol_multiplier: 0.5      # Чим більше = частіше LOW_VOL
```

**Як це працює**:
1. Система виявляє **HIGH_VOLATILITY** (ATR > 2.0 × SMA)
2. Система **зменшує розмір позиції** на 40% (`0.60`)
3. **Але** може **розширити SL** через додатковий параметр:

```yaml
# ДОБАВИТИ (нова конфіг):
execution:
  manage:
    volatility_adaptive:      # ← НОВА СЕКЦІЯ
      enable: true

      # Множники для HIGH_VOLATILITY
      high_vol_sl_multiplier: 1.5    # SL × 1.5 (більше місця)
      high_vol_tp_ratio_boost: 0.8   # TP ratio зменшити (менш амбіційно)

      # Множники для LOW_VOLATILITY
      low_vol_sl_multiplier: 0.8     # SL × 0.8 (менше місця)
      low_vol_tp_ratio_boost: 1.2    # TP ratio збільшити (більш амбіційно)
```

**Приклад**:
```
HIGH_VOLATILITY РЕЖИМ:
  Base SL = 50 bps
  Adjusted SL = 50 × 1.5 = 75 bps   (більше запасу)
  Base TP ratio = 1.0
  Adjusted TP ratio = 1.0 × 0.8 = 0.8  (менш амбіційно)

LOW_VOLATILITY РЕЖИМ:
  Base SL = 50 bps
  Adjusted SL = 50 × 0.8 = 40 bps   (менше запасу)
  Base TP ratio = 1.0
  Adjusted TP ratio = 1.0 × 1.2 = 1.2  (більш амбіційно)
```

---

## 🎛️ ТОП-5 НАЛАШТУВАНЬ ДЛЯ ТЕСТУВАННЯ

| Сценарій | SL bps | k₁ | k₂ | Payoff R | Примітка |
|----------|--------|----|----|----------|---------|
| **1. Консервативно** | 30 | 0.8 | 1.3 | 1.2 | Менше рис, менше прибутку |
| **2. Середнє** | 50 | 0.6 | 1.0 | 1.5 | За замовчуванням |
| **3. Агресивно** | 75 | 0.5 | 1.25 | 1.75 | Більше місця, більше прибутку |
| **4. Мікро (для почин.)** | 20 | 1.0 | 1.5 | 1.0 | Найменше рис |
| **5. Висока волатильність** | 100 | 0.4 | 1.5 | 2.0 | Для CTB, дельта-нейтральних |

---

## ✅ РЕЦЕПТ: Як змінити TP/SL у config

### Крок 1: Відкрий конфіг
```bash
code config/aurora/trading.yaml
```

### Крок 2: Знайди секцію (лінія ~148)
```yaml
  execution:
    manage:
      brackets:
        enable: true
        stop_loss_bps: 50              # ← ТУТ
        take_profit_low_ratio: 0.6     # ← ТУТ
        take_profit_high_ratio: 1.0    # ← ТУТ
```

### Крок 3: Змінь значення

**Приклад: Розширити для волатильності**
```yaml
        stop_loss_bps: 75              # +50% більше запасу
        take_profit_low_ratio: 0.5     # Менш оптимістично
        take_profit_high_ratio: 1.25   # Більше потенціалу
```

### Крок 4: Збережи Ctrl+S

### Крок 5: Перезавантаж систему
```bash
# API повинна перечитати конфіг
# Зазвичай відбувається автоматично (reload=true в uvicorn)
```

---

## 🔬 ЯК ТЕСТУВАТИ ЗМІНИ

### Тест 1: Перевіри, чи змінилися параметри
```bash
# Додай print у коді
# apps/reference/domains/execution_position/adapter.py

print(f"SL calculated: {order.stop_price}")
print(f"TP calculated: {order.take_profit_price}")
```

### Тест 2: Запусти на testnet
```bash
# Переконайся, що trading.mode = "testnet"
# Виконай 5-10 трейдів вручну

# Перевір logs:
tail -f logs/event_chain.log | grep "EXECUTION"
```

### Тест 3: Емуляторні дані
```python
# test_tp_sl_calculation.py
def test_bracket_distances():
    entry = 45000
    sl_bps = 75
    tp_low_ratio = 0.5
    tp_high_ratio = 1.25

    sl_price = entry * (1 - sl_bps / 10000)  # LONG
    tp_low_price = entry + (sl_bps * tp_low_ratio) * (entry / 10000)
    tp_high_price = entry + (sl_bps * tp_high_ratio) * (entry / 10000)

    assert sl_price == 44662.5
    assert tp_low_price == 45168.75
    assert tp_high_price == 45562.5

    print(f"SL: {entry} → {sl_price} ({(sl_price - entry) / entry * 100:.2f}%)")
    print(f"TP_low: {entry} → {tp_low_price} ({(tp_low_price - entry) / entry * 100:.2f}%)")
    print(f"TP_high: {entry} → {tp_high_price} ({(tp_high_price - entry) / entry * 100:.2f}%)")
```

---

## 🎓 ВИВЧИМО ФОРМУЛИ

### Formula 1: SL Distance (базова)
```
SL_price = Entry × (1 - SL_bps / 10000)    [LONG]
SL_price = Entry × (1 + SL_bps / 10000)    [SHORT]

Example (LONG, Entry=45000, SL=50 bps):
SL = 45000 × (1 - 0.005) = 45000 × 0.995 = 44775
```

### Formula 2: TP Distance (складна)
```
TP_price = Entry + (SL_bps × ratio) × (Entry / 10000)   [LONG]
TP_price = Entry - (SL_bps × ratio) × (Entry / 10000)   [SHORT]

Example (LONG, Entry=45000, SL=50, ratio=1.0):
TP = 45000 + (50 × 1.0) × (45000 / 10000)
TP = 45000 + 50 × 4.5
TP = 45000 + 225 = 45225
```

### Formula 3: Payoff Ratio (для Kelly)
```
Payoff_Ratio = TP_bps / SL_bps

Example:
SL = 50 bps
TP = 75 bps (при ratio=1.5)
Payoff = 75 / 50 = 1.5 ✅
```

---

## 📈 ДИНАМІЧНЕ НАЛАШТУВАННЯ (Майбутнє)

**Що можна добавити** (Phase 2):

```yaml
execution:
  manage:
    brackets:
      adaptive_mode: true          # Автоматично змінювати на ходу

      # Залежно від ATR
      atr_based:
        enable: true
        atr_period: 14
        sl_multiplier_by_atr: 0.5   # SL = ATR × 0.5
        tp_multiplier_by_atr: 1.0   # TP = ATR × 1.0

      # Залежно від WIN RATE
      dynamic_adjustment:
        enable: true
        win_rate_threshold: 0.45
        if_below_threshold:
          sl_expand_pct: 20          # Розширити SL на 20%
          tp_contract_pct: 10        # Звузити TP на 10%
        if_above_threshold:
          sl_contract_pct: 10        # Звузити SL на 10%
          tp_expand_pct: 20          # Розширити TP на 20%
```

---

## 🎯 ЧЕКЛИСТ НАЛАШТУВАННЯ

- [ ] **Визнач характер ринку** (HIGH_VOL чи LOW_VOL?)
- [ ] **Виконай тести** з 3-5 різних наборів параметрів
- [ ] **Запиши результати**:
  - Win rate %
  - Avg profit per trade
  - Max drawdown
  - Trades per day
- [ ] **Порівняй результати** між старими та новими параметрами
- [ ] **Обери найкращий набір** для твого стилю
- [ ] **Задокументуй** вибір у README
- [ ] **Деплой на testnet** на 24 години
- [ ] **Перевір логи** на anomalies
- [ ] **Деплой на продакшн** з confidence

---

## 🆘 ЧАСТОВІ ПРОБЛЕМИ

| Проблема | Причина | Рішення |
|----------|---------|---------|
| Занадто багато SL хітів | SL занадто близько | ↑ `stop_loss_bps` |
| TP ніколи не хітає | TP занадто далеко | ↓ `take_profit_high_ratio` |
| Низька win rate | Рис/прибуток неоптимальні | Налаштуй `payoff_ratio_r` |
| Мало трейдів | Сигнали рідкі або TP далеко | ↓ `signal_threshold`, ↓ TP |
| Занадто багато трейдів | Сигнали часті, риск висок | ↑ `signal_threshold`, ↑ SL |

---

## 📚 ДОДАТКОВІ РЕСУРСИ

**Пов'язані файли**:
1. `config/aurora/trading.yaml` - головний конфіг
2. `vfoundation/fsm/fsm.py` - реалізація bracket tracking
3. `apps/reference/domains/execution_position/` - execution logic

**Документація**:
- `docs/ORDER_LIFECYCLE_AND_EXECUTION_FLOW.md`
- `docs/domains/execution_position/`
- `docs/DEPLOYMENT_CHECKLIST.md`

---

**Last Updated**: 4 November 2025
**Status**: ✅ Ready for implementation
**Next Step**: Обери сценарій і налаштуй конфіг
