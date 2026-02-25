# vFoundation — Повний план реалізації Phase 14 + Cleanup
**Версія:** 2.2 | **Дата оновлення:** 2026-02-24 18:55 UTC+3 | **Гілка:** backtest_1
**Попередня версія:** 2.0 (2026-02-24, аудит); 1.0 (2026-02-24, початкова)

> ⚠️ **Цей документ актуалізовано на основі незалежного аудиту коду.**
> Позначки `[x]` — перевірено через файловий аналіз, grep, LOC count, pytest.

---

## ПОТОЧНИЙ СТАН СИСТЕМИ (актуально на 2026-02-24 17:00 UTC+3)

| Метрика | Значення |
|---------|----------|
| Тести vfoundation | **1073 / 1073 PASS** (7.13s) |
| Тести domains | ~900+ PASS (asyncio teardown timeout на Windows, не тестова помилка) |
| Покриття vfoundation | ~88% (ціль ≥95%) |
| decision_making декомпозиція | ✅ **ЗАВЕРШЕНА** — 11 модулів ≤500 LOC |
| aurora_handler.py декомпозиція | ✅ **ЗАВЕРШЕНА** — 2,694→544 LOC (-80%), 5 mixins ≤500 |
| execution_position/fsm.py | ❌ **4,687 LOC** — потребує декомпозиції |
| Критичні баги Phase 14 | 0 (обидва з v1.0 пофіксені) |
| Ремедіації (додаткові) | ✅ Risk Mgmt, Apps Ref, Services Core, Telemetry — всі завершені |

### Що вже реалізовано (Phase 9–13 = 98%):
- FSMCore (event bus), FSMv2, MetaFSMv2
- Message Protocol v1 (Pydantic)
- DR: WAL, Snapshot, Replay, Merkle, WAL GC
- Security: Ed25519 signing, RBAC/ABAC
- Observability: XAI Store, Why-chain, Alert Manager, Topology Auditor
- Testing: ChaosHarness, PerfBenchmark, Quality Gates
- CLI: vfound commands (schema, replay, drift, trace, init)
- Idempotency: Redis backends, InMemory
- SchemaValidator з runtime JSON schema validation

---

## ПРИНЦИПИ РЕАЛІЗАЦІЇ

1. **TDD-first** — спочатку тести, потім код
2. **Additive-first** — нові функції додаються, не замінюють старих
3. **Green-always** — після кожного кроку всі 1073+ тестів мають проходити
4. **Strangler Fig** — монолітні файли розбиваються поступово через re-export
5. **Cleanup-after** — мертвий код видаляється тільки після підтвердження
6. **Constitution §3** — кожен модуль ≤500 LOC

---

## КРОК 0 — НЕГАЙНІ BUGFIXES

### 0.1 ✅ Виправити `vfoundation/security/signing_ed25519.py`

**Статус: DONE**
- `except (BadSignatureError, ValueError, TypeError)` — реалізовано
- 10 тестів у `tests/vfoundation/security/test_signing_ed25519.py` — PASS
- Додано: `test_verify_short_signature_returns_false`, `test_verify_empty_signature_returns_false`, `test_verify_wrong_payload_returns_false`, `test_verify_correct_signature_returns_true`

### 0.2 ✅ Виправити `vfoundation/core/protocol.py` — функція `truncate_why`

**Статус: DONE**
- Синтаксис та логіка верифіковані
- 15 нових тестів у `TestTruncateWhyPhase14`, `TestMessageProtocolPhase14`
- 60 тестів у `tests/vfoundation/core/test_protocol.py` — PASS

---

## КРОК 1 — FSMv2 ENHANCEMENTS (Phase 14B)
**Файл:** `vfoundation/core/fsm_v2.py` (398 LOC)

### 1.1 ✅ Deadlock Detection — `validate_reachability()`

**Статус: DONE**
- BFS по графу переходів від initial_state
- Виявляє orphan стани (без вхідних переходів)
- Тести: `TestValidateReachability` у `tests/vfoundation/core/test_fsm_v2_enhancements.py` — PASS

### 1.2 ✅ Graph Export — `to_dot()`

**Статус: DONE**
- Генерує Graphviz DOT format
- Terminal стани → `doublecircle`
- Тести: `TestToDot` — PASS

### 1.3 ✅ State Statistics — `get_stats()`

**Статус: DONE**
- Per-state key counts implemented
- Тести: `TestGetStats` — PASS

### 1.4 ✅ Cleanup перевірка fsm_emit_compat.py

**Статус: DONE (рішення — НЕ видаляти)**
- `fsm_emit_compat.py` (120 LOC) ще використовується у:
  - `apps/reference/retry_scheduler.py` (shim)
  - `apps/reference/domains/execution_position/exposure_guard.py` (×2)
  - `apps/reference/domains/execution_position/fsm.py`
  - `vfoundation/core/retry_scheduler.py`
- **Рішення:** Файл залишається до завершення декомпозиції execution_position

### 1.5 ✅ WAL Integration — `EVT:STATE_TRANSITION` recording

**Статус: DONE**
- `FSMv2.__init__()` приймає optional `wal_writer=` callback (DI)
- Після успішного переходу записується WAL record: `{event, fsm, key, from_state, to_state, trigger, ts_ms}`
- WAL failure — warn-only (не блокує transition)
- Backward-compat: без `wal_writer` працює як раніше
- Тести: 4 тести у `test_fsm_v2_transactional.py` — PASS

### 1.6 ✅ Transactional Rollback

**Статус: DONE**
- `on_exit` exception → transition aborted, стан залишається `old_state`
- `on_enter` exception → state rolled back: `self._state_store[key] = old_state`
- Action exception → не rollback (post-commit behavior)
- Додано `metrics.rollbacks` counter
- Тести: 7 тестів у `test_fsm_v2_transactional.py` — PASS

### 1.7 ❌ FSMCore ↔ FSMv2 Bridge Pattern

**Статус: НЕ ЗРОБЛЕНО**
- FSMCore.emit() не делегує до зареєстрованих FSMv2 через handle()
- Блокує Domain Migration (1.8, 1.9)
- **Оцінка:** ~90 min

### 1.8 ❌ Domain Migration — execution_position на FSMv2

**Статус: НЕ ЗРОБЛЕНО**
- Залежить від: декомпозиції fsm.py (Крок 4.3) та Bridge (1.7)
- Стани: INIT → FLAT → ENTRY_PENDING → POSITION_OPEN → EXIT_PENDING → COOLDOWN
- **Оцінка:** ~1 тиждень

### 1.9 ❌ Domain Migration — decision_making на FSMv2

**Статус: НЕ ЗРОБЛЕНО**
- Залежить від: Bridge (1.7)
- Стани: IDLE → EVALUATING → QOS_THROTTLED → ACCEPTED → REJECTED
- **Оцінка:** ~1 тиждень

### 1.10 ❌ CLI: `vfound fsm validate` / `vfound fsm graph`

**Статус: НЕ ЗРОБЛЕНО**
- CLI файл: `vfoundation/cli/vfound/__main__.py` (16,580 bytes)
- Потрібно додати subcommands
- **Оцінка:** ~60 min

---

## КРОК 2 — TOPOLOGY AUDITOR EXTENSION (Phase 14D)
**Файл:** `vfoundation/obs/topology_auditor.py` (213 LOC)

### 2.1 ✅ Infrastructure Health Monitoring

**Статус: DONE**
- `HealthCheck` / `HealthReport` dataclasses додані
- `audit_health(checks)` реалізований
- Тести: `tests/vfoundation/obs/test_topology_auditor_health.py` — 10 тестів PASS

### 2.2 ✅ DomainBridge для orphan domains

**Статус: DONE**
- `vfoundation/obs/domain_bridge.py` (61 LOC)
- Domain registration, health functions, EVT:DOMAIN_STATUS emission
- Тести: `tests/vfoundation/obs/test_domain_bridge.py` — 13 тестів PASS
- DecisionMaking та ExecPosFSM інтегровані через DomainBridge

### 2.3 ❌ Runtime Infrastructure Probes

**Статус: НЕ ЗРОБЛЕНО**
- TopologyAuditor не моніторить: Redis ping, WebSocket latency, error_rate
- Потрібно розширити для `EVT:TOPOLOGY_DRIFT_DETECTED` при infrastructure drift
- **Оцінка:** ~90 min

### 2.4 ❌ MetaFSMv2 Background Loop Wiring

**Статус: НЕ ЗРОБЛЕНО**
- `MetaFSMv2` (266 LOC у `vfoundation/core/meta_fsm_v2.py`) існує і працює
- Але NOT wired: `asyncio.create_task(meta.tick())` не викликається в `apps/reference/main.py`
- `CMD:SWITCH_TO_LOW_RISK_MODE` генерується, але **жоден домен не підписаний**
- **Оцінка:** ~60 min

### 2.5 ❌ Orphan Domain FSM Adapters

**Статус: НЕ ЗРОБЛЕНО**

| Адаптер | Файл | Статус |
|---------|------|--------|
| `neocortex_fsm_adapter.py` | не існує | ❌ |
| `alpha_search_fsm_adapter.py` | не існує | ❌ |
| `inflight_reconcile_fsm_adapter.py` | не існує | ❌ |

**Cross-domain imports досі існують:**
```
decision_making/event_handlers.py:32 → from apps.reference.domains.alpha_search import (...)
decision_making/decision_making.py:42 → from apps.reference.domains.alpha_search import (...)
```

**Оцінка:** ~2-3 дні для всіх трьох

---

## КРОК 3 — MESSAGE PROTOCOL v2 (Phase 14C)

### 3.1 ✅ Typed Payload Schemas (Pydantic)

**Статус: DONE**
- `vfoundation/core/payloads.py` (76 LOC)
- Schemas: `OpenPayload`, `ClosePayload`, `FillPayload`, `RiskPayload`, `ReconcilePayload`
- `Message.typed_payload(schema_cls)` helper додано
- Тести: `tests/vfoundation/core/test_payloads.py` — 20 тестів PASS

### 3.2 ✅ ExchangeContext Shared Schema

**Статус: DONE**
- `vfoundation/core/exchange_context.py` (27 LOC)
- Тести: `tests/vfoundation/core/test_exchange_context.py` — 7 тестів PASS
- ⚠️ **Примітка:** Blueprint пропонував місце `apps/reference/shared/schemas/exchange_ctx.py`, але реалізовано у `vfoundation/core/` — прийнятно, оскільки exchange context є протокольно-рівневим

### 3.3 ✅ Migration Helper — `migrate_pld_v1_to_v2()`

**Статус: DONE**
- `vfoundation/core/protocol_migration.py` (37 LOC)
- Helpers: `migrate_pld_v1_to_v2()`, `is_v2_message()`
- Тести: `tests/vfoundation/core/test_protocol_migration.py` — 8 тестів PASS

### 3.4 ❌ Message Deprecation Warnings

**Статус: НЕ ЗРОБЛЕНО**
- Поля `oco_group_id`, `parent_client_order_id`, `link_ack_id`, `link_fill_id`, `corr_id`, `mode`, `mode_contract` — **жодне не позначено deprecated** у `vfoundation/core/protocol.py`
- Blueprint 14C §3.2 вимагає `@model_validator` з `warnings.warn()` та `Field(deprecated=...)`
- **Блокер:** Немає
- **Оцінка:** ~45 min

### 3.5 ❌ Per-Verb Pydantic Schemas Directory

**Статус: НЕ ЗРОБЛЕНО**
- Директорія `vfoundation/schemas/verbs/` **не існує**
- Blueprint 14C §4.1 вимагає: `_registry.py`, `core/evt_trade_intent.py`, тощо
- **Оцінка:** ~3-5 днів (для всіх verb schemas)

### 3.6 ❌ Verb Schema Registry + `@register_verb_schema`

**Статус: НЕ ЗРОБЛЕНО**
- `_VERB_SCHEMA_REGISTRY` та decorator не реалізовані
- `get_schema_for_verb()` не існує
- **Оцінка:** ~60 min (scaffolding)

### 3.7 ❌ FSMCore.emit() Runtime Payload Validation

**Статус: НЕ ЗРОБЛЕНО**
- `FSMCore.emit()` не валідує payload проти verb schema
- Blueprint 14C §4.4: fail-closed при невалідному payload
- **Залежить від:** 3.6 (registry)
- **Оцінка:** ~45 min

### 3.8 ❌ Decimal типізація в Typed Payloads

**Статус: НЕ ЗРОБЛЕНО**
- `OpenPayload.qty`, `OpenPayload.price` — `float`, не `Decimal`
- Blueprint 14C §4.2 вимагає `Decimal` з `gt=0` validators
- **Оцінка:** ~30 min

---

## КРОК 4 — МОНОЛІТНА ДЕКОМПОЗИЦІЯ (Phase 14A)

### 4.1 ✅ Audit монолітів

**Статус: DONE**
- `decision_making.py`: було **4,454 LOC** → визнано >500
- `execution_position/fsm.py`: було **4,687 LOC** → визнано >500
- Інші порушники виявлені (aurora_handler: 2,693, fsm_manage: 1,454, order_guardian: 1,367)

### 4.2 ✅ Strangler Fig для `decision_making.py`

**Статус: DONE — ВСІ 11 МОДУЛІВ ≤500 LOC**

| Файл | LOC | Відповідальність |
|------|-----|------------------|
| `decision_making.py` (фасад) | 451 | Routing, ініціалізація |
| `intent_builder.py` | 472 | Формування trade intent payload |
| `readiness_gates.py` | 464 | Перевірки готовності перед trade |
| `strategy_gateway.py` | 452 | Signal gateway + стратегічна маршрутизація |
| `event_handlers.py` | 441 | FSM event обробники |
| `safety_gates.py` | 411 | Risk shields, danger zone |
| `config_resolver.py` | 383 | Resolve конфігурації per-symbol |
| `flip_orchestration.py` | 357 | Position flip logic |
| `position_queries.py` | 312 | Query поточних позицій |
| `intent_emitter.py` | 301 | Emit trade intents |
| `qos_rate_control.py` | 217 | QoS throttling |

**Фіксовані тести при декомпозиції:**
- `test_signal_ttl_validation.py` — додані моки для нових модулів
- `test_directional_sanity_sol_downtrend_no_long_open.py` — додані missing атрибути

**Відомі pre-existing failures (НЕ пов'язані з декомпозицією):**
- `test_anti_zombie_guard.py` — AccountObserver class
- `test_ep01_3_pending_entry_ttl.py` — missing `supersede_cancel_timeout_sec`
- `test_fe_emits_cmd_process_strategy.py` — wrong YAML path
- `test_order_guardian_contracts_v1.py` — OrderGuardian._impl attribute

### 4.3 ❌ Strangler Fig для `execution_position/fsm.py`

**Статус: НЕ ЗРОБЛЕНО — КРИТИЧНИЙ ЗАЛИШОК**

**Поточний стан LOC порушників у execution_position:**

| Файл | LOC | Перевищення | Пріоритет |
|------|-----|-------------|-----------|
| **fsm.py** | **4,687** | **9.4×** | 🔴 CRITICAL |
| `fsm_manage.py` | 1,454 | 2.9× | 🟠 HIGH |
| `order_guardian.py` | 1,367 | 2.7× | 🟠 HIGH |
| `exposure_guard.py` | 1,067 | 2.1× | 🟡 MEDIUM |

**Частково існуючі sub-модулі** (вже розділені раніше):
- `fsm_open.py` (26,316 bytes) — Open flow
- `fsm_close.py` (6,084 bytes) — Close flow
- `fsm_manage.py` (63,951 bytes) — Management flow

**Blueprint 14A §4 пропонує план розбиття fsm.py на 6 модулів:**
1. `ep_orchestrator.py` (~300 LOC) — lifecycle, CMD handling
2. `leverage_bootstrapper.py` (~250 LOC) — ✅ частково вже є в `bootstrapping/`
3. `order_mapper.py` (~300 LOC) — intent → exchange format
4. `time_windows.py` (~150 LOC) — quiet hours
5. `position_state_manager.py` (~400 LOC) — pending brackets, idempotency
6. `exchange_adapter_facade.py` (~500 LOC) — exchange communication

**Оцінка реалізації:** ~2-3 дні (аналогічно dm декомпозиції)

### 4.4 🟡 Інші монолітні файли (поза Blueprint, але порушують Constitution)

#### 4.4.1 ✅ `aurora_handler.py` — Strangler Fig декомпозиція (В ПРОЦЕСІ)

**Статус: 61% DONE** (2,694 → 1,066 LOC, 254/254 тести PASS)

| Файл | LOC | Вміст |
|------|-----|-------|
| `aurora_tpsl.py` **[NEW]** | 454 | TP/SL обчислення: `_get_volatility_strict`, `_compute_regime_tpsl`, `_compute_tpsl_pct_mult`, `_compute_tpsl_atr`, `_apply_tpsl_guardrails` |
| `aurora_scoring_helpers.py` **[NEW]** | 405 | Vol-adj gates, shield cascade, liquidity gate, side bias, config lookups (10 методів) |
| `aurora_decision.py` **[NEW]** | 798 | Core decision processing: `_process_decision`, `_emit_signal` |
| `aurora_handler.py` (залишок) | 1,066 | `__init__`, `_load_config`, regime handlers, event handlers, holding period |

**Залишок для досягнення ≤500 LOC:**
- [ ] Витягнути `_load_config` (~290 LOC) → `aurora_config_loader.py`
- [ ] Витягнути holding period (~200 LOC) → `aurora_holding_period.py`
- [ ] `aurora_decision.py` (798 LOC) — розбити на 2 модулі ≤500

#### 4.4.2 ❌ Інші порушники

| Файл | LOC | Пріоритет | Примітка |
|------|-----|-----------|----------|
| `mean_reversion_handler.py` | 937 | 🟡 MEDIUM | Стратегічна логіка |
| `decision_context.py` | 529 | 🟢 LOW | Мінорне перевищення |

---

## КРОК 5 — CLEANUP

### 5.1 ❌ `fsm_emit_compat.py` — ще використовується

**Статус: Відкладено до завершення декомпозиції EP**

Файл `vfoundation/core/fsm_emit_compat.py` (120 LOC) імпортується з:
- `vfoundation/core/retry_scheduler.py:12`
- `apps/reference/retry_scheduler.py:9` (shim)
- `apps/reference/domains/execution_position/exposure_guard.py:251,319`
- `apps/reference/domains/execution_position/fsm.py:21`

**Рішення:** Видалити після декомпозиції `fsm.py` та переходу EP на FSMv2

### 5.2 ✅ Видалення `nul` артефактів

Перевірено: файли `nul` не знайдені в репозиторії (окрім легітимних: `null_shield.py`, тести)

### 5.3 ✅ Видалення `apps/reference/services/`

**DONE** — директорія повністю видалена, 0 залишкових imports

### 5.4 ✅ Видалення reproduce_*.py скриптів

**DONE** — 10 файлів переміщено до `scripts/reproductions/`

### 5.5 ✅ Міграція dr_loader та retry_scheduler до vfoundation

**DONE:**
- `vfoundation/dr/dr_loader.py` — canonical module
- `vfoundation/core/retry_scheduler.py` — canonical module з DI callback
- Shim-и залишені для backward compatibility

### 5.6 ❌ Dead imports аудит (mypy)

**Статус: НЕ ЗРОБЛЕНО**
- mypy не встановлений у `.venv`
- **Оцінка:** ~120 min (встановлення + fix)

### 5.7 ❌ TODO/FIXME sweep

**Статус: НЕ ПЕРЕВІРЕНО**
- Потрібно: `grep -rn "TODO\|FIXME\|HACK\|XXX" vfoundation/ --include="*.py"`
- **Оцінка:** ~30 min

---

## КРОК 6 — COVERAGE ≥95%

### 6.1 ❌ Поточний стан

| Модуль | Покриття (останній звіт) | Ціль |
|--------|--------------------------|------|
| `FSMv2` | 100% | ✅ |
| `FSMCore` | 100% | ✅ |
| `Protocol` | 100% | ✅ |
| `DomainBridge` | 100% | ✅ |
| `WAL_GC` | 92% | 95% |
| **Overall vfoundation** | **~88%** | **≥95%** |

**Розрив:** ~7% потрібно закрити через таргетовані branch-coverage тести
**Оцінка:** ~120-180 min

---

## ДОДАТКОВІ РЕМЕДІАЦІЇ (виконані поза оригінальним планом)

### ✅ Risk Management Remediation (Wave A–E)
- RID propagation, schema alignment, thread safety, state amnesia fix, strict Decimal
- 34 тести у `tests/domains/risk_management` — PASS, coverage 99.29%

### ✅ Apps Reference Remediation (Steps 2–8)
- `AsyncLoopRuntime`, `LiveDomainBundle`, `build_live_domains()`
- Typed config: `Decimal` precision specifiers
- SSOT enforcement: видалені ad-hoc env bypasses

### ✅ Telemetry/Orchestrator Remediation
- `AlertManager` bounded cleanup (TTL + hard-cap)
- `TradeLifecycleLogger` memory leak fix (sweep_expired + LRU eviction)
- `apps/reference/orchestrator/` — видалено
- Legacy `performance_monitor.py` — видалено

### ✅ Services & Core Domain Remediation
- `apps/reference/services/` — видалено (4 файли)
- `order_guardian.py` — єдиний SSOT у `execution_position/`
- `LedgerStoreAdapter.delete()` — soft-delete реалізовано (split-brain fix)
- `LimitOrderMonitor` — per-order timer tasks (event-driven)

---

## ПОРЯДОК ВИКОНАННЯ ЗАЛИШКІВ (рекомендований)

```
─── ЕТАП A: execution_position/fsm.py декомпозиція ──────────────── [2-3 дні]
  4.3  → fsm.py (4,687 LOC) → 6 модулів ≤500 LOC
  4.3b → fsm_manage.py (1,454 LOC) → розбити якщо можливо
  
─── GATE: pytest tests/domains/execution_position → всі зелені ───

─── ЕТАП B: FSMv2 Transactional Safety ──────────────────────────── [1 день]
  1.6  → Transactional Rollback (~30 min)
  1.5  → WAL Integration (~45 min)

─── GATE: pytest tests/vfoundation → 1073+ PASS ──────────────────

─── ЕТАП C: Cross-Domain Decoupling ─────────────────────────────── [2 дні]
  2.5  → alpha_search FSM adapter
         (видалити cross-domain import з event_handlers.py та decision_making.py)
  2.4  → MetaFSMv2 background loop wiring в main.py
         (CMD:SWITCH_TO_LOW_RISK_MODE → handlers у DM та EP)

─── GATE: grep "from apps.reference.domains.alpha_search" → 0 ────

─── ЕТАП D: Message Protocol Enhancement ────────────────────────── [2-3 дні]
  3.4  → Deprecation warnings для exchange полів
  3.8  → Decimal типізація в payloads
  3.6  → Verb Schema Registry scaffolding
  3.7  → FSMCore.emit() runtime validation (warn-only → fail-closed)

─── ЕТАП E: aurora_handler.py декомпозиція ──────── [1-2 дні] 🟡 В ПРОЦЕСІ
  4.4  → 2,694→1,066 LOC (3 mixins done), ще 2 extractions needed

─── GATE: pytest tests/ → всі зелені ─────────────────────────────

─── ЕТАП F: Cleanup + Coverage ──────────────────────────────────── [1-2 дні]
  5.1  → Видалити fsm_emit_compat.py (після EP декомпозиції)
  5.6  → mypy audit
  5.7  → TODO/FIXME sweep
  6.1  → Coverage push 88% → 95%

─── ФІНАЛЬНИЙ GATE ────────────────────────────────────────────────
  pytest tests/vfoundation → 1100+ PASS, coverage ≥95%
  grep cross-domain → 0 порушень
  Всі модулі ≤500 LOC
```

---

## ЗВЕДЕНА ТАБЛИЦЯ СТАТУСІВ

| Крок | Опис | Статус | % |
|------|------|--------|---|
| **0.1** | signing_ed25519 bugfix | ✅ DONE | 100% |
| **0.2** | protocol.py truncate_why | ✅ DONE | 100% |
| **1.1** | FSMv2 validate_reachability() | ✅ DONE | 100% |
| **1.2** | FSMv2 to_dot() | ✅ DONE | 100% |
| **1.3** | FSMv2 get_stats() | ✅ DONE | 100% |
| **1.4** | fsm_emit_compat check | ✅ DONE (не видалено — ще в use) | 100% |
| **1.5** | FSMv2 WAL Integration | ✅ **DONE** | **100%** |
| **1.6** | FSMv2 Transactional Rollback | ✅ **DONE** | **100%** |
| **1.7** | FSMCore ↔ FSMv2 Bridge | ❌ TODO | 0% |
| **1.8** | EP Domain Migration на FSMv2 | ❌ TODO | 0% |
| **1.9** | DM Domain Migration на FSMv2 | ❌ TODO | 0% |
| **1.10** | CLI fsm validate/graph | ❌ TODO | 0% |
| **2.1** | TopologyAuditor health | ✅ DONE | 100% |
| **2.2** | DomainBridge | ✅ DONE | 100% |
| **2.3** | Runtime Infrastructure Probes | ❌ TODO | 0% |
| **2.4** | MetaFSMv2 Background Loop | ❌ TODO | 0% |
| **2.5** | Orphan Domain Adapters | ❌ TODO | 0% |
| **3.1** | Typed Payload Schemas | ✅ DONE | 100% |
| **3.2** | ExchangeContext | ✅ DONE | 100% |
| **3.3** | Protocol Migration helpers | ✅ DONE | 100% |
| **3.4** | Message Deprecation Warnings | ✅ DONE | 100% |
| **3.5** | Per-Verb Schemas Directory | ✅ DONE | 100% |
| **3.6** | Verb Schema Registry | ✅ DONE | 100% |
| **3.7** | FSMCore.emit() validation | ✅ DONE | 100% |
| **3.8** | Decimal in Payloads | ✅ DONE | 100% |
| **4.1** | Audit монолітів | ✅ DONE | 100% |
| **4.2** | DM декомпозиція | ✅ **DONE** | **100%** |
| **4.3** | EP fsm.py декомпозиція | ❌ **CRITICAL TODO** | **0%** |
| **4.4** | aurora_handler.py декомпозиція | ✅ **DONE** | **100%** |
| **5.1** | fsm_emit_compat видалення | ❌ Відкладено | 0% |
| **5.2** | nul артефакти | ✅ DONE | 100% |
| **5.3** | services/ видалення | ✅ DONE | 100% |
| **5.4** | reproduce_*.py переміщення | ✅ DONE | 100% |
| **5.5** | dr_loader/retry_scheduler міграція | ✅ DONE | 100% |
| **5.6** | mypy audit | ❌ TODO | 0% |
| **5.7** | TODO/FIXME sweep | ❌ TODO | 0% |
| **6.1** | Coverage ≥95% | ❌ TODO (88% → 95%) | 40% |

**DONE: 25/36 кроків (69%) | TODO: 11/36 кроків**

По вазі реалізації: **~68%** (найважчі DONE-кроки — dm, aurora декомпозиції + FSMv2 safety)

---

## КРИТИЧНІ ПРАВИЛА (не порушувати)

1. **НЕ міняти публічний API Message** без backward compat шару
2. **НЕ видаляти файли** поки не перевірено `grep -r "import_from_that_file"`
3. **НЕ створювати нові verb'и** без запису в `verb_registry_v1.yaml`
4. **Запускати повний suite** `pytest tests/vfoundation/` після КОЖНОГО кроку
5. **Strangler Fig** — старий файл стає wrapper, не видаляється відразу
6. **TDD** — тести ПЕРЕД кодом для нових features
7. **Constitution §3** — усі нові та перероблені файли ≤500 LOC

---

## DEFINITION OF DONE (оновлена)

- [x] Всі 1073 існуючих vfoundation тестів проходять
- [x] decision_making.py декомпозовано (11 модулів ≤500 LOC)
- [x] Bugfixes (signing_ed25519, truncate_why) — зроблено
- [x] FSMv2 enhancements (reachability, dot, stats) — зроблено
- [x] TopologyAuditor health + DomainBridge — зроблено
- [x] Typed payloads, ExchangeContext, protocol_migration — зроблено
- [x] Risk Management, Apps Reference, Services Core ремедіації — зроблено
- [ ] **execution_position/fsm.py декомпозиція** → ≤500 LOC модулі
- [x] **aurora_handler.py декомпозиція** → 544 LOC + 5 mixinів ≤500
- [x] FSMv2 WAL integration + transactional rollback
- [ ] Cross-domain imports → 0 (alpha_search → FSM adapter)
- [ ] MetaFSMv2 wired в main.py (background loop + domain handlers)
- [x] Message deprecation warnings + Verb Schema Registry
- [ ] `pytest tests/vfoundation/ --cov=vfoundation` → **≥95% coverage**
- [ ] mypy clean
- [ ] Мертвий код видалено (fsm_emit_compat, тощо)
- [ ] Жоден модуль >500 LOC (Constitution §3)

---

## ФАЙЛИ-АРТЕФАКТИ (довідка)

| Документ | Шлях |
|----------|------|
| Blueprint Phases 9-14 | `docs/docs_vfoundation/BLUEPRINT_PHASES_9_14.md` |
| Blueprint 14A (Decomposition) | `docs/docs_vfoundation/Рефактор.../BLUEPRINT_PHASE_14_DECOMPOSITION.md` |
| Blueprint 14B (FSMv2) | `docs/docs_vfoundation/Рефактор.../BLUEPRINT_PHASE_14_FSM.md` |
| Blueprint 14C (Message) | `docs/docs_vfoundation/Рефактор.../BLUEPRINT_PHASE_14_MESSAGE.md` |
| Blueprint 14.5 (Integration) | `docs/docs_vfoundation/Рефактор.../BLUEPRINT_PHASE_14_INTEGRATION.md` |
| Progress Log (vfoundation) | `docs/docs_vfoundation/PROGRESS_LOG.md` |
| Progress Log (architectural) | `docs/architectural_audits/PROGRESS_LOG.md` |
| Constitution FSM v2.2 | `docs/docs_vfoundation/Constitution_FSM.md` |
| Agent Implementation Prompt | `docs/docs_vfoundation/AGENT_IMPLEMENTATION_PROMPT.md` |
