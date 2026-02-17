# NEOCORTEX R2 Shadow Production Plan (Reliability-First, Hybrid Integration)

## 1. Summary
- Ціль цього циклу: довести **R2 Shadow** до production-ready без trade actuation.
- Принцип: **Reliability First**; alpha-метрики залишаються важливими, але не є gate №1.
- Інтеграція: **Hybrid Path**; стабілізуємо поточний `MultiTailer` і паралельно вводимо контрактний event feed.
- Reward політика: **Structured Only** (тільки структурований realized PnL, без equity-delta в production).
- Сумісність подій: **Dual Emit** для shadow intent на перехідний період.

## 2. Baseline (фактичний стан перед роботою)
- Neocortex suite виключений з core CI (`pytest.ini:3`), а `python_paths` не включає neocortex package (`pytest.ini:2`).
- Поточний backpressure може зупинити ingestion назавжди: `while len(self.buffer) > threshold` у `apps/reference/domains/neocortex/transport/adapter.py:127`, тоді як буфер не дренується (`apps/reference/domains/neocortex/logic/memory/buffer.py:42`, `apps/reference/domains/neocortex/logic/memory/buffer.py:69`).
- Async task lifecycle неповний: `create_task(...)` є (`apps/reference/domains/neocortex/transport/adapter.py:263`, `apps/reference/domains/neocortex/transport/adapter.py:369`), але `_pending_tasks` не наповнюється (`apps/reference/domains/neocortex/transport/adapter.py:104`, `apps/reference/domains/neocortex/transport/adapter.py:463`).
- Reward в коді зараз proxy через equity delta (`apps/reference/domains/neocortex/logic/ingest/multi_tailer.py:509`, `apps/reference/domains/neocortex/logic/ingest/multi_tailer.py:513`, `apps/reference/domains/neocortex/logic/ingest/multi_tailer.py:518`), що не відповідає обраному Structured Only.
- Контракт подій розсинхронізований: код емітить `EVT:NEOCORTEX_SHADOW_INTENT` (`apps/reference/domains/neocortex/transport/adapter.py:319`), docs вимагають `..._PROPOSED` (`apps/reference/domains/neocortex/docs/EVENTS.md:95`), у `domain.yaml` shadow intent взагалі не описаний (`apps/reference/domains/neocortex/domain.yaml:29`).
- Частина конфіг-полів не керує runtime (ризик “фальшивої конфігурованості”): `queue_maxsize` (`apps/reference/domains/neocortex/config_models.py:41`), `keep_last_n_checkpoints` (`apps/reference/domains/neocortex/config_models.py:263`), `sequence_length` (`apps/reference/domains/neocortex/config_models.py:191`), `state_dim` лише частково валідований (`apps/reference/domains/neocortex/config_models.py:392`).
- `run_mode: backtest` у дефолті (`apps/reference/domains/neocortex/config/system.yaml:18`) і backtest-логіка може перепризначати order source (`apps/reference/domains/neocortex/logic/ingest/multi_tailer.py:192`, `apps/reference/domains/neocortex/logic/ingest/multi_tailer.py:209`).
- Logging без ротації: три output файли (`neocortex.log`, `neocortex_metrics.csv`, `shadow_intents.jsonl`) не мають rotation policy; Aurora `observability.yaml` не включає neocortex sink; log format неуніфікований між `main.py` і PPO library; alerts не маршрутизуються через контрактний `EVT:NEOCORTEX_ALERT`.

## 3. Target DoD (R2 Shadow Production)
- Надійність ingestion/training loop: 0 deadlock/hang на 24h soak.
- Reward completeness: 100% закритих позицій мають structured realized PnL; відсутні proxy-нагороди в production.
- Контрактна узгодженість: `domain.yaml`, `docs/EVENTS.md`, runtime emission і споживачі синхронні.
- CI прозорість: Neocortex tests у mandatory pipeline; deterministic test profile.
- Shadow stability: без side-effect на execution path; тільки shadow/output observability.
- Recovery: clean restart з відновленням offsets, normalizer state, checkpoints без втрат цілісності.

## 4. Public APIs / Interfaces / Types (зміни)
| Area | Change | Compatibility |
|---|---|---|
| Shadow event | Канонічний event: `EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED`; додаємо `schema_version`, `idempotent_key`, `why[]`, `confidence`, `source_ts` | Dual emit legacy `EVT:NEOCORTEX_SHADOW_INTENT` на 2 релізи |
| Reward source | Вхідний контракт `EVT:POSITION_CLOSED`/equivalent payload з `realized_pnl_net`, `symbol`, `trade_id`, `close_ts_ms`, `fees` | Breaking для Neocortex ingestion; coordinated cross-domain rollout |
| Episode type | `EpisodeV2` з обов’язковими `trade_id`, `symbol`, `side`, `realized_pnl_net`, `reward`, `open_ts_ms`, `close_ts_ms`, `features_vector` | Migration adapter з V1 у V2 лише в staging |
| Config schema | Явні секції `reward`, `backpressure`, `event_contract`, `ingest_mode`; прибираємо/реалізуємо “мертві” параметри | Minor+deprecation notes |
| Domain contract | Оновити `domain.yaml` exports/imports під фактичні R2 події | Required before production gate |

## 5. Implementation Plan (decision-complete)

### Phase 0. Contract Freeze & Scope Lock (2-3 дні)
1. Зафіксувати SSOT контрактів у `apps/reference/domains/neocortex/docs/EVENTS.md` і `apps/reference/domains/neocortex/domain.yaml`.
2. Зафіксувати Structured Only reward contract із `execution_position` (cross-domain ADR).
3. Зафіксувати migration matrix `legacy -> canonical` для shadow event.
4. **[GAP-1]** Верифікувати або імплементувати emission `EVT:POSITION_CLOSED` у `execution_position/fsm.py`. Зараз подія декларована як export (`domain_execution_position.yaml:41`), але runtime емітить лише лог (`fsm.py:1623`) без `emit()`. Без цього Phase 2 заблокована.
5. **[GAP-2]** Оновити `verb_registry_v1.yaml`: додати `EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED` (status: `experimental`); змінити `EVT:NEOCORTEX_SHADOW_INTENT` на `deprecated`. Registry-first інваріант (`copilot-instructions.md:32,94`).

**DoD**
- Підписаний ADR для reward/event contracts.
- Версіонований schema package і changelog.
- Є compatibility matrix для всіх downstream consumers.
- `EVT:POSITION_CLOSED` емітиться в runtime з payload `{realized_pnl_net, symbol, trade_id, close_ts_ms, fees}` або є документований альтернативний шлях.
- `verb_registry_v1.yaml` містить canonical `_PROPOSED` event і legacy позначений `deprecated`.

### Phase 1. Runtime Reliability Hardening (1 тиждень)
1. Переписати backpressure з `len(buffer)` на **inflight training queue depth / semaphore**, без залежності від загального розміру replay buffer.
2. Додати policy: коли bridge недоступний, ingestion **не блокується**, training переводиться в degraded mode з alert.
3. Всі `asyncio.create_task` реєструвати в `_pending_tasks`; завершення/скасування через task-group pattern.
4. Явно розвести `dream` і `ppo_update`: Dreamer/CausalGraph лишається optional, default off для production R2. При dream enabled, зафіксувати production `dream_episode_threshold` (>=5; поточне значення `1` у `neuro.yaml:65` створює надмірний training overhead).
5. Привести `run_mode` і path-routing до fail-closed: без неявного перепризначення order source.
6. **Logging hygiene:**
   - Увімкнути `RotatingFileHandler` для `neocortex.log` (10MB, 5 backups — аналогічно Aurora `observability.yaml` policy).
   - Додати rotation або retention cap для `neocortex_metrics.csv` і `shadow_intents.jsonl` (size-based або date-based).
   - Уніфікувати log format між `main.py` (`%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`) і PPO library (`%(asctime)s - %(name)s - [%(levelname)s] - %(message)s`) — єдиний формат через shared formatter.
   - Маршрутизувати operational alerts (bridge degraded, `WARN:NO_STRUCTURED_REWARD_RECEIVED`, backpressure sustained) через `EVT:NEOCORTEX_ALERT` контракт (`domain.yaml` exports), а не лише Python logger.

**DoD**
- 10k event stress test проходить без timeout.
- Shutdown завершує всі background tasks і завершує checkpoint/save state.
- Bridge failure не зупиняє ingestion loop.
- Backtest/live path routing детермінований і протестований.
- **[GAP-8]** Lightweight observability з Phase 1: structured logs + базові метрики (`buffer_size`, `training_latency_ms`, `backpressure_events`, `inflight_tasks`) доступні через стандартний log output або telemetry endpoint.
- Log rotation активний для всіх трьох output файлів; 24h soak test не генерує необмежене зростання файлів.
- Operational alerts емітяться як `EVT:NEOCORTEX_ALERT` з відповідним severity/code.

### Gate 1→2: Upstream Reward Readiness (Phase 2 entry gate)
**[GAP-3]** Phase 2 починається ТІЛЬКИ після підтвердження:
- `EVT:POSITION_CLOSED` стабільно емітиться з `realized_pnl_net` на staging (мінімум 50 closed positions без missing fields).
- Contract test `execution_position → neocortex` green.

**No fallback:** якщо upstream не готовий, training переходить у state `waiting_for_reward_source`, ingestion залишається активним, генерується `WARN:NO_STRUCTURED_REWARD_RECEIVED`. Phase 2 заблокована до upstream readiness confirmation.

### Phase 2. Structured Reward Integration (Cross-domain) (1-1.5 тижня)
1. Додати/закріпити structured realized PnL у `execution_position` close-event payload.
2. Оновити parser/ingest на strict structured parsing; без structured reward episode у training не допускається.
3. Додати data-quality alerts через `EVT:NEOCORTEX_ALERT`: missing reward fields, duplicate trade_id, out-of-order close events.
4. Прибрати production використання equity-delta reward у `MultiTailer`.

**DoD**
- Coverage structured reward = 100% у replay/staging.
- `reward_source=structured_only` enforced через config validation.
- У логах/метриках відсутні proxy reward pathways.

### Phase 3. Config Truthfulness & Model Path Cleanup (1 тиждень)
1. Або реалізувати, або вилучити runtime-поля: `queue_maxsize`, `keep_last_n_checkpoints`, `sequence_length`, `state_dim` semantics.
2. Зафіксувати sequence training contract для world model (input shape, batching, assertions).
3. Додати checkpoint retention logic (keep_last_n_checkpoints).
4. Усунути API drift у telemetry: episode/pnl метрики мають реально писатися.

**DoD**
- Кожне поле конфіга або використовується runtime, або видалене.
- Runtime asserts на model input/output contracts.
- Checkpoint retention перевірений integration test.

### Phase 4. Test & CI Replatforming (1 тиждень)
1. Додати `apps/reference/domains/neocortex/tests` у mandatory CI testpaths.
2. Прибрати залежність від ручного `PYTHONPATH`: package-consistent imports і test invocation.
3. Розмітити довгі сценарії: `slow`, `soak`, `e2e_long`; встановити окремі timeout policy.
4. Переписати loop-handling у flaky tests на уніфікований async test harness.

**DoD**
- Mandatory CI profile green.
- Flaky timeout rate < 1% за 20 прогонів.
- Є окремі jobs: `unit-fast`, `integration`, `soak-nightly`.
- Всі neocortex test imports працюють з поточним `python_paths` конфігом (`pytest.ini:2`), без додаткових PYTHONPATH hacks.

### Phase 5. Shadow Rollout & Operations (1 тиждень)
1. Canary shadow rollout на 1-2 символи.
2. Розширення до повного symbol set після SLO confirmation.
3. Dual emit migration: telemetry по споживачах legacy event.
4. Deprecation legacy event після completion criteria.

**DoD**
- 7 днів canary без P1/P0 інцидентів.
- Shadow pipeline працює без впливу на execution.
- Legacy consumer coverage = 0 перед вимкненням old event.

## 6. Test Plan (обов’язкові сценарії)
| Layer | Must-have tests | Acceptance |
|---|---|---|
| Unit | Backpressure state machine, structured reward parser, event schema validation, config truthfulness | 100% pass, deterministic seed |
| Integration | Adapter+Tailer+Bridge lifecycle, graceful shutdown, bridge failure degradation, dual emit consistency | Без timeout/hang |
| Contract | Producer-consumer schema tests для reward та shadow events | No schema drift |
| Performance | 10k/100k event replay latency, memory ceiling, queue saturation | В межах SLO |
| Soak | 24h shadow run на staging data stream | 0 deadlock, 0 data-loss |
| Chaos | killed worker, log rotation, delayed/out-of-order close events | Controlled degradation, auto-recovery |

## 7. Weak Spots + 3 Hypotheses (і як боротися)

### Weak Spot A: Deadlock/Timeout у runtime та тестах
- Гіпотеза A1: блокування викликає залежність backpressure від `len(buffer)` замість inflight processing.
- Гіпотеза A2: незареєстровані background tasks залишають loop у “напівживому” стані.
- Гіпотеза A3: різні test loop patterns (`get_event_loop`, ручний `new_event_loop`) породжують flaky timeouts.
- План боротьби: task-group architecture, inflight semaphore, standardized async harness, soak+chaos tests.

### Weak Spot B: Ненадійний reward signal
- Гіпотеза B1: structured realized PnL приходить не у всіх close events через upstream gaps.
- Гіпотеза B2: розбіжність між gross/net pnl (fees/slippage) спотворює reward.
- Гіпотеза B3: out-of-order lifecycle events ламатимуть episode closure.
- План боротьби: strict reward schema, upstream contract tests, trade_id correlation, missing-field hard fail у staging.

### Weak Spot C: Contract drift (code vs docs vs domain.yaml)
- Гіпотеза C1: legacy/canonical event names співіснують без чіткої deprecation політики.
- Гіпотеза C2: документація випереджає runtime або навпаки.
- Гіпотеза C3: downstream consumer’и читають неверсіоновані payload fields.
- План боротьби: schema_version everywhere, dual emit with cutoff date, contract CI gate.

### Weak Spot D: “Фальшива” конфігурованість
- Гіпотеза D1: параметри, не підключені до runtime, дають ілюзію керування.
- Гіпотеза D2: дефолти (`backtest` mode) провокують неправильний datasource у production.
- Гіпотеза D3: model-related params (`state_dim`, `sequence_length`) не відповідають фактичному train path.
- План боротьби: config-to-runtime audit, fail-closed validation, remove-or-wire policy для кожного поля.

### Weak Spot E: Test visibility gap у CI
- Гіпотеза E1: Neocortex регресії залишаються невидимими через testpaths exclusion.
- Гіпотеза E2: package import style вимагає ручних env hacks.
- Гіпотеза E3: важкі тести запускаються в неправильному профілі та фальшиво “червонять” pipeline.
- План боротьби: mandatory CI suite, package-correct imports, multi-profile test matrix (fast/integration/soak).

## 8. Rollout Gates
- Gate G1: Contract Gate — schema freeze, cross-domain reward contract signed, `EVT:POSITION_CLOSED` emission verified, verb registry updated.
- Gate G1→2: Upstream Reward Readiness — `EVT:POSITION_CLOSED` стабільний на staging, contract test green, no reward fallback policy enforced.
- Gate G2: Reliability Gate — stress+integration без deadlock/timeouts, lightweight observability operational.
- Gate G3: Observability Gate — SLO dashboards + alerts + runbooks (повна версія; базові метрики вже з G2).
- Gate G4: Canary Gate — 7 днів стабільності.
- Gate G5: Deprecation Gate — legacy shadow event fully drained.

## 9. Assumptions and Defaults Used
- Цільовий реліз: **R2 Shadow production**.
- Пріоритет: **Reliability First**.
- Інтеграція: **Hybrid Path**.
- Reward policy: **Structured Only**.
- Event migration: **Dual Emit** для shadow intent.
- Scope змін: **Cross-domain allowed** (Neocortex + upstream execution contracts).
- R3 actuation у цей цикл не входить.
- **No reward fallback:** equity-delta pathway не використовується як fallback policy для R2; відсутність structured reward блокує training, не підміняє його proxy.
- Цільовий документ для збереження: `docs/Невирішені питання/NEOCORTEX_R2_PRODUCTION_PLAN.md`.
