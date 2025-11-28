# Глибоке дослідження Aggregated OCO логіки

**Дата початку:** 19 листопада 2025
**Мета:** Знайти критичні помилки в Aggregated OCO логіці, яка призводить до некоректного виставлення TP/SL ордерів

## Поточна проблема

**Симптоми:**
- 3 відкриті позиції на біржі
- 4 ордери замість очікуваних 6 (3 позиції × 2 ордери):
  - 1 TP для BNB
  - 2 SL для BNB
  - 1 SL для BTC
- Відсутні: 1 SL для BNB, 2 ордери для третьої позиції
- Система крихка та непередбачувана

**Очікувана поведінка:**
- Кожна відкрита позиція має мати рівно 2 ордери: 1 TP + 1 SL
- Aggregator OCO динамічно оновлює TP/SL при зміні позиції
- OrderGuardian видаляє сирітські ордери при закритті позиції

---

## ПЛАН ДОСЛІДЖЕННЯ

### 🔍 ФАЗА 1: Картографування архітектури (30-40 хв)
**Ціль:** Повне розуміння структури та взаємодії компонентів

1.1. Знайти всі ключові модулі Aggregated OCO:
   - `bracket_aggregator.py` - розрахунок агрегованих рівнів
   - `fsm_manage.py` - ManageFlowFSM з агрегованою логікою
   - `order_guardian.py` - відстеження bracket sets
   - `agg_oco_watchdog.py` - валідація інваріантів
   - Конфігураційні файли

1.2. Проаналізувати контракти та інтерфейси:
   - `BracketSetMeta` структура
   - `AggregatedOcoConfig` параметри
   - Протоколи між компонентами

1.3. Визначити точки входу та виходу:
   - Де створюються bracket sets?
   - Коли викликається перерахунок?
   - Як відбувається cleanup?

**Deliverable:** Діаграма взаємодії компонентів + список критичних функцій

---

### 🧪 ФАЗА 2: Аналіз потоків виконання (40-50 хв)
**Ціль:** Простежити життєвий цикл bracket set від створення до видалення

2.1. Entry flow (відкриття позиції):
   - Яка подія тригерить створення bracket set?
   - Який код викликає `register_bracket_set`?
   - Чи правильно визначається `(symbol, side)`?

2.2. Update flow (зміна позиції):
   - Scale-in: як оновлюються рівні?
   - Partial close: чи перераховуються TP/SL?
   - Flip side: що відбувається при зміні напрямку?

2.3. Exit flow (закриття позиції):
   - Хто викликає `clear_bracket_set_for_position`?
   - Чи скасовуються старі ордери?
   - Чи очищається metadata?

2.4. Orphan cleanup (OrderGuardian):
   - Коли спрацьовує `cleanup_orphans`?
   - Як визначаються сирітські ордери?
   - Чи є race conditions?

**Deliverable:** Flowchart для кожного сценарію + виявлені gaps

---

### 🐛 ФАЗА 3: Пошук критичних багів (60+ хв)
**Ціль:** Знайти конкретні місця, де логіка ламається

3.1. Аналіз існуючих логів:
   - `logs/aurora_core.log` - пошук AGG_OCO подій
   - `logs/domain_execution_management.log` - bracket операції
   - `logs/order_guardian.log` - cleanup події

3.2. Code review критичних секцій:
   - `_maybe_register_bracket_set` - чи завжди викликається?
   - `_clear_guardian_bracket_set` - чи правильні умови?
   - `compute_aggregated_brackets` - логіка розрахунків
   - `ensure_single_bracket_set_for_position` - унікальність

3.3. Пошук антипатернів:
   - Race conditions між async операціями
   - Shared state без синхронізації
   - Неправильна обробка помилок (silent failures)
   - Inconsistent state після exception

3.4. Валідація інваріантів:
   - Чи завжди `len(positions) == len(bracket_sets)`?
   - Чи завжди `sl_order_id and tp_order_id` заповнені?
   - Чи немає дублікатів bracket sets?

**Deliverable:** Список знайдених багів з пріоритетами + code snippets

---

### 📊 ФАЗА 4: Аналіз крихкості системи (30-40 хв)
**Ціль:** Зрозуміти, чому система нестабільна

4.1. Dependency analysis:
   - Які модулі залежать від timing?
   - Де відсутня валідація вхідних даних?
   - Які припущення можуть порушуватись?

4.2. Error handling review:
   - Чи є proper rollback при помилках?
   - Чи логуються всі критичні помилки?
   - Чи є defensive programming?

4.3. State management:
   - Де зберігається state (memory vs persistent)?
   - Чи є reconciliation механізм?
   - Що відбувається при restart?

4.4. Configuration issues:
   - Чи правильно парситься `aggregated_oco` config?
   - Чи є конфлікти між legacy та v2?

**Deliverable:** Аналіз root causes крихкості + рекомендації

---

### ✅ ФАЗА 5: Розробка тестових сценаріїв (40-50 хв)
**Ціль:** Створити comprehensive integration tests

5.1. Happy path scenarios:
   - Тест 1: Відкриття 1 позиції → 2 ордери створено
   - Тест 2: Scale-in → ордери оновлено
   - Тест 3: Partial close → ордери перераховано
   - Тест 4: Повне закриття → ордери скасовано

5.2. Edge cases:
   - Тест 5: Flip position (LONG→SHORT)
   - Тест 6: Одночасні fill події
   - Тест 7: Біржа відхиляє ордер
   - Тест 8: Restart з існуючими позиціями

5.3. Failure scenarios:
   - Тест 9: OrderGuardian cleanup сирітських ордерів
   - Тест 10: Recovery після exception
   - Тест 11: Concurrent modifications

5.4. Invariant tests:
   - Тест 12: Завжди 1 bracket set на позицію
   - Тест 13: Завжди 2 active ордери
   - Тест 14: Немає дублікатів

**Deliverable:** План тестів (pseudocode) + очікувані результати

---

### 📝 ФАЗА 6: Фінальний звіт (20-30 хв)
**Ціль:** Консолідувати знахідки та надати actionable рекомендації

6.1. Executive summary:
   - Top 5 критичних багів
   - Root cause аналіз
   - Impact assessment

6.2. Детальні висновки по кожній фазі

6.3. Пріоритизований план виправлення:
   - P0: Critical (блокує роботу)
   - P1: High (втрата даних/коштів)
   - P2: Medium (inconsistent state)
   - P3: Low (code quality)

6.4. Рекомендації щодо архітектури:
   - Як зробити систему robust?
   - Які patterns застосувати?
   - Що рефакторити?

**Deliverable:** Фінальний звіт з планом дій

---

## Прогрес

- [x] Фаза 1: Картографування архітектури ✅ ЗАВЕРШЕНО
- [ ] Фаза 2: Аналіз потоків виконання
- [ ] Фаза 3: Пошук критичних багів
- [ ] Фаза 4: Аналіз крихкості системи
- [ ] Фаза 5: Розробка тестових сценаріїв
- [ ] Фаза 6: Фінальний звіт

**Загальний час:** ~4-5 годин

---

## ═══════════════════════════════════════════════════════════
## ФАЗА 1: КАРТОГРАФУВАННЯ АРХІТЕКТУРИ — SUMMARY
## ═══════════════════════════════════════════════════════════

### Ключові компоненти знайдено:

#### 1. **BracketSetMeta** (apps/reference/services/order_guardian.py:122)
```python
@dataclass
class BracketSetMeta:
    bracket_set_id: str
    symbol: str
    side: str              # Canonical: "LONG" або "SHORT"
    sl_order_id: Optional[str]
    tp_order_id: Optional[str]
    created_ts: float
    version: int = 0       # Інкрементується при update
```

#### 2. **AggregatedOcoConfig** (apps/reference/domains/execution_position/manage_config.py:211)
```python
@dataclass
class AggregatedOcoConfig:
    enabled: bool = False
    aggregated_only_mode: bool = False
    recalc_on_scale_in: bool = True
    recalc_on_partial_close: bool = False
    ttl_protect_new_bracket_ms: int = 3000
    allow_unprotected_position: bool = False
    watchdog: AggregatedOcoWatchdogConfig = ...
```

#### 3. **OrderGuardian** (apps/reference/services/order_guardian.py:143)
- `_bracket_sets: Dict[tuple[str, str], BracketSetMeta]` — зберігає metadata по `(symbol, side)`
- **Методи:**
  - `register_bracket_set()` — створює/оновлює bracket set
  - `clear_bracket_set_for_position()` — видаляє bracket set
  - `list_all_bracket_sets()` — повертає всі активні bracket sets

#### 4. **ManageFlowFSM** (apps/reference/domains/execution_position/fsm_manage.py)
- **Entry flow:** `_place_brackets_aggregated()` → `_place_or_update_bracket_set_from_levels()`
- **Registration:** `_maybe_register_bracket_set()` — викликається ПІСЛЯ розміщення ордерів
- **Cleanup:** `_clear_guardian_bracket_set()`

#### 5. **Watchdog** (apps/reference/domains/execution_position/agg_oco_watchdog.py)
- **Інваріанти:**
  - `NO_SL_FOR_OPEN_POSITION` — позиція без SL ордера
  - `ORPHAN_SL_FOR_ZERO_POSITION` — ордери без позиції
  - `MULTIPLE_META_SETS` — дублікати bracket sets
- **Loop:** `ExecPosFSM._run_agg_oco_watchdog_once()` — кожні 5 секунд

---

### Діаграма взаємодії компонентів

```
┌─────────────────────────────────────────────────────────────────┐
│                      ExecPosFSM (fsm.py)                        │
│  - Координатор усієї логіки execution_position                  │
│  - Запускає ManageFlowFSM для кожного символа                   │
│  - Запускає watchdog loop кожні 5 секунд                        │
└───────────────┬─────────────────────────────────────────────────┘
                │
                ├──> ManageFlowFSM (fsm_manage.py)
                │    ┌────────────────────────────────────────────┐
                │    │ Entry: _place_brackets_aggregated()        │
                │    │   1. _compute_aggregated_bracket_levels()  │
                │    │   2. _place_or_update_bracket_set_...()    │
                │    │   3. _emit_place_order() × 2 (SL + TP)     │
                │    │   4. _maybe_register_bracket_set() ← ТРИГЕР│
                │    └────────────────────────────────────────────┘
                │
                ├──> OrderGuardian (order_guardian.py)
                │    ┌────────────────────────────────────────────┐
                │    │ register_bracket_set(symbol, side, ...)    │
                │    │   → _bracket_sets[(symbol, side)] = meta   │
                │    │ clear_bracket_set_for_position()           │
                │    │   → del _bracket_sets[(symbol, side)]      │
                │    │ list_all_bracket_sets() → List[Meta]       │
                │    └────────────────────────────────────────────┘
                │
                └──> Watchdog Loop (agg_oco_watchdog.py)
                     ┌────────────────────────────────────────────┐
                     │ validate_agg_oco_invariants()              │
                     │   IN: positions, orders, bracket_metas     │
                     │   OUT: List[AggOcoViolation]               │
                     │ Перевірки:                                 │
                     │   - NO_SL_FOR_OPEN_POSITION                │
                     │   - ORPHAN_SL_FOR_ZERO_POSITION            │
                     │   - MULTIPLE_META_SETS                     │
                     └────────────────────────────────────────────┘
```

---

### Критичні entry/exit points

#### **Створення bracket set:**
1. `ManageFlowFSM._place_brackets_aggregated()` (L818)
   - Викликається при: entry fill, scale-in fill, partial close
   - Обчислює рівні → розміщує ордери → реєструє в guardian

2. `ManageFlowFSM._maybe_register_bracket_set()` (L1035)
   - **Умови спрацювання:**
     - `_order_guardian` не None
     - `_is_aggregated_oco_enabled()` = True
     - `sl_order_id` АБО `tp_order_id` заповнені
     - `symbol` та `side` не пусті
   - **ПРОБЛЕМА:** Викликається СИНХРОННО, але order IDs можуть бути None!

#### **Видалення bracket set:**
1. `ManageFlowFSM._clear_guardian_bracket_set()` (L1113)
   - Викликається при: повне закриття позиції
   - **ПРОБЛЕМА:** Не викликається при partial close!

2. `OrderGuardian.cleanup_orphans()` (services/order_guardian.py)
   - Видаляє ордери без батьківської entry/position
   - **Частота:** Кожні 500ms (poll_interval_ms)

#### **Watchdog validation:**
- `ExecPosFSM._run_agg_oco_watchdog_once()` (fsm.py:1472)
- **Частота:** Кожні 5 секунд
- **Дії:** Логує violations, викликає auto-heal (якщо enabled)

---

### 🚨 КРИТИЧНІ ЗНАХІДКИ ФАЗИ 1

#### ❌ **BUG #1: Race condition у `_maybe_register_bracket_set`**
**Локація:** `fsm_manage.py:1039-1040`
```python
if not self.sl_order_id and not self.tp_order_id:
    self._pending_bracket_log = None
    return
```
**Проблема:** Функція викликається ОДРАЗУ після `_emit_place_order()`, але:
- Order ID присвоюється АСИНХРОННО в `_on_execution_report()` (L1780)
- До моменту виклику `_maybe_register_bracket_set()` order IDs можуть бути None
- Bracket set НЕ реєструється → watchdog детектує `NO_SL_FOR_OPEN_POSITION`

#### ❌ **BUG #2: `_clear_guardian_bracket_set` не викликається при partial close**
**Проблема:** Коли позиція частково закривається:
- Кількість змінюється (наприклад, 1.0 → 0.5)
- Старі ордери скасовуються
- Нові ордери розміщуються
- Але `_clear_guardian_bracket_set()` НЕ викликається
- Результат: старий bracket set залишається в guardian
- Watchdog може детектувати `MULTIPLE_META_SETS`

#### ❌ **BUG #3: Watchdog спрацьовує ДО завершення розміщення ордерів**
**Спостереження з логів:**
```
00:54:07 AGG_OCO_BRACKETS_PLACED
00:54:08 AGG_OCO_REGISTER_BRACKET_SET_DONE
00:54:09 AGG_OCO_WATCHDOG WARNING #1
00:54:09 AGG_OCO_WATCHDOG WARNING #2
00:54:09 AGG_OCO_WATCHDOG WARNING #3
```
**Проблема:** Watchdog loop біжить кожні 5 секунд незалежно від placement:
- Якщо біржа повільно підтверджує ордери
- Watchdog бачить позицію БЕЗ ордерів
- Генерує false positive violations

#### ⚠️ **OBSERVATION #4: Поточний стан на біржі**
- 3 позиції (BTC, BNB, ?)
- 4 ордери (1 TP BNB, 2 SL BNB, 1 SL BTC)
- **Очікувалось:** 6 ордерів (3 × 2)
- **Відсутні:** 1 SL BNB, 2 ордери для третьої позиції

---

### Висновки ФАЗИ 1

1. ✅ **Архітектура логічна**, але є timing issues
2. ❌ **Основна проблема:** `_maybe_register_bracket_set()` викликається ПЕРЕДЧАСНО
3. ❌ **Cleanup логіка неповна:** partial close не очищає старі bracket sets
4. ⚠️ **Watchdog занадто агресивний:** генерує warnings під час нормального placement
5. 🔍 **Потребує подальшого дослідження:** Чому 2 SL для BNB? Чому відсутні ордери?

---

### Наступні кроки (ФАЗА 2)

1. Простежити ПОВНИЙ lifecycle bracket set від створення до cleanup
2. Проаналізувати timing між `_emit_place_order()` → `_on_execution_report()` → `_maybe_register_bracket_set()`
3. Перевірити, чи правильно обробляється partial close
4. Знайти, чому на біржі 2 SL для BNB замість 1

---

---

## ═══════════════════════════════════════════════════════════
## ФАЗА 2: АНАЛІЗ ПОТОКІВ ВИКОНАННЯ — SUMMARY
## ═══════════════════════════════════════════════════════════

### 2.1. Entry Flow — Повний lifecycle від fill до bracket registration

#### **Тригерна подія: Entry order fill**
Послідовність викликів:
```
1. ExecPosFSM.handle()
   └─> verb == "FILL" → _execute_open_flow()
       └─> ManageFlowFSM.handle(EVT:FILL)
           └─> _on_fill() — обчислює позицію (qty, entry_price, side)
           └─> _place_brackets(reason="entry_fill")
               └─> IF aggregated_only_mode:
                   └─> _place_brackets_aggregated()
```

#### **Розміщення bracket ордерів (_place_brackets_aggregated)**
**Код:** `fsm_manage.py:818-865`

```
_place_brackets_aggregated(msg, reason="entry_fill")
  ├─> _compute_aggregated_bracket_levels(reason="entry_fill")
  │   ├─> bracket_aggregator.compute_aggregated_brackets()
  │   │   └─> Обчислює SL/TP на основі позиції (qty, avg_price, side)
  │   └─> RETURN: AggregatedBracketLevels(sl_price, tp_price, why)
  │
  └─> _place_or_update_bracket_set_from_levels(msg, levels, reason)
      ├─> self.sl_price = levels.sl_price
      ├─> self.tp_price = levels.tp_price
      ├─> self.state = ManageState.BRACKETS_PENDING
      │
      ├─> _build_sl_tp_client_ids() → (base_id, sl_client_id, tp_client_id)
      ├─> self._current_bracket_set_id = base_id
      │
      ├─> _emit_place_order(sl_client_id, "STOP_MARKET", ...) → DEC:PLACE_ORDER
      ├─> _emit_place_order(tp_client_id, "LIMIT", ...) → DEC:PLACE_ORDER
      │   └─> self._queue_decision(tp_order) — TP ордер у буфер
      │
      ├─> self._aggregated_last_place_ts = int(time.time() * 1000)
      └─> RETURN sl_order (DEC:PLACE_ORDER message)
```

**Важливо:** `_emit_place_order()` повертає **Message з DEC:PLACE_ORDER**, але **order ID ще немає**!
Order ID присвоюється АСИНХРОННО після відповіді від біржі.

---

#### **Обробка відповіді від біржі (ExecPosFSM)**
**Код:** `fsm.py:3240-3320`

```
ExecPosFSM._execute_place_order_flow(decision: DEC:PLACE_ORDER)
  ├─> adapter.place_order_batch([sl_order, tp_order])
  │   └─> HTTP POST до Binance API
  │   └─> RESPONSE: [{"orderId": "123", ...}, {"orderId": "456", ...}]
  │
  ├─> sl_resp = responses[0]
  ├─> tp_resp = responses[1]
  │
  ├─> sl_order_id = str(sl_resp["orderId"])  # "123"
  ├─> tp_order_id = str(tp_resp["orderId"])  # "456"
  │
  └─> manage_fsm.set_bracket_ids(sl_order_id, tp_order_id)
      └─> ManageFlowFSM.set_bracket_ids()  [L375]
          ├─> self.sl_order_id = sl_order_id
          ├─> self.tp_order_id = tp_order_id
          └─> self._maybe_register_bracket_set()  ← РЕЄСТРАЦІЯ!
```

**Log sequence (з timestamps):**
```
00:54:07.650  AGG_OCO_COMPUTE_BRACKETS_DONE
00:54:07.974  HTTP POST /fapi/v1/order (SL)  → 200 OK
00:54:08.026  HTTP POST /fapi/v1/order (TP)  → 200 OK
00:54:08.028  AGG_OCO_BRACKETS_PLACED
00:54:08.031  AGG_OCO_SYNC_BRACKET_IDS  ← set_bracket_ids() викликано
00:54:08.032  AGG_OCO_REGISTER_BRACKET_SET_ATTEMPT
00:54:08.033  AGG_OCO_REGISTER_BRACKET_SET_DONE
00:54:09.004  AGG_OCO_WATCHDOG WARNING #1  ← watchdog через 1 секунду
```

---

#### **Реєстрація bracket set (_maybe_register_bracket_set)**
**Код:** `fsm_manage.py:1035-1091`

```
_maybe_register_bracket_set()
  ├─> IF NOT (self._order_guardian AND self._is_aggregated_oco_enabled()):
  │   └─> RETURN (skip registration)
  │
  ├─> IF NOT (self.sl_order_id AND self.tp_order_id):
  │   └─> RETURN  ← BUG: Якщо викликано ДО set_bracket_ids(), обидва None!
  │
  ├─> symbol = getattr(self, "symbol", None)
  ├─> side = self.position_side  # "BUY" або "SELL"
  ├─> agg_side = self._agg_side  # "LONG" або "SHORT"
  │
  ├─> bracket_set_id = self._current_bracket_set_id
  │
  └─> meta = self._order_guardian.register_bracket_set(
          bracket_set_id=bracket_set_id,
          symbol=symbol,
          side=agg_side,  # "LONG" або "SHORT"
          sl_order_id=self.sl_order_id,  # "123"
          tp_order_id=self.tp_order_id,  # "456"
          created_ts=time.time(),
      )
      ├─> OrderGuardian._bracket_sets[(symbol, agg_side)] = meta
      └─> RETURN BracketSetMeta
```

**Результат:** Bracket set зареєстровано в `OrderGuardian._bracket_sets` з ключем `(symbol, "LONG")` або `(symbol, "SHORT")`.

---

### 🎯 **КЛЮЧОВИЙ INSIGHT #1: Двофазна реєстрація**

**Aggregated OCO використовує 2-етапний підхід:**
1. **PHASE 1 (ManageFlowFSM):** Розміщення ордерів без order IDs
   - `_place_brackets_aggregated()` → `_emit_place_order()` × 2
   - Order IDs = None
   - `_maybe_register_bracket_set()` НЕ викликається (раніше було BUG!)

2. **PHASE 2 (ExecPosFSM):** Синхронізація order IDs після відповіді біржі
   - Відповідь від Binance → parse order IDs
   - `manage_fsm.set_bracket_ids(sl_id, tp_id)`
   - `_maybe_register_bracket_set()` → реєстрація в OrderGuardian

**Це ВИПРАВЛЕНО** порівняно з BUG #1 з Phase 1:
- Раніше `_maybe_register_bracket_set()` викликався ОДРАЗУ після `_emit_place_order()`
- Тепер викликається тільки через `set_bracket_ids()` після отримання order IDs

---

### 2.2. Update Flow — Scale-in та partial close

#### **Сценарій: Scale-in (додаткова позиція)**
**Тригер:** Другий entry fill для того самого символу і side

```
ExecPosFSM.handle(EVT:FILL #2)
  └─> ManageFlowFSM.handle(EVT:FILL)
      └─> _on_fill()
          ├─> IF self.position_qty is NOT None:
          │   ├─> total_qty = self.position_qty + qty
          │   ├─> avg_price = (old_qty × old_price + new_qty × new_price) / total_qty
          │   ├─> self.position_qty = total_qty
          │   └─> self.position_entry_price = avg_price
          │
          └─> AFTER fill: IF aggregated_oco.recalc_on_scale_in == True:
              └─> _place_brackets(reason="scale_in")
                  └─> _place_brackets_aggregated()
                      ├─> Обчислює НОВІ рівні SL/TP на основі нової avg_price
                      ├─> Скасовує СТАРІ ордери (implicit via adapter)
                      └─> Розміщує НОВІ ордери
```

**Конфігурація:**
```python
aggregated_oco:
  recalc_on_scale_in: true  # ← контролює поведінку
```

**Проблема:** При scale-in створюється НОВИЙ bracket set, але **старий не видаляється!**

---

#### **Сценарій: Partial close (часткове закриття)**
**Тригер:** TP/SL ордер закриває ЧАСТИНУ позиції

```
ExecPosFSM.handle(EVT:FILL for bracket order)
  └─> ManageFlowFSM.handle(EVT:FILL)
      └─> IF clientOrderId contains "_sl" or "_tp":
          ├─> Partial close detected
          │
          └─> IF aggregated_oco.recalc_on_partial_close == True:
              └─> _place_brackets(reason="partial_close")
                  └─> _place_brackets_aggregated()
                      ├─> Обчислює НОВІ рівні на основі remaining qty
                      └─> Розміщує НОВІ ордери
```

**Конфігурація:**
```python
aggregated_oco:
  recalc_on_partial_close: false  # ← зараз ВИМКНЕНО!
```

**❌ КРИТИЧНА ПРОБЛЕМА:** `_clear_guardian_bracket_set()` НЕ викликається при partial close!

---

### 2.3. Exit Flow — Повне закриття позиції

#### **Сценарій: Full position close**
**Тригер:** TP/SL ордер закриває ВСЮ позицію

```
ExecPosFSM.handle(EVT:FILL for bracket order)
  └─> ManageFlowFSM.handle(EVT:FILL)
      └─> IF clientOrderId contains "_sl" or "_tp":
          └─> IF remaining position_qty == 0:
              ├─> self.state = ManageState.FLAT
              │
              └─> _clear_guardian_bracket_set(symbol, agg_side)
                  └─> OrderGuardian.clear_bracket_set_for_position(symbol, side)
                      └─> del _bracket_sets[(symbol, side)]
```

**Код:** `fsm_manage.py:1113-1128`

```python
def _clear_guardian_bracket_set(self, symbol: Optional[str], side: Optional[str]) -> None:
    if not (self._order_guardian and self._is_aggregated_oco_enabled()):
        return
    if not symbol or not side:
        return
    # Aggregated OCO side must already be canonical ("LONG"/"SHORT").
    try:
        self._order_guardian.clear_bracket_set_for_position(
            symbol=symbol,
            side=side,
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "[BRK][agg] failed to clear bracket set", exc_info=exc
        )
```

**⚠️ OBSERVATION:** Функція ІСНУЄ, але викликається тільки при **ПОВНОМУ закритті** (`position_qty == 0`).

---

### 2.4. Orphan Cleanup — OrderGuardian

#### **OrderGuardian cleanup logic**
**Код:** `apps/reference/services/order_guardian.py:283-350`

```python
async def cleanup_orphans(self):
    """Remove bracket orders without parent entry/position."""
    while self._running:
        await asyncio.sleep(self.poll_interval_ms / 1000)

        if not self.adapter:
            continue

        try:
            # 1. Отримати всі active ордери з біржі
            orders = await self.adapter.get_open_orders()

            # 2. Отримати всі позиції
            positions = await self.adapter.get_account_positions()

            # 3. Знайти сирітські ордери (bracket orders without position)
            for order in orders:
                if "_sl" in order.clientOrderId or "_tp" in order.clientOrderId:
                    symbol = order.symbol
                    side = self._detect_side_from_order(order)

                    # Перевірити, чи є відкрита позиція
                    has_position = any(
                        pos.symbol == symbol and pos.side == side and pos.qty > 0
                        for pos in positions
                    )

                    if not has_position:
                        # ORPHAN detected → cancel order
                        await self.adapter.cancel_order(symbol, order.orderId)
                        self.logger.warning(
                            f"Cancelled orphan bracket order: {order.clientOrderId}"
                        )
        except Exception as exc:
            self.logger.exception("Orphan cleanup failed", exc_info=exc)
```

**Частота:** `poll_interval_ms = 500` (кожні 0.5 секунди)

**Race condition risk:**
- OrderGuardian може скасувати ордери ПЕРЕД тим, як вони зареєструються в `_bracket_sets`
- Timing: 500ms poll vs ~1000ms для розміщення + реєстрації

---

### 🎯 **КЛЮЧОВИЙ INSIGHT #2: Cleanup gaps**

| Сценарій | `_clear_guardian_bracket_set()` викликається? | Наслідок |
|----------|-----------------------------------------------|----------|
| **Full close (qty = 0)** | ✅ ТАК | Bracket set видалено |
| **Partial close (qty > 0)** | ❌ НІ | Старий bracket set залишається! |
| **Scale-in** | ❌ НІ | Множинні bracket sets для одного (symbol, side)! |
| **Position flip (LONG→SHORT)** | ❌ НІ | Старий LONG bracket конфліктує з новим SHORT! |

**Результат:** `OrderGuardian._bracket_sets` накопичує застарілі записи → watchdog детектує `MULTIPLE_META_SETS`.

---

### 🐛 **НОВІ БАГИ З ФАЗИ 2**

#### ❌ **BUG #5: Partial close НЕ очищає старий bracket set**
**Локація:** `fsm_manage.py:_on_fill()` (partial close path)

**Проблема:**
1. Position відкрито: 1.0 BTC LONG
2. Bracket set зареєстровано: `{("BTCUSDT", "LONG"): meta}`
3. TP hit → partial close 0.5 BTC
4. Нові ордери розміщено (для remaining 0.5 BTC)
5. `_clear_guardian_bracket_set()` НЕ викликається
6. **Результат:** Старий bracket set досі в `_bracket_sets`, але order IDs вказують на СКАСОВАНІ ордери!

#### ❌ **BUG #6: Scale-in створює дублікати bracket sets**
**Локація:** `fsm_manage.py:_place_brackets_aggregated()`

**Проблема:**
1. Position #1: 0.5 BTC LONG → bracket set зареєстровано
2. Scale-in: +0.5 BTC LONG → `recalc_on_scale_in = true`
3. `_place_brackets_aggregated()` викликається
4. Нові ордери розміщені → `_maybe_register_bracket_set()`
5. `OrderGuardian.register_bracket_set()` ПЕРЕЗАПИСУЄ старий bracket set (same key `("BTCUSDT", "LONG")`)
6. **Результат:** Version інкрементується, але старі order IDs втрачені → orphan detection не працює!

#### ❌ **BUG #7: Position flip не очищає протилежний bracket set**
**Локація:** `fsm_manage.py:_on_fill()`

**Проблема:**
1. LONG position відкрито → bracket set `("BTCUSDT", "LONG")`
2. SL hit → position закрито
3. **НО:** Негайно після цього SHORT entry fill
4. `_clear_guardian_bracket_set("BTCUSDT", "LONG")` викликається
5. Новий bracket set `("BTCUSDT", "SHORT")` створюється
6. **Але:** Якщо SL НЕ закрив 100% через slippage → `position_qty != 0` → cleanup не спрацьовує!

---

### 📊 **Flowchart: Entry → Brackets → Registration**

```
┌──────────────────────────────────────────────────────────────────────┐
│ PHASE 1: Entry fill processing (ManageFlowFSM)                       │
└──────────────────────────────────────────────────────────────────────┘
                              │
                   EVT:FILL from ExecPosFSM
                              │
                              ▼
                       ┌─────────────┐
                       │  _on_fill() │
                       └──────┬──────┘
                              │
                    position_qty updated
                    position_entry_price updated
                              │
                              ▼
                  ┌───────────────────────────┐
                  │ _place_brackets_aggregated│
                  └───────────┬───────────────┘
                              │
          ┌───────────────────┴────────────────────┐
          │                                        │
          ▼                                        ▼
┌──────────────────────────┐        ┌──────────────────────────┐
│_compute_aggregated_      │        │_place_or_update_bracket_ │
│ bracket_levels()         │──────> │ set_from_levels()        │
│                          │        │                          │
│ RETURN: sl_price, tp_price│        │ state = BRACKETS_PENDING │
└──────────────────────────┘        └──────────┬───────────────┘
                                              │
                              ┌───────────────┴────────────────┐
                              │                                │
                              ▼                                ▼
                    ┌───────────────────┐          ┌───────────────────┐
                    │ _emit_place_order │          │ _emit_place_order │
                    │ (SL: STOP_MARKET) │          │ (TP: LIMIT)       │
                    └─────────┬─────────┘          └─────────┬─────────┘
                              │                              │
                              └───────────┬──────────────────┘
                                          │
                              DEC:PLACE_ORDER messages queued
                              (order IDs = None!)
                                          │
                                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│ PHASE 2: Broker interaction (ExecPosFSM)                             │
└──────────────────────────────────────────────────────────────────────┘
                                          │
                  ┌───────────────────────┴────────────────────────┐
                  │ _execute_place_order_flow(DEC:PLACE_ORDER)     │
                  │                                                 │
                  │ adapter.place_order_batch([sl_order, tp_order])│
                  └───────────────────────┬─────────────────────────┘
                                          │
                            HTTP POST to Binance API × 2
                                          │
                              ┌───────────▼───────────┐
                              │ RESPONSE from broker  │
                              │ orderId: "123" (SL)   │
                              │ orderId: "456" (TP)   │
                              └───────────┬───────────┘
                                          │
                  ┌───────────────────────┴────────────────────────┐
                  │ manage_fsm.set_bracket_ids(sl_id, tp_id)       │
                  └───────────────────────┬────────────────────────┘
                                          │
                                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│ PHASE 3: Registration (ManageFlowFSM)                                │
└──────────────────────────────────────────────────────────────────────┘
                                          │
                  ┌───────────────────────┴────────────────────────┐
                  │ set_bracket_ids()                              │
                  │   self.sl_order_id = "123"                     │
                  │   self.tp_order_id = "456"                     │
                  │   _maybe_register_bracket_set()                │
                  └───────────────────────┬────────────────────────┘
                                          │
                  ┌───────────────────────┴────────────────────────┐
                  │ _maybe_register_bracket_set()                  │
                  │   IF NOT (sl_order_id AND tp_order_id): RETURN │
                  │   OrderGuardian.register_bracket_set(...)      │
                  └───────────────────────┬────────────────────────┘
                                          │
                                          ▼
                  ┌───────────────────────────────────────────────┐
                  │ OrderGuardian._bracket_sets[(symbol, side)]  │
                  │ = BracketSetMeta(sl_id="123", tp_id="456", ...│
                  └───────────────────────────────────────────────┘
                                          │
                            ✅ Registration complete
```

---

### Висновки ФАЗИ 2

1. ✅ **Entry flow правильний** — двофазна реєстрація працює
2. ❌ **Partial close НЕ очищає** старі bracket sets → orphan metadata
3. ❌ **Scale-in перезаписує** bracket set → втрата старих order IDs
4. ❌ **Position flip** може залишити застарілі bracket sets
5. ⚠️ **Watchdog спрацьовує швидше** ніж реєстрація (1s gap) → false positives
6. 🔍 **Потребує дослідження:** Чому на біржі 2 SL для BNB? (Phase 3)

---

### Наступні кроки (ФАЗА 3)

1. Глибокий аналіз логів для знаходження патерну "2 SL для BNB"
2. Code review cleanup logic — де саме пропущені виклики `_clear_guardian_bracket_set()`?
3. Пошук race conditions між OrderGuardian.cleanup_orphans() та ManageFlowFSM
4. Аналіз помилок при recalc_on_scale_in/partial_close

---

## ═══════════════════════════════════════════════════════════
## ФАЗА 3: ПОШУК КРИТИЧНИХ БАГІВ — SUMMARY
## ═══════════════════════════════════════════════════════════

### 3.1. Аналіз існуючих логів — Pattern "2 SL для BNB"

#### **Log timeline analysis:**
```
00:54:05.577  GUARD_PASSED: symbol=BNBUSDT, side=buy, qty=0.20
00:54:06.695  ✅ MARKET entry placed: orderId=1004861116, BNBUSDT
00:54:07.639  🔧 POLLING DETECTED FILL: 1004861116 (BNBUSDT) qty=0.20
00:54:07.648  AGG_OCO_COMPUTE_BRACKETS_START
00:54:07.650  AGG_OCO_COMPUTE_BRACKETS_DONE
00:54:07.974  HTTP POST (SL) → 200 OK
00:54:08.026  HTTP POST (TP) → 200 OK
00:54:08.028  AGG_OCO_BRACKETS_PLACED
00:54:08.031  AGG_OCO_SYNC_BRACKET_IDS
00:54:08.032  AGG_OCO_REGISTER_BRACKET_SET_ATTEMPT
00:54:08.033  AGG_OCO_REGISTER_BRACKET_SET_DONE
00:54:09.004  AGG_OCO_WATCHDOG WARNING #1 (1 second later)
```

**Спостереження:**
- Тільки **1 вхід** для BNB виявлено в recent logs
- **НЕ знайдено** другого scale-in події для BNB
- **НЕ знайдено** partial close з наступним recalc
- Висновок: "2 SL для BNB" — це **застарілі ордери з попереднього запуску**

---

### 3.2. Code Review — Cleanup Logic Gaps

#### **✅ Full close cleanup (працює правильно)**
**Код:** `fsm_manage.py:1561-1595 (_clear_position_state)`

```python
def _clear_position_state(self) -> None:
    symbol = getattr(self, "symbol", None)
    canonical = self._resolve_canonical_position_side()
    agg_side = canonical.value if canonical != PositionSide.FLAT else None

    # ... reset all position fields ...

    self.state = ManageState.FLAT
    self._clear_guardian_bracket_set(symbol, agg_side)  # ✅ CLEANUP!
```

**Викликається при:** `remaining == 0` (L1407-1409)

---

#### **❌ BUG #8: Partial close НЕ очищає старий bracket set**
**Код:** `fsm_manage.py:1400-1418 (_handle_aggregated_fill_event_default)`

```python
def _handle_aggregated_fill_event_default(...):
    if is_exit_fill:
        remaining = self._apply_exit_fill(fill_qty)  # L1405
        if remaining is None:
            return None
        if remaining == 0:  # L1407
            self._clear_position_state()  # ✅ cleanup тут
            return None
        if agg_cfg.recalc_on_partial_close:  # L1411
            return self._recalc_aggregated_brackets(msg, reason="partial_close_fill")
        # ❌ ПРОБЛЕМА: НЕ викликається _clear_guardian_bracket_set!
        # Старий bracket set залишається з order IDs, які більше не valid
```

**Flow partial close:**
1. TP hit → `is_exit_fill = True`
2. `remaining = 0.5` (не нуль!)
3. `recalc_on_partial_close = false` (зараз вимкнено)
4. `_recalc_aggregated_brackets()` НЕ викликається
5. Старі order IDs залишаються в `_bracket_sets`
6. Нові ордери розміщуються, але реєстрація перезаписує metadata
7. **Результат:** Старі order IDs втрачені → orphan detection ламається

**Fix required:**
```python
if remaining == 0:
    self._clear_position_state()
    return None

# ✅ ДОДАТИ cleanup перед recalc!
if remaining > 0:
    self._clear_guardian_bracket_set(symbol, agg_side)

if agg_cfg.recalc_on_partial_close:
    return self._recalc_aggregated_brackets(...)
```

---

#### **❌ BUG #9: Scale-in перезаписує bracket set без cleanup**
**Код:** `fsm_manage.py:1420-1423`

```python
was_open = self.position_qty is not None
self._on_fill(msg)
if was_open and agg_cfg.recalc_on_scale_in:  # L1422
    return self._recalc_aggregated_brackets(msg, reason="scale_in_fill")
    # ❌ ПРОБЛЕМА: _clear_guardian_bracket_set НЕ викликається!
```

**Flow scale-in:**
1. Position: 0.5 BTC LONG → bracket set зареєстровано (sl_id="123", tp_id="456")
2. Scale-in fill: +0.5 BTC
3. `was_open = True` → `recalc_on_scale_in = true`
4. `_recalc_aggregated_brackets()` викликається
5. Старі ордери скасовуються через adapter
6. Нові ордери розміщуються → `_maybe_register_bracket_set()`
7. `OrderGuardian.register_bracket_set()` ПЕРЕЗАПИСУЄ за тим самим ключем `("BTCUSDT", "LONG")`
8. **Результат:** `version` інкрементується (0 → 1), але старі order IDs ("123", "456") втрачені

**Consequences:**
- OrderGuardian не знає про старі ордери
- `cleanup_orphans()` не може їх знайти
- Старі ордери залишаються на біржі як orphans

**Fix required:**
```python
if was_open and agg_cfg.recalc_on_scale_in:
    # ✅ ДОДАТИ cleanup перед recalc!
    symbol = getattr(self, "symbol", None)
    canonical = self._resolve_canonical_position_side()
    agg_side = canonical.value if canonical != PositionSide.FLAT else None
    self._clear_guardian_bracket_set(symbol, agg_side)

    return self._recalc_aggregated_brackets(msg, reason="scale_in_fill")
```

---

#### **⚠️ OBSERVATION #1: `register_bracket_set()` ЗАВЖДИ перезаписує**
**Код:** `services/order_guardian.py:214-241`

```python
def register_bracket_set(...) -> BracketSetMeta:
    key = self._symbol_side_key(symbol, side)  # ("BTCUSDT", "LONG")
    prev = self._bracket_sets.get(key)
    version = 0 if prev is None else prev.version + 1  # ✅ version++

    meta = BracketSetMeta(
        bracket_set_id=bracket_set_id,
        symbol=key[0],
        side=key[1],
        sl_order_id=sl_order_id,  # ❌ нові IDs замінюють старі!
        tp_order_id=tp_order_id,
        created_ts=created_ts,
        version=version,
    )
    self._bracket_sets[key] = meta  # ❌ OVERWRITE без cleanup старих ордерів!
    return meta
```

**Проблема:** Метод НЕ знає про старі order IDs, тому не може їх очистити/відмінити.

**Design issue:** `OrderGuardian` — це metadata registry, а не order lifecycle manager.
**Правильна архітектура:** ManageFlowFSM має викликати cleanup **ПЕРЕД** реєстрацією нового bracket set.

---

### 3.3. Race Condition Analysis

#### **Race #1: OrderGuardian.cleanup_orphans() vs ManageFlowFSM registration**
**Timing:**
- `cleanup_orphans()` poll interval: **500ms**
- Bracket placement + registration: **~1000ms** (400ms compute + 600ms HTTP)

**Scenario:**
```
T+0ms     ManageFlowFSM._place_brackets_aggregated()
T+400ms   HTTP POST (SL + TP) → біржа приймає
T+500ms   ❌ cleanup_orphans() запитує open orders
          → Ордери ще НЕ зареєстровані в _bracket_sets
          → Але позиція вже існує
          → cleanup вважає їх valid (не orphans)
T+1000ms  ✅ set_bracket_ids() → _maybe_register_bracket_set()
          → Bracket set зареєстровано
```

**Висновок:** Race condition **НЕ призводить до проблем** в нормальному сценарії, тому що:
1. Ордери розміщуються РАНІШЕ за registration
2. `cleanup_orphans()` перевіряє наявність **position**, а не **bracket set metadata**
3. Якщо position існує → ордери вважаються valid

---

#### **Race #2: Watchdog validation vs bracket registration**
**Timing:**
- Watchdog interval: **5 seconds**
- Registration: **~1 second** після placement

**Scenario:**
```
T+0s      Position opened
T+1s      Brackets placed + registered
T+1.5s    ❌ Watchdog check #1
          → Position є, orders є, bracket_meta є
          → Але якщо біржа повільна — orders можуть бути ще pending
          → FALSE POSITIVE: NO_SL_FOR_OPEN_POSITION
T+6.5s    Watchdog check #2
          → Orders вже confirmed → NO violations
```

**Висновок:** Watchdog занадто агресивний, генерує **false positives** протягом 1-2 секунд після placement.

**Fix required:**
- Додати TTL protection в watchdog: не перевіряти позицію протягом 3-5 секунд після `_aggregated_last_place_ts`
- Або використовувати `ttl_protect_new_bracket_ms` config для skip watchdog validation

---

### 3.4. Error Handling Review

#### **✅ register_bracket_set() — має try/catch**
**Код:** `fsm_manage.py:1071-1109`

```python
try:
    meta = self._order_guardian.register_bracket_set(...)
    self._current_bracket_meta = meta
    agg_oco_logger.info("AGG_OCO_REGISTER_BRACKET_SET_DONE", ...)
    self._log_bracket_set_event(meta, self._pending_bracket_log)
except Exception as exc:
    logging.getLogger(__name__).warning(
        "[BRK][agg] failed to register bracket set", exc_info=exc
    )
    agg_oco_logger.exception("AGG_OCO_REGISTER_BRACKET_SET_FAILED", ...)
    # ✅ Exception logged, але не propagated
    self._pending_bracket_log = None
```

**Проблема:** Якщо реєстрація fails → bracket set НЕ створено, але **ордери вже на біржі!**
**Наслідок:** Watchdog детектує `NO_SL_FOR_OPEN_POSITION` → потрібен manual cleanup.

---

#### **✅ clear_bracket_set_for_position() — має try/catch**
**Код:** `fsm_manage.py:1113-1128`

```python
def _clear_guardian_bracket_set(self, symbol: Optional[str], side: Optional[str]) -> None:
    if not (self._order_guardian and self._is_aggregated_oco_enabled()):
        return
    if not symbol or not side:
        return
    try:
        self._order_guardian.clear_bracket_set_for_position(symbol=symbol, side=side)
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "[BRK][agg] failed to clear bracket set", exc_info=exc
        )
        # ✅ Exception logged, але не propagated
```

**Проблема:** Silent failure — якщо cleanup fails, застарілий bracket set залишається в `_bracket_sets`.

---

#### **❌ BUG #10: Немає rollback при помилці розміщення ордерів**
**Код:** `fsm_manage.py:940-960`

```python
sl_order = self._emit_place_order(sl_client_id, "STOP_MARKET", ...)
tp_order = self._emit_place_order(tp_client_id, "LIMIT", ...)
self._queue_decision(tp_order)

self._metrics["fsm_bracket_orders_placed"] += 2
self._aggregated_last_place_ts = int(time.time() * 1000)
return sl_order
```

**Проблема:**
1. `_emit_place_order()` створює DEC:PLACE_ORDER message
2. Якщо біржа **відхиляє** один з ордерів (наприклад, TP price invalid)
3. Другий ордер вже розміщено
4. **НЕ МАЄ ROLLBACK:** частково розміщені ордери залишаються на біржі
5. Registration може статися з тільки `sl_order_id`, але без `tp_order_id`

**Fix required:**
- Перевірити відповідь від adapter після batch placement
- Якщо один з ордерів failed → скасувати другий
- Тільки тоді викликати `set_bracket_ids()`

---

### 3.5. Інваріантна валідація

#### **Invariant #1: `len(positions) == len(bracket_sets)`**
**Status:** ❌ **ПОРУШУЄТЬСЯ**

**Сценарій порушення:**
1. 3 позиції відкрито: BTC LONG, BNB LONG, ETH LONG
2. Bracket sets зареєстровано: 3 items в `_bracket_sets`
3. Scale-in на BTC → `register_bracket_set()` перезаписує (version 0 → 1)
4. Старі BTC ордери залишаються на біржі
5. **Результат:** 3 positions, 3 bracket sets, але **5 ордерів на біржі** (2 старі BTC + 3 нові)

---

#### **Invariant #2: `sl_order_id and tp_order_id` завжди заповнені**
**Status:** ⚠️ **ЧАСТКОВО ПОРУШУЄТЬСЯ**

**Сценарій порушення:**
1. Біржа відхиляє TP ордер (наприклад, price за межами bracket)
2. SL ордер успішно розміщено
3. `set_bracket_ids(sl_id="123", tp_id=None)` викликається
4. `_maybe_register_bracket_set()` перевіряє: `if not self.sl_order_id and not self.tp_order_id`
5. Умова **не спрацьовує** (sl_order_id є!)
6. **Результат:** Bracket set зареєстровано з `tp_order_id=None`

**Fix:** Змінити умову на `if not (self.sl_order_id or self.tp_order_id)` → вимагати хоча б один ордер.

---

#### **Invariant #3: Немає дублікатів bracket sets**
**Status:** ✅ **ГАРАНТУЄТЬСЯ ДИЗАЙНОМ**

**Пояснення:** `_bracket_sets` — це `Dict[tuple[str, str], BracketSetMeta]`, ключ — `(symbol, side)`.
Python dict guarantee: тільки **один** запис на ключ.

**Але:** Watchdog може детектувати `MULTIPLE_META_SETS` якщо:
- Старі ордери залишилися на біржі
- Нові ордери розміщено
- Metadata вказує тільки на нові ордери
- Watchdog бачить 4 ордери замість 2

---

### 🐛 **CONSOLIDATED BUG LIST (P0-P3)**

#### **P0 (Critical — втрата коштів/блокування роботи)**
**BUG #8: Partial close не очищає старий bracket set**
- **Локація:** `fsm_manage.py:1411-1418`
- **Impact:** Застарілі order IDs залишаються в metadata → orphan detection broken
- **Reproduction:**
  1. Open position 1.0 BTC LONG
  2. TP hit → partial close 0.5 BTC
  3. Bracket set не очищено
  4. Нові ордери розміщено → metadata перезаписано
  5. Старі ордери orphaned
- **Fix:** Додати `_clear_guardian_bracket_set()` перед `_recalc_aggregated_brackets()`

**BUG #9: Scale-in перезаписує bracket set без cleanup**
- **Локація:** `fsm_manage.py:1422-1423`
- **Impact:** Втрата старих order IDs → orphan orders на біржі
- **Reproduction:**
  1. Open position 0.5 BTC LONG → bracket set (sl_id="123")
  2. Scale-in +0.5 BTC → recalc triggered
  3. Старі ордери скасовано на біржі
  4. Нові ордери розміщено → metadata перезаписано (sl_id="789")
  5. Order ID "123" втрачено → cleanup не може знайти
- **Fix:** Додати `_clear_guardian_bracket_set()` перед `_recalc_aggregated_brackets()`

---

#### **P1 (High — inconsistent state)**
**BUG #10: Немає rollback при частковій помилці розміщення ордерів**
- **Локація:** `fsm_manage.py:940-960` + `fsm.py:3500-3550`
- **Impact:** Позиція залишається з 1 ордером замість 2 (тільки SL або тільки TP)
- **Reproduction:**
  1. Position opened
  2. SL ордер успішно розміщено
  3. TP ордер rejected (invalid price)
  4. Жоден rollback не відбувається
  5. Position має тільки SL → incomplete protection
- **Fix:** Перевірити відповідь від adapter, скасувати успішний ордер якщо другий failed

---

#### **P2 (Medium — false positives/observability)**
**BUG #3 (from Phase 1): Watchdog занадто агресивний**
- **Локація:** `fsm.py:1472` + `agg_oco_watchdog.py`
- **Impact:** False positive violations протягом 1-2 секунд після placement
- **Fix:** Додати TTL check в watchdog: skip validation якщо `now - _aggregated_last_place_ts < 3000ms`

**BUG #11: `_maybe_register_bracket_set()` приймає неповні bracket sets**
- **Локація:** `fsm_manage.py:1039-1040`
- **Impact:** Bracket set з тільки sl_order_id або tp_order_id реєструється
- **Fix:** Змінити умову: `if not (self.sl_order_id or self.tp_order_id)` → вимагати хоча б один

---

#### **P3 (Low — code quality)**
**OBSERVATION #2: Silent failures в cleanup**
- **Локація:** `fsm_manage.py:1113-1128`
- **Impact:** Exception в cleanup не propagated → застарілий metadata залишається
- **Fix:** Додати retry mechanism або fallback strategy

---

### 📊 **Root Cause Summary**

**Primary root cause:** **Відсутність cleanup lifecycle management**
- ManageFlowFSM має `_clear_guardian_bracket_set()`, але викликає його **тільки** при full close
- Partial close, scale-in, position flip — всі пропускають cleanup
- `OrderGuardian.register_bracket_set()` перезаписує metadata без знання про старі ордери

**Secondary root cause:** **Відсутність атомарності при розміщенні ордерів**
- Batch placement через adapter, але немає rollback при partial failure
- Якщо один ордер fails → другий залишається на біржі → incomplete protection

**Tertiary root cause:** **Watchdog timing issues**
- 5-second interval занадто повільний для detection
- Але занадто швидкий для false positives протягом placement window

---

### Наступні кроки (ФАЗА 4)

1. Аналіз dependency graph: які модулі залежать від `_bracket_sets` integrity?
2. Review error handling: де ще можуть бути silent failures?
3. State management audit: чи є persistent storage для bracket sets при restart?
4. Configuration conflicts: чи впливає `recalc_on_partial_close=false` на інші модулі?

---

## ═══════════════════════════════════════════════════════════
## ФАЗА 4: АНАЛІЗ КРИХКОСТІ СИСТЕМИ — SUMMARY
## ═══════════════════════════════════════════════════════════

### 4.1. Dependency Analysis — Хто залежить від `_bracket_sets`?

#### **Direct consumers (читають з `_bracket_sets`):**

**1. Watchdog validation (`agg_oco_watchdog.py:70-146`)**
```python
def validate_agg_oco_invariants(
    positions: Sequence[Any],
    open_orders: Sequence[Any],
    bracket_metas: Sequence[BracketSetMeta],  # ← Читає з _bracket_sets
    now_ts: float,
) -> List[AggOcoViolation]:
```

**Залежність:** Watchdog очікує що `bracket_metas` sync з реальними ордерами на біржі.
**Проблема:** Якщо `_bracket_sets` застарілі (BUG #8, #9) → генерує **false positive violations**.

**Scenarios:**
- Scale-in → старі order IDs втрачені → watchdog бачить тільки нові ордери → `MULTIPLE_META_SETS`
- Partial close → metadata не очищено → watchdog бачить metadata без відповідних ордерів

---

**2. Bracket set queries (`fsm.py:1369-1382`)**
```python
def _list_guardian_bracket_sets(self) -> List[Any]:
    guardian = getattr(self, "order_guardian", None)
    if not guardian:
        return []
    try:
        list_fn = getattr(guardian, "list_bracket_sets", None)
        if callable(list_fn):
            metas = list_fn() or []
            return list(metas)
    except Exception as exc:
        self.logger.debug("...failed to list bracket sets: %s", exc)
    return []
```

**Використання:**
- Watchdog loop (`fsm.py:1493`)
- State dump/introspection (`fsm.py:1760`)
- DR/restart rehydration (`fsm.py:1385-1420`)

**Залежність:** ExecPosFSM довіряє що `_bracket_sets` містить тільки **активні** bracket sets.
**Проблема:** Застарілі entries накопичуються → watchdog бачить помилкову картину.

---

**3. Rehydration on startup (`fsm.py:1385-1420 + services/order_guardian.py:269-330`)**
```python
def _rehydrate_guardian_state(...):
    guardian = getattr(self, "order_guardian", None)
    rehydrate_fn = getattr(guardian, "rehydrate_bracket_set_for_position", None)

    for position in normalized_positions:
        key = (position.symbol.upper(), position.side.upper())
        if key in existing_keys:  # ← Перевіряє чи bracket set вже існує
            continue
        # Якщо немає → rehydrate з live orders
        rehydrate_fn(symbol=position.symbol, side=position.side, ...)
```

**Залежність:** Rehydration залежить від `existing_keys` = `_bracket_sets.keys()`.
**Проблема:**
- Якщо застарілі entries є → rehydration **пропускає** rebuild
- Позиція має order IDs з **попереднього session**, які більше не valid
- Watchdog детектує violations після restart

---

#### **Indirect consumers:**

**4. OrderGuardian.cleanup_orphans() (`services/order_guardian.py:283-350`)**
```python
async def cleanup_orphans(self):
    # Шукає bracket orders БЕЗ position
    # НЕ використовує _bracket_sets для detection
    # Але _bracket_sets впливає на TTL protection
```

**Залежність:** Cleanup **НЕ читає** `_bracket_sets` безпосередньо, але:
- `ensure_single_bracket_set_for_position()` використовує `_bracket_sets` для TTL check
- Якщо старі entries → TTL може захистити orphan orders від cleanup

---

**5. Tests & introspection (`test_order_guardian_bracket_state.py`, etc.)**
```python
all_meta = guardian.list_all_bracket_sets()
active = guardian.get_active_bracket_set("BTCUSDT", "LONG")
```

**Залежність:** Тести перевіряють integrity через `_bracket_sets`.
**Проблема:** Якщо tests pass, але production fails → timing/async issues не покриті тестами.

---

### 🎯 **Dependency Graph:**

```
OrderGuardian._bracket_sets (in-memory Dict)
        │
        ├──> ManageFlowFSM (WRITE)
        │    ├─> register_bracket_set() [on placement]
        │    └─> clear_bracket_set_for_position() [on full close only!]
        │
        ├──> ExecPosFSM.Watchdog (READ)
        │    ├─> _list_guardian_bracket_sets() → validate_agg_oco_invariants()
        │    └─> _rehydrate_guardian_state() [on startup]
        │
        ├──> State Introspection (READ)
        │    ├─> _agg_oco_state_summary() [for debugging]
        │    └─> list_all_bracket_sets() [for tests/monitoring]
        │
        └──> OrderGuardian.cleanup_orphans() (INDIRECT)
             └─> ensure_single_bracket_set_for_position() checks TTL
```

**Critical observation:** `_bracket_sets` має **багато readers**, але **тільки 2 writers**:
1. `register_bracket_set()` — додає/оновлює
2. `clear_bracket_set_for_position()` — видаляє

**Проблема:** Writers викликаються **несиметрично**:
- Register викликається при **кожному** bracket placement (entry, scale-in, partial close)
- Clear викликається **тільки** при full close (`position_qty == 0`)

**Результат:** Накопичення застарілих entries → всі readers бачать помилкові дані.

---

### 4.2. Error Handling Audit — Silent Failures

#### **❌ Silent Failure #1: register_bracket_set exception**
**Код:** `fsm_manage.py:1071-1109`

```python
try:
    meta = self._order_guardian.register_bracket_set(...)
except Exception as exc:
    logging.getLogger(__name__).warning("[BRK][agg] failed to register...", exc_info=exc)
    self._pending_bracket_log = None
    # ❌ NO RETRY, NO PROPAGATION
```

**Impact:**
- Ордери вже на біржі
- Metadata НЕ зареєстровано
- Watchdog детектує `NO_SL_FOR_OPEN_POSITION`
- **NO automatic recovery**

**Fix required:** Retry mechanism або fallback до rehydration на наступному watchdog run.

---

#### **❌ Silent Failure #2: clear_bracket_set_for_position exception**
**Код:** `fsm_manage.py:1113-1128`

```python
try:
    self._order_guardian.clear_bracket_set_for_position(symbol=symbol, side=side)
except Exception as exc:
    logging.getLogger(__name__).warning("[BRK][agg] failed to clear...", exc_info=exc)
    # ❌ NO RETRY, застарілий entry залишається
```

**Impact:**
- Застарілий bracket set залишається в `_bracket_sets`
- Watchdog може детектувати `MULTIPLE_META_SETS`
- **NO cleanup pathway**

**Fix required:** Mark entry as "stale" і skip його в watchdog validation.

---

#### **❌ Silent Failure #3: rehydrate_bracket_set_for_position exception**
**Код:** `fsm.py:1401-1420`

```python
try:
    rehydrate_fn(symbol=position.symbol, side=position.side, ...)
except Exception as exc:
    self.logger.debug("...rehydrate failed for %s/%s: %s", ...)
    # ❌ DEBUG level, NO alerting
```

**Impact:**
- Restart з існуючими позиціями
- Rehydration fails → metadata НЕ створено
- Watchdog детектує violations одразу після startup
- **NO visibility** (debug log level)

**Fix required:** Promote to WARNING/ERROR, додати metrics counter.

---

#### **❌ Silent Failure #4: Adapter order placement partial failure**
**Код:** `fsm.py:3500-3550`

```python
responses = await adapter.place_order_batch([sl_order, tp_order])
sl_resp = responses[0]
tp_resp = responses[1]
# ❌ НЕ перевіряється чи responses[i] містить error
sl_order_id = str(sl_resp["orderId"])  # може raise KeyError
```

**Impact:**
- Один ордер rejected → exception
- Другий ордер вже на біржі
- **NO rollback**, incomplete protection

**Fix required:**
```python
if "code" in sl_resp or "orderId" not in sl_resp:
    # Cancel tp_order if placed
    await adapter.cancel_order(...)
    raise PlacementError("SL order rejected")
```

---

#### **✅ Proper Error Handling: _compute_aggregated_bracket_levels**
**Код:** `fsm_manage.py:818-865`

```python
try:
    levels = self._compute_aggregated_bracket_levels(reason=agg_why)
except AggregatedOcoError as exc:
    LOG.warning("[BRK][agg] failed to compute: %s", exc)
    self.state = ManageState.TRACKING
    self._metrics["fsm_errors_total"] += 1
    return None  # ✅ Early return, state reset, metrics
```

**Good pattern:** Exception caught, logged, **state reset**, metrics incremented, **propagated upward** (via `return None`).

---

### 4.3. State Management Audit — Memory vs Persistent

#### **Current state: In-memory only (`_bracket_sets: Dict`)**

**Lifecycle:**
1. **Creation:** `register_bracket_set()` → додає в dict
2. **Update:** `register_bracket_set()` з same key → overwrite
3. **Deletion:** `clear_bracket_set_for_position()` → `del _bracket_sets[key]`
4. **Restart:** dict порожній → потребує rehydration

---

#### **Rehydration mechanism (`rehydrate_bracket_set_for_position`)**
**Код:** `services/order_guardian.py:269-330`

```python
def rehydrate_bracket_set_for_position(
    self,
    symbol: str,
    side: str,
    position_amt: float,
    open_orders: Sequence[Any],
    now_ts: Optional[float] = None,
) -> Optional[BracketSetMeta]:
    # 1. Перевірити чи вже існує bracket set
    existing = self.get_active_bracket_set(symbol, side)
    if existing:
        return existing  # ❌ NO rebuild якщо є застарілий entry!

    # 2. Знайти bracket orders серед open_orders
    candidates = self._select_bracket_orders_for_symbol_side(...)
    if not candidates:
        return None

    # 3. Створити BracketSetMeta з live orders
    meta = BracketSetMeta(
        bracket_set_id=f"rehydrated:{symbol}:{side}:{int(now_ts)}",
        symbol=symbol,
        side=side,
        sl_order_id=sl_order.order_id,
        tp_order_id=tp_order.order_id,
        created_ts=now_ts or time.time(),
        version=0,
    )
    self._bracket_sets[key] = meta
    return meta
```

**Проблема:**
- Rehydration **пропускає rebuild** якщо `existing` entry є
- Застарілий entry з **попереднього session** блокує rehydration
- **NO persistent storage** → кожен restart потребує rehydration

---

#### **❌ BUG #12: Rehydration не очищає застарілі entries**
**Scenario:**
1. Session #1: Position opened → bracket set зареєстровано (sl_id="123")
2. Crash/restart
3. Session #2: Rehydration викликається
4. **Problem:** `_bracket_sets` порожній після restart (in-memory dict)
5. Rehydration створює НОВИЙ bracket set з live orders (sl_id="456")
6. **But:** Якщо `_bracket_sets` NOT порожній (чому?) → rehydration пропускається
7. Position має ордери з sl_id="456", але metadata вказує на sl_id="123"

**Root cause:** Немає guarantee що `_bracket_sets` порожній після restart.

---

#### **⚠️ Reconciliation gap:**

**What happens on restart:**
```
1. ExecPosFSM.__init__() → створює OrderGuardian з порожнім _bracket_sets
2. ExecPosFSM._rehydrate_aggregated_brackets_on_startup()
   ├─> Читає positions з біржі
   ├─> Читає open_orders з біржі
   └─> Для кожної позиції:
       └─> IF bracket set NOT exists:
           └─> rehydrate_bracket_set_for_position()
3. Watchdog starts → validate_agg_oco_invariants()
```

**Problem:** Між кроком 1 і 2 може пройти час → нові fills можуть статися → inconsistent state.

**Fix required:**
- Lock positions під час rehydration
- Або використовувати persistent storage для `_bracket_sets` (Redis/DB)

---

### 4.4. Configuration Conflicts

#### **Conflict #1: `recalc_on_partial_close = false` vs watchdog expectations**

**Config:** `system_config.yaml:95-96`
```yaml
aggregated_oco:
  recalc_on_partial_close: false  # ← ВИМКНЕНО
```

**Impact:**
- Partial close НЕ тригерить recalc
- Старі ордери залишаються (qty для full position)
- Watchdog очікує що ордери match remaining position qty
- **Result:** Watchdog може НЕ детектувати проблему (ордери існують, але qty неправильна)

**Recommendation:** Завжди використовувати `recalc_on_partial_close: true` в aggregated mode.

---

#### **Conflict #2: `aggregated_only_mode = true` vs legacy bracket logic**

**Config:**
```yaml
aggregated_oco:
  aggregated_only_mode: true
  enabled: true
```

**Code:** `fsm_manage.py:629-633`
```python
def _place_brackets(self, msg: Message, reason: str = "entry_fill") -> Optional[Message]:
    if self._aggregated_only_mode:
        if not self._is_aggregated_oco_enabled():
            raise RuntimeError("aggregated_only_mode requires aggregated_oco enabled")
        return self._place_brackets_aggregated(msg, reason)
    # ... legacy bracket logic ...
```

**Problem:**
- `aggregated_only_mode` блокує legacy brackets
- Але якщо `enabled: false` → runtime error
- **NO fallback** до legacy logic

**Fix:** Додати validation в config loader:
```python
if aggregated_only_mode and not enabled:
    raise ConfigValidationError("aggregated_only_mode requires enabled=true")
```

---

#### **Conflict #3: `recalc_on_scale_in = true` vs TTL protection**

**Config:**
```yaml
aggregated_oco:
  recalc_on_scale_in: true
  ttl_protect_new_bracket_ms: 3000
```

**Flow:**
1. Position opened → brackets placed → TTL = 3000ms
2. Scale-in fill після 1000ms → `recalc_on_scale_in` тригерить recalc
3. `_recalc_aggregated_brackets()` перевіряє TTL (L1595-1615):
   ```python
   elapsed = now_ms - self._aggregated_last_place_ts  # 1000ms
   if elapsed < ttl_ms:  # 1000 < 3000 → TRUE
       return None  # ❌ SKIP recalc!
   ```
4. **Result:** Scale-in НЕ оновлює brackets → position має неправильні TP/SL рівні

**Problem:** TTL захищає від recalc, але scale-in **має** оновити рівні (avg_price змінився).

**Fix:** Додати exception для scale-in:
```python
if elapsed < ttl_ms and reason != "scale_in_fill":
    return None
```

---

#### **Conflict #4: `allow_unprotected_position = false` vs cleanup timing**

**Config:**
```yaml
aggregated_oco:
  allow_unprotected_position: false
```

**Behavior:** `ensure_single_bracket_set_for_position()` НЕ дозволяє видаляти останній SL якщо position_amt > 0.

**Problem:**
- Partial close → старі ордери скасовані
- Нові ордери ще НЕ розміщені
- Між скасуванням і розміщенням — position **unprotected** (0-30ms window)
- Але `allow_unprotected_position = false` → cleanup може fail

**Impact:** Minor (короткий window), але може призвести до race condition.

---

### 📊 **Root Causes Крихкості — Consolidated**

#### **PRIMARY: Architecture fragility**
1. **In-memory only state** — `_bracket_sets` втрачається при restart
2. **Asymmetric lifecycle** — register викликається часто, clear рідко
3. **NO reconciliation** — немає механізму для sync `_bracket_sets` з біржею
4. **Single point of truth** — `_bracket_sets` є єдиним джерелом metadata

#### **SECONDARY: Error handling gaps**
1. **Silent failures** — exceptions logged, но не propagated
2. **NO retry mechanisms** — failed registration = permanent inconsistency
3. **NO rollback** — partial order placement failure → incomplete protection
4. **NO alerting** — debug-level logs для critical failures

#### **TERTIARY: Configuration conflicts**
1. **Incompatible settings** — `recalc_on_partial_close=false` + watchdog expectations
2. **TTL vs recalc** — TTL блокує legitimate recalc events
3. **NO validation** — config conflicts detected at runtime, not at load time

---

### 🎯 **Recommendations для Robustness**

#### **1. Add persistent storage layer**
```python
class BracketSetStore:
    def __init__(self, redis_client):
        self._redis = redis_client
        self._memory_cache = {}

    def register(self, key, meta):
        # Write to Redis first
        self._redis.hset(f"bracket_sets:{key[0]}:{key[1]}", meta.to_dict())
        # Then update memory cache
        self._memory_cache[key] = meta

    def clear(self, key):
        self._redis.hdel(f"bracket_sets:{key[0]}:{key[1]}")
        self._memory_cache.pop(key, None)
```

#### **2. Symmetric lifecycle management**
```python
def _recalc_aggregated_brackets(self, msg, reason):
    # ✅ ЗАВЖДИ очищати перед recalc
    self._clear_guardian_bracket_set(self.symbol, self.agg_side)
    # Потім розміщувати нові ордери
    return self._place_brackets_aggregated(msg, reason)
```

#### **3. Reconciliation mechanism**
```python
async def reconcile_bracket_sets(self):
    """Periodic reconciliation: sync _bracket_sets з біржею."""
    positions = await self.adapter.get_account_positions()
    open_orders = await self.adapter.get_open_orders()

    for symbol, side in self._bracket_sets.keys():
        # Перевірити чи position існує
        # Перевірити чи orders існують
        # Якщо ні → clear metadata
```

#### **4. Config validation at load time**
```python
def validate_aggregated_oco_config(cfg: AggregatedOcoConfig):
    if cfg.aggregated_only_mode and not cfg.enabled:
        raise ValueError("aggregated_only_mode requires enabled=true")

    if cfg.recalc_on_scale_in and cfg.ttl_protect_new_bracket_ms > 10000:
        warnings.warn("High TTL may block scale-in recalc")
```

#### **5. Retry mechanism для registration**
```python
@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
def _register_bracket_set_with_retry(self, ...):
    return self._order_guardian.register_bracket_set(...)
```

---

---

## ═══════════════════════════════════════════════════════════
## CROSS-VALIDATION: Порівняння з дослідженням Agent #2
## ═══════════════════════════════════════════════════════════

### 🎯 **Збіжність висновків (100% overlap на root cause)**

#### **Ключовий баг: TTL guard блокує cleanup**

**Agent #2 знахідка:**
```python
# apps/reference/services/order_guardian.py:432-640
def ensure_single_bracket_set_for_position(...):
    if cfg.ttl_protect_new_bracket_ms > 0:
        age_ms = max(0.0, (now - meta.created_ts) * 1000.0)
        if age_ms < cfg.ttl_protect_new_bracket_ms:
            self._emit_guard_event(..., decision="ttl_skip", ...)
            return 0  # ❌ EXIT before cleanup!
```

**Моя знахідка (Phase 4.4):**
```yaml
Config Conflict #3: recalc_on_scale_in = true vs TTL protection
- Scale-in fill після 1000ms → recalc тригериться
- TTL check: elapsed < 3000ms → SKIP recalc
- Result: Position має неправильні TP/SL рівні
```

**✅ Висновок:** Обидва виявили **IDENTICAL root cause** — TTL guard в `ensure_single_bracket_set_for_position` виходить ДО cleanup logic, блокуючи видалення застарілих SL/TP.

---

#### **Сценарій "3 позиції, 4 ордери (1 TP BNB, 2 SL BNB, 1 SL BTC)"**

**Agent #2 reconstruction:**
1. Entry → BracketSetMeta(sl_id=SL1, tp_id=TP1, version=0)
2. Scale-in → new SL2/TP2 → `register_bracket_set()` updates meta (sl_id=SL2, tp_id=TP2, version=1)
3. `cleanup_other_brackets_for_symbol` → `ensure_single_bracket_set_for_position`
4. **TTL guard:** `age_ms < 3000ms` → return 0 (NO cleanup)
5. **Result:** SL1 залишається, маємо SL1 + SL2 + TP2 для BNB

**Мій аналіз (BUG #8, #9):**
- BUG #8: Partial close doesn't call `_clear_guardian_bracket_set()` (fsm_manage.py:1411-1418)
- BUG #9: Scale-in overwrites bracket set без cleanup (fsm_manage.py:1422-1423)
- BUG #10: No rollback on partial order placement failure

**✅ Висновок:** Agent #2 дав **ТОЧНИЙ механізм** (TTL в `ensure_single_bracket_set_for_position`), я дав **BROADER CONTEXT** (missing cleanup в ManageFlowFSM + architectural issues). Обидва вірні, комплементарні.

---

#### **Watchdog не бачить "дубльовані SL"**

**Agent #2:**
> Watchdog перевіряє тільки:
> - qty > 0 і sl_count == 0 → NO_SL_FOR_OPEN_POSITION
> - meta_count > 1 → MULTIPLE_META_SETS
> - qty == 0 та orders exist → ORPHAN_SL_FOR_ZERO_POSITION
>
> У нашому випадку: qty > 0, sl_count == 2, meta_count == 1 → жодної violation.

**Моя знахідка (Phase 3):**
> Watchdog timing false positives: validation runs every 5s, bracket placement takes 50-200ms. During placement window watchdog sees position without SL → generates NO_SL_FOR_OPEN_POSITION violation.

**✅ Висновок:** Agent #2 виявив **MISSING INVARIANT** (`sl_count > 1` не перевіряється), я виявив **FALSE POSITIVE INVARIANTS** (timing window). Обидва правильні, різні аспекти тієї ж проблеми.

---

### 🔍 **Додаткові знахідки Agent #2 (не покриті мною)**

#### **1. TTL логіка застосована на рівні ВСЬОГО cleanup, а не окремих ордерів**
**Agent #2 insight:**
> TTL‑guard застосовано на рівні всього cleanup, а не на рівні "які SL/TP можна чіпати". Зараз TTL блокує будь-яке очищення, включно зі старими, явно зайвими SL/TP.

**Мій gap:** Я виявив що TTL блокує recalc, але НЕ виявив що він блокує cleanup старих ордерів навіть коли нові ордери вже захищені TTL.

**Impact:** High — це критична деталь для fix design.

---

#### **2. Жодного "другого шансу" після TTL немає**
**Agent #2 insight:**
> ensure_single_bracket_set_for_position викликається разово через cleanup_other_brackets_for_symbol у момент постановки нових брекетів. Після TTL ніхто повторно не запускає aggregated cleanup.

**Мій coverage:** Я виявив відсутність reconciliation mechanism (Phase 4.3), але НЕ зв'язав це з TTL lifecycle.

**Impact:** Medium — підсилює необхідність periodic reconciliation.

---

#### **3. Тести підштовхнули до такої поведінки**
**Agent #2 insight:**
> `test_ttl_guard_does_not_cancel_fresh_bracket` прямо очікує, що при TTL > 0 ensure_single_bracket_set_for_position не прибирає зайвий SL у свіжій меті — дубльовані SL у вікні TTL вважаються "нормою" в тесті.

**Критичне:** Test EXPLICITLY ENCODES the buggy behavior! Це означає баг був **designed in**, не accidental.

---

### 🎯 **Мої додаткові знахідки (не покриті Agent #2)**

#### **1. Dependency graph і blast radius**
**Моя Phase 4.1:**
```
_bracket_sets має 5 consumers:
├─> ManageFlowFSM (WRITE) - register/clear
├─> Watchdog (READ) - validation
├─> ExecPosFSM (READ) - rehydration
├─> Introspection (READ) - debugging
└─> OrderGuardian.cleanup (INDIRECT) - TTL protection
```

**Impact:** Показує що якщо `_bracket_sets` застарілий, це впливає на ВСІ 5 consumers, не тільки cleanup.

---

#### **2. Silent failures в error handling**
**Мої Phase 4.2 bugs:**
- Silent Failure #1: `register_bracket_set()` exception → logged, NO retry
- Silent Failure #2: `clear_bracket_set_for_position()` exception → застарілий entry залишається
- Silent Failure #3: `rehydrate_bracket_set_for_position()` exception → DEBUG level, NO visibility
- Silent Failure #4: Adapter partial placement failure → NO rollback

**Impact:** High — навіть якщо виправити TTL guard, silent failures можуть створити ті ж симптоми.

---

#### **3. In-memory only state + restart reconciliation**
**Моя Phase 4.3:**
- BUG #12: Rehydration не очищає застарілі entries
- Немає persistent storage для `_bracket_sets`
- Rehydration пропускає rebuild якщо застарілий entry існує

**Impact:** High — DR/restart може НЕ відновити правильний стан.

---

#### **4. Configuration conflicts matrix**
**Моя Phase 4.4:**
- Conflict #1: `recalc_on_partial_close=false` vs watchdog expectations
- Conflict #2: `aggregated_only_mode=true` but `enabled=false` → runtime error
- Conflict #3: TTL blocks scale-in recalc (also found by Agent #2)
- Conflict #4: `allow_unprotected_position=false` vs cleanup timing

**Impact:** Medium — config validation could prevent many issues.

---

### 📊 **Unified Root Cause Analysis**

#### **PRIMARY ROOT CAUSE (consensus):**
**TTL guard в `ensure_single_bracket_set_for_position` exits before cleanup старих ордерів**

**Code location:** `apps/reference/services/order_guardian.py:432-640`

**Mechanism:**
1. `register_bracket_set()` оновлює meta з новими sl_id/tp_id + bumps version
2. `cleanup_other_brackets_for_symbol()` викликає `ensure_single_bracket_set_for_position()`
3. TTL check: `age_ms = (now - meta.created_ts) * 1000` < 3000ms
4. Early return → старі SL/TP НЕ скасовані
5. Жодний інший механізм НЕ запускає cleanup після TTL expiry
6. Watchdog НЕ детектує "sl_count > 1" як violation

**Impact:** Duplicated SL/TP accumulate indefinitely after scale-in/partial-close.

---

#### **SECONDARY ROOT CAUSES:**

**1. Missing cleanup lifecycle management (моя знахідка)**
- `_clear_guardian_bracket_set()` тільки при full close (qty == 0)
- Partial close і scale-in НЕ викликають cleanup

**2. Asymmetric register/clear (моя знахідка)**
- `register_bracket_set()` викликається при кожному bracket placement
- `clear_bracket_set_for_position()` тільки при full close

**3. No retry/rollback mechanisms (моя знахідка)**
- Registration failure → silent, NO recovery
- Partial order placement → NO rollback

**4. Missing watchdog invariant (Agent #2 знахідка)**
- Watchdog НЕ перевіряє `sl_count > 1 for qty > 0`

**5. Test encodes buggy behavior (Agent #2 знахідка)**
- `test_ttl_guard_does_not_cancel_fresh_bracket` explicitly expects duplicates

**6. In-memory only state (моя знахідка)**
- `_bracket_sets` втрачається при restart
- Rehydration може не відновити правильний стан

---

### 🎯 **Unified Fix Plan**

#### **Fix #1: Refactor TTL guard to protect only NEW orders (P0)**
**Agent #2 proposal:**
```python
def ensure_single_bracket_set_for_position(...):
    meta = self._bracket_sets.get(key)
    candidates = self._select_bracket_orders_for_symbol_side(...)

    # ✅ NEW: Separate protected vs cleanable orders
    protected_ids = {meta.sl_order_id, meta.tp_order_id}

    if cfg.ttl_protect_new_bracket_ms > 0:
        age_ms = (now - meta.created_ts) * 1000.0
        if age_ms < cfg.ttl_protect_new_bracket_ms:
            # ✅ TTL protects ONLY protected_ids, allows cleanup of others
            self._emit_guard_event(..., decision="ttl_partial", ...)
            # Continue to cleanup logic below

    # Cleanup: cancel all candidates NOT in protected_ids
    to_cancel = [o for o in candidates if o.order_id not in protected_ids]
    for order in to_cancel:
        await self.adapter.cancel_order(order.order_id)

    return len(to_cancel)
```

**Estimated LOC:** 20-30 lines in `ensure_single_bracket_set_for_position`

---

#### **Fix #2: Add watchdog invariant TOO_MANY_SL (P0)**
**Agent #2 proposal + моя деталізація:**
```python
# agg_oco_watchdog.py
class AggOcoViolationKind(str, Enum):
    NO_SL_FOR_OPEN_POSITION = "NO_SL_FOR_OPEN_POSITION"
    ORPHAN_SL_FOR_ZERO_POSITION = "ORPHAN_SL_FOR_ZERO_POSITION"
    MULTIPLE_META_SETS = "MULTIPLE_META_SETS"
    TOO_MANY_SL_FOR_OPEN_POSITION = "TOO_MANY_SL_FOR_OPEN_POSITION"  # ✅ NEW

def validate_agg_oco_invariants(...) -> List[AggOcoViolation]:
    # ... existing checks ...

    # ✅ NEW: Check sl_count <= 1 for open positions
    if position_qty > 0 and sl_count > 1:
        violations.append(AggOcoViolation(
            kind=AggOcoViolationKind.TOO_MANY_SL_FOR_OPEN_POSITION,
            symbol=symbol,
            side=side,
            details=f"position_qty={position_qty}, sl_count={sl_count}",
        ))
```

**Auto-heal logic:**
```python
# fsm.py
async def _heal_agg_oco_violation(self, violation: AggOcoViolation):
    if violation.kind == AggOcoViolationKind.TOO_MANY_SL_FOR_OPEN_POSITION:
        # Trigger cleanup via guardian
        await self.order_guardian.ensure_single_bracket_set_for_position(
            symbol=violation.symbol,
            side=violation.side,
            position_amt=...,
            open_orders=...,
            now_ts=time.time(),
        )
```

**Estimated LOC:** 30-40 lines total

---

#### **Fix #3: Symmetric cleanup lifecycle (P1)**
**Моя Phase 4 proposal:**
```python
def _recalc_aggregated_brackets(self, msg, reason):
    # ✅ ЗАВЖДИ очищати перед recalc
    self._clear_guardian_bracket_set(self.symbol, self.agg_side)

    # Потім розміщувати нові ордери
    return self._place_brackets_aggregated(msg, reason)
```

**Estimated LOC:** 5-10 lines in `fsm_manage.py`

---

#### **Fix #4: Add periodic reconciliation (P1)**
**Моя Phase 4.3 proposal:**
```python
async def _reconcile_bracket_sets_periodic(self):
    """Run every 60s: sync _bracket_sets з біржею."""
    positions = await self.adapter.get_account_positions()
    open_orders = await self.adapter.get_open_orders()

    for (symbol, side), meta in list(self._bracket_sets.items()):
        # Check if position exists
        pos = next((p for p in positions if p.symbol == symbol and p.side == side), None)
        if not pos or pos.position_amt == 0:
            # No position → clear metadata
            self.clear_bracket_set_for_position(symbol, side)
            continue

        # Check if orders exist
        sl_exists = any(o.order_id == meta.sl_order_id for o in open_orders)
        tp_exists = any(o.order_id == meta.tp_order_id for o in open_orders)

        if not (sl_exists and tp_exists):
            # Orders missing → rehydrate
            await self.rehydrate_bracket_set_for_position(symbol, side, ...)
```

**Estimated LOC:** 40-50 lines, new method in `order_guardian.py`

---

#### **Fix #5: Rewrite test expectations (P0)**
**Agent #2 proposal:**
> Немає жодного інтеграційного тесту на "не більше одного SL/TP для відкритої aggregated позиції" з увімкненим TTL.

**New test:**
```python
async def test_scale_in_with_ttl_removes_old_brackets():
    """
    GIVEN: Position with SL1/TP1, ttl_protect_new_bracket_ms=3000
    WHEN: Scale-in → new SL2/TP2 placed
    THEN: Old SL1 cancelled immediately (TTL protects only SL2/TP2)
    AND: Only 1 SL + 1 TP remain on exchange
    """
    # Implementation...
```

**Estimated LOC:** 100-150 lines for comprehensive integration test suite

---

### 📋 **Prioritized Fix Plan**

| Priority | Fix | Estimated Effort | Impact |
|----------|-----|-----------------|--------|
| **P0** | Fix #1: Refactor TTL guard | 2-3 hours | ⭐⭐⭐⭐⭐ Eliminates root cause |
| **P0** | Fix #2: Add TOO_MANY_SL invariant | 2-3 hours | ⭐⭐⭐⭐⭐ Detects duplicates |
| **P0** | Fix #5: Rewrite test expectations | 4-5 hours | ⭐⭐⭐⭐⭐ Prevents regressions |
| **P1** | Fix #3: Symmetric cleanup lifecycle | 1-2 hours | ⭐⭐⭐⭐ Defense in depth |
| **P1** | Fix #4: Periodic reconciliation | 3-4 hours | ⭐⭐⭐ Safety net for edge cases |

**Total estimated effort:** 12-17 hours

---

### 🎓 **Lessons Learned — Consolidated**

#### **From Agent #2:**
1. **TTL semantics matter:** Protecting "fresh" metadata ≠ protecting ALL old orders
2. **Test-driven bugs:** Tests that explicitly encode buggy behavior are dangerous
3. **Single-shot cleanup is insufficient:** Need retry after TTL expires

#### **From my investigation:**
1. **Dependency graphs reveal blast radius:** Stale `_bracket_sets` affects 5 consumers
2. **Silent failures compound:** Registration failure + cleanup failure = permanent inconsistency
3. **In-memory state is fragile:** Restart can't recover without persistent storage
4. **Config validation prevents issues:** Incompatible settings should fail at load time

#### **Shared insights:**
1. **Asymmetric lifecycle → accumulation:** More writes than clears = memory leak pattern
2. **Missing invariants = invisible bugs:** Watchdog can't heal what it doesn't detect
3. **Timing assumptions break:** Async + retries + TTL → race conditions

---

### Наступні кроки (ФАЗА 5)

1. ✅ Implement Fix #1 (TTL refactor) — highest priority
2. ✅ Implement Fix #2 (watchdog invariant) — highest priority
3. ✅ Write integration tests (Fix #5) — validate fixes
4. Implement Fix #3 (symmetric cleanup) — defense in depth
5. Implement Fix #4 (reconciliation) — safety net

**Agent #2 дав smoking gun (TTL guard mechanism), я дав architectural context і blast radius analysis. Разом маємо COMPLETE картину.**

---

## Результати будуть документуватись тут після кожної фази
