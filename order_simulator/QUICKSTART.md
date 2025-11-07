# Order Simulator - QUICK START 🚀

## За 2 хвилини

### Крок 1: Тестовий запуск з фейковими даними

```powershell
cd c:\Users\user\Music\Phenix\order_simulator
python test_run_realistic.py
```

**Очікуємо вихід**: 20 результатів (10 WIN, 10 LOSS)

### Крок 2: Аналіз результатів

```powershell
python analyze.py
```

**Очікуємо**:
```
📊 ЗАГАЛЬНА СТАТИСТИКА
Всього результатів: 20
Перемог (WIN): 10 (50.0%)
Програшів (LOSS): 10 (50.0%)
Загальний PNL: +1980.60

🎯 СТАТИСТИКА ПО ВАРІАНТАХ
Scalp          2   2   50.0%    +661.00  (🏆 Найкращий)
Aggressive     2   2   50.0%    +517.60
Balanced-High  2   2   50.0%    +422.00
Balanced-Low   2   2   50.0%    +242.00
Conservative   2   2   50.0%    +138.00
```

## Основні команди

| Команда | Що робить |
|---------|-----------|
| `python test_run.py` | Тест з простими фейковими даними |
| `python test_run_realistic.py` | Тест з реалістичними цінами (BTCUSDT +, ETHUSDT -) |
| `python monitor.py` | **Live режим** - читає реальний event_chain.log |
| `python analyze.py` | Аналіз results.jsonl і експорт в CSV |

## Файли 📁

```
order_simulator/
├── config.json                 ← Конфіг (5 варіантів TP/SL)
├── monitor.py                  ← Головна утиліта
├── analyze.py                  ← Аналізатор результатів
├── test_run.py                 ← Простий тест
├── test_run_realistic.py       ← Реалістичний тест
│
├── active_orders.json          ← Поточні позиції (auto-update)
├── results.jsonl               ← Історія результатів (JSONL)
├── analysis.csv                ← Експорт результатів
├── simulation.log              ← Лог симулятора
│
└── README.md                   ← Повна документація
```

## Приклади результатів

### Сценарій 1: BTCUSDT (ціна вверх - WIN)
```
Entry:  45000
Prices: 45025 → 45050 → 45090 → 45135 → 45225 → 45270 → 45337.5

Результати:
  Conservative (TP: 45090)    → WIN +90
  Balanced-Low (TP: 45135)    → WIN +135
  Balanced-High (TP: 45225)   → WIN +225
  Aggressive (TP: 45270)      → WIN +270
  Scalp (TP: 45337.5)         → WIN +337.5
```

### Сценарій 2: ETHUSDT (ціна вниз - LOSS)
```
Entry:  2800
Prices: 2799 → 2797 → 2793 → 2788.8 → 2786 → 2779

Результати:
  Scalp (SL: 2793)            → LOSS -7
  Aggressive (SL: 2788.8)     → LOSS -11.2
  Balanced-Low (SL: 2786)     → LOSS -14
  Balanced-High (SL: 2786)    → LOSS -14
  Conservative (SL: 2779)     → LOSS -21
```

### Статистика за тестом
```
СКАЛЬПЕР вийшов в лідери:
  +661 PNL (2W, 2L, 50% WR)

CONSERVATIVE - найконсервативніший:
  +138 PNL (2W, 2L, 50% WR)

ВИСНОВОК: На трендах Scalp перемагає, але на укладах вищі збитки
```

## Live режим (з реальними логами)

```powershell
# 1. Запуск симулятора (чекатиме на нові ордери)
python monitor.py

# 2. У іншому терміналі - запуск основної системи
cd c:\Users\user\Music\Phenix
python -m apps.reference.main

# 3. Симулятор буде читати event_chain.log й автоматично:
#    - Детектувати EVT:ORDER_OPENED
#    - Створювати 5 варіантів
#    - Отримувати ціни з EVT:PRICE_UPDATE
#    - Записувати результати в results.jsonl
```

**Вихід monitor.py**:
```
2025-11-04 10:30:44 [INFO] OrderSimulator initialized
2025-11-04 10:30:45 [INFO] Created order rid-001 with 5 variants: 45000.0 BTCUSDT
2025-11-04 10:30:48 [INFO] WIN: var_balanced_low - BTCUSDT @ 45225.0
2025-11-04 10:30:48 [INFO] Stats: {'active_orders': 1, 'wins': 1, 'losses': 0, ...}
2025-11-04 10:30:50 [INFO] Stats: {'active_orders': 0, 'wins': 1, 'losses': 2, ...}
```

## Як інтерпретувати аналіз

### Profit Factor
```
Profit Factor = |Сума виграшів| / |Сума програшів|
  > 1.5 = Дуже хорошо
  > 1.0 = Позитивно
  < 1.0 = Мінусові
```

### Win Rate %
```
(Кількість WIN) / (Всього) * 100
  > 60% = Агресивна стратегія
  50%   = Збалансована
  < 40% = Консервативна
```

### Avg PNL
```
Середня P&L на один трейд
  > 100 = Гарна стратегія
  > 0   = Позитивна
  < 0   = Мінусова
```

## Проблеми?

**Q: Немає результатів після analyze.py?**
A: Запусти `python test_run_realistic.py` щоб генерувати дані.

**Q: Як додати свій варіант TP/SL?**
A: Редагуй `config.json`:
```json
{
  "id": "var_custom",
  "name": "My Variant",
  "tp_ratio": 0.8,
  "sl_ratio": 1.2
}
```

**Q: Як запустити monitor.py постійно?**
A: Редагуй в PowerShell:
```powershell
While ($true) {
    python monitor.py
    Start-Sleep -Seconds 5
}
```

## Наступні кроки

1. ✅ Запусти тест → вивчи результати
2. ✅ Запусти live режим (з реальною системою)
3. ✅ Збирай дані за декілька днів торгівлі
4. 🔄 Аналізуй який варіант найкращий для твоєї стратегії
5. 🚀 Оновлювання основної системи з найкращим варіантом

---

**Версія**: 1.0
**Статус**: ✅ Готово до використання
**Контакт**: Quantum Trader X Team
