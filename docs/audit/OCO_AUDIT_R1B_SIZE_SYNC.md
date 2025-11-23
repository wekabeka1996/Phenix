# PACK OCO-AUDIT-R1 — R1-B TP/SL Size Synchronization Audit

**Date:** 2025-11-23  
**RID:** OCO-AUDIT-R1-B-SIZE-SYNC  
**Type:** Read-only audit (no code changes)  
**Scope:** Aggregated OCO / TP‑SL size behavior in `ExecPosRuntimeV2` + `BracketService`

---

## 1. Ціль і контекст

- Перевірити, як зараз Aggregated OCO синхронізує **обсяг TP/SL** з:
  - частковим закриттям позиції (partial close),
  - добором в ту ж сторону (scale‑in),
  - реверсом (flip / reverse),
  - повним закриттям позиції (full close).
- Виявити:
  - де є явна/неявна логіка перерахунку обсягу/рівнів TP/SL,
  - де cleanup при `position_qty → 0` покладається на DR / watchdog / зовнішні сервіси,
  - де існує ризик розриву інваріантів «position_qty vs bracket_qty».

Фокус: `apps/reference/domains/execution_position/shadow_execpos/runtime.py` + `bracket_service.py` + `position_model.py` + `watchdog.py`.

---

## 2. Інвентар size‑залежної логіки

### 2.1 Де перераховується позиція

- `PositionState` + `apply_fill` (`position_model.py`):
  - **Scale‑in (same side):**  
    - `new_qty = state.qty + signed_fill`  
    - `new_avg = (state.avg_entry_price * |state.qty| + price * quantity) / |new_qty|`  
    - `scale_in_count++`.
  - **Partial close (same side remains):**  
    - `closing_qty = min(abs(state.qty), quantity)`  
    - `new_qty = state.qty + signed_fill` (same sign)  
    - `avg_entry_price` зберігається; `scale_out_count++`.
  - **Flip / reverse (side changes):**  
    - `new_qty` змінює знак → новий `PositionState` з `avg_entry_price = fill_price`, `scale_in_count=0`.
  - **Full close (flat):**  
    - `abs(new_qty) < 1e-12` → `qty=0`, `avg_entry_price=0`, `open_time=None`, `scale_out_count++`.

- `_handle_trade_executed` (`runtime.py`):
  - Викликає `apply_fill`, зберігає `new_state` в `_positions_by_symbol[symbol]`.
  - Після оновлення:
    - пише WAL (`write_trade_wal`, `write_position_wal`),
    - шле exposure update,
    - запускає `_run_watchdog_analysis()`,
    - викликає `_evaluate_brackets(symbol, new_state, reason="trade_executed")`,
    - викликає `_evaluate_trailing(...)`.

### 2.2 Де залежать TP/SL від position_qty / position_value

- `BracketService.evaluate(state, cfg)`:
  - Для **MISSING_SL / MISSING_TP**:
    - `qty` для `PLACE_SL` / `PLACE_TP` = `state.position_view.qty` (aggregated qty).
  - Для **STALE_LEVELS** (перерахунок рівнів):
    - так само використовує `state.position_view.qty` при `PLACE_SL` / `PLACE_TP`.
  - **НЕ** перевіряє суму qty існуючих SL/TP проти `position_qty`.

- `_evaluate_brackets(symbol, position, reason)` (`runtime.py`):
  - Будує `BracketPositionView` з:
    - `qty = Decimal(abs(position.qty))`,
    - `avg_entry_price = Decimal(position.avg_entry_price)`.
  - Далі `BracketService.build_state(...)` + `evaluate(...)` → `BracketPlan`.

- `_apply_bracket_plan(symbol, position, plan, reason)`:
  - Для `PLACE_SL` / `PLACE_TP` / `ADJUST`:
    - `qty = float(action.qty)` якщо задано, **інакше** `abs(position.qty)`.
  - Тобто нові/відкориговані SL/TP завжди ставляться або на `state.position_view.qty`, або на `abs(PositionState.qty)` якщо `action.qty` не заданий.

### 2.3 Де відбувається cleanup при `position_qty → 0`

- **На рівні BracketService:**
  - `state.is_flat and state.has_brackets` (тобто `position_view is None` або `qty==0`, але є SL/TP):
    - `severity="WARN"`, `why="orphan_brackets|pos_flat_sl_or_tp_active"`,
    - генерує `CANCEL` для всіх SL та TP (`reason_code="ORPHAN_SL"/"ORPHAN_TP"`).

- **Хто реально викликає orphan‑cleanup:**
  - `_run_bracket_recovery_pass()` (`runtime.py`) — **одноразовий** DR‑прохід:
    - Будує `pos_views` лише для non‑flat позицій (`abs(pos.qty) > 0`).
    - Будує `order_views` для всіх ордерів за всіма символами.
    - Викликає `BracketService.evaluate_all(...)` або `evaluate_all_for_recovery(...)`:
      - Для flat‑state з орфанами → план з `CANCEL` (Invariant 1).
    - Для кожного плану викликає `_apply_bracket_plan(...)`:
      - CANCELи виконуються через `ExecutionService.cancel_order`.
      - `placed_orders` порожній → `guardian.clear_bracket_set(symbol, side)` викликається.
    - Після проходу: `_recovery_completed = True` → подальші ORDERS_SNAPSHOT не запускають цей cleanup.
  - `AggOcoWatchdogService`:
    - Також викликає `BracketService.evaluate_all(...)`, але повертає лише `WatchdogRecommendation`s.
    - `_run_watchdog_analysis()` в runtime:
      - **НЕ** виконує cancel/place; використовує рекомендації лише для:
        - `WatchdogAction.SUPPRESS_BRACKETS` → зараз **відключено**, замінено на FORCE snapshot.
        - `WatchdogAction.FORCE_SNAPSHOT` → `_request_orders_snapshot(symbol)`.

- **Важливе обмеження:**
  - `_evaluate_brackets(...)` викликається **тільки** коли `position.side in {"LONG","SHORT"}`:
    - `if position.side not in ("LONG", "SHORT"): return`.
  - Guard‑loop (`_run_guard_iteration`) бере лише non‑flat позиції.
  - `_handle_position_sync` викликає `_evaluate_brackets` тільки при `abs(current_state.qty) > 0.0001`.
  - Наслідок: після **full close** (позиція FLAT) regular‑loop **не** викликає BracketService для orphan‑cleanup; це робиться лише при DR‑pass або через зовнішній OrderGuardian.

---

## 3. Сценарії size‑sync (очікуване vs фактичне)

### 3.1 Сценарій 1 — Partial Close (часткове закриття)

**Вхідний стан (S1‑IN):**

- Position:
  - `symbol="BTCUSDT"`, `qty = 2.0`, `side=LONG`, `avg_entry_price=100.0`.
- Brackets:
  - `SL`: `STOP_MARKET SELL`, `quantity=2.0`, `stop_price=98.0`, `reduce_only=True`.
  - `TP`: `TAKE_PROFIT_MARKET SELL`, `quantity=2.0`, `stop_price=104.0`, `reduce_only=True`.
- Snapshot:
  - `_orders_snapshot_state["BTCUSDT"] == "FRESH"` (після останнього ORDERS_SNAPSHOT).

**Подія (S1‑EVT):**

- Partial close fill: `TRADE_EXECUTED`, `side="SELL"`, `quantity=0.5`, `price=102.0`.

**Очікуваний стан TP/SL (S1‑EXPECT):**

- Position:
  - `qty` → `1.5`, `avg_entry_price` зазвичай **залишається** 100.0 (partial close).
- TP/SL:
  - Обсяги SL/TP скориговано до `1.5` (не більше, ніж `abs(position_qty)`).
  - Рівні можуть бути незмінні (якщо стратегія не перераховує рівні від partial close) або перераховані за `sl_pct`/`tp_rr`.
- Інваріанти:
  - `0 < sum(SL.qty) ≤ abs(position_qty)`  
  - `0 ≤ sum(TP.qty) ≤ abs(position_qty)`.

**Фактичний алгоритм (S1‑ACTUAL):**

1. `_handle_trade_executed`:
   - `apply_fill(...)`:
     - `closing_qty = min(abs(2.0), 0.5) = 0.5`,
     - `new_qty = 2.0 - 0.5 = 1.5` (partial close),
     - `avg_entry_price` залишається 100.0.
   - Оновлює `_positions_by_symbol["BTCUSDT"]` на `qty=1.5, avg_entry_price=100.0`.
2. `_evaluate_brackets(symbol="BTCUSDT", position, reason="trade_executed")`:
   - Snapshot FRESH → дозволено.
   - Будує `PositionView` з `qty=1.5`, `avg_entry_price=100.0`.
   - Будує `OrderView` для існуючих SL/TP (`quantity=2.0` кожен).
   - `BracketService.build_state(...)`:
     - `BracketSet.position_qty = 1.5`.
     - `sl_count=1`, `tp_count=1`.
   - `BracketService.evaluate(state, cfg)`:
     - `state.is_flat == False`, `sl_count == 1`, `tp_count == 1`.
     - Умови:
       - `MISSING_SL` не тригериться.
       - `MISSING_TP` не тригериться.
       - `TOO_MANY_SL` не тригериться.
       - `STALE_LEVELS` перевіряє **ціну**, не `qty`:
         - якщо `current_sl_price == desired_sl_price` від `_compute_desired_levels`, жодних дій.
     - **Немає логіки**, яка дивиться на розбіжність `order.qty (2.0)` vs `position_qty (1.5)`.
     - План: `severity="INFO"`, `actions=[]`.
3. `_apply_bracket_plan` не викликається (plan.has_actions=False) → SL/TP залишаються на `quantity=2.0`.

**Висновок (S1‑GAP):**

- При partial close:
  - Position.qty зменшується, але **існуючі SL/TP не перераховуються по qty**, якщо не змінюється `avg_entry_price` так, щоб активувати `stale_levels`.
  - Можливий стан: `sum(bracket_qty) > abs(position_qty)` (SL/TP «прикривають» більший обсяг, ніж поточна позиція).
  - Інваріант «bracket_qty ≤ position_qty» не забезпечений на рівні BracketService/Runtime.

### 3.2 Сценарій 2 — Scale‑in (добір в ту ж сторону)

**Вхідний стан (S2‑IN):**

- Position:
  - `qty = 1.0`, `side=LONG`, `avg_entry_price=100.0`.
- Brackets:
  - `SL`: `qty=1.0`, `stop_price=98.0`.
  - `TP`: `qty=1.0`, `stop_price=104.0`.

**Подія (S2‑EVT):**

- Новий entry fill: `TRADE_EXECUTED`, `side="BUY"`, `quantity=1.0`, `price=110.0`.

**Очікуваний стан TP/SL (S2‑EXPECT):**

- Position:
  - Scale‑in: `qty = 2.0`, `avg_entry_price = 105.0` (за формулою).
- TP/SL:
  - SL/TP повинні **агреговано** захищати `2.0`:
    - або один SL/TP на `qty=2.0` з новими рівнями,
    - або кілька SL/TP, сумарний обсяг яких не перевищує 2.0.

**Фактичний алгоритм (S2‑ACTUAL):**

1. `apply_fill`:
   - `state.qty * signed_fill > 0` → scale‑in.
   - `new_qty = 1.0 + 1.0 = 2.0`.
   - `new_avg = (100*1 + 110*1)/2 = 105.0`.
2. `_evaluate_brackets(..., reason="trade_executed")`:
   - PositionView: `qty=2.0`, `avg_entry_price=105.0`.
   - OrderView: існуючі SL/TP з `qty=1.0`, `stop_price=98.0 / 104.0`.
   - `BracketService.evaluate(...)`:
     - `sl_count==1`, `tp_count==1`.
     - `_compute_desired_levels(...)` обчислює нові `sl_price` / `tp_price` від `avg_entry_price=105.0`.
     - Якщо старі рівні ≠ нові → `stale_levels`:
       - план містить `CANCEL old SL`, `PLACE_SL` з `qty=state.position_view.qty=2.0`,
       - `CANCEL old TP`, `PLACE_TP` з `qty=2.0`.
     - Якщо старі рівні випадково співпадають з новими (рідко, але можливо) → жодних дій.
3. `_apply_bracket_plan(...)`:
   - CANCEL старих SL/TP, PLACE нових:
     - `quantity=2.0` для кожного нового SL/TP (або `float(action.qty)` якщо заданий).
   - Guardian реєструє новий bracket set через `register_bracket_set`.

**Висновок (S2‑STATUS):**

- Scale‑in покритий **краще**, ніж partial close:
  - Через зміну `avg_entry_price` спрацьовує `stale_levels` → перевиставляє SL/TP **і** по ціні, і по qty.
- Умови, коли scale‑in може не перезапустити recalc:
  - Якщо `BracketRulesConfig.sl_pct/tp_rr` такі, що старі рівні випадково дорівнюють новим (крайовий кейс).

### 3.3 Сценарій 3 — Reverse (close + відкриття в протилежну сторону)

**Вхідний стан (S3‑IN):**

- Position:
  - LONG `qty=2.0`, `avg_entry_price=100.0`.
- Brackets:
  - LONG‑захист: `SL SELL qty=2.0`, `TP SELL qty=2.0`.

**Подія (S3‑EVT):**

- Reverse fill: `TRADE_EXECUTED`, `side="SELL"`, `quantity=4.0`, `price=95.0`  
  → закриває LONG і відкриває SHORT `qty=2.0`.

**Очікуваний стан TP/SL (S3‑EXPECT):**

- Старі LONG SL/TP:
  - повністю **видалені** (CANCEL), не можуть «стріляти» по новій SHORT позиції.
- Нова SHORT позиція:
  - має свій набір SL/TP (`BUY` reduceOnly) на обсяг `2.0`.
  - Немає змішування старих LONG exit‑ордерів з новим SHORT захистом.

**Фактичний алгоритм (S3‑ACTUAL):**

1. `apply_fill`:
   - Opposite direction, `closing_qty=2.0`, `new_realized_pnl` розрахований.
   - `new_qty = 2.0 - 4.0 = -2.0` → flip:
     - новий `PositionState(symbol, qty=-2.0, avg_entry_price=95.0, side=SHORT)`.
2. `_evaluate_brackets(symbol, position(side=SHORT), reason="trade_executed")`:
   - PositionView: `side="SHORT"`, `qty=2.0`, `avg_entry_price=95.0`.
   - OrderView: включає **старі** LONG‑exit ордери (SELL reduceOnly).
   - `BracketService.build_state(..., symbol=symbol, side="SHORT")`:
     - `pos_map` лише для `(symbol,"SHORT")`.
     - `orders_map` має всі ордери по symbol, але через `symbol`+`side` фільтр `all_keys = {(symbol,"SHORT")}`.
     - `_classify_orders` з `side="SHORT"`:
       - для exit‑ордерів: SHORT позиція → exit повинні бути `BUY`,
       - наявні SELL‑ордери (старі LONG brackets) **відфільтровуються** (incompatible side).
     - Результат: `BracketState` для `(symbol,"SHORT")` з:
       - `position_view` (новий SHORT),
       - `bracket_set` без SL/TP (legs=[]).
   - `BracketService.evaluate(state, cfg)` для SHORT:
     - `sl_count == 0`, `tp_count == 0` → `MISSING_SL`:
       - ALERT, `PLACE_SL` / `PLACE_TP` для SHORT на `qty=2.0`.
     - **Жодного** `CANCEL` для старих LONG SL/TP (бо вони не увійшли як леги).
3. `_apply_bracket_plan(...)`:
   - PLACE нових SHORT SL/TP (BUY reduceOnly).
   - Старі LONG SL/TP **не** відмінені на цьому кроці.
4. Cleanup старих LONG brackets теоретично можливий:
   - через `_run_bracket_recovery_pass()` (якщо ще не виконувався і орфани будуть побачені як flat‑state + brackets),
   - або через зовнішній OrderGuardian / watchdog (поза ExecPosRuntimeV2).
   - Але runtime сам по собі при цьому reverse‑fillі старі SL/TP не чистить.

**Висновок (S3‑GAP):**

- Після reverse сценарію можливий стан:
  - Нова SHORT позиція з новими BUY SL/TP,
  - Старі LONG SELL SL/TP все ще відкриті (орфани) до наступного cleanup‑циклу.
- Cleanup старих LONG brackets не гарантується **синхронно** з реверсом; залежить від DR‑pass або зовнішньої логіки.

### 3.4 Сценарій 4 — Full Close (повне закриття)

**Вхідний стан (S4‑IN):**

- Position:
  - `qty > 0` або `< 0`, з відповідними SL/TP.

**Подія (S4‑EVT):**

- Full close:
  - або через bracket SL/TP fill (reduceOnly),
  - або через manual DEC:CLOSE / MARKET reduceOnly ордер,
  - або через комбінацію fills + POSITION_SYNC.

**Очікуваний стан TP/SL (S4‑EXPECT):**

- Після того як `abs(position_qty)==0`:
  - Протягом ≤ N подій (`ORDERS_SNAPSHOT` / `POSITION_SYNC`) всі SL/TP:
    - або `CANCELED`/`FILLED`/`EXPIRED` на біржі,
    - або відсутні в локальному mirror,
    - або помічені як орфани й скасовані автоматично.

**Фактичний алгоритм (S4‑ACTUAL):**

1. Позиція стає FLAT (`apply_fill` або `_handle_single_position_update`).
2. `_evaluate_brackets(...)`:
   - Не викликається для FLAT позиції:
     - `position.side == "FLAT"` → early return.
3. Guard‑loop:
   - Обробляє лише `active_positions` з `abs(qty) > 0`.
4. Watchdog:
   - `_run_watchdog_analysis` бачить орфани через `AggOcoWatchdogService` → `WatchdogRecommendation` з `kind`/`action`.
   - Runtime **не** виконує `CANCEL` на базі цих рекомендацій; максимум — форсує ORDERS_SNAPSHOT.
5. `_run_bracket_recovery_pass()`:
   - Якщо ще не виконувався:
     - побачить flat‑state + brackets через `evaluate_all` і викличе `_apply_bracket_plan` з CANCEL.
     - після цього `_recovery_completed=True` → більше не запускається.
   - Якщо вже виконувався раніше (найтиповіший випадок в довгоживучому процесі):
     - full close більше **не** тригерить orphan‑cleanup через цей механізм.

**Висновок (S4‑GAP):**

- Після full close cleanup SL/TP **не гарантовано** робиться ExecPosRuntimeV2:
  - надія — на зовнішній OrderGuardian / історичні механізми,
  - або на одноразовий DR‑pass `_run_bracket_recovery_pass` (який може вже бути «вичерпаний»).
- Інваріант «через N подій всі SL/TP зникли при `position_qty == 0`» наразі **не забезпечений** самим runtime+BracketService.

---

## 4. Узагальнення виявлених дірок

- **Partial close (S1):**
  - Немає перевірки `sum(bracket_qty) ≤ abs(position_qty)` → SL/TP можуть залишатися «завеликими».
  - `recalc_on_partial_close` в `BracketRulesConfig` існує, але **ніяким чином не використовується** в `evaluate()`.
- **Scale‑in (S2):**
  - Загалом працює через `stale_levels` (перерахунок ціни) і використання `position_view.qty` для нових ордерів.
  - Потенційно fragile, якщо конфіг / ринок дає однакові рівні до/після scale‑in.
- **Reverse (S3):**
  - Нові SL/TP для SHORT ставляться, але cleanup старих LONG brackets покладається на інші механізми (recovery, зовнішній guardian).
  - Немає зв’язки по `position_id`/версії; binding чисто по `(symbol, side)` + clientOrderId хешу.
- **Full close (S4):**
  - Немає регулярного виклику `BracketService.evaluate` для flat‑state (крім DR‑pass).
  - Watchdog detect‑only; cleanup орфанів де‑факто поза runtime.

---

## 5. Пропоновані інваріанти R1‑B‑INV‑*

> Ці інваріанти **ще не виконуються** в коді; вони задають ціль для майбутньої фази OCO‑STABILIZE‑R2.

- **R1‑B‑INV‑1 (Size bound per side):**  
  Для будь‑якого `POSITION_SYNC` або internal snapshot, якщо `abs(position_qty(symbol, side)) > 0`, то:
  - `0 < sum(SL.qty for reduceOnly exit orders matching (symbol, side)) ≤ abs(position_qty)`,
  - `0 ≤ sum(TP.qty for same) ≤ abs(position_qty)`.

- **R1‑B‑INV‑2 (Zero position ⇒ no active brackets):**  
  Якщо `abs(position_qty(symbol, side)) == 0`, то протягом не більше ніж `N` подій (`ORDERS_SNAPSHOT` / `POSITION_SYNC` / guard‑iterations):
  - всі SL/TP, що відносяться до цієї пари `(symbol, side, position_id)`, мають:
    - статус `CANCELED` / `FILLED` / `EXPIRED` **або**
    - бути відсутні в локальному mirror `_open_orders_by_symbol`.

- **R1‑B‑INV‑3 (No overshoot on partial close):**  
  При будь‑якому partial close (TRADE_EXECUTED або POSITION_SYNC, де `|qty_after| < |qty_before|` і знак не змінюється):
  - після виконання `BracketService.evaluate` + застосування плану:
    - `sum(SL.qty)` і `sum(TP.qty)` **не можуть бути більшими**, ніж `abs(position_qty_after)`,
    - **не допускаються** «висячі» частини SL/TP, які не можуть виконатись без створення негативного залишку.

- **R1‑B‑INV‑4 (Reverse separation):**  
  При реверсі (side змінюється з LONG на SHORT або навпаки):
  - bracket‑ордери старої сторони `(symbol, previous_side)` мають бути:
    - або повністю скасовані в рамках одного узгодженого плану (`CANCEL` + `PLACE_*`),
    - або чітко позначені як орфани, які cleanup‑яться до того, як нова позиція отримає свої SL/TP.
  - Заборонено використання старих SL/TP як захисту нової позиції без явної пере‑прив’язки (`position_id`/версія).

- **R1‑B‑INV‑5 (Deterministic recalc flags):**  
  Прапори `recalc_on_partial_close` / `recalc_on_scale_in` в `BracketRulesConfig` мають:
  - явно впливати на те, чи генерується план з `CANCEL`/`PLACE_*` при виявленні часткового закриття / добору,
  - бути задокументовані в BracketService contract (які сценарії включають/виключають перерахунок).

---

## 6. Summary для R1‑B

- Поточна реалізація Aggregated OCO в V2:
  - має коректну арифметику позиції (`apply_fill`) для partial close / scale‑in / flip,
  - використовує `position_qty` для **нових** SL/TP, але не перевіряє / не обрізає **існуючі** обсяги при partial close,
  - добре покриває scale‑in через `stale_levels`, але мало робить для partial close і reverse з точки зору size‑sync,
  - покладається на DR‑recovery / зовнішній Guardian / історичний watchdog для orphan cleanup при full close.

Ці висновки будуть використані в R1‑C (race‑condition аналіз) та R1‑D (проект тестового пакету), без змін у продукційному коді на цьому етапі.

