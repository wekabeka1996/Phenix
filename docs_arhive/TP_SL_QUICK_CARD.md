# 🎯 TP/SL Quick Reference Card

**Коротка шпаргалка для швидкої зміни параметрів**

---

## 📍 ГДЕ ЗМІНЮВАТИ

**Файл**: `config/aurora/trading.yaml`
**Лінії**: 148-160

```yaml
execution:
  manage:
    brackets:
      stop_loss_bps: 50              # ← Змінюй ТУТ
      take_profit_low_ratio: 0.6     # ← Змінюй ТУТ
      take_profit_high_ratio: 1.0    # ← Змінюй ТУТ
```

---

## 🚀 ШВИДКІ РЕЦЕПТИ

### 🟢 Коли ринок СПОКІЙНИЙ (Low Vol)
**Проблема**: Мало волатильності, хочу більше трейдів.

```yaml
# КОПІЮЙ ТІСНО:
stop_loss_bps: 35
take_profit_low_ratio: 0.8
take_profit_high_ratio: 1.3
```

**Результат**:
- SL: -0.35% (близько)
- TP_low: +0.28% (близько)
- TP_high: +0.46% (близько)
- ⏱️ Більше трейдів на день
- 📊 Менший прибуток за трейд

---

### 🔴 Коли ринок ВОЛАТИЛЬНИЙ (High Vol)
**Проблема**: Занадто багато коливань, SL часто хітає.

```yaml
# КОПІЮЙ ТІСНО:
stop_loss_bps: 75
take_profit_low_ratio: 0.5
take_profit_high_ratio: 1.25
```

**Результат**:
- SL: -0.75% (далеко)
- TP_low: +0.38% (далеко)
- TP_high: +0.94% (далеко)
- ⏱️ Менше трейдів, але більша вірогідність хіту
- 📊 Більший прибуток за трейд

---

### 🟡 СЕРЕДНЄ (Баланс)
**Проблема**: Хочу баланс між кількістю та розміром трейдів.

```yaml
# КОПІЮЙ ТІСНО (поточний default):
stop_loss_bps: 50
take_profit_low_ratio: 0.6
take_profit_high_ratio: 1.0
```

**Результат**:
- SL: -0.5% (середнє)
- TP_low: +0.3% (малий)
- TP_high: +0.5% (середній)
- ⏱️ Регулярні трейди
- 📊 Регулярний прибуток

---

## 📊 ТАБЛИЦЯ: ПРЯМА КОНВЕРТАЦІЯ

| SL_bps | TP_low (×0.6) | TP_high (×1.0) | % Риск | % Мин.Проф | % Макс.Проф |
|--------|---------------|----------------|--------|-----------|------------|
| **20** | 12 | 20 | -0.20% | +0.12% | +0.20% |
| **30** | 18 | 30 | -0.30% | +0.18% | +0.30% |
| **35** | 21 | 35 | -0.35% | +0.21% | +0.35% |
| **50** | 30 | 50 | -0.50% | +0.30% | +0.50% |
| **75** | 45 | 75 | -0.75% | +0.45% | +0.75% |
| **100** | 60 | 100 | -1.00% | +0.60% | +1.00% |

---

## 🎯 ШАБЛОНИ КОНФІГІВ (Копіюй Цілком)

### Template 1: Ultraconservative (Мікро-ризик)
```yaml
execution:
  manage:
    brackets:
      enable: true
      stop_loss_bps: 20
      take_profit_low_ratio: 1.0
      take_profit_high_ratio: 1.5
      atomic_close: true
      bracket_tracking: true
```

### Template 2: Conservative
```yaml
execution:
  manage:
    brackets:
      enable: true
      stop_loss_bps: 30
      take_profit_low_ratio: 0.8
      take_profit_high_ratio: 1.3
      atomic_close: true
      bracket_tracking: true
```

### Template 3: Balanced (ПОТОЧНИЙ)
```yaml
execution:
  manage:
    brackets:
      enable: true
      stop_loss_bps: 50
      take_profit_low_ratio: 0.6
      take_profit_high_ratio: 1.0
      atomic_close: true
      bracket_tracking: true
```

### Template 4: Aggressive
```yaml
execution:
  manage:
    brackets:
      enable: true
      stop_loss_bps: 75
      take_profit_low_ratio: 0.5
      take_profit_high_ratio: 1.25
      atomic_close: true
      bracket_tracking: true
```

### Template 5: Mega Aggressive
```yaml
execution:
  manage:
    brackets:
      enable: true
      stop_loss_bps: 100
      take_profit_low_ratio: 0.4
      take_profit_high_ratio: 1.5
      atomic_close: true
      bracket_tracking: true
```

---

## 🔬 ТЕСТУВАННЯ: Як перевірити

### Крок 1: Змінь конфіг
```bash
# Під. текстовий редактор
code config/aurora/trading.yaml
# Вставь один з Template вище
# Збережи Ctrl+S
```

### Крок 2: Перезавантаж API
```bash
# API повинна перечитати конфіг (auto-reload=true)
# Або вручну перезапусти:
Ctrl+C  # Зупини сервер
# Запусти знову
uvicorn apps.reference.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Крок 3: Запусти 5-10 трейдів на testnet
```bash
# Перегляди ordre від рукою (CLI або вручну в UI)
# Перевір SL і TP відстані в Binance Futures
```

### Крок 4: Порівняй результати
```bash
# У логах шукай:
grep "SL_price" logs/event_chain.log
grep "TP_price" logs/event_chain.log

# Вони повинні бути такими як розраховано у таблиці вище
```

---

## ⚙️ МАТЕМАТИКА ПОЗАДУ (для розуміння)

### Коли вибираєш SL = 50 bps

```
1 bps = 0.01% = 1/100 of 1%
50 bps = 0.5%

Приклад:
Entry Price (BTC) = 45,000
50 bps = 50 × 0.5% / 100 = ?

Правильно:
50 bps / 10,000 = 0.005 = 0.5%
45,000 × 0.005 = 225

Значит:
SL Price = 45,000 - 225 = 44,775 ✅
```

### Коли вибираєш TP_ratio = 1.0

```
TP = Entry + (SL_bps × ratio) × (Entry / 10,000)

TP = 45,000 + (50 × 1.0) × (45,000 / 10,000)
TP = 45,000 + 50 × 4.5
TP = 45,000 + 225 = 45,225 ✅
```

---

## 🎮 ІНТЕРАКТИВНА СХЕМА

```
Як змінюється TP при змінах параметрів?

При ОДНОМУ ТІЖ SL=50:

take_profit_low_ratio = 0.4  →  TP ≈ 45,090  (менше зростання)
take_profit_low_ratio = 0.6  →  TP ≈ 45,135  (більше)
take_profit_low_ratio = 0.8  →  TP ≈ 45,180  (ще більше)
take_profit_low_ratio = 1.0  →  TP ≈ 45,225  (максимум для цього SL)

При ОДНОМУ ТІЖ ratio=1.0:

stop_loss_bps = 30  →  TP ≈ 45,135
stop_loss_bps = 50  →  TP ≈ 45,225
stop_loss_bps = 75  →  TP ≈ 45,338
stop_loss_bps = 100 →  TP ≈ 45,450
```

---

## ✅ ЧЕКЛИСТ ЗМІН

- [ ] Теоретично підібрав параметри (див. таблицю вище)
- [ ] Обрав Template (1-5)
- [ ] Змінив значення у `config/aurora/trading.yaml`
- [ ] Збережи файл (Ctrl+S)
- [ ] Запустив тест на testnet
- [ ] Переглянув логи (grep SL_price, TP_price)
- [ ] Порівняв з таблицею вище
- [ ] Результати збігаються? ✅ = Готово
- [ ] Результати не збігаються? 🔴 = Перевір код (адаптер)

---

## 🚨 ВАЖЛИВО!

1. **Завжди** тестуй на **testnet** спочатку
2. **Запис** старих параметрів, якщо щось пійде не так
3. **Не змінюй** коли система працює
4. **Перезавантажуй** API після змін конфігу
5. **Чекай** 5-10 трейдів перед висновками

---

## 📞 ПОМИЛКИ?

| Щось странне | Рішення |
|-------------|---------|
| API не перечитав конфіг | Перезавантаж вручну (kill + restart) |
| SL/TP не змінилися | Перевір синтаксис YAML (пробіли важливі!) |
| Помилка в конфігу | Скопіюй Template вище повністю |
| Невпевнений у параметрах | Почни з Template 3 (Balanced) |

---

**Last Updated**: 4 November 2025
**Format**: Quick Reference
**Status**: Ready to use
