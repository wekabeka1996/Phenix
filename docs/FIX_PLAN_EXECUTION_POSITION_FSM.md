# План виправлення помилок та стабілізації Execution Position FSM

## 1. Вступ та Мета
Цей документ описує комплексний план виправлення критичних помилок, витоків пам'яті та архітектурних недоліків, виявлених під час аудиту домену `execution_position` (файли `fsm.py`, `fsm_manage.py`, `fsm_open.py`, `fsm_close.py`).

**Мета:** Забезпечити стабільність роботи системи в режимі 24/7, усунути ризики OOM (Out Of Memory), гарантувати коректну обробку асинхронних задач та уніфікувати роботу з даними.

---

## 2. Аналіз Проблем та Стратегія Виправлення

### 🔴 P0: Критичні помилки (Blocker)

#### 2.1. `AttributeError` при ініціалізації Watchdog
**Проблема:** У `fsm.py` при ініціалізації `OrderTimeoutWatchdog` передається посилання на `self._handle_order_timeout`, який на момент виконання `__init__` може бути ще не повністю зв'язаний або визначений у MRO, що викликає помилку при першому виклику.
**Рішення:** Використати пізнє зв'язування (late binding) через `lambda`.
**Логіка:**
```python
on_timeout_callback=lambda d: self._handle_order_timeout(d)
```
**Вплив:** Усуває runtime crash при старті FSM.

---

### 🟠 P1: Витоки пам'яті та Асинхронність (High Priority)

#### 2.2. Усунення 6 типів витоків пам'яті
**Проблема:** FSM накопичує дані про події та стани без механізму очищення. При високочастотній торгівлі це призведе до падіння процесу через 7-30 днів.

| Об'єкт | Причина витоку | Стратегія виправлення |
|--------|----------------|-----------------------|
| `_processed_events` (Set) | Нескінченне додавання ключів ідемпотентності | **⚠️ CRITICAL FIX:** Додати окремий Dict `_processed_events_ts: Dict[str, float]` для зберігання timestamps. Залишити існуючий `Set[str]` для перевірок `in`. Периодичне очищення старших 1 години через cleanup метод. **НЕ** змінювати тип Set на Tuple - це зламає 3 існуючі перевірки (lines 2238, 2297, 2386). |
| `idempotency_store` | Очищення тільки при `CMD:OPEN` | **⚠️ CRITICAL FIX:** **НЕ** переміщати cleanup в background `_cleanup_loop` (race condition з sync `handle()`). Натомість викликати `_cleanup_idempotency_store()` на **початку кожного** `handle()`, незалежно від verb. Альтернатива: додати `threading.Lock` навколо всіх операцій з `idempotency_store`. |
| `_close_position_state` | Записи залишаються після закриття | **Event-driven Cleanup:** Видаляти запис при переході FSM у стан `FLAT`. |
| `_aggregated_bracket_buffer` | Записи залишаються назавжди | **TTL + Cleanup:** Очищати при успішному виставленні брекетів або таймауті. |
| `_exec_error_history` | `deque` росте без обмежень | **Bounded Deque:** Встановити `maxlen=100` при ініціалізації. |
| `_autoheal_retry_counts` | Немає видалення старих лічильників | **Time-window Reset:** Скидати/видаляти лічильники, якщо `last_ts` > 1 година. |

**Вплив:** Стабілізація споживання RAM. Не впливає на контракти.

**⚠️ ВАЖЛИВО:** Два перші пункти містять критичні імплементаційні деталі, які можуть зламати існуючу логіку. Дивіться деталі в розділі "Детальна Реалізація".

#### 2.3. Керування Асинхронними Задачами (Fire-and-forget)
**Проблема:** Використання `create_task` без збереження посилання на задачу (lines 1371, 1384, 1409). Якщо задача впаде з помилкою, вона не буде залогована, а при shutdown вона не буде коректно зупинена.
**Рішення:**
1. Створити `self._background_tasks: Set[asyncio.Task] = set()` та `self._background_tasks_lock = asyncio.Lock()`.
2. Використати патерн "Safe Task Wrapper" з thread-safety:
   ```python
   async def _add_task_safely(self, task: asyncio.Task):
       async with self._background_tasks_lock:
           self._background_tasks.add(task)

   async def _remove_task_safely(self, task: asyncio.Task):
       async with self._background_tasks_lock:
           self._background_tasks.discard(task)

   def _log_task_exception(self, task: asyncio.Task):
       try:
           task.result()  # Raises if task failed
       except asyncio.CancelledError:
           pass
       except Exception as e:
           self.logger.error(f"Background task failed: {e}", exc_info=True)

   # When creating task:
   task = target_loop.create_task(coro_obj)
   asyncio.create_task(self._add_task_safely(task))
   task.add_done_callback(lambda t: asyncio.create_task(self._remove_task_safely(t)))
   task.add_done_callback(self._log_task_exception)
   ```
3. У методі `shutdown()` скасовувати всі задачі з сету.

**⚠️ Thread-Safety:** CPython's GIL не гарантує атомарність `set.add()`/`discard()`. Використовуємо `asyncio.Lock` для захисту.

**Вплив:** Гарантія чистого завершення роботи, видимість помилок у фонових процесах.

#### 2.4. Стратегія Блокування (Threading vs Asyncio Lock)
**Аналіз:** `fsm.py` використовує `threading.Lock` всередині синхронного методу `handle()`.
**Рішення:**
- **Зберегти `threading.Lock`**, оскільки `handle()` є синхронним методом, і перехід на `asyncio.Lock` вимагатиме зміни сигнатури на `async def handle()`, що порушить контракт FSM.
- **Оптимізація:** Переконатися, що код всередині блоку `with self._flows_lock:` виконується миттєво (тільки in-memory операції) і не містить I/O, щоб не блокувати Event Loop.

#### 2.5. Уніфікація Decimal Conversion (Підвищено до P1)
**Проблема:** Знайдено 5 різних реалізацій з **несумісними сигнатурами**:
- `_as_decimal(value) -> Optional[Decimal]` - Returns None on error (5 uses)
- `_coerce_decimal(value, default) -> Decimal` - Returns default on error (10+ uses)
- `_coerce_decimal_value(value) -> Optional[Decimal]` - Returns None (2 uses)
- `_strict_coerce_decimal(value, default) -> Decimal` - **Raises ValueError** (1 use)
- `_coerce_decimal(value, fallback) -> Decimal` - Returns fallback (5 uses in config_exposure_policy.py)

Це створює ризики неузгодженості даних (Data Consistency) - caller очікує None, але отримує exception.

**Рішення (Incremental Migration):**
1. Створити єдину утиліту `apps.reference.utils.decimal_utils.to_decimal` з modes:
   ```python
   def to_decimal(
       value: Any,
       default: Optional[Decimal] = None,
       strict: bool = False
   ) -> Optional[Decimal]:
       """
       Args:
           value: Value to convert
           default: Return this if conversion fails (unless strict=True)
           strict: If True, raise ValueError on invalid input
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
2. **Поступова міграція (5-10 call sites за раз):**
   - Phase 1: brackets_config.py, manage_config.py (highest risk)
   - Phase 2: fsm.py, fsm_manage.py
   - Phase 3: config_exposure_policy.py
3. **Regression testing кожного call site** перед мерджем.

**⚠️ ВАЖЛИВО:** НЕ замінювати всі 20+ call sites одночасно. Кожен caller має свої очікування щодо error handling.

**Вплив:** Передбачувана поведінка при математичних операціях, усунення плаваючих багів.

#### 2.6. Уніфікація Config Parsing (Підвищено до P1)
**Проблема:** Дублювання логіки доступу до вкладених ключів конфігу.
**Рішення:** Винести логіку в `vfoundation.config.utils`.

---

### 🟡 P2: Якість коду та Безпека (Medium Priority)

#### 2.7. Безпека Оновлення Стану (Optimistic Updates)
**Проблема:** `self.sl_price` встановлюється до успішного виконання API запиту.
**Рішення:** Патерн "Revert on Failure" або оновлення стану тільки після успішного `await`.

#### 2.8. Повне Очищення при Shutdown
**Проблема:** Метод `shutdown()` (line 2509) не очищає внутрішні структури даних після зупинки background tasks.
**Рішення:** Додати явне очищення всіх словників та буферів **після** зупинки watchdog/guardian:
```python
def shutdown(self):
    # Existing cleanup (watchdog, guardian, tasks)
    if hasattr(self, 'watchdog') and self.watchdog:
        self.watchdog.stop()
    if hasattr(self, 'order_guardian') and self.order_guardian:
        loop = self._get_async_loop()
        if loop:
            self._submit_async(self.order_guardian.stop(), loop)
    task = getattr(self, "_agg_watchdog_task", None)
    if task:
        self._agg_watchdog_task = None
        try:
            loop = self._get_async_loop()
            if loop and hasattr(loop, "call_soon_threadsafe"):
                loop.call_soon_threadsafe(task.cancel)
            else:
                task.cancel()
        except Exception:
            pass

    # ✅ NEW: Cancel all background tasks
    if hasattr(self, '_background_tasks'):
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
        self._background_tasks.clear()

    # ✅ NEW: Clear all memory structures AFTER tasks stopped
    if hasattr(self, '_close_position_state'):
        self._close_position_state.clear()
    if hasattr(self, '_aggregated_bracket_buffer'):
        self._aggregated_bracket_buffer.clear()
    if hasattr(self, '_exec_error_history'):
        self._exec_error_history.clear()
    if hasattr(self, '_autoheal_retry_counts'):
        self._autoheal_retry_counts.clear()
    if hasattr(self, '_livepos_rest_backoff_until'):
        self._livepos_rest_backoff_until.clear()
    if hasattr(self, '_processed_events'):
        self._processed_events.clear()
    if hasattr(self, '_processed_events_ts'):
        self._processed_events_ts.clear()

    self.logger.info("ExecPosFSM shutdown complete")
```

**⚠️ Критичний порядок:** Tasks мають бути зупинені **перед** `.clear()`, інакше race condition.

---

## 3. Детальна Реалізація Критичних Виправлень

### 3.1. `_processed_events` TTL Cleanup (BLOCKER #1)

**⚠️ КРИТИЧНО:** НЕ змінювати `Set[str]` на `Set[Tuple[str, float]]` - це зламає існуючі перевірки!

**Правильна реалізація:**
```python
# fsm.py line ~331: Initialization
self._processed_events: Set[str] = set()  # ← Keep as Set[str]
self._processed_events_ts: Dict[str, float] = {}  # ← NEW: Track timestamps separately

# fsm.py lines 2238, 2297, 2386: Keep existing logic unchanged
event_key = f"trade_executed_{idempotent_key}_{symbol}"
if event_key in self._processed_events:  # ← Still works with Set[str]
    return
self._processed_events.add(event_key)
self._processed_events_ts[event_key] = time.time()  # ← NEW: Track timestamp

# NEW: Cleanup method (called from _cleanup_loop every 5 minutes)
def _cleanup_old_processed_events(self, max_age_sec: float = 3600.0):
    """Remove processed events older than max_age_sec (default 1 hour)."""
    now = time.time()
    expired = [k for k, ts in self._processed_events_ts.items() if now - ts > max_age_sec]
    for key in expired:
        self._processed_events.discard(key)
        self._processed_events_ts.pop(key, None)
    if expired:
        self.logger.debug(f"Cleaned {len(expired)} old processed events")
```

**Додати виклик у _cleanup_loop:**
```python
async def _cleanup_loop(self):
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        try:
            self._cleanup_old_processed_events(max_age_sec=3600.0)
            # ... other cleanup
        except Exception as e:
            self.logger.error(f"Cleanup loop error: {e}")
```

---

### 3.2. `idempotency_store` Cleanup (BLOCKER #2)

**⚠️ КРИТИЧНО:** НЕ переміщати cleanup в async `_cleanup_loop` - race condition з sync `handle()`!

**Правильна реалізація (Варіант A - рекомендується):**
```python
# fsm_open.py line ~140: Change handle() to ALWAYS cleanup
def handle(self, msg: Message) -> Optional[Message]:
    # ✅ ALWAYS cleanup at start, not just for CMD:OPEN
    self._cleanup_idempotency_store()

    if msg.op == "CMD" and msg.verb == "OPEN":
        # ... rest of logic
        idempotent_key = msg.pld.get("idempotent_key")
        if idempotent_key:
            if idempotent_key in self.idempotency_store:
                return self._reject(msg, "IDEMPOTENCY_FAIL", "duplicate command")
            self.idempotency_store[idempotent_key] = time.time()
        # ...
```

**Альтернатива (Варіант B - якщо потрібен background cleanup):**
```python
# fsm_open.py: Add lock
def __init__(...):
    # ...
    self._idempotency_lock = threading.Lock()

def _cleanup_idempotency_store(self):
    with self._idempotency_lock:
        now = time.time()
        expired = [k for k, ts in self.idempotency_store.items()
                   if now - ts > self.idempotency_window_sec]
        for key in expired:
            del self.idempotency_store[key]

def handle(self, msg: Message):
    if msg.op == "CMD" and msg.verb == "OPEN":
        with self._idempotency_lock:
            if idempotent_key in self.idempotency_store:
                return self._reject(...)
            self.idempotency_store[idempotent_key] = time.time()
```

**Рекомендація:** Використати Варіант A (простіше, без lock overhead).

---

## 4. План Реалізації (Оновлений Timeline)

### Фаза 1: P0 та Критичні Фікси (Day 1)
1. ✅ **Fix P0:** `AttributeError` у `fsm.py` (lambda binding) - 5 хвилин
2. ⚠️ **BLOCKER #1:** Fix `_processed_events` (додати `_processed_events_ts` Dict) - 30 хвилин
3. ⚠️ **BLOCKER #2:** Fix `idempotency_store` (cleanup в handle або add Lock) - 20 хвилин
4. ✅ **Unit tests** для обох блокерів - 1 година

### Фаза 2: Fire-and-Forget та Shutdown (Day 2)
1. **Fix P1 (Tasks):** Впровадження `_background_tasks` set з asyncio.Lock - 1.5 години
2. **Shutdown cleanup:** Додати `.clear()` для всіх dicts після task cancellation - 30 хвилин
3. **Review Lock:** Перевірка критичних секцій під `threading.Lock` - 30 хвилин
4. **Integration tests** - 1 година

### Фаза 3: Memory Leaks (Day 3)
1. Додавання `maxlen=100` для `_exec_error_history` deque - 10 хвилин
2. Cleanup для `_close_position_state` (event-driven) - 30 хвилин
3. Cleanup для `_aggregated_bracket_buffer` (TTL) - 45 хвилин
4. Time-window reset для `_autoheal_retry_counts` - 30 хвилин
5. **Memory leak tests** (10K events) - 1 година

### Фаза 4: Decimal Unification (Day 4-5)
1. Створення `apps.reference.utils.decimal_utils.to_decimal` з modes - 1 година
2. **Phase 1 migration:** brackets_config.py, manage_config.py (5 call sites) - 2 години
   - Regression tests для кожного call site
3. **Phase 2 migration:** fsm.py, fsm_manage.py (10 call sites) - 3 години
   - Regression tests
4. **Phase 3 migration:** config_exposure_policy.py (5 call sites) - 2 години
   - Final integration tests

### Фаза 5: Config Parsing + Edge Cases (Day 6)
1. Рефакторинг Config Parsing → `vfoundation.config.utils` - 2 години
2. Виправлення оптимістичних оновлень стану (P2) - 2 години
3. **Final integration testing** - 2 години
4. **Load testing** (100 msg/sec, 1 hour) - 1 година

**Оновлений Timeline:** 5 днів → **6 днів** (через критичні фікси та додаткове тестування)

---

## 5. Критерії Прийомки (Testing & Verification)

Для кожного виправлення мають бути створені або оновлені тести:

### 5.1. Critical Path Tests (MUST PASS)

1. **_processed_events Structure Test:**
   ```python
   def test_processed_events_backwards_compatibility():
       fsm = ExecPosFSM(...)
       # Verify Set[str] still works
       event_key = "trade_executed_key123_BTCUSDT"
       assert event_key not in fsm._processed_events
       fsm._processed_events.add(event_key)
       assert event_key in fsm._processed_events  # ← Must still work
   ```

2. **Idempotency Race Condition Test:**
   ```python
   def test_idempotency_no_race():
       flow = OpenFlowFSM(...)
       # Simulate concurrent access
       import threading
       def add_key():
           flow.idempotency_store["test"] = time.time()
       def cleanup():
           flow._cleanup_idempotency_store()

       threads = [threading.Thread(target=add_key),
                  threading.Thread(target=cleanup)]
       for t in threads:
           t.start()
       for t in threads:
           t.join()
       # Should not crash or corrupt store
   ```

3. **Memory Leak Test:**
   - Запустити цикл з 10,000 подій `TRADE_EXECUTED`.
   - Перевірити, що `len(_processed_events)` < 1000 після cleanup.
   - Verify `len(_processed_events_ts)` matches `len(_processed_events)`.

4. **Decimal Compatibility Test:**
   ```python
   def test_decimal_migration_compatibility():
       # Test each migrated call site
       from apps.reference.utils.decimal_utils import to_decimal

       # Old: _as_decimal returns None
       assert to_decimal(None) is None
       assert to_decimal("invalid") is None

       # Old: _coerce_decimal returns default
       assert to_decimal("invalid", Decimal("10")) == Decimal("10")

       # Old: _strict_coerce_decimal raises
       with pytest.raises(ValueError):
           to_decimal("invalid", strict=True)
   ```

### 5.2. Integration Tests

5. **Async Lock Test:**
   - Перевірити, що `handle()` з `threading.Lock` не блокує Event Loop.
   - Використати `asyncio.sleep` всередині critical section у тесті.

6. **Fire-and-Forget Task Test:**
   ```python
   async def test_background_tasks_tracked():
       fsm = ExecPosFSM(...)
       initial_count = len(fsm._background_tasks)

       # Create background task
       async def dummy():
           await asyncio.sleep(0.1)
       fsm._submit_async(dummy(), loop)

       # Verify task tracked
       assert len(fsm._background_tasks) > initial_count

       # Wait for completion
       await asyncio.sleep(0.2)

       # Verify cleanup via done_callback
       assert len(fsm._background_tasks) == initial_count
   ```

7. **Shutdown Test:**
   ```python
   def test_shutdown_cleanup():
       fsm = ExecPosFSM(...)
       # Add data to structures
       fsm._processed_events.add("test")
       fsm._close_position_state["BTCUSDT"] = {}

       fsm.shutdown()

       # Verify all cleared
       assert len(fsm._processed_events) == 0
       assert len(fsm._close_position_state) == 0
       # Verify no pending tasks
       loop = fsm._get_async_loop()
       if loop:
           pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
           assert len(pending) == 0
   ```

### 5.3. Load Tests

8. **High-Frequency Trading Simulation:**
   - 100 messages/second протягом 1 години
   - Verify memory growth < 50MB
   - Verify `_processed_events` size stable (< 1000)
   - Verify no task leaks (background_tasks size stable)

9. **Long-Running Idle Test:**
   - Hold position open for 24h without new CMD:OPEN
   - Verify `idempotency_store` cleaned (if using Variant A)
   - Verify no memory leaks in any Dict/Set structure

## 6. Вплив на Інші Модулі

- **Контракти:** Змін у зовнішніх контрактах (JSON Schema) не передбачається.
- **Адаптери:** Змін в адаптерах не потрібно, але FSM стане більш стійким до помилок адаптерів.
- **Моніторинг:** Додадуться нові метрики:
  - `fsm_processed_events_size` - поточний розмір Set
  - `fsm_processed_events_cleanup_count` - кількість cleanup операцій
  - `fsm_background_tasks_active` - кількість активних фонових задач
  - `fsm_idempotency_store_size` - розмір idempotency store
  - `fsm_memory_structures_total_size` - сумарний розмір всіх Dict/Set
- **Тестування:** Додано 9 нових тестів (3 critical path, 4 integration, 2 load tests).

---

## 7. Ризики та Мітігації

| Ризик | Ймовірність | Вплив | Мітігація |
|-------|-------------|-------|-----------|
| Type mismatch в `_processed_events` після TTL | HIGH | CRITICAL | ✅ Використати окремий Dict для timestamps |
| Race condition в `idempotency_store` | MEDIUM | HIGH | ✅ Cleanup в sync handle() або add Lock |
| Breaking changes при Decimal migration | MEDIUM | MEDIUM | ✅ Incremental migration + regression tests |
| Thread-safety issues в task wrapper | LOW | MEDIUM | ✅ asyncio.Lock навколо set operations |
| Shutdown order issues | LOW | LOW | ✅ Document порядок: tasks → .clear() |

---

## 8. Rollback Plan

У разі критичних проблем після деплою:

1. **P0 Lambda Fix:** Rollback trivial (remove lambda, restore direct ref) - НЕ рекомендується, це виправляє баг.
2. **_processed_events:** Rollback remove `_processed_events_ts` Dict and cleanup call - низький ризик.
3. **idempotency_store:** Rollback to cleanup only in CMD:OPEN - середній ризик (memory leak returns).
4. **Fire-and-forget tasks:** Rollback remove `_background_tasks` set - низький ризик (втрата visibility).
5. **Decimal unification:** Rollback incrementally per call site - низький ризик завдяки incremental approach.

**Критичні індикатори для rollback:**
- Memory growth > 100MB/hour
- Idempotency failures (duplicate trades)
- Task leak (background_tasks > 50)
- Decimal conversion errors in logs > 10/minute

---

## 9. Checklist Перед Merge

- [ ] ✅ P0 lambda fix applied та протестовано
- [ ] ⚠️ BLOCKER #1: `_processed_events_ts` Dict додано, existing checks не зламані
- [ ] ⚠️ BLOCKER #2: `idempotency_store` cleanup strategy обрано (Variant A or B)
- [ ] ✅ Fire-and-forget wrapper з asyncio.Lock реалізовано
- [ ] ✅ Shutdown `.clear()` після task cancellation
- [ ] ✅ Decimal `to_decimal()` створено з modes
- [ ] ⚠️ Phase 1 Decimal migration (5 call sites) + regression tests
- [ ] ✅ Unit tests: 3 critical path tests проходять
- [ ] ✅ Integration tests: 4 tests проходять
- [ ] ✅ Load tests: 2 scenarios (high-freq + idle) проходять
- [ ] ✅ Memory leak verification: growth < 50MB/hour
- [ ] ✅ Code review з фокусом на race conditions
- [ ] ✅ Documentation updated (metrics, rollback plan)

**Estimated Total Time:** 6 робочих днів (48 годин розробки + тестування)
