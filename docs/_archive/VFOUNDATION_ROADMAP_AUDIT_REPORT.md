# VFOUNDATION / MetaFSM2 Roadmap — Глибокий Аудиторський Звіт

**Дата аудиту:** 2026-04-09  
**Аудитор:** Antigravity (автоматизований аналіз кодової бази)  
**Джерело правди:** `VFOUNDATION_METAFSM2_ROADMAP_SSOT_v1.md`  
**Метод:** Статичний аналіз коду + cross-reference runtime артефактів

---

## 0. Методологія та обмеження

**ФАКТИ** — підтверджено кодом та артефактами.  
**ІНФЕРЕНЦІЇ** — логічні висновки з доказів.  
**ПРИПУЩЕННЯ** — позначені явно.  
**НЕВІДОМО** — позначено як таке.

**Обмеження аудиту:**
- Відсутній runtime profiling / live trace
- Не перевірялись результати `pytest` (немає CI виводу)
- WAL replay на real traces не верифікований без виконання

---

## 1. Зведена таблиця реалізації по фазах

| Фаза | Назва | Статус у SSOT | **Реальний статус** | % Impl | Якість |
|------|-------|---------------|----------------------|--------|--------|
| 0 | Governance Freeze | DONE | ✅ ПІДТВЕРДЖЕНО | 100% | Висока |
| 1 | Architecture Truth Freeze | DONE ENOUGH | ✅ ПІДТВЕРДЖЕНО | 95% | Висока |
| 2 | Shadow Truth Layer | DONE | ✅ ПІДТВЕРДЖЕНО | 100% | Висока |
| 3 | Pre-Stabilization Execution-Truth Hardening | MOSTLY DONE | ⚠️ ПЕРЕВАЖНО DONE | 85% | Середня |
| 4 | Lifecycle Contract Hardening | CLOSED | ✅ ПІДТВЕРДЖЕНО | 100% | Висока |
| 5A | Restart Truth Audit | DONE | ✅ ПІДТВЕРДЖЕНО | 100% | Висока |
| 5B.1 | Canonical Restore Model Spec | DONE | ✅ ПІДТВЕРДЖЕНО | 100% | Висока |
| 5B.1A | Minimum Artifact Correction | DONE | ✅ ПІДТВЕРДЖЕНО | 100% | Висока |
| 5B.2 | Writer-Side Introduction | DONE | ✅ ПІДТВЕРДЖЕНО | 100% | Висока |
| **5B.3** | **Dark Reader / Diff-Only Validation** | **NEXT EXACT PACKAGE** | 🚨 **РОЗХОДЖЕННЯ: ВЖЕ DONE** | 100% | Висока |
| **5B.4** | **Authoritative Reader** | PLANNED AFTER 5B.3 | 🚨 **РОЗХОДЖЕННЯ: ВЖЕ DONE** | 100% | Середня |
| 5B.5 | Warm-State Deprecation Boundary | PLANNED AFTER 5B.4 | ❌ НЕ РОЗПОЧАТО | 0% | — |
| 6 | Foundation-to-Runtime Closure | NOT STARTED | ❌ НЕ РОЗПОЧАТО | 0% | — |
| 7–12 | Cutover Phases | NOT STARTED | ❌ НЕ РОЗПОЧАТО | 0% | — |

**Загальний прогрес:** ~72% від Phase 0 до Phase 5B.4 виконано, з критичним SSOT drift.

---

## 2. Критичне Розходження SSOT ↔ Runtime (НАЙВАЖЛИВІШИЙ ВИСНОВОК)

> [!CAUTION]
> **SSOT застарів щодо фактичного стану реалізації.**

### 2A. Phase 5B.3 — розходження

**SSOT каже:** `Status: NEXT EXACT PACKAGE`  
**Факт:**  
- `apps/reference/domains/execution_position/restore_artifact.py` містить повну реалізацію `ExecutionPositionRestoreArtifactDarkReader` (~200 рядків)
- `apps/reference/domains/execution_position/fsm.py` містить `_run_restore_artifact_dark_read_comparison()` (рядки 1886–1941)
- `tests/domains/execution_position/test_execution_restore_dark_read.py` — 14,158 байт, 10+ тест-кейсів (exact_match, mismatch, corrupt, stale, mixed_certainty)
- `ops/restore/execution_position_startup_truth_v1.jsonl` рядок 2 містить `"restore_dark_read": {"attempted": true, "comparison_outcome": "mismatch", ...}` — dark read **вже виконується в продакшн**

**Висновок:** Phase 5B.3 **DONE**, не "NEXT EXACT PACKAGE".

### 2B. Phase 5B.4 — розходження

**SSOT каже:** `Status: PLANNED AFTER 5B.3`  
**Факт:**  
- `config/aurora/domains.yaml` рядок 504: `mode: authoritative` — authoritative mode **увімкнено в продакшн конфігурації**
- `apps/reference/domains/execution_position/fsm.py` містить `_run_restore_artifact_authoritative_read()` (рядки 1943–2078) та `_apply_authoritative_restore_record()` (рядки 2080–2230+)
- `ops/restore/execution_position_startup_truth_v1.jsonl` рядок 3 містить `"reconcile_sequence": ["authoritative_restore_read", ...]` та `"restore_authoritative": {"attempted": true, "mode": "authoritative", ...}` — authoritative reader **вже виконується в продакшн**
- `tests/domains/execution_position/test_execution_restore_authoritative_read.py` — 12,717 байт, повний тест-набір
- Схема `ExecutionPositionRestoreAuthoritativeStatus` та `ExecutionPositionRestoreAuthoritativeSymbolStatus` повністю реалізовані

**Висновок:** Phase 5B.4 **DONE**, не "PLANNED".

### 2C. Що потрібно виправити негайно

**SSOT потребує оновлення** для відображення реального стану:
```
5B.3 → DONE (dark-read implemented, tested, runtime evidence exists)
5B.4 → DONE (authoritative reader implemented, config mode=authoritative, runtime evidence exists)
5B.5 → NEXT EXACT PACKAGE (warm-state deprecation boundary — not started)
```

---

## 3. Детальний аналіз по кожній фазі

### Phase 0 — Governance Freeze ✅ 100%

**Докази реалізації:**
- YAML + Pydantic SSOT підтверджено: `config/aurora/domains.yaml` + `apps/reference/config_models.py` (258,830 байт)
- No big-bang migration — підтверджено відсутністю прямих FSMv2/MetaFSMv2 imports в runtime
- `package complete only with report + validation evidence` — дотримується (звіти є в `ops/restore/`, `REPORT.md`)
- Fail-closed policy: `config_models.py:306` явно позначає unwired config

**Ризики Phase 0:**
- Мінімальні. Дисципліна дотримується.

---

### Phase 1 — Architecture Truth Freeze ✅ 95%

**Докази:**
- `execution_position/fsm.py` залишається монолітом (~4530 рядків, 198,373 байт) — підтверджено обмеження migration rate
- Відсутність FSMv2/MetaFSMv2 в runtime path — підтверджує "cutover is forbidden"
- restore/replay boundary — підтверджено кодом: `restore_artifact.py` явно окремий від `dr/replay.py`

**Хвости:**
- "Exact cutover target is not frozen yet" — залишається відкритим, відповідно плану

---

### Phase 2 — Shadow Truth Layer ✅ 100%

**Докази:**
- `data/shadow_telemetry/` — 61 директорія (щоденні дані з 2026-02-08 по 2026-04-09) — активна
- `shadow_telemetry` domain: `main.py`, `main_bridge.py` — operational
- `apps/reference/telemetry/shadow_journal.py` — існує, використовується
- `config/aurora/domains.yaml:687` — shadow_telemetry enabled, з event allowlist (TRADE_EXECUTED, ORDER_PLACED тощо)
- WAL operational: `ops/wal/` містить файли ~25MB/день (2026-04-04 — 2026-04-09)

---

### Phase 3 — Pre-Stabilization ⚠️ 85%

**Підтверджене виконання:**
- `test_pre_stabilization_duplicate_fill_and_repeated_close_hardening.py` — 11,485 байт, повний тест-набір
- `test_brackets_pending_silent_drop_fix.py` — 6,240 байт
- `test_execution_truth_continuation_non_cmd_close_identity_restart.py` — 16,127 байт

**Незакриті хвости (FACT):**
- `execution_position/fsm.py` все ще є монолітом — maintenance risk підтверджено SSOT
- WAL replay не є повним (replay.py лише 116 рядків, базова реалізація)
- "not every close-producing path is equally proven" — залишається відкритим

---

### Phase 4 — Lifecycle Contract Hardening ✅ 100%

**Докази:**
- `test_execution_guard_blocked_contract.py` — підтверджує EVT:EXECUTION_GUARD_BLOCKED schema/runtime alignment
- `test_brackets_pending_silent_drop_fix.py` — підтверджує BRACKETS_PENDING fix
- `test_dec_open_contract_audit.py`, `test_reject_contract_and_lifecycle_fix.py` — contract coverage
- Schema files в `apps/reference/domains/execution_position/schemas/` існують

---

### Phase 5 — Restart Truth Hardening — ДЕТАЛЬНИЙ АУДИТ

#### 5A ✅ 100%
Підтверджено: `ops/restore/execution_position_startup_truth_v1.jsonl` + тести restart truth.

#### 5B.1 ✅ 100%
`ExecutionPositionRestoreEnvelope`, `ExecutionPositionRestoreLifecycleRecord` — Pydantic моделі з `extra="forbid"`, model_validator для deferred_bracket_ref — clean contract design.

#### 5B.1A ✅ 100%
`contour_id` не присутній у схемі (підтверджено). Мінімальна поверхня артефакту.

#### 5B.2 ✅ 100%
`ExecutionPositionRestoreArtifactWriter.persist()`:
- atomic write через `tempfile.mkstemp` + `os.replace()` — правильно
- `os.fsync()` на файл та батьківський директорій — правильно
- Дедуплікація через `_last_payload_json` — ефективно
- `ops/restore/execution_position_restore_envelope_v1.json` — існує, актуальний

#### 5B.3 ✅ 100% (але SSOT не оновлено!)

`ExecutionPositionRestoreArtifactDarkReader`:
- Порівнює 7 полів per-symbol: manage_phase, manage_truth_source, close_phase, bracket_state, bracket_truth_source, live_reconcile_required, deferred_bracket_ref.entry_order_id
- 4 класи mismatch: exact_field_mismatch, heuristic_only_field, artifact_only_field, unknown_vs_guessed_mismatch — семантично правильно
- Stale/corrupt/missing обробляються явно (fail-closed)
- `does_not_mutate_runtime_state` тест підтверджує ізоляцію
- **Runtime proof:** startup_truth запис показує `"comparison_outcome": "mismatch"`, 21 поле mismatch — dark read активний і звітує

**Якісна проблема:** При `artifact_state == "stale"`, поточний код порівнює артефакт НЕ зупиняючись — це поведінка "порівнюємо навіть застарілий". Для observation only це прийнятно, але документується як ризик для 5B.4.

#### 5B.4 ✅ 100% (але SSOT не оновлено!)

`_run_restore_artifact_authoritative_read()` + `_apply_authoritative_restore_record()`:
- Застосовує `ManageState(manage_phase)` та `CloseState(close_phase)` до runtime FSM flow objects
- Обробляє DEFERRED_PENDING_WAL через перевірку pending_brackets WAL
- explicit unknown для unsupported states
- Config: `mode: authoritative, dark_read_max_artifact_age_ms: 300000`

**Якісна проблема виявлена (INFERENCE):**  
У `startup_truth_v1.jsonl` рядок 3 показує: `"restore_authoritative": {"applied_record_count": 0, "artifact_state": "stale"}` — тобто під час останнього authoritative run **артефакт був стале (8.2M ms = 2.28 год)** і жодного запису не відновлено. Це коректна поведінка (fail-closed on stale), але означає що **фактичний authoritative restore ще не застосовувався** в умовах свіжого артефакту.

**Невідомо:** Чи тестувалась повна E2E послідовність (write → restart → authoritative_read з non-stale artifact → apply → observe lifecycle state)?

#### 5B.5 ❌ 0% — НЕ РОЗПОЧАТО

**Факти:**
- `execution_truth_warm_state_v1.json` — файл все ще визначений у `config/aurora/domains.yaml:500`, `enabled: true`
- `apps/reference/domains/execution_position/truth_hardening.py` все ще використовує `"state_type": "execution_truth_warm_state_v1"` (рядок 399), `"logs/execution_truth_warm_state_v1.json"` (рядок 772) як restore path
- Жодного deprecation marker, `#non-authoritative`, або знаку переходу на cache-only
- `DeprecationRegistry` (vfoundation/core/deprecation.py) — EXISTS але жоден entry не зареєстрований для warm_state
- warm_state залишається **lifecycle-authority concern** в поточному коді

**Висновок:** 5B.5 є справжнім наступним пакетом, а не 5B.3 як у SSOT.

---

### Phase 6 — Foundation-to-Runtime Closure ❌ 0%

**Критичний факт:**
- `FSMv2` та `MetaFSMv2` присутні лише в:
  - `vfoundation/core/fsm_v2.py` (423 рядки) — бібліотека
  - `vfoundation/core/meta_fsm_v2.py` (265 рядків) — бібліотека
  - `tests/vfoundation/core/` — тести бібліотеки
  - `tests/test_coverage_final_push.py` — coverage test
- **НУЛЬ** imports FSMv2/MetaFSMv2 в `apps/reference/` runtime

**Runtime використовує:**
- `FSMCore` (old event bus) — `from vfoundation.core import FSMCore` (main.py:88, retry_scheduler.py:8)
- Custom per-domain flow FSMs (`OpenFlowFSM`, `ManageFlowFSM`, `CloseFlowFSM`) — НЕ powered by FSMv2
- `vfoundation.dr.wal` — WAL operational
- `vfoundation.core.protocol.Message` — operational
- `vfoundation.core.schema_registry` — operational

**Висновок:** FSMv2/MetaFSMv2 є **library-only artifact**, не governance-first runtime surface. Phase 6 не розпочато.

---

### Phases 7–12 ❌ 0%

Жодного коду, артефактів, або конфігурації що відповідає cutover, shadow migration, formal transition models, або replay/DR consolidation в Phase 11/12 capacity.

---

## 4. Технічний Борг

### Підтверджені та задокументовані борги

| Файл | Рядок | Борг | Рівень ризику |
|------|-------|------|---------------|
| `apps/reference/config_models.py` | 306 | `failsafe_qty_check` parsed but NOT wired to runtime | СЕРЕДНІЙ |
| `apps/reference/domains/execution_position/event_handlers.py` | 570 | `res_id` cleanup pending | НИЗЬКИЙ |
| `apps/reference/main.py` | 506 | Global deferral mechanism not implemented | СЕРЕДНІЙ |
| `apps/reference/domains/neocortex/logic/amygdala/valuation.py` | 50 | Value Network forward pass not implemented | НИЗЬКИЙ (future) |
| `apps/reference/domains/execution_position/fsm_manage.py` | 1687 | SL breakeven after TP1 optional feature | НИЗЬКИЙ |

### Структурний технічний борг

| Елемент | Розмір | Ризик |
|---------|--------|-------|
| `execution_position/fsm.py` | 4530 рядків / 198kB | **ВИСОКИЙ** — монолітний FSM, maintenance risk підтверджено SSOT |
| `execution_position/fsm_manage.py` | 86kB/2000+ рядків | **СЕРЕДНІЙ** — великий manage flow |
| `vfoundation/dr/replay.py` | 116 рядків | **СЕРЕДНІЙ** — базова реалізація, бракує real-trace replay |
| `DeprecationRegistry` | 0 реєстрацій | **СЕРЕДНІЙ** — існує але порожній; warm_state не позначено |

### Накопичення боргу (INFERENCE)
WAL файли: ~25MB/день × 6 днів = ~150MB за тиждень без gc крім `wal_gc.py`. Потрібно перевірити `wal_gc` retention policy для Phase 11 readiness.

---

## 5. Дублювання та Drift

### Знайдені дублювання

**1. Phase numbering drift у тест-файлах (ВАЖЛИВО)**
Кодова база містить файли з фазовими номерами що **не відповідають** поточній SSOT roadmap:
```
tests/test_phase3_psi_vector.py     → стара схема нумерації
tests/test_phase4_integration.py    → стара схема нумерації
tests/test_phase5_regression.py     → стара схема нумерації
tests/test_phase7_performance.py    → стара схема нумерації
tests/test_phase9_tuning.py         → стара схема нумерації
tests/test_phase10_documentation.py → стара схема нумерації
tests/test_phase14_2_fsm_split.py   → стара схема нумерації
```
Ці файли використовують OLD алфа-нумерацію (Phase 3 = PSI vector, а не Pre-Stabilization). Це НЕ є SSOT-roadmap фазами. Ризик confusion при комунікації.

**2. Retry Scheduler wrapper**
- `vfoundation/core/retry_scheduler.py` (17kB) — primary
- `apps/reference/retry_scheduler.py` (1,367 байт) — wrapper
- Потенційний drift якщо базова бібліотека змінюється

**3. Message compat layer**
- `vfoundation/core/fsm_emit_compat.py` (3,618 байт) — compat for old emit pattern
- `vfoundation/core/message_compat.py` (3,544 байт) — message compat
- Два шари сумісності — ризик drift між ними

**4. DR loader дублювання**
- `apps/reference/dr_loader.py` (1,015 байт) wraps `vfoundation/dr/dr_loader.py` (7,172 байт)
- Аналогічно retry_scheduler — wrapper pattern

### Відсутнє дублювання (хороший знак)
- `restore_artifact.py` чітко відокремлений між domain та library
- Pydantic моделі не дублюються між YAML та runtime
- WAL реалізація — єдина

---

## 6. Покриття доменів

### Активно охоплені домени ✅

| Домен | Стан | Покриття тестами | Примітки |
|-------|------|-----------------|---------|
| `execution_position` | Production | 87+ тест-файлів | Найглибше покриття |
| `shadow_telemetry` | Production | ✅ | 61 день даних |
| `position_tracking` | Production | ✅ | WAL operational |
| `risk_management` | Production | ✅ | |
| `market_data` | Production | ✅ | |
| `regime_detector` | Production | ✅ | |
| `feature_engineering` | Production | ✅ | Pillars, multi-TF |
| `decision_making` | Production | ✅ | |
| `vfoundation.dr` (WAL) | Production | ✅ | Hash chain, CAS |
| `vfoundation.core` (FSMv2) | Library only | ✅ | NOT in runtime |
| `objective_engine` | Production | Partial | |

### Домени з пробілами ⚠️

| Домен | Проблема |
|-------|---------|
| `MetaFSMv2` runtime wiring | 0% runtime, library only |
| `vfoundation.dr.replay` | Basic, no real-trace replay proof |
| DR smoke / recovery | No evidence of DR testing artifacts |
| `neocortex` | Valuation forward pass TODO |

---

## 7. Чи рухаєтеся ви по карті реалізації?

### Відповідь: Так, але карта застаріла

**Позитивне:**
- Фізичний прогрес **випереджає** SSOT — реалізовано більше ніж заявлено
- Discipline (no big-bang, additive-only, contract-first) дотримується
- Artifact-first approach (startup truth JSONL, restore envelope) — правильний
- Shadow layer active, WAL operational, contract schemas validated

**Проблемне:**
- SSOT **не оновлено** після завершення 5B.3 та 5B.4 — це порушення власного правила:  
  *"This file may be updated only when one of the following is proven with evidence: phase status changes, exit gate is passed"*  
- В результаті: команда/агент читає SSOT і думає що 5B.3 ще попереду, але реально вже 5B.5
- **Поточна фактична позиція:** Phase 5B.5 — це наступний точний пакет

---

## 8. Аналіз Exit Gates

### Phase 5 повна — перевірка exit gate

```
✅ restart can restore working execution state → ЧАСТКОВА (authoritative reader існує, але E2E з
   fresh artifact не підтверджено через stale artifact під час останнього run)
✅ execution lifecycle snapshot separate from portfolio snapshot → підтверджено (restore_envelope
   окремий від position_tracking WAL)
⚠️ operator can explain what was restored/reconstructed/unknown → startup_truth artifact дає це,
   але warm_state deprecation boundary ще не зроблено → Phase 5 exit gate НЕ READY поки 5B.5 не done
```

**Fail condition для Phase 5:**
> "restore keeps pretending to be replay" — warm_state ще має lifecycle-authority implication (truth_hardening.py:772,825,844) → **fail condition активний**

---

## 9. Пріоритизовані рекомендації

### 🚨 Критично (зроби зараз)

1. **ОНОВИТИ SSOT**: Змінити статус 5B.3 → DONE, 5B.4 → DONE, 5B.5 → NEXT EXACT PACKAGE. Це пряме порушення governance rule: "phase status changes must be reflected".

2. **Верифікувати E2E authoritative restore**: Запустити з fresh artifact (artifact_age < 300000ms) та перевірити що `applied_record_count > 0` і lifecycle state коректно відновлюється. Поточний runtime evidence показує лише stale auth-read.

### ⚠️ Важливо (наступний пакет)

3. **Phase 5B.5 — Warm-State Deprecation Boundary**:
   - Позначити `execution_truth_warm_state_v1.json` як `cache-only` в config та коментарях
   - Зареєструвати в `DeprecationRegistry`
   - Видалити або перемаркувати restore paths у `truth_hardening.py:772,825,844`
   - Це є справжнім блоком для Phase 5 exit gate

4. **Phase 5 Closure Audit**: Після 5B.5 — провести closure audit: чи можна пояснити exact/reconstructed/unknown для кожного restart?

### 📋 Технічний борг (планово)

5. **Тест-файли з старою нумерацією**: Перейменувати або задокументувати зв'язок між test_phase3..phase14 та поточними SSOT фазами щоб уникнути confusion.

6. **failsafe_qty_check**: Підключити до runtime або явно видалити з конфіга з документацією.

7. **WAL GC retention policy**: Переконатись що `wal_gc.py` правильно обробляє retention для Phase 11 readiness.

---

## 10. Числова оцінка

| Вимір | Оцінка | Обґрунтування |
|-------|--------|---------------|
| **Загальна реалізація плану** | **~72%** | Phases 0–5B.4 done; 5B.5, 6–12 не розпочаті |
| **Якість реалізації** | **8/10** | Контракти clean, Pydantic, atomic writes, fail-closed |
| **Відповідність SSOT** | **6/10** | Реалізація випереджає SSOT; SSOT не оновлено |
| **Технічний борг** | **Помірний** | fsm.py монолітний, warm_state не deprecated |
| **Дублювання** | **Низьке** | Wrapper patterns є, але контрольовані |
| **Domain coverage** | **9/10** | Всі активні домени охоплені; MetaFSMv2 не в runtime |
| **Напрямок руху** | **Правильний** | additive-only, contract-first дотримується |

---

## 11. Висновок

**Ви рухаєтесь правильно.** Дисципліна governance (no big-bang, contract-first, fail-closed) чітко дотримується в коді. Фактичний прогрес **кращий** ніж фіксує SSOT.

**Головна проблема:** Не технічна — адміністративна. SSOT document відстає від реального стану коду на 2 повних (суб)фази. Це ризик для координації та для наступного агентного пакету, який прочитає "NEXT EXACT PACKAGE: 5B.3" та почне реалізовувати те, що вже зроблено.

**Справжня наступна позиція:** Phase 5B.5 (Warm-State Deprecation Boundary) → Phase 5 Closure Audit → Phase 6 (Foundation-to-Runtime Closure).

Phase 6 залишається суттєво незачепленою і є найбільшим архітектурним викликом: FSMv2/MetaFSMv2 повинні вийти з library-only режиму та стати governance layer для реального runtime hot-path.

---

*Звіт підготовлено відповідно до AGENT_REPORT_SCHEMA. Факти відокремлені від інференцій. Невідомі зони позначені явно.*
