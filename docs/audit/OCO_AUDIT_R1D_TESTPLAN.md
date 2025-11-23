# PACK OCO-AUDIT-R1 — R1-D Test Plan for Aggregated OCO

**Date:** 2025-11-23  
**RID:** OCO-AUDIT-R1-D-TESTPLAN  
**Type:** Test design (no tests implemented yet)  
**Scope:** ExecPosRuntimeV2 + BracketService + Aggregated OCO race/size invariants

---

## 1. Ціль

- На основі R1‑A/B/C сформувати **контрактний** тестовий пакет для Aggregated OCO:
  - покрити зміну розміру позиції (partial close, scale‑in, reverse),
  - покрити full close + new entry same symbol,
  - покрити timeout / stale ORDERS_SNAPSHOT / UNKNOWN snapshot_state,
  - покрити manual cancel TP/SL (якщо дозволено сценарієм).
- Тести будуть реалізовані у фазі `PACK: OCO-STABILIZE-R2`, на етапі R1 — лише проектування.

---

## 2. Пропонована структура тестових файлів

- `tests/domains/execution_position/test_agg_oco_size_sync.py`  
  → сценарії зміни розміру позиції (partial close, scale‑in, reverse).

- `tests/domains/execution_position/test_agg_oco_races_close_and_reopen.py`  
  → full close + новий entry по тому ж символу; reverse + orphans.

- `tests/domains/execution_position/test_agg_oco_timeout_and_snapshot_state.py`  
  → timeout’и, empty/stale ORDERS_SNAPSHOT, snapshot_state `UNKNOWN/STALE/FRESH`.

Крім того, частина існуючих тестів (`test_bracket_service.py`, `test_oco_scenarios_v2_full.py`, `test_execpos_v2_*`) буде **рефакторитись** для повторного використання фікстур і сценаріїв.

---

## 3. Група 1 — Position Size Change (partial close, scale-in, reverse)

### TEST-OCO-R1-001 — Partial close reduces bracket qty

- **Type:** Unit + integration (BracketService + ExecPosRuntimeV2).  
- **Given:**
  - LONG позиція `qty=2.0`, `avg_entry_price=100.0`.
  - Активні SL/TP: SELL reduceOnly, `quantity=2.0`.
  - FRESH ORDERS_SNAPSHOT (локальний mirror узгоджений з біржею).
- **When:**
  - Приходить partial close fill `TRADE_EXECUTED` SELL `quantity=0.5` @ 102.0.
  - Виконується `_handle_trade_executed` + `_evaluate_brackets(reason="trade_executed")`.
- **Then:**
  - `BracketPlan` (або послідовність evaluate‑викликів) забезпечує:
    - `sum(bracket_qty) ≤ abs(position_qty_after)` (ціль — R1‑B‑INV‑1/3).
    - Немає залишку SL/TP, які перевищують розмір позиції.
- **Classes:** `ExecPosRuntimeV2`, `BracketService`, `PositionState`, `ExecutionService` (mock).  
- **Invariants/Risks:** R1‑B‑INV‑1/3, R1‑C‑RISK‑3.

### TEST-OCO-R1-002 — Scale-in recomputes price and qty

- **Type:** Integration (ExecPosRuntimeV2).  
- **Given:**
  - Початковий fill LONG 1.0 @ 100.0 → SL/TP на 1.0.
  - `_open_orders_by_symbol` містить ці SL/TP.
- **When:**
  - Другий fill LONG 1.0 @ 110.0 (scale‑in) через `TRADE_EXECUTED`.
- **Then:**
  - `PositionState.qty == 2.0`, `avg_entry_price == 105.0`.
  - BracketService через `stale_levels` генерує план:
    - CANCEL старих SL/TP,
    - PLACE_SL/TP на `qty=2.0` з новими рівнями.
- **Classes:** `ExecPosRuntimeV2`, `BracketService`, `ExecutionService` (AsyncMock).  
- **Invariants/Risks:** R1‑B‑INV‑1, R1‑B‑INV‑5.

### TEST-OCO-R1-003 — Reverse cancels previous side brackets and protects new side

- **Type:** Integration (ExecPosRuntimeV2 with guardian stub).  
- **Given:**
  - LONG `qty=2.0` з SL/TP SELL reduceOnly.
  - Ордери відображені в `_open_orders_by_symbol`.
- **When:**
  - Reverse fill: SELL `quantity=4.0` @ 95.0 → SHORT `qty=2.0`.
- **Then (desired contract):**
  - План включає:
    - CANCEL усіх SL/TP для LONG (старої сторони),
    - PLACE_SL/TP для SHORT (нової сторони).
  - Після застосування плану:
    - На біржі й у mirror немає активних LONG‑brackets.
- **Classes:** `ExecPosRuntimeV2`, `BracketService`, `ExecutionService`, `guardian` (AsyncMock).  
- **Invariants/Risks:** R1‑B‑INV‑4, R1‑C‑RISK‑4.

### TEST-OCO-R1-004 — Partial close via TP/SL fill (reduceOnly)

- **Type:** Unit (BracketService) + integration (runtime scenario runner).  
- **Given:**
  - LONG `qty=2.0`, SL/TP кожен на 2.0.
  - Partial fill TP на 1.0 (reduceOnly) → позиція `qty=1.0`.
- **When:**
  - Відновлюється state через POSITION_SYNC + ORDERS_SNAPSHOT (один SL/TP на 1.0, один уже FILLED).
  - Запускається evaluate / guard_loop.
- **Then:**
  - BracketService не генерує перевищення qty (ніяких PLACE_* з qty > 1.0).
  - Орфан‑ордери (якщо є) помічаються і CANCEL’яться.
- **Invariants/Risks:** R1‑B‑INV‑1/3, R1‑C‑RISK‑3.

---

## 4. Група 2 — Full close + new entry same symbol

### TEST-OCO-R1-010 — Full close via bracket SL/TP + new entry

- **Type:** Integration (ExecPosRuntimeV2 + fake adapter).  
- **Given:**
  - LONG позиція `qty>0` з активними SL/TP.
  - Bracket SL/TP існують на біржі та в `_open_orders_by_symbol`.
- **When:**
  1. SL або TP повністю закриває позицію (fill + ACCOUNT_UPDATE/ORDERS_SNAPSHOT).
  2. Невдовзі приходить новий `CMD:OPEN` по тому ж `symbol`.
  3. Новий entry заповнюється (TRADE_EXECUTED) і тригерить `_evaluate_brackets`.
- **Then:**
  - Старі SL/TP:
    - або відсутні в mirror на момент нової evaluate,
    - або явно визначені як orphans і CANCEL’яться до/при створенні нових brackets.
  - Немає сценарію, де нова позиція вважається захищеною SL/TP, яких фактично більше нема на біржі.
- **Classes:** `ExecPosRuntimeV2`, `ExecutionService` (spy), fake `BinanceAdapter`.  
- **Invariants/Risks:** R1‑B‑INV‑2, R1‑C‑RISK‑1/2.

### TEST-OCO-R1-011 — Manual DEC:CLOSE + new CMD:OPEN

- **Type:** Integration (RuntimeFacade + runtime).  
- **Given:**
  - LONG позиція з SL/TP.
- **When:**
  1. `CMD:CLOSE` від DecisionMaking → CLOSE_INTENT.
  2. Позиція стає FLAT через TRADE_EXECUTED/ACCOUNT_UPDATE.
  3. Новий `CMD:OPEN` по тому ж символу → нова LONG позиція.
  4. Тригериться bracket evaluation для нової позиції.
- **Then:**
  - Cleanup SL/TP від попередньої позиції не видаляє brackets, створені для нової (немає symbol‑only cleanup без позиційних перевірок).
  - Нові TP/SL будуються з нуля або коректно пере‑прив’язуються (через майбутній `position_id` / versioning).
- **Invariants/Risks:** R1‑B‑INV‑2, R1‑C‑RISK‑2.

---

## 5. Група 3 — Timeout / stale ORDERS_SNAPSHOT / UNKNOWN snapshot_state

### TEST-OCO-R1-020 — Empty ORDERS_SNAPSHOT with open position

- **Type:** Integration (ExecPosRuntimeV2, без реальної біржі).  
- **Given:**
  - Позиція `qty>0` в `_positions_by_symbol`.
  - `_open_orders_by_symbol[symbol]` містить поточні SL/TP.
- **When:**
  - Приходить `ORDERS_SNAPSHOT` з `orders=[]` (наприклад, Binance тимчасово віддає пустий список).
  - Потім `TRADE_EXECUTED` або `POSITION_SYNC`.
- **Then:**
  - Тест‑інваріант: або:
    - `_open_orders_by_symbol[symbol]` явно синхронізується з `orders=[]`, **або**
    - існує окремий механізм, який не дозволяє трактувати старі ордери як актуальні при `result="empty"`.
  - В майбутній реалізації — перевірка R1‑C‑RISK‑1 (відсутність stale локального mirror при `orders=[]`).
- **Invariants/Risks:** R1‑C‑RISK‑1.

### TEST-OCO-R1-021 — Timeout placing SL/TP forces UNKNOWN snapshot_state

- **Type:** Integration (ExecPosRuntimeV2 + ExecutionService stub, вже частково покрито в S2).  
- **Given:**
  - Новий план `PLACE_SL/PLACE_TP`.
- **When:**
  - `ExecutionService.place_order` повертає `{"success": False, "error_kind": "ADAPTER_ERROR_TIMEOUT"}`.
- **Then:**
  - `_orders_snapshot_state[symbol] == "UNKNOWN"`, `_last_orders_snapshot_ts[symbol] == 0.0`.
  - Викликається `_request_orders_snapshot(force=True)`.
  - `_evaluate_brackets` блокується до приходу нового ORDERS_SNAPSHOT.
- **Invariants/Risks:** R1‑C‑RISK‑5 (match with existing S2 contract).

### TEST-OCO-R1-022 — Snapshot TTL + guard_loop skips evaluation on STALE for account_update_sync

- **Type:** Unit/integration (runtime with mocked time).  
- **Given:**
  - `_orders_snapshot_state[symbol] == "FRESH"`, але `time.monotonic()` просунутий так, що TTL вийшов.
- **When:**
  - Викликається `_evaluate_brackets(symbol, position, reason="account_update_sync")`.
- **Then:**
  - `snapshot_state` переводиться в `"STALE"`.
  - Evaluate пропускається з `BRACKETS result="snapshot_blocked"`.
  - Валідується, що це **fail-closed** шлях для account_update, але не для `trade_executed`.
- **Invariants/Risks:** R1‑C‑RISK‑5.

---

## 6. Група 4 — Manual cancel TP/SL

### TEST-OCO-R1-030 — Manual cancel SL only (position still open)

- **Type:** Unit (BracketService) + integration (runtime).  
- **Given:**
  - Позиція `qty>0`.
  - Є SL+TP; користувач вручну скасовує SL (через DEC:CANCEL / UI).
  - ORDERS_SNAPSHOT відображає TP, але SL відсутній.
- **When:**
  - Запускається evaluate (через TRADE_EXECUTED, POSITION_SYNC або guard_loop).
- **Then (desired):**
  - Якщо стратегія **вимагає SL**:
    - `BracketPlan` з `MISSING_SL` → PLACE_SL (і, за потреби, PLACE_TP).
  - Якщо `allow_unprotected_position=True`:
    - Plan `severity="INFO"`, жодних PLACE_SL — manual cancel поважаємо.
- **Invariants/Risks:** R1‑B‑INV‑1/2, узгодження з config flags.

### TEST-OCO-R1-031 — Manual cancel both SL and TP

- **Type:** Unit (BracketService).  
- **Given:**
  - `BracketState` з position_view.qty>0, але `bracket_set=None`.
- **When:**
  - `evaluate(state, cfg)` з різними `allow_unprotected_position`.
- **Then:**
  - Чітка поведінка:
    - або ALERT + `PLACE_SL/TP`,
    - або INFO без дій (manual unprotected дозволений).
- **Invariants/Risks:** R1‑B‑INV‑1/2, контроль fail‑open vs fail‑closed.

---

## 7. Мапа «тест → інваріант/ризик»

| Test ID | Type | Основні інваріанти / ризики |
| --- | --- | --- |
| TEST-OCO-R1-001 | size change | R1‑B‑INV‑1, R1‑B‑INV‑3, R1‑C‑RISK‑3 |
| TEST-OCO-R1-002 | size change | R1‑B‑INV‑1, R1‑B‑INV‑5 |
| TEST-OCO-R1-003 | size change | R1‑B‑INV‑4, R1‑C‑RISK‑4 |
| TEST-OCO-R1-004 | size change | R1‑B‑INV‑1/3, R1‑C‑RISK‑3 |
| TEST-OCO-R1-010 | full close + new entry | R1‑B‑INV‑2, R1‑C‑RISK‑1/2 |
| TEST-OCO-R1-011 | full close + new entry | R1‑B‑INV‑2, R1‑C‑RISK‑2 |
| TEST-OCO-R1-020 | snapshot empty | R1‑C‑RISK‑1 |
| TEST-OCO-R1-021 | timeout → UNKNOWN | R1‑C‑RISK‑5, S2‑timeout contract |
| TEST-OCO-R1-022 | STALE for account_update_sync | R1‑C‑RISK‑5 |
| TEST-OCO-R1-030 | manual cancel SL | R1‑B‑INV‑1/2, config semantics |
| TEST-OCO-R1-031 | manual cancel SL+TP | R1‑B‑INV‑1/2 |

---

## 8. Домени та фікстури

- **Домени / класи:**
  - `ExecPosRuntimeV2` (головний інтеграційний об’єкт).
  - `BracketService` (pure‑unit tests для інваріантів).
  - `ExecutionService` (mock/stub для edge‑cases: timeout, adapter errors).
  - `AggOcoWatchdogService` (детект‑only; в тестах потрібен для валідації recommendations).
  - `PositionState` / `apply_fill` (unit tests для scale‑in / partial close / reverse).
  - Fake/mock `BinanceAdapter` (для поведінки get_open_orders, place_order).

- **Фікстури:**
  - Runtime з:
    - мінімальним `config={"execution_position": {"aggregated_oco": {...}}}`,
    - mock ExecutionService / adapter.
  - BracketService з stub‑aggregator (`sl_price`, `tp_price` фіксуються).
  - Clock/time фікстура для контролю TTL (`time.monotonic` patch).

---

## 9. Додатковий ROADMAP для OCO-STABILIZE-R2

- Додати в ROADMAP/TODO фазу:

> **PACK: OCO-STABILIZE-R2 — імплементація тестів і фіксів за OCO-AUDIT-R1**  
> - Реалізувати тести TEST-OCO-R1-XXX у файлах:  
>   - `tests/domains/execution_position/test_agg_oco_size_sync.py`  
>   - `tests/domains/execution_position/test_agg_oco_races_close_and_reopen.py`  
>   - `tests/domains/execution_position/test_agg_oco_timeout_and_snapshot_state.py`  
> - Поетапно впровадити інваріанти R1‑B‑INV‑* та усунути ризики R1‑C‑RISK‑*.  
> - Оновити контракт `EXEC_POS_BRACKETS_CONTRACT.md` та `EXEC_POS_V2_RUNTIME_SPEC.md` відповідно до нової поведінки.

Цей документ завершує дизайн тестпакету для Aggregated OCO в рамках PACK OCO-AUDIT-R1.

