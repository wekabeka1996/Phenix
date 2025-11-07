# 🔍 LOG NameError — Комплексне Дослідження

**Дата:** 3 листопада 2025, 02:52 UTC
**Помилка:** `NameError: name 'LOG' is not defined`
**Файл:** `apps/reference/domains/position_tracking/position_tracking.py`
**Лінія:** 271 (та ще 4 місця)
**Severity:** 🔴 **CRITICAL** — система краша при обробці `EVT:ACCOUNT_UPDATE_RECEIVED`

---

## 1. АНАЛІЗ ПОМИЛКИ

### Трасування помилки:
```
vfoundation/core/fsm_core.py line 63 in emit()
  └─ callback(message)  # Викликає listener для EVT:ACCOUNT_UPDATE_RECEIVED

apps/reference/domains/position_tracking/position_tracking.py line 271
  └─ LOG.info(f"📊 SYNC: Received ...")  # ← ПОМИЛКА: LOG не визначена
     NameError: name 'LOG' is not defined
```

### Контекст помилки:
```python
# position_tracking.py line 271
def on_account_update(self, event: Message) -> None:
    """..."""
    self.logger.info("Handling EVT:ACCOUNT_UPDATE_RECEIVED...")  # ← Правильно (лін. 198)

    # ... код ...

    LOG.info(f"📊 SYNC: Received ...")  # ← ПОМИЛКА! (лін. 271)
    #  ↑ Велика буква LOG замість self.logger
```

---

## 2. ЛОКАЛІЗАЦІЯ ВСІХ ВИНИКНЕНЬ

### Файл: `position_tracking.py`

| Лінія | Код | Статус | Причина |
|-------|-----|--------|---------|
| 198 | `self.logger.info(...)` | ✅ OK | Правильна конвенція |
| 271 | `LOG.info(...)` | ❌ ПОМИЛКА | Велика буква, глобальна змінна не існує |
| 291 | `LOG.info(...)` | ❌ ПОМИЛКА | Велика буква |
| 296 | `LOG.info(...)` | ❌ ПОМИЛКА | Велика буква |
| 305 | `LOG.warning(...)` | ❌ ПОМИЛКА | Велика буква |
| 308 | `LOG.info(...)` | ❌ ПОМИЛКА | Велика буква |

**Всього помилок:** 5 місць у `position_tracking.py`

### Інші файли (перевірено):

| Файл | LOG | Статус | Тип |
|------|-----|--------|-----|
| `execution_position/fsm.py` лін. 50 | `LOG = logging.getLogger(__name__)` | ✅ OK | Правильне глобальне визначення |
| `market_data/market_data_connector.py` лін. 22 | `LOG = logging.getLogger(__name__)` | ✅ OK | Правильне глобальне визначення |

**Висновок:** Проблема **локалізована** у `position_tracking.py` в методі класу `on_account_update()`.

---

## 3. КОРЕНЕВА ПРИЧИНА

### Що сталось:

1. **Клас `PositionTracking`** визначує `self.logger` у методі `__init__()` (лін. 49)
   ```python
   def __init__(self, fsm, config):
       self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
   ```

2. **Глобальна змінна `logger`** визначена на лінії 22 для модуля
   ```python
   logger = logging.getLogger(__name__)
   ```

3. **Помилка:** У методу `on_account_update()` використовується `LOG` (велика), якої **НЕ ІСНУЄ**
   - Глобальна: `logger` (мала)
   - Інстанцна: `self.logger`
   - Використано: `LOG` (не існує!)

### Гіпотеза про походження:

- Код був скопійований з файлів, де **Є** глобальна `LOG` (наприклад, `fsm.py`)
- У `position_tracking.py` забули додати глобальну `LOG = logging.getLogger(__name__)`
- Замість того, щоб використовувати `self.logger` (як правильно робиться на лінії 198)

---

## 4. НАСЛІДКИ ПОМИЛКИ

### Гравітацій паралізу:

```
🔴 Коли сталось?
   └─ Біля 02:52 UTC на лінії 271
   └─ Під час обробки EVT:ACCOUNT_UPDATE_RECEIVED від AccountConnector

🔴 Що трапилось?
   └─ FSMCore.emit() перехопив NameError
   └─ Listener функція прив'язала до краша
   └─ Система втратила подію про оновлення рахунку

🔴 Якими були наслідки?
   1. ❌ Позиції НЕ оновилися з Binance
   2. ❌ P&L розрахунки НЕ оновилися
   3. ❌ Сигнали про закриття позицій НЕ підстрахані
   4. ❌ RID event chain РОЗРИВАЄТЬСЯ (нема логу про sync)

🔴 Скільки разів це сталось?
   └─ НЕВІДОМО — потрібна перевірка логів після 02:52 UTC
   └─ Якщо AccountConnector змикає кожні 30 сек → помилка повторюється кожні 30 сек
```

### Пов'язані FSM/域 домени:

```
EVT:ACCOUNT_UPDATE_RECEIVED (Джерело: AccountConnector)
  ├─ Position Tracking (Слухач): on_account_update()
  │   └─ 🔴 NameError на лінії 271
  │       └─ 📉 Позиції НЕ синхронізуються
  │           └─ 🎯 Decision Making не бачить актуальні позиції
  │               └─ 🚫 Сигнали генеруються НЕВІРНО
  │
  └─ Cascading Failure (каскадна помилка):
      1. Position Tracking crash
      2. No EVT:PORTFOLIO_STATE_UPDATED emitted
      3. Decision Making uses stale portfolio data
      4. Position sizing calculations WRONG
      5. Execution Position receives WRONG sizes
```

---

## 5. ЛАНЦЮГирия Залежностей

```
AccountConnector (market_data domain)
  │ (polls Binance /fapi/v2/positionRisk every 30s)
  ├─ Emits: EVT:ACCOUNT_UPDATE_RECEIVED
  │
  ├─ Listeners:
  │   ├─ PositionTracking.on_account_update() [position_tracking.py line 268]
  │   │   └─ 🔴 CRASHES at line 271 (LOG not defined)
  │   │       └─ Doesn't emit: EVT:PORTFOLIO_STATE_UPDATED
  │   │
  │   └─ [Other listeners if any - TBD]
  │
  └─ Expected flow:
      EVT:ACCOUNT_UPDATE_RECEIVED
      ├─ PositionTracking processes
      └─ Emits EVT:PORTFOLIO_STATE_UPDATED
          ├─ DecisionMaking receives
          ├─ Updates latest_portfolio
          └─ Uses for position sizing
```

---

## 6. КОНВЕНЦІЇ ТА МАСШТАБ ПРОБЛЕМИ

### Конвенція Логування в Проекті:

| Файл | Конвенція | Приклад | Тип |
|------|-----------|---------|-----|
| **Module-level components** | `LOG = logging.getLogger(__name__)` | `fsm.py`, `market_data_connector.py` | Глобальна |
| **Class-based components** | `self.logger = logging.getLogger(...)` | `PositionTracking.__init__()` line 49 | Інстанцна |

### Масштаб Проблеми:

```
🎯 Критична область: position_tracking.py (методи класу)
   ├─ ✅ Правильні: self.logger (лінії 198, 253, 262, 358, 365, 376, 382, 389, 426, 454)
   ├─ ❌ Помилкові: LOG (лінії 271, 291, 296, 305, 308) — 5 помилок
   └─ Імовірна причина: Copy-paste від fsm.py без коригування

🎯 Інші файли (перевірені):
   ├─ fsm.py: ✅ Правильне LOG = logging.getLogger(__name__)
   └─ market_data_connector.py: ✅ Правильне LOG = logging.getLogger(__name__)

🎯 Заходи запобігання:
   └─ Код review не вловив — LOG vs logger vs self.logger
```

---

## 7. ПЛАН ВИПРАВЛЕННЯ (БЕЗ КОДУ)

### Варіант A: Замінити на `self.logger` (РЕКОМЕНДУЄТЬСЯ)

**Логіка:**
- `position_tracking.py` — це **клас-based компонента**
- У класі вже є `self.logger`
- Всі інші місця в методі використовують `self.logger` (лінія 198)
- **Консистентна** конвенція

**Що змінити:**
- Лінія 271: `LOG.info(...)` → `self.logger.info(...)`
- Лінія 291: `LOG.info(...)` → `self.logger.info(...)`
- Лінія 296: `LOG.info(...)` → `self.logger.info(...)`
- Лінія 305: `LOG.warning(...)` → `self.logger.warning(...)`
- Лінія 308: `LOG.info(...)` → `self.logger.info(...)`

**Переваги:**
- ✅ Синхронно з рештою файлу
- ✅ Немає глобального стану
- ✅ Тестування простіше (mock self.logger)
- ✅ Багатопоточність безпечніше

---

### Варіант B: Додати глобальну `LOG` (МЕНШЕ РЕКОМЕНДУЄТЬСЯ)

**Логіка:**
- Додати на лінію 22 (після `logger`): `LOG = logger`
- Це задовольнить помилку NameError

**Що змінити:**
- Лінія 22: Додати `LOG = logger`

**Недоліки:**
- ❌ Змішає конвенції (self.logger та глобальна LOG)
- ❌ Зберігає технічний борг
- ❌ Сплутує інших розробників

---

### Варіант C: Комбіноване Рішення (ОПТИМАЛЬНЕ)

**Комбіна:** Варіант A + профілактичні заходи

1. **Заміна:** `LOG` → `self.logger` (5 місць)
2. **Перевірка:** Grep всіх файлів на `LOG.` у методах класу
3. **Тестування:** Unit тести для `on_account_update()`
4. **Code Review:** Перевірити інші методи в `position_tracking.py`

---

## 8. ПЛАН ВИКОНАННЯ (ПОРЯДОК)

### Phase 1: Локалізація (ВЖЕ ЗАВЕРШЕНА)
- ✅ Знайдено 5 помилок у `position_tracking.py`
- ✅ Перевірено інші файли — проблем немає
- ✅ Визначена коренева причина
- ✅ Проаналізовані наслідки

### Phase 2: Розроблення Виправлення (ДАЛІ)
- [ ] Написати SQL-like операцію (список змін)
- [ ] Перевірити, чи вищі рядки коду залежать від LOG
- [ ] Перевірити, чи є інші методи з LOG (grep всього файлу)
- [ ] Планувати тестування

### Phase 3: Валідація Виправлення
- [ ] Запустити unit тести
- [ ] Інтеграційні тести з AccountConnector
- [ ] Перевірити вихід подій
- [ ] Логування перевірити

### Phase 4: Контроль Якості
- [ ] Перевірити, чи немає нових помилок
- [ ] Перевірити, чи LOG не використовується більше нікуди в файлі
- [ ] Code Review

---

## 9. ОПЕРАЦІЙНІ ТЕРИ

### Тест 1: Перевірити інші методи на LOG

```bash
grep -n "LOG\." apps/reference/domains/position_tracking/position_tracking.py
# Очікуваний результат після виправлення: НІЧОГО
```

### Тест 2: Перевірити, чи self.logger визначена всюди

```bash
grep -n "def " apps/reference/domains/position_tracking/position_tracking.py | head -20
# Кожна функція методу повинна мати доступ до self.logger
```

### Тест 3: Запустити систему з AccountConnector

```bash
# Повинна НЕ краша при EVT:ACCOUNT_UPDATE_RECEIVED
python -m apps.reference.main 2>&1 | grep -i "EVT:ACCOUNT_UPDATE_RECEIVED\|NameError"
```

---

## 10. РЕЗЮМЕ

| Пункт | Результат |
|-------|-----------|
| **Помилка** | `NameError: name 'LOG' is not defined` |
| **Локація** | `position_tracking.py` лінії 271, 291, 296, 305, 308 |
| **Причина** | Використання глобальної `LOG` замість `self.logger` в методу класу |
| **Наслідки** | Краш на кожному оновленні рахунку (~30 сек), позиції не синхронізуються |
| **Масштаб** | 5 помилок у 1 файлі, інші файли OK |
| **Рішення** | Замінити `LOG` на `self.logger` (Варіант A) |
| **Тестування** | Unit тести, інтеграційні тести, моніторинг логів |

---

**Дослідження завершено.** Готово до розроблення Плану виправлення.

**RID:** `LOG_NAMEREF_PT_20251103`
**Severity:** 🔴 CRITICAL
**Status:** 🔍 RESEARCHED
