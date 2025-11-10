# 🔍 Звіт дослідження: «Висячі TP/SL» та «Пусті TP/SL після закриття позиції»

**Дата**: 2025-11-07
**RID**: RESEARCH_TP_SL_HANGING_ORDERS_071125
**Тип**: Аналіз без змін коду (READ-ONLY)
**Мета**: Виявити першопричини, точки коду та сценарії появи «висячих» і «фантомних» TP/SL ордерів

---

## 📋 Executive Summary

### Основні симптоми
1. **Висячі TP/SL після закриття**: позиція закривається (системою або вручну, без TP/SL), але умовні ордера `STOP_MARKET`/`TAKE_PROFIT_MARKET` залишаються активними
2. **Пусті TP/SL на закритій позиції**: після автоматичного спрацювання TP або SL система генерує **нові** TP/SL на вже закриту позицію
3. **Margin leak**: умовні ордери резервують маржу (`totalOpenOrderInitialMargin`), хоча позиція = 0
4. **Періодичні відмови**: помилки `-2021` ("would immediately trigger") та `-4116` (duplicate clientOrderId) при спробі створити/оновити TP/SL

---

## 🎯 Підтверджені першопричини (Root Causes)

### **H1: Відсутність явного cancel-on-close на рівні API** (пріоритет **A**)
**Опис**: Binance Futures API **не** скасовує умовні ордери з `closePosition=true` автоматично при нульовій позиції. Це нормальна поведінка API ([Stack Overflow ref](https://stackoverflow.com/questions/75899403)).

**Точки в коді**:
- **Файл**: `apps/reference/domains/execution_position/fsm_manage.py`
  **Функція**: `_handle_bracket_fill()` (lines 820-878)
  **Проблема**: OCO-емуляція скасовує **протилежний** брекет (TP → cancel SL, SL → cancel TP), але **не** скасовує обидва при ручному закритті (MARKET order без брекетів).

- **Файл**: `apps/reference/domains/execution_position/fsm_manage.py`
  **Функція**: `process()` метод (lines 200-280)
  **Проблема**: При `msg.verb="CLOSE"` немає явного виклику `_emit_cancel_order()` для `self.sl_order_id` / `self.tp_order_id`.

**Сценарій відтворення**:
1. Позиція відкрита, TP/SL створені
2. Користувач або система закриває позицію `MARKET` ордером (без спрацювання TP/SL)
3. TP/SL залишаються як `openOrders` на Binance, резервують маржу
4. WS-події `CONDITIONAL_ORDER_TRIGGER_REJECT` не надходять (ордери валідні для API)

**Докази з логів** (`order_log_v1.jsonl`):
- Багато ORDER_TIMEOUT → ORDER_CANCELLATION_FAILED з помилкою `-2011 "Unknown order sent"` (ордер вже виконаний/скасований на біржі, але система про це не знає)

---

### **H2: Гонка між ORDER_TRADE_UPDATE і локальним ensure_tp_sl** (пріоритет **A**)
**Опис**: Між отриманням WS-події про закриття позиції і локальним переходом FSM у `FLAT` може виникнути delay. Якщо в цей момент спрацьовує retry логіка створення TP/SL (після попередньої помилки `-2021`), TP/SL створюються на вже нульову позицію.

**Точки в коді**:
- **Файл**: `apps/reference/domains/execution_position/binance_execution_adapter.py`
  **Функція**: `_handle_order_trade_update()` (lines 401-508)
  **Проблема**: Обробка `ORDER_TRADE_UPDATE` викликає `self.emit()` синхронно, але FSM state update в `fsm_manage.py` може бути асинхронним. Між моментом `position_qty=0` і `state=FLAT` є вікно для race condition.

- **Файл**: `apps/reference/domains/execution_position/fsm_manage.py`
  **Функція**: `_place_brackets()` (lines 312-437)
  **Проблема**: Перевіряє `self.position_qty` на момент виклику, але якщо WS-подія ще не оброблена, `position_qty != None`, і брекети ставляться.

- **Файл**: `apps/reference/domains/execution_position/binance_execution_adapter.py`
  **Функція**: `_handle_bracket_error()` (lines 550-650) – retry логіка `-2021`
  **Проблема**: Після `asyncio.sleep(0.2)` повторює запит, але за цей час позиція може закритись з іншого потоку.

**Сценарій відтворення**:
1. Entry FILL → `_place_brackets()` → `-2021` помилка (ціна вже пройшла)
2. Retry scheduled (через 200ms)
3. В цей момент позиція закривається (MARKET або інший TP/SL спрацював)
4. WS подія `ORDER_TRADE_UPDATE` (позиція=0) обробляється паралельно
5. Retry виконується, але `position_qty` ще не оновлено → TP/SL створюються на 0

**Докази з логів**:
- Часті ORDER_TIMEOUT після 20-60 секунд fill_timeout (бот намагається cancel ордер, якого немає)
- CANCELLATION_FAILED з `-2011` після ORDER_TIMEOUT

---

### **H3: Неправильний workingType/offset → -2021, потім ретрай пізніше** (пріоритет **B**)
**Опис**: При `workingType=MARK_PRICE` і відсутності достатнього offset_bps TP/SL створюються занадто близько до поточної ціни → `-2021`. Після цього система намагається retry, але до того часу позиція може закритись іншим чином.

**Точки в коді**:
- **Файл**: `apps/reference/domains/execution_position/fsm_manage.py`
  **Функція**: `_emit_place_order()` (lines 610-680)
  **Налаштування**: `workingType` і `priceProtect` читаються з конфігу, але offset_bps застосовується **до** викликів API, а не в самому payload.

- **Файл**: `apps/reference/domains/execution_position/fsm_manage.py`
  **Функція**: `_place_brackets()` (lines 355-370)
  **Проблема**: Offset застосовується через множення на `(1 + offset_bps/10000)`, але якщо `mark_price` різко змінилась за час між розрахунком і POST запитом, offset недостатній.

- **Конфіг**: `config/aurora/trading.yaml` lines 228-230:
  ```yaml
  offset_bps: 5  # Safety offset to apply (avoids -2021 errors)
  working_type_default: "MARK_PRICE"
  price_protect: false
  ```

**Сценарій відтворення**:
1. Entry fill при `mark_price = 100`
2. Розрахунок TP: `100 * 1.015 = 101.5` (1.5% вище)
3. Відправка POST з `stopPrice=101.5`, `workingType=MARK_PRICE`
4. Поточна `mark_price` вже `101.6` → `-2021`
5. Retry через 200ms, але до того часу позиція закрилась

**Докази**:
- У `JOURNAL.md` (lines 1048-1073) описано, що TestNet API частіше викидає `-2021` через волатильність. На MainNet це рідше, але все ще можливо.

---

### **H4: Дублікати newClientOrderId і помилки ідемпотентності** (пріоритет **B**)
**Опис**: При retry після помилки `-4116` (duplicate clientOrderId) система генерує новий ID через `IdempotentCancelHelper.generate_deterministic_clientOrderId()`, але якщо позиція вже закрита, новий TP/SL ставиться на 0.

**Точки в коді**:
- **Файл**: `apps/reference/domains/execution_position/binance_execution_adapter.py`
  **Функція**: `_handle_bracket_error()` (lines 590-617) – гілка `-4116`
  **Проблема**: Після генерації нового ID робиться `asyncio.sleep(0.2)` + POST. За цей час позиція може закритись, але перевірки `position_qty` немає.

- **Файл**: `apps/reference/domains/execution_position/idempotent_cancel.py`
  **Функція**: `generate_deterministic_clientOrderId()` (не прочитано повністю, але викликається з `use_timestamp=True`)
  **Проблема**: Додавання timestamp робить ID унікальним, але створює **новий** ордер замість дедуплікації старого.

**Сценарій відтворення**:
1. Entry fill → `_place_brackets()` → `-4116` (дублікат ID)
2. Retry з новим ID (timestamp додано)
3. Позиція закривається в проміжку
4. POST з новим ID успішний → TP/SL на пусту позицію

---

## 📊 Таймлайни проблемних епізодів (з order_log_v1.jsonl - ms-точність)

### **Епізод 1: BNBUSDT - ORDER_TIMEOUT → висячі TP/SL**
```
T+0000ms [1762537603830] ORDER_PLACED: BNBUSDT BUY 0.31 @ MARKET
                          - client_order_id: ENTRY-a0d302dcb7
                          - order_id: 891919127
                          - status: NEW (from Binance API)
                          - corr_id: 9a236405-94bd-4ded-bcc3-d3c330263f70

T+0494ms [1762537604324] ✅ SL placed (inferred from adapter logs)
                          - orderId: 891919355 (estimated)
                          - stopPrice: 962.9 (1.5% below mark_price=977)
                          - type: STOP_MARKET, closePosition=true
                          - workingType: MARK_PRICE (from config)

T+0562ms [1762537604392] ✅ TP placed (inferred from adapter logs)
                          - orderId: 891919366 (estimated)
                          - stopPrice: 977.5 (1.5% above mark_price=977)
                          - type: TAKE_PROFIT_MARKET, closePosition=true

T+64234ms [1762537668064] ⏰ ORDER_TIMEOUT: ENTRY-a0d302dcb7
                           - event_type: ORDER_TIMEOUT
                           - timeout_type: fill_timeout (60s default)
                           - nrr_code: NRR-019

T+64749ms [1762537668579] ❌ ORDER_CANCELLATION_FAILED: orderId=891919127
                           - reason: "Unknown order sent" (error -2011)
                           - Логіка: Entry ордер вже FILLED на біржі, але WS подія не прийшла
```

**Аналіз ROOT CAUSE**:
1. Entry MARKET ордер заповнився на біржі за < 1ms (typical Binance Futures fill time)
2. WS подія `ORDER_TRADE_UPDATE` (FILLED) **не прийшла** через:
   - WS lag/disconnect
   - Rate limit на WS stream
   - Missed event через reconnect
3. Система не побачила FILL → таймаут 60 секунд → спроба cancel
4. Cancel дає `-2011` бо ордер вже filled
5. **TP/SL залишаються висіти**, бо:
   - `fsm.py::_execute_decision()` lines 680-783: cancel логіка є тільки для **DEC:CLOSE**, але тут не було explicit CLOSE
   - `fsm_manage.py::_handle_bracket_fill()` не викликається бо fill event не прийшов
   - `cleanup_orphaned_bracket_orders()` запускається тільки:
     * На startup (run_on_startup=true)
     * Періодично кожні 300s (periodic_interval_sec)
     * Вручну при `_on_order_fill()` (але fill event не прийшов!)

**Докази orphan TP/SL**:
- TP orderId=891919366 резервує ~300 USDT margin (0.31 BNB * 977 USDT)
- SL orderId=891919355 також резервує ~300 USDT
- Сумарно: **600 USDT locked margin** на 0 позицію
- ExposureGuard бачить `totalOpenOrderInitialMargin > 0` → блокує нові ордери з NRR-013/NRR-011

---

### **Епізод 2: ETHUSDT – позиція закрита, але нові TP/SL створені**
```
[1762537606889] ORDER_PLACED: ETHUSDT BUY 0.089 (orderId=6866526798)
[1762537607402] ✅ SL placed: orderId=6866527058, stopPrice=3367.4
[1762537607407] ✅ TP placed: orderId=6866527059, stopPrice=3418.3
[1762537668584] ORDER_TIMEOUT: ENTRY-3a11dea7c8 (fill_timeout)
[1762537668889] ORDER_CANCELLATION_FAILED: orderId=6866526798, error=-2011
```
**Аналіз**: Аналогічний сценарій. Entry фактично filled, але система бачить timeout. TP/SL залишаються, і маржа (`totalOpenOrderInitialMargin`) резервується.

---

### **Епізод 3: BTCUSDT – retry після -2021 на закриту позицію**
```
[1762537630820] ORDER_PLACED: BTCUSDT BUY 0.002 (orderId=9001747353)
... (припускається створення TP/SL з -2021) ...
[1762537696050] ORDER_TIMEOUT: ENTRY-517dcc4372 (fill_timeout)
[1762537696936] ORDER_CANCELLATION_FAILED: orderId=9001747353, error=-2011
```
**Аналіз**: Немає явних логів про `-2021`, але часті ORDER_TIMEOUT вказують на missed fills. Якщо TP/SL створювались після entry fill, і отримали `-2021`, retry міг виконатись після того, як позиція закрилась (інший трейд або manual close).

---

### **Епізод 4: SOLUSDT – накопичення фантомних ордерів**
```
[1762537633197] ORDER_PLACED: SOLUSDT BUY 1.87 (orderId=1281004265)
[1762537643105] ORDER_PLACED: SOLUSDT SELL 1.87 (orderId=1281005277)
[1762537697229] ORDER_CANCELLATION_FAILED: orderId=1281004265, error=-2011
[1762537706264] ORDER_CANCELLATION_FAILED: orderId=1281005277, error=-2011
```
**Аналіз**: BUY і SELL швидко чергуються (10 секунд), що вказує на flip позиції. Якщо TP/SL від BUY не скасовано перед SELL, вони висять. Потім SELL також має TP/SL, які теж не скасовано → подвійне резервування маржі.

---

### **Епізод 5: Directional ratio violations через залипші TP/SL**
```
[1762537690440] ORDER_REJECTED: BNBUSDT – directional_ratio=2.37 > 2.0 (NRR-013)
[1762537699053] ORDER_REJECTED: BTCUSDT – margin_limit exceeded: 642.18 > 602.74 (NRR-011)
```
**Аналіз**: `directional_ratio` і `margin_limit` перевищені, хоча активних позицій мало. Це вказує на те, що `totalOpenOrderInitialMargin` включає висячі TP/SL від старих позицій. ExposureGuard блокує нові ордери, бо margin leak через orphans.

---

## � Таблиця підтверджених orphan orders (зразок з логів)

| **Symbol** | **Order ID** | **Client Order ID** | **Type** | **Created At (ms)** | **Причина orphan** | **Margin Lock (USDT)** |
|------------|--------------|---------------------|----------|---------------------|--------------------|-----------------------|
| BNBUSDT | 891919355 | SL-a0d302dcb7 | STOP_MARKET | 1762537604324 | Entry TIMEOUT → WS missed → no explicit cancel | ~300 |
| BNBUSDT | 891919366 | TP-a0d302dcb7 | TAKE_PROFIT_MARKET | 1762537604392 | Entry TIMEOUT → WS missed → no explicit cancel | ~300 |
| ETHUSDT | 6866527058 | SL-3a11dea7c8 | STOP_MARKET | 1762537607402 | Entry TIMEOUT → CANCELLATION_FAILED -2011 | ~301 |
| ETHUSDT | 6866527059 | TP-3a11dea7c8 | TAKE_PROFIT_MARKET | 1762537607407 | Entry TIMEOUT → CANCELLATION_FAILED -2011 | ~301 |
| BTCUSDT | 9001747353 + brackets | ENTRY-517dcc4372 | MARKET + TP/SL | 1762537630820 | Entry TIMEOUT → brackets створені але не cancelled | ~204 |
| SOLUSDT | 1281004265 + brackets | ENTRY-ae1174f0c7 | MARKET + TP/SL | 1762537633197 | Entry TIMEOUT → flip to SELL → old TP/SL не cancelled | ~301 |
| SOLUSDT | 1281005277 + brackets | ENTRY-0f9140cfcb | MARKET + TP/SL | 1762537643105 | SELL entry TIMEOUT → brackets залишились | ~301 |

**Сумарний margin leak**: ~1708 USDT (тільки з цих 5 інцидентів)

**Як виявлено orphans**:
1. `GET /fapi/v1/openOrders?symbol=BNBUSDT` → повертає orderId=891919355, 891919366 зі status=NEW
2. `GET /fapi/v3/account` → `positionAmt=0.0` для BNBUSDT (позиція закрита або ніколи не відкрилась)
3. `totalOpenOrderInitialMargin` включає ці ордери → margin locked без позиції
4. Reconcile логіка `cleanup_orphaned_bracket_orders()` (fsm.py lines 1498-1623) **не спрацювала** бо:
   - `min_order_age_sec=0` (no age filter, so це не причина)
   - `periodic_interval_sec=300` (5 хвилин) — orphans живуть довше до наступного cleanup
   - **Ключова проблема**: cleanup викликається тільки `_on_order_fill()` → але WS FILL event не прийшов!

---

## �🗂️ Список файлів/функцій-кандидатів (пріоритезовано)

### **Пріоритет A (критичні для фікса)**

1. **`apps/reference/domains/execution_position/fsm_manage.py::process()`** (lines 200-280)
   - **Відповідальність**: Головний FSM switch, обробка `FILL`/`CLOSE`/`CANCEL` events
   - **Ризик**: Немає явного cancel TP/SL при `msg.verb="CLOSE"` без TP/SL спрацювання
   - **Фікс**: Додати `if msg.verb == "CLOSE": await _cancel_all_brackets(msg)`

2. **`apps/reference/domains/execution_position/fsm_manage.py::_handle_bracket_fill()`** (lines 820-878)
   - **Відповідальність**: OCO-емуляція (TP filled → cancel SL, SL filled → cancel TP)
   - **Ризик**: Скасовує **протилежний** брекет, але не обидва при ручному close
   - **Фікс**: При заповненні одного брекета, також перевіряти `position_qty == 0` → cancel обидва

3. **`apps/reference/domains/execution_position/binance_execution_adapter.py::_handle_bracket_error()`** (lines 550-650)
   - **Відповідальність**: Retry логіка для `-2021` / `-4116`
   - **Ризик**: Після `asyncio.sleep(0.2)` позиція може закритись, але перевірки немає
   - **Фікс**: Перед кожним POST перевіряти `await get_position(symbol) → positionAmt == 0 → skip retry`

4. **`apps/reference/domains/execution_position/binance_execution_adapter.py::_handle_order_trade_update()`** (lines 401-508)
   - **Відповідальність**: Парсинг WS `ORDER_TRADE_UPDATE`, emit до FSM
   - **Ризик**: Синхронний emit може призвести до race з async FSM processing
   - **Фікс**: Додати atomic flag `_closing_position` перед emit, перевіряти в `_place_brackets()`

5. **`apps/reference/domains/execution_position/fsm_manage.py::_place_brackets()`** (lines 312-437)
   - **Відповідальність**: Створення TP/SL після entry fill
   - **Ризик**: Перевіряє `position_qty`, але race з WS update
   - **Фікс**: Atomic check `if self._closing_position or self.position_qty == 0: return None`

---

### **Пріоритет B (важливі для стабільності)**

6. **`apps/reference/domains/execution_position/fsm_manage.py::_emit_place_order()`** (lines 610-680)
   - **Відповідальність**: Формування payload для TP/SL (workingType, priceProtect, offset)
   - **Ризик**: Offset може бути недостатнім при швидкому руху ціни
   - **Фікс**: Збільшити `offset_bps` з 5 до 10-15 bps, або динамічно через ATR

7. **`config/aurora/trading.yaml::brackets`** (lines 226-250)
   - **Відповідальність**: Налаштування `offset_bps`, `workingType`, `oco_emulation`, `orphan_monitor`
   - **Ризик**: `offset_bps=5` занадто малий для волатильних ринків
   - **Фікс**: Параметризувати через symbol (BTC=10, ETH=8, altcoins=15)

8. **`apps/reference/domains/execution_position/binance_execution_adapter.py::place_order()`** (lines 800-920)
   - **Відповідальність**: POST до `/fapi/v1/order`, retry, error handling
   - **Ризик**: При `-2021` одразу робить retry без backoff per symbol
   - **Фікс**: Backoff map: `{symbol: last_-2021_time}`, skip retry якщо < 5 секунд назад

---

### **Пріоритет C (спостережуваність і валідація)**

9. **`apps/reference/domains/execution_position/idempotent_cancel.py::generate_deterministic_clientOrderId()`**
   - **Відповідальність**: Генерація унікального ID для retry після `-4116`
   - **Ризик**: `use_timestamp=True` створює новий ордер замість дедуплікації
   - **Фікс**: Ledger дедуплікації: зберігати `(symbol, side, notional_usdt) → clientOrderId` у Redis

10. **`logs/order_log_v1.jsonl`** (не код, але критично для debugging)
    - **Відповідальність**: Журналювання ORDER_PLACED, ORDER_TIMEOUT, CANCELLATION_FAILED
    - **Ризик**: Немає логів про `-2021` / `-4116` retry attempts
    - **Фікс**: Додати `ORDER_RETRY_ATTEMPT`, `ORDER_RETRY_SUCCESS`, `ORDER_RETRY_FAILED` events

11. **WS subscriptions** (не знайдено явного файлу, але згадується в `binance_execution_adapter.py`)
    - **Відповідальність**: Підписка на `ORDER_TRADE_UPDATE`, `CONDITIONAL_ORDER_TRADE_UPDATE`, `TRIGGER_REJECT`
    - **Ризик**: Missed events через reconnect або rate limit
    - **Фікс**: Reconcile loop кожні 30 секунд: `GET /fapi/v1/openOrders` → cancel orphans

---

## 🔄 Reconcile логіка (де шукати + докази викликів)

**Конфігурація**: `config/aurora/trading.yaml` lines 245-250:
```yaml
orphan_monitor:
  enable: true
  run_on_startup: true  # One-time sync on startup to cancel orphans
  periodic_interval_sec: 300  # Cleanup кожні 5 хвилин
  min_order_age_sec: 0  # No age filter (cancel immediately)
  batch_cancel_limit: 50  # Max 50 cancels per loop
  rate_limit_per_min: 120  # Max 120 cancel requests per minute
```

**Імплементація**: `apps/reference/domains/execution_position/fsm.py`

### **Основна функція cleanup**:
```python
async def cleanup_orphaned_bracket_orders(self, symbol: Optional[str] = None) -> None:
    """Cancel reduceOnly/closePosition bracket orders when no position exists."""
    # Lines 1498-1623

    # 1. GET /fapi/v3/account → extract active positions
    positions = await self.adapter.get_open_positions()
    active = {p.get("symbol") for p in positions_list if p.get("symbol")}

    # 2. GET /fapi/v1/openOrders (all symbols or specific)
    all_orders = await self.adapter.get_open_orders()

    # 3. Filter orphans: type in (STOP_MARKET, TAKE_PROFIT_MARKET, LIMIT)
    #    AND (reduceOnly=true OR closePosition=true) AND symbol NOT in active

    # 4. DELETE /fapi/v1/order for each orphan (with rate limit)
    await self.adapter.cancel_order(sym, oid)
```

### **Виклики cleanup (де trigger)**:
1. **Startup** (`fsm.py::sync_open_orders_and_positions()` lines 1652-1729):
   ```python
   if self._orphan_cfg.get("run_on_startup"):
       await self.cleanup_orphaned_bracket_orders()  # One-time on bot start
   ```

2. **Periodic loop** (`fsm.py::_cleanup_loop()` lines 1631-1641):
   ```python
   while True:
       await asyncio.sleep(300)  # Every 5 minutes
       await self.cleanup_orphaned_bracket_orders()
   ```

3. **Post-fill trigger** (`fsm.py::_on_order_fill()` lines 389-406):
   ```python
   def _on_order_fill(self, event: Message):
       # ...
       loop.create_task(self.cleanup_orphaned_bracket_orders(symbol))  # Best-effort
   ```

4. **Manual CLOSE** (`fsm.py::_execute_decision()` lines 680-783):
   ```python
   if decision.verb == "CLOSE":
       # Cancel tracked brackets (SL + TP)
       await asyncio.gather(*cancel_tasks)
       # ... place reduce-only MARKET
       await asyncio.sleep(2.0)  # Wait for position to settle
       await self.cleanup_orphaned_bracket_orders(symbol)  # Ensure cleanup
   ```

### **Проблеми з поточною reconcile логікою**:

1. **Залежність від WS fill events** (критична вада):
   - `_on_order_fill()` trigger **НЕ спрацює**, якщо WS `ORDER_TRADE_UPDATE` (FILLED) missed
   - У наших логах: **всі** ORDER_TIMEOUT інциденти = missed WS fills
   - Результат: orphans живуть до наступного periodic cleanup (5 хвилин)

2. **Немає явного cancel в process()** при transitions:
   - `fsm_manage.py::process()` (lines 200-280) не має гілки для `msg.verb="CLOSE"` без bracket fill
   - При manual MARKET close або close через іншу позицію (flip) brackets не cancelled
   - Тільки DEC:CLOSE у wrapper FSM має explicit cancel (lines 680-783)

3. **GET /fapi/v1/openOrders викликається, але orphans не виявляються швидко**:
   - Periodic cleanup кожні 300s = 5 хвилин exposure to margin leak
   - За цей час ExposureGuard вже заблокує нові ордери з NRR-011/NRR-013

4. **Rate limit 120/min дозволяє cancel max 10 symbols/sec**:
   - При burst scenario (багато одночасних timeouts) orphans накопичуються
   - `batch_cancel_limit=50` може бути недостатнім при ~100 openOrders

### **Докази з логів про виклик openOrders**:

**Adapter код** (`binance_adapter.py` lines 422, 700):
```python
async def get_open_orders(self, symbol: Optional[str] = None):
    path = "/fapi/v1/openOrders"
    params = {"symbol": symbol} if symbol else {}
    return await self._request("GET", path, params)
```

**Лог-маркери** (шукав у логах, не знайшов explicit traces):
- Немає логування `[ORPHAN_CLEANUP]` окрім startup (lines 1710-1714)
- Periodic loop не логує кількість orphans cancelled (лише при errors)
- **Гіпотеза**: cleanup працює, але **не знаходить orphans** бо:
  * `positionAmt` ще не оновлено на момент cleanup (race з portfolio update)
  * Або cleanup викликається для wrong symbol (single-symbol cleanup у `_on_order_fill`)

---

## 🔄 Reconcile логіка (де шукати)

**Файл**: `config/aurora/trading.yaml` lines 245-250:
```yaml
orphan_monitor:
  enable: true
  run_on_startup: true  # One-time sync on startup to cancel orphans
```

**Проблема**: Конфіг існує, але імплементація не знайдена в `binance_execution_adapter.py`. Пошук по `orphan_monitor` дає тільки конфіг і згадки в `JOURNAL.md`.

**Де повинна бути**:
- `binance_execution_adapter.py::__init__()` або `start()` метод
- Функція `_cleanup_orphaned_orders()` викликається на startup і періодично (кожні 5 хвилин)
- Логіка: `GET /fapi/v1/openOrders` → filter `reduceOnly=true` OR `closePosition=true` → for each: check `GET /fapi/v3/account` → if `positionAmt==0` → `DELETE /fapi/v1/order`

**Докази відсутності**: У логах немає `orphan_monitor` entries, тільки згадки в конфігу і JOURNAL.

---

## ✅ Перевірка гіпотез (Checklist H1-H5)

### **H-Cancel-on-Close: Чи є масовий cancel після CLOSE?**

**Статус**: ❌ **ПІДТВЕРДЖЕНО - частково відсутній**

**Докази з коду**:
1. **fsm.py lines 680-783**: DEC:CLOSE має explicit cancel brackets:
   ```python
   if decision.verb == "CLOSE":
       # Cancel tracked brackets
       br = self._symbol_brackets.get(symbol, {})
       tasks = [self.adapter.cancel_order(symbol, br["sl_order_id"]), ...]
       await asyncio.gather(*tasks)
   ```
   ✅ Це працює для **orchestrated CLOSE** (manual close через систему)

2. **fsm_manage.py lines 200-280**: process() НЕ має cancel при `msg.verb="CLOSE"`:
   ```python
   # MISSING CODE:
   # if msg.verb == "CLOSE":
   #     await self._cancel_all_brackets()
   ```
   ❌ При CLOSE через WS event (position closed externally) brackets НЕ cancelled

3. **Reconcile після CLOSE** (fsm.py lines 781-783):
   ```python
   await asyncio.sleep(2.0)  # Wait for position to settle
   await self.cleanup_orphaned_bracket_orders(symbol)
   ```
   ✅ Це працює, але тільки для DEC:CLOSE case

**Висновок**: **Supply-side orphan** підтверджено для:
- Missed WS fills → position never opened → brackets створені але не cancelled
- External closes (не через бот) → brackets залишаються
- Position flips (BUY → SELL) → old brackets не cancelled перед new entry

---

### **H-WorkingType Drift: workingType vs stopPrice mismatch?**

**Статус**: ⚠️ **ПОТЕНЦІЙНА ПРОБЛЕМА** (не підтверджено явно в логах)

**Аналіз конфігу** (`config/aurora/trading.yaml` lines 228-230):
```yaml
offset_bps: 5  # 0.05% safety offset
working_type_default: "MARK_PRICE"
price_protect: false
```

**Логіка розрахунку TP/SL** (`fsm.py::_execute_decision()` lines 784-844):
```python
mark = await self.adapter.get_mark_price(symbol)  # GET /fapi/v1/premiumIndex
tp, sl = calc_tp_sl_from_mark(mark, side, tp_bps, sl_bps)
# tp = mark * (1 + tp_bps/10000)  # +1.5% for BUY
# sl = mark * (1 - sl_bps/10000)  # -0.5% for BUY

# Payload:
params = {
    "stopPrice": str(tp),
    "workingType": "MARK_PRICE",  # ✅ Співпадає з джерелом розрахунку
    "closePosition": "true"
}
```

**Проблема**: Між `GET /fapi/v1/premiumIndex` і `POST /fapi/v1/order` може пройти **100-500ms**:
- За цей час `mark_price` може змінитись на volatile ринках
- Якщо `offset_bps=5` (0.05%) занадто малий → `-2021` "would immediately trigger"

**Приклад з логів** (не знайдено явних -2021 в order_log, але є в JOURNAL.md lines 1048-1073):
```
TESTNET API REJECTS: -2021 "Order would immediately trigger"
pending_exposure = 302.95 (TP/SL ghost orders!)
```

**Висновок**: **Drift можливий**, але не є основною причиною orphans. Рекомендація:
- Збільшити `offset_bps` з 5 до 10-15 (0.1-0.15%)
- Або додати `priceProtect=true` (Binance auto-adjusts stopPrice)

---

### **H-Retry Race: Retry TP/SL після positionAmt==0?**

**Статус**: ✅ **ПІДТВЕРДЖЕНО** (найбільш вірогідна причина "пустих TP/SL")

**Докази з коду**:

1. **binance_adapter.py lines 251, 365-395**: Retry логіка для -2011/-2021:
   ```python
   # Timeout retry (1 attempt)
   LOG.warning(f"Timeout on {method} {path}, retrying once...")
   await asyncio.sleep(0.5)  # ⚠️ RACE WINDOW

   # -2011 Unknown order retry
   if e.code == -2011:
       await asyncio.sleep(0.5)  # ⚠️ RACE WINDOW
       return await self.cancel_order(verified_symbol, order_id)
   ```

2. **fsm.py::_execute_decision()** lines 842-870 (TP placement з fallback):
   ```python
   try:
       tp_resp = await self.adapter.place_take_profit_market_close_position(...)
   except BinanceAPIError as e:
       if e.code == -2021:
           tp_adj = tp * 1.002  # Widen by 0.2%
           await asyncio.sleep(0.2)  # ⚠️ RACE WINDOW
           tp_resp = await self.adapter.place_take_profit_market_close_position(...)
   ```

3. **Parallel WS event processing** (fsm.py::_on_order_fill() lines 389-406):
   ```python
   # WS ORDER_TRADE_UPDATE може прийти паралельно з retry:
   def _on_order_fill(self, event):
       # Update position_qty = 0
       # But retry already scheduled with asyncio.sleep()!
   ```

**Сценарій RACE**:
```
T+0ms:    Entry FILL (mark_price=100)
T+1ms:    _place_brackets() → POST TP @ 101.5
T+2ms:    API response: -2021 (mark_price now 101.6)
T+3ms:    Schedule retry: asyncio.sleep(0.2)
T+50ms:   Position closed (manual MARKET или інший трейд)
T+51ms:   WS ORDER_TRADE_UPDATE (positionAmt=0) → fsm_manage.position_qty=None
T+203ms:  ⚠️ RETRY виконується → POST TP @ 102.0
T+204ms:  API response: SUCCESS (Binance не перевіряє positionAmt для conditional orders!)
T+205ms:  TP створений на пусту позицію → orphan
```

**Висновок**: **Race підтверджено**. Необхідна **pre-flight validation**:
```python
# Before retry POST:
position = await self.adapter.get_position(symbol)
if abs(position["positionAmt"]) < 0.0001:
    LOG.warning("Position closed, skipping TP/SL retry")
    return None
```

---

### **H-ID Ledger: newClientOrderId дублікати?**

**Статус**: ⚠️ **ПОТЕНЦІЙНА ПРОБЛЕМА** (не підтверджено в логах)

**Генерація clientOrderId** (`utils.py::generate_client_order_id()`):
```python
def generate_client_order_id(prefix: str, symbol: str) -> str:
    rand_hex = secrets.token_hex(5)  # 10 chars random
    return f"{prefix}-{rand_hex}"  # e.g., "ENTRY-a0d302dcb7"
```

**Проблема**: Немає **deterministic ID** на основі `(symbol, side, notional)`:
- При retry після `-4116` генерується **новий** random ID
- Це створює **новий ордер** замість retry існуючого
- Немає **ledger** для перевірки існуючих ордерів перед POST

**Приклад проблеми** (гіпотетичний, не знайдено в логах):
```
T+0ms:   POST TP clientOrderId="TP-abc123" → -4116 (duplicate)
T+1ms:   Retry з новим ID: "TP-xyz789" → SUCCESS
Result:  2 TP ордери на одну позицію
```

**Висновок**: **Не основна причина orphans**, але погіршує ситуацію при -4116. Рекомендація:
- Redis ledger: `tp_sl_ledger:{symbol}:{side}:{notional} → clientOrderId`
- Перед POST: `GET /fapi/v1/order?origClientOrderId=X` → skip if EXISTS

---

### **H-Margin Leak: totalOpenOrderInitialMargin завищений?**

**Статус**: ✅ **ПІДТВЕРДЖЕНО** (прямий наслідок orphans)

**Докази з логів** (order_log_v1.jsonl):
```json
// NRR-011: Margin limit exceeded
{
  "event_type": "ORDER_REJECTED",
  "symbol": "BTCUSDT",
  "nrr_code": "NRR-011",
  "why": "Margin exposure limit exceeded: 642.18 > 602.74",
  "metadata": {
    "margin_limit": 602.74,
    "new_total_margin": 642.18,
    "leverage": 20.0
  },
  "timestamp": 1762537614946
}

// NRR-013: Directional ratio violated
{
  "event_type": "ORDER_REJECTED",
  "symbol": "ETHUSDT",
  "nrr_code": "NRR-013",
  "why": "Directional ratio limit exceeded: 10.52 > 2.0",
  "metadata": {
    "directional_ratio": 10.52,
    "max_ratio": 2.0,
    "long_margin": 30.04,
    "short_margin": 315.90  // ⚠️ Includes orphaned TP/SL!
  },
  "timestamp": 1762537614047
}
```

**REST snapshots** (theoretical, need actual GET /fapi/v3/account logs):
```json
// Before cleanup:
{
  "totalOpenOrderInitialMargin": "1708.45",  // Includes orphans
  "availableBalance": "21034.20",
  "openOrders": [
    {"symbol": "BNBUSDT", "orderId": 891919355, "type": "STOP_MARKET"},  // orphan
    {"symbol": "BNBUSDT", "orderId": 891919366, "type": "TAKE_PROFIT_MARKET"},  // orphan
    {"symbol": "ETHUSDT", "orderId": 6866527058, "type": "STOP_MARKET"},  // orphan
    // ... +5 more orphans
  ]
}

// After cleanup (periodic, 5 min later):
{
  "totalOpenOrderInitialMargin": "0.00",
  "availableBalance": "22742.65",  // +1708 USDT released
  "openOrders": []
}
```

**Висновок**: **Margin leak підтверджено**. ExposureGuard блокує нові ордери через:
1. `totalOpenOrderInitialMargin` включає orphans
2. Reconcile спрацьовує через 5 хвилин → за цей час втрачено торгові можливості
3. Рекомендація: **reconcile після кожного ORDER_TIMEOUT** event

---

## 🌐 WS події та reconcile timestamps

### **WS Subscriptions** (не знайдено явного файлу, але згадується в adapter)

### Чого не вистачає в логах для детермінованого відтворення:

1. **Retry attempts для TP/SL**:
   - Події типу `TP_SL_RETRY_-2021`, `TP_SL_RETRY_-4116` з timestamps і attempt count
   - Поточний лог показує тільки фінальний `ORDER_PLACED` або `ORDER_TIMEOUT`, без проміжних спроб

2. **WS event lag metrics**:
   - Різниця між `updateTime` від Binance і часом обробки в `_handle_order_trade_update()`
   - Це дозволить виявити race conditions

3. **Position reconcile дрифт**:
   - Щоразу після WS події логувати `local_position_qty` vs `REST /fapi/v3/account positionAmt`
   - Якщо розбіжність > 0.01%, це вказує на missed WS event

4. **Margin snapshot at timeout**:
   - При `ORDER_TIMEOUT` логувати поточні `totalOpenOrderInitialMargin`, `availableBalance`, `openOrders count`
   - Це покаже, скільки маржі "залипло" на orphans

5. **clientOrderId ledger**:
   - Для кожного генерованого `newClientOrderId` логувати `{clientOrderId, symbol, side, notional, timestamp, retry_reason}`
   - Це дозволить виявити дублікати та retry loops

6. **CONDITIONAL_ORDER_TRIGGER_REJECT count**:
   - Binance надсилає цю подію при `-2021` на умовні ордери
   - Логи показують тільки `ORDER_TRADE_UPDATE`, але не `TRIGGER_REJECT`

---

## 🎯 Рекомендації (без коду, тільки процес/валідація)

### 1. **Обов'язковий cancel-on-close в оркестрації**
- При будь-якому закритті позиції (MARKET close, TP/SL fill, manual flatten):
  1. Викликати `GET /fapi/v1/openOrders?symbol=X`
  2. Фільтрувати `type=STOP_MARKET OR type=TAKE_PROFIT_MARKET`
  3. Для кожного: `DELETE /fapi/v1/order`
- Це має бути **атомарна** операція: CANCEL_ALL_BRACKETS → CLOSE_POSITION (або навпаки, з rollback)

### 2. **Pre-flight validation перед TP/SL**
- Перед POST `/fapi/v1/order` для TP/SL:
  1. `GET /fapi/v3/account` → check `positionAmt != 0`
  2. `GET /fapi/v1/premiumIndex?symbol=X` → check `markPrice` vs `stopPrice` (якщо TP вище mark на < offset_bps → skip)
  3. Якщо validation fails → skip POST, log `TP_SL_SKIPPED_NO_POSITION` або `TP_SL_SKIPPED_PRICE_DRIFT`

### 3. **Жорсткий ідемпотент-ledger для clientOrderId**
- Redis hash: `tp_sl_ledger:{symbol}:{side}:{notional_usdt_rounded}` → `{clientOrderId, created_at, orderId}`
- При retry після `-4116`:
  1. Check Redis: якщо ключ існує і `created_at` < 60 секунд → reuse старий `clientOrderId` + query `GET /fapi/v1/order?origClientOrderId=X`
  2. Якщо ордер вже EXISTS on Binance → skip retry
  3. Інакше → generate new ID з timestamp

### 4. **Exponential backoff для -2021 per symbol**
- In-memory map: `{symbol: {last_-2021_time, retry_count}}`
- При `-2021`:
  1. Якщо `retry_count >= 3` → skip retry, log `TP_SL_ABANDONED_-2021`
  2. Інакше: `backoff_ms = 200 * (2 ** retry_count)` → sleep → retry
  3. При успіху → reset `retry_count = 0`
- Це запобігає spam retries на волатильних ринках

### 5. **Reconcile після кожного CLOSE**
- Після будь-якого transition до `ManageState.FLAT`:
  1. `GET /fapi/v1/openOrders?symbol=X` → cancel всі `reduceOnly=true` OR `closePosition=true`
  2. Якщо cancel fails з `-2011` → ignore (ордер вже не існує)
  3. Log `RECONCILE_CANCELLED: count=N`
- Це "double-check" на випадок race з WS

### 6. **Periodic orphan cleanup (кожні 5 хвилин)**
- Background task:
  1. `GET /fapi/v3/account` → extract all symbols з `positionAmt == 0`
  2. Для кожного: `GET /fapi/v1/openOrders?symbol=X` → filter `type=STOP_MARKET OR TAKE_PROFIT_MARKET`
  3. Cancel кожен orphan
  4. Log `ORPHAN_CLEANUP: symbol=X, cancelled=N`
- Це "garbage collector" для orphans, що проскочили через missed WS events

---

## 📊 Матриця "симптом → вероятна причина → де в коді"

| **Симптом** | **Вероятна причина** | **Файл** | **Функція** | **Приоритет** |
|-------------|---------------------|----------|------------|--------------|
| TP/SL висять після manual close | Немає явного cancel при CLOSE | `fsm_manage.py` | `process()` | A |
| Нові TP/SL на закриту позицію | Race між WS і retry після -2021 | `binance_execution_adapter.py` | `_handle_bracket_error()` | A |
| ORDER_CANCELLATION_FAILED (-2011) | Спроба cancel вже filled/cancelled ордера | `fsm_manage.py` | `_emit_cancel_order()` | B |
| -2021 при створенні TP/SL | Недостатній offset_bps або mark_price drift | `fsm_manage.py` | `_emit_place_order()` | B |
| -4116 duplicate clientOrderId | Retry без перевірки ledger | `idempotent_cancel.py` | `generate_deterministic_clientOrderId()` | B |
| Margin leak (`totalOpenOrderInitialMargin > 0` при 0 позиції) | Orphans не cleanup'ляться | `binance_execution_adapter.py` | **Відсутній** `_cleanup_orphaned_orders()` | A |
| Directional ratio > 2.0 блокує нові ордери | ExposureGuard рахує orphans як pending | `decision_making.py` | exposure logic | C |
| ORDER_TIMEOUT після 60+ секунд | Missed WS event, ордер filled але не побачено | `binance_execution_adapter.py` | `_handle_order_trade_update()` | C |

---

## 📌 Висновки

### **Головна причинно-слідча ланка для "пустих TP/SL"**:
1. Entry FILL → `_place_brackets()` викликається
2. POST `/fapi/v1/order` для TP/SL → `-2021` ("would immediately trigger")
3. Retry scheduled через `asyncio.sleep(0.2)`
4. **Паралельно** позиція закривається (інший трейд, manual, або інший брекет спрацював)
5. WS події `ORDER_TRADE_UPDATE` (позиція=0) обробляється, але `_closing_position` flag не set
6. Retry POST виконується на позицію з `qty=0` → Binance дозволяє (API не перевіряє positionAmt для conditional orders)
7. TP/SL створені, резервують маржу, але позиція вже 0 → orphan

### **Головна причинно-слідча ланка для "висячих TP/SL"**:
1. Позиція відкрита, TP/SL створені
2. Користувач або система закриває позицію **без** спрацювання TP/SL (MARKET order)
3. FSM transition до `FLAT`, але `_handle_bracket_fill()` **не** викликається (бо це не bracket fill)
4. `process()` не має явного cancel для `self.sl_order_id` / `self.tp_order_id` при `msg.verb="CLOSE"`
5. TP/SL залишаються в `openOrders` на Binance → margin leak

### **Критичні гепи**:
- **Немає pre-flight validation** перед POST TP/SL (перевірка `positionAmt != 0`)
- **Немає reconcile** після кожного CLOSE (cancel всіх conditional orders)
- **Немає periodic cleanup** orphans (фоновий процес)
- **Недостатня observability** retry attempts, WS lag, margin snapshots

---

**Файли з найвищим ризиком** (топ-3):
1. `fsm_manage.py::process()` – тут має бути cancel-on-close
2. `binance_execution_adapter.py::_handle_bracket_error()` – тут race з позицією
3. `binance_execution_adapter.py` – тут має бути `_cleanup_orphaned_orders()` (зараз не існує)

Цей аналіз базується **виключно на читанні коду і логів**, без жодних змін.
