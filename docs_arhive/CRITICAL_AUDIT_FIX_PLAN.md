# 🔴 КРИТИЧНИЙ АУДИТ FIX_PLAN: Виявлені Ризики та Блокери

---
**HISTORICAL NOTE (2025-11-21 - EP-LEGACY-PURGE-S1)**

This document was written before legacy ExecPosFSM was removed.
ExecPosRuntimeV2 is now the only active execution runtime.
This document is preserved for historical context.

See: `docs/EXEC_POS_RUNTIME_STATE.md` for current state.
---

**Дата**: 2025-11-19
**Scope**: Аналіз FIX_PLAN_EXECUTION_POSITION_FSM.md перед імплементацією
**Мета**: Виявити потенційні помилки, які можуть з'явитися після застосування плану виправлень
**Результат**: **3 КРИТИЧНИХ РИЗИКИ** + **2 MODERATE RISKS** знайдено

---

## Executive Summary

⚠️ **УВАГА**: FIX_PLAN містить **3 реалізації, які призведуть до нових багів** якщо впроваджувати як є.

| Пункт Плану | Знайдений Ризик | Severity | Блокує Впровадження? |
|-------------|-----------------|----------|---------------------|
| 2.2 (_processed_events TTL) | ❌ Type mismatch - break equality checks | **CRITICAL** | **YES** |
| 2.2 (idempotency_store cleanup) | ❌ Race condition with sync handle() | **CRITICAL** | **YES** |
| 2.5 (Decimal unification) | ⚠️ Incompatible signatures at 20+ call sites | **HIGH** | Partial |
| 2.3 (Fire-and-forget wrapper) | ⚠️ Thread-safety not guaranteed | **MEDIUM** | No |
| 2.8 (Shutdown .clear()) | ✅ Safe if order preserved | **LOW** | No |

---

## 🔴 BLOCKER #1: _processed_events TTL Implementation

### Проблема в FIX_PLAN

**План каже (розділ 2.2):**
> "**TTL Cache / LRU:** Використати `vfoundation.utils.TTLCache` або періодичне очищення ключів старше 1 години."

**Приклад з DEEP_AUDIT_REPORT:**
```python
def _cleanup_old_events(self, max_age_sec: float = 300.0):
    # Store (event_key, timestamp) instead of plain string
    now = time.time()
    self._processed_events = {
        (key, ts) for key, ts in self._processed_events
        if now - ts < max_age_sec
    }
```

### Чому це ламає код

**Поточна реалізація (fsm.py lines 2238, 2297, 2386):**
```python
# Line 331: Initialization
self._processed_events: Set[str] = set()

# Line 2297: Usage
event_key = f"trade_executed_{idempotent_key}_{symbol}"
if event_key in self._processed_events:  # ← Expects string key
    return
self._processed_events.add(event_key)
```

**Після зміни на TTL (як в прикладі):**
```python
# Changed to Set[Tuple[str, float]]
self._processed_events: Set[Tuple[str, float]] = set()

# Line 2297: BREAKS!
event_key = f"trade_executed_{idempotent_key}_{symbol}"  # ← Still string
if event_key in self._processed_events:  # ← Will NEVER match tuples!
    return
self._processed_events.add(event_key)  # ← Type error: can't add str to Set[Tuple]
```

**Impact**:
- Ідемпотентність повністю зламана
- Дублікати подій не відфільтровуються
- Потенційні подвійні виконання трейдів

### Правильна Реалізація

**Варіант A: Окремий Dict (рекомендую)**
```python
# Line 331: Two separate structures
self._processed_events: Set[str] = set()
self._processed_events_ts: Dict[str, float] = {}  # key -> timestamp

# Line 2297: Keep existing logic
event_key = f"trade_executed_{idempotent_key}_{symbol}"
if event_key in self._processed_events:
    return
self._processed_events.add(event_key)
self._processed_events_ts[event_key] = time.time()  # Track timestamp

# Cleanup method (called periodically)
def _cleanup_old_events(self, max_age_sec: float = 3600.0):
    now = time.time()
    expired = [k for k, ts in self._processed_events_ts.items() if now - ts > max_age_sec]
    for key in expired:
        self._processed_events.discard(key)
        del self._processed_events_ts[key]
```

**Варіант B: Замінити Set на Dict (більше змін)**
```python
# Line 331: Change to Dict
self._processed_events: Dict[str, float] = {}  # key -> timestamp

# Lines 2238, 2297, 2386: Change all checks
event_key = f"trade_executed_{idempotent_key}_{symbol}"
if event_key in self._processed_events:  # Still works (dict __contains__)
    return
self._processed_events[event_key] = time.time()  # Changed from .add()

# Cleanup same as Variant A
```

---

## 🔴 BLOCKER #2: idempotency_store Race Condition

### Проблема в FIX_PLAN

**План каже (розділ 2.2):**
> "**Background Cleanup:** Додати очищення у `_cleanup_loop` незалежно від вхідних команд."

### Чому це створює race condition

**Поточна реалізація (fsm_open.py line 145):**
```python
def handle(self, msg: Message):  # ← SYNCHRONOUS method
    if msg.verb == "OPEN":
        self._cleanup_idempotency_store()  # ← Called inline, thread-safe

        idempotent_key = msg.pld.get("idempotent_key")
        if idempotent_key in self.idempotency_store:  # ← Check
            return self._reject(...)
        self.idempotency_store[idempotent_key] = time.time()  # ← Write
```

**Після переміщення в background _cleanup_loop:**
```python
# In ExecPosFSM (fsm.py) - runs in ASYNC event loop, different thread
async def _cleanup_loop(self):
    while True:
        await asyncio.sleep(60)
        # Iterate all flows and cleanup their idempotency_store
        for symbol, flow in self.open_flows.items():
            flow._cleanup_idempotency_store()  # ← Background thread deletes

# Meanwhile in OpenFlowFSM.handle() - SYNC method, main thread
def handle(self, msg: Message):
    if idempotent_key in self.idempotency_store:  # ← RACE: key deleted between check and use
        return self._reject(...)
```

**Race Scenario:**
1. Time T0: Main thread checks `key in store` → False (key exists)
2. Time T0+1ms: Background thread deletes key (expired TTL)
3. Time T0+2ms: Main thread tries `store[key]` → KeyError or wrong state

**Impact**:
- Duplicate CMD:OPEN може пройти перевірку
- Possible double position entries
- Corrupted idempotency tracking

### Правильна Реалізація

**Варіант A: Залишити cleanup в handle() (найпростіше, рекомендую)**
```python
def handle(self, msg: Message):
    # ALWAYS cleanup at start of handle(), not just for CMD:OPEN
    self._cleanup_idempotency_store()  # ← Thread-safe, same thread as checks

    if msg.verb == "OPEN":
        idempotent_key = msg.pld.get("idempotent_key")
        # ... rest of logic
```

**Варіант B: Add threading.Lock (складніше)**
```python
# In OpenFlowFSM.__init__
self._idempotency_lock = threading.Lock()

def _cleanup_idempotency_store(self):
    with self._idempotency_lock:  # ← Lock
        # ... cleanup logic

def handle(self, msg: Message):
    with self._idempotency_lock:  # ← Same lock
        if idempotent_key in self.idempotency_store:
            # ...
```

---

## ⚠️ HIGH RISK: Decimal Unification Incompatibility

### Проблема в FIX_PLAN

**План каже (розділ 2.5):**
> "Створити єдину утиліту `apps.reference.utils.decimal_utils.to_decimal`."

### Чому це складніше ніж здається

**Знайдено 5 різних сигнатур:**

| Функція | Сигнатура | Behavior on Error | Locations |
|---------|-----------|-------------------|-----------|
| `_as_decimal` | `(value) -> Optional[Decimal]` | Returns `None` | fsm.py (5 uses) |
| `_coerce_decimal` | `(value, default) -> Decimal` | Returns `default` | manage_config.py, brackets_config.py (10+ uses) |
| `_coerce_decimal_value` | `(value) -> Optional[Decimal]` | Returns `None` | fsm_manage.py (2 uses) |
| `_strict_coerce_decimal` | `(value, default) -> Decimal` | **Raises ValueError** | manage_config.py (1 use) |
| `_coerce_decimal` | `(value, fallback) -> Decimal` | Returns `fallback` | config_exposure_policy.py (5 uses) |

**Приклад несумісності:**

```python
# Current: brackets_config.py line 173
sl_fixed = _coerce_decimal(sl_fixed_raw)  # Returns None on error
if sl_fixed is None:
    # ... handle missing value

# If replaced with unified to_decimal() that raises:
sl_fixed = to_decimal(sl_fixed_raw)  # Raises on error
# ← Caller expects None check, now gets exception!
```

### Міграційний План (доповнення до FIX_PLAN)

**Крок 1: Створити to_decimal() з modes**
```python
# apps/reference/utils/decimal_utils.py
def to_decimal(
    value: Any,
    default: Optional[Decimal] = None,
    strict: bool = False
) -> Optional[Decimal]:
    """
    Unified decimal conversion.

    Args:
        value: Value to convert
        default: Return this if conversion fails (unless strict=True)
        strict: If True, raise ValueError on invalid input

    Returns:
        Decimal or default (or None if no default provided)

    Raises:
        ValueError: If strict=True and value is invalid
    """
    if value is None:
        if strict and default is None:
            raise ValueError("Cannot convert None to Decimal")
        return default

    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as e:
        if strict:
            raise ValueError(f"Invalid decimal value: {value}") from e
        return default
```

**Крок 2: Поступова міграція**
```python
# Replace _as_decimal:
-qty = _as_decimal(value)
+qty = to_decimal(value, default=None)

# Replace _coerce_decimal:
-sl_bps = _coerce_decimal(value, Decimal("10.0"))
+sl_bps = to_decimal(value, default=Decimal("10.0"))

# Replace _strict_coerce_decimal:
-target = _strict_coerce_decimal(value, Decimal("2.0"))
+target = to_decimal(value, default=Decimal("2.0"), strict=True)
```

**Крок 3: Regression testing**
- Unit test кожного call site з old vs new behavior
- Verify default values match expected

---

## ⚠️ MEDIUM RISK: Fire-and-Forget Task Wrapper Thread-Safety

### Проблема в FIX_PLAN

**План каже (розділ 2.3):**
```python
task = asyncio.create_task(coro)
self._background_tasks.add(task)
task.add_done_callback(self._background_tasks.discard)
```

### Потенційний Ризик

**Thread-safety в CPython**:
- `set.add()` and `set.discard()` are **not atomic** in Python spec
- CPython's GIL makes them *mostly* safe, but not guaranteed
- Other Python implementations (PyPy, Jython) may have issues

**Scenario:**
1. Task A completes → callback calls `discard(task_A)`
2. Task B completes → callback calls `discard(task_B)`
3. If both callbacks run simultaneously (different threads), `set` internal state may corrupt

### Правильна Реалізація

**Додати asyncio.Lock:**
```python
# In __init__
self._background_tasks: Set[asyncio.Task] = set()
self._background_tasks_lock = asyncio.Lock()

# In _submit_async
async def _add_task_safely(task):
    async with self._background_tasks_lock:
        self._background_tasks.add(task)

async def _remove_task_safely(task):
    async with self._background_tasks_lock:
        self._background_tasks.discard(task)

# When creating task
task = target_loop.create_task(coro_obj)
asyncio.create_task(_add_task_safely(task))  # Wrap in async context
task.add_done_callback(lambda t: asyncio.create_task(_remove_task_safely(t)))
```

**Альтернатива (простіше):** Використати `asyncio.gather()` або `asyncio.TaskGroup` (Python 3.11+)

---

## ✅ LOW RISK: Shutdown .clear() Order

### Аналіз FIX_PLAN

**План каже (розділ 2.8):**
```python
def shutdown(self):
    # ... existing cleanup ...
    self._close_position_state.clear()
    self._aggregated_bracket_buffer.clear()
    self._exec_error_history.clear()
    # ...
```

### Чому це SAFE

**Поточний порядок shutdown() (line 2509):**
1. `watchdog.stop()` - зупиняє background polling
2. `order_guardian.stop()` - зупиняє reconciliation loop
3. `_agg_watchdog_task.cancel()` - скасовує watchdog task
4. (Після цього можна безпечно `.clear()`)

**Ризик:** Якщо `.clear()` викликати **до** зупинки tasks, можлива race condition (task читає dict в момент clear).

**Рекомендація:** Додати `.clear()` в кінець shutdown(), after all tasks stopped.

---

## 📋 Оновлений FIX_PLAN Timeline

### Day 1: P0 + Critical Fixes
1. ✅ Fix `_handle_order_timeout` lambda (safe, 5 min)
2. ⚠️ **NEW**: Fix `_processed_events` implementation (використати Variant A з окремим Dict)
3. ⚠️ **NEW**: Fix `idempotency_store` cleanup strategy (залишити в handle() або add Lock)

### Day 2-3: Memory Leaks (REVISED)
1. Implement `_processed_events` TTL cleanup (з правильною структурою даних)
2. Add `maxlen` for `deque` structures
3. Cleanup для `_close_position_state`, `_aggregated_bracket_buffer`
4. Implement shutdown `.clear()` в правильному порядку

### Day 4: Decimal Unification (REVISED)
1. Create `to_decimal()` з modes (default, strict)
2. **NEW**: Incremental migration plan (не все одразу)
3. **NEW**: Regression tests для кожного call site
4. Update 5-10 highest risk call sites (brackets_config, manage_config)

### Day 5: Fire-and-Forget + Testing
1. Implement task wrapper з asyncio.Lock
2. **NEW**: Add regression tests для threading edge cases
3. Final integration testing

---

## 🎯 Критичні Рекомендації

### ПЕРЕД Початком Імплементації

1. **BLOCKER #1**: Вибрати варіант для `_processed_events` (Variant A або B)
2. **BLOCKER #2**: Вибрати варіант для `idempotency_store` (keep in handle або add Lock)
3. **HIGH RISK**: Створити migration plan для Decimal з testing matrix

### Під Час Імплементації

4. **P0 First**: Почати з lambda fix (safe, швидко)
5. **Test After Each**: Запускати тести після кожної зміни (не батч)
6. **Incremental**: Decimal unification робити поступово, не всі 20+ call sites одразу

### Після Імплементації

7. **Memory Monitoring**: Додати metrics для `len(_processed_events)`, `len(idempotency_store)`
8. **Load Testing**: Симуляція 10,000 events/minute протягом 1 години
9. **Regression**: Verify idempotency works (duplicate events filtered)

---

## 📊 Risk Matrix

| Issue | Likelihood | Impact | Risk Score | Mitigation Priority |
|-------|------------|--------|------------|---------------------|
| _processed_events type mismatch | **100%** | Critical | **10/10** | P0 - Fix before ANY other change |
| idempotency_store race | **80%** | High | **8/10** | P0 - Must decide strategy |
| Decimal incompatibility | **60%** | Medium | **6/10** | P1 - Incremental migration |
| Task wrapper thread-safety | **20%** | Medium | **4/10** | P2 - Add lock as precaution |
| Shutdown .clear() order | **10%** | Low | **2/10** | P2 - Document order |

---

## ✅ Фінальний Чеклист

Перед мерджем будь-якого коміту з FIX_PLAN перевірити:

- [ ] `_processed_events` structure підтримує існуючі `in` checks
- [ ] `idempotency_store` cleanup не має race conditions
- [ ] `to_decimal()` backward compatible з 20+ call sites
- [ ] Fire-and-forget wrapper використовує asyncio.Lock
- [ ] Shutdown `.clear()` після зупинки всіх tasks
- [ ] Unit tests покривають нові edge cases
- [ ] Memory leak tests проходять (10K events, stable RAM)
- [ ] Idempotency tests проходять (duplicates filtered)

---

## 💡 Висновок

**FIX_PLAN загалом добрий (9/10)**, але містить **3 критичні імплементаційні деталі**, які призведуть до нових багів якщо не виправити.

**Оновлений вердикт:** ⚠️ **CONDITIONAL APPROVAL**
- ✅ Approve після виправлення BLOCKER #1 та #2
- ⚠️ Decimal unification робити інкрементально
- ✅ Решта плану safe для впровадження

**Estimated Timeline:** 5 днів → **6-7 днів** (через додаткове тестування)
