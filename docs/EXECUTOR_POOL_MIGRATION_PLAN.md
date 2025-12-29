# План міграції на ExecutorPool Architecture

**Дата:** 2025-11-29
**Автор:** Copilot
**Статус:** Draft

---

## 📋 Зміст

1. [Поточна архітектура](#1-поточна-архітектура)
2. [Цільова архітектура](#2-цільова-архітектура)
3. [Файли для видалення/заміни](#3-файли-для-видаленнязаміни)
4. [Файли для модифікації](#4-файли-для-модифікації)
5. [План міграції по фазах](#5-план-міграції-по-фазах)
6. [Тести](#6-тести)
7. [Rollback план](#7-rollback-план)

---

## 1. Поточна архітектура

### 1.1 Потік даних (поточний)

```
┌──────────────────────────────────────────────────────────────────────┐
│                         DecisionMaking                                │
│  - QoS rate limiting per symbol                                       │
│  - Deferred scheduler for retries                                     │
│  - Emits EVT:TRADE_INTENT_PROPOSED                                    │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     V2RuntimeFacade                                   │
│  - Maps legacy messages to RuntimeEvent                               │
│  - Per-symbol throttle (_pending_symbols)                             │
│  - Async callback for pending status clearing                         │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    ExecPosRuntimeV2                                   │
│  - SyncOrderExecutor (SINGLE instance for ALL symbols)                │
│  - ExecutionService (async fallback)                                  │
│  - BracketService (complex state reconstruction)                      │
│  - Gatekeeper, WAL, Exposure Bridge                                   │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      SyncOrderExecutor                                │
│  - ONE executor for ALL symbols                                       │
│  - Blocking when busy (rejects other symbols)                         │
│  - Uses quantity in brackets (needs recalculation)                    │
│  - Complex bracket calculation via BracketService                     │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.2 Проблеми поточної архітектури

| Проблема | Файл | Рядки |
|----------|------|-------|
| 1 executor = всі монети блокуються | `sync_executor.py` | 85-95 |
| quantity в brackets = перерахунок | `sync_executor.py` | 456-461 |
| Складний BracketService (1316 рядків) | `bracket_service.py` | * |
| QoS дублюється в DM та Facade | `decision_making.py`, `runtime_factory.py` | 1000+, 180+ |
| ThreadPoolExecutor overhead | `runtime.py` | 107-109 |

---

## 2. Цільова архітектура

### 2.1 Новий потік даних

```
┌──────────────────────────────────────────────────────────────────────┐
│                         DecisionMaking                                │
│  - Simplified: emit intent, let ExecutorPool handle throttle          │
│  - Remove complex QoS defer logic                                     │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     V2RuntimeFacade (Simplified)                      │
│  - Remove _pending_symbols tracking                                   │
│  - Direct routing to ExecutorPool                                     │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    ExecPosRuntimeV2 (Simplified)                      │
│  - ExecutorPool (replaces SyncOrderExecutor)                          │
│  - Remove BracketService (brackets in SymbolExecutor)                 │
│  - Gatekeeper, WAL, Exposure Bridge (keep)                            │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       ExecutorPool                                    │
│  - Global rate limiter (8 orders/sec)                                 │
│  - Lazy creation of SymbolExecutor per symbol                         │
│  - Fill event routing                                                 │
└───────────┬───────────────┼───────────────┬──────────────────────────┘
            │               │               │
            ▼               ▼               ▼
      ┌──────────┐   ┌──────────┐   ┌──────────┐
      │ BTCUSDT  │   │ ETHUSDT  │   │ SOLUSDT  │
      │ Executor │   │ Executor │   │ Executor │
      │ (own     │   │ (own     │   │ (own     │
      │  thread) │   │  thread) │   │  thread) │
      └──────────┘   └──────────┘   └──────────┘
```

### 2.2 Ключові зміни

| Аспект | Було | Стало |
|--------|------|-------|
| Executor | 1 на всі монети | 1 на кожну монету |
| Brackets quantity | Explicit qty | closePosition=true |
| Brackets перерахунок | При кожній зміні позиції | Тільки ціна (якщо потрібно) |
| Rate limiting | DM + Facade + Runtime | Тільки ExecutorPool |
| BracketService | 1316 рядків | Видалити (логіка в SymbolExecutor) |
| Fill event routing | Complex via Runtime | Direct via ExecutorPool |

---

## 3. Файли для видалення/заміни

### 3.1 Повне видалення (deprecated)

| Файл | Причина | Рядків |
|------|---------|--------|
| `shadow_execpos/sync_executor.py` | Замінено на ExecutorPool | 550 |
| `shadow_execpos/bracket_service.py` | Логіка в SymbolExecutor | 1316 |
| `shadow_execpos/async_manager.py` | Не потрібен з sync pool | ~200 |

### 3.2 Тести для видалення/переписування

| Файл | Дія |
|------|-----|
| `test_sync_executor.py` | Видалити (замінено на test_symbol_executor.py) |
| `test_sync_executor_runtime_integration.py` | Переписати для ExecutorPool |
| `test_bracket_service.py` | Видалити |
| `test_bracket_service_*.py` (5 файлів) | Видалити |
| `test_bracket_wiring*.py` (2 файли) | Видалити |
| `test_async_manager.py` | Видалити |

---

## 4. Файли для модифікації

### 4.1 ExecPosRuntimeV2 (`runtime.py`)

**Поточний стан:** 2284 рядки
**Цільовий стан:** ~1500 рядків (видалення bracket логіки)

#### Зміни:

```python
# ВИДАЛИТИ (рядки ~100-110):
from .sync_executor import SyncOrderExecutor
from .bracket_service import BracketService, ...

# ДОДАТИ:
from .executor_pool import ExecutorPool

# ЗАМІНИТИ в __init__ (рядки ~105-115):
# Було:
self.sync_executor = SyncOrderExecutor(...)
self._sync_executor_pool = ThreadPoolExecutor(...)

# Стане:
self.executor_pool = ExecutorPool(
    adapter=adapter,
    gatekeeper=self.gatekeeper,
    sl_pct=sl_pct,
    tp_rr=tp_rr,
)

# ВИДАЛИТИ:
self.bracket_service = BracketService(...)  # рядок ~95
self._bracket_status: Dict[str, BracketStatus] = {}  # рядок ~160

# СПРОСТИТИ _handle_entry_intent (рядки 700-900):
# Замість sync_executor.execute_entry() використовувати:
result = self.executor_pool.execute_order(
    symbol=symbol,
    side=side,
    quantity=str(adjusted_qty),
    price=str(adjusted_price) if adjusted_price else None,
    client_order_id=payload.get("client_order_id"),
)

# ВИДАЛИТИ повністю:
- _handle_trade_executed_apply_fill_and_brackets() (~200 рядків)
- _evaluate_brackets_for_symbol() (~150 рядків)
- _apply_bracket_plan() (~100 рядків)
- _guard_loop() (~80 рядків) - brackets частину
```

### 4.2 V2RuntimeFacade (`runtime_factory.py`)

**Поточний стан:** ~600 рядків
**Цільовий стан:** ~400 рядків

#### Зміни:

```python
# ВИДАЛИТИ (рядки 165-210):
# - _pending_symbols tracking
# - _is_symbol_throttled()
# - _mark_symbol_pending()
# - _clear_symbol_pending()

# СПРОСТИТИ handle() (рядки 250-320):
# Видалити throttle перевірку для ENTRY_INTENT
# Всю throttle логіку делегувати на ExecutorPool

# СПРОСТИТИ on_trade_executed (рядки 450-470):
# Замість _sync_orders_and_handle_trade:
self.runtime.executor_pool.on_fill(
    symbol=symbol,
    fill_price=payload.get("price"),
    fill_qty=payload.get("quantity"),
    order_id=payload.get("order_id"),
)
```

### 4.3 DecisionMaking (`decision_making.py`)

**Поточний стан:** 2089 рядків
**Цільовий стан:** ~1800 рядків

#### Зміни:

```python
# СПРОСТИТИ QoS логіку (рядки 990-1100):
# Замість складної defer логіки з busy guard:
# - Видалити _qos_next_allowed_ts tracking
# - Видалити _ensure_after_cooldown_retry()
# - ExecutorPool має власний rate limiter

# Залишити тільки базову перевірку:
if self.executor_pool.is_busy(symbol):
    logger.info(f"[{symbol}] Executor busy, intent queued")
    return  # ExecutorPool обробить через свою чергу
```

### 4.4 Gatekeeper (`gatekeeper.py`)

**Без змін** - продовжує валідувати qty/price перед ExecutorPool

### 4.5 Types (`types.py`)

#### Зміни:

```python
# ДОДАТИ новий RuntimeEvent kind:
class RuntimeEventKind(Enum):
    FILL_RECEIVED = "FILL_RECEIVED"  # New: for ExecutorPool routing
```

---

## 5. План міграції по фазах

### Phase 1: Створення нових компонентів ✅ DONE

| Задача | Статус | Файл |
|--------|--------|------|
| SymbolExecutor | ✅ | `symbol_executor.py` |
| ExecutorPool | ✅ | `executor_pool.py` |
| Тести | ✅ | `test_symbol_executor.py` |

### Phase 2: Інтеграція з Runtime (NEXT)

| Задача | Файл | Оцінка |
|--------|------|--------|
| 2.1 Додати ExecutorPool в runtime.py | `runtime.py` | 2h |
| 2.2 Routing fill events | `runtime.py`, `runtime_factory.py` | 1h |
| 2.3 Спростити _handle_entry_intent | `runtime.py` | 2h |
| 2.4 Написати integration tests | `test_executor_pool_integration.py` | 2h |

### Phase 3: Видалення старого коду

| Задача | Файл | Оцінка |
|--------|------|--------|
| 3.1 Видалити sync_executor.py | `sync_executor.py` | 30m |
| 3.2 Видалити bracket_service.py | `bracket_service.py` | 30m |
| 3.3 Видалити async_manager.py | `async_manager.py` | 15m |
| 3.4 Видалити застарілі тести | `test_sync_executor*.py`, `test_bracket_*.py` | 1h |
| 3.5 Оновити __init__.py | `__init__.py` | 15m |

### Phase 4: Спрощення DM та Facade

| Задача | Файл | Оцінка |
|--------|------|--------|
| 4.1 Видалити QoS defer логіку з DM | `decision_making.py` | 2h |
| 4.2 Видалити _pending_symbols з Facade | `runtime_factory.py` | 1h |
| 4.3 Оновити тести DM | `test_decision_making_*.py` | 2h |

### Phase 5: Cleanup та документація

| Задача | Оцінка |
|--------|--------|
| 5.1 Видалити dead code | 1h |
| 5.2 Оновити JOURNAL.md | 30m |
| 5.3 Run full test suite | 30m |
| 5.4 Performance benchmark | 1h |

---

## 6. Тести

### 6.1 Нові тести (створити)

| Файл | Опис |
|------|------|
| `test_symbol_executor.py` | ✅ Вже створено (26 тестів) |
| `test_executor_pool_integration.py` | Integration з Runtime |
| `test_executor_pool_fill_routing.py` | Fill event routing |
| `test_executor_pool_rate_limit.py` | Rate limit behavior |
| `test_close_position_brackets.py` | closePosition=true |

### 6.2 Тести для видалення

```
tests/domains/execution_position/shadow_execpos/
├── test_sync_executor.py                    # ВИДАЛИТИ
├── test_sync_executor_runtime_integration.py # ВИДАЛИТИ
├── test_bracket_service.py                  # ВИДАЛИТИ
├── test_bracket_service_cleanup.py          # ВИДАЛИТИ
├── test_bracket_service_id_generation.py    # ВИДАЛИТИ
├── test_bracket_service_tick_size.py        # ВИДАЛИТИ
├── test_bracket_snapshot_gating.py          # ВИДАЛИТИ
├── test_bracket_snapshot_gating_enhanced.py # ВИДАЛИТИ
├── test_bracket_wiring.py                   # ВИДАЛИТИ
├── test_bracket_wiring_v2_exec.py           # ВИДАЛИТИ
├── test_async_manager.py                    # ВИДАЛИТИ
```

### 6.3 Тести для модифікації

| Файл | Зміни |
|------|-------|
| `test_runtime_wiring.py` | Використовувати ExecutorPool |
| `test_execpos_v2_entry_chain_smoke.py` | Оновити для нової архітектури |
| `test_runtime_facade_integration.py` | Видалити _pending_symbols тести |

---

## 7. Rollback план

### 7.1 Git tags перед кожною фазою

```bash
git tag -a "pre-executor-pool-phase-2" -m "Before ExecutorPool integration"
git tag -a "pre-executor-pool-phase-3" -m "Before old code removal"
git tag -a "pre-executor-pool-phase-4" -m "Before DM simplification"
```

### 7.2 Feature flag

```yaml
# config/execution_position.yaml
execution_position:
  use_executor_pool: true   # false = fallback to old sync_executor
  sync_executor_enabled: false  # deprecated
```

### 7.3 Відкат команди

```bash
# Відкат до Phase 1 (нові компоненти без інтеграції)
git checkout pre-executor-pool-phase-2

# Повний відкат
git checkout pre-executor-pool-phase-1
```

---

## 8. Метрики успіху

| Метрика | Поточне | Ціль |
|---------|---------|------|
| Рядків коду в shadow_execpos | ~6000 | ~3500 |
| Тестів bracket_service | 50+ | 0 (видалено) |
| Паралельних монет | 1 | N (необмежено) |
| p95 order latency | 150ms | <100ms |
| Rate limit violations | ~5/min | 0 |

---

## 9. Порядок виконання

```
Week 1:
├── Day 1: Phase 2.1-2.2 (Integration)
├── Day 2: Phase 2.3-2.4 (Tests)
├── Day 3: Phase 3.1-3.3 (Remove old code)
└── Day 4: Phase 3.4-3.5 (Remove old tests)

Week 2:
├── Day 1: Phase 4.1 (DM simplification)
├── Day 2: Phase 4.2-4.3 (Facade + tests)
├── Day 3: Phase 5 (Cleanup)
└── Day 4: Production testing
```

---

## 10. Checklist перед початком Phase 2

- [x] SymbolExecutor створено та протестовано (26 tests pass)
- [x] ExecutorPool створено та протестовано
- [x] closePosition=true працює в brackets
- [ ] Backup поточного стану (git tag)
- [ ] Всі поточні тести проходять
- [ ] Документація оновлена

---

**Наступний крок:** Підтвердження плану та початок Phase 2 (інтеграція ExecutorPool в runtime.py)
