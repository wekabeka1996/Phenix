# FSMP-P2-T02-FIX — TaskSpec для Copilot

**RID**: FSMP-P2-T02-FIX  
**Priority**: P0 (URGENT)  
**Status**: READY  
**Branch**: `feat/p2-distributed-idemp-fix`

---

## 🎯 Цель (Goal)

Дове� ти **FSMP-P2-T02** до DoD без изменения API/логики:
- Coverage ≥ 90% (� ейча�  81%)
- Tests 14/14 PASS (� ейча�  7/14)
- mypy --strict = 0 warnings (� ейча�  3)
- SLO validated: p95 ≤ 10ms, timeout_rate ≤ 1%

---

## 📋 Задачи (Tasks)

### 1. Embedded Lua Runtime (Приоритет: P0)

**Проблема**: `fakeredis` не поддерживает Lua scripts (EVAL/EVALSHA).

**Решение**:
- Создать `EmbeddedRedisHarness` или инжектируемый `LuaExecutor`:
  - Эмулирует Lua-� крипты из `redis_store.py` (RESERVE_SCRIPT, CONFIRM_SCRIPT, RELEASE_SCRIPT)
  - Гарантирует атомарно� ть в рамках те� та (mutex/lock)
  - Совме� тим �  `fakeredis` (базовые команды: GET/SET/DEL/PEXPIRE/EXISTS)

**Файл**: `tests/idempotency/fixtures/lua_executor.py`

**API**:
```python
class LuaExecutor:
    def __init__(self, redis_client: Any) -> None: ...
    
    def evalsha(self, sha: str, num_keys: int, *args: str) -> List[str]:
        """Execute Lua script with atomic guarantees."""
        ...
```

**Критерий**: `RedisIdempotencyStore` работает �  `LuaExecutor` вме� то реального Redis в те� тах.

---

### 2. Добавить 7 пропущенных те� тов

#### Test 8: Concurrent reserve race (race.py)

```python
def test_idemp_concurrency_reserve_race():
    """10 threads/processes → exactly 1 NEW, rest DUPLICATE_SAME/EXTERN_OWNER."""
    # Barrier sync
    # Assert: new_count == 1, no double "victory"
```

#### Test 9: Conflict under race (race.py)

```python
def test_idemp_conflict_under_race():
    """Parallel different digests → all but one get CONFLICT/BUSY."""
    # Assert: new_count == 1, conflict_count + busy_count == N-1
```

#### Test 10: TTL expiry (ttl_resilience.py)

```python
def test_idemp_ttl_expiry():
    """After TTL expires, key disappears; repeat reserve → NEW."""
    # time.sleep(ttl_ms / 1000 + buffer)
    # Assert: get_status() == EMPTY, reserve() == NEW
```

#### Test 11: Store timeout/retry/CB (ttl_resilience.py)

```python
def test_idemp_store_timeout_retry_cb():
    """Inject timeouts → backoff/CB/ERR; WHY≤80 present."""
    # Mock Redis failures
    # Assert: CBOpenError raised, metrics.idemp_cb_open_total > 0, WHY≤80
```

#### Test 12: Adapter integration - no-op on duplicate (adapter_integration.py)

```python
def test_adapter_with_distributed_idemp_noop_on_duplicate():
    """Repeated submit returns same EVT (no SDK I/O)."""
    # First: reserve→NEW → SDK called
    # Second: reserve→DUPLICATE_SAME → SDK NOT called
    # Assert: sdk.submit.call_count == 1
```

#### Test 13: Adapter busy owner handling (adapter_integration.py)

```python
def test_adapter_busy_owner():
    """EXTERN_OWNER → ERR.idemp.busy with WHY≤80."""
    # Worker 1 reserves
    # Worker 2 tries → BusyError
    # Assert: err.code == "ERR.idemp.busy", len(err.why) <= 80
```

#### Test 14: Metrics counters and p95 (metrics.py)

```python
def test_idemp_metrics_counters_p95():
    """100 ops → counters + p95 ≤ 10ms."""
    # Assert: p95_reserve <= 10.0, p95_confirm <= 10.0
    # Assert: idemp_reserve_total["NEW"] == 100
```

**Файлы**:
- `tests/idempotency/test_race.py` (обновить под `LuaExecutor`)
- `tests/idempotency/test_ttl_resilience.py` (обновить)
- `tests/idempotency/test_adapter_integration.py` (обновить)
- `tests/idempotency/test_metrics.py` (обновить)

---

### 3. Coverage Uplift: ≥90%

**Current**:
- `simple_redis_store.py`: 81%
- `errors.py`: 82%
- `store.py`: 76%
- `redis_store.py`: 0% (не те� тировал� я)

**Target**: ≥90% на ВСЕ модули

**Подход**:
1. И� пользовать `LuaExecutor` для те� тирования `RedisIdempotencyStore` (о� новная имплементация)
2. Покрыть граничные � лучаи:
   - CB transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
   - Retry exhaustion
   - Missing record on release/confirm
   - Race conditions (owner mismatch)
3. Property-based tests (е� ли времени до� таточно): `hypothesis` для fuzz-те� тов

**Команда проверки**:
```bash
pytest tests/idempotency/ --cov=vfoundation.core.idempotency --cov-report=term-missing --cov-fail-under=90
```

---

### 4. Mypy --strict: 0 Warnings

**Current warnings**:
- `redis.from_url`: untyped call
- Redis client type issues

**Решение**:
1. Создать `Protocol` для Redis client:
```python
from typing import Protocol

class RedisClientProtocol(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> bool: ...
    def delete(self, key: str) -> int: ...
    def evalsha(self, sha: str, numkeys: int, *args: str) -> List[str]: ...
    # ...
```

2. И� пользовать `cast()` или `# type: ignore[no-untyped-call]` �  комментарием WHY.

**Файлы**: `redis_store.py`, `simple_redis_store.py`

**Команда проверки**:
```bash
mypy vfoundation/vfoundation/core/idempotency --strict
```

---

### 5. Validate SLO в те� тах

**Метрики**:
- `p95(reserve) ≤ 10ms`
- `p95(confirm) ≤ 10ms`
- `timeout_rate ≤ 1%`

**Реализация**:
```python
def test_slo_validation():
    """Run 1000 ops, check p95 ≤ 10ms, timeout_rate ≤ 1%."""
    for i in range(1000):
        store.reserve(...)
    
    p95 = store.metrics.get_p95_reserve_latency()
    assert p95 <= 10.0, f"p95={p95}ms exceeds 10ms SLO"
    
    timeout_rate = store.metrics.timeout_count / 1000
    assert timeout_rate <= 0.01, f"timeout_rate={timeout_rate} exceeds 1%"
```

**Файл**: `tests/idempotency/test_slo.py`

---

### 6. WHY≤80 Automated Validators

Создать хелпер для проверки WHY в те� тах:

```python
def assert_why_valid(err: IdempotencyError) -> None:
    """Assert WHY ≤ 80 chars."""
    assert len(err.why) <= 80, f"WHY too long ({len(err.why)}): {err.why}"
    assert err.code.startswith("ERR.idemp."), f"Invalid code: {err.code}"
```

И� пользовать во ВСЕХ те� тах �  ошибками.

---

### 7. Update Documentation

**Файл**: `docs/FSMP-P2-T02-COMPLETION-REPORT.md`

Обновить � екции:
- Test Results: 14/14 PASS ✅
- Coverage: ≥90% ✅
- mypy: 0 warnings ✅
- SLO: p95≤10ms, timeout_rate≤1% ✅
- Удалить WVR-02

---

## 🚪 Definition of Done (DoD)

| Criterion | Target | Current | Status |
|-----------|--------|---------|--------|
| Tests PASS | 14/14 | 7/14 | ❌ |
| Coverage | ≥90% | 81% | ❌ |
| mypy --strict | 0 warnings | 3 | ❌ |
| p95 latency | ≤10ms | <2ms | ✅ |
| timeout_rate | ≤1% | 0% | ✅ |
| WHY≤80 validators | All ERR paths | Partial | ❌ |
| Documentation | Updated | Partial | ❌ |

**Gate**: ALL ✅ before merge.

---

## 🚫 Out of Scope (STOP-рамка)

- ❌ NO изменения API/логики (только те� ты/типы)
- ❌ NO изменения FSM/WAL
- ❌ NO новые фичи
- ❌ NO внешние зави� имо� ти (Docker Redis)

---

## 📦 Deliverables

1. `tests/idempotency/fixtures/lua_executor.py` — embedded Lua runtime
2. `tests/idempotency/test_race.py` — 2 race tests
3. `tests/idempotency/test_ttl_resilience.py` — 2 TTL/resilience tests
4. `tests/idempotency/test_adapter_integration.py` — 2 adapter tests
5. `tests/idempotency/test_metrics.py` — 1 metrics test
6. `tests/idempotency/test_slo.py` — SLO validation test
7. Type annotations in `redis_store.py`, `simple_redis_store.py`
8. Updated `docs/FSMP-P2-T02-COMPLETION-REPORT.md`

---

## 🔧 Commands

```bash
# Run all tests
pytest tests/idempotency/ -v

# Coverage check (fail if <90%)
pytest tests/idempotency/ --cov=vfoundation.core.idempotency --cov-fail-under=90

# Mypy check
mypy vfoundation/vfoundation/core/idempotency --strict

# Full gate check
pytest tests/idempotency/ -v --cov=vfoundation.core.idempotency --cov-fail-under=90 && mypy vfoundation/vfoundation/core/idempotency --strict
```

---

## ⏱️ Estimate

- **Lua executor**: 1-2h
- **7 tests**: 2-3h
- **Coverage uplift**: 1-2h
- **Mypy cleanup**: 0.5-1h
- **Documentation**: 0.5h

**Total**: 5-8.5h

---

**Approval Required**: After 14/14 PASS + cov≥90% + mypy=0

**Next**: FSMP-P2-T03 (Portfolio Accounting)

---

**Author**: vFoundation Team  
**Date**: 2025-10-14  
**Status**: READY FOR EXECUTION
