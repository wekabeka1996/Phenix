# Deep Audit Report: `fsm.py`
**Date:** 2025-11-20
**Target:** `apps/reference/domains/execution_position/fsm.py`
**Lines:** ~5800
**Auditor:** Antigravity

## 1. Загальна Оцінка: 3/10

Файл `fsm.py` є класичним прикладом **"God Object"** (Божественного Об'єкта). Він порушує майже всі принципи SOLID, особливо Single Responsibility Principle (SRP).

*   **Читабельність:** Низька. Логіка розмазана по 5800 рядках.
*   **Підтримуваність:** Критично низька. Будь-яка зміна ризикує зламати непов'язаний функціонал.
*   **Тестованість:** Важка. Потрібно мокати десятки залежностей (adapter, guardian, watchdog, exposure, config, wal).
*   **Надійність:** Середня, тримається на "милицях" (try-except blocks, timeouts).

---

## 2. Критичні Проблеми

### 2.1. Архітектурний Хаос (God Class)
Клас `ExecPosFSM` знає і робить занадто багато:
1.  **Orchestrator:** Керує `OpenFlow`, `ManageFlow`, `CloseFlow`.
2.  **Adapter Proxy:** Обгортає виклики до біржі (`_call_adapter_fn`).
3.  **Watchdog:** Містить логіку `AggOcoWatchdog` (рядки 2009-2283).
4.  **Exposure Guard:** Інтегрується з ризик-менеджментом.
5.  **WAL Manager:** Відповідає за реплей логів (`replay_on_startup`).
6.  **Metrics Aggregator:** Збирає метрики з усіх компонентів.
7.  **Gatekeeper:** Реалізує логіку `SYMBOL_TIDY`.

**Наслідок:** Файл неможливо розділити на команди. Конфлікти при злитті гарантовані.

### 2.2. Змішування Асинхронності та Синхронності
Метод `_call_adapter_fn` (рядки 1552-1576) намагається бути універсальним солдатом:
```python
if asyncio.iscoroutinefunction(f):
    return await f(*args, **kwargs)
else:
    result = f(*args, **kwargs)
    if asyncio.iscoroutine(result):
        return await result
```
Це створює непередбачувану поведінку блокування Event Loop, якщо адаптер синхронний і повільний.

### 2.3. Fragile Exception Handling ("String Matching")
Логіка покладається на парсинг текстових повідомлень помилок:
-   `_is_qty_rounding_error`: перевіряє "Quantity rounds to zero with stepSize"
-   `_is_unknown_order_error`: перевіряє "unknown order"
-   `_is_cancel_success_response`: перевіряє статус або код -2011.

**Ризик:** Якщо біржа або бібліотека змінить текст помилки, система впаде.

---

## 3. Дублювання Коду

### 3.1. Tick Size Resolution
Логіка отримання `tick_size` розкидана і дубльована:
-   `fsm.py`: `_execute_decision` (рядки 4132-4145)
-   `fsm_manage.py`: `_place_brackets_legacy`
-   `fsm_manage.py`: `_place_brackets_aggregated`

### 3.2. Client Order ID Generation
Генерація ID відбувається в `utils.py`, але `fsm.py` також має логіку парсингу та маніпуляції ID (наприклад, `_derive_aggregated_bracket_key`).

### 3.3. Watchdog Logic
`AggOcoWatchdog` реалізований всередині `fsm.py` (методи `_run_agg_oco_watchdog_once`, `_heal_...`), хоча існує окремий файл `agg_oco_watchdog.py` (який, схоже, містить лише допоміжні функції або стару версію). Це порушення модульності.

---

## 4. Неправильні Методи та Реалізації

### 4.1. `_execute_decision` (рядки 3728-4756)
Цей метод — монстр на **1000 рядків**. Він містить:
-   Логіку перевірки `domain_mode` (testnet/live guardrails).
-   Обробку `CANCEL_ORDER`.
-   Обробку `PLACE_ORDER` (з retry loop для -2021).
-   Обробку `CLOSE` (найскладніша частина з "Phase A1/A2", "Quick Profit", "By-Entry Close").

**Вердикт:** Цей метод має бути розбитий на окремий клас `ExecutionService`.

### 4.2. `_closing_position` Timeout (Race Condition)
Як зазначено в попередньому аудиті, використання таймаутів (800ms) для синхронізації стану закриття є ненадійним.
```python
# Рядок 3598
manage._closing_position = True
manage._closing_position_ts = time.time()
```
Це "милиця" замість справжньої синхронізації станів.

### 4.3. `_truthy_flag`
```python
def _truthy_flag(value: Any) -> bool:
    # ... "yes", "on", "1" ...
```
Це виглядає як "велосипед". Pydantic або стандартні бібліотеки мають це робити на рівні конфігурації.

---

## 5. Обгрунтування Розміру (Чому так сталося?)

Така кількість коду (5800 рядків) **НЕ Є обгрунтованою** технічною необхідністю. Це результат:
1.  **Organic Growth:** Функціонал додавався поступово ("ще один if", "ще один метод") без рефакторингу.
2.  **Fear of Refactoring:** Розробники боялися виносити код, щоб не зламати критичний шлях виконання.
3.  **Lack of Abstractions:** Відсутність чітких шарів (наприклад, `ExecutionLayer`, `RiskLayer`, `ObservabilityLayer`). Всі вони злилися в один `ExecPosFSM`.

## 6. Рекомендації (Plan of Action)

1.  **Extract `AggOcoWatchdog`:** Винести всю логіку `_agg_oco_watchdog_loop` та `_heal_...` в окремий клас/файл. (-500 рядків).
2.  **Extract `ExecutionService`:** Винести `_execute_decision` та `_call_adapter_fn` в окремий сервіс, що відповідає лише за спілкування з біржею. (-1200 рядків).
3.  **Extract `Gatekeeper`:** Винести логіку `SYMBOL_TIDY` та `_entry_tidy_gate_allow`. (-100 рядків).
4.  **Refactor `_closing_position`:** Замінити прапорці та таймаути на явну машину станів (`State Pattern`).

**Фінальний вердикт:** Файл потребує негайного "розпилу", інакше він стане (або вже став) головним джерелом багів та блокером для розвитку системи.
