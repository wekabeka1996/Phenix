# EXECUTION_POSITION NO_SL AUTOHEAL RESEARCH

**Дата:** 2025-11-20
**RID:** EP-INV-AGG-OCO-NO-SL-RESEARCH
**Тип:** Audit (read-only, no code changes)

---

## Update 2025-11-20 | EP-FIX-ENTRY-PRICE-FALLBACK-A

- ManageFlowFSM `_ensure_position_entry_price`: tries `price_service.mark/last` when entry_price is missing or zero before aggregated brackets; if still absent, fail-closes with `AGG_OCO_ENTRY_PRICE_NOT_READY` + metric.

---

## Update 2025-11-20 | EP-FIX-TRADE-EXECUTED-PRICE-ENRICHMENT-A

- ExecPosFSM `_enrich_fill_price` now guards all TRADE_EXECUTED/FILL events: enriches price from ManageFlow entry_price, WS snapshot, or PriceService; otherwise logs `EXEC_POS_TRADE_EXECUTED_SKIPPED_NO_PRICE` and drops the event.

---

## Update 2025-11-20 | EP-FIX-TRADE-EXECUTED-IDEMPOTENCY-B

- ExecPosFSM `_should_process_fill` adds simple in-memory idempotency for TRADE_EXECUTED/FILL based on (symbol|side|orderId) + cumulative qty; duplicates are skipped with metric/log before reaching ManageFlow.

---

## Update 2025-11-20 | EP-AH-CLEANUP-ORPHAN-DUPLICATE-VERIFY

- Cleanup-only watchdog handlers for ORPHAN_SL/TOO_MANY_SL are cancel-only (no FSM state changes or event emission); auto-heal disabled leaves cleanup inactive.

## Update 2025-11-20 | EP-ASYNC-CLEANUP-SUBMIT-A

- ExecPosFSM `_submit_async` now tracks background tasks via `_bg_tasks`, logs failures/cancels, and all internal fire-and-forget scheduling runs through this helper to avoid silent errors.

## Update 2025-11-20 | EP-AH-NO-SL-AUTOHEAL-REMOVAL

- Deprecated `ExecPosFSM._heal_no_sl_for_open_position` was fully removed; NO_SL detections now only log via `_record_no_sl_watchdog_observation`. Retry counters and REST force-fallback hooks tied to the old handler were deleted together with the method. All references in this research below remain for historical context only.

---

## 1. Контекст та мета

Провести повний аудит домену `execution_position` щодо:
- Проблеми `NO_SL_FOR_OPEN_POSITION`
- Логіки auto-heal та її побічних ефектів
- Джерел `entry_price` та його відсутності
- Асинхронних взаємодій і потенційних race conditions
- Розривів між реальними івентами та документацією

**Обмеження:** Жодних змін у робочому коді. Тільки створення звіту.

---

## 2. Карта модулів та відповідальностей

### 2.1. Основні модулі

| Модуль | Файл | Відповідальність |
|--------|------|------------------|
| **ExecPosFSM** | `fsm.py` (5134 рядків) | Оркестрація всіх sub-FSM, адаптер Binance, event bus |
| **ManageFlowFSM** | `fsm_manage.py` (2448 рядків) | Трекінг позиції, розрахунок/розміщення brackets (SL/TP) |
| **OrderTimeoutWatchdog** | `watchdog.py` (621 рядок) | Таймаути ордерів (ACK/FILL), REST polling для missed fills |
| **AGG_OCO Watchdog** | `fsm.py:_agg_oco_watchdog_loop` | Перевірка інваріантів (`NO_SL`, `ORPHAN_SL`, `TOO_MANY_SL`), auto-heal |
| **OrderGuardian** | `order_guardian.py` (wrapper) + `services/order_guardian.py` | Реєстрація bracket sets, cleanup orphans, unified ownership |
| **OpenFlowFSM** | `fsm_open.py` | Розміщення entry ордерів |
| **CloseFlowFSM** | `fsm_close.py` | Закриття позицій |

### 2.2. Архітектурна діаграма

```
┌──────────────┐
│ ExecPosFSM   │ ◄─ FSMCore event bus (EVT:TRADE_EXECUTED, EVT:ORDER_ACK, EVT:PORTFOLIO_STATE_UPDATED)
└──────┬───────┘
       ├─► ManageFlowFSM[symbol] ───► compute_aggregated_brackets() ───► DEC:PLACE_ORDER (SL/TP)
       │                           └─► register_bracket_set() ───► OrderGuardian
       │
       ├─► OrderTimeoutWatchdog ───► REST polling (get_order) ───► EVT:TRADE_EXECUTED (source=rest_watchdog)
       │
       └─► AGG_OCO Watchdog (async loop) ───► validate_agg_oco_invariants() ───► auto_heal (якщо enabled)
```

---

## 3. Поточна реалізація NO_SL / auto-heal / AGG_OCO

### 3.1. Детекція `NO_SL_FOR_OPEN_POSITION`

**Де:** `fsm.py:_agg_oco_watchdog_loop()` → `validate_agg_oco_invariants()` (імпортується з `agg_oco_watchdog.py`)

**Код-локація:**
- **Файл:** `apps/reference/domains/execution_position/fsm.py`
- **Рядки:** ~1620-1700 (`_run_agg_oco_watchdog_once`)

**Логіка:**
```python
async def _run_agg_oco_watchdog_once(self) -> None:
    # 1. Fetch open_orders & positions via REST API
    open_orders = await self._call_adapter_fn("get_open_orders", None)
    positions = await self._call_adapter_fn("get_open_positions")

    # 2. Перетворити позиції у WatchdogPosition (normalize_positions_for_watchdog)
    normalized_positions = normalize_positions_for_watchdog(positions)

    # 3. Отримати список bracket_metas з OrderGuardian
    metas = self._list_guardian_bracket_sets()

    # 4. Rehydrate guardian state (якщо є позиції без bracket meta)
    if normalized_positions:
        self._rehydrate_guardian_state(...)

    # 5. Валідація інваріантів
    violations = validate_agg_oco_invariants(
        positions=positions,
        open_orders=open_orders,
        bracket_metas=metas,
        now_ts=now_ts,
    )

    # 6. Логування та auto-heal
    for violation in violations:
        self._log_watchdog_violation(violation)
        if self._agg_watchdog_auto_heal:
            await self._auto_heal_watchdog_violation(violation)
```

**Інваріанти, що перевіряються:**
1. `NO_SL_FOR_OPEN_POSITION` — позиція відкрита (qty > 0), але немає жодного SL ордера
2. `ORPHAN_SL_FOR_ZERO_POSITION` — позиція закрита (qty = 0), але залишився SL/TP ордер
3. `TOO_MANY_SL_FOR_OPEN_POSITION` — кілька SL ордерів для однієї позиції

**Джерело даних:**
- **Позиції:** `adapter.get_open_positions()` (REST API Binance)
- **Ордери:** `adapter.get_open_orders()` (REST API Binance)
- **Bracket metadata:** `OrderGuardian.list_bracket_sets()` (in-memory або Ledger DB)

### 3.2. Auto-heal для `NO_SL_FOR_OPEN_POSITION`

**Де:** `fsm.py:_heal_no_sl_for_open_position()` (рядки ~1780-1860)

**Механізм:**
```python
async def _heal_no_sl_for_open_position(self, violation: AggOcoViolation) -> None:
    symbol = violation.symbol

    # [COSTYL-1] Circuit breaker: обмеження 5 спроб за 60с
    retry_key = f"autoheal_{symbol}"
    count, last_ts = self._autoheal_retry_counts.get(retry_key, (0, 0.0))
    if count >= 5:
        LOG.critical("AGG_OCO_AUTOHEAL_ABORTED_LOOP_DETECTED", ...)
        return  # ⛔ Повний стоп — але позиція залишається без SL!

    # [ASYNC_RISK-1] Force-reset ManageFlowFSM state (якщо застряг у BRACKETS_PENDING)
    manage_flow = self.manage_flows.get(symbol)
    if manage_flow.state == ManageState.BRACKETS_PENDING:
        manage_flow.state = ManageState.TRACKING  # ⚠️ Мутація стану без транзакції

    # [COSTYL-2] Створення fake TRADE_EXECUTED івенту для тригера recalc
    msg = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="execution_position.watchdog",
        pld={
            "symbol": symbol,
            "qty": str(violation.details.get("position_amt", 0)),
            "source": "watchdog_autoheal"  # ← Фейкова подія!
        },
        why="watchdog_autoheal_no_sl"
    )

    # [ASYNC_RISK-2] Синхронний виклик handle() з async контексту
    result = manage_flow.handle(msg)
    if result and result.op == "DEC":
        self._dispatch_decision(result, symbol)  # ← може емітити DEC:PLACE_ORDER
```

**[COSTYL] Проблеми:**
1. **Фейкова подія `TRADE_EXECUTED`** — емітується зі `source="watchdog_autoheal"`, але не є реальним fill'ом. Це може порушити обліковість у correlation_store, metrics, why-chain.
2. **Race condition:** Якщо між моментом детекції `NO_SL` та спробою healing прийшов реальний fill/cancel через WS, auto-heal може створити дублікат SL.
3. **Circuit breaker abort:** Після 5-ї спроби auto-heal **повністю припиняється**, але позиція **залишається без захисту**. Це критична дірка.
4. **REST backoff force-clear:** `_livepos_rest_backoff_until` примусово очищується після `_rest_backoff_force_threshold` спроб, що може призвести до спаму REST API.

---

## 4. Джерела entry_price та всі місця, де він може стати 0/None

### 4.1. Шляхи заповнення `position_entry_price`

**ManageFlowFSM.position_entry_price** заповнюється у:

#### **Шлях 1: FILL подія (_on_fill)**
**Файл:** `fsm_manage.py:_on_fill()` (рядки 590-620)

```python
def _on_fill(self, msg: Message):
    pld = msg.pld or {}
    qty = Decimal(str(pld.get("qty") or pld.get("quantity") or 0))
    price = Decimal(str(pld.get("price", 0)))  # ⚠️ Може бути 0!

    # Fallback на PriceService (якщо price=0)
    if price <= 0 and self.price_service and self.symbol:
        quote = self.price_service.get_current(self.symbol)
        fallback = getattr(quote, 'mark', None) or getattr(quote, 'last', None)
        if fallback:
            price = Decimal(str(fallback))

    if self.position_qty is None:
        # Перше відкриття позиції
        self.position_entry_price = price  # ⚠️ Може залишитись 0 якщо fallback провалився
    else:
        # Scale-in: усереднення
        avg_price = (self.position_qty * self.position_entry_price + qty * price) / total_qty
        self.position_entry_price = avg_price
```

**[TECH_DEBT] Проблеми:**
- Якщо `pld["price"]` відсутня або `0`, і `PriceService.get_current()` теж провалюється (наприклад, через rate-limit або недоступність), **`position_entry_price` залишається `0`**.
- Це призводить до помилки `"avg_entry_price must be > 0"` в `compute_aggregated_brackets()`.

#### **Шлях 2: Live position snapshot (_handle_aggregated_fill_event_aggregated_only)**
**Файл:** `fsm_manage.py:_handle_aggregated_fill_event_aggregated_only()` (рядки 1469-1640)

```python
def _handle_aggregated_fill_event_aggregated_only(self, ...):
    raw_snapshot = self._get_live_position_state()  # ← REST API або portfolio state
    snapshot = PositionSnapshot.from_generic_payload(raw_snapshot)

    # Fallback chain для entry_price:
    # 1. avg_price з snapshot
    avg_price_raw = raw_snapshot.get("avg_price") or raw_snapshot.get("entryPrice")
    if avg_price_raw:
        self.position_entry_price = Decimal(str(avg_price_raw))

    # 2. Fallback на fill price з message
    if self.position_entry_price is None or self.position_entry_price <= 0:
        fill_price = pld.get("price") or pld.get("avg_price")
        if fill_price:
            self.position_entry_price = Decimal(str(fill_price))

    # 3. Fallback на PriceService mark price
    if self.position_entry_price is None or self.position_entry_price <= 0:
        quote = self.price_service.get_current(symbol)
        mark = getattr(quote, 'mark', None)
        if mark:
            self.position_entry_price = Decimal(str(mark))
```

**[TECH_DEBT] Проблеми:**
- **Stale snapshot:** Якщо REST API відповідає з застарілими даними (`position_amt=0`, `entryPrice=0`), fallback може не спрацювати.
- **REST API timeout:** `_fetch_rest_position_snapshot()` має timeout `REST_FALLBACK_TIMEOUT_SEC` (за замовчуванням 15s). Якщо таймаут спрацьовує часто, встановлюється backoff window (`_livepos_rest_backoff_until`), і snapshot взагалі не отримується.
- **Метрика:** `_livepos_metrics["rest_timeouts"]` та `_livepos_metrics["portfolio_stale_data"]` трекують ці випадки, але **не блокують execution**.

#### **Шлях 3: REST polling watchdog (OrderTimeoutWatchdog)**
**Файл:** `watchdog.py:_poll_order_statuses()` (рядки 240-440)

```python
async def _poll_order_statuses(self) -> None:
    for order_id in tracked_order_ids:
        order_status = await self.get_order_fn(symbol, order_id)
        if status == "FILLED":
            fill_payload = self._build_trade_payload(...)  # ← будує TRADE_EXECUTED
            await self._emit_via_hook("EVT:TRADE_EXECUTED", fill_payload, ...)
```

**[ASYNC_RISK] Проблеми:**
- Watchdog емітує `EVT:TRADE_EXECUTED` напряму через `fsm_emit_compat`, але **також викликає `ExecPosFSM.handle(msg)`**.
- Це створює **два шляхи обробки одного fill'а**: через event bus і через direct call.
- Якщо обидва шляхи відпрацьовують, можливий **double-fill** або **race condition** з іншим fill івентом з WS.

### 4.2. Місця, де `entry_price` перевіряється як `None` або `0`

**Файл:** `fsm_manage.py:_compute_aggregated_bracket_levels()` (рядки 1209-1230)

```python
def _compute_aggregated_bracket_levels(self, *, reason: str):
    # [GUARD] Перевірка entry_price перед викликом aggregator
    if self.position_entry_price is None or self.position_entry_price <= 0:
        self._metrics["agg_entry_price_not_ready"] += 1
        agg_oco_logger.warning("AGG_OCO_ENTRY_PRICE_NOT_READY", ...)
        return None  # ⚠️ Повертає None замість помилки

    # Виклик aggregator (який вимагає avg_entry_price > 0)
    return compute_aggregated_brackets(
        position_amt=abs(self.position_qty),
        avg_entry_price=self.position_entry_price,  # ← Must be > 0
        ...
    )
```

**Наслідок:**
- Якщо `entry_price` не готова, **brackets не розміщуються**.
- Позиція залишається **без захисту** до наступного fill'а або auto-heal спроби.
- **Watchdog детектує це як `NO_SL_FOR_OPEN_POSITION`** і запускає auto-heal (якщо enabled).

---

## 5. Повний список асинхронних взаємодій

### 5.1. `asyncio.create_task` / `loop.create_task`

| Локація | Файл:рядок | Призначення | Lifecycle tracking | Потенційні ризики |
|---------|------------|-------------|--------------------|--------------------|
| `OrderTimeoutWatchdog._start_task()` | `watchdog.py:148` | Запуск `_watchdog_loop()` | `self._watchdog_task` | ✅ Task зберігається, `.cancel()` у `.stop()` |
| `ExecPosFSM._submit_async()` | `fsm.py:1360-1440` | Універсальний scheduler для coroutines | ❌ Fire-and-forget | [ASYNC_RISK] Немає `.done_callback`, exceptions можуть бути проковтнуті |
| `ExposureGuard._safe_create_task()` | `exposure_guard.py:1490-1504` | Емісія подій через `emit_compat()` | ❌ Fire-and-forget | [ASYNC_RISK] Немає обробки помилок |
| `ExecPosFSM._agg_oco_watchdog_loop()` | `fsm.py:1621` | AGG_OCO watchdog цикл | `self._agg_watchdog_task` | ✅ Cancellable, але немає `.done_callback` |

**[ASYNC_RISK] Ключові проблеми:**
1. **`_submit_async()` fire-and-forget:** Tasks створюються без збереження посилання. Якщо task упаде з exception, це **не буде залоговано**.
2. **Closing coro objects:** У тестах (без event loop) `_submit_async()` намагається закрити coroutine об'єкти вручну через `.close()`, але це не гарантує cleanup у всіх випадках.
3. **Thread-safety:** `_submit_async()` використовує `asyncio.run_coroutine_threadsafe()` для cross-thread scheduling, але не перевіряє, чи loop ще живий після schedule.

### 5.2. Background loops

| Loop | Файл:рядок | Interval | Stop mechanism |
|------|------------|----------|----------------|
| `OrderTimeoutWatchdog._watchdog_loop()` | `watchdog.py:210-230` | `check_interval_ms` (1000ms) | `self._started = False` |
| `AGG_OCO watchdog loop` | `fsm.py:1621-1636` | `_agg_watchdog_interval_sec` (5s) | `asyncio.CancelledError` |
| `OrderGuardian poll loop` | `services/order_guardian.py` | `poll_interval_ms` (500ms) | `self._running = False` |
| `FSM cleanup loop` | `fsm.py:_cleanup_loop()` | `orphan_cfg.interval_sec` (config) | Conditional `_fsm_cleanup_enabled` |

**[ASYNC_RISK] Проблеми:**
- **Двоє cleanup loops:** Guardian poll loop + FSM cleanup loop. Якщо `guardian.unified=true`, FSM cleanup має бути **disabled**, але логіка вимикання не завжди спрацьовує через config projection issues.
- **Watchdog start timing:** `_ensure_watchdog_running()` викликається в кількох місцях (`__init__`, `set_async_loop`, `_bind_watchdog_hooks`), що може призвести до **duplicate start attempts**.

---

## 6. Карта подій (EVT/DEC/UPD) для execution_position + розриви з документацією

### 6.1. Події, що **існують у коді**, але **не описані** в `FSM_EVENT_MAP.md`

| Подія | Де емітується | Призначення |
|-------|---------------|-------------|
| `EVT:TRADE_EXECUTED` | `watchdog.py:_emit_watchdog_event()` | REST polling detected fill (watchdog source) |
| `EVT:ORDER_STATE_CHANGED` | `watchdog.py:_poll_order_statuses()` | REST polling detected cancel/reject |
| `EVT:MANAGE_SKIPPED` | `fsm_manage.py:handle()` | Manage disabled або wait_mode active |
| `EVT:SYMBOL_TIDY` | `services/order_guardian.py` | Guardian cleanup completed для symbol |
| `AGG_OCO_WATCHDOG` | `fsm.py:_log_watchdog_violation()` | Логування violation (не event, а structured log) |
| `AGG_OCO_AUTOHEAL` | `fsm.py:_heal_no_sl_for_open_position()` | Auto-heal action (log event) |
| `AGG_OCO_ENTRY_PRICE_NOT_READY` | `fsm_manage.py:_compute_aggregated_bracket_levels()` | Entry price missing/zero |
| `AGG_OCO_REGISTER_BRACKET_SET_DONE` | `fsm_manage.py:_maybe_register_bracket_set()` | Bracket set зареєстровано в Guardian |

### 6.2. Події з `FSM_EVENT_MAP.md`, що **не використовуються** у поточній реалізації

| Подія з доків | Статус | Коментар |
|---------------|--------|----------|
| `EVT:TP_FILLED` | ❌ Не існує | Заміна: `EVT:TRADE_EXECUTED` з перевіркою `is_exit_order(pld)` |
| `EVT:SL_FILLED` | ❌ Не існує | Те саме — узагальнено в `TRADE_EXECUTED` |
| `CMD:CLOSE` | ❌ Не існує | Заміна: `DEC:CLOSE` (decision, не command) |
| `EVT:CLOSED` | ❌ Не існує | FSM cleanup відбувається через internal state transitions |
| `EVT:POSITION_OPENED` | ❌ Не існує | Немає окремої події; трекається через `ManageState.FLAT → BRACKETS_PENDING` |

### 6.3. [CONTRACT_DRIFT] Розриви з документацією

**Проблема:** `FSM_EVENT_MAP.md` описує **legacy per-entry OCO model** (окремі `TP_FILLED` / `SL_FILLED` події), але поточна реалізація використовує:
- **Aggregated OCO model** з єдиною `TRADE_EXECUTED` подією для всіх fills
- **Guardian-based ownership** замість per-entry tracking
- **Watchdog invariants** (`NO_SL`, `ORPHAN_SL`, `TOO_MANY_SL`) замість event-driven state machine

**Рекомендація:** Оновити `FSM_EVENT_MAP.md` на **Aggregated OCO v2** карту подій (або створити окремий `FSM_EVENT_MAP_AGGREGATED_OCO.md`).

---

## 7. Виявлені костилі, технічний борг, підозрілі місця

### 7.1. [COSTYL] Фейкові події від auto-heal

**Файл:** `fsm.py:_heal_no_sl_for_open_position()` (рядки 1780-1860)

**Проблема:**
- Створюється fake `EVT:TRADE_EXECUTED` зі `source="watchdog_autoheal"` та `qty` з violation details.
- Це **не є реальним fill'ом**, але обробляється так само, як і реальний.
- Може порушити:
  - **Correlation tracking** (RID/corr_id chain)
  - **Metrics** (total fills, executed qty)
  - **WHY-chain** (fake event у DR replay)

**Рекомендація:** Замінити на **прямий виклик** `_place_brackets_aggregated()` без емісії fake події.

### 7.2. [ASYNC_RISK] Double fill через watchdog + WS

**Файл:** `watchdog.py:_emit_watchdog_event()` + `fsm.py:_on_trade_executed()`

**Проблема:**
- Watchdog REST polling детектує fill і емітує `EVT:TRADE_EXECUTED`.
- Одночасно може прийти **той самий fill через WebSocket** (з затримкою).
- **Немає idempotency check** на рівні `ExecPosFSM.handle()` для `TRADE_EXECUTED` з однаковим `orderId`.

**Рекомендація:** Додати **deduplication** через `self._processed_events` (вже існує у коді, але не використовується для `TRADE_EXECUTED`).

### 7.3. [TECH_DEBT] REST backoff force-clear

**Файл:** `fsm.py:_heal_no_sl_for_open_position()` (рядки 1786-1800)

```python
if next_count >= self._rest_backoff_force_threshold:
    forced_symbol = symbol.upper()
    if self._livepos_rest_backoff_until.pop(forced_symbol, None) is not None:
        LOG.info("LIVEPOS_FORCE_REST_FALLBACK", ...)
```

**Проблема:**
- Після `_rest_backoff_force_threshold` (за замовчуванням 2) спроб auto-heal, **видаляється REST backoff** для forced REST fallback.
- Це може призвести до **спаму REST API** при degraded performance (timeout → retry → timeout → retry...).
- **Rate limiter watchdog** (`_rps_limit=10 req/s`) може блокувати ці запити, але це не гарантує захист.

**Рекомендація:** Використовувати **exponential backoff** замість flat threshold.

### 7.4. [COSTYL] ManageFlowFSM state mutation без FSM transition

**Файл:** `fsm.py:_heal_no_sl_for_open_position()` (рядки 1803-1807)

```python
if manage_flow.state == ManageState.BRACKETS_PENDING:
    LOG.warning("Force-resetting ManageFlowFSM state from BRACKETS_PENDING to TRACKING")
    manage_flow.state = ManageState.TRACKING  # ⚠️ Direct mutation!
```

**Проблема:**
- **Прямий assignment** `manage_flow.state = ...` без FSM transition logic.
- Пропускаються **on_exit / on_enter callbacks** (якщо вони є).
- Немає **логування** у WHY-chain про цей forced reset.

**Рекомендація:** Додати метод `ManageFlowFSM.force_reset_state()` з proper logging + metrics.

### 7.5. [TECH_DEBT] Entry price fallback chain fragility

**Файл:** `fsm_manage.py:_handle_aggregated_fill_event_aggregated_only()` (рядки 1590-1620)

**Проблема:**
- **Три fallbacks** для entry_price (snapshot → fill payload → PriceService mark).
- Якщо **всі три провалюються**, `position_entry_price` залишається `0` або `None`.
- Це **не блокує execution**, але призводить до:
  - `AGG_OCO_ENTRY_PRICE_NOT_READY` warning
  - Пропуск `_place_brackets_aggregated()`
  - Детекція `NO_SL_FOR_OPEN_POSITION` watchdog'ом
  - Auto-heal спроба (яка може також провалитись через те саме)

**Рекомендація:** Додати **hard fail + alert** якщо entry_price недоступна після N спроб.

### 7.6. [ASYNC_RISK] _submit_async() без exception handling

**Файл:** `fsm.py:_submit_async()` (рядки 1360-1440)

**Проблема:**
- Fire-and-forget tasks **не мають `.done_callback()`**.
- Якщо task упаде з exception, це **не буде залоговано**.
- У production це може призвести до **silent failures** (наприклад, Guardian cleanup loop упав, але ніхто не знає).

**Рекомендація:** Додати default `_task_done_callback()` з logging exceptions.

---

## 8. Висновки та рекомендації для наступного таску (fix-пакет)

### 8.1. Критичні проблеми (P0)

1. **[P0] Auto-heal circuit breaker abort без fallback**
   - **Проблема:** Після 5-ї спроби auto-heal повністю припиняється, позиція залишається без SL.
   - **Рішення:** Додати **emergency SL placement** через direct API call (bypass FSM) або **hard stop trading** для symbol.
   - **Файл:** `fsm.py:_heal_no_sl_for_open_position()` рядки 1791-1795.

2. **[P0] Entry price fallback chain провалюється silently**
   - **Проблема:** Якщо всі 3 fallbacks (snapshot, fill payload, PriceService) провалюються, позиція відкривається **без entry_price**.
   - **Рішення:** Додати **hard fail + circuit breaker** для symbol.
   - **Файл:** `fsm_manage.py:_handle_aggregated_fill_event_aggregated_only()` рядки 1590-1620.

3. **[P0] Double fill через watchdog + WS**
   - **Проблема:** Watchdog REST polling та WebSocket можуть емітити один і той же fill двічі.
   - **Рішення:** Додати deduplication через `orderId` в `self._processed_events`.
   - **Файл:** `watchdog.py:_emit_watchdog_event()` + `fsm.py:_on_trade_executed()`.

### 8.2. Високий пріоритет (P1)

4. **[P1] Видалити fake TRADE_EXECUTED події з auto-heal**
   - **Проблема:** Fake події порушують correlation tracking, metrics, WHY-chain.
   - **Рішення:** Замінити на прямий виклик `_place_brackets_aggregated()`.
   - **Файл:** `fsm.py:_heal_no_sl_for_open_position()` рядки 1810-1825.

5. **[P1] REST backoff exponential замість flat threshold**
   - **Проблема:** Flat threshold `_rest_backoff_force_threshold=2` може призвести до REST API spam.
   - **Рішення:** Exponential backoff: 20s → 40s → 80s → max 5m.
   - **Файл:** `fsm.py:_heal_no_sl_for_open_position()` рядки 1786-1800.

6. **[P1] ManageFlowFSM state mutation через proper transition method**
   - **Проблема:** Direct assignment `manage_flow.state = ...` пропускає FSM logic.
   - **Рішення:** Додати `force_reset_state(new_state, reason)` метод.
   - **Файл:** `fsm.py:_heal_no_sl_for_open_position()` рядки 1803-1807.

### 8.3. Середній пріоритет (P2)

7. **[P2] _submit_async() exception handling**
   - **Проблема:** Fire-and-forget tasks без `.done_callback()` можуть падати silently.
   - **Рішення:** Додати default callback з logging.
   - **Файл:** `fsm.py:_submit_async()` рядки 1360-1440.

8. **[P2] Оновити FSM_EVENT_MAP.md на Aggregated OCO v2**
   - **Проблема:** Документація описує legacy model, код використовує aggregated.
   - **Рішення:** Створити `FSM_EVENT_MAP_AGGREGATED_OCO_V2.md` з реальними івентами.
   - **Файл:** `docs/For_GPT/FSM_EVENT_MAP.md`.

9. **[P2] Додати metrics для auto-heal success/failure rate**
   - **Проблема:** Немає метрик для відстеження, наскільки часто auto-heal успішний.
   - **Рішення:** Додати `agg_autoheal_success`, `agg_autoheal_failed`, `agg_autoheal_aborted`.
   - **Файл:** `fsm.py:_heal_no_sl_for_open_position()`.

### 8.4. Низький пріоритет (P3)

10. **[P3] Consolidate cleanup loops (Guardian vs FSM)**
    - **Проблема:** Два окремі cleanup loops можуть працювати одночасно.
    - **Рішення:** Якщо `guardian.unified=true`, повністю вимкнути FSM cleanup loop.
    - **Файл:** `fsm.py:_schedule_fsm_cleanup_loop()`.

---

**Кінець звіту**
