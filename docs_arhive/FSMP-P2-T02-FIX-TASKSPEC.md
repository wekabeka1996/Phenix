# FSMP-P2-T02-FIX ‚ î TaskSpec  ¥ ª è Copilot

**RID**: FSMP-P2-T02-FIX  
**Priority**: P0 (URGENT)  
**Status**: READY  
**Branch**: `feat/p2-distributed-idemp-fix`

---

## üéØ  ¶ µ ª å (Goal)

 î æ ≤ µ   Ç ∏ **FSMP-P2-T02**  ¥ æ DoD  ± µ ∑  ∏ ∑ º µ Ω µ Ω ∏ è API/ ª æ ≥ ∏ ∫ ∏:
- Coverage ‚â• 90% (   µ π á     81%)
- Tests 14/14 PASS (   µ π á     7/14)
- mypy --strict = 0 warnings (   µ π á     3)
- SLO validated: p95 ‚â§ 10ms, timeout_rate ‚â§ 1%

---

## üìã  ó   ¥   á ∏ (Tasks)

### 1. Embedded Lua Runtime ( ü   ∏ æ   ∏ Ç µ Ç: P0)

** ü   æ ± ª µ º  **: `fakeredis`  Ω µ    æ ¥ ¥ µ   ∂ ∏ ≤   µ Ç Lua scripts (EVAL/EVALSHA).

** † µ à µ Ω ∏ µ**:
-  ° æ ∑ ¥   Ç å `EmbeddedRedisHarness`  ∏ ª ∏  ∏ Ω ∂ µ ∫ Ç ∏   É µ º ã π `LuaExecutor`:
  -  ≠ º É ª ∏   É µ Ç Lua-   ∫   ∏   Ç ã  ∏ ∑ `redis_store.py` (RESERVE_SCRIPT, CONFIRM_SCRIPT, RELEASE_SCRIPT)
  -  ì       Ω Ç ∏   É µ Ç    Ç æ º     Ω æ   Ç å  ≤      º ∫   Ö  Ç µ   Ç   (mutex/lock)
  -  ° æ ≤ º µ   Ç ∏ º    `fakeredis` ( ±   ∑ æ ≤ ã µ  ∫ æ º   Ω ¥ ã: GET/SET/DEL/PEXPIRE/EXISTS)

** §   π ª**: `tests/idempotency/fixtures/lua_executor.py`

**API**:
```python
class LuaExecutor:
    def __init__(self, redis_client: Any) -> None: ...
    
    def evalsha(self, sha: str, num_keys: int, *args: str) -> List[str]:
        """Execute Lua script with atomic guarantees."""
        ...
```

** ö   ∏ Ç µ   ∏ π**: `RedisIdempotencyStore`      ± æ Ç   µ Ç    `LuaExecutor`  ≤ º µ   Ç æ    µ   ª å Ω æ ≥ æ Redis  ≤  Ç µ   Ç   Ö.

---

### 2.  î æ ±   ≤ ∏ Ç å 7      æ   É â µ Ω Ω ã Ö  Ç µ   Ç æ ≤

#### Test 8: Concurrent reserve race (race.py)

```python
def test_idemp_concurrency_reserve_race():
    """10 threads/processes ‚Üí exactly 1 NEW, rest DUPLICATE_SAME/EXTERN_OWNER."""
    # Barrier sync
    # Assert: new_count == 1, no double "victory"
```

#### Test 9: Conflict under race (race.py)

```python
def test_idemp_conflict_under_race():
    """Parallel different digests ‚Üí all but one get CONFLICT/BUSY."""
    # Assert: new_count == 1, conflict_count + busy_count == N-1
```

#### Test 10: TTL expiry (ttl_resilience.py)

```python
def test_idemp_ttl_expiry():
    """After TTL expires, key disappears; repeat reserve ‚Üí NEW."""
    # time.sleep(ttl_ms / 1000 + buffer)
    # Assert: get_status() == EMPTY, reserve() == NEW
```

#### Test 11: Store timeout/retry/CB (ttl_resilience.py)

```python
def test_idemp_store_timeout_retry_cb():
    """Inject timeouts ‚Üí backoff/CB/ERR; WHY‚â§80 present."""
    # Mock Redis failures
    # Assert: CBOpenError raised, metrics.idemp_cb_open_total > 0, WHY‚â§80
```

#### Test 12: Adapter integration - no-op on duplicate (adapter_integration.py)

```python
def test_adapter_with_distributed_idemp_noop_on_duplicate():
    """Repeated submit returns same EVT (no SDK I/O)."""
    # First: reserve‚ÜíNEW ‚Üí SDK called
    # Second: reserve‚ÜíDUPLICATE_SAME ‚Üí SDK NOT called
    # Assert: sdk.submit.call_count == 1
```

#### Test 13: Adapter busy owner handling (adapter_integration.py)

```python
def test_adapter_busy_owner():
    """EXTERN_OWNER ‚Üí ERR.idemp.busy with WHY‚â§80."""
    # Worker 1 reserves
    # Worker 2 tries ‚Üí BusyError
    # Assert: err.code == "ERR.idemp.busy", len(err.why) <= 80
```

#### Test 14: Metrics counters and p95 (metrics.py)

```python
def test_idemp_metrics_counters_p95():
    """100 ops ‚Üí counters + p95 ‚â§ 10ms."""
    # Assert: p95_reserve <= 10.0, p95_confirm <= 10.0
    # Assert: idemp_reserve_total["NEW"] == 100
```

** §   π ª ã**:
- `tests/idempotency/test_race.py` ( æ ± Ω æ ≤ ∏ Ç å    æ ¥ `LuaExecutor`)
- `tests/idempotency/test_ttl_resilience.py` ( æ ± Ω æ ≤ ∏ Ç å)
- `tests/idempotency/test_adapter_integration.py` ( æ ± Ω æ ≤ ∏ Ç å)
- `tests/idempotency/test_metrics.py` ( æ ± Ω æ ≤ ∏ Ç å)

---

### 3. Coverage Uplift: ‚â•90%

**Current**:
- `simple_redis_store.py`: 81%
- `errors.py`: 82%
- `store.py`: 76%
- `redis_store.py`: 0% ( Ω µ  Ç µ   Ç ∏   æ ≤   ª   è)

**Target**: ‚â•90%  Ω    í ° ï  º æ ¥ É ª ∏

** ü æ ¥ Ö æ ¥**:
1.  ò     æ ª å ∑ æ ≤   Ç å `LuaExecutor`  ¥ ª è  Ç µ   Ç ∏   æ ≤   Ω ∏ è `RedisIdempotencyStore` ( æ   Ω æ ≤ Ω   è  ∏ º   ª µ º µ Ω Ç   Ü ∏ è)
2.  ü æ ∫   ã Ç å  ≥     Ω ∏ á Ω ã µ    ª É á   ∏:
   - CB transitions (CLOSED ‚Üí OPEN ‚Üí HALF_OPEN ‚Üí CLOSED)
   - Retry exhaustion
   - Missing record on release/confirm
   - Race conditions (owner mismatch)
3. Property-based tests ( µ   ª ∏  ≤   µ º µ Ω ∏  ¥ æ   Ç   Ç æ á Ω æ): `hypothesis`  ¥ ª è fuzz- Ç µ   Ç æ ≤

** ö æ º   Ω ¥        æ ≤ µ   ∫ ∏**:
```bash
pytest tests/idempotency/ --cov=vfoundation.core.idempotency --cov-report=term-missing --cov-fail-under=90
```

---

### 4. Mypy --strict: 0 Warnings

**Current warnings**:
- `redis.from_url`: untyped call
- Redis client type issues

** † µ à µ Ω ∏ µ**:
1.  ° æ ∑ ¥   Ç å `Protocol`  ¥ ª è Redis client:
```python
from typing import Protocol

class RedisClientProtocol(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> bool: ...
    def delete(self, key: str) -> int: ...
    def evalsha(self, sha: str, numkeys: int, *args: str) -> List[str]: ...
    # ...
```

2.  ò     æ ª å ∑ æ ≤   Ç å `cast()`  ∏ ª ∏ `# type: ignore[no-untyped-call]`     ∫ æ º º µ Ω Ç     ∏ µ º WHY.

** §   π ª ã**: `redis_store.py`, `simple_redis_store.py`

** ö æ º   Ω ¥        æ ≤ µ   ∫ ∏**:
```bash
mypy vfoundation/vfoundation/core/idempotency --strict
```

---

### 5. Validate SLO  ≤  Ç µ   Ç   Ö

** ú µ Ç   ∏ ∫ ∏**:
- `p95(reserve) ‚â§ 10ms`
- `p95(confirm) ‚â§ 10ms`
- `timeout_rate ‚â§ 1%`

** † µ   ª ∏ ∑   Ü ∏ è**:
```python
def test_slo_validation():
    """Run 1000 ops, check p95 ‚â§ 10ms, timeout_rate ‚â§ 1%."""
    for i in range(1000):
        store.reserve(...)
    
    p95 = store.metrics.get_p95_reserve_latency()
    assert p95 <= 10.0, f"p95={p95}ms exceeds 10ms SLO"
    
    timeout_rate = store.metrics.timeout_count / 1000
    assert timeout_rate <= 0.01, f"timeout_rate={timeout_rate} exceeds 1%"
```

** §   π ª**: `tests/idempotency/test_slo.py`

---

### 6. WHY‚â§80 Automated Validators

 ° æ ∑ ¥   Ç å  Ö µ ª   µ    ¥ ª è      æ ≤ µ   ∫ ∏ WHY  ≤  Ç µ   Ç   Ö:

```python
def assert_why_valid(err: IdempotencyError) -> None:
    """Assert WHY ‚â§ 80 chars."""
    assert len(err.why) <= 80, f"WHY too long ({len(err.why)}): {err.why}"
    assert err.code.startswith("ERR.idemp."), f"Invalid code: {err.code}"
```

 ò     æ ª å ∑ æ ≤   Ç å  ≤ æ  í ° ï •  Ç µ   Ç   Ö     æ à ∏ ± ∫   º ∏.

---

### 7. Update Documentation

** §   π ª**: `docs/FSMP-P2-T02-COMPLETION-REPORT.md`

 û ± Ω æ ≤ ∏ Ç å    µ ∫ Ü ∏ ∏:
- Test Results: 14/14 PASS ‚úÖ
- Coverage: ‚â•90% ‚úÖ
- mypy: 0 warnings ‚úÖ
- SLO: p95‚â§10ms, timeout_rate‚â§1% ‚úÖ
-  £ ¥   ª ∏ Ç å WVR-02

---

## üö™ Definition of Done (DoD)

| Criterion | Target | Current | Status |
|-----------|--------|---------|--------|
| Tests PASS | 14/14 | 7/14 | ‚ùå |
| Coverage | ‚â•90% | 81% | ‚ùå |
| mypy --strict | 0 warnings | 3 | ‚ùå |
| p95 latency | ‚â§10ms | <2ms | ‚úÖ |
| timeout_rate | ‚â§1% | 0% | ‚úÖ |
| WHY‚â§80 validators | All ERR paths | Partial | ‚ùå |
| Documentation | Updated | Partial | ‚ùå |

**Gate**: ALL ‚úÖ before merge.

---

## üö´ Out of Scope (STOP-     º ∫  )

- ‚ùå NO  ∏ ∑ º µ Ω µ Ω ∏ è API/ ª æ ≥ ∏ ∫ ∏ ( Ç æ ª å ∫ æ  Ç µ   Ç ã/ Ç ∏   ã)
- ‚ùå NO  ∏ ∑ º µ Ω µ Ω ∏ è FSM/WAL
- ‚ùå NO  Ω æ ≤ ã µ  Ñ ∏ á ∏
- ‚ùå NO  ≤ Ω µ à Ω ∏ µ  ∑   ≤ ∏   ∏ º æ   Ç ∏ (Docker Redis)

---

## üì¶ Deliverables

1. `tests/idempotency/fixtures/lua_executor.py` ‚ î embedded Lua runtime
2. `tests/idempotency/test_race.py` ‚ î 2 race tests
3. `tests/idempotency/test_ttl_resilience.py` ‚ î 2 TTL/resilience tests
4. `tests/idempotency/test_adapter_integration.py` ‚ î 2 adapter tests
5. `tests/idempotency/test_metrics.py` ‚ î 1 metrics test
6. `tests/idempotency/test_slo.py` ‚ î SLO validation test
7. Type annotations in `redis_store.py`, `simple_redis_store.py`
8. Updated `docs/FSMP-P2-T02-COMPLETION-REPORT.md`

---

## üîß Commands

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

## ‚è±Ô∏è Estimate

- **Lua executor**: 1-2h
- **7 tests**: 2-3h
- **Coverage uplift**: 1-2h
- **Mypy cleanup**: 0.5-1h
- **Documentation**: 0.5h

**Total**: 5-8.5h

---

**Approval Required**: After 14/14 PASS + cov‚â•90% + mypy=0

**Next**: FSMP-P2-T03 (Portfolio Accounting)

---

**Author**: vFoundation Team  
**Date**: 2025-10-14  
**Status**: READY FOR EXECUTION
