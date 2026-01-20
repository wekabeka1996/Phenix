# ORDER-LIFECYCLE-AUDIT-01 — Phase 6: Dead / Legacy Paths Map (orders)
Дата: 2026-01-12  
Ціль: знайти “старі” гілки, які ще торкаються ордерів, але ймовірно неактивні після бар-моделі

Примітка: тут “dead/legacy” = **не видно явного runtime wiring** в `apps/reference/main.py` або є явні коментарі/kill-switch, що вимикають шлях.

---

## 1) Legacy orchestration stack (ймовірно не використовується в core runtime)
- `apps/reference/orchestrator/orchestrator_fsm.py` (RID lifecycle: EVAL→OPEN→MONITOR→CLOSED)  
  Evidence: модуль існує, але `apps/reference/main.py` не імпортує/не ініціалізує OrchestratorFSM.  
  Ризик: “дубль” концептуального Open/Monitor/Close може вводити в оману при grep-навігації по `CMD:OPEN`.
  Рекомендація: quarantine/explicitly mark as legacy у docs або додати “not wired” marker у playbook.

---

## 2) Legacy init / duplicate wiring (main.py)
- `apps/reference/main.py#L1395-L1403`:
  - є коментар: “Legacy unused initialization… actual one used at line 1718”
  - `decision_making = DecisionMaking(...)` створюється в `initialize_domains`, але позначений як legacy/unused.

Ризик:
- аудити/інструменти можуть “бачити” 2 різні DM інстанси в різних runtime pathways (залежно від того, який init використали).

---

## 3) Tick-driven remnants (після переходу на bar-driven)

### 3.1 `EVT:MARKET_TICK_RECEIVED` як data-path лишився (це не dead, але “legacy-trigger risk”)
- Wiring:
  - `apps/reference/main.py` підписує `bar_aggregator.on_market_tick` на `EVT:MARKET_TICK_RECEIVED`
  - `FeatureEngineering` слухає `EVT:MARKET_TICK_RECEIVED` (tick→features)
  - `PositionTracking` опціонально слухає `EVT:MARKET_TICK_RECEIVED` (mark prices)

### 3.2 DecisionMaking “bar-only law” відсікає tick-level `FEATURES_CALCULATED`
- `apps/reference/domains/decision_making/decision_making.py#L1810-L1842`:
  - якщо `tf_sec <= 0` → reject tick-level features (throttled logging)

Ризик:
- якщо десь інший компонент згенерує `FEATURES_CALCULATED` з `tf_sec=0/None`, DM може “німо” не приймати тригери.

---

## 4) “Events exist in code/docs but not actually produced” (dead-ish)

### 4.1 `EVT:ORDER_ACK` / `EVT:ORDER_FILL`
- `apps/reference/domains/execution_position/fsm.py` підписується:
  - `self.bus.listen("EVT:ORDER_ACK", self._on_order_ack)`
  - `self.bus.listen("EVT:ORDER_FILL", self._on_order_fill)`
- Але в repo нема явного producer для `EVT:ORDER_ACK`/`EVT:ORDER_FILL` (окрім docs/strings).
  - Реальні runtime updates приходять як `EVT:TRADE_EXECUTED` / `EVT:ORDER_STATE_CHANGED` (WS + watchdog polling hook).

Ризик:
- наявність dead listeners створює ілюзію, що система має ACK/FILL події як first-class, але фактично pipeline інший.
  Це ускладнює observability та “Orders Created:0” debug (див. Phase5 report).

### 4.2 `EVT:TICK_RECEIVED`
- Token існує в verb registry і runtime scan (бо згадується у `apps/reference/domains/decision_making/__init__.py` як документація),
  але немає явного emit/consumer у runtime code.

Ризик:
- registry coverage за “string scan” може бути хибно-позитивною (docs tokens ≠ runtime events).

---

## 5) “Old market-first placement” candidates
Головні placement calls зараз сконцентровані в `apps/reference/domains/execution_position/fsm.py`:
- `adapter.place_market_entry` (ENTRY)
- `adapter.place_limit_entry` (ENTRY)
- `adapter.place_market_reduce_only` / `adapter.place_limit_reduce_only` (exit/brackets)

Кандидати “legacy”:
- `apps/reference/services/order_guardian.py` в `register_entry()` hardcode `type="MARKET"` для entry metadata  
  (це не dead, але legacy/market-first припущення, токсичне для LIMIT-first).

---

## 6) Рекомендації (audit-only)
1) Позначити/ізолювати orchestrator layer як не-wired (або додати явний runtime entrypoint, якщо планується використання).
2) Прибрати/перемкнути dead listeners (`EVT:ORDER_ACK/FILL`) або зробити їх реально emitted (але тільки через registry + strict schema).
3) Для registry drift: не включати docs-only файли в runtime-token scan або маркувати tokens як “documentation-only”.

