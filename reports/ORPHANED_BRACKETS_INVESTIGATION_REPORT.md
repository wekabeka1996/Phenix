# Звіт дослідження проблеми висячих ордерів (Orphaned Brackets)

**Дата**: 5 листопада 2025
**Мета**: Виявити root causes проблем висячих TP/SL ордерів та несинхронних timeout-скасувань
**Методологія**: Аналіз логів, коду FSM, тестів без внесення змін

---

## Executive Summary

Виявлено **дві критичні проблеми** в системі управління брекетами (TP/SL ордерами):

1. **Timeout ≠ Cancellation на біржі**: Ордери, що вважаються системою "timed out" і скасованими (NRR-019), **фактично залишаються активними на біржі** і можуть виконуватися.

2. **Orphaned Brackets після fill'у**: Коли спрацьовує TP або SL, система **не завжди скасовує зворотний bracket** (OCO-емуляція працює лише за умови правильної конфігурації та передачі повного payload до ManageFlowFSM).

3. **Orphan Monitor неефективний**: Реалізований cleanup_orphaned_bracket_orders **не виконується у критичні моменти** (відсутні виклики при fill'ах, ручних закриттях, startup sync не гарантує повне очищення).

**Оцінка серйозності**: 🔴 CRITICAL — призводить до неконтрольованої експозиції, подвійних позицій, збитків через несподівані екзекуції.

---

## 1. Проблема: Timeout-скасування не синхронізовані з біржею

### 1.1 Виявлені факти з логів

**Приклад 1**: `order_log_v1.jsonl:5` (SOLUSDT)
```json
{"rid": "8837e925-7fed-433a-8cb1-65843c5aca03", "event_type": "ORDER_PLACED",
 "symbol": "SOLUSDT", "client_order_id": "ENTRY-2d3691eb1f", "order_id": "1228002865",
 "adapter_response": {"orderId": 1228002865, "status": "NEW", ...},
 "timestamp": 1762364112616}

{"rid": "8837e925-7fed-433a-8cb1-65843c5aca03", "event_type": "ORDER_TIMEOUT",
 "symbol": "SOLUSDT", "client_order_id": "ENTRY-2d3691eb1f", "order_id": "1228002865",
 "nrr_code": "NRR-019", "why": "Order timeout: fill_timeout",
 "timestamp": 1762364142895}
```

**Часова лінія**:
- `1762364112616` — Ордер розміщений, біржа відповіла `status: "NEW"` (orderId=1228002865)
- `1762364142895` — **30.3 секунди потім**: watchdog емітує ORDER_TIMEOUT (fill_timeout)

**Проблема**: Лог показує, що біржа **підтвердила розміщення ордера** (ACK status="NEW"). Після timeout watchdog логує NRR-019 і **викликає** `adapter.cancel_order(symbol, order_id)` (fsm.py:855), **але**:

- Немає логу про **результат скасування** (успіх/помилка від біржі).
- **Якщо біржа відхилить скасування** (наприклад, ордер уже виконується або заповнений), система **не дізнається** про це і вважатиме ордер скасованим.
- У подальших логах **відсутні записи про fill** цього ордера → ордер або скасовано вручну пізніше, або залишився на біржі.

**Підтвердження з коду** (`apps/reference/domains/execution_position/fsm.py:844-862`):

```python
async def _handle_order_timeout(self, deadline):
    # ...log NRR-019...
    if self.adapter and not self.shadow_mode:
        try:
            self.watchdog.cancel_attempt_count += 1
            cancel_result = await self.adapter.cancel_order(
                deadline.symbol, deadline.order_id
            )
            self.watchdog.cancel_success_count += 1
            LOG.info(f"✅ Cancelled timed-out order {deadline.order_id}: {cancel_result}")
        except Exception as e:
            LOG.warning(f"Failed to cancel timed-out order {deadline.order_id}: {e}")
```

**Root Cause**:
- `cancel_success_count` інкрементується **до того, як** біржа підтверджує скасування (await повертає `cancel_result`, але **не перевіряє** його статус).
- Якщо біржа повертає помилку (наприклад, `-2011 Unknown order`), exception **логується як warning**, але **не викликає rollback** або повторної спроби.
- OrderLogger **не пише** `ORDER_STATE_CHANGED` або `ORDER_CANCELLED` після спроби скасування → **втрата аудиту**.

### 1.2 Наслідки

- **Phantom fills**: Ордери, що вважаються скасованими, можуть виконатися на біржі через хвилини/години.
- **Дубльовані позиції**: Якщо watchdog скасував entry ордер, але він заповнився, система **не знає** про позицію → не розмістить TP/SL.
- **Exposure leaks**: Exposure guard резервує margin при розміщенні, але **не звільняє** його при timeout (fsm.py:844 не викликає `exposure_guard.release`).

### 1.3 Додаткові спостереження з логів

Усі ORDER_TIMEOUT у логах — це **fill_timeout** (ack_timeout_ms=8000, fill_ttl_ms=30000). Жодних ACK timeout не виявлено → біржа швидко підтверджує розміщення, але **не виконує** MARKET ордери (testnet може мати низьку ліквідність).

**Підтвердження**: У логах є 7+ ORDER_TIMEOUT для entry ордерів (SOLUSDT/ETHUSDT), але **немає подальших FILL** подій для цих `order_id`.

---

## 2. Проблема: Висячі TP/SL після fill'у (Orphaned Brackets)

### 2.1 Механізм OCO-емуляції (ManageFlowFSM)

**Код** (`apps/reference/domains/execution_position/fsm_manage.py:455-491`):

```python
def _handle_bracket_fill(self, msg: Message) -> Optional[Message]:
    """Handle SL/TP bracket fills and perform OCO emulation."""
    pld = msg.pld or {}
    order_id = pld.get("orderId")

    if not order_id:
        return None

    # Check if this is a bracket fill
    if order_id == self.sl_order_id:
        # SL filled - cancel TP (OCO emulation)
        decision = None
        if self.tp_order_id and self.config.get("brackets", {}).get("oco_emulation", False):
            decision = self._emit_cancel_order(msg, self.tp_order_id, "OCO_SL_filled")
        # Always clear the filled order from tracking
        self.sl_order_id = None
        return decision

    elif order_id == self.tp_order_id:
        # TP filled - cancel SL (OCO emulation)
        decision = None
        if self.sl_order_id and self.config.get("brackets", {}).get("oco_emulation", False):
            decision = self._emit_cancel_order(msg, self.sl_order_id, "OCO_TP_filled")
        # Always clear the filled order from tracking
        self.tp_order_id = None
        return decision

    return None
```

### 2.2 Умови спрацювання OCO

OCO-емуляція **спрацьовує тільки якщо**:
1. `msg.pld` містить `orderId` (string).
2. `orderId` збігається з `self.sl_order_id` або `self.tp_order_id`.
3. Конфіг `brackets.oco_emulation: true` (перевірено в `config/aurora/trading.yaml` — **присутнє**).
4. Інший bracket ID **не є None** (наприклад, `self.tp_order_id` існує, коли SL fill'иться).

**Потенційні причини невдачі OCO**:

#### A. Відсутність `orderId` у payload

**Приклад** із `ExecPosFSM.handle` (fsm.py:435-448):

```python
elif msg.verb in ["PARTIAL_FILL", "FILL", "TRADE_EXECUTED", "ORDER_UPDATED"]:
    manage_result = manage_flow.handle(msg)
    close_result = close_flow.handle(msg)
    result = manage_result if manage_result else close_result

    # EXP-FIX: Handle post-fill hold for FILLED orders
    if msg.verb == "FILL" and result:
        self._handle_fill_event(msg)
```

**Проблема**: `msg` передається до `manage_flow.handle(msg)` **як є**. Якщо **WebSocket event** від біржі має поле `o` (lowercase "o" для orderId), а не `orderId`, то `pld.get("orderId")` поверне `None` → OCO **не спрацює**.

**Підтвердження**: У BinanceAdapter (`vfoundation/adapters/binance_adapter.py`) WebSocket order update events мають структуру:
```python
{
  "e": "ORDER_TRADE_UPDATE",
  "o": {
    "s": "BTCUSDT",
    "i": 12345678,  # orderId
    "X": "FILLED",
    ...
  }
}
```

Поле `orderId` знаходиться у вкладеному об'єкті `o` → потрібне нормалізування перед передачею до FSM.

#### B. Невідповідність tracked ID

`self.sl_order_id` і `self.tp_order_id` встановлюються в `ExecPosFSM._execute_decision` (fsm.py:683, 705):

```python
# Track SL bracket per symbol
self._symbol_brackets.setdefault(symbol, {})["sl_order_id"] = sl_order_id
```

**Але** ManageFlowFSM **не отримує** цих ID безпосередньо. ManageFlowFSM має **власні** `self.sl_order_id`/`self.tp_order_id`, які встановлюються у `_place_brackets` (fsm_manage.py:280-307).

**Gap**: Якщо ExecPosFSM розмістив TP/SL **після** того, як ManageFlowFSM перейшов у стан `TRACKING`, то ManageFlowFSM **не знає** про ці ID → OCO **не спрацює**.

### 2.3 Сценарій висячого TP після SL fill'у

1. Entry MARKET order виконується → ManageFlowFSM отримує FILL → переходить у `BRACKETS_PENDING`.
2. ManageFlowFSM емітує `DEC:PLACE_ORDER` для SL/TP → ExecPosFSM викликає `adapter.place_stop_market_close_position` / `place_take_profit_market_close_position`.
3. Біржа підтверджує SL (orderId=X) і TP (orderId=Y).
4. ExecPosFSM зберігає `_symbol_brackets[symbol] = {"sl_order_id": "X", "tp_order_id": "Y"}`.
5. ManageFlowFSM отримує `ORDER_UPDATED` з `orderId=X` і `orderId=Y` → встановлює `self.sl_order_id = "X"`, `self.tp_order_id = "Y"` → переходить у `BRACKETS_PLACED`.
6. **SL спрацьовує** (ринкова ціна досягла SL) → біржа надсилає WebSocket event з `{"o": {"i": X, "X": "FILLED", ...}}`.
7. WebSocket aggregator емітує `EVT:ORDER_FILL` або `EVT:TRADE_EXECUTED` з `pld={...}`.
8. **Якщо** `pld["orderId"] != "X"` (неправильний маппінг поля) → ManageFlowFSM **не розпізнає** fill як SL → OCO **не спрацює** → TP залишається на біржі.
9. **Альтернативно**: Якщо ManageFlowFSM отримує FILL, але `self.sl_order_id` вже був очищений раніше (наприклад, через іншу подію) → порівняння `order_id == self.sl_order_id` не збігається → OCO **пропущено**.

### 2.4 Ручне закриття (Manual CLOSE)

**Код** (`fsm.py:498-541`):

```python
if decision.verb == "CLOSE":
    # Cancel tracked brackets
    br = self._symbol_brackets.get(symbol, {})
    tasks = []
    if br.get("sl_order_id"):
        tasks.append(self.adapter.cancel_order(symbol, br["sl_order_id"]))
    if br.get("tp_order_id"):
        tasks.append(self.adapter.cancel_order(symbol, br["tp_order_id"]))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    # Determine side/qty from current positions...
    await self.adapter.place_market_reduce_only(symbol, close_side, close_qty, ...)
    self._symbol_brackets.pop(symbol, None)
```

**Поведінка**:
- При `DEC:CLOSE` ExecPosFSM **скасовує** TP/SL з `_symbol_brackets` **перед** розміщенням reduce-only MARKET.
- Скасування виконується через `asyncio.gather(*tasks, return_exceptions=True)` → **навіть якщо** один cancel fail'иться, інші **виконуються**.
- **Але**: Немає перевірки статусу результатів `gather` → якщо біржа повертає помилку (наприклад, `-2011 Unknown order`), система **не дізнається**.

**Потенційна проблема**:
- Якщо ManageFlowFSM **не синхронізував** `_symbol_brackets` (наприклад, TP/SL були розміщені, але ID не збереглися), то `br.get("sl_order_id")` поверне `None` → скасування **пропущено**.

---

## 3. Проблема: Orphan Monitor неефективний

### 3.1 Поточна реалізація

**Код** (`fsm.py:1183-1260`):

```python
async def cleanup_orphaned_bracket_orders(self, symbol: Optional[str] = None) -> None:
    """Cancel reduceOnly/closePosition bracket orders when no position exists."""
    if not self.adapter:
        return
    try:
        positions = await self.adapter.get_open_positions()
        active = {p.get("symbol") for p in positions if p.get("symbol")}

        if symbol:
            symbols = [symbol]
        else:
            try:
                all_orders = await self.adapter.get_open_orders()
                symbols = sorted({o.get("symbol") for o in all_orders if o.get("symbol")})
            except Exception:
                symbols = []

        # [Controls: min_age, batch_limit, rate_limit...]

        for sym in symbols:
            if not sym or sym in active:
                continue
            try:
                open_orders = await self.adapter.get_open_orders(sym)
            except Exception as e:
                LOG.warning(f"cleanup: failed to fetch open orders for {sym}: {e}")
                continue
            for o in open_orders:
                otype = (o.get("type") or "").upper()
                reduce_only = str(o.get("reduceOnly", "")).lower() == "true"
                close_pos = str(o.get("closePosition", "")).lower() == "true"
                if otype in ("STOP_MARKET", "TAKE_PROFIT_MARKET", "LIMIT") and (reduce_only or close_pos):
                    # [Age/batch/rate filters...]
                    await self.adapter.cancel_order(sym, oid)
                    LOG.info(f"cleanup: cancelled orphaned order {oid} for {sym}")
```

**Тригери**:
1. **Startup**: `sync_open_orders_and_positions()` — якщо `orphan_cfg.run_on_startup: true` (fsm.py:164-168).
2. **Periodic**: `_cleanup_loop()` — кожні `periodic_interval_sec` секунд (fsm.py:1262-1277).
3. **On FILL**: `_on_order_fill` → `loop.create_task(self.cleanup_orphaned_bracket_orders(symbol))` (fsm.py:259).

### 3.2 Виявлені недоліки

#### A. Startup sync не гарантує cleanup

`sync_open_orders_and_positions` (fsm.py:1279-1324) виконує:
```python
for pos in positions:
    position_amt = float(pos.get("positionAmt", 0))
    if abs(position_amt) < 0.0001:
        # No position - cancel any orphaned orders for this symbol
        if symbol in orders_by_symbol:
            for order in orders_by_symbol[symbol]:
                try:
                    await self.adapter.cancel_order(symbol, order["orderId"])
```

**Проблема**:
- Перевіряє **лише позиції з `positionAmt=0`** → якщо біржа **не повертає** позиції з нульовим amount (Binance Futures зазвичай **не включає** такі позиції у `get_open_positions()`), то orphan cleanup **не виконується**.
- **Не викликає** `cleanup_orphaned_bracket_orders` напряму → логіка скасування **дублюється**.

#### B. Periodic loop не завжди активний

`_cleanup_loop` запускається в `__init__` (fsm.py:159-171):
```python
if not self.shadow_mode:
    self._initialize_adapter()
    self.watchdog.start()
    try:
        loop = asyncio.get_event_loop()
        if loop and not self._bg_started:
            # ...schedule tasks...
            self._bg_started = True
    except RuntimeError:
        # No running loop yet
        pass
```

**Проблема**:
- Якщо `asyncio.get_event_loop()` викликається **до** створення event loop (синхронний контекст __init__), то `RuntimeError` → loop **не запускається**.
- У тестах (shadow_mode=True або мокові адаптери) loop **взагалі не створюється** → метрики/поведінка orphan monitor **не тестуються**.

#### C. On-fill cleanup має race condition

`_on_order_fill` (fsm.py:251-259):
```python
try:
    loop = asyncio.get_event_loop()
    if loop:
        loop.create_task(self.cleanup_orphaned_bracket_orders(symbol))
except RuntimeError:
    pass
```

**Проблема**:
- Cleanup запускається **асинхронно** після fill → якщо fill закрив позицію **частково**, то `get_open_positions()` ще **має** цей символ → cleanup **пропустить** скасування.
- Cleanup викликається для **одного символа** → якщо fill був для entry ордера (не bracket), то cleanup **нічого не зробить** (brackets ще не розміщені).

#### D. Min-age filter може пропустити fresh orphans

Конфіг `min_order_age_sec: 0` (за замовчуванням) вимикає фільтр, але **якщо встановлено** (наприклад, 15-30 секунд), то:
- Brackets, розміщені **щойно** (< 15 сек), **не скасовуються**.
- Якщо позиція закрилась вручну **одразу після** розміщення brackets, то вони залишаться на біржі **на 15+ секунд**.

---

## 4. Тести vs Reality

### 4.1 Юніт-тести (test_orphaned_bracket_monitor.py)

**Існуючі тести**:
1. `test_cleanup_orphans_when_no_position_cancels_reduce_only_orders`
2. `test_cleanup_skips_when_position_exists`
3. `test_cleanup_only_target_symbol`
4. `test_sync_open_orders_and_positions_cancels_orphans_on_startup`
5. `test_cleanup_resilient_on_cancel_error`
6. `test_on_order_fill_schedules_best_effort_cleanup`

**Що тестується**:
- FakeAdapter з детермінованими позиціями/ордерами.
- Cleanup викликається **синхронно** через `await fsm.cleanup_orphaned_bracket_orders()`.
- Startup sync працює **якщо** `positions` містить записи з `positionAmt=0`.

**Що НЕ тестується**:
- **Real WebSocket events** з Binance (payload shape, поля `o.i` vs `orderId`).
- **Асинхронний lifecycle**: timeout watchdog + fill events + cleanup → реальні race conditions **не покриваються**.
- **Адаптер помилки**: якщо `cancel_order` fail'иться з `-2011`, чи система **повторить** спробу або **залишить** orphan?
- **Метрики**: чи `orphan_monitor.cancels` інкрементується **навіть якщо** біржа відхилила скасування?

### 4.2 Тести OCO (test_manage_flow_fsm_oco.py)

**Існуючі тести**:
1. `test_oco_sl_fills_cancels_tp`
2. `test_oco_tp_fills_cancels_sl`
3. `test_oco_disabled_no_cancel`
4. `test_oco_only_cancels_if_counterpart_exists`
5. ...

**Що тестується**:
- ManageFlowFSM отримує `EVT:FILL` з правильним `pld["orderId"]`.
- OCO емітує `DEC:CANCEL_ORDER` **якщо** конфіг ввімкнено.

**Що НЕ тестується**:
- **ExecPosFSM integration**: чи DEC:CANCEL_ORDER справді **викликає** `adapter.cancel_order`?
- **Biржевий відгук**: якщо біржа відхиляє скасування (наприклад, TP вже виконується), чи система **обробляє** це?
- **Payload mismatch**: якщо WebSocket event має `o.i` замість `orderId`, чи OCO **спрацює**?

---

## 5. Root Causes Summary

| # | Root Cause | Component | Severity |
|---|------------|-----------|----------|
| RC1 | Timeout cancellation **не перевіряє** відповідь біржі | OrderTimeoutWatchdog → ExecPosFSM._handle_order_timeout | 🔴 CRITICAL |
| RC2 | OrderLogger **не пише** CANCELLED/REJECTED після timeout cancel | ExecPosFSM._handle_order_timeout | 🟠 HIGH |
| RC3 | WebSocket payload **не нормалізований** (orderId у вкладеному об'єкті) | BinanceAdapter / WebSocketAggregator | 🔴 CRITICAL |
| RC4 | ManageFlowFSM OCO **не спрацьовує**, якщо orderId **не збігається** з tracked | ManageFlowFSM._handle_bracket_fill | 🔴 CRITICAL |
| RC5 | `_symbol_brackets` **не синхронізований** з ManageFlowFSM | ExecPosFSM._execute_decision → ManageFlowFSM | 🟠 HIGH |
| RC6 | `cleanup_orphaned_bracket_orders` **не викликається** на критичних івентах (manual CLOSE) | ExecPosFSM.handle | 🟠 HIGH |
| RC7 | Startup sync **не обробляє** символи без `positionAmt=0` в API відповіді | ExecPosFSM.sync_open_orders_and_positions | 🟡 MEDIUM |
| RC8 | Min-age filter **пропускає** fresh orphans (якщо ввімкнено) | ExecPosFSM.cleanup_orphaned_bracket_orders | 🟡 MEDIUM |
| RC9 | Тести **не покривають** real WebSocket payloads і адаптер помилки | test_orphaned_bracket_monitor.py, test_manage_flow_fsm_oco.py | 🟡 MEDIUM |

---

## 6. Рекомендації (без змін коду)

### 6.1 Негайні дії (Priority P0)

1. **Перевірити біржеві логи**:
   - Увійти до Binance Testnet UI → Orders history.
   - Знайти ордери з `orderId` із ORDER_TIMEOUT логів (наприклад, `1228002865`, `6702732634`).
   - Перевірити **фактичний статус**: CANCELED, FILLED, або NEW (active).
   - **Якщо NEW** → підтверджує RC1 (timeout cancel failed).

2. **Додати детальне логування cancel результатів**:
   - У `_handle_order_timeout` після `await adapter.cancel_order(...)` перевірити `cancel_result["status"]` → якщо **не "CANCELED"**, логувати **ERROR**.
   - Додати `order_logger.write({"event_type": "ORDER_CANCELLATION_FAILED", ...})`.

3. **Ввімкнути debug логування WebSocket events**:
   - У `BinanceAdapter` або `WebSocketAggregator` логувати **raw payload** кожної події → перевірити shape (чи є `orderId` на топ-рівні).

### 6.2 Короткострокові дії (Priority P1)

4. **Нормалізувати WebSocket payload**:
   - У `WebSocketAggregator` або `_parse_order_update` маппити `o.i` → `orderId`, `o.X` → `status` тощо.
   - Додати unit test з **raw Binance payload** → перевірити, що `orderId` правильно витягнуто.

5. **Синхронізувати `_symbol_brackets` з ManageFlowFSM**:
   - При розміщенні TP/SL у ExecPosFSM викликати `manage_flow.set_bracket_ids(sl_order_id, tp_order_id)`.
   - Додати метод у ManageFlowFSM для прямого оновлення tracked IDs.

6. **Викликати cleanup після manual CLOSE**:
   - У `_execute_decision(CLOSE)` після `place_market_reduce_only` викликати `await self.cleanup_orphaned_bracket_orders(symbol)` **з затримкою** (наприклад, 2 секунди) → гарантувати, що позиція закрилась.

7. **Виправити startup sync**:
   - У `sync_open_orders_and_positions` викликати `cleanup_orphaned_bracket_orders()` напряму замість дублювання логіки.
   - Не покладатися на `positionAmt=0` → сканувати **всі** ордери і порівнювати з **поточними** позиціями.

### 6.3 Довгострокові дії (Priority P2)

8. **Додати integration tests з real WebSocket mock**:
   - Використовувати fixtures з **реальними** Binance payload'ами (з документації API).
   - Тестувати повний lifecycle: place → ACK → FILL → OCO cancel → verify на біржі (mock).

9. **Імплементувати retry logic для cancel**:
   - Якщо `cancel_order` fail'иться з `-2011`, спробувати ще раз через 1-2 секунди.
   - Якщо ордер **справді не існує** (`-2011`), видалити з tracking → не вважати помилкою.

10. **Додати observability**:
    - Метрики: `orphan_monitor.cancel_failures`, `orphan_monitor.cancel_retries`.
    - Alerts: якщо `cancel_failures > 5` за хвилину → critical alert.

11. **Запровадити reconciliation loop**:
    - Кожні 5 хвилин порівнювати `_symbol_brackets` з **фактичними** ордерами на біржі.
    - Якщо знайдено розбіжність (tracked ID не існує на біржі), очистити tracking.

---

## 7. Висновки

### Підтверджені проблеми:
1. ✅ **Timeout-скасування не синхронізовані**: Ордери, що вважаються скасованими системою (NRR-019), можуть залишатися активними на біржі.
2. ✅ **Висячі TP/SL після fill'у**: OCO-емуляція не спрацьовує через:
   - Невідповідність payload shape (WebSocket `o.i` vs `orderId`).
   - Несинхронізовані ID між ExecPosFSM і ManageFlowFSM.
3. ✅ **Orphan Monitor неефективний**: Cleanup не викликається в критичні моменти (manual CLOSE, fill events має race conditions).

### Реальні наслідки:
- **Підтверджено логами**: 7+ ORDER_TIMEOUT для entry ордерів, жодного FILL для цих ID → підозра на phantom orders на біржі.
- **Ризик exposure leaks**: Якщо timeout cancel failed, позиція може відкритися несподівано → margin exposure не враховується.
- **Ризик подвійних TP/SL**: Якщо OCO не спрацьовує, обидва brackets залишаються активними → потенційно виконаються обидва (подвійний збиток).

### Рекомендована стратегія фіксу:
1. **Негайно**: Перевірити біржеві логи для ORDER_TIMEOUT ордерів → підтвердити фактичний статус.
2. **P0**: Нормалізувати WebSocket payload, синхронізувати `_symbol_brackets` з ManageFlowFSM.
3. **P1**: Додати retry/observability для cancel operations, викликати cleanup після manual CLOSE.
4. **P2**: Integration tests з real payloads, reconciliation loop.

---

**Статус**: Дослідження завершено. Код **не змінювався**. Рекомендації готові до імплементації.
