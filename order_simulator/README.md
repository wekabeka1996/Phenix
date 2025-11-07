# Order Simulator 📊

**Утиліта для тестування 5 варіантів TP/SL конфігурацій паралельно**

Окремий екосистем (не інтегрований в основний проект) для дослідження того, які варіанти TP/SL відпрацьовували б краще на реальних даних.

## Архітектура 🏗️

```
monitor.py (main loop)
├─ Читає event_chain.log
├─ Детектує EVT:ORDER_OPENED
├─ Створює 5 паралельних SimulatedPosition (варіанти)
├─ Слідкує за EVT:PRICE_UPDATE
├─ Записує WIN/LOSS результати
└─ Зберігає statistiku в results.jsonl
```

## Файли 📁

| Файл | Роль |
|------|------|
| **config.json** | 5 варіантів TP/SL конфігурації |
| **monitor.py** | Головна утиліта для моніторингу |
| **test_run.py** | Тестовий запуск з фейковими даними |
| **active_orders.json** | Поточні активні позиції (auto-update) |
| **results.jsonl** | Історія всіх WIN/LOSS результатів |
| **simulation.log** | Лог роботи симулятора |

## 5 Варіантів TP/SL 🎯

| ID | Назва | TP Ratio | SL Ratio | Характер |
|-----|--------|----------|----------|----------|
| 1 | Conservative | 0.4 | 1.5 | Мінімальний прибуток, максимальний буфер (безпечно) |
| 2 | Balanced-Low | 0.6 | 1.0 | **Стандартна система (поточна)** |
| 3 | Balanced-High | 1.0 | 1.0 | 1:1 Risk/Reward |
| 4 | Aggressive-Tight | 1.2 | 0.8 | Щільний стоп, агресивний прибуток |
| 5 | Scalp | 1.5 | 0.5 | Мікростопи, швидкі прибутки |

### Як розраховується

**Базис**: 50 bps stop loss

- **SL**: Entry × (1 - 50 × sl_ratio / 10000)
- **TP**: Entry + (50 × tp_ratio) × (Entry / 10000)

Приклад: Entry = 45000 BTCUSDT, Conservative (tp=0.4, sl=1.5)
```
SL = 45000 × (1 - 75/10000) = 44662.5
TP = 45000 + (20) × (45000/10000) = 45090
```

## Запуск 🚀

### 1. Тестовий запуск (фейкові дані)

```powershell
cd c:\Users\user\Music\Phenix\order_simulator
python test_run.py
```

**Вихід**:
```
📊 Тест Order Simulator
================================================================================

1️⃣  Генерування фейкових подій...
   ✅ 12345 bytes in log

2️⃣  Запуск симулятора на 10 секунд...

3️⃣  Симулятор вихідні дані:
   [INFO] Stats: {'active_orders': 1, 'active_positions': 5, ...}

4️⃣  Показання результатів...

РЕЗУЛЬТАТИ ТЕСТУВАННЯ
================================================================================

Активні ордери: 1
  test-order-001:
    - var_conservative: ACTIVE (TP: 45090, SL: 44662)
    - var_balanced_low: WIN (TP: 45225, SL: 44775)
    - ...

Закритих позицій: 2
  WIN: 1
  LOSS: 1

  Переможні варіанти:
    Balanced-Low: BTCUSDT @ 45225.00 (PNL: 225.00)

  Програшні варіанти:
    Scalp: BTCUSDT @ 44700.00 (PNL: -300.00)

================================================================================
```

### 2. Запуск в режимі live (читає реальний event_chain.log)

```powershell
cd c:\Users\user\Music\Phenix\order_simulator
python monitor.py
```

**Вихід** (кожні 2 секунди):
```
[INFO] OrderSimulator initialized
[INFO] Starting OrderSimulator (poll interval: 2s)
[INFO] Stats: {'active_orders': 3, 'active_positions': 15, 'completed': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0, 'total_pnl': 0.0}
[INFO] WIN: var_balanced_low - BTCUSDT @ 45225.0
[INFO] Stats: {'active_orders': 3, 'active_positions': 10, 'completed': 1, 'wins': 1, 'losses': 0, 'win_rate': 100.0, 'total_pnl': 225.0}
```

**Ctrl+C** для зупинки.

## Результати 📊

### Формат results.jsonl

Один JSON об'єкт на рядок:

```json
{
  "timestamp": "2025-11-04T10:30:45.123456",
  "order_id": "test-order-001",
  "variant_id": "var_balanced_low",
  "variant_name": "Balanced-Low",
  "symbol": "BTCUSDT",
  "entry_price": 45000.0,
  "tp_price": 45225.0,
  "sl_price": 44775.0,
  "close_price": 45225.0,
  "result": "WIN",
  "pnl": 225.0
}
```

### Аналіз результатів

```python
import json
from pathlib import Path

results = []
with open("results.jsonl") as f:
    results = [json.loads(line) for line in f if line.strip()]

# Статистика по варіантах
from collections import defaultdict

by_variant = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pnl": 0})

for r in results:
    variant = r['variant_name']
    by_variant[variant]["wins" if r['result'] == 'WIN' else "losses"] += 1
    by_variant[variant]["total_pnl"] += r['pnl']

for variant, stats in by_variant.items():
    total = stats["wins"] + stats["losses"]
    wr = (stats["wins"] / total * 100) if total > 0 else 0
    print(f"{variant:20} | W: {stats['wins']:3} | L: {stats['losses']:3} | WR: {wr:5.1f}% | PNL: {stats['total_pnl']:+.2f}")
```

## Конфігурація 🔧

Редагуй `config.json`:

```json
{
  "enabled": true,
  "poll_interval_sec": 2,           // Інтервал перевірки логів (сек)
  "max_active_orders": 5,            // Максимум активних ордерів одночасно
  "log_source": "../logs/event_chain.log",
  "wallet": 40.0,                    // $40 (тестовий гаманець)
  "leverage": 60,                    // 60x leverage
  "base_sl_bps": 50                  // Базовий SL в bps
}
```

## Структура Даних 📋

### active_orders.json

```json
{
  "test-order-001": [
    {
      "order_id": "test-order-001",
      "variant_id": "var_conservative",
      "variant_name": "Conservative",
      "symbol": "BTCUSDT",
      "entry_price": 45000.0,
      "tp_price": 45090.0,
      "sl_price": 44662.5,
      "status": "ACTIVE",
      "pnl": null,
      "close_price": null,
      "created_at": "2025-11-04T10:30:44.123456",
      "closed_at": null
    },
    { /* other 4 variants */ }
  ]
}
```

## Loggung 📝

Симулятор пише логи в `simulation.log`:

```
2025-11-04 10:30:44,123 [INFO] OrderSimulator initialized
2025-11-04 10:30:44,456 [INFO] Created order test-order-001 with 5 variants: 45000.0 BTCUSDT
2025-11-04 10:30:46,789 [INFO] WIN: var_balanced_low - BTCUSDT @ 45225.0
2025-11-04 10:30:46,790 [INFO] Stats: {'active_orders': 1, 'active_positions': 4, ...}
```

## FAQ 🤔

**Q: Чому 5 варіантів?**
A: Коалозбір даних про те, яка конфігурація найстабільніша. Кожна має різний trade-off.

**Q: Чи це інтегровано з основною системою?**
A: Ні. Це окремий experimental tool. Результати потім вручну аналізуються.

**Q: Реальні ціни чи симульовані?**
A: Ціни з реального `event_chain.log` від основної системи. Позиції - симульовані.

**Q: Як додати свій варіант?**
A: Додай запис в `config.json` → `variants` з новим `tp_ratio` і `sl_ratio`.

**Q: Що якщо немає `EVT:ORDER_OPENED` в логах?**
A: Симулятор чекатиме. Можеш використовувати `test_run.py` щоб генерувати фейкові ордери.

## Розвиток 🚀

- [ ]웹ーداш для статистики в реал-тайм
- [ ] Графіки win rate по варіантам
- [ ] Експорт в CSV для Excel
- [ ] Автоматичний вибір найкращого варіанту
- [ ] Backtesting на історичних даних

---

**Автор**: Quantum Trader X Research Team
**Версія**: 1.0
**Дата**: 2025-11-04
