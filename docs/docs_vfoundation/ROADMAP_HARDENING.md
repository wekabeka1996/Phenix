# vFoundation Hardening Roadmap v1.0

**Дата:** 2026-02-19
**Базується на:** [Аудит.md](Аудит.md)
**Принцип:** Не зламати працюючу систему. Additive-first, потім refactor.

---

## Прогрес

| Phase | Status | Tests before → after |
|-------|--------|---------------------|
| Phase 0 | ✅ DONE | 51 → 51 (0 new broken) |
| Phase 1 | ✅ DONE | 51 → 101 (+50 tests) |
| Phase 2 | ✅ DONE (2.1 + verb fix + 2.2 + 2.3) | 101 → 110 |
| Phase 3 | ✅ DONE (3.1 FSMv2 + 3.2 SchemaValidator + 3.3 MetaFSMv2) | 110 → 157 |
| Phase 4.1 | ✅ DONE (shared types) | 157 → 161 |
| Phase 4.2–4.3 | ⏸️ DEFERRED (needs full domain test coverage) | |
| Phase 5.1 | ✅ DONE (TopologyAuditor) | 161 → 169 |
| Phase 5.2 | ✅ DONE (IntentLayer) | 169 → 182 |
| Phase 5.3–5.4 | ⏸️ DEFERRED (breaking changes to Message envelope) | |
| Phase 6 | ✅ DONE (coverage gaps) | 182 → 245 |
| Phase 7 | ✅ DONE (deep coverage + fixes) | 245 → 326 |
| Phase 8 | ✅ DONE (foundational coverage + deprecated cleanup) | 326 → 531 |

**Final gate: 531 passed, 0 failed.**

### Phase 6 — Coverage Gaps (additive, non-breaking)

**Ціль:** Покрити тестами всі модулі vfoundation, які мали 0 coverage.

| # | Module | Tests | File |
|---|--------|-------|------|
| 6.1 | `adapters/exchange/acl.py` | 14 (dataclasses, submit, cancel, stream, idempotency, metrics) | `tests/vfoundation/adapters/test_exchange_acl.py` |
| 6.2 | `obs/logger.py` | 4 (JsonFormatter JSON output, exceptions, extra fields, log_event) | `tests/vfoundation/obs/test_logger.py` |
| 6.3 | `obs/correlation.py` | 9 (put/get roundtrip, SL/TP ack, TTL expiry, cleanup, stats, coercion) | `tests/vfoundation/obs/test_correlation.py` |
| 6.4 | `core/adapters/base.py` | 8 (ExchangeOrderParams, ExchangeOrderResponse, ExchangePosition, ABC enforcement) | `tests/vfoundation/core/test_adapters_base.py` |
| 6.5 | `core/why_codes.py` | 15 (WhyCode enum, descriptions completeness, format, payload) | `tests/vfoundation/core/test_why_codes.py` |
| 6.6 | `core/idempotency/idempotency.py` | 13 (begin/complete/get lifecycle, legacy methods, metrics, cleanup) | `tests/vfoundation/core/test_idempotency.py` |

**Gate:** 245 passed, 0 failed. +63 tests.

### Phase 7 — Deep Coverage + Stub Fixes (additive, non-breaking)

**Ціль:** Покрити залишкові непротестовані модулі, виправити стаби, прибрати deprecated код.

| # | Module / Task | Tests | File |
|---|--------------|-------|------|
| 7.1 | `core/routing.py` (Router, sig verify, CB, why-len, idem) | 14 | `tests/vfoundation/core/test_routing.py` |
| 7.2 | `core/cache/ttl_cache.py` (MonotonicTTLCache, LRU, TTL, janitor) | 21 | `tests/vfoundation/core/test_ttl_cache.py` |
| 7.3 | `core/adapters/idempotency_ledger.py` (check_and_store, TTL, LRU) | 10 | `tests/vfoundation/core/test_idempotency_ledger.py` |
| 7.4 | `core/adapters/execution_exceptions.py` (error classes, WHY truncation) | 18 | `tests/vfoundation/core/test_execution_exceptions.py` |
| 7.5 | `core/fsm_emit_compat.py` (3 emit fallback paths) | 8 | `tests/vfoundation/core/test_fsm_emit_compat.py` |
| 7.6 | `dr/wal_gc.py` (cleanup, rotation, stats) | 9 | `tests/vfoundation/dr/test_wal_gc.py` |
| 7.7 | Wire `ExchangeACL._is_duplicate` → `IdempotencyLedger` | +1 dedup test | Functional fix (was always False) |
| 7.8 | Delete `core/meta_fsm.py` (0 live imports, replaced by v2) | - | Removed |
| 7.9 | Fix stale "stub implementation" comment in `routing.py` | - | Comment fix |

**Gate:** 326 passed, 0 failed. +81 tests, 1 file removed, 1 stub fixed.

### Phase 8 — Foundational Coverage + Deprecated Cleanup (additive, non-breaking)

**Ціль:** Покрити P0/P1 модулі (protocol, config, WAL, idempotency, execution_adapter, Redis store), видалити deprecated binance_adapter.

| # | Module / Task | Tests | File |
|---|--------------|-------|------|
| 8.1 | `core/protocol.py` (Message, Op, IntentType, truncate_why, validators, is_expired) | 45 | `tests/vfoundation/core/test_protocol.py` |
| 8.2 | `config.py` (Config ENV loading, reload, bounds clamping, execution mode, warnings) | 27 | `tests/vfoundation/test_config.py` |
| 8.3 | `dr/wal.py` (append, CAS, read_all, read_by_rid, verify_chain, merkle, lock metrics) | 34 | `tests/vfoundation/dr/test_wal.py` |
| 8.4 | `core/idempotency/errors.py` (all 7 error classes, WHY ≤80 enforcement, codes) | 30 | `tests/vfoundation/core/test_idempotency_errors.py` |
| 8.5 | `core/idempotency/store.py` (enums, DTOs, IdempotencyMetrics, ABC, _LatencyMeasurer) | 24 | `tests/vfoundation/core/test_idempotency_store.py` |
| 8.6 | `core/adapters/execution_adapter.py` (CircuitBreaker, AdapterMetrics, MockExecutionAdapter) | 28 | `tests/vfoundation/core/test_execution_adapter.py` |
| 8.7 | `core/idempotency/backends/simple_redis_store.py` (reserve/confirm/get/release via fakeredis) | 17 | `tests/vfoundation/core/test_simple_redis_store.py` |
| 8.8 | Delete `adapters/binance_adapter.py` (0 active imports confirmed) | - | Removed |

**Gate:** 531 passed, 0 failed. +205 tests, 1 file removed.

---

## Фази та DoD

### Phase 0 — Hygiene (без функціональних змін)

**Ціль:** Прибрати мертвий код, виправити pyproject.toml, прибрати orphaned configs.

| # | Task | DoD | Ризик |
|---|------|-----|-------|
| 0.1 | pyproject.toml: перенести test deps у `[project.optional-dependencies]` | `pip install vfoundation` не ставить pytest/fakeredis | ZERO |
| 0.2 | Видалити `vfoundation/core/degradation.py` (7 LOC, 0 imports) | Файл відсутній, тести зелені | ZERO |
| 0.3 | Видалити `vfoundation/dataref/signed_urls_stub.py` (0 live imports) | Файл відсутній, тести зелені | ZERO |
| 0.4 | Позначити `vfoundation/adapters/binance_adapter.py` як deprecated shim | Docstring + DeprecationWarning | ZERO |
| 0.5 | Позначити `vfoundation/core/fsm.py` та `vfoundation/core/meta_fsm.py` як deprecated | Docstring + DeprecationWarning. НЕ видаляти (є один тест-імпорт). | ZERO |

**Gate:** `pytest tests/vfoundation -q` — всі тести зелені.

---

### Phase 1 — Test Coverage для критичної інфраструктури

**Ціль:** Покрити тестами security, DR, core routing перед будь-якими змінами.

| # | Task | DoD | Target |
|---|------|-----|--------|
| 1.1 | Тести для `security/signing_ed25519.py` | sign → verify round-trip; bad sig → False; key from seed deterministic | 100% coverage |
| 1.2 | Тести для `security/redaction.py` | sensitive fields replaced; non-sensitive preserved | 100% coverage |
| 1.3 | Тести для `security/ratelimits.py` | allow up to limit; deny over limit; window expiry | 100% coverage |
| 1.4 | Тести для `security/rbac_abac.py` | valid token → True; invalid → False; empty → False | 100% coverage |
| 1.5 | Тести для `core/retry_cb.py` | RetryPolicy backoff bounds; CB CLOSED→OPEN→HALF_OPEN→CLOSED transitions | 100% coverage |
| 1.6 | Тести для `core/ttl.py` | TTL profiles dict matches Constitution values | trivial |
| 1.7 | Тести для `obs/why.py` | append_why adds to chain; empty why skipped | 100% coverage |
| 1.8 | Тести для `obs/tracing.py` | new_span returns hex; parent propagated | 100% coverage |
| 1.9 | Тести для `dr/merkle.py` | empty → sha256(""); single hash; balanced tree; odd count | 100% coverage |
| 1.10 | Тести для `dr/snapshot.py` | save → load_latest round-trip; empty domain → None | 100% coverage |
| 1.11 | Тести для `dr/replay.py` | replay_for_rid на tmp WAL; integrity check; from_ts filter | core paths |

**Gate:** `pytest tests/vfoundation -q` — 25+ тестів зелені. Нові тести не залежать від apps/*.

---

### Phase 2 — Fix стабів та хардкоду (non-breaking)

**Ціль:** Замінити fake implementations на функціональні, прибрати хардкод.

| # | Task | DoD |
|---|------|-----|
| 2.1 | CLI `hash_chain_valid: True` → реальна валідація через `wal.verify_chain()` | CLI replay повертає справжнє значення integrity |
| 2.2 | `MockExecutionAdapter` → перенести в `tests/` fixtures | Прибрати з `vfoundation/core/adapters/execution_adapter.py` |
| 2.3 | Config YAML loading: або видалити orphaned YAML, або підключити до config.py | YAML або працює, або видалений |

**Gate:** `pytest tests/vfoundation -q` + `pytest tests/ -q --ignore=tests/backtest` — зелені.

---

### Phase 3 — Core FSM формалізм (additive)

**Ціль:** Зробити FSMCore справжнім FSM engine без зламу існуючого pub/sub API.

| # | Task | DoD |
|---|------|-----|
| 3.1 | FSM v2 з state management, guards, transition table | `FSMv2` клас з `register_state()`, `register_transition()`, `handle()` |
| 3.2 | Schema validation on emit | `FSMCore.emit()` валідує pld проти verb schema з registry |
| 3.3 | MetaFSM v2 з EntropyMonitor інтеграцією | MetaFSM реагує на entropy spikes і topology drift |

**Gate:** Нові тести на FSMv2. Старий FSMCore API залишається backward-compatible.

---

### Phase 4 — Cross-domain imports та модульність

**Ціль:** Розширити shared types та зменшити coupling.

| # | Task | DoD |
|---|------|-----|
| 4.1 | Shared types module для cross-domain data types | `apps/reference/shared/types.py` з Bar, NRR, RegimeThresholds |
| 4.2 | Розбити decision_making.py (4K LOC) | 4+ модулі ≤ 800 LOC |
| 4.3 | Розбити fsm.py (4K LOC) | 4+ модулі ≤ 800 LOC |

**Gate:** Zero cross-domain imports. `pytest -q` зелений.

---

### Phase 5 — Missing components (Constitution compliance)

**Ціль:** Реалізувати відсутні компоненти з Constitution v2.2.

| # | Task | DoD |
|---|------|-----|
| 5.1 | TopologyAuditor | Emits EVT:TOPOLOGY_DRIFT_DETECTED |
| 5.2 | Intent Layer | QoS / пріоритизація на базі intent field |
| 5.3 | Message envelope refactor | Trading-specific fields → pld; core envelope clean |
| 5.4 | Typed pld per verb via discriminated unions | Per-verb Pydantic models |

---

## Порядок виконання

```
Phase 0 (сьогодні) → Phase 1 (сьогодні) → Phase 2 (наступний sprint)
→ Phase 3 → Phase 4 → Phase 5
```

Кожна фаза має `pytest tests/vfoundation -q` gate.
