# Execution Position FSM Safety — Implementation Plan

Дата: 2025-12-23

## 0) Передумови / поточні симптоми (evidence-based)

### Симптом
- Є `CMD:OPEN` (і в логах bridge, і в WAL), але немає **жодного** термінального outcome на рівні execution domain:
  - немає `DEC:OPEN` (open flow не стартує),
  - немає `ERR:OPEN` (немає фіксації причини відмови),
  - і часто немає слідів у `domain_execution_management.log`.

### Ключові докази
- WAL для рядів (BTC/ETH/DOGE) містить `EVT:TRADE_INTENT_PROPOSED` + `CMD:OPEN`, але **без** `DEC:*` / `ERR:*`.
- У `logs/order_log_v1.jsonl` є записи від `ExposureGuard` з `symbol == ""` та дефолтним `side="SELL"` → це ознака некоректного виклику `reserve()` без даних.

### Гіпотеза, що підтверджується кодом
- `ExecPosFSM.handle(OPEN)` виконує fail-closed exposure gate **до** open-flow. Якщо gate блокує — відбувається `return None` без гарантованого durable-сигналу.
- `ExposureGuard.reserve()` викликається з дефолтами (або в блокуючій гілці), що створює “phantom reservations” і може з’їдати capacity.

### Підтверджено в коді (конкретні дефекти)
1) **`reserve()` викликається без `symbol/side`** у `fsm.py`, а `exposure_guard.reserve()` має дефолти `symbol=""`, `side="SELL"` → у логах з’являються записи з порожнім `symbol`.
2) **“Paranoid reserve” при блокуванні**: при `can_open()==False` все одно відбувається `reserve()` → це логічно некоректно (резервувати exposure для відхиленого open не можна).
3) **`ERR:OPEN` емітиться асинхронно без гарантій**: якщо async loop відсутній/недоступний, `ERR` може ніколи не з’явитися, а `CMD:OPEN` “зникає” без слідів.
4) **Exception-path не є fail-closed**: якщо в `_check_exposure_fail_closed()` стається виняток, поточна поведінка має блокувати відкриття та синхронно фіксувати `ERR:OPEN` (зараз у деяких реалізаціях помилки можуть пропускати open далі).

---

## 1) Мета

1) Усунути “silent failures” у обробці `CMD:OPEN`.
2) Забезпечити **цілісність даних** у `ExposureGuard` (жодних `symbol==""`, коректні `side/leverage`).
3) Для кожного `CMD:OPEN` забезпечити **термінальний outcome**:
   - або `DEC:OPEN` (успішний старт open flow),
   - або `ERR:OPEN` / `DEC:DROP` з чітким `reason_code`.

---

## 2) Non-goals (щоб не роздувати scope)

- Не змінюємо стратегії DecisionMaking, QoS, Arbitration.
- Не додаємо нові “nice-to-have” метрики/дашборди.
- Не робимо великий рефактор усіх FSM — лише точкові гарантії для `CMD:OPEN`.

---

## 3) Інваріанти (контракти, які мають стати правдою)

### I-A: CMD→(DEC|ERR)
Для кожного `CMD:OPEN` (визначаємо по `rid` + `idempotent_key`) в рамках одного запуску має з’явитися рівно один термінальний outcome:
- `DEC:OPEN_*` **або** `ERR:OPEN_*` (або `DEC:DROP_*` — якщо так називаємо відмови).

### I-B: Reservation integrity
Будь-який reserve/intent від `ExposureGuard` повинен мати:
- `symbol != ""`
- `side in {"BUY","SELL"}`
- `leverage > 0`
- кореляцію: `rid`, `idempotent_key`

### I-C: Fail-closed ≠ silent
Fail-closed блокування на exposure gate:
- завжди пише в WAL (sync),
- завжди логиться в execution management log (structured),
- не залежить від async loop.

---

## 4) User Review Required (важливо)

**Ця зміна змінює поведінку ExposureGuard:**
- `reserve()` **більше не викликається** для заблокованих `OPEN`.

Це є виправленням логіки (phantom reservations — некоректні), але може змінити старі метрики/патерни спостереження.

---

## 5) Пропоновані зміни (Implementation)

### 5.1) Execution Position Domain — `fsm.py`
Файл: `apps/reference/domains/execution_position/fsm.py`

#### 5.1.1 Synchronous Fail-Closed
Оновити `_check_exposure_fail_closed()` так, щоб він:
- отримував повний payload команди (`rid`, `symbol`, `side`, `leverage`, `idempotent_key`, `notional/qty` якщо є);
- викликав `can_open()` і **якщо blocked**:
  - **синхронно** писав `ERR:OPEN` (або `DEC:DROP`) у WAL (best-effort, але sync),
  - писав структурований лог в `domain_execution_management.log` (щоб grep ловив `EXPOSURE_FAIL_CLOSED_OPEN_BLOCKED`),
  - повертав `blocked=True`.

Додатково:
- У `except Exception` гілці `_check_exposure_fail_closed()` має бути **fail-closed**:
  - синхронно записати `ERR:OPEN` з `reason_code=EXPOSURE_CHECK_ERROR`,
  - повернути `blocked=True` (а не пропускати open далі).

> Важливо: не покладатися на async emitter для первинної фіксації причини.

#### 5.1.2 Reservation Fixes
В `handle(OPEN)`:
- витягти `symbol`, `side`, `leverage` явно з msg;
- **викликати `reserve()` тільки якщо `can_open()` пройшов**;
- передавати в `reserve()` правильні значення:
  - `symbol=msg.symbol`
  - `side=msg.side`
  - `leverage=msg.leverage`
  - кореляція: `rid`, `idempotent_key`

Явно заборонено:
- “paranoid reserve” у блокуючій гілці (`can_open()==False`) — видалити. Якщо потрібна audit-подія, робити окремий лог/EVT без впливу на exposure.

#### 5.1.3 Idempotency
- Переконатися, що повторний `CMD:OPEN` з тим самим `idempotent_key`:
  - не додає резерв повторно,
  - повертає детермінований outcome (наприклад `ERR:OPEN_ALREADY_HANDLED` або “no-op”).

### 5.2) ExposureGuard — `exposure_guard.py`
Файл: `apps/reference/domains/execution_position/exposure_guard.py`

#### 5.2.1 Enforce symbol presence
- Змінити `reserve()` так, щоб `symbol` був обов’язковим:
  - якщо `symbol` порожній — `raise ValueError` або `assert` (краще `ValueError` з повідомленням).

#### 5.2.2 Side handling
- Визначати напрямок експозиції через `side`, а не через знак notional (де це можливо).
- Якщо десь ще використовується “sign-by-notional”, зафіксувати єдиний контракт:
  - `side` — primary, notional sign — derived.

### 5.3) WAL / Logging contract
- Для blocked `OPEN` вводимо стабільний `reason_code` (наприклад: `EQUITY_UNKNOWN`, `PORTFOLIO_STALE`, `UTILIZATION_EXCEEDED`, `DIR_RATIO_EXCEEDED`, ...).
- У WAL та логах обов’язкові поля:
  - `rid`, `idempotent_key`, `symbol`, `side`, `reason_code`, і мінімальні цифри (equity/utilization) за можливості.

---

## 6) План тестування

### 6.1 Unit tests (обов’язково)

1) **Fail-Closed Unit Test**
- Arrange: змусити `ExposureGuard.can_open()` повернути blocked (наприклад `EQUITY_UNKNOWN`).
- Act: `ExecPosFSM.handle(CMD:OPEN)`.
- Assert:
  - у WAL writer (mock / tmp WAL) з’являється `ERR:OPEN` з `rid/symbol/side/reason_code`;
  - `reserve()` **не викликаний**;
  - немає жодних записів з `symbol==""`.

1b) **Fail-Closed on Exception Unit Test**
- Arrange: змусити `_check_exposure_fail_closed()` кинути виняток (наприклад через mock у `can_open()` або некоректний payload).
- Assert:
  - open блокується (fail-closed),
  - синхронно з’являється `ERR:OPEN` з `reason_code=EXPOSURE_CHECK_ERROR`.

2) **Reservation Args Unit Test**
- Arrange: `can_open()` → pass.
- Act: `handle(CMD:OPEN)`.
- Assert: `reserve()` викликаний з коректними `symbol/side/leverage` та кореляцією.

3) **Idempotency Unit Test**
- Arrange: два рази викликати `handle(CMD:OPEN)` з тим самим `idempotent_key`.
- Assert: reserve не “росте” при повторі; outcome детермінований.

### 6.2 Integration tests (WAL/лог контракт)

4) **CMD→Terminal Outcome Integration**
- Прогнати мінімальний шлях: bridge → execution_position.
- Assert: у WAL для кожного `CMD:OPEN` є або `DEC:OPEN`, або `ERR:OPEN`.

5) **Log Regression: No empty symbol**
- Після тестового прогона згенерувати тестовий `order_log_v1.jsonl` (в tmp dir) і перевірити:
  - немає жодного рядка з `source_fsm=="ExposureGuard"` і `symbol==""`.

6) **No Reserve on Blocked Attempt**
- Arrange: `can_open()==False`.
- Assert: internal reservations не збільшуються (0 нових резервацій).

> Примітка: тести мають писати всі артефакти (WAL/log) у `tmp_path`, щоб не бруднити `ops/wal`.

### 6.3 Manual verification (швидкий чек)

- Запустити через `main.py` (або мінімальний integration script).
- Примусово згенерувати ситуацію fail-closed (наприклад відключити portfolio updates або підставити `equity=None`).
- Перевірити:
  - з’являється `ERR:OPEN` у WAL,
  - у логах є `EXPOSURE_FAIL_CLOSED_OPEN_BLOCKED`.

---

## 7) Definition of Done (DoD)

- **DoD-1**: У тестах та в локальному прогонах немає записів `ExposureGuard` з `symbol==""` (автотест).
- **DoD-2**: Кожний `CMD:OPEN` у WAL має термінальний outcome `DEC:OPEN` або `ERR:OPEN` (integration test).
- **DoD-3**: Fail-closed блокування пише WAL sync (unit test), незалежно від async loop.
- **DoD-3b**: Будь-який exception у exposure-check → fail-closed + sync `ERR:OPEN` (unit test).
- **DoD-4**: Повторний `CMD:OPEN` з тим самим `idempotent_key` не змінює резерви/експозицію (unit test).
- **DoD-5**: `pytest` проходить для змінених/доданих тестів; якщо є старі фейли поза scope — вони задокументовані окремо.

### Статус DoD (2025-12-23)
- DoD-1: ✅ додано regression-тест (no `symbol==""` в `ExposureGuard` логах у рамках тестів).
- DoD-2: ✅ є integration-тест на fail-closed WAL (`tests/integration/test_execpos_fail_closed_wal_integration_v1.py`).
- DoD-3/3b: ✅ unit + integration підтверджують sync `ERR:OPEN` і fail-closed на exception.
- DoD-4: ✅ `reserve()` idempotent по ключу (unit).
- DoD-5: ✅ цільові набори тестів зелені (execpos fail-closed + exposure matrix + open-flow guards/leverage + soft-clip).

---

## 8) План впровадження (порядок)

1) `fsm.py`: синхронний `ERR:OPEN` + прибрати reserve на blocked + правильні args.
2) `exposure_guard.py`: enforce `symbol` + side handling.
3) Unit tests.
4) Integration tests.
5) `pytest`.
6) Короткий smoke run та перевірка WAL/логів.

### Чек-лист викату (мінімальний, fail-closed safe)
1) Перед деплоєм:
  - Переконатися, що `trading.execution.exposure.leverage_defaults` має `__default__` і ключі для топ-символів.
  - Переконатися, що в live-профілі для кожного інструмента є `instruments.<SYM>.execution.{margin_mode,target_leverage,leverage_policy}` якщо використовується leverage verification.
2) Деплой/рестарт сервісів:
  - Рестарт `execution_position` (і bridge, якщо потрібно) з чистими логами для валідації.
3) Після рестарту (5–15 хв):
  - WAL: на кожен `CMD:OPEN` має з’являтися `DEC:OPEN` або `ERR:OPEN` (тепер `ERR` durable sync).
  - Логи: відсутні `ExposureGuard` записи з `symbol==""`.
  - Метрики/спостереження: можливий спад “reservation volume” (бо прибрали phantom reserve) — це очікувано.
4) Якщо бачимо `ERR:OPEN` через exposure gate:
  - Зняти `reason_code` і перевірити portfolio/equity оновлення; це більше не буде “silent”.

---

## 9) Ризики та пом’якшення

- Ризик: зміна поведінки метрик (бо прибираємо phantom reserve).
  - Мітігація: додати явний лог “attempt blocked” без впливу на exposure.
- Ризик: злам сумісності, якщо десь викликають `reserve()` без symbol.
  - Мітігація: швидко знайти всі виклики через grep/semantic search + оновити.

---

## 10) Відкриті питання (якщо потрібні рішення)

1) Чи потрібно вводити окремий тип події `DEC:DROP_OPEN` замість `ERR:OPEN`?
2) Де саме має жити “release” резерва, якщо reserve робимо до open-flow, а потім qty-guards відмовляють?
3) Чи потрібен таймаутний “watchdog” для випадків, коли `DEC:OPEN` не приходить через падіння адаптера?
