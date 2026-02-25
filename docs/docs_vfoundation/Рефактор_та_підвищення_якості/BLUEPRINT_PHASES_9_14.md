# vFoundation Engineering Blueprint — Phases 9–18

**Дата:** 2026-02-20 (v1.1 errata: 2026-02-21, v1.2: 2026-02-21, v1.3: 2026-02-22, **v1.4: 2026-02-24**)
**Базується на:** [ROADMAP_HARDENING.md](ROADMAP_HARDENING.md), [Аудит.md](Аудит.md), [Constitution_FSM.md](Constitution_FSM.md)
**Передумова:** Фази 0–8 завершені (531 тест, 0 збоїв, 37/43 модулів покрито)
**Принцип:** Additive-first → cleanup → refactor. Не зламати працюючу систему.

> **v1.1 Errata (2026-02-21):** Після незалежного аудиту blueprint'у виявлено 4 HIGH, 3 MEDIUM, 3 LOW знахідки.
> Всі виправлення інтегровані в цей документ. Додано Phase 9.0 (передумови/залежності),
> виправлено шляхи, усунено кругові залежності, додано verb registry кроки.
> Повний аудит — див. [Додаток A: Незалежний аудит](#додаток-a-незалежний-аудит-blueprint-v10).
>
> **v1.2 Errata (2026-02-21):** Другий незалежний архітектурний аудит (Gemini) підтвердив
> точність Blueprint'у та виявив 1 нову знахідку: `FSMCore.emit()` генерує новий `rid`
> замість passthrough — розриває кореляцію на рівні envelope (бізнес-rid зберігається в `pld`).
> Додано Phase 9.0.4. Gemini-claim про "ExecPosFSM drops price_ctx" — **спростовано** кодом.
> Повний аудит — див. [Додаток B: Архітектурний аудит (Gemini)](#додаток-b-архітектурний-аудит-gemini).
>
> **v1.3 Errata (2026-02-22):** Третій незалежний аудит (Staff Architect) — найглибший з трьох.
> 20 конкретних клеймів верифіковано, скоринг 5.1/10, вердикт **No-Go** без Pre-Phase 9 hardening.
> **Ключова нова знахідка:** `_cli_root` у CLI резолвиться в `vfoundation/`, а не repo root —
> Phase 9.0.2 fix був неповним. Також виявлені: Constitution protocol drift (v=1 vs v=2,
> data_ref schema), dependency SSOT bifurcation, 5 collection errors у broader suite,
> idempotency tests globally skipped. Додано Phases 9.0.5–9.0.8, оновлено Phase 9.0.2.
> Повний аудит — див. [Додаток C: Staff Architect аудит](#додаток-c-staff-architect-аудит).
>
> **v1.4 Gap Analysis (2026-02-24):** Після виконання агентом Phases 9–13 (712 tests, 0 failures),
> проведено honest-assessment загальної готовності vFoundation. **Висновок: library completeness ~70%,
> а не ~90%.** 90% стосувалось лише виконання Blueprint Phases 9–13. Для досягнення справжніх 90%
> library completeness додано Phases 15–17: CLI Completeness (§10.2), Schema Versioning & Protocol v2
> Infrastructure (§5, §10.4), Cross-cutting Production Contracts (§8, §11, audit concerns).
> Також зафіксовано 2 залишкові gaps від Phases 9–13: `fsm.py` не видалено (Phase 9.4),
> `drift` command без тестів. Повний gap analysis — див. [Gap Analysis: Шлях до 90%](#gap-analysis-шлях-до-90-vfoundation).

---

## Зміст

| Phase | Назва | Пріоритет | Орієнтовні тести |
|-------|-------|-----------|-------------------|
| **9.0** | P0 Prerequisites (deps, paths, rid, ADR, suite) | CRITICAL | 0 |
| **9** | P0 Coverage + Cleanup | CRITICAL | +65–75 |
| **10** | P1 Audit Closure + Tooling | HIGH | +30–40 |
| **11** | P2 Observability Hardening | MEDIUM | +25–35 |
| **12** | P3 Constitution §12 Quality Gates | MEDIUM | +20–30 |
| **13** | P4 Constitution §7–§10 Feature Gaps | LOW | +15–25 |
| **14** | P5 Deferred Refactoring (4.2–5.4) | HIGH | varies |
| **15** | P6 Cleanup + CLI Completeness (§10.2) | MEDIUM | +20–25 |
| **16** | P7 Schema Versioning & Protocol v2 Infra (§5, §10.4) | HIGH | +25–35 |
| **17** | P8 Cross-cutting Production Contracts (§8, §11) | MEDIUM | +20–25 |

> **v1.4 UPDATE:** Phases 9–13 виконані (712 tests). Phase 14 залишається planned.
> Phases 15–17 додані для досягнення 90% library completeness.

**Прогнозований підсумок:** ~810–840 тестів, ≥90% library completeness, 0 Constitution gaps відкритих.

---

# Phase 9.0 — P0 Prerequisites: Dependencies & Path Fixes

**Ціль:** Виправити залежності та зламані шляхи ДО початку тестування. Без цієї фази Phase 9.1 та 9.2 не можуть працювати.

**Передумова:** 531 passed, 0 failed.
**Очікуваний результат:** 531 passed, 0 failed. Залежності задекларовані. Шляхи коректні.

---

### Phase 9.0.1 — Задекларувати відсутні залежності

**Проблема (HIGH):** `fakeredis[lua]` встановлений у venv, але **не задекларований** у `requirements.txt`. Аналогічно `pynacl` — CLI `__main__.py` імпортує `from vfoundation.security.signing_ed25519 import sign` на рівні модуля, що падає без PyNaCl.

**Кроки:**

1. Додати до `requirements.txt` секцію dev-deps:
   ```
   # Dev/test dependencies
   fakeredis[lua]>=2.0.0
   PyNaCl>=1.5.0
   ```
2. Перевірити інсталяцію:
   ```bash
   pip install -e . -r requirements.txt
   python -c "import fakeredis; print(fakeredis.__version__)"
   python -c "import nacl; print(nacl.__version__)"
   ```
3. Gate: `pytest tests/vfoundation -q` → 531 passed, 0 failed (нічого не зламано)

---

### Phase 9.0.2 — Виправити CLI root resolution + drift path

**Проблема (CRITICAL):** `vfound drift` (line 289 у `cli/__main__.py`) має **дві** помилки:

**Помилка A (root-cause, v1.3):** `_cli_root` (line 13) резолвиться в `vfoundation/`, а не repo root:
```python
# __file__ = vfoundation/cli/vfound/__main__.py
_cli_root = pathlib.Path(__file__).parent.parent.parent.resolve()
# parent = vfoundation/cli/vfound/
# parent.parent = vfoundation/cli/
# parent.parent.parent = vfoundation/   ← НЕ repo root!
```
Тому `_cli_root / "apps"` → `vfoundation/apps/` — директорія **НЕ ІСНУЄ**.
Навіть з коректним subpath `vfound drift` завжди падає: `FileNotFoundError`.

> **Джерело:** Staff Architect аудит (v1.3), claim #1. Попередній Phase 9.0.2 (v1.1) фіксив
> лише subpath, але не root-cause.

**Помилка B (subpath, v1.1):** Навіть якщо root виправлений, хардкод `apps/monitoring/drift_monitor.py` хибний.
Реальний шлях: `apps/reference/domains/execution_position/drift_monitor.py`.

**Кроки:**

1. В `vfoundation/cli/vfound/__main__.py` (line 13) — виправити root resolution:
   ```python
   # OLD (broken — resolves to vfoundation/, not repo root):
   _cli_root = pathlib.Path(__file__).parent.parent.parent.resolve()
   # NEW (correct — go 4 levels up to repo root):
   _cli_root = pathlib.Path(__file__).parent.parent.parent.parent.resolve()
   # vfoundation/cli/vfound/__main__.py → .parent⁴ → repo root
   ```
2. В `vfoundation/cli/vfound/__main__.py` (line 289) — виправити subpath:
   ```python
   # OLD (broken subpath):
   drift_monitor_path = (_cli_root / "apps" / "monitoring" / "drift_monitor.py")
   # NEW (correct subpath):
   drift_monitor_path = (_cli_root / "apps" / "reference" / "domains" / "execution_position" / "drift_monitor.py")
   ```
3. Перевірити що `sys.path` inserts (lines 15-18) ще коректні після зміни `_cli_root`:
   - `_cli_root` тепер = repo root → `sys.path.insert(0, str(_cli_root))` — **ОК** (для `apps.reference.*`)
   - `_vfoundation_pkg = _cli_root / "vfoundation"` → repo_root/vfoundation/ — **ОК**
4. Gate: `python -c "from vfoundation.cli.vfound.__main__ import _cli_root; print(_cli_root)"` → repo root
5. Gate: `python -m vfoundation.cli.vfound --help` → no crash
6. Gate: `pytest tests/vfoundation -q` → 531 passed

---

### Phase 9.0.3 — Оновити debug_api.py docstring

**Проблема (LOW):** `vfoundation/obs/debug_api.py` line 101 також містить застарілий шлях:
```python
Store a DriftReport (apps/monitoring/drift_monitor.py).
```

**Кроки:**

1. Замінити коментар на:
   ```python
   Store a DriftReport (apps/reference/domains/execution_position/drift_monitor.py).
   ```
2. Gate: `pytest tests/vfoundation -q` → 531 passed

---

### Phase 9.0.4 — Виправити FSMCore.emit() rid passthrough

**Проблема (MEDIUM):** `FSMCore.emit()` ([fsm_core.py](../../vfoundation/core/fsm_core.py) line 56) створює `Message()` без передачі `rid`. Оскільки `Message.rid` має `default_factory=lambda: str(uuid.uuid4())`, кожен emit генерує новий UUID.

**Наслідки:**
- WAL-записи та observability tools що читають `msg.rid` (а не `pld["rid"]`) **втрачають кореляцію** з оригінальним бізнес-RID.
- Бізнес-логіка НЕ зламана — `DecisionMaking` зберігає `rid` в `pld["rid"]`, і ExecPosFSM читає саме звідти.
- Це **envelope-level traceability gap**, не data loss.

> **Джерело:** Архітектурний аудит (Gemini), підтверджено верифікацією коду.
> Claim про "ExecPosFSM drops price_ctx" з того ж аудиту — **спростовано**:
> `_smart_extract()` (fsm.py lines 740–770) явно витягує дані з `price_ctx` nested dict.

**Кроки:**

1. В `vfoundation/core/fsm_core.py`, метод `emit()` — додати параметр `rid`:
   ```python
   # OLD (line 41):
   def emit(self, event_name: str, payload: Dict[str, Any], why: str, data_ref: Optional[List[str]] = None) -> None:
   # NEW:
   def emit(self, event_name: str, payload: Dict[str, Any], why: str, data_ref: Optional[List[str]] = None, rid: Optional[str] = None) -> None:
   ```
2. В тілі emit, передати rid до Message:
   ```python
   # OLD (line 56):
   message = Message(
       op="EVT",
       verb=event_name.split(":")[1],
       src="fsm_core",
       dst="any",
       pld=payload,
       why=why,
       data_ref=data_ref or [],
   )
   # NEW:
   msg_kwargs: Dict[str, Any] = dict(
       op="EVT",
       verb=event_name.split(":")[1],
       src="fsm_core",
       dst="any",
       pld=payload,
       why=why,
       data_ref=data_ref or [],
   )
   if rid is not None:
       msg_kwargs["rid"] = rid
   message = Message(**msg_kwargs)
   ```
3. **НЕ змінювати** жоден існуючий виклик `fsm.emit()` — `rid=None` зберігає поточну поведінку (backward-compatible).
4. Gate: `pytest tests/vfoundation -q` → 531 passed, 0 failed
5. Gate: `pytest tests/ -q --ignore=tests/backtest` → no regressions

**Підсумок Phase 9.0.4:** 0 нових тестів, ~10 LOC зміна, backward-compatible.

---

### Phase 9.0.5 — Dependency SSOT alignment (requirements.txt ↔ pyproject.toml)

**Проблема (MEDIUM):** Два джерела правди для залежностей:
- `requirements.txt` — 19 рядків, **НЕ має** `redis`, `PyNaCl`, `fakeredis`, `structlog`, `opentelemetry-*`
- `vfoundation/pyproject.toml` — **МАЄ** `PyNaCl>=1.5`, `redis>=5.0`, `fakeredis>=2.21` (test)

Це спричиняє drift: CI може встановлювати різні набори залежностей залежно від способу інсталяції.

> **Джерело:** Staff Architect аудит (v1.3), claim #2. Gemini аудит також зафіксував.

**Рішення — визначити SSOT:**

Phase 9.0.1 додає `fakeredis[lua]` та `PyNaCl` до `requirements.txt`, але це не вирішує кореневу проблему.
Потрібна **явна політика** dependency management:

**Кроки:**

1. Визначити `vfoundation/pyproject.toml` як **canonical SSOT** для пакету vfoundation
2. `requirements.txt` (repo root) — зберегти як **aggregator** для всього проєкту (включає non-vfoundation deps: pandas, numpy, websockets, etc.)
3. Додати до `requirements.txt` відсутні production deps:
   ```
   # vfoundation core (mirror of pyproject.toml[dependencies])
   redis>=5.0
   structlog>=24.1
   opentelemetry-sdk>=1.26
   ```
4. Додати коментар-маркер у `requirements.txt`:
   ```
   # ⚠️ SSOT for vfoundation package deps: vfoundation/pyproject.toml
   # This file aggregates ALL project deps (vfoundation + apps + tools)
   ```
5. Перевірити `fakeredis[lua]>=2.0.0` (з Phase 9.0.1) — pyproject.toml має `fakeredis>=2.21` (без `[lua]`). Вирівняти:
   ```toml
   # pyproject.toml [project.optional-dependencies] test:
   "fakeredis[lua]>=2.21"
   ```
6. Gate: `pip install -e vfoundation -r requirements.txt` → no conflicts
7. Gate: `pytest tests/vfoundation -q` → 531 passed

---

### Phase 9.0.6 — Constitution protocol drift ADR

**Проблема (HIGH):** Contract drift між Constitution FSM.md та runtime Message model:

| Поле | Constitution (§5.2) | Код (`protocol.py`) | Drift |
|------|---------------------|---------------------|-------|
| `v` | `2` | `1` | **Version mismatch** |
| `data_ref` | `[{uri, sha256, bytes, ctype, ttl_ms}]` | `List[str]` | **Schema structural mismatch** |
| `sig` | "обов'язковий для CMD/DEC" (§11) | `Optional[str] = None` | Enforcement gap |

> **Джерело:** Staff Architect аудит (v1.3), claim #3 (arch gap #3).
> Жоден попередній аудит це не виявив.

**Стратегія:** Це **не runtime fix** (breaking change). Потрібен ADR (Architecture Decision Record) який:
- Фіксує поточний drift як відомий
- Визначає migration path для v=1→v=2
- Задає data_ref target schema
- Визначає enforcement timeline для sig

**Кроки:**

1. Створити `docs/ADR-003-message-protocol-drift.md`:
   ```markdown
   # ADR-003: Message Protocol Drift (v=1 vs Constitution v=2)
   
   ## Status: ACCEPTED
   ## Context: Constitution §5.2 defines v=2 with object data_ref; runtime uses v=1 with List[str]
   ## Decision: 
   - Phase 14.3 буде bump v=1→v=2 разом з envelope refactor
   - data_ref migration: List[str] → List[DataRef] (Pydantic model)
   - sig enforcement: додати warning validator у Phase 14.3 (CMD/DEC without sig → DeprecationWarning)
   ## Consequences: До Phase 14.3 drift відомий і задокументований
   ```
2. Додати посилання на ADR в Constitution_FSM.md (як footnote до §5.2)
3. Gate: `pytest tests/vfoundation -q` → 531 passed (documentation-only change)

---

### Phase 9.0.7 — Виправити broader test suite collection errors

**Проблема (MEDIUM):** `pytest tests/ -q --ignore=tests/backtest` дає **5 collection errors**:
```
ERROR tests/integration/test_startup_filters_wiring.py
ERROR tests/integration/test_statdump_endpoint.py - AttributeError: __path__
ERROR tests/test_circuit_breaker.py
ERROR tests/test_coverage_boost.py
ERROR tests/test_exact_90_percent.py
```
Причина: `vfoundation.core is not a package` — namespace package collision. Коли Python бачить
`vfoundation/core/` і `tests/` з `sys.path` manipulation, imports ламаються у broader suite.

> **Джерело:** Staff Architect аудит (v1.3), claim #13.

**Стратегія:** Це системна проблема з package boundaries, не одноразовий fix. Повне рішення —
Phase 14 scope. Але мінімальний fix можливий:

**Кроки:**

1. Перевірити чи `tests/test_circuit_breaker.py`, `tests/test_coverage_boost.py`, `tests/test_exact_90_percent.py` дублюють покриття з `tests/vfoundation/`:
   - Якщо так — **видалити** (вони legacy з до-vfoundation ери)
   - Якщо ні — виправити imports
2. Перевірити `tests/integration/` — чи потрібні ці тести для vfoundation gate:
   - Якщо ні — додати `conftest.py` з `collect_ignore` або `pytest.ini` marker
3. Мінімальний gate: `pytest tests/ -q --ignore=tests/backtest` → 0 collection errors
4. Gate: `pytest tests/vfoundation -q` → 531 passed (не погіршити)

**Підсумок:** Мета — 0 collection errors у broader suite. Якщо файли-дублікати — видалити.

---

### Phase 9.0.8 — Активувати або перенести idempotency тести

**Проблема (MEDIUM):** `tests/idempotency/__init__.py` має module-level `pytest.skip()`:
```python
pytest.skip("Idempotency tests - complex distributed setup", allow_module_level=True)
```
Це **глобально вимикає** всі тести в `tests/idempotency/`. Active gate (`tests/vfoundation`) не покриває Redis/Lua idempotency path, створюючи **хибну впевненість** що exactly-once працює.

> **Джерело:** Staff Architect аудит (v1.3), claim #2 (arch gap #2).

**Стратегія:** Phase 9.1 створює **повноцінну test suite** для `redis_store.py` в `tests/vfoundation/`.
Після Phase 9.1 — `tests/idempotency/` стає redundant.

**Кроки:**

1. Перевірити вміст `tests/idempotency/` — що саме тестується, скільки тестів
2. Якщо тести дублюють Phase 9.1 scope → залишити skip, видалити після Phase 9.1
3. Якщо тести покривають унікальні сценарії → мігрувати в `tests/vfoundation/core/`
4. Додати коментар до `tests/idempotency/__init__.py`:
   ```python
   # NOTE: These tests are superseded by tests/vfoundation/core/test_redis_store.py (Phase 9.1)
   # This module will be removed after Phase 9.1 completion.
   ```
5. Gate: `pytest tests/vfoundation -q` → 531 passed

---

**Підсумок Phase 9.0:** 0 нових тестів, 2 path fixes (root + subpath), 2 dependency declarations,
1 rid passthrough fix, 1 dependency SSOT policy, 1 protocol drift ADR, 1 suite stability fix,
1 idempotency test activation plan.

---

# Phase 9 — P0 Coverage + Deprecated Cleanup

**Ціль:** Закрити два критичні непокритих модуля (`redis_store.py` 554 LOC, `cli/__main__.py` 421 LOC), видалити legacy код.

**Передумова:** Phase 9.0 complete. 531 passed, 0 failed.
**Очікуваний результат:** ~596–610 passed, 0 failed. MockExecutionAdapter перенесений. fsm.py видалений.

---

### Phase 9.1 — `redis_store.py` тести (fakeredis + Lua)

**Чому P0:** Це production exactly-once idempotency backend з 3 Lua-скриптами (`RESERVE_SCRIPT`, `CONFIRM_SCRIPT`, `RELEASE_SCRIPT`). 554 LOC — **найбільший непокритий модуль**. Lua-логіка не верифікована жодним тестом.

**Файл:** `tests/vfoundation/core/test_redis_store.py`
**Залежності:** `fakeredis[lua]` (задекларовано в Phase 9.0.1)

#### Етап 9.1.1 — Підготовка та scaffold

1. Перевірити що `fakeredis[lua]` доступний:
   ```python
   import fakeredis
   server = fakeredis.FakeServer()
   r = fakeredis.FakeRedis(server=server, decode_responses=True)
   r.ping()
   ```
2. Створити test fixture `@pytest.fixture` який:
   - Піднімає `fakeredis.FakeServer()`
   - Створює `RedisIdempotencyStore(redis_url="redis://localhost", worker_id="test-w1")`
   - **Monkey-patch** `redis.from_url` → повертає `FakeRedis` (бо конструктор викликає `redis.from_url()`)
   - Alternative: параметризувати конструктор для прийняття `client` напряму (якщо monkey-patch надто крихкий)
3. Перевірити що `self.client.ping()` працює з fakeredis + Lua-скрипти загружаються

#### Етап 9.1.2 — Reserve операція (Lua: `RESERVE_SCRIPT`)

Тести (мінімум 8):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_reserve_new_returns_NEW` | Нового ключа → `ReserveStatus.NEW`, `lease_ms` = заданий TTL |
| 2 | `test_reserve_duplicate_same_idempotent` | Повторний reserve з тим самим `key+owner+digest` → `DUPLICATE_SAME` |
| 3 | `test_reserve_duplicate_conflict_raises` | Повторний reserve з іншим `payload_digest` → `ConflictError` |
| 4 | `test_reserve_extern_owner_raises` | Інший worker → `BusyError` з owner info |
| 5 | `test_reserve_metrics_updated` | Після reserve metrics counters коректні (`idemp_reserve_total["NEW"] == 1`) |
| 6 | `test_reserve_ttl_expiry_then_new` | Після TTL expiry → reserve того ж ключа дає `NEW` (Redis PEXPIRE) |
| 7 | `test_reserve_records_latency` | `metrics.idemp_reserve_latency_ms_p50` > 0 після операції |
| 8 | `test_reserve_redis_error_triggers_retry` | Мокаємо redis error на 1-й спробі, 2-а успішна → retry працює |

#### Етап 9.1.3 — Confirm операція (Lua: `CONFIRM_SCRIPT`)

Тести (мінімум 6):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_confirm_held_record` | reserve → confirm → `ConfirmStatus.CONFIRMED` |
| 2 | `test_confirm_missing_key_raises` | confirm без reserve → `MissingError` |
| 3 | `test_confirm_with_meta` | confirm з `meta={"result": "ok"}` → record зберігає meta |
| 4 | `test_confirm_without_meta` | confirm без meta → status CONFIRMED, meta absent |
| 5 | `test_confirm_metrics_updated` | `idemp_confirm_total["CONFIRMED"]` incremented |
| 6 | `test_confirm_records_latency` | Latency metric записана |

#### Етап 9.1.4 — Get Status операція

Тести (мінімум 5):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_get_status_empty` | Неіснуючий ключ → `GetStatus.EMPTY` |
| 2 | `test_get_status_held` | Після reserve → `GetStatus.HELD`, owner correct |
| 3 | `test_get_status_confirmed` | Після confirm → `GetStatus.CONFIRMED`, meta present |
| 4 | `test_get_status_returns_payload_digest` | `payload_digest` field коректний |
| 5 | `test_get_status_returns_ts_ns` | `ts_ns` > 0, reasonable value |

#### Етап 9.1.5 — Release операція (Lua: `RELEASE_SCRIPT`)

Тести (мінімум 5):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_release_held_record` | reserve → release → `ReleaseStatus.RELEASED` |
| 2 | `test_release_missing_raises` | release неіснуючого → `MissingError` |
| 3 | `test_release_wrong_owner_raises` | reserve worker-A → release worker-B → `StoreError` ("owner mismatch") |
| 4 | `test_release_cleans_redis_key` | Після release `get_status` → `EMPTY` |
| 5 | `test_release_metrics_updated` | `idemp_release_total["RELEASED"]` incremented |

#### Етап 9.1.6 — Circuit Breaker + Retry

Тести (мінімум 6):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_cb_closed_by_default` | `_cb_state == "CLOSED"` after init |
| 2 | `test_cb_opens_on_error_threshold` | 100 calls, 60%+ errors → `_cb_state == "OPEN"` |
| 3 | `test_cb_open_raises_CBOpenError` | Операція під час OPEN → `CBOpenError` |
| 4 | `test_cb_half_open_after_cooldown` | Після cooldown → HALF_OPEN, проби проходять |
| 5 | `test_cb_closes_after_successful_probes` | N successful probes → CLOSED |
| 6 | `test_retry_exponential_backoff` | Мокаємо time.sleep, перевіряємо delay pattern |

#### Етап 9.1.7 — Full lifecycle + edge cases

Тести (мінімум 5):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_full_lifecycle_reserve_confirm_get` | reserve→confirm→get_status round-trip |
| 2 | `test_full_lifecycle_reserve_release_reserve` | reserve→release→re-reserve (reuse key) |
| 3 | `test_key_prefix_idemp` | Internal key має prefix `idemp:` |
| 4 | `test_redis_unavailable_raises_StoreError` | Connection failure → `StoreError("connect", ...)` |
| 5 | `test_no_redis_package_raises_ImportError` | mock `REDIS_AVAILABLE=False` → `ImportError` |

**Підсумок 9.1:** ~35 тестів. Gate: `pytest tests/vfoundation -q` → 566 passed.

---

### Phase 9.2 — `cli/__main__.py` тести (typer CliRunner)

**Чому P0:** Governance tool. `vfound dict validate` використовується в CI gates, `vfound replay` — в DR-процедурі. 421 LOC — zero тестів.

**Файл:** `tests/vfoundation/cli/test_cli_main.py`
**Залежності:** `typer.testing.CliRunner`, `tmp_path`, mock WAL/YAML

#### Етап 9.2.1 — Test scaffold + helpers

1. Створити `tests/vfoundation/cli/__init__.py`
2. Fixture `runner` → `CliRunner(mix_stderr=False)`
3. Fixture `mock_wal_dir(tmp_path)`:
   - Створює `tmp_path/ops/wal/` з 2-3 `.jsonl` файлами
   - Містить Messages з відомими RIDs
   - Містить hash-chain для integrity перевірки
4. Fixture `mock_dicts(tmp_path)`:
   - Створює `tmp_path/vfoundation/dictionaries/global_v2_2_framework.yaml`
   - Створює `tmp_path/apps/reference/dictionaries/global_v2_2.yaml`
   - Валідна структура з `version`, `ops`, `ttl_profiles`, `security`, `limits`
5. `monkeypatch.chdir(tmp_path)` — для CWD-залежних path resolution

#### Етап 9.2.2 — `vfound schema` command

Тести (мінімум 3):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_schema_gen_creates_message_v1_json` | `result.exit_code == 0`, `schemas/message_v1.json` exists |
| 2 | `test_schema_gen_valid_json_schema` | Файл parseable JSON, має `$defs` або `properties` |
| 3 | `test_schema_gen_output_message` | stdout містить "Schemas generated" |

#### Етап 9.2.3 — `vfound dict lint` command

Тести (мінімум 4):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_dict_lint_global_ok` | `--global` з валідними файлами → exit 0, "OK" |
| 2 | `test_dict_lint_global_missing_file` | Без файлу → exit 1, "FAIL" |
| 3 | `test_dict_lint_domain_ok` | `--domain` з існуючою dir → exit 0 |
| 4 | `test_dict_lint_domain_missing` | `--domain` без dir → exit 1 |

#### Етап 9.2.4 — `vfound dict validate` command

Тести (мінімум 6):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_dict_validate_ok` | Валідні дикти → exit 0, "OK" |
| 2 | `test_dict_validate_missing_required_key` | YAML без `version` → exit 1, error msg |
| 3 | `test_dict_validate_invalid_ttl_range` | ttl_profiles з ttl=99999 → error |
| 4 | `test_dict_validate_sign_ops_not_subset` | sign_required_ops ⊄ ops → error |
| 5 | `test_dict_validate_report_json` | `--report report.json` → файл JSON з `ok`, `errors` |
| 6 | `test_dict_validate_report_md` | `--report report.md` → файл Markdown з заголовком |

#### Етап 9.2.5 — `vfound rfc` command

Тести (мінімум 3):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_rfc_new_creates_file` | `docs/RFC-test-name.md` created |
| 2 | `test_rfc_new_uses_template` | Файл містить "RFC-test-name" (заміна ADR-XXXX) |
| 3 | `test_rfc_new_existing_fails` | Повторний виклик → exit 1, "Exists" |

⚠️ **Передумова:** Треба створити `docs/ADR-Template.md` якщо не існує, або mock через `tmp_path`.

#### Етап 9.2.6 — `vfound replay` command

Тести (мінімум 5):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_replay_existing_rid` | exit 0, report JSON created, `events_count > 0` |
| 2 | `test_replay_missing_rid` | exit 1, "No events found" |
| 3 | `test_replay_no_wal_dir` | exit 1, "WAL directory not found" |
| 4 | `test_replay_shadow_mode` | `--shadow` → events not in report, integrity shown |
| 5 | `test_replay_custom_output` | `--output custom.json` → file at custom path |

#### Етап 9.2.7 — `vfound trace` command

Тести (мінімум 2):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_trace_get_found` | exit 0, JSON з events |
| 2 | `test_trace_get_not_found` | exit 0, events = [] |

#### Етап 9.2.8 — `vfound simulate` command

Тести (мінімум 2):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_simulate_creates_wal_entries` | exit 0, WAL files contain ASK+DEC |
| 2 | `test_simulate_output_message` | stdout містить "Simulated rid=" |

⚠️ **Увага:** `simulate` викликає `wal.append()` і `sign()` — треба mock або real WAL dir.

#### Етап 9.2.9 — `vfound drift` command

Тести (мінімум 3):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_drift_batch_with_data` | exit 0, report JSON з confusion matrix |
| 2 | `test_drift_no_wal` | exit 1, "WAL directory not found" |
| 3 | `test_drift_empty_wal` | exit 1, "No DEC or EVT messages" |

⚠️ **Увага:** `drift` динамічно імпортує `drift_monitor.py`.
**Шлях виправлений у Phase 9.0.2** (`apps/reference/domains/execution_position/drift_monitor.py`).
Для тестів: mock `importlib.util.spec_from_file_location` або створити stub модуль у `tmp_path`.

**Підсумок 9.2:** ~28 тестів. Gate: `pytest tests/vfoundation -q` → 594 passed.

---

### Phase 9.3 — MockExecutionAdapter: перенести в tests/

**Чому:** Audit finding — production код не має містити mock-класів.

**Кроки:**

#### Етап 9.3.1 — Верифікація поточного стану

1. Перевірити що `tests/vfoundation/core/test_execution_adapter.py` (line 17) імпортує з production path
2. Точний список імпортів:
   ```
   from vfoundation.core.adapters.execution_adapter import MockExecutionAdapter  # production
   ```
3. ⚠️ **Errata v1.1:** `tests/vfoundation/fixtures/mock_execution_adapter.py` — **orphan dead code**.
   Файл не імпортується нізвідки. Import path `from tests.vfoundation.fixtures...` **не працює** як Python import (tests/ не є package з правильним namespace). Файл буде видалений.

#### Етап 9.3.2 — Перемістити MockExecutionAdapter в conftest.py

> **v1.1 FIX:** Замість broken import з `tests/vfoundation/fixtures/`, скопіювати `MockExecutionAdapter` в `tests/vfoundation/conftest.py` як shared fixture.

1. В `tests/vfoundation/conftest.py` додати:
   ```python
   from vfoundation.core.adapters.execution_adapter import ExecutionAdapter

   class MockExecutionAdapter(ExecutionAdapter):
       """Mock adapter for testing. Moved from production code in Phase 9.3."""
       # ... (скопіювати логіку з production class)
   ```
2. В `tests/vfoundation/core/test_execution_adapter.py`:
   - Замінити `from vfoundation.core.adapters.execution_adapter import MockExecutionAdapter`
   - На `from tests.vfoundation.conftest import MockExecutionAdapter`
   - АБО використати pytest fixture: `@pytest.fixture def mock_adapter(): ...`
3. Видалити orphan: `git rm tests/vfoundation/fixtures/mock_execution_adapter.py`
4. Перевірити всі тести зелені

#### Етап 9.3.3 — Видалити MockExecutionAdapter з production

1. В `vfoundation/core/adapters/execution_adapter.py`:
   - Видалити клас `MockExecutionAdapter` (рядки ~468–кінець)
   - Залишити `# MockExecutionAdapter moved to tests/vfoundation/fixtures/` коментар
2. Gate: `pytest tests/vfoundation -q` → all pass
3. Gate: `pytest tests/ -q --ignore=tests/backtest` → all pass (перевірити що ніщо зовнішнє не зламалось)

**Підсумок 9.3:** 0 нових тестів, 1 production class removed, imports rewired.

---

### Phase 9.4 — Видалити legacy `core/fsm.py`

**Чому:** Deprecated з Phase 0.5, замінений на `fsm_core.py` + `fsm_v2.py`. Єдиний імпорт — `tests/test_coverage_final_push.py` line 15.

**Кроки:**

#### Етап 9.4.1 — Мігрувати legacy тест

1. Відкрити `tests/test_coverage_final_push.py`
2. Файл містить **3 тести** (не 1!):
   - `test_fsm_no_transition_error()` — line 13, імпортує deprecated `vfoundation.core.fsm.FSM`
   - `test_config_wal_dir_default()` — line 38, тестує `Config.wal_dir` default
   - `test_idempotency_store_simple()` — line 55, тестує `IdempotencyStore` instantiation
3. **Дії:**
   - `test_fsm_no_transition_error()` — **ВИДАЛИТИ** (FSMv2 має 24 тести, включаючи unknown verb handling)
   - `test_config_wal_dir_default()` — **ЗАЛИШИТИ** (покриває Config branch, ще не дубльований)
   - `test_idempotency_store_simple()` — **ЗАЛИШИТИ** (покриває базовий instantiation)
4. Після видалення `test_fsm_no_transition_error()` також видалити `sys.path` hack (lines 3-11), оскільки решта тестів імпортують напряму.
5. Gate: `pytest tests/ -q` → all pass

#### Етап 9.4.2 — Видалити файл

1. `git rm vfoundation/core/fsm.py`
2. Перевірити `vfoundation/core/__init__.py` — якщо є re-export `from .fsm import FSM` — видалити
3. Gate: `pytest tests/vfoundation -q` → all pass
4. Gate: `grep -r "from vfoundation.core.fsm import" --include="*.py"` → 0 results (крім .trash/)

**Підсумок 9.4:** 0 нових тестів, 1 deprecated file removed, 1 legacy test migrated.

---

### Phase 9 — Фінальний gate

```bash
pytest tests/vfoundation -q  # → ~596 passed, 0 failed
pytest tests/ -q --ignore=tests/backtest  # → no regressions
```

**Оновити ROADMAP_HARDENING.md:**
```markdown
| Phase 9 | ✅ DONE | 531 → ~596 (+65 tests, 2 files removed) |
```

---

# Phase 10 — P1 Audit Closure + Debug API Tests

**Ціль:** Закрити всі відкриті audit findings. Покрити `debug_api.py` dedicated тестами в `tests/vfoundation/`. Покрити trivial модулі.

**Передумова:** Phase 9 complete, ~596 passed.
**Очікуваний результат:** ~630–640 passed. 0 відкритих audit findings.

---

### Phase 10.1 — `debug_api.py` dedicated тести

**Чому P1:** 154 LOC, тести існують але розкидані поза `tests/vfoundation/`. Потрібна canonical test suite.

**Файл:** `tests/vfoundation/obs/test_debug_api.py`

> **v1.1 FIX (MEDIUM):** `debug_api.py` використовує 4 глобальні змінні: `_router_timings_ms`, `_total_requests`, `_timeout_count`, `_drift_reports`. Без reset між тестами — state pollution.

#### Етап 10.1.0 — Обов'язковий reset fixture (autouse)

```python
@pytest.fixture(autouse=True)
def _reset_debug_api_globals():
    """Reset all debug_api global state before each test."""
    from vfoundation.obs import debug_api
    debug_api._router_timings_ms.clear()
    debug_api._total_requests = 0
    debug_api._timeout_count = 0
    debug_api._drift_reports.clear()
    yield
```

> **v1.1 NOTE:** ~5 з 18 запланованих тестів дублюють покриття з `test_metrics_smoke.py` та `test_final_90_percent.py`.
> При написанні — перевірити дублікати та або пропустити, або видалити старі на користь canonical suite.

#### Етап 10.1.1 — Metrics functions

Тести (мінімум 6):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_record_router_timing_updates_list` | Після `record_router_timing(5.0)` → list non-empty |
| 2 | `test_get_p95_router_time_correct` | 100 timing values → p95 ≈ expected |
| 3 | `test_get_p95_empty_returns_zero` | No recordings → 0.0 |
| 4 | `test_record_timeout_increments_counter` | `record_timeout()` → `get_timeout_rate() > 0` |
| 5 | `test_timeout_rate_fraction` | 10 total, 2 timeouts → rate ≈ 0.2 |
| 6 | `test_router_timing_capped_at_5000` | >5000 entries → older entries pruned |

#### Етап 10.1.2 — Drift report storage

Тести (мінімум 4):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_add_drift_report_stores` | `add_drift_report(report)` → internal list grows |
| 2 | `test_drift_reports_cap_100` | 150 reports → list stays 100 |
| 3 | `test_find_drift_report_for_rid` | Report з mismatch.rid → found |
| 4 | `test_find_drift_report_missing_rid` | Unknown rid → None |

#### Етап 10.1.3 — Debug endpoint logic

Тести (мінімум 5):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_debug_rid_returns_events` | `debug_rid(rid, "Bearer dev")` → events, why_chain |
| 2 | `test_debug_rid_unauthorized` | `debug_rid(rid, None)` → HTTPException 403 |
| 3 | `test_debug_rid_bad_token` | `debug_rid(rid, "Bearer bad")` → 403 |
| 4 | `test_metrics_returns_dict` | `metrics()` → dict з p95, timeout_rate, confusion fields |
| 5 | `test_debug_rid_with_drift_report` | Після `add_drift_report(...)` → `result["drift_report"]` present |

#### Етап 10.1.4 — require_admin function

Тести (мінімум 3):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_require_admin_valid_token` | `require_admin("Bearer dev")` → True |
| 2 | `test_require_admin_invalid_format` | `require_admin("Token xyz")` → HTTPException |
| 3 | `test_require_admin_none` | `require_admin(None)` → HTTPException |

**Підсумок 10.1:** ~18 тестів. Gate: ~614 passed.

---

### Phase 10.2 — `redis_protocol.py` тести

**Чому:** TypedDict + Protocol — мінімальний, але покрити для повноти.

**Файл:** `tests/vfoundation/core/test_redis_protocol.py`

Тести (мінімум 4):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_RecordTD_is_TypedDict` | `RecordTD` can be constructed with correct keys |
| 2 | `test_RecordTD_total_false` | All fields optional (total=False) |
| 3 | `test_RedisClientProtocol_has_methods` | Protocol defines ping, evalsha, eval, set, get, exists, delete |
| 4 | `test_protocol_structural_subtyping` | Mock з потрібними методами задовольняє Protocol (runtime_checkable) |

**Підсумок 10.2:** 4 тести. Gate: ~618 passed.

---

### Phase 10.3 — `order_logger.py` тести

**Чому:** Compatibility shim, 16 LOC. Потрібен 1 тест для import path та fallback.

**Файл:** `tests/vfoundation/obs/test_order_logger.py`

Тести (мінімум 3):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_order_logger_importable` | `from vfoundation.obs.order_logger import order_logger` |
| 2 | `test_order_logger_has_write` | `hasattr(order_logger, 'write')` |
| 3 | `test_dummy_logger_fallback` | mock failed import → `_DummyOrderLogger.write()` no-op |

**Підсумок 10.3:** 3 тести. Gate: ~621 passed.

---

### Phase 10.4 — `streaming_io.py` тести

**Чому:** 12 LOC file chunker. Мінімальне покриття.

**Файл:** `tests/vfoundation/dataref/test_streaming_io.py`

Тести (мінімум 4):

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_read_chunks_returns_all_data` | `b"".join(read_chunks(path))` == original content |
| 2 | `test_read_chunks_respects_size` | Кожен chunk ≤ size bytes |
| 3 | `test_read_chunks_empty_file` | Порожній файл → generator yields nothing |
| 4 | `test_read_chunks_default_size` | Без параметра → size=8192 (перевірити через len) |

**Підсумок 10.4:** 4 тести. Gate: ~625 passed.

---

### Phase 10.5 — ExchangeACL stub documentation marker

**Чому:** Весь ExchangeACL (237 LOC) — stub. Навіть shadow_mode=False веде на `_stub_submit`. Це **design decision** (не bug), але потрібен explicit marker.

**Кроки:**

1. Додати module-level docstring:
   ```python
   """
   Exchange ACL — Access Control Layer for exchange operations.
   
   STATUS: STUB (all methods return synthetic responses).
   Real exchange integration is NOT implemented.
   shadow_mode controls logging verbosity, not actual exchange routing.
   
   TODO: Replace _stub_submit/_stub_event with real exchange gateway calls.
   """
   ```
2. Додати `# STUB` коментар до `submit()` та `cancel()` methods
3. **НЕ видаляти** — stub потрібний для backtest та shadow mode

**Підсумок 10.5:** 0 тестів, documentation/clarity improvement.

---

### Phase 10 — Фінальний gate

```bash
pytest tests/vfoundation -q  # → ~629 passed, 0 failed
```

**Оновити ROADMAP_HARDENING.md:**
```markdown
| Phase 10 | ✅ DONE | 596 → ~629 (+33 tests, audit findings closed) |
```

---

# Phase 11 — P2 Observability Hardening (Constitution §9)

**Ціль:** Реалізувати XAI store reference, OTLP export foundation, why_chain coverage tool.

**Передумова:** Phase 10 complete, ~629 passed.
**Очікуваний результат:** ~660 passed. Constitution §9 gaps частково закриті.

---

### Phase 11.1 — XAI Store (why_explain_ref backing)

**Constitution §9.1:** `why_explain_ref` вказує на XAI-сховище детальних пояснень. Поле існує в `Message`, але store не реалізований.

**Файл:** `vfoundation/obs/xai_store.py`
**Тести:** `tests/vfoundation/obs/test_xai_store.py`

#### Етап 11.1.1 — Design (інтерфейс)

```python
class XAIStore(ABC):
    """Abstract store for detailed why-explanations."""
    
    @abstractmethod
    def put(self, rid: str, explanation: dict) -> str:
        """Store explanation, return URI for why_explain_ref."""
        ...
    
    @abstractmethod
    def get(self, uri: str) -> dict | None:
        """Retrieve explanation by URI."""
        ...
    
    @abstractmethod
    def list_for_rid(self, rid: str) -> list[str]:
        """List all explanation URIs for a given rid."""
        ...
```

#### Етап 11.1.2 — InMemoryXAIStore implementation

```python
class InMemoryXAIStore(XAIStore):
    """Local in-memory XAI store for dev/test."""
    
    def __init__(self, max_entries: int = 10_000): ...
    def put(self, rid: str, explanation: dict) -> str: ...
    def get(self, uri: str) -> dict | None: ...
    def list_for_rid(self, rid: str) -> list[str]: ...
```

- URI format: `xai://memory/{uuid}`
- LRU eviction at `max_entries`
- Thread-safe (threading.Lock)

#### Етап 11.1.3 — Тести (мінімум 8)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_put_returns_uri` | URI starts with "xai://memory/" |
| 2 | `test_get_returns_explanation` | put → get round-trip |
| 3 | `test_get_missing_returns_none` | Unknown URI → None |
| 4 | `test_list_for_rid` | Put 3 explanations for same rid → list returns 3 URIs |
| 5 | `test_list_for_rid_empty` | Unknown rid → [] |
| 6 | `test_lru_eviction` | Put max+1 entries → oldest evicted |
| 7 | `test_thread_safety` | Concurrent puts from 4 threads → no crash |
| 8 | `test_abc_enforcement` | Direct `XAIStore()` instantiation → TypeError |

**Підсумок 11.1:** ~80 LOC module + 8 тестів.

---

### Phase 11.2 — Why-chain coverage measurement tool

**Constitution §12:** `why_chain coverage ≥ 95%`. Потрібен інструмент для вимірювання.

**Файл:** `vfoundation/obs/why_chain_coverage.py`
**Тести:** `tests/vfoundation/obs/test_why_chain_coverage.py`

#### Етап 11.2.1 — Implementation

```python
def measure_why_coverage(events: list[dict]) -> WhyCoverageReport:
    """
    Analyze list of Message dicts.
    Returns coverage stats: total, with_why, without_why, err_with_why, coverage_pct.
    """
```

- Input: list of message dicts (from WAL or test)
- Checks: `why` field present and non-empty
- Special: ERR messages MUST have why (100% required)
- Output: `WhyCoverageReport` dataclass

#### Етап 11.2.2 — Тести (мінімум 6)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_all_have_why` | 10/10 → 100% |
| 2 | `test_some_missing_why` | 8/10 → 80% |
| 3 | `test_err_messages_tracked_separately` | ERR without why → `err_missing_why > 0` |
| 4 | `test_empty_list` | [] → 0%, no crash |
| 5 | `test_threshold_pass` | `report.passes_threshold(95)` == True |
| 6 | `test_threshold_fail` | `report.passes_threshold(95)` == False |

**Підсумок 11.2:** ~50 LOC + 6 тестів.

---

### Phase 11.3 — OTLP exporter foundation (stub + contract)

**Constitution §9.2:** Метрики через OpenTelemetry OTLP. Реалізовувати повний pipeline — overkill. Але потрібен контракт + local fallback.

**Файл:** `vfoundation/obs/otlp_exporter.py`
**Тести:** `tests/vfoundation/obs/test_otlp_exporter.py`

#### Етап 11.3.1 — Design

```python
class OTLPExporter(ABC):
    """Abstract OTLP metric/span exporter."""
    
    @abstractmethod
    def export_span(self, span_data: dict) -> bool: ...
    
    @abstractmethod
    def export_metric(self, metric_name: str, value: float, labels: dict) -> bool: ...

class NoopOTLPExporter(OTLPExporter):
    """No-op exporter for environments without OTLP collector."""
    
    def export_span(self, span_data: dict) -> bool: return True
    def export_metric(self, metric_name: str, value: float, labels: dict) -> bool: return True

class InMemoryOTLPExporter(OTLPExporter):
    """In-memory exporter for testing."""
    
    def __init__(self): self.spans = []; self.metrics = []
    ...
```

#### Етап 11.3.2 — Тести (мінімум 6)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_noop_exporter_returns_true` | Both methods → True |
| 2 | `test_memory_exporter_stores_spans` | `export_span(...)` → spans list grows |
| 3 | `test_memory_exporter_stores_metrics` | `export_metric(...)` → metrics list grows |
| 4 | `test_abc_enforcement` | Direct `OTLPExporter()` → TypeError |
| 5 | `test_span_data_structure` | Stored span has expected fields |
| 6 | `test_memory_exporter_clear` | `.clear()` empties both lists |

**Підсумок 11.3:** ~60 LOC + 6 тестів.

---

### Phase 11.4 — Alert hooks framework

**Constitution §9.4:** Alert hooks при ENTROPY_SPIKE, TOPOLOGY_DRIFT, ERR% threshold.

**Файл:** `vfoundation/obs/alert_hooks.py`
**Тести:** `tests/vfoundation/obs/test_alert_hooks.py`

#### Етап 11.4.1 — Design

```python
AlertCallback = Callable[[str, dict], None]  # (alert_type, context)

class AlertManager:
    """Central alert manager. Register hooks per alert type."""
    
    def register(self, alert_type: str, callback: AlertCallback) -> None: ...
    def fire(self, alert_type: str, context: dict) -> int: ...  # returns num called
    def unregister_all(self, alert_type: str) -> None: ...

# Pre-defined alert types
ALERT_ENTROPY_SPIKE = "ENTROPY_SPIKE"
ALERT_TOPOLOGY_DRIFT = "TOPOLOGY_DRIFT"
ALERT_ERR_RATE_HIGH = "ERR_RATE_HIGH"
ALERT_CB_OPEN = "CB_OPEN"
```

#### Етап 11.4.2 — Тести (мінімум 7)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_register_and_fire` | Register callback → fire → callback called with context |
| 2 | `test_fire_no_hooks` | Fire unknown type → returns 0, no crash |
| 3 | `test_multiple_hooks` | Register 3 → fire → all 3 called |
| 4 | `test_unregister_all` | Register → unregister → fire → 0 called |
| 5 | `test_fire_returns_count` | 2 hooks → fire returns 2 |
| 6 | `test_hook_receives_context` | Context dict passed through to callback |
| 7 | `test_hook_exception_doesnt_crash` | Faulty callback raises → other hooks still fire |

**Підсумок 11.4:** ~50 LOC + 7 тестів.

---

### Phase 11 — Фінальний gate

```bash
pytest tests/vfoundation -q  # → ~656 passed, 0 failed
```

**Оновити ROADMAP_HARDENING.md:**
```markdown
| Phase 11 | ✅ DONE | 629 → ~656 (+27 tests, §9 XAI/OTLP/alerts/why-coverage) |
```

---

# Phase 12 — P3 Constitution §12 Quality Gates

**Ціль:** Реалізувати chaos-тест framework, DR timing verification, performance benchmark harness.

**Передумова:** Phase 11 complete, ~656 passed.
**Очікуваний результат:** ~680 passed. Constitution §12 gaps закриті.

---

### Phase 12.1 — Chaos test harness

**Constitution §12:** "Chaos-тести: ін'єкція TIMEOUT/CB-OPEN/мережевих розділів."

**Файл:** `vfoundation/testing/chaos.py`
**Тести:** `tests/vfoundation/testing/test_chaos.py`

#### Етап 12.1.1 — Design

```python
class ChaosInjector:
    """Inject controlled failures into vfoundation components."""
    
    def __init__(self, seed: int | None = None): ...
    
    def inject_timeout(self, router: Router, probability: float = 0.3) -> ContextManager: ...
    def inject_cb_open(self, adapter: ExecutionAdapter) -> ContextManager: ...
    def inject_network_partition(self, redis_store: RedisIdempotencyStore) -> ContextManager: ...
    
    @contextmanager
    def inject_random_failures(self, rate: float = 0.1) -> Generator: ...
```

Кожен injector:
- Є context manager (увімкнути → тест → вимкнути)
- Детермінований через seed
- Не мутує production state після exit

#### Етап 12.1.2 — Тести (мінімум 8)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_inject_timeout_causes_timeout` | Router message → TTL exceeded → ERR:TIMEOUT |
| 2 | `test_inject_timeout_cleanup` | Після exit context → routing нормальний |
| 3 | `test_inject_cb_open_raises` | Adapter operation → `CBOpenError` |
| 4 | `test_inject_cb_open_recovery` | Після exit → CB back to CLOSED |
| 5 | `test_inject_network_partition` | Redis op → `StoreError` |
| 6 | `test_inject_network_partition_recovery` | Після exit → Redis ops succeed |
| 7 | `test_deterministic_with_seed` | Same seed → same failure pattern |
| 8 | `test_random_failures_rate` | 1000 ops, rate=0.1 → ~100 failures (±20%) |

**Підсумок 12.1:** ~120 LOC + 8 тестів.

---

### Phase 12.2 — DR timing verification (RTO/RPO)

**Constitution §12:** "DR-тести: симуляція відмови + відновлення з WAL; перевірка RTO/RPO."
**Constitution §8.1:** RTO standard=5–15 min, critical=1–4 min. RPO standard=1 min, critical=15 sec.

> **v1.1 FIX (MEDIUM):** Оригінальний план позначав залежність 12.2→13.1 (RECONCILE flow).
> Це створювало **кругову залежність** (Phase 12 перед Phase 13, але 12.2 потребує 13.1).
> **Рішення:** DR timing реалізується **без** RECONCILE step. RECONCILE інтеграція буде додана
> як окремий тест у Phase 13.1 після реалізації ReconcileEngine.

**Файл:** `vfoundation/testing/dr_timing.py`
**Тести:** `tests/vfoundation/testing/test_dr_timing.py`

#### Етап 12.2.1 — Design

```python
@dataclass
class DRTimingResult:
    recovery_time_ms: float   # Time from failure to full recovery
    data_loss_events: int      # Events lost (between last checkpoint and failure)
    data_loss_window_ms: float # Time window of potential data loss
    rto_ok: bool               # recovery_time_ms ≤ rto_target_ms
    rpo_ok: bool               # data_loss_window_ms ≤ rpo_target_ms

def simulate_dr_recovery(
    wal_dir: Path,
    snapshot_dir: Path,
    failure_ts: int,
    rto_target_ms: float = 900_000,   # 15 min
    rpo_target_ms: float = 60_000,     # 1 min
) -> DRTimingResult:
    """
    Simulate DR procedure:
    1. Load latest snapshot before failure_ts
    2. Replay WAL from snapshot to failure_ts
    3. Measure recovery time
    4. Calculate data loss
    """
```

#### Етап 12.2.2 — Тести (мінімум 6)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_recovery_within_rto` | 100 WAL events → recovery < RTO target |
| 2 | `test_rpo_no_data_loss` | Snapshot + WAL → data_loss_events == 0 |
| 3 | `test_rto_exceeded_detected` | Велика кількість events → `rto_ok == False` if slow |
| 4 | `test_rpo_gap_detected` | Gap між snapshot і failure > RPO → `rpo_ok == False` |
| 5 | `test_empty_wal` | No WAL → data_loss = all since snapshot |
| 6 | `test_no_snapshot` | No snapshots → recovery from WAL beginning |

**Підсумок 12.2:** ~80 LOC + 6 тестів.

---

### Phase 12.3 — Performance benchmark harness

**Constitution §12:** "p95 FSM (hot) ≤ 50 мс" та "CB health: час у OPEN < 2%"

**Файл:** `vfoundation/testing/perf_benchmark.py`
**Тести:** `tests/vfoundation/testing/test_perf_benchmark.py`

#### Етап 12.3.1 — Design

```python
@dataclass
class PerfReport:
    operation: str
    samples: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    passes_threshold: bool  # p95 ≤ threshold

def benchmark_fsm_hot_path(
    fsm: FSMv2, 
    messages: list[Message],
    p95_threshold_ms: float = 50.0,
) -> PerfReport: ...

def benchmark_cb_health(
    adapter: ExecutionAdapter,
    duration_sec: float = 60.0,
) -> CBHealthReport: ...
```

#### Етап 12.3.2 — Тести (мінімум 5)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_benchmark_returns_report` | PerfReport has all fields |
| 2 | `test_p95_calculation_correct` | Known latencies → p95 matches expected |
| 3 | `test_threshold_pass` | Fast operations → passes_threshold = True |
| 4 | `test_threshold_fail` | Slow operations → passes_threshold = False |
| 5 | `test_cb_health_report` | CBHealthReport with open_pct field |

**Підсумок 12.3:** ~70 LOC + 5 тестів.

---

### Phase 12 — Фінальний gate

```bash
pytest tests/vfoundation -q  # → ~675 passed, 0 failed
```

> **DoD [Phase 12] — ✅ DONE (2026-02-23)**
> - Gate: 712 passed, 0 failed
> - Файли створені: `vfoundation/testing/chaos.py`, `vfoundation/testing/dr_timing.py`, `vfoundation/testing/perf_benchmark.py`, `tests/vfoundation/testing/test_quality_gates.py` 
> - Нових тестів: 19
> - Хардкоди: 0
> - Примітки: All Quality Gate harnesses implemented.

**Оновити ROADMAP_HARDENING.md:**
```markdown
| Phase 12 | ✅ DONE | 656 → ~675 (+19 tests, §12 chaos/DR-timing/perf) |
```

---

# Phase 13 — P4 Constitution Feature Gaps (§7, §8, §10)

**Ціль:** Закрити Constitution gaps: RECONCILE flow, CLI commands, WAL S3 archive contract, Latent Embeddings stub.

**Передумова:** Phase 12 complete, ~675 passed.
**Очікуваний результат:** ~700 passed. Всі Constitution секції мають хоча б foundation.

---

### Phase 13.1 — RECONCILE / CMD:REPAIR flow

**Constitution §8.3 step 5:** "Надіслати RECONCILE для узгодження між доменами; Meta-FSM ініціює CMD:REPAIR"

**Файл:** `vfoundation/dr/reconcile.py`
**Тести:** `tests/vfoundation/dr/test_reconcile.py`

> **v1.1 FIX (HIGH — contract compliance):** Verbs `RECONCILE` та `REPAIR` **відсутні** у
> `apps/reference/dictionaries/verb_registry_v1.yaml`. Згідно copilot-instructions §2:
> "НЕ створювати новий verb, доки не перевірено registry."

#### Етап 13.1.0 — Зареєструвати verbs у registry (ОБОВ'ЯЗКОВО ПЕРЕД кодом)

1. Відкрити `apps/reference/dictionaries/verb_registry_v1.yaml`
2. Додати записи:
   ```yaml
   - op: EVT
     verb: RECONCILE
     owner: inflight_reconcile
     status: experimental
     schema: null
   - op: CMD
     verb: REPAIR
     owner: inflight_reconcile
     status: experimental
     schema: null
   ```
3. Gate:
   ```bash
   pytest -q tests/vfoundation/test_verb_registry_warn_only.py
   pytest -q tests/vfoundation/test_verb_owner_inference_report.py
   ```
4. **Тільки після цього** переходити до 13.1.1.

#### Етап 13.1.1 — Design

```python
@dataclass
class ReconcileResult:
    rid: str
    domains_checked: list[str]
    mismatches: list[dict]
    repair_commands_sent: int
    success: bool

class ReconcileEngine:
    """Cross-domain state reconciliation after DR recovery."""
    
    def __init__(self, meta_fsm: MetaFSMv2, wal: WAL): ...
    
    def reconcile(self, domain: str, since_ts: int) -> ReconcileResult:
        """
        1. Read WAL events since_ts for domain
        2. Compare expected vs actual state
        3. Emit CMD:REPAIR for mismatches
        """
        ...
```

#### Етап 13.1.2 — Тести (мінімум 6)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_reconcile_no_mismatches` | Clean state → success=True, mismatches=[] |
| 2 | `test_reconcile_detects_mismatch` | Injected conflict → mismatches non-empty |
| 3 | `test_reconcile_emits_repair_cmd` | Mismatch → CMD:REPAIR message emitted |
| 4 | `test_reconcile_result_fields` | All fields populated |
| 5 | `test_reconcile_empty_wal` | No events → success=True (nothing to reconcile) |
| 6 | `test_reconcile_since_ts_filter` | Only events after since_ts processed |

**Підсумок 13.1:** ~100 LOC + 6 тестів.

---

### Phase 13.2 — WAL S3 archive contract (ABC + local impl)

**Constitution §8.2:** "S3 WORM storage". Повна S3 інтеграція — out of scope (потрібен cloud access). Але контракт + local implementation потрібні.

**Файл:** `vfoundation/dr/wal_archive.py`
**Тести:** `tests/vfoundation/dr/test_wal_archive.py`

#### Етап 13.2.1 — Design

```python
class WALArchiver(ABC):
    """Archive WAL segments to durable storage."""
    
    @abstractmethod
    def archive(self, wal_file: Path) -> str:
        """Archive WAL file, return URI.""" ...
    
    @abstractmethod
    def verify(self, uri: str) -> bool:
        """Verify archived segment integrity.""" ...
    
    @abstractmethod
    def restore(self, uri: str, target: Path) -> bool:
        """Restore archived segment.""" ...

class LocalWALArchiver(WALArchiver):
    """Archive to local directory (dev/test)."""
    
    def __init__(self, archive_dir: Path): ...
```

#### Етап 13.2.2 — Тести (мінімум 6)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_archive_creates_copy` | Archive → file in archive_dir |
| 2 | `test_archive_returns_uri` | URI format: `file:///archive/...` |
| 3 | `test_verify_valid` | Archived file → True |
| 4 | `test_verify_corrupted` | Tampered file → False |
| 5 | `test_restore_round_trip` | archive → restore → content matches |
| 6 | `test_abc_enforcement` | Direct `WALArchiver()` → TypeError |

**Підсумок 13.2:** ~80 LOC + 6 тестів.

---

### Phase 13.3 — Wire WAL GC → WALArchiver

**Кроки:**

1. В `vfoundation/dr/wal_gc.py` line 62:
   - Замінити `# Archive to S3/cloud (optional - TODO)` на:
   ```python
   if self.archiver:
       self.archiver.archive(wal_file)
   ```
2. Додати `archiver: WALArchiver | None = None` до `__init__`
3. Тест: GC з archiver → file archived before deletion

**Підсумок 13.3:** +1 тест, ~5 LOC зміна.

---

### Phase 13.4 — Missing CLI commands (stubs)

**Constitution §10.2:** `vfound init`, `vfound schema gen --from pydantic`, `vfound test gen`, `vfound simulate flow`, `vfound trace get`.

`vfound trace` вже існує (line 395). `vfound simulate` вже існує (line 168). Залишилось:

#### Етап 13.4.1 — `vfound init` (domain scaffolding)

```python
@app.command("init")
def init_domain(name: str, owner: str = "unknown") -> None:
    """Scaffold new domain directory structure."""
    domain_dir = pathlib.Path(f"apps/reference/domains/{name}")
    if domain_dir.exists():
        typer.echo(f"Domain {name} already exists"); raise typer.Exit(1)
    domain_dir.mkdir(parents=True)
    (domain_dir / "__init__.py").write_text(f'"""Domain: {name}"""\n')
    (domain_dir / f"{name}.py").write_text(f'"""Main module for {name} domain."""\n')
    typer.echo(f"Created domain: {domain_dir}")
```

#### Етап 13.4.2 — Тести для нових CLI commands (мінімум 4)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_init_creates_domain_dir` | Directory created з __init__.py |
| 2 | `test_init_existing_fails` | Existing dir → exit 1 |
| 3 | `test_init_creates_main_module` | `{name}.py` created |
| 4 | `test_init_output_message` | stdout містить "Created domain" |

**Підсумок 13.4:** ~30 LOC + 4 тести.

---

### Phase 13.5 — Latent Embeddings stub (Constitution §7)

**Constitution §7:** "Latent Embeddings — розширений контекст для CMD". Zero code exists.

**Стратегія:** Реалізувати ABC + InMemory stub + тести для контракту. Повна ML-імплементація — out of scope (потрібні model weights).

**Файл:** `vfoundation/core/latent_embeddings.py`
**Тести:** `tests/vfoundation/core/test_latent_embeddings.py`

#### Етап 13.5.1 — Design

```python
@dataclass
class LatentContext:
    """Latent state embedding for enriching CMD messages."""
    rid: str
    embedding: list[float]  # Dense vector
    domain: str
    ts: int
    confidence: float = 0.0  # [0..1]

class LatentEmbeddingProvider(ABC):
    """Provide latent embeddings for command enrichment."""
    
    @abstractmethod
    def encode(self, state: dict, domain: str) -> LatentContext: ...
    
    @abstractmethod
    def similarity(self, a: LatentContext, b: LatentContext) -> float: ...

class ZeroEmbeddingProvider(LatentEmbeddingProvider):
    """No-op provider (returns zero vectors). For dev/test."""
    
    def __init__(self, dim: int = 64): ...
    def encode(self, state: dict, domain: str) -> LatentContext: ...
    def similarity(self, a: LatentContext, b: LatentContext) -> float: ...
```

#### Етап 13.5.2 — Тести (мінімум 5)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_zero_provider_returns_context` | encode → LatentContext з zero vector |
| 2 | `test_embedding_dim_correct` | len(embedding) == dim |
| 3 | `test_similarity_zero_vectors` | similarity(zero, zero) == 1.0 (or 0.0 for cosine of zeros) |
| 4 | `test_abc_enforcement` | Direct instantiation → TypeError |
| 5 | `test_latent_context_fields` | All fields populated correctly |

**Підсумок 13.5:** ~60 LOC + 5 тестів.

---

### Phase 13 — Фінальний gate

```bash
pytest tests/vfoundation -q  # → ~703 passed, 0 failed
```

> **DoD [Phase 13] — ✅ DONE (2026-02-23)**
> - Gate: 712 passed, 0 failed
> - Файли створені: `vfoundation/core/reconcile.py`, `vfoundation/dataref/wal_archiver.py`, `vfoundation/dataref/latent_embeddings.py`, `tests/vfoundation/test_phase13.py`
> - Нових тестів: ~26
> - Хардкоди: 0
> - Примітки: All Constitution Feature Gaps (RECONCILE, Archive, CLI init, Latent Embeddings) implemented with stub/concrete behavior and tested. Verb registry updated first.

**Оновити ROADMAP_HARDENING.md:**
```markdown
| Phase 13 | ✅ DONE | 675 → ~712 (+26 tests, §7/§8/§10 Constitution gaps) |
```

---

# Phase 14 — P5 Deferred Refactoring (Phases 4.2–4.3, 5.3–5.4)

**Ціль:** Закрити deferred phases. **BREAKING CHANGES** — потребують окремого PR з migration guide.

**Передумова:** Phases 9–13 complete, ~703 passed. Domain-level тести верифіковані.
**Очікуваний результат:** Залежить від scope. Це фаза планування.

---

### Phase 14.1 — Phase 4.2: Split `decision_making.py` (~4K LOC)

**Передумова:** Domain `decision_making/` має тести (перевірити `tests/domains/test_decision_making*.py`)

#### Етап 14.1.1 — Аналіз залежностей

1. Побудувати import graph для `apps/reference/domains/decision_making/decision_making.py`
2. Ідентифікувати логічні блоки:
   - Signal evaluation (EVAL verb handlers)
   - Position sizing logic
   - Risk pre-checks
   - DEC formation
3. Кожен блок → окремий файл ≤ 800 LOC

#### Етап 14.1.2 — Extract module pattern

Для кожного sub-module:

1. Створити `apps/reference/domains/decision_making/{submodule}.py`
2. Перемістити функції/класи
3. В оригіналі залишити re-imports:
   ```python
   # Backward compatibility
   from .signal_eval import evaluate_signal  # noqa: F401
   ```
4. Gate: `pytest tests/ -q --ignore=tests/backtest` → зелені

#### Етап 14.1.3 — Cleanup re-imports (наступний PR)

1. Оновити всі зовнішні імпорти на прямі шляхи
2. Видалити re-imports з оригіналу
3. Gate: `grep -r "from.*decision_making.decision_making import"` → 0 використань legacy path

---

### Phase 14.2 — Phase 4.3: Split `execution_position/fsm.py` (~4K LOC)

Аналогічний pattern до 14.1:

1. Аналіз залежностей
2. Логічні блоки: state management, order lifecycle, position tracking, event handlers
3. Extract → backward-compat re-imports → cleanup

---

### Phase 14.3 — Phase 5.3: Message envelope refactor

**BREAKING CHANGE.** Перемістити trading-specific поля з core Message в `pld`.

#### Етап 14.3.1 — Ідентифікувати trading-specific поля

Поля в Message які НЕ є частиною universal protocol:
- `oco_group_id`
- `parent_client_order_id`
- `account_qualifier`
- Будь-які інші domain-specific fields

#### Етап 14.3.2 — Migration plan

1. Додати ці поля в `pld` schema per domain
2. Deprecation: зберегти old fields з `DeprecationWarning` на 2 releases
3. Migration script: `vfound migrate message-envelope`
4. В кожному домені оновити code з `msg.oco_group_id` на `msg.pld.get("oco_group_id")`

#### Етап 14.3.3 — Implementation

1. Оновити `Message` model — зробити deprecated fields Optional з default=None
2. Додати validator: якщо deprecated field set → copy to pld, emit warning
3. Domain-by-domain migration (1 PR per domain)
4. Final: видалити deprecated fields

---

### Phase 14.4 — Phase 5.4: Typed pld per verb

#### Етап 14.4.1 — Define per-verb Pydantic models

```python
class EvalPayload(BaseModel):
    signal_type: str
    confidence: float
    timeframe: str

class OpenPayload(BaseModel):
    side: Literal["BUY", "SELL"]
    size: float
    price: float | None = None
```

#### Етап 14.4.2 — Discriminated union

```python
PldUnion = Annotated[
    EvalPayload | OpenPayload | ClosePayload | ...,
    Field(discriminator="verb")
]
```

#### Етап 14.4.3 — Schema validation wiring

1. Router validates `pld` against verb-specific schema
2. SchemaValidator integration  
3. CI gate: invalid pld → test fails

---

### Phase 14 — Gate

```bash
pytest tests/ -q  # → all pass after each sub-phase
```

⚠️ **Увага:** Phase 14 — це **окремі великі PR**, кожен з migration guide. Не робити все одночасно.

> **v1.1 NOTE:** Phase 14 потребує окремий detailed blueprint з rollback plan для кожного
> sub-phase, оскільки це breaking changes. Створити `BLUEPRINT_PHASE_14_BREAKING.md` перед початком.

---

# Gap Analysis: Шлях до 90% vFoundation

**Дата аналізу:** 2026-02-24
**Передумова:** Phases 9–13 виконані агентом (712 tests, 0 failures). Phase 14 — 0%.

## Honest Assessment: Що означає "90%"

Після виконання Phases 9–13 агент заявив "90% complete". Це **хибна інтерпретація**:
- 90% стосувалось лише виконання **Blueprint Phases 9–13**, а не загальної готовності vFoundation.
- Реальна library completeness на момент аналізу: **~70%**.
- Production-readiness: **~40–45%** (потребує реальну інфраструктуру: S3, KMS, geo-replication).

**Scope "90% library completeness"** означає:
- Всі Constitution §§ мають **code contracts** (ABC/interfaces + in-memory implementations + тести)
- CLI повністю функціональний per §10.2
- Schema versioning pipeline існує (negotiation, deprecation, migration tooling)
- Cross-cutting concerns мають хоча б контрактні інтерфейси
- Monolith split та Message v2 migration — завершені або в процесі
- **OUT OF SCOPE:** real S3/KMS/WORM/geo — це deployment concerns, не library code

## Поточний стан по категоріях Constitution

| Категорія | Constitution § | Поточний % | Ключові прогалини | Цільова Phase |
|-----------|---------------|-----------|-------------------|---------------|
| Core protocol (Message, FSM, routing) | §3, §5 | ~85% | `v=1` замість `v=2`, `data_ref: List[str]` замість об'єктів | 14.3, 16 |
| CLI tooling | §10.2 | ~80% | `test gen` відсутній, `drift` без тестів, sub-command naming | 15 |
| Security | §11 | ~60% | RBAC — trivial token check (no ABAC), redaction — flat only, ratelimits — no thread lock | 17 |
| Observability | §9 | ~80% | OTLP exporter — чистий stub (Noop), решта — real in-memory | 17 |
| DR / Resilience | §8 | ~75% | WAL/merkle/snapshot — real. WORM/S3/geo — infra scope. fsm.py не видалено. | 15 |
| Quality gates | §12 | ~75% | Synthetic benchmarks, не real I/O. | done (synthetic OK for library) |
| Schema versioning | §10.4, §13.2 | **0%** | Zero infra: no negotiation, no deprecation validators, no migration | 16 |
| Cross-cutting concerns | Audit findings | ~30% | Error taxonomy, shutdown ordering, backpressure, metric naming | 17 |
| Modularity (monolith split) | Deferred | **0%** | `decision_making` ~4K LOC, `execution_position/fsm` ~4K LOC | 14 |

## Що потрібно для 90%

| # | Блок роботи | Phase | Пріоритет | Покриває | Δ до 90% |
|---|-------------|-------|-----------|---------|----------|
| 1 | Breaking changes: split monoliths + Message v2 + typed pld | **14** | HIGH | §5, §14, modularity | +12% |
| 2 | Cleanup + CLI completeness | **15** | MEDIUM | §10.2, audit gaps, fsm.py | +3% |
| 3 | Schema versioning + Protocol v2 infrastructure | **16** | HIGH | §5, §10.4, §13.2 | +8% |
| 4 | Cross-cutting production contracts | **17** | MEDIUM | §8, §11, audit concerns | +5% |
| **Σ** | | **14–17** | | | **+28% (70%→≥90%)** |

**Прогнозований підсумок після Phases 14–17:** ~810–840 тестів, ≥90% library completeness.

---

# Phase 15 — P6 Cleanup + CLI Completeness (Constitution §10.2)

**Ціль:** Закрити залишкові gaps від Phases 9–13 та довести CLI до повної відповідності Constitution §10.2.

**Передумова:** Phases 9–13 complete (712 tests). Phase 14 — незалежний (може бути паралельно).
**Очікуваний результат:** ~732 passed. CLI 100% per Constitution. Legacy cleanup завершений.

---

### Phase 15.1 — Delete legacy `fsm.py` (carry-over від Phase 9.4)

**Проблема:** `vfoundation/core/fsm.py` досі існує (44 LOC, deprecated). Єдиний імпорт — `tests/test_coverage_final_push.py` тест #1.

**Кроки:**

1. Верифікувати що ніхто крім test_coverage_final_push.py не імпортує:
   ```bash
   grep -r "from vfoundation.core.fsm import" --include="*.py" | grep -v __pycache__
   ```
2. Видалити `vfoundation/core/fsm.py`
3. Видалити тест #1 з `tests/test_coverage_final_push.py` (залишити тести 2-3: Config.wal_dir, IdempotencyStore)
4. Gate: `pytest tests/vfoundation -q` → 711 passed (або 712 якщо тест вже не рахувався)

---

### Phase 15.2 — CLI `drift` command тести

**Проблема:** `vfound drift` — єдина з 10 CLI команд **без тестів**. Команда існує (line 268 `__main__.py`), функціональна після Phase 9.0.2 fix.

**Файл:** `tests/vfoundation/cli/test_cli_main.py` (додати `TestDriftCommand` клас)

**Тести (мінімум 4):**

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_drift_no_config_files` | Відсутність конфігів → повідомлення "no files" або пустий результат |
| 2 | `test_drift_with_valid_config` | Валідний конфіг → без дрифту → "OK" |
| 3 | `test_drift_detects_mismatch` | Конфіг з розбіжностями → повідомлення про дрифт |
| 4 | `test_drift_output_format` | Формат виводу відповідає structlog JSON |

**Підсумок 15.2:** 0 LOC production + 4 тести.

---

### Phase 15.3 — CLI `test gen` command (Constitution §10.2)

**Проблема:** `vfound test gen --module X` — єдина Constitution CLI команда яка **повністю відсутня**. Інші 7 — існують.

**Файл:** `vfoundation/cli/vfound/__main__.py` (додати `@app.command("test-gen")`)

#### Етап 15.3.1 — Design

```python
@app.command("test-gen")
def test_gen(
    module: str = typer.Argument(..., help="Module path like vfoundation.core.routing"),
    output: pathlib.Path = typer.Option(None, "--output", "-o", help="Output test file path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print template without writing"),
) -> None:
    """Generate contract test template for a given module."""
    mod_path = module.replace(".", "/") + ".py"
    if not pathlib.Path(mod_path).exists():
        typer.echo(f"Module not found: {mod_path}"); raise typer.Exit(1)

    # Parse module: extract public classes/functions
    import ast
    tree = ast.parse(pathlib.Path(mod_path).read_text())
    public_names = [
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    ]

    # Generate test template
    test_lines = [
        f'"""Auto-generated contract tests for {module}."""',
        f"import pytest",
        f"from {module} import {', '.join(public_names[:10]) if public_names else 'pass'}",
        "",
    ]
    for name in public_names[:10]:
        test_lines.append(f"def test_{name.lower()}_exists():")
        test_lines.append(f'    """Verify {name} is importable and callable/instantiable."""')
        test_lines.append(f"    assert {name} is not None")
        test_lines.append("")

    content = "\n".join(test_lines)

    if dry_run:
        typer.echo(content)
    else:
        out_path = output or pathlib.Path(f"tests/test_{module.split('.')[-1]}_gen.py")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content)
        typer.echo(f"Generated: {out_path} ({len(public_names)} symbols)")
```

#### Етап 15.3.2 — Тести (мінімум 5)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_test_gen_module_not_found` | Неіснуючий модуль → exit 1 |
| 2 | `test_test_gen_dry_run` | `--dry-run` → stdout contains test template |
| 3 | `test_test_gen_creates_file` | Без `--dry-run` → файл створений |
| 4 | `test_test_gen_extracts_symbols` | Шаблон містить правильні назви класів/функцій |
| 5 | `test_test_gen_custom_output` | `--output custom.py` → правильний шлях |

**Підсумок 15.3:** ~40 LOC production + 5 тестів.

---

### Phase 15.4 — CLI sub-command alignment з Constitution naming

**Проблема:** 4 CLI команди мають **flat naming** замість Constitution **sub-command naming**:
- `vfound rfc <name>` → Constitution каже `vfound rfc new <name>`
- `vfound schema` → Constitution каже `vfound schema gen`
- `vfound trace <rid>` → Constitution каже `vfound trace get <rid>`
- `vfound simulate <file>` → Constitution каже `vfound simulate flow <file>`

**Стратегія:** Backward-compatible — додати sub-typer з sub-команд, зберегти flat fallback з DeprecationWarning.

**Кроки:**

1. Для кожної з 4 команд:
   - Створити sub-typer (e.g., `rfc_app = typer.Typer()`)
   - Додати sub-command (`@rfc_app.command("new")`)
   - Оригінальну flat command → deprecation wrapper
2. Тести для кожного sub-command (4 × 2 = 8 тестів: new path + legacy path)
3. Gate: всі існуючі тести проходять + нові

**Підсумок 15.4:** ~60 LOC production + 8 тестів.

---

### Phase 15.5 — ExchangeACL stub documentation + contract tests

**Проблема:** `ExchangeACL` — повний stub (`_stub_submit` в обох shadow/live гілках, `stream_events()` yields fake SOLUSDT). Phase 10.5 додав лише markdown doc. Потрібні contract-level тести.

**Стратегія:** Не реалізовувати real exchange (out of scope), але додати ABC contract tests що верифікують інтерфейс.

**Тести (мінімум 3):**

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_acl_implements_exchange_interface` | ExchangeACL has submit/cancel/stream methods |
| 2 | `test_acl_shadow_mode_no_real_orders` | Shadow mode → жодного реального ордеру |
| 3 | `test_acl_idempotency_dedup_wired` | `_is_duplicate` → IdempotencyLedger (Phase 7.7 fix) |

**Підсумок 15.5:** 0 LOC production + 3 тести.

---

### Phase 15 — Gate

```bash
pytest tests/vfoundation -q  # → ~732 passed, 0 failed
```

---

# Phase 16 — P7 Schema Versioning & Protocol v2 Infrastructure (Constitution §5, §10.4)

**Ціль:** Створити інфраструктуру для schema versioning, Message v=1→v=2 сумісності, та `data_ref` alignment з Constitution. **Це prerequisite для Phase 14.3** (message envelope refactor).

**Передумова:** Phase 14.1–14.2 можуть бути паралельними. Phase 16 потрібен ПЕРЕД Phase 14.3.
**Очікуваний результат:** ~762 passed. Schema versioning pipeline готовий.

---

### Phase 16.1 — Schema Version Registry Module

**Проблема (0% infra):** Немає жодного механізму версіонування схем. Constitution §10.4 вимагає:
- Версіонування всіх схем (`_v1`, `_v2`)
- Deprecation windows мінімум 2 releases
- Schema-budget per домен
- Semantic diff в CI

**Файл:** `vfoundation/core/schema_version.py`
**Тести:** `tests/vfoundation/core/test_schema_version.py`

#### Design

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class SchemaStatus(Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    REMOVED = "removed"

@dataclass
class SchemaVersion:
    """Tracked schema version with lifecycle metadata."""
    name: str                    # e.g., "cmd_open_v1"
    version: int                 # e.g., 1
    status: SchemaStatus
    deprecated_since: str | None = None   # ISO date
    removal_target: str | None = None     # ISO date
    successor: str | None = None          # "cmd_open_v2"

@dataclass
class SchemaRegistry:
    """In-memory schema version registry with deprecation tracking."""
    _schemas: dict[str, SchemaVersion] = field(default_factory=dict)

    def register(self, sv: SchemaVersion) -> None: ...
    def get(self, name: str) -> SchemaVersion | None: ...
    def deprecate(self, name: str, successor: str, removal_date: str) -> None: ...
    def active_schemas(self) -> list[SchemaVersion]: ...
    def deprecated_schemas(self) -> list[SchemaVersion]: ...
    def validate_no_removed_in_use(self, used_schemas: set[str]) -> list[str]: ...
```

#### Тести (мінімум 8)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_register_and_get` | Roundtrip: register → get |
| 2 | `test_deprecate_sets_status` | deprecate → status=DEPRECATED, successor set |
| 3 | `test_deprecate_unknown_raises` | deprecate nonexistent → KeyError |
| 4 | `test_active_schemas_filter` | active_schemas() excludes deprecated/removed |
| 5 | `test_deprecated_schemas_filter` | deprecated_schemas() returns only deprecated |
| 6 | `test_validate_removed_in_use` | Використання removed schema → warning list |
| 7 | `test_validate_all_active_ok` | Тільки active → пустий список |
| 8 | `test_schema_version_immutable_fields` | name/version не змінюються після creation |

**Підсумок 16.1:** ~80 LOC + 8 тестів.

---

### Phase 16.2 — Message v=1↔v=2 Compatibility Layer

**Проблема:** Constitution §5.2 каже `"v": 2`, код має `v: int = 1`. ADR в Phase 9.0.6 задокументував drift, але **ніякого коду** не створено.

**Стратегія:** Facade pattern. Message default залишається v=1 (backward-compat), додається:
- `MessageV2` subclass або upgrade function
- Compat validator: v=1 messages → auto-upgrade з DeprecationWarning
- v=2 messages → validate new fields (span_id, parent_span_id як required)

**Файл:** `vfoundation/core/message_compat.py`
**Тести:** `tests/vfoundation/core/test_message_compat.py`

#### Design

```python
import warnings
from vfoundation.core.protocol import Message

def upgrade_v1_to_v2(msg: Message) -> Message:
    """Upgrade v=1 Message to v=2 format. Adds missing fields with defaults."""
    if msg.v >= 2:
        return msg
    warnings.warn(
        f"Message v={msg.v} is deprecated. Use v=2.",
        DeprecationWarning, stacklevel=2,
    )
    # Upgrade: set v=2, ensure span_id/parent_span_id exist
    return msg.model_copy(update={
        "v": 2,
        "span_id": msg.span_id or msg.rid,  # default span = rid
    })

def validate_v2_contract(msg: Message) -> list[str]:
    """Validate that a v=2 message meets Constitution §5.2 requirements."""
    issues: list[str] = []
    if msg.v < 2:
        issues.append(f"v={msg.v}, expected >=2")
    if not msg.why:
        issues.append("why is required")
    if not msg.rid:
        issues.append("rid is required")
    return issues

def is_backward_compatible(v1_msg: Message, v2_msg: Message) -> bool:
    """Check if v2 message preserves v1 semantics (same rid, op, verb, src, dst)."""
    return all([
        v1_msg.rid == v2_msg.rid,
        v1_msg.op == v2_msg.op,
        v1_msg.verb == v2_msg.verb,
        v1_msg.src == v2_msg.src,
        v1_msg.dst == v2_msg.dst,
    ])
```

#### Тести (мінімум 8)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_upgrade_v1_to_v2_sets_version` | v=1 → v=2 після upgrade |
| 2 | `test_upgrade_v2_noop` | v=2 → повертає as-is |
| 3 | `test_upgrade_emits_deprecation_warning` | DeprecationWarning при v=1 |
| 4 | `test_upgrade_preserves_all_fields` | rid, op, verb, pld — незмінні |
| 5 | `test_upgrade_generates_span_id` | span_id заповнюється якщо None |
| 6 | `test_validate_v2_ok` | Валідний v=2 → порожній список |
| 7 | `test_validate_v2_missing_why` | Без why → "why is required" |
| 8 | `test_backward_compatible_check` | Upgrade зберігає семантичну рівність |

**Підсумок 16.2:** ~60 LOC + 8 тестів.

---

### Phase 16.3 — `data_ref` Schema Alignment (Constitution §5.2)

**Проблема:** Constitution §5.2 каже:
```json
"data_ref": [{"uri":"s3://...", "sha256":"...", "bytes":1234567, "ctype":"application/parquet", "ttl_ms": 600000}]
```

Код має: `data_ref: List[str] = Field(default_factory=list)`

**Стратегія:** Створити `DataRef` Pydantic model, оновити `Message.data_ref` тип, зберегти backward compat для `List[str]`.

**Файл:** `vfoundation/core/data_ref.py`
**Тести:** `tests/vfoundation/core/test_data_ref.py`

#### Design

```python
from pydantic import BaseModel, Field

class DataRef(BaseModel):
    """Structured data reference per Constitution §5.2 / §11.1."""
    uri: str                       # s3://bucket/path or file://local/path
    sha256: str                    # hex digest for integrity verification
    bytes: int = 0                 # payload size
    ctype: str = "application/octet-stream"  # content type
    ttl_ms: int = 600_000          # default 10 min

# Backward compat: accept both str and DataRef
DataRefItem = str | DataRef
```

**Зміна в `protocol.py`:** `data_ref: list[DataRefItem]` з Pydantic validator що конвертує str → DataRef(uri=str).

#### Тести (мінімум 6)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_data_ref_model_fields` | Всі поля Constitution §5.2 |
| 2 | `test_data_ref_defaults` | bytes=0, ctype=octet-stream, ttl=600000 |
| 3 | `test_message_data_ref_str_compat` | `Message(data_ref=["s3://..."])` → працює (backward compat) |
| 4 | `test_message_data_ref_object` | `Message(data_ref=[DataRef(...)])` → працює |
| 5 | `test_data_ref_sha256_validation` | Некоректний sha256 → validation error |
| 6 | `test_data_ref_serialization` | Round-trip: model → JSON → model |

**Підсумок 16.3:** ~40 LOC + 6 тестів.

---

### Phase 16.4 — Deprecation Policy Validator

**Проблема:** Немає автоматичного enforcement deprecation policies. Constitution §10.4 вимагає deprecation windows мінімум 2 releases.

**Файл:** `vfoundation/core/deprecation.py`
**Тести:** `tests/vfoundation/core/test_deprecation.py`

#### Design

```python
import warnings
from dataclasses import dataclass
from typing import Callable, Any

@dataclass
class DeprecationEntry:
    """Track a deprecated API/feature."""
    name: str
    since: str              # version or date
    removal_target: str     # version or date when it will be removed
    replacement: str | None = None
    message: str | None = None

class DeprecationRegistry:
    """Centralized deprecation tracking."""
    _entries: dict[str, DeprecationEntry]

    def register(self, entry: DeprecationEntry) -> None: ...
    def check(self, name: str) -> DeprecationEntry | None: ...
    def warn_if_deprecated(self, name: str) -> None: ...
    def all_deprecated(self) -> list[DeprecationEntry]: ...

def deprecated(name: str, since: str, removal: str, replacement: str | None = None):
    """Decorator to mark function/class as deprecated."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            warnings.warn(
                f"{name} deprecated since {since}, removal target {removal}. "
                f"Use {replacement} instead." if replacement else
                f"{name} deprecated since {since}, removal target {removal}.",
                DeprecationWarning, stacklevel=2,
            )
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

#### Тести (мінімум 7)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_register_and_check` | Roundtrip |
| 2 | `test_check_nonexistent` | None |
| 3 | `test_warn_if_deprecated` | DeprecationWarning emitted |
| 4 | `test_warn_nondeprecated_silent` | Нема warning |
| 5 | `test_deprecated_decorator` | Decorated function emits warning |
| 6 | `test_deprecated_decorator_preserves_return` | Return value unchanged |
| 7 | `test_all_deprecated_list` | Повний список |

**Підсумок 16.4:** ~70 LOC + 7 тестів.

---

### Phase 16 — Gate

```bash
pytest tests/vfoundation -q  # → ~762 passed, 0 failed
```

---

# Phase 17 — P8 Cross-cutting Production Contracts (Constitution §8, §11, Audit Concerns)

**Ціль:** Закрити 6 з 8 Missing Concerns від Staff Architect аудиту. Реалізувати production-level контракти для security, error handling, shutdown, та backpressure.

**Передумова:** Phases 9–13 complete. Незалежний від Phases 14–16.
**Очікуваний результат:** ~787 passed. Cross-cutting concerns мають ABC + in-memory impl + тести.

---

### Phase 17.1 — Error Taxonomy (Standardized Error Codes + Registry)

**Проблема (Audit Missing Concern #4):** Немає стандартизованої таксономії помилок. Error classes scattered across modules, metric labels inconsistent.

**Файл:** `vfoundation/core/errors.py`
**Тести:** `tests/vfoundation/core/test_error_taxonomy.py`

#### Design

```python
from enum import IntEnum
from dataclasses import dataclass

class ErrorCategory(IntEnum):
    """Standardized error categories with numeric codes."""
    VALIDATION   = 1000  # Invalid input, schema mismatch
    TIMEOUT      = 2000  # TTL expired, deadline exceeded
    CIRCUIT_OPEN = 3000  # Circuit breaker open
    IDEMPOTENCY  = 4000  # Duplicate request, conflict
    SECURITY     = 5000  # Auth failure, signature invalid
    DR_FAILURE   = 6000  # WAL corruption, snapshot missing
    PROTOCOL     = 7000  # Unknown verb, invalid op, version mismatch
    INTERNAL     = 9000  # Unexpected / unclassified

@dataclass(frozen=True)
class ErrorCode:
    """Specific error code within a category."""
    category: ErrorCategory
    sub_code: int          # 0-999
    label: str             # metric-safe label (snake_case)
    description: str       # human-readable

    @property
    def code(self) -> int:
        return self.category.value + self.sub_code

class ErrorRegistry:
    """Centralized registry of all known error codes."""
    _codes: dict[int, ErrorCode]

    def register(self, ec: ErrorCode) -> None: ...
    def get(self, code: int) -> ErrorCode | None: ...
    def by_category(self, cat: ErrorCategory) -> list[ErrorCode]: ...
    def all_labels(self) -> set[str]: ...
```

#### Стандартні коди (pre-registered)

```python
# Pre-register standard codes
ERRORS = ErrorRegistry()
ERRORS.register(ErrorCode(ErrorCategory.VALIDATION, 1, "schema_invalid", "Payload failed schema validation"))
ERRORS.register(ErrorCode(ErrorCategory.VALIDATION, 2, "why_too_long", "WHY field exceeds 80 chars"))
ERRORS.register(ErrorCode(ErrorCategory.TIMEOUT, 1, "ttl_expired", "Message TTL expired"))
ERRORS.register(ErrorCode(ErrorCategory.CIRCUIT_OPEN, 1, "cb_open", "Circuit breaker in OPEN state"))
ERRORS.register(ErrorCode(ErrorCategory.IDEMPOTENCY, 1, "duplicate_rid", "Duplicate request ID"))
ERRORS.register(ErrorCode(ErrorCategory.SECURITY, 1, "sig_invalid", "Ed25519 signature verification failed"))
ERRORS.register(ErrorCode(ErrorCategory.SECURITY, 2, "auth_denied", "RBAC/ABAC access denied"))
ERRORS.register(ErrorCode(ErrorCategory.DR_FAILURE, 1, "wal_corrupt", "WAL hash chain verification failed"))
ERRORS.register(ErrorCode(ErrorCategory.PROTOCOL, 1, "unknown_verb", "Verb not in registry"))
ERRORS.register(ErrorCode(ErrorCategory.PROTOCOL, 2, "version_mismatch", "Message version unsupported"))
```

#### Тести (мінімум 6)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_error_code_numeric` | code = category + sub_code |
| 2 | `test_registry_roundtrip` | register → get |
| 3 | `test_by_category_filter` | by_category → тільки одна категорія |
| 4 | `test_all_labels_unique` | Кожен label унікальний (metric-safe) |
| 5 | `test_standard_codes_registered` | Всі pre-registered codes доступні |
| 6 | `test_error_code_frozen` | ErrorCode is immutable |

**Підсумок 17.1:** ~100 LOC + 6 тестів.

---

### Phase 17.2 — Graceful Shutdown Contract (Constitution §8.4)

**Проблема (Audit Missing Concern #3):** Немає контракту для graceful shutdown та startup ordering.

**Файл:** `vfoundation/core/lifecycle.py`
**Тести:** `tests/vfoundation/core/test_lifecycle.py`

#### Design

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class ShutdownPhase:
    """Ordered shutdown phase."""
    name: str
    priority: int     # lower = earlier (0 = first to shutdown)
    timeout_ms: int   # max time for this phase

class LifecycleHook(ABC):
    """Interface for components that need ordered startup/shutdown."""

    @abstractmethod
    async def on_startup(self) -> None: ...

    @abstractmethod
    async def on_shutdown(self, phase: ShutdownPhase) -> None: ...

    @abstractmethod
    def health_check(self) -> bool: ...

class LifecycleManager:
    """Manages ordered startup and graceful shutdown of components."""
    _hooks: list[tuple[int, str, LifecycleHook]]

    def register(self, name: str, hook: LifecycleHook, priority: int = 50) -> None: ...
    async def startup_all(self) -> list[str]: ...       # returns failed components
    async def shutdown_all(self, timeout_ms: int = 30_000) -> list[str]: ...
    def health_all(self) -> dict[str, bool]: ...
```

#### Тести (мінімум 5)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_startup_order` | Components start in priority order |
| 2 | `test_shutdown_reverse_order` | Shutdown = reverse startup order |
| 3 | `test_shutdown_timeout` | Slow component → timeout, others still shut down |
| 4 | `test_health_all` | Aggregated health status |
| 5 | `test_register_duplicate_name` | Duplicate name → ValueError |

**Підсумок 17.2:** ~80 LOC + 5 тестів.

---

### Phase 17.3 — Security Hardening (RBAC Roles, Nested Redaction, Thread-safe Ratelimits)

**Проблема:** Модулі в `vfoundation/security/` мають мінімальні реалізації:
- `rbac_abac.py`: 12 LOC, тільки admin token check, нема ролей/ABAC
- `redaction.py`: 9 LOC, тільки flat dict, нема nested objects
- `ratelimits.py`: 18 LOC, робочий sliding window, але без thread lock

**Файли:** Оновити існуючі в `vfoundation/security/`
**Тести:** `tests/vfoundation/security/test_security_hardened.py`

#### Етап 17.3.1 — RBAC з ролями

```python
# rbac_abac.py — extend from 12 LOC to ~50 LOC
from enum import Enum

class Role(Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"
    SERVICE = "service"

@dataclass
class Permission:
    resource: str    # e.g., "/debug/*", "/replay/*"
    actions: set[str]  # e.g., {"read", "write", "execute"}

class RBACPolicy:
    """Role-based access control with configurable permissions."""
    _role_permissions: dict[Role, list[Permission]]

    def grant(self, role: Role, perm: Permission) -> None: ...
    def check(self, role: Role, resource: str, action: str) -> bool: ...
    def require(self, role: Role, resource: str, action: str) -> None: ...  # raises
```

#### Етап 17.3.2 — Nested redaction

```python
# redaction.py — extend from 9 LOC to ~30 LOC
def redact(data: dict, sensitive_keys: set[str] | None = None, depth: int = 5) -> dict:
    """Redact sensitive fields from nested dicts/lists up to depth."""
    ...
```

#### Етап 17.3.3 — Thread-safe ratelimiter

```python
# ratelimits.py — add threading.Lock
import threading

class RateLimiter:
    def __init__(self, max_per_sec: int) -> None:
        self._lock = threading.Lock()
        ...
```

#### Тести (мінімум 8)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_rbac_admin_access` | Admin → access granted |
| 2 | `test_rbac_viewer_denied_write` | Viewer → write denied |
| 3 | `test_rbac_require_raises` | Deny → PermissionError |
| 4 | `test_redact_nested_dict` | Nested sensitive key → "***" |
| 5 | `test_redact_list_of_dicts` | List of dicts → all redacted |
| 6 | `test_redact_depth_limit` | depth=1 → only top-level |
| 7 | `test_ratelimit_thread_safety` | Concurrent calls → no race condition |
| 8 | `test_ratelimit_allows_within_budget` | Under limit → all pass |

**Підсумок 17.3:** ~80 LOC (delta) + 8 тестів.

---

### Phase 17.4 — Backpressure / Bounded Queue Contract (Constitution §8.4)

**Проблема (Audit Missing Concern #6):** Constitution §8.4 вимагає: "черги per-key з обмеженням розміру; при p95 latency > порогу — автоматичний throttle". Нульовий код.

**Файл:** `vfoundation/core/backpressure.py`
**Тести:** `tests/vfoundation/core/test_backpressure.py`

#### Design

```python
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

class BackpressureAction(Enum):
    ACCEPT = "accept"
    THROTTLE = "throttle"
    REJECT = "reject"

@dataclass
class QueueStats:
    size: int
    capacity: int
    p95_latency_ms: float
    throttle_active: bool

class BoundedQueue:
    """Per-key bounded queue with automatic backpressure."""

    def __init__(self, capacity: int = 1000, throttle_threshold: float = 0.8):
        self._capacity = capacity
        self._throttle_threshold = throttle_threshold
        self._queues: dict[str, deque] = {}

    def offer(self, key: str, item: Any) -> BackpressureAction: ...
    def poll(self, key: str) -> Any | None: ...
    def stats(self, key: str) -> QueueStats: ...
    def is_throttled(self, key: str) -> bool: ...
```

#### Тести (мінімум 4)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_accept_under_capacity` | Offer → ACCEPT |
| 2 | `test_throttle_at_threshold` | 80%+ → THROTTLE |
| 3 | `test_reject_at_capacity` | 100% → REJECT |
| 4 | `test_poll_reduces_pressure` | Poll → throttle released |

**Підсумок 17.4:** ~60 LOC + 4 тестів.

---

### Phase 17.5 — OTLP Exporter Real HTTP Contract

**Проблема:** `obs/otlp_exporter.py` має лише `NoopOTLPExporter`. Для library completeness потрібен хоча б testable HTTP contract (ABC + mock server).

**Стратегія:** Реалізувати `HttpOTLPExporter` що робить POST запит на configurable endpoint. Не залежати від OTel SDK — lightweight implementation per Constitution §9.2.

**Файл:** Оновити `vfoundation/obs/otlp_exporter.py`
**Тести:** `tests/vfoundation/obs/test_otlp_http.py`

#### Design

```python
class HttpOTLPExporter(OTLPExporter):
    """OTLP exporter via HTTP POST. Requires endpoint URL."""

    def __init__(self, endpoint: str, timeout_ms: int = 5000, batch_size: int = 100):
        self._endpoint = endpoint
        self._timeout_ms = timeout_ms
        self._batch_size = batch_size
        self._buffer: list[dict] = []

    def export(self, spans: list[dict]) -> bool:
        self._buffer.extend(spans)
        if len(self._buffer) >= self._batch_size:
            return self._flush()
        return True

    def _flush(self) -> bool:
        import urllib.request, json
        try:
            req = urllib.request.Request(
                self._endpoint,
                data=json.dumps({"spans": self._buffer}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=self._timeout_ms / 1000)
            self._buffer.clear()
            return True
        except Exception:
            return False

    def shutdown(self) -> None:
        self._flush()

    def is_healthy(self) -> bool:
        return True  # Lightweight: no persistent connection
```

#### Тести (мінімум 3)

| # | Тест | Що перевіряє |
|---|------|-------------|
| 1 | `test_http_exporter_buffers` | Spans buffered until batch_size |
| 2 | `test_http_exporter_flush_called` | batch_size reached → POST (mock server) |
| 3 | `test_http_exporter_failure_returns_false` | Unreachable endpoint → False, no crash |

**Підсумок 17.5:** ~50 LOC (delta) + 3 тестів.

---

### Phase 17 — Gate

```bash
pytest tests/vfoundation -q  # → ~787 passed, 0 failed
```

---

# Зведена таблиця

| Phase | Назва | Нові тести | Нові модулі | Видалені файли | Сукупний підсумок |
|-------|-------|------------|-------------|----------------|-------------------|
| 9.0 | Prerequisites (deps, paths, rid, ADR) | 0 | 0 | 0 | ~531 |
| 9.1 | redis_store tests | ~35 | 0 | 0 | ~566 |
| 9.2 | CLI tests | ~28 | 0 | 0 | ~594 |
| 9.3 | Mock→conftest.py | 0 | 0 | 1 class + 1 orphan | ~594 |
| 9.4 | Delete fsm.py | -1 | 0 | 1 file | ~593 |
| **9 total** | | **~62** | **0** | **3** | **~593** |
| 10.1 | debug_api tests | ~18 | 0 | 0 | ~612 |
| 10.2 | redis_protocol tests | 4 | 0 | 0 | ~616 |
| 10.3 | order_logger tests | 3 | 0 | 0 | ~619 |
| 10.4 | streaming_io tests | 4 | 0 | 0 | ~623 |
| 10.5 | ACL docs | 0 | 0 | 0 | ~623 |
| **10 total** | | **~29** | **0** | **0** | **~623** |
| 11.1 | XAI Store | 8 | 1 | 0 | ~631 |
| 11.2 | why_chain coverage | 6 | 1 | 0 | ~637 |
| 11.3 | OTLP exporter | 6 | 1 | 0 | ~643 |
| 11.4 | Alert hooks | 7 | 1 | 0 | ~650 |
| **11 total** | | **~27** | **4** | **0** | **~650** |
| 12.1 | Chaos tests | 8 | 1 | 0 | ~658 |
| 12.2 | DR timing | 6 | 1 | 0 | ~664 |
| 12.3 | Perf benchmark | 5 | 1 | 0 | ~669 |
| **12 total** | | **~19** | **3** | **0** | **~669** |
| 13.1 | RECONCILE flow | 6 | 1 | 0 | ~675 |
| 13.2 | WAL archive | 6 | 1 | 0 | ~681 |
| 13.3 | GC→Archiver wire | 1 | 0 | 0 | ~682 |
| 13.4 | CLI init command | 4 | 0 | 0 | ~686 |
| 13.5 | Latent Embeddings | 5 | 1 | 0 | ~691 |
| **13 total** | | **~22** | **3** | **0** | **~691** |
| **14** | Deferred refactors | varies | varies | 0 | **TBD** |
| 15.1 | Delete fsm.py | -1 | 0 | 1 file | ~711 |
| 15.2 | CLI drift tests | 4 | 0 | 0 | ~715 |
| 15.3 | CLI test-gen command | 5 | 0 | 0 | ~720 |
| 15.4 | CLI sub-command alignment | 8 | 0 | 0 | ~728 |
| 15.5 | ACL contract tests | 3 | 0 | 0 | ~731 |
| **15 total** | | **~19** | **0** | **1** | **~731** |
| 16.1 | Schema Version Registry | 8 | 1 | 0 | ~739 |
| 16.2 | Message v1↔v2 compat | 8 | 1 | 0 | ~747 |
| 16.3 | data_ref alignment | 6 | 1 | 0 | ~753 |
| 16.4 | Deprecation validator | 7 | 1 | 0 | ~760 |
| **16 total** | | **~29** | **4** | **0** | **~760** |
| 17.1 | Error taxonomy | 6 | 1 | 0 | ~766 |
| 17.2 | Graceful shutdown | 5 | 1 | 0 | ~771 |
| 17.3 | Security hardening | 8 | 0 (updates) | 0 | ~779 |
| 17.4 | Backpressure contract | 4 | 1 | 0 | ~783 |
| 17.5 | OTLP HTTP contract | 3 | 0 (update) | 0 | ~786 |
| **17 total** | | **~26** | **3** | **0** | **~786** |
| **Σ Phases 9–17** | | **~234** | **17** | **4** | **~786** |

---

# Порядок виконання та залежності

```
Phase 9.0 (P0: prerequisites)    ← ПЕРШИЙ КРОК
  ├── 9.0.1 Declare deps          ← fakeredis[lua], pynacl → requirements.txt
  ├── 9.0.2 Fix CLI root + path   ← _cli_root .parent⁴ + drift subpath (v1.3 DEEPENED)
  ├── 9.0.3 Fix debug_api docstr  ← cosmetic
  ├── 9.0.4 Fix FSMCore rid       ← emit() rid passthrough (v1.2 NEW)
  ├── 9.0.5 Dep SSOT policy       ← requirements.txt ↔ pyproject.toml (v1.3 NEW)
  ├── 9.0.6 Protocol drift ADR    ← v=1→v=2, data_ref schema (v1.3 NEW)
  ├── 9.0.7 Fix suite errors      ← 5 collection errors broader suite (v1.3 NEW)
  └── 9.0.8 Idempotency tests     ← activate/migrate tests/idempotency (v1.3 NEW)

Phase 9 (P0: coverage + cleanup) ← після Phase 9.0
  ├── 9.1 redis_store tests       ← незалежний (потребує 9.0.1)
  ├── 9.2 CLI tests               ← незалежний (потребує 9.0.2)
  ├── 9.3 Mock→conftest.py        ← після 9.1-9.2 (щоб не плутати gate)
  └── 9.4 Delete fsm.py           ← після 9.3 (залишити 2 з 3 тестів у final_push)

Phase 10 (P1: audit closure)      ← після Phase 9
  ├── 10.1 debug_api tests        ← незалежний (autouse reset fixture!)
  ├── 10.2 redis_protocol tests   ← незалежний
  ├── 10.3 order_logger tests     ← незалежний
  ├── 10.4 streaming_io tests     ← незалежний
  └── 10.5 ACL docs               ← незалежний

Phase 11 (P2: observability)      ← після Phase 10
  ├── 11.1 XAI Store              ← незалежний
  ├── 11.2 why_chain coverage     ← незалежний
  ├── 11.3 OTLP exporter          ← незалежний
  └── 11.4 Alert hooks            ← незалежний

Phase 12 (P3: quality gates)      ← після Phase 11
  ├── 12.1 Chaos harness          ← потребує 11.4 (alert hooks)
  ├── 12.2 DR timing              ← НЕЗАЛЕЖНИЙ (v1.1: кругова залежність на 13.1 усунена)
  └── 12.3 Perf benchmark         ← незалежний

Phase 13 (P4: feature gaps)       ← після Phase 11
  ├── 13.1 RECONCILE              ← 13.1.0: СПОЧАТКУ verb_registry_v1.yaml!
  ├── 13.2 WAL archive            ← незалежний
  ├── 13.3 GC→Archiver wire       ← після 13.2
  ├── 13.4 CLI init               ← незалежний
  └── 13.5 Latent Embeddings      ← незалежний

Phase 14 (P5: refactoring)        ← після Phase 13 + domain tests
  ├── 14.1 Split decision_making  ← потребує domain tests
  ├── 14.2 Split exec fsm         ← потребує domain tests
  ├── 14.3 Message envelope       ← потребує 14.1, 14.2, 16.1-16.4 (schema infra!)
  └── 14.4 Typed pld              ← після 14.3

Phase 15 (P6: cleanup + CLI)      ← після Phase 13 (незалежний від 14)
  ├── 15.1 Delete fsm.py          ← carry-over від Phase 9.4
  ├── 15.2 CLI drift tests        ← незалежний
  ├── 15.3 CLI test-gen            ← незалежний
  ├── 15.4 CLI sub-command align   ← незалежний
  └── 15.5 ACL contract tests     ← незалежний

Phase 16 (P7: schema versioning)  ← після Phase 13 (ПЕРЕД Phase 14.3!)
  ├── 16.1 Schema Version Reg     ← незалежний
  ├── 16.2 Message v1↔v2 compat   ← потребує 16.1
  ├── 16.3 data_ref alignment     ← незалежний
  └── 16.4 Deprecation validator  ← потребує 16.1

Phase 17 (P8: cross-cutting)      ← після Phase 13 (незалежний від 14-16)
  ├── 17.1 Error taxonomy          ← незалежний
  ├── 17.2 Graceful shutdown       ← незалежний
  ├── 17.3 Security hardening      ← незалежний
  ├── 17.4 Backpressure contract   ← незалежний
  └── 17.5 OTLP HTTP contract     ← потребує 11.3 (OTLP ABC)
```

**Паралелізм:** Phases 15, 16, 17 — **незалежні один від одного** і від Phase 14.1–14.2.
Phase 14.3 (Message envelope refactor) **потребує Phase 16** (schema versioning infra) як prerequisite.

---

# Інваріанти (правила для кожного етапу)

1. **Gate:** Кожен етап завершується `pytest tests/vfoundation -q` → 0 failures
2. **Non-breaking:** Phases 9–13, 15, 17 — additive only. Жодних змін до існуючих API.
3. **Registry-first:** Якщо додається новий verb — спочатку `verb_registry_v1.yaml` (§0 copilot-instructions)
4. **Мінімальний diff:** Кожен етап — 1 тема. Не змішувати features з cleanup.
5. **ROADMAP update:** Після кожної Phase — оновлення таблиці прогресу в ROADMAP_HARDENING.md
6. **Commit convention:** `phase-X.Y: description` (e.g., `phase-9.1: redis_store tests`)
7. **Backward compat:** Phases 16 (schema versioning) — зберігати backward compat для v=1 Messages
8. **Breaking convention:** Phase 14 — кожен sub-phase = окремий PR з migration guide
9. **No hardcoded values:** Жодних захардкоджених параметрів — use config/env/arguments

---

# Domains Without vfoundation Integration (довідник)

5 доменів не використовують vfoundation:

> **v1.3 NOTE:** Фактично `apps/reference/domains/` містить **16 доменів**, не 5.
> Нижче перелічені ті, що не мають прямого імпорту vfoundation. Повний перелік неінтегрованих —
> потребує окремий аудит всіх 16 доменів (див. Staff Architect audit, claim #17).

| Domain | LOC (≈) | Складність інтеграції | Пріоритет |
|--------|---------|----------------------|-----------|
| `exchange_filters/` | ? | LOW — утилітарний, без FSM | P4 |
| `inflight_reconcile/` | ? | HIGH — потребує RECONCILE flow (Phase 13.1) | P3 |
| `neocortex/` | ? | HIGH — ML domain, складна логіка | P4 |
| `regime_allowlist/` | ? | LOW — утилітарний lookup | P4 |
| `snapshot_scheduler/` | ? | MEDIUM — потребує DR/snapshot integration | P3 |

**Інтеграція цих доменів — ПІСЛЯ Phase 13.** Кожен домен — окремий PR з:
1. Додати `from vfoundation.core.protocol import Message`
2. Замінити ad-hoc event emission на `FSMCore.emit()`
3. Додати `why` field to all messages
4. Register verbs в `verb_registry_v1.yaml`

---

# Ризики та мітігація

| Ризик | Вплив | Мітігація |
|-------|-------|-----------|
| fakeredis не підтримує Lua-скрипти у новій версії | Phase 9.1 blocked | Тестувати з `fakeredis[lua]` >= 2.0; fallback: mock evalsha |
| CLI тести CWD-залежні | Phase 9.2 flaky | `monkeypatch.chdir(tmp_path)` для кожного тесту |
| drift command path was broken (v1.0) | Phase 9.2.9 fails | **v1.3 FIX:** Root-cause (_cli_root) + subpath виправлено в Phase 9.0.2 |
| Undeclared deps (fakeredis, pynacl) | Phase 9.1/9.2 ImportError | **v1.1 FIX:** Phase 9.0.1 declares both in requirements.txt |
| FSMCore.emit() генерує новий rid | Envelope-level traceability gap | **v1.2 FIX:** Phase 9.0.4 додає optional `rid` param (backward-compatible) |
| `_cli_root` резолвиться в `vfoundation/`, не repo root | **ВСІ** CLI path-based команди падають | **v1.3 FIX:** Phase 9.0.2 додає .parent level |
| Constitution `v=2` vs code `v=1` drift | Contract compliance gap | **v1.3 FIX:** Phase 9.0.6 ADR, deferred до Phase 14.3 |
| Dependency SSOT bifurcated (req.txt ≠ pyproject.toml) | CI installs different deps | **v1.3 FIX:** Phase 9.0.5 alignment policy |
| 5 collection errors у broader suite | Full `pytest tests/` не працює | **v1.3 FIX:** Phase 9.0.7 cleanup |
| Idempotency tests globally skipped | False confidence exactly-once | **v1.3 FIX:** Phase 9.0.8 activation plan |
| Chaos injection змінює global state | Phase 12.1 side effects | Context managers з guaranteed cleanup |
| Phase 14 breaking changes | Production downtime | Deprecation window 2 releases, migration script, окремий blueprint |
| CLI sub-command restructuring | Existing scripts break | Flat commands зберігаються як deprecated aliases (Phase 15.4) |
| Message v=1→v=2 migration | All consumers must update | Backward compat layer (Phase 16.2), auto-upgrade з warning |
| `data_ref` type change (List[str]→List[DataRef]) | Existing code breaks | Union type `str | DataRef` з Pydantic validator (Phase 16.3) |
| Schema versioning adds complexity | Over-engineering | Minimal viable: registry + deprecation decorator only. No full schema evolution framework. |
| Security hardening changes RBAC behavior | Existing `require_admin()` callers | Зберегти `require_admin()` як legacy wrapper поверх нового RBACPolicy |
| OTLP HTTP exporter timeout | Network issues у тестах | Mock HTTP server з `http.server` у тестах, no real network |
| Thread-safe ratelimiter perf overhead | Hot-path latency increase | Lock contention мінімальний при нормальному load |

---

**Документ версія:** 1.4 (v1.1 + Gemini errata + Staff Architect errata + **Gap Analysis to 90%**)
**Автор:** Copilot Engineering Agent
**Статус:** DRAFT — очікує затвердження

---

# Додаток A: Незалежний аудит Blueprint v1.0

**Дата аудиту:** 2026-02-21
**Метод:** Незалежна верифікація 10 конкретних claims проти реального коду.
**Загальна оцінка v1.0:** 6.3/10

## Знахідки (верифіковані)

### HIGH severity (4)

| # | Знахідка | Статус у v1.1 |
|---|---------|---------------|
| H1 | `fakeredis[lua]` НЕ задекларований у `requirements.txt` — blueprint казав "вже в dev-deps" | ✅ Виправлено: Phase 9.0.1 |
| H2 | `pynacl` незадекларований — CLI `__main__.py` падає без PyNaCl | ✅ Виправлено: Phase 9.0.1 |
| H3 | `vfound drift` хардкодить `apps/monitoring/drift_monitor.py` — файл НЕ існує. Реальний шлях: `apps/reference/domains/execution_position/drift_monitor.py` | ✅ Виправлено: Phase 9.0.2 |
| H4 | RECONCILE/REPAIR verbs **відсутні** у `apps/reference/dictionaries/verb_registry_v1.yaml`. Phase 13.1 пропонував реалізацію без registry entry — порушення copilot-instructions §2 | ✅ Виправлено: Phase 13.1.0 |

### MEDIUM severity (3)

| # | Знахідка | Статус у v1.1 |
|---|---------|---------------|
| M1 | Phase 12.2→13.1 кругова залежність: DR timing "потребує RECONCILE", але Phase 12 перед Phase 13 | ✅ Виправлено: Phase 12.2 note + dep graph |
| M2 | `debug_api.py` глобальний стан (`_router_timings_ms`, `_total_requests`, `_timeout_count`, `_drift_reports`) ніколи не reset між тестами | ✅ Виправлено: Phase 10.1.0 autouse fixture |
| M3 | Zero schema versioning інфраструктура — Phase 14.3 потребує deprecation windows, але інфраструктури нема | ✅ Позначено: Phase 14 note про окремий blueprint |

### LOW severity (3)

| # | Знахідка | Статус у v1.1 |
|---|---------|---------------|
| L1 | `tests/vfoundation/fixtures/mock_execution_adapter.py` — orphan dead code, import path не працює | ✅ Виправлено: Phase 9.3 використає conftest.py |
| L2 | `test_coverage_final_push.py` має 3 тести (не 1): fsm, Config.wal_dir, IdempotencyStore | ✅ Виправлено: Phase 9.4 явно зберігає тести 2 і 3 |
| L3 | ~5/18 запланованих debug_api тестів дублюють покриття в `test_metrics_smoke.py` та `test_final_90_percent.py` | ✅ Позначено: Phase 10.1 note про дедуплікацію |

## Оцінка за 10 критеріями

| Критерій | v1.0 | v1.1 | Коментар |
|----------|------|------|----------|
| Повнота | 7/10 | 8/10 | Додано Phase 9.0, verb registry кроки |
| Точність | 5/10 | 8/10 | Всі 4 HIGH path/dep помилки виправлені |
| Здійснимість | 6/10 | 8/10 | Залежності задекларовані, шляхи валідні |
| Пріоритизація | 8/10 | 9/10 | Phase 9.0 як обов'язковий prerequisite |
| Гранулярність | 9/10 | 9/10 | Без змін (була сильна) |
| Управління залежностями | 4/10 | 8/10 | Кругова залежність усунена, deps declared |
| Ризик-менеджмент | 6/10 | 7/10 | Додано rollback plan для Phase 14 |
| Контрактна відповідність | 5/10 | 9/10 | Verb registry compliance забезпечена |
| Підтримуваність | 7/10 | 8/10 | Conftest.py замість orphan fixtures |
| Тестопридатність | 6/10 | 8/10 | Reset fixtures, дедуплікація noted |
| **Загальна** | **6.3/10** | **8.2/10** | |

## 10 Рекомендацій (трекер)

| # | Рекомендація | Статус |
|---|-------------|--------|
| 1 | Додати Phase 9.0 — dependency fix: `fakeredis[lua]`, `pynacl` → requirements.txt; fix drift path | ✅ Done |
| 2 | Phase 13.1 — register RECONCILE/REPAIR в verb_registry ПЕРЕД implementation | ✅ Done |
| 3 | Phase 12.2 — усунути залежність на 13.1 (кругова) | ✅ Done |
| 4 | Phase 9.2.9 — fix drift command path або mark SKIP/DEFERRED | ✅ Done (path fix) |
| 5 | Phase 9.4 — explicitly state "видалити тест 1, залишити тести 2 і 3" | ✅ Done |
| 6 | Phase 10.1 — додати autouse fixture для reset 4 debug_api globals | ✅ Done |
| 7 | Phase 9.3 — inline MockExecutionAdapter в conftest.py замість broken import | ✅ Done |
| 8 | Додати Phase 12.5 — integration smoke test (WAL→snapshot→replay e2e) | ⏳ Deferred to Phase 12 impl |
| 9 | Replace test count metric з `pytest --cov=vfoundation --cov-fail-under=85` | ⏳ Deferred to Phase 12 impl |
| 10 | Phase 14 — needs separate detailed blueprint з rollback plan | ✅ Noted in Phase 14 section |

---

# Додаток B: Архітектурний аудит (Gemini)

**Дата аудиту:** 2026-02-21
**Автор:** Independent Architectural Auditor (Gemini)
**Метод:** Full code + doc review, Constitution cross-reference, 15-criterion scoring
**Вердикт:** CONDITIONAL GO (Requires Pre-Phase 9 Blocker Resolution)
**Повний документ:** [ARCHITECTURAL_REVIEW_gemini.md](ARCHITECTURAL_REVIEW_gemini.md)

## Підтверджені claims (verified)

| Claim | Перевірка | Статус |
|-------|-----------|--------|
| `fakeredis[lua]` і `pynacl` відсутні в requirements.txt | `grep -c 'fakeredis\|pynacl' requirements.txt` → 0 | ✅ Підтверджено (вже в Phase 9.0.1) |
| CLI drift path broken (`apps/monitoring/`) | `__main__.py` line 289 | ✅ Підтверджено (вже в Phase 9.0.2) |
| RECONCILE/REPAIR не в verb_registry | `verb_registry_v1.yaml` search | ✅ Підтверджено (вже в Phase 13.1.0) |
| MockExecutionAdapter stranded in production | `execution_adapter.py` ~line 468 | ✅ Підтверджено (вже в Phase 9.3) |
| `debug_api.py` global mutable state з locks | 4 module-level vars + `_metrics_lock` | ✅ Підтверджено (вже в Phase 10.1.0) |
| ExchangeACL — повний stub | `stream_events()` yields fake SOLUSDT | ✅ Підтверджено (вже в Phase 10.5) |
| LOC counts точні (redis_store ~554, CLI 421) | `wc -l` verification | ✅ Підтверджено |

## Нова знахідка (прийнята)

| # | Знахідка | Severity | Статус у v1.2 |
|---|---------|----------|---------------|
| G1 | `FSMCore.emit()` не передає `rid` до `Message()` — генерується новий UUID. Envelope-level traceability gap (бізнес-rid зберігається в `pld["rid"]`, тому trade correlation працює). | MEDIUM | ✅ Додано Phase 9.0.4 |

## Спростовані claims

| # | Claim | Чому спростовано |
|---|-------|------------------|
| G2 | "ExecPosFSM intentionally drops price_ctx, falling back to static config multipliers" | `_smart_extract()` (fsm.py lines 740–770) **явно** витягує дані з `price_ctx` nested dict. DecisionMaking передає `stop_price`/`target_price` на root рівні payload. Дані проходять end-to-end. |
| G3 | "Correct drift path is `vfoundation/obs/drift_monitor.py`" | Файл `vfoundation/obs/drift_monitor.py` **не існує**. Реальний шлях: `apps/reference/domains/execution_position/drift_monitor.py` (аудит ввів власну помилку). |

## Scoring порівняння

| Критерій аудиту | Gemini Score (binary 0/1) | Наш коментар |
|----------------|--------------------------|---------------|
| Constitutional adherence | 0 | Verb registration для RECONCILE/REPAIR — Phase 13 scope, не Phase 9 blocker |
| Contract-first schema | 0 | **Спростовано:** price_ctx propagation працює |
| E2E Traceability | 0 | Частково — envelope rid gap реальний, але бізнес-rid через pld працює. Виправлено Phase 9.0.4 |
| Locking/Concurrency | 0 | debug_api locks — dev-only endpoint, не production hot path |
| Crypto verification | 0 | Deps відсутні в requirements.txt — вже виправлено Phase 9.0.1 |
| Modularity | 0 | Монолітні домени ~4K LOC — Phase 14 scope (deferred by design) |
| **Gemini Total** | **8/15 (53%)** | Binary scoring занадто harsh. 3 з 7 "failures" спростовані або вже адресовані. |

---

# Додаток C: Staff Architect аудит

**Дата аудиту:** 2026-02-21
**Автор:** Independent Staff Architect
**Метод:** Full code + doc review, Constitution cross-reference, 15-criterion weighted scoring
**Вердикт:** **No-Go** без Pre-Phase 9 hardening (5.1/10)
**Повний документ:** [ARCHITECTURAL_REVIEW.md](ARCHITECTURAL_REVIEW.md)

> Це найглибший з трьох аудитів: 20 конкретних клеймів з рядками коду, 8 архітектурних прогалин,
> 15-критеріїв скоринг, 8 Missing Concerns, risk matrix з probability×impact.

## Верифікація claims (20 клеймів)

### ПІДТВЕРДЖЕНО (14/20)

| # | Claim | Деталі | Статус у v1.3 |
|---|-------|--------|---------------|
| 1 | `_cli_root` резолвиться в `vfoundation/`, не repo root — Phase 9.0.2 fix неповний | `.parent.parent.parent` = `vfoundation/`, не repo root. Навіть правильний subpath під `_cli_root` = `vfoundation/apps/reference/...` — не існує | ✅ Phase 9.0.2 deepened: +1 parent level |
| 2 | Dependency SSOT роздвоєний (requirements.txt ≠ pyproject.toml) | `requirements.txt` — 0 redis/PyNaCl. `pyproject.toml` — має всі | ✅ Phase 9.0.5 NEW |
| 3 | FSMCore.emit() rid passthrough gap | Вже знали з v1.2 | ✅ Phase 9.0.4 (unchanged) |
| 5 | Legacy `fsm.py` ще використовується | Blueprint Phase 9.4 планує видалення — коректно | ✅ Phase 9.4 (unchanged) |
| 8 | Coverage: redis_store 0%, debug_api 30% | Підтверджено — саме тому Blueprint існує | ✅ Phases 9.1, 10.1 |
| 9 | ExchangeACL: `_stub_submit` в обох shadow/live гілках | `if shadow_mode: _stub_submit() else: _stub_submit()` — ідентичний код | ✅ Phase 10.5 stub marker |
| 11 | `why_explain_ref` без producer/consumer | Поле є в `protocol.py`, ніде не використовується | ✅ Phase 11.1 XAI Store |
| 12 | DR timing — synthetic, без real I/O benchmark | Fair critique | ⏳ Phase 12.2 scope note |
| 13 | 5 collection errors у broader test suite (namespace collision) | `2200 collected, 5 errors`. Причина: `vfoundation.core is not a package` | ✅ Phase 9.0.7 NEW |
| 14 | RECONCILE/REPAIR не в verb_registry | Grep → 0 matches | ✅ Phase 13.1.0 (unchanged) |
| 15 | WAL archive — TODO залишок | `wal_gc.py:63: # Archive to S3/cloud (optional - TODO)` | ✅ Phase 13.2/13.3 (unchanged) |
| 18 | Phase 14 envelope refactor — HIGH risk | `oco_group_id` використовується в 10+ місцях ExecPosFSM top-level | ✅ Phase 14 note (unchanged) |
| 19 | `vfound migrate` CLI не існує | Підтверджено — Phase 14.3 потребує | ⏳ Phase 14 scope |
| 20 | Backward compat infra відсутня | Немає deprecation validators | ⏳ Phase 14 scope |

### НОВА ЗНАХІДКА (прийнята, 3)

| # | Знахідка | Severity | Статус у v1.3 |
|---|---------|----------|---------------|
| N1 | Constitution `v=2`, код `v=1` — Message version contract drift | HIGH | ✅ Phase 9.0.6 ADR NEW |
| N2 | `data_ref: List[str]` в коді vs `[{uri, sha256, bytes, ctype}]` в Constitution | HIGH | ✅ Phase 9.0.6 ADR (same) |
| N3 | `tests/idempotency/` globally skipped via `pytest.skip()` — false confidence | MEDIUM | ✅ Phase 9.0.8 NEW |

### ХИБНЕ ТРАКТУВАННЯ (3/20)

| # | Claim | Чому |
|---|-------|------|
| 4 | "MockExecutionAdapter не перенесений в conftest" — Blueprint каже "fixed" | Blueprint **планує** це в Phase 9.3, не стверджує зроблено. `conftest.py` логічно ще не існує |
| 7 | "Цільові test-файли Phase 10 не існують" | Phase 10 **планує їх створити**. Це план інженерних робіт, не звіт |
| 17 | "5 доменів без vfoundation, але фактично 6" | Фактично `apps/reference/domains/` має **16** піддиректорій. Агент сам помилився в підрахунку |

### ТРИВІАЛЬНЕ (1/20)

| # | Claim | Коментар |
|---|-------|---------|
| 6 | LOC mismatch (421 vs 420, 554 vs 553) | Різниця 1-3 рядки, не є проблемою |

## Архітектурні прогалини (8)

| # | Severity | Gap | Статус у v1.3 |
|---|----------|-----|---------------|
| 1 | HIGH | CLI `_cli_root` → `vfoundation/` блокує DR tooling | ✅ Phase 9.0.2 (deepened) |
| 2 | HIGH | Exactly-once false confidence (redis_store 0% coverage, idempotency tests skipped) | ✅ Phase 9.1 + 9.0.8 |
| 3 | HIGH | Constitution v=2 vs runtime v=1 contract drift; data_ref schema mismatch | ✅ Phase 9.0.6 ADR |
| 4 | HIGH | RECONCILE/REPAIR без SSOT registry entry | ✅ Phase 13.1.0 (unchanged) |
| 5 | MEDIUM | DR archive/WORM залишається TODO | ✅ Phase 13.2/13.3 |
| 6 | MEDIUM | Phase 14 без migrate CLI / schema versioning pipeline | ⏳ Phase 14 scope |
| 7 | MEDIUM | Cross-domain coupling / hidden imports | ⏳ Phase 14 scope |
| 8 | LOW | LOC-based пріоритизація неточна | Acknowledged, not actionable |

## Missing Concerns (8)

Агент ідентифікував 8 cross-cutting concerns які Blueprint не покриває:

| # | Concern | Severity | Дія |
|---|---------|----------|-----|
| 1 | Schema/version lifecycle (compatibility matrix, automated contract diff) | MEDIUM | Частково: Phase 9.0.6 ADR |
| 2 | Canary/feature flags для Phase 14 breaking changes | MEDIUM | ⏳ Phase 14 bluepr scope |
| 3 | Graceful shutdown + startup ordering tests | LOW | ⏳ Post-blueprint |
| 4 | Error taxonomy (codes/classes/metric labels) | MEDIUM | ⏳ Post-blueprint |
| 5 | Metric naming convention + cardinality budget | LOW | ⏳ Post-blueprint |
| 6 | Backpressure/rate-limiting at system boundary | MEDIUM | Constitution req, ⏳ Post-blueprint |
| 7 | Dependency SSOT policy | MEDIUM | ✅ Phase 9.0.5 |
| 8 | Package boundary hardening (namespace pitfalls) | MEDIUM | ✅ Phase 9.0.7 (partial) |

## Scoring порівняння (усі три аудити)

| Аудит | Скоринг | Кількість клеймів | Підтверджені | Нові знахідки | Вердикт |
|-------|---------|-------------------|-------------|---------------|---------|
| Self-audit (v1.0→v1.1) | 6.3→8.2/10 | 10 | 10/10 | 0 (self) | Conditional Go |
| Gemini (v1.1→v1.2) | 8/15 (binary) | ~15 | 7/15 | 1 (rid passthrough) | Conditional Go |
| **Staff Architect (v1.2→v1.3)** | **5.1/10** | **20** | **14/20** | **3** (`_cli_root`, Constitution drift, idempotency skip) | **No-Go → Conditional Go after v1.3** |

### Post-v1.3 self-assessment

| Критерій (з аудиту) | Score v1.2 | Score v1.3 | Коментар |
|---------------------|-----------|-----------|---------|
| 1. Архітектурна відповідність Constitution | 5 | 6 | ADR для v=1→v=2 / data_ref. Drift задокументований. |
| 2. Повнота production scenarios | 4 | 5 | Broader suite, idempotency activation planned |
| 3. Реалістичність test strategy | 5 | 6 | Suite errors addressed, dep SSOT aligned |
| 4. Пріоритизація | 7 | 8 | Phase 9.0 розширений з 4 до 8 sub-steps |
| 5. Інкрементальність | 8 | 8 | Без змін |
| 6. Contract-first compliance | 5 | 7 | Registry-first + ADR для protocol drift |
| 7. Security coverage | 6 | 6 | Без змін (KMS/WORM out of scope) |
| 8. DR/HA coverage | 4 | 5 | CLI root fix unblocks DR tooling |
| 9. Observability | 6 | 6 | Без змін |
| 10. Backward compat | 4 | 5 | ADR defines migration timeline |
| 11. Domain integration | 3 | 4 | 16 domains acknowledged, audit note |
| 12. CI/CD readiness | 4 | 6 | Broader suite fix, dep alignment |
| 13. Performance | 5 | 5 | Без змін |
| 14. Error handling taxonomy | 3 | 3 | Deferred to post-blueprint |
| 15. Doc quality | 7 | 8 | Errata system + 3 appendices |
| **Середній** | **5.1** | **5.9** | **+0.8 points** |

> **Висновок:** v1.3 закриває 3 з 4 HIGH arch gaps (CLI root, Constitution drift ADR, RECONCILE registry).
> Четвертий HIGH (exactly-once coverage) закривається Phase 9.1 при імплементації.
> Після Phase 9.0 completion — **Conditional Go** для Phase 9+.
