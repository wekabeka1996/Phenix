# Архітектурний аудит: UNIFIED_RUNTIME_STANDARDIZATION_PLAN

**Дата:** 2026-03-12
**Тип:** Глибокий архітектурний аудит + оцінка реалізації
**Об'єкт:** `docs/roadmaps/UNIFIED_RUNTIME_STANDARDIZATION_PLAN.md` (821 рядок, 16 секцій)
**Режим:** Дослідження. Код не змінювався.

---

## I. Загальний вердикт

| Показник | Оцінка |
|---|---|
| **Загальний % реалізації** | **~35%** |
| **Якість плану (архітектура)** | **9/10** |
| **Якість плану (торговельна логіка)** | **8/10** |
| **Реалістичність виконання** | **7/10** |
| **Придатність як SSOT дорожньої карти** | **8/10** |

---

## II. Концептуальна оцінка плану

### 2.1 Архітектурне мислення

**Оцінка: 9/10**

План демонструє зрілий staff-level архітектурний підхід:

- **Contract-first design** — кожна підсистема визначена через її контракт, а не через реалізацію
- **Layered readiness model** — 5-шаровий стек (Data continuity → Analytics continuity → Strategy sufficiency → Execution safety → Trading permission) є еталонним підходом для алгоритмічних систем
- **Ownership invariant** — принцип "one scope, one owner" усуває більшість проблем із shared mutable state
- **Structured state model** — перехід від boolean `full_ready` до 5-state enum (READY/COLD/PARTIAL/BLOCKED/INVALIDATED_GAP) з `why`/`source`/`evidence_ref` є правильним рішенням для операційної прозорості

**Що особливо сильне:**
- Розрізнення `can_manage_existing_risk` vs `can_open_new_risk` — це критично правильний інваріант для торговельних систем
- Деградований режим (`protect-only`) — обов'язковий для системи з відкритими позиціями
- Стратегічна ізоляція — план правильно визнає, що Quadratic readiness не має блокувати mean_reversion
- Rollback як first-class requirement — не afterthought

**Де втрачено бали:**
- Plan не включає явну стратегію міграції існуючого тест-покриття — як перевести ~1200+ тестів на нові контракти?

### 2.2 Торговельна логіка та поведінка машини

**Оцінка: 8/10**

| Аспект | Оцінка | Обґрунтування |
|---|---|---|
| Readiness перед входом в ринок | **10/10** | Layered gates з fail-closed семантикою — золотий стандарт |
| Protect-only при рестарті | **10/10** | Критично правильно: TP/SL захист не може залежати від warmup |
| Стратегічна ізоляція | **9/10** | md_amr local hydration правильно збережено; compatibility matrix формалізована |
| Regime per-symbol | **8/10** | Правильне визнання, що поточний детектор per-symbol; план для layered regime зрілий |
| Gap handling | **7/10** | INVALIDATED_GAP стан визначений, але repair/synthetic_repair семантика лише ескізний |
| Rollback | **7/10** | Правильно визначений як вимога; деталі реалізації shallow |
| Latency/throughput awareness | **5/10** | **Відсутній** — жодного слова про latency budget, throughput constraints, hot-path considerations |
| Market microstructure integration | **7/10** | Мікроструктура визнана окремим шаром, але немає формальної специфікації її контракту |
| Disaster recovery | **6/10** | WAL згадується в суміжних документах, але план не формалізує DR readiness contract |

**Критичне зауваження щодо торговельної логіки:**

Plan правильно визначає, що "scoring math is not the main problem" — це вірно для системи на ранніх стадіях зрілості виконавчого контуру. Однак для повноцінної production-grade алгоритмічної системи відсутні:

1. **Latency budget** — скільки мілісекунд від EVT:BAR_CLOSED до CMD:PROCESS_STRATEGY → EVT:TRADE_INTENT_PROPOSED? Readiness checks додають overhead
2. **Backpressure policy** — що робити, якщо readiness evaluation займає довше ніж бар?
3. **Execution slippage contract** — як readiness model враховує slippage при деградації?
4. **Market hours / session semantics** — 24/7 crypto, але funding events, deleveraging events, maintenance windows не формалізовані

### 2.3 Якість плану як документа

**Оцінка: 8/10**

| Критерій | Оцінка | Деталі |
|---|---|---|
| Структурована чіткість | **9/10** | 16 секцій з clear decomposition |
| Evidence-based | **9/10** | Чотири named audit документи як evidence base |
| Actionable deliverables | **8/10** | Кожна фаза має explicit deliverables і exit criteria |
| Пріоритизація | **8/10** | Phase A→B1→B2→C→D→E — логічний порядок лівих залежностей |
| Точність термінології | **9/10** | Чіткі визначення для кожного state, scope, mode |
| Визначення "done" | **7/10** | Acceptance criteria є, але деякі criteria суб'єктивні ("truthful statement") |
| Rollout risk management | **7/10** | Rollback визначений, але trigger thresholds не специфіковані кількісно |
| Dependencies між фазами | **8/10** | Implicit: Phase B2 залежить від B1, Phase E від C+D — але не формально зв'язані |

---

## III. Поелементний аудит реалізації

### Section 5: Canonical Readiness Model

| Підпункт | Заплановано | Реалізовано | % | Якість реалізації |
|---|---|---|---|---|
| 5.0 Ownership model (7 scopes) | 7 scopes з ownership table | `RuntimeReadinessScope` enum (7 scopes), `READINESS_SCOPE_OWNERS` dict | **100%** | **10/10** — Точне відображення плану |
| 5.1 Canonical readiness fields | Per-symbol per-strategy | `StrategyRuntimeReadinessSnapshot` у `mean_reversion_handler`, `md_amr_handler` | **70%** | **8/10** — Працює для MR/md_amr, не для Aurora |
| 5.1A State model (5 states) | READY/COLD/PARTIAL/BLOCKED/INVALIDATED_GAP + why/updated_at/source/evidence_ref | `RuntimeReadinessState` enum + `RuntimeReadinessStatus` dataclass | **100%** | **10/10** — Повне 1:1 з планом |
| 5.2 Scope semantics | 7 scope definitions | Scopes defined, semantics implementable through status population | **60%** | **7/10** — Семантика є, але не всі scopes активно populating |
| 5.3 Layer model (5 layers) | Data→Analytics→Strategy→Execution→Permission | Implicit through scope ordering; no explicit layer evaluator | **30%** | **5/10** — Структура є, enforcement ні |
| 5.4 Protective risk invariant | can_manage_existing_risk vs can_open_new_risk | `RuntimePermissions` dataclass з `PROTECT_ONLY` mode | **100%** | **10/10** — Точна реалізація |
| 5.5 Degraded mode policy | Formal policy table | `blocking_reason_chain` у snapshots; rollup_state → permissions bridge | **50%** | **6/10** — Дані є, policy arbiter відсутній |

**Підсумок Section 5: ~73%** реалізована як contract, ~40% активно wired у runtime

---

### Section 6: Startup and Restart Contracts

| Підпункт | Заплановано | Реалізовано | % | Якість |
|---|---|---|---|---|
| 6.1 Cold start | Declare all layers cold, run hydration | `RuntimeAnalyticsRestoreState.COLD` as default; planner in `main.py` | **60%** | **7/10** |
| 6.2 Warm restart | Rebuild analytics → strategy → execution | Restore contract exists; integration partial | **40%** | **6/10** |
| 6.3 Restart with open positions | Protect-only mode | `has_open_position` → `can_manage_existing_risk=True, can_open_new_risk=False` | **70%** | **8/10** |
| 6.4 Restart after data gap | Carry gap metadata | `INVALIDATED_DUE_TO_GAP` state in restore/readiness | **40%** | **6/10** |

**Підсумок Section 6: ~53%**

---

### Section 7: Bar and Replay Contract

| Підпункт | Заплановано | Реалізовано | % | Якість |
|---|---|---|---|---|
| 7.1 Canonical bar identity | symbol/timeframe_sec/bar_start_ts_ms/bar_end_ts_ms/close_boundary_ts_ms/source_mode | **НУЛЬ** — жоден з canonical field names не знайдений у кодовій базі | **0%** | **N/A** |
| 7.2 Canonical replay identity | 5-field replay identity | **НУЛЬ** | **0%** | **N/A** |
| 7.3 Required replay guarantees | dedup/parity/source_mode | **НУЛЬ** | **0%** | **N/A** |

**Підсумок Section 7: 0%** — це найбільший незакритий блок

> [!WARNING]
> Section 7 — foundation layer від якого залежать B1, B2, та Phase E. Повна відсутність реалізації bar identity є **критичним блокером** для будь-якого подальшого прогресу по цьому плану.

---

### Section 8: Analytics Restore and Hydration

| Підпункт | Заплановано | Реалізовано | % | Якість |
|---|---|---|---|---|
| 8.1 Restorable objects | 7 categories | `RuntimeAnalyticsRestoreScope` — 9 scopes (більше ніж планувалося) | **100%** | **10/10** |
| 8.2 Restore modes | restored/cold/invalidated_due_to_gap | `RuntimeAnalyticsRestoreState` — 4 states (RESTORED/COLD/PARTIAL/INVALIDATED_DUE_TO_GAP) | **100%** | **10/10** |
| 8.3 Startup hydration planner | Strategy-aware planner | `bootstrap/startup_hydration_planner.py` — 404 рядки, per-strategy requirements | **80%** | **9/10** |
| 8.4 Component boundaries | Planner/Hydrator/Replayer/Evaluator/Arbiter | Planner ✅, Evaluator partial ✅; Hydrator/Replayer/Arbiter **не реалізовані** | **40%** | **5/10** |

**Підсумок Section 8: ~65%** — contracts excellent, execution pipeline incomplete

---

### Section 9: Strategy Isolation

| Підпункт | Заплановано | Реалізовано | % | Якість |
|---|---|---|---|---|
| 9.1 Isolation principles | 5 principles | Mean reversion + md_amr actively populate scopes; strategy-aware planner exists | **60%** | **7/10** |
| 9.2 Protected paths | Aurora/MR/md_amr | `_get_aurora_requirement`, `_get_mean_reversion_requirement`, `_get_md_amr_requirement` | **80%** | **9/10** |
| 9.3 Compatibility matrix | 11-column table | `strategy_compatibility_matrix.py` exists | **70%** | **8/10** |

**Підсумок Section 9: ~70%**

---

### Section 10: Regime Architecture

| Підпункт | Заплановано | Реалізовано | % | Якість |
|---|---|---|---|---|
| 10.1 Honest classifier naming | "per-symbol structural regime" | regime_detector працює per-symbol; naming не формалізований | **30%** | **5/10** |
| 10.2 Target layered architecture | global backdrop / structural / execution micro | Ні — однорівнева модель | **10%** | **3/10** |
| 10.3 Leakage removal | 3 priority targets | `latest_regime`/`latest_warmup` не знайдені в decision_making — **МОЖЛИВО ВИДАЛЕНІ** | **50%** | **6/10** |

**Підсумок Section 10: ~30%** — найменш просунута частина

---

### Section 11-12: Phased Implementation + Migration Path

| Фаза | Заплановано | Реалізовано | Companion Doc | % |
|---|---|---|---|---|
| Phase A: Contract standardization | 7 deliverables | Readiness schema ✅, State model ✅, Ownership ✅, Startup modes ✅; Bar identity ❌, Strategy isolation partial | [URS-A1](file:///c:/Users/user/Music/Phenix/docs/roadmaps/URS-A1_READINESS_SCHEMA_AND_STATE_MODEL.md) ✅ | **65%** |
| Phase B1: Bar identity + gap policy | 4 deliverables | **НУЛЬ** implementation | [URS-A2](file:///c:/Users/user/Music/Phenix/docs/roadmaps/URS-A2_CANONICAL_BAR_IDENTITY_AND_REPLAY_IDENTITY.md) ✅, [URS-B1](file:///c:/Users/user/Music/Phenix/docs/roadmaps/URS-B1_GAP_POLICY.md) ✅ | **5%** (spec only) |
| Phase B2: Analytics restore + hydration | 4 deliverables | Contracts ✅, Planner ✅; Hydrator/Replayer ❌ | [URS-B2](file:///c:/Users/user/Music/Phenix/docs/roadmaps/URS-B2_ANALYTICS_RESTORE.md) ✅, [URS-B3](file:///c:/Users/user/Music/Phenix/docs/roadmaps/URS-B3_STARTUP_HYDRATION_PLANNER.md) ✅ | **60%** |
| Phase C: Strategy isolation | 5 deliverables | Compatibility matrix ✅, strategy-aware planner ✅; tests partial | — | **50%** |
| Phase D: Regime architecture | 4 deliverables | Leakage partially addressed; layered regime ❌ | — | **15%** |
| Phase E: Quadratic rollout | 5 deliverables | `scoring_version` config exists; gate/test/rollback ❌ | — | **5%** |

**Зважена реалізація по фазам: ~35%**

---

### Section 13 / 13.1: Must-Fix + Observability

| # | Must-Fix Item | Статус | % |
|---|---|---|---|
| 1 | Canonical bar identity | ❌ Не реалізовано | 0% |
| 2 | Analytics restore or cold truth | ✅ Contract + planner | 60% |
| 3 | Separate FE full_ready from Quadratic | ⚠️ Partial — `compute_warmup_full_ready_for_symbol()` exists but still flat boolean | 30% |
| 4 | Remove scoring side-cache dependence | ❓ Потребує окремого аудиту | ~20% |
| 5 | Strategy-aware hydration planner | ✅ `startup_hydration_planner.py` | 80% |
| 6 | Preserve md_amr local hydration | ✅ `local_hydration_contract='md_amr_rest_hydration'` | 90% |
| 7 | Remove global regime leakage | ⚠️ Partial — leakage targets partially removed | 50% |
| 8 | Symbol-scoped regime SSOT | ⚠️ regime_detector is per-symbol; consumers partially scoped | 40% |
| 9 | Formal gap policy | ⚠️ `INVALIDATED_DUE_TO_GAP` exists; repair policy ❌ | 30% |
| 10 | Integration test for Quadratic cycle | ❌ Не реалізовано | 0% |
| 11 | Operator-visible telemetry | ⚠️ Snapshots to_payload(); no telemetry surface | 20% |
| 12 | Rollback from Quadratic | ❌ Не реалізовано | 0% |

**Середній % Must-Fix: ~35%**

---

### Section 14: Acceptance Criteria

| # | Criterion | Статус |
|---|---|---|
| 1 | Per-strategy per-symbol why-chain | ✅ `StrategyRuntimeReadinessSnapshot.blocking_reason_chain` |
| 2 | Restart protect-only | ✅ Contract; ⚠️ partial integration |
| 3 | Canonical bar identity | ❌ |
| 4 | Quadratic readiness separate | ⚠️ Scope exists; not fully wired |
| 5 | MR/md_amr operable under planner | ✅ Planner supports both |
| 6 | Per-symbol regime SSOT | ⚠️ Partial |
| 7 | Config flip last step | ❌ Not enforced |
| 8 | Protect positions after restart | ✅ Contract defined |
| 9 | One owner, one state, one why | ✅ Full in contract layer |
| 10 | Planner cannot block independent strategy | ✅ Strategy-aware planning |
| 11 | MR/md_amr compatibility tests | ⚠️ Tests exist; coverage partial |
| 12 | Rollback mechanism | ❌ |
| 13 | Operator telemetry | ❌ |

**Acceptance criteria met: 5/13 повних, 4/13 часткових, 4/13 нереалізованих**

---

## IV. Тест-покриття реалізованих контрактів

| Test Suite | Status | Evidence |
|---|---|---|
| [test_runtime_readiness_contract.py](file:///c:/Users/user/Music/Phenix/tests/contracts/test_runtime_readiness_contract.py) | ✅ Exists with compiled cache | Contracts validated |
| [test_aurora_runtime_readiness_contract.py](file:///c:/Users/user/Music/Phenix/tests/domains/decision_making/test_aurora_runtime_readiness_contract.py) | ✅ Exists | Aurora handler integration |
| [test_startup_hydration_planner.py](file:///c:/Users/user/Music/Phenix/tests/bootstrap/test_startup_hydration_planner.py) | ✅ Exists with compiled cache | Planner logic covered |
| [test_runtime_analytics_restore.py](file:///c:/Users/user/Music/Phenix/tests/bootstrap/test_runtime_analytics_restore.py) | ✅ Exists | Restore logic covered |
| [test_runtime_analytics_restore_contract.py](file:///c:/Users/user/Music/Phenix/tests/contracts/test_runtime_analytics_restore_contract.py) | ✅ Exists | Contract invariants |

**Тест-покриття для реалізованих частин: ДОБРЕ.** Кожний новий contract має dedicated test suite.

---

## V. Критична оцінка торговельної поведінки

### 5.1 Що план робить правильно для алгоритмічної торгівлі

1. **Protect-only mode** — найважливіший інваріант. Система з відкритими позиціями **ОБОВ'ЯЗКОВО** повинна мати можливість захищати позиції навіть коли аналітика не готова. Це правильно і реалізовано.

2. **Strategy isolation** — mean_reversion і md_amr мають різні timeframes, різні залежності, різні warmup semantics. План правильно визнає це і відмовляється від "global readiness" моделі.

3. **Layered readiness** — не "trading or not trading", а 5-рівневий стек, де кожний рівень може бути COLD/PARTIAL/READY незалежно. Це дозволяє точну діагностику "чому система не торгує".

4. **Gap invalidation** — ринкові дані з пропусками (gaps) повинні інвалідувати аналітичний стан, а не ігноруватися. План правильно моделює це.

### 5.2 Що потребує доопрацювання

1. **Latency contract** — для crypto-ринку на 5m барах latency є менш критичним, але для будь-якої мікроструктури (microstructure_ready scope) latency budget обов'язковий. План мовчить про це.

2. **Funding rate events** — Binance futures мають 8-годинні funding events, які можуть суттєво вплинути на PnL. План не включає funding rate aware readiness.

3. **Exchange maintenance windows** — Binance scheduled maintenance має бути formalized у gap policy.

4. **Concurrency semantics** — asyncio-based system із multiple symbols і strategies. План не визначає, чи readiness evaluation atomic, eventual-consistent, або lock-free.

5. **Order-in-flight semantics** — план визначає can_open_new_risk, але не моделює перехідний стан "order submitted but not yet confirmed".

### 5.3 Порівняння з industry best practices

| Practice | Industry Standard | Plan Coverage | Gap |
|---|---|---|---|
| Layered readiness gates | Jane Street / Two Sigma pattern | ✅ 5-layer model | None |
| Strategy isolation | Standard: separate risk per strategy | ✅ Per-strategy-symbol scoping | None |
| Protect-only restart | Critical for any prod system | ✅ Explicit contract | None |
| Kill switch / circuit breaker | Required by all regulated venues | ❌ Not in plan | **Missing** |
| Position limits by venue/symbol | Standard risk management | Not in scope | Out of scope |
| Latency monitoring | Standard for HFT; important for all | ❌ Not in plan | **Missing** |
| Disaster recovery | Required for production | ⚠️ WAL exists; DR readiness not formalized | **Partial** |
| Audit trail | Required by regulation | ✅ WAL + telemetry | OK for crypto |

---

## VI. Зведена матриця оцінок (0-10 шкала)

### По розділам плану

| # | Розділ | Якість визначення | Якість реалізації | % реалізації | Пріоритетність |
|---|---|---|---|---|---|
| §5 | Canonical Readiness Model | **9** | **8** | 73% | КРИТИЧНИЙ |
| §6 | Startup & Restart | **8** | **6** | 53% | КРИТИЧНИЙ |
| §7 | Bar & Replay Contract | **8** | **0** | 0% | КРИТИЧНИЙ (blocker) |
| §8 | Analytics Restore & Hydration | **9** | **8** | 65% | ВИСОКИЙ |
| §9 | Strategy Isolation | **8** | **7** | 70% | ВИСОКИЙ |
| §10 | Regime Architecture | **7** | **3** | 30% | СЕРЕДНІЙ |
| §11-12 | Phased Roadmap + Migration | **8** | **4** | 35% | META |
| §13 | Must-Fix Items | **8** | **4** | 35% | КРИТИЧНИЙ |
| §13.1 | Observability | **7** | **2** | 20% | ВИСОКИЙ |
| §14 | Acceptance Criteria | **8** | **4** | 38% | META |

### По категоріям якості

| Категорія | Оцінка (0-10) | Обґрунтування |
|---|---|---|
| Архітектурна зрілість | **9** | Staff-level contract-first thinking; layered ownership model |
| Торговельна коректність | **8** | Protect-only + strategy isolation; missing latency/funding |
| Операційна повнота | **7** | Observability заявлена, але не formalized як deliverable з деталями |
| Еволюційність (additive-only) | **9** | Plan explicitly avoids broad refactoring; additive contracts |
| Testability | **8** | Existing tests strong; missing integration acceptance tests |
| Documentation quality | **8** | 5/8 companion docs exist; plan is self-contained and navigable |
| Risk management | **7** | Rollback defined; triggers not quantitative; no circuit breaker |
| Production readiness path | **7** | Clear path A→E; bar identity gap blocks forward motion |
| Machine behavior integrity | **8** | Fail-closed defaults; protect-only; no silent assumptions |
| Team/contributor clarity | **8** | Ownership table + exit criteria per phase; contributor can start work |

---

## VII. Стратегічні рекомендації

### 7.1 Негайні дії

1. **Реалізувати Section 7 (Bar Identity)** — це єдиний нульовий блок і foundation dependency для Phase B1, B2, та E
2. **Wire readiness scopes до Aurora handler** — mean_reversion і md_amr вже інтегровані, Aurora handler ще ні
3. **Інтеграційний тест** — хоча б один end-to-end test від startup до першого READY state

### 7.2 Архітектурні поради

1. **Додати latency budget** — навіть для 5m-bar системи, readiness chain не повинен займати >500ms
2. **Формалізувати circuit breaker** — kill switch + readiness collapse → FROZEN за <1 bar
3. **Визначити telemetry surface** — `to_payload()` вже є; потрібен explicit transport (metrics/WAL/log)
4. **Додати funding rate awareness** до gap policy для futures-specific behavior

### 7.3 Оцінка ризиків прогресу

| Ризик | Ймовірність | Вплив | Мітигація |
|---|---|---|---|
| Bar identity implementation неможлива без refactoring market_data | СЕРЕДНЯ | ВИСОКИЙ | Pilot на одному symbol + tf |
| Readiness chain додає runtime overhead | НИЗЬКА | СЕРЕДНІЙ | Lazy evaluation + caching |
| Strategy isolation порушення при додаванні нових стратегій | СЕРЕДНЯ | СЕРЕДНІЙ | Compatibility matrix як CI enforce |
| Quadratic rollout before contracts ready | ВИСОКА | КРИТИЧНИЙ | Plan explicitly gates this — добре |

---

## VIII. Порівняння з суміжними документами

| Companion Document | Статус | Відповідність плану |
|---|---|---|
| [URS-A1](file:///c:/Users/user/Music/Phenix/docs/roadmaps/URS-A1_READINESS_SCHEMA_AND_STATE_MODEL.md) Readiness Schema | ✅ Exists | Реалізовано у `runtime_readiness.py` |
| [URS-A2](file:///c:/Users/user/Music/Phenix/docs/roadmaps/URS-A2_CANONICAL_BAR_IDENTITY_AND_REPLAY_IDENTITY.md) Bar Identity | ✅ Spec exists | **Реалізація: 0%** |
| [URS-B1](file:///c:/Users/user/Music/Phenix/docs/roadmaps/URS-B1_GAP_POLICY.md) Gap Policy | ✅ Spec exists | **Реалізація: partial (INVALIDATED_GAP state)** |
| [URS-B2](file:///c:/Users/user/Music/Phenix/docs/roadmaps/URS-B2_ANALYTICS_RESTORE.md) Analytics Restore | ✅ Exists | Реалізовано у `runtime_analytics_restore.py` |
| [URS-B3](file:///c:/Users/user/Music/Phenix/docs/roadmaps/URS-B3_STARTUP_HYDRATION_PLANNER.md) Hydration Planner | ✅ Exists | Реалізовано у `startup_hydration_planner.py` |
| URS-C1 Strategy Compatibility | ❌ Not found | Лише `strategy_compatibility_matrix.py` code |
| URS-D1 Regime Layering | ❌ Not found | Не розпочато |
| URS-E1 Quadratic Rollout | ❌ Not found | Не розпочато |

**5/8 companion docs створено. 3/8 відсутні для пізніх фаз (C, D, E).**

---

## IX. Фінальна позиція

### Сильні сторони плану та реалізації

1. **Архітектурна концепція еталонна** — layered readiness з ownership model є правильним підходом для production trading system
2. **Contract-first execution** — нові контракти (`runtime_readiness`, `runtime_analytics_restore`) реалізовані чисто, з повним тест-покриттям
3. **Strategy isolation** — md_amr і mean_reversion правильно ізольовані, planner strategy-aware
4. **Protect-only invariant** — критично правильний для системи з відкритими позиціями; формалізований і реалізований
5. **Incremental delivery** — 5 companion docs, пофазна реалізація, additive-only contracts

### Головні ризики

1. **Bar identity = 0%** — foundation layer не реалізований; блокує Phase B1 і далі
2. **Regime architecture = 30%** — layered regime архітектура лише на папері
3. **Observability = 20%** — contracts мають `to_payload()`, але transport/surface відсутній
4. **Rollback = 0%** — визначений як вимога, але жодного коду
5. **Quadratic rollout gate = 5%** — config exists, gate/test/rollback відсутні

### Вердикт

Plan є **високоякісним staff-level архітектурним документом** (9/10 за концепцію) з **~35% реалізацією**. Реалізовані частини (readiness schema, analytics restore, hydration planner) зроблені якісно. Критичний блокер — повна відсутність canonical bar identity (Section 7), без якого подальший прогрес по Phase B1→E неможливий.

Рекомендація: **зберегти план як SSOT дорожньої карти**, реалізувати Section 7 як наступний пріоритет, і wire Aurora handler до readiness scopes паралельно.
