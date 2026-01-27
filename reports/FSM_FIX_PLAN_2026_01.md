# FSM.PY ПЛАН ВИПРАВЛЕНЬ (КРИТИЧНИЙ АНАЛІЗ)

**Дата**: 2026-01-26  
**Автор**: Copilot Agent  
**Scope**: `apps/reference/domains/execution_position/fsm.py`

---

## ПРЕАМБУЛА: АРХІТЕКТУРНІ ОБМЕЖЕННЯ

Перед тим як пропонувати фікси, зафіксуємо інваріанти системи:

### 1. Контрактні обмеження (verb_registry_v1.yaml)
```yaml
EVT:ORDER_FILL:    owner=execution_position, status=experimental
EVT:TRADE_EXECUTED: owner=position_tracking, status=active, schema=trade_executed_v1.json
```

**Важливо**: `TRADE_EXECUTED` - це офіційний event для fills, `ORDER_FILL` - experimental.

### 2. Архітектурні межі (ARCHITECTURE.md)
- **Async boundary**: `EVT:TRADE_INTENT_PROPOSED` → Execution FSM
- **Sync boundary**: Risk Gate blocks
- **Truth domain**: WAL + Position Tracking

### 3. Принцип fail-closed
Система використовує fail-closed семантику - відсутність даних/конфігурації = блокування, не дефолти.

---

## ФАЗА 1: ШВИДКІ БЕЗПЕЧНІ ФІКСИ (LOW RISK)

### FIX-1.1: Додати EVT:TRADE_EXECUTED listener (ADDITIVE)

**Проблема**: FSM слухає `EVT:ORDER_FILL` (L315), але ніхто його не емітить.

**Поточний стан**:
```python
# Line 315 - DEAD LISTENER
self.bus.listen("EVT:ORDER_FILL", self._on_order_fill)
```

**Workaround що існує** (L1880-1882):
```python
elif msg.verb == "TRADE_EXECUTED":
    self._on_order_fill(msg)  # Already works via handle()
```

**Пропозиція**: Додати другий listener (адитивно, не видаляти старий)

```python
# Line ~320 (після EVT:ORDER_FILL)
self.bus.listen("EVT:TRADE_EXECUTED", self._on_order_fill)
```

**Обґрунтування**:
1. ✅ Адитивна зміна - не ламає існуючий код
2. ✅ Якщо хтось емітне ORDER_FILL - працюватиме
3. ✅ TRADE_EXECUTED вже має schema в registry (active status)
4. ✅ Обидва шляхи (bus + handle()) тепер працюють

**Критика підходу**:
- ⚠️ Дублювання: `_on_order_fill` може викликатись двічі (bus + handle)
- **Mitigation**: `_on_order_fill` вже повинен мати idempotency (це P2-005)

**Ризик**: 🟢 LOW - адитивна зміна

---

### FIX-1.2: Idempotency в `_on_order_fill` ✅ ALREADY EXISTS

**Статус**: ✅ **ВЖЕ РЕАЛІЗОВАНО** (L1531-1534)

**Поточний код** (вже присутній):
```python
# 🔄 IDEMPOTENT: Check if this event was already processed
event_key = f"fill_{order_id}_{symbol}"
if not self._mark_processed_event(event_key):
    LOG.debug(f"[FILL] Skipping duplicate FILL for {symbol} order {order_id}")
    return
```

**Висновок**: FIX-1.2 НЕ ПОТРІБЕН - код вже ідемпотентний.
Це означає FIX-1.1 можна безпечно додавати - дублі будуть відфільтровані.

**Ризик**: N/A - не потребує змін

---

### FIX-1.3: Error callback для `_submit_async` (OBSERVABILITY)

**Проблема**: Async exceptions ковтаються мовчки (L781-800)

**Поточний код**:
```python
def _submit_async(self, coro, loop=None) -> None:
    if running_loop is target_loop:
        target_loop.create_task(coro)  # No callback!
    else:
        asyncio.run_coroutine_threadsafe(coro, target_loop)  # Future ignored!
```

**Пропозиція**:

```python
def _submit_async(
    self,
    coro: Coroutine[Any, Any, Any],
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> None:
    """Schedule coroutine on a target loop, thread-safe."""
    target_loop = loop or self._get_async_loop()
    if not target_loop:
        LOG.warning("[ASYNC] No loop available to schedule %r - TASK DROPPED", coro)
        return

    def _on_task_done(fut: asyncio.Future) -> None:
        """Log unhandled exceptions from async tasks."""
        try:
            fut.result()
        except asyncio.CancelledError:
            pass  # Normal cancellation
        except Exception as exc:
            LOG.error(
                "[ASYNC] Unhandled exception in async task: %s",
                exc,
                exc_info=True,
            )

    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if running_loop is target_loop:
        task = target_loop.create_task(coro)
        task.add_done_callback(_on_task_done)
    else:
        fut = asyncio.run_coroutine_threadsafe(coro, target_loop)
        fut.add_done_callback(_on_task_done)
```

**Обґрунтування**:
1. ✅ Exceptions тепер логуються на ERROR рівні
2. ✅ Не змінює behavior - тільки observability
3. ✅ `LOG.debug` → `LOG.warning` для missing loop (тепер видно в production)
4. ✅ Стандартний asyncio pattern

**Критика підходу**:
- ⚠️ Лише логування, не retry/recovery
- **Mitigation**: Це Phase 1 - observability first, recovery окремим етапом
- ⚠️ Callback може спрацювати в іншому потоці
- **Mitigation**: LOG thread-safe, метрики можна додати пізніше

**Ризик**: 🟢 LOW - observability only

---

### FIX-1.4: Type normalization для `_pending_brackets` (DEFENSIVE)

**Проблема**: Key зберігається як `str`, але lookup може бути з `int`

**Поточний код**:
```python
# L3051 - store as str
self._pending_brackets[str(entry_resp["orderId"])] = {...}

# L1595 - lookup without normalization
if order_id in self._pending_brackets:  # order_id could be int!
```

**Пропозиція** (L1595):
```python
# Normalize order_id to str for lookup
order_id_str = str(order_id) if order_id is not None else None
if order_id_str and order_id_str in self._pending_brackets:
    bracket_data = self._pending_brackets.pop(order_id_str)
```

**Обґрунтування**:
1. ✅ Консистентність з store path (L3051)
2. ✅ Exchange API часто повертає int, наш код очікує str

**Ризик**: 🟢 LOW

---

## ФАЗА 2: АРХІТЕКТУРНІ РІШЕННЯ (MEDIUM RISK)

### FIX-2.1: Persistence для `_pending_brackets` (ARCHITECTURAL)

**Проблема**: LIMIT entry brackets втрачаються при restart.

**Поточний стан**:
- `_pending_brackets` = in-memory dict
- `hydrate()` не відновлює цей стан

**ВАРІАНТИ РІШЕННЯ**:

#### Варіант A: WAL persistence (Recommended)

```python
# При записі в _pending_brackets (L3051)
self._pending_brackets[entry_order_id] = bracket_data
wal.write({
    "event": "PENDING_BRACKET_STORED",
    "order_id": entry_order_id,
    "data": bracket_data,
    "ts": get_clock().now_sec()
})

# При видаленні (L1596)
bracket_data = self._pending_brackets.pop(order_id)
wal.write({
    "event": "PENDING_BRACKET_CONSUMED",
    "order_id": order_id,
    "ts": get_clock().now_sec()
})

# В hydrate() - replay WAL
def hydrate(self, position_data):
    # Existing logic...
    self._restore_pending_brackets_from_wal()
```

**Плюси**:
- ✅ Узгоджено з існуючою WAL інфраструктурою
- ✅ Audit trail

**Мінуси**:
- ⚠️ WAL може накопичуватись
- ⚠️ Replay logic потребує тестування

#### Варіант B: REST reconciliation on startup

```python
async def _reconcile_pending_brackets_on_startup(self):
    """Query exchange for open LIMIT orders and rebuild pending brackets."""
    open_orders = await self.adapter.get_open_orders()
    for order in open_orders:
        if order["type"] == "LIMIT" and order["status"] == "NEW":
            # Check if we have TP/SL intent stored somewhere
            # Rebuild _pending_brackets entry
            pass
```

**Плюси**:
- ✅ Не потребує WAL
- ✅ Exchange = source of truth

**Мінуси**:
- ⚠️ Втрачаємо TP/SL параметри (не зберігаються на exchange)
- ⚠️ Потребує додаткового state для TP/SL

#### Варіант C: Hybrid (WAL + REST verification)

**Рекомендація**: Варіант A (WAL) для Phase 2, з REST verification як sanity check.

**Критика підходу**:
- ⚠️ Збільшує складність
- ⚠️ WAL format = новий contract
- **Mitigation**: Strict schema + version field

**Ризик**: 🟡 MEDIUM

---

### FIX-2.2: Dead code cleanup - EVT:ORDER_FILL listener

**ТІЛЬКИ ПІСЛЯ FIX-1.1 deployed та verified**

**Пропозиція**: Видалити мертвий listener

```python
# REMOVE Line 315:
# self.bus.listen("EVT:ORDER_FILL", self._on_order_fill)
```

**Критика підходу**:
- ⚠️ Якщо якийсь код все ж емітить ORDER_FILL - зламаємо
- **Mitigation**: Grep показав що ніхто не емітить

**Ризик**: 🟡 MEDIUM - потребує verification period

---

## ФАЗА 3: ДОВГОСТРОКОВІ ПОКРАЩЕННЯ (HIGH COMPLEXITY)

### FIX-3.1: `_pending_intent_data` TTL + cleanup

Потребує архітектурного review - можливо краще зберігати в WAL або Redis.

### FIX-3.2: `_supersede_queue` persistence

Аналогічно до FIX-2.1.

### FIX-3.3: Retry mechanism для `_submit_async`

Потребує circuit breaker pattern implementation.

---

## ПЛАН ТЕСТУВАННЯ

### Phase 1 Tests (для FIX-1.1 to FIX-1.4)

#### Test 1.1: EVT:TRADE_EXECUTED via bus triggers _on_order_fill

```python
def test_trade_executed_via_bus_triggers_on_order_fill():
    """Verify that EVT:TRADE_EXECUTED emitted via bus triggers _on_order_fill."""
    fsm = create_test_fsm()
    
    # Setup pending bracket
    fsm._pending_brackets["123456"] = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "sl": 49000,
        "tp": 51000,
    }
    
    # Emit via bus
    fsm.bus.emit("EVT:TRADE_EXECUTED", {
        "orderId": "123456",
        "symbol": "BTCUSDT",
        "quantity": 0.1,
        "price": 50000,
    }, why="test")
    
    # Verify bracket was consumed
    assert "123456" not in fsm._pending_brackets
```

#### Test 1.2: Idempotency in _on_order_fill

```python
def test_on_order_fill_idempotency():
    """Verify duplicate fills are ignored."""
    fsm = create_test_fsm()
    call_count = [0]
    
    original_place_brackets = fsm._place_deferred_brackets
    def counting_wrapper(*args):
        call_count[0] += 1
        return original_place_brackets(*args)
    fsm._place_deferred_brackets = counting_wrapper
    
    fill_event = Message(
        op="EVT", verb="TRADE_EXECUTED",
        pld={"orderId": "123", "symbol": "BTCUSDT"}
    )
    
    # Call twice
    fsm._on_order_fill(fill_event)
    fsm._on_order_fill(fill_event)
    
    # Should only process once
    assert call_count[0] <= 1
```

#### Test 1.3: _submit_async logs exceptions

```python
def test_submit_async_logs_exceptions(caplog):
    """Verify async exceptions are logged."""
    fsm = create_test_fsm()
    loop = asyncio.new_event_loop()
    fsm._async_loop = loop
    
    async def failing_coro():
        raise ValueError("Test exception")
    
    with caplog.at_level(logging.ERROR):
        fsm._submit_async(failing_coro(), loop)
        loop.run_until_complete(asyncio.sleep(0.1))
    
    assert "Test exception" in caplog.text
    assert "[ASYNC]" in caplog.text
```

#### Test 1.4: Type normalization in bracket lookup

```python
def test_pending_brackets_type_normalization():
    """Verify int orderId works with str-keyed dict."""
    fsm = create_test_fsm()
    
    # Store with str key
    fsm._pending_brackets["123456"] = {"symbol": "BTCUSDT"}
    
    # Lookup with int (simulating exchange response)
    fill_event = Message(
        op="EVT", verb="TRADE_EXECUTED",
        pld={"orderId": 123456, "symbol": "BTCUSDT"}  # int!
    )
    
    fsm._on_order_fill(fill_event)
    
    # Should have been consumed
    assert "123456" not in fsm._pending_brackets
```

### Regression Tests

```bash
# Run existing execution_position tests
pytest tests/domains/execution_position/ -v

# Run integration tests
pytest tests/integration/test_decision_to_execution_flow.py -v

# Run order guardian tests
pytest tests/order_guardian/ -v
```

---

## ROLLOUT PLAN

### Week 1: Phase 1 deployment
1. ~~Deploy FIX-1.2 (idempotency)~~ ✅ ALREADY EXISTS
2. Deploy FIX-1.3 (_submit_async logging)
3. Deploy FIX-1.4 (type normalization)
4. Deploy FIX-1.1 (TRADE_EXECUTED listener) - SAFE due to existing idempotency
5. Monitor logs for 24h

### Week 3: Phase 2 analysis
1. Analyze WAL patterns
2. Design persistence schema
3. Implement FIX-2.1

### Week 4+: Gradual rollout of Phase 2/3

---

## КРИТИКА ЗАГАЛЬНОГО ПІДХОДУ

### Що може піти не так?

1. **Подвійна обробка fills**
   - Risk: FIX-1.1 + existing handle() path = 2 calls
   - Mitigation: FIX-1.2 (idempotency) deployed FIRST

2. **Logging overhead**
   - Risk: FIX-1.3 adds callback overhead
   - Mitigation: Callback lightweight, only logs on exception

3. **Breaking existing tests**
   - Risk: Tests may mock ORDER_FILL, not TRADE_EXECUTED
   - Mitigation: Run full test suite before deploy

4. **WAL format changes (Phase 2)**
   - Risk: Breaking change for replay
   - Mitigation: Version field + migration

### Чому ці зміни безпечні?

1. **Адитивність**: FIX-1.1-1.4 не видаляють код, тільки додають
2. **Backward compatible**: Старі paths залишаються працювати
3. **Defensive**: Idempotency захищає від edge cases
4. **Observable**: Logging дозволяє виявити проблеми в production

### Альтернативи які відкинуто

1. **Повне видалення ORDER_FILL listener одразу**
   - Відкинуто: Занадто ризиковано без verification period

2. **Зміна watchdog/WS client на ORDER_FILL**
   - Відкинуто: TRADE_EXECUTED вже в registry як active, ORDER_FILL = experimental

3. **Redis замість WAL для brackets**
   - Відкинуто: Додає зовнішню залежність, WAL вже є

---

## ACCEPTANCE CRITERIA

### Phase 1 Complete When:
- [ ] All 4 fixes deployed
- [ ] Zero duplicate fill processing (logs clean)
- [ ] Zero unlogged async exceptions
- [ ] Existing tests pass
- [ ] 48h production monitoring clean

### Phase 2 Complete When:
- [ ] Pending brackets survive restart
- [ ] WAL replay tested with synthetic failures
- [ ] No orphan LIMIT orders without brackets

---

## APPENDIX: CODE LOCATIONS

| Fix | File | Lines | Type |
|-----|------|-------|------|
| FIX-1.1 | fsm.py | ~320 | Add listener |
| FIX-1.2 | fsm.py | 1512-1520 | Add check |
| FIX-1.3 | fsm.py | 781-800 | Replace method |
| FIX-1.4 | fsm.py | 1595 | Modify lookup |
| FIX-2.1 | fsm.py | 3051, 1596, hydrate | Multiple |

---

*Plan created: 2026-01-26*
