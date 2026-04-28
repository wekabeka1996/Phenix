# 06 — Neocortex Master Blueprint & Definition of Done (SSOT-Кресленик)

> Канонічна архітектурна специфікація домену `apps/reference/domains/neocortex/`
> та формальні бінарні умови, після виконання яких можна впевнено сказати:
> «Neocortex реалізовано на 100%».

- Статус: `ACTIVE_BLUEPRINT`
- Зв'язки:
  - реальність runtime: [01_CURRENT_STATE_GAP_ANALYSIS.md](01_CURRENT_STATE_GAP_ANALYSIS.md)
  - експлуатація: [02_DATA_COLLECTION_PROTOCOL.md](02_DATA_COLLECTION_PROTOCOL.md), [03_RUN_INSTRUCTIONS.md](03_RUN_INSTRUCTIONS.md)
  - технічний борг: [05_TECH_DEBT_ERADICATION_PLAN_V2_IDEAL.md](05_TECH_DEBT_ERADICATION_PLAN_V2_IDEAL.md) (заміняє [04_TECH_DEBT_ERADICATION_PLAN_V1.md](04_TECH_DEBT_ERADICATION_PLAN_V1.md))
  - аудит коду: [NEOCORTEX_CODE_QUALITY_AUDIT_2026-04-28.md](NEOCORTEX_CODE_QUALITY_AUDIT_2026-04-28.md)
  - попередній рефакторинг: [NEOCORTEX_FAIL_CLOSED_REFACTOR_REPORT.md](NEOCORTEX_FAIL_CLOSED_REFACTOR_REPORT.md)
  - інтеграційний контракт: [NEOCORTEX_IMPLEMENTATION_SSOT_v2.md](NEOCORTEX_IMPLEMENTATION_SSOT_v2.md)
  - дослідницький фон: [DeepMind.md](DeepMind.md) / [DeepMind_RnD_Almanac_v2.1.md](DeepMind_RnD_Almanac_v2.1.md)
- Виконавча частина: [07_NEOCORTEX_EXECUTION_ROADMAP.md](07_NEOCORTEX_EXECUTION_ROADMAP.md)

Цей документ — **WHAT і WHY**.
07-й — **HOW і WHEN**.
Якщо вони суперечать одне одному, перемагає **06** для контракту і **07** для порядку дій.

---

## 0. Принципи цього креслення

1. **Bounded authority, не AI-трейдер.** Neocortex — обмежений контролер довіри над Aurora, що ніколи не генерує власну альфу і ніколи не емітить `CMD:*` напряму.
2. **Fail-closed усюди.** Будь-яка нестача даних, контракту чи моделі — це bounded `fallback`, а не синтетичне «безпечне» рішення.
3. **Каузальний час — священний.** Тренувальні та authority-сусідні рядки приймаються тільки з причинно встановленим `event_ts_ms`. Wallclock, captured, file-offset — лише як `diagnostics-only`.
4. **Контракти > файли.** Спочатку контракт + тест, потім поділ файлу. Поділ без контракту переносить двозначність у менші коробки.
5. **Простота важливіша за елегантність.** Найкоротший шлях до перевірюваного інваріанта — переможний шлях.
6. **Бінарна повнота.** «Зроблено» ≠ «майже зроблено». DoD — це чек-листи з пройденими/не-пройденими тестами і артефактами, а не суб'єктивна оцінка.
7. **Само-оскарження обов'язкове.** Кожен рівень містить розділ «Де я можу помилятися», інакше блюпринт не має права входити в SSOT.

---

## 1. Сфера домену та межі

### 1.1 Що належить Neocortex

- Тіньовий рантайм (Stage 0.3): `main.py`, `logic/ingest/state_aggregator_v2.py`, `logic/brain/baseline_inference.py`, `logic/gates/shadow.py`, `logic/ingest/observation.py`.
- Authority seam (NEW): `NeocortexAuthorityBridge` (синхронний хук), консоль `neocortex.trust_enabled`.
- Outcome ledger: `DecisionOutcomeLedgerRow` зборка та фіналізація.
- Offline шар: реконструкція датасету за `event-time merge`, baseline estimator, OPE.
- Конфіги: `apps/reference/domains/neocortex/config/{neuro,ingest,replay,system}.yaml`, `domain.yaml`.
- Telemetry-sink і shadow-WAL.

### 1.2 Що не належить Neocortex (явні межі)

- Алфа і стратегії — `alpha_search`, `domains/strategies/*`.
- Gate chain і primary intent emission — `decision_making`.
- Маршрутизація ордерів та lifecycle — `execution_position`.
- Глобальний `panic_killswitch` — `trading.ops` / `execution_position`.
- Шинні гарантії і WAL — `vfoundation`.

Neocortex може **читати** артефакти цих доменів, але ніколи їх не модифікує під час runtime.

### 1.3 Заборонене (хард-інваріанти)

- ❌ Пряма емісія `CMD:OPEN`/`CMD:CLOSE` з Neocortex.
- ❌ Зміна напрямку, розміру, символа, стратегії запропонованого intent.
- ❌ Втручання у reduce-only, protective-close, panic, exchange-recovery, bracket-cleanup.
- ❌ Patching YAML у runtime.
- ❌ Синтетичний `FLAT`/`0.0`/`unknown` як «безпечне» рішення при збої моделі.
- ❌ Маркування wallclock/file-offset як `event_time_is_causal=true` у production-shadow або training.
- ❌ Будь-який shared state між символами (LSTM hidden, normalizer registry, ledger row).

### 1.4 Самооскарження межі

- Сумнів: чи `modulate` справді безпечний, навіть у allowlist `[signal_threshold_bias, cooldown_mult]`?
  - **Відповідь:** так, лише якщо overlay діє з наступного семантичного тіку, має жорсткі межі (`Appendix C` SSOT_v2) і TTL. Інакше overlay перетворюється на скриту YAML-мутацію.
- Сумнів: чи `trust_enabled=false` достатньо швидкий?
  - **Відповідь:** так, бо bridge синхронний і повертає `fallback` за `O(1)` без мережевого виклику; додатково мусить бути unit-тест на `< 1ms`.

---

## 2. Канонічні інваріанти (I1..I12)

Усі інваріанти — машинно-перевірюваним тестом. Жоден не може бути «soft».

| ID | Інваріант | Перевірюючий артефакт |
|----|-----------|------------------------|
| I1 | Hot path не імпортує жодного legacy/RL/PPO модуля | `tests/domains/neocortex/architecture/test_import_boundaries.py` |
| I2 | Production-shadow startup падає при відсутності будь-якого business-default у YAML | config-reflection test |
| I3 | Будь-який рядок без причинного `event_ts_ms` отримує `trainable=false` і `dataset_visibility=diagnostics_only` | parser/aggregator contract tests |
| I4 | Жоден ML-шлях не повертає синтетичний `FLAT`/zero latent/zero reward після збою | bridge timeout tests + brain.core fallback tests |
| I5 | `panic_killswitch` і `neocortex.trust_enabled` — два різні кіл-світчі, ніколи не плутаються | runtime contract test |
| I6 | Authority response, отриманий після `expires_at_ms`, ігнорується і логується як `LATE` | bridge deadline test |
| I7 | Кожен `decision_id` дає рівно один термінальний `DecisionOutcomeLedgerRow` | ledger terminalization test |
| I8 | `ModulationStoreRecord` діє тільки з наступного семантичного тіку і має TTL | overlay timing test |
| I9 | LSTM/per-symbol hidden state ніколи не шеритися між символами і обнуляється на `done=true` | causal stream isolation test |
| I10 | `reward_valid=false` поки не існує валідованого `baseline_pnl_estimate` | dataset gate test |
| I11 | Будь-який `except Exception` у hot path має типізований outcome і reason code | linter+test policy |
| I12 | Telemetry/CSV/SQLite sinks мають bounded queue з drop-counters | bounded-queue tests |

### 2.1 Що буде, якщо порушити інваріант

- I1, I3, I4, I5, I6, I9 → **критичні**: блокують live authority взагалі.
- I2, I7, I10 → **датасет-критичні**: блокують offline RL.
- I8, I11, I12 → **операційні**: блокують промоушн з `shadow` у `advisory`.

### 2.2 Самооскарження інваріантів

- Сумнів: чи I3 не надмірний для діагностичних даних?
  - Перевірка: ні, бо діагностика дозволена через `diagnostics_only`. Інваріант забороняє лише трактувати таке як training-truth.
- Сумнів: чи I10 не блокує проєкт назавжди?
  - Перевірка: ні. Він блокує лише offline RL фазу, не блокує shadow-baseline. Знімається після прийняття baseline estimator пакету (див. §4.4).

---

## 3. Контракти (повний реєстр)

Усі поля наведені у [NEOCORTEX_IMPLEMENTATION_SSOT_v2.md](NEOCORTEX_IMPLEMENTATION_SSOT_v2.md) §4. Тут — лише різниця/доповнення і умови сумісності.

### 3.1 Реєстр

| Контракт | Власник | Persistence | Сумісність |
|----------|---------|-------------|------------|
| `ObservationEnvelope` | `decision_making` | authority request journal | NEW |
| `ControlDecisionRequest` | `decision_making` | request journal | NEW |
| `ControlDecisionResponse` | `neocortex` | response journal | NEW |
| `AuthorityMode` enum | config | snapshot у журналі | NEW |
| `ModulationStoreRecord` | `decision_making` | окремий modulation journal | NEW |
| `DecisionOutcomeLedgerRow` | `neocortex` evaluation | ledger WAL | NEW |
| `CausalTimeProvenance` enum | усі парсери | у самому рядку | NEW (див. §4.3) |
| `FailureOutcomeTaxonomy` enum | усі hot-path сервіси | telemetry counters | NEW (див. §4.5) |

### 3.2 Версіонування

- Кожен контракт має `version` поле і `schema_passport_id`.
- Зміна структури — мінорна версія + міграційний тест.
- Видалення поля — мажорна версія + двохкроковий cutover (діагностичний тільки → видалення).

### 3.3 Самооскарження контрактів

- Сумнів: чи не дублюється `idempotent_key` із `decision_id`?
  - Так, для `ControlDecisionRequest` `idempotent_key = decision_id`. Це навмисно: ми хочемо явно типізовану ідемпотентність на рівні Router.route(), яка не залежить від семантики `decision_id`.
- Сумнів: чи `DecisionOutcomeLedgerRow` не стане «всім для всіх»?
  - Ризик реальний. Захист: рядок має суворі стани `EXECUTED_AND_CLOSED | VETOED | BASELINE_FALLBACK_NO_EXECUTION | BASELINE_FALLBACK_EXECUTED | REJECTED_UPSTREAM | INVALID_FOR_DATASET`. Кожен інший стан = bug.

---

## 4. Архітектурні шари

### 4.1 Шар L0 — Data Plane (read-only)

- Джерела: `alpha_input_v1.jsonl`, `aurora_core.log`, `order_log_v1.jsonl`, `shadow_telemetry/decision_ledger_v1.jsonl`, feature WAL.
- Контракт: тільки причинні рядки можуть пройти у L1+. Решта йде в `diagnostics_only` корзину.
- Власник: парсери `logic/ingest/parsers/*`.
- DoD рівня:
  - усі парсери виставляють `CausalTimeProvenance`;
  - `legacy_non_causal_file_offset` дозволено лише в `replay.diagnostics_legacy=true`;
  - 100% покриття failure-режимів парсера (malformed JSON, missing keys, alias drift).

### 4.2 Шар L1 — State Aggregation

- `NeocortexStateAggregator` (Stage 0.3) і `state_aggregator_v2.py`.
- Інваріант: `S_t` будується тільки з причинно попередніх фактів; freshness/missingness — явні поля, а не нулі.
- DoD:
  - `CONTEXT_DIM` зафіксований у passport;
  - усі alias таймстемпів покриті alias-reconciliation тестом;
  - missingness mask — окреме поле, не імпутація.

### 4.3 Шар L2 — Inference (BaselineController + майбутні моделі)

- Stage 0.3: Logistic Regression `BaselineController`.
- Майбутні: VAE, action-conditioned latent dynamics, CQL/IQL.
- Інваріант I4: жодного синтетичного `FLAT`/zero latent. Збій моделі — `RuntimeError` → `fallback` outcome.
- DoD рівня:
  - артефакт моделі має `schema_passport`, `threshold_provenance`, `feature_names`, `sentinel_policy`;
  - missing toxic class 1 → `ValueError` (вже виконано в [NEOCORTEX_FAIL_CLOSED_REFACTOR_REPORT.md](NEOCORTEX_FAIL_CLOSED_REFACTOR_REPORT.md));
  - `encode_async()`/`act_async()` піднімають `RuntimeError` замість синтетики (вже виконано).

### 4.4 Шар L3 — Authority Seam

- `NeocortexAuthorityBridge.decide(request) -> response` — синхронний хук в `decision_making.strategy_gateway` між успіхом gate chain і викликом `_propose_trade_intent()`.
- Жорсткі ворота:
  - `decision_making` володіє `deadline_ms`, fallback-рішенням і журналом.
  - `expires_at_ms = decision_basis_ts_ms + deadline_ms`.
  - `max_inflight_per_symbol = 1`.
- DoD:
  - hit-rate `< deadline_ms` ≥ 99.5% під відтворюваним навантаженням;
  - `LATE` response завжди ігнорується і логуються;
  - kill-switch drill: `trust_enabled=false` веде до `fallback` за `< 1ms` без побічних ефектів.

### 4.5 Шар L4 — Outcome Ledger

- Фіналізація `DecisionOutcomeLedgerRow` за `decision_id`.
- Шви join: `rid`, `lifecycle_id`, `trade_id`.
- Failure taxonomy (NEW enum):
  - `BLOCK` — input заборонений до подальшого ML;
  - `FALLBACK` — типізована відмова bridge → baseline;
  - `SKIP_ROW` — рядок викинуто з причиною;
  - `DEGRADED_OBSERVABILITY` — частина телеметрії втрачена, але runtime ок;
  - `FATAL_STARTUP` — startup-gate fail;
  - `LEGACY_DIAGNOSTIC_ONLY` — рядок пропущено для тренування.
- DoD:
  - кожен `decision_id` → рівно один термінальний рядок;
  - 0 рядків зі станом `OPEN` старшим за 24 години (для відтворюваного фікстура);
  - 100% покриття гілок `terminal_status`.

### 4.6 Шар L5 — Offline / Learning

- Складається з: dataset builder, baseline estimator, OPE-evaluator, Offline RL trainer (CQL/IQL).
- Заблоковано (I10) до завершення baseline estimator пакету.
- DoD:
  - `reward = (realized_pnl_net - baseline_pnl_estimate) - γ·stress - λ·opportunity_cost - μ·intervention_budget_violation` обчислюється тільки offline;
  - `reward_valid=true` тільки для рядків, що пройшли support-quality gate;
  - permutation test зводить альфу до 0 на перемішаних мітках.

### 4.7 Самооскарження архітектури

- Сумнів: чому L3 синхронний, а не bus-based?
  - Бо `FSMCore.emit()` інлайн (див. SSOT v2 §3.4). Async bus давав би «спізнілий критик», що знецінює I6.
- Сумнів: чи L4 не дублює `execution_position` lifecycle ledger?
  - Ні. `execution_position` — episode-centric (по trade), L4 — decision-centric (по `decision_id`). Це різні зрізи; шви декларовані join-ключами.
- Сумнів: чи L5 справді blocked-by-baseline?
  - Так. Без `baseline_pnl_estimate` reward — це сирий PnL, який підштовхує агента до reward-hacking. Це задокументований дегенеративний оптимум з [DeepMind.md](DeepMind.md) Крок 1.3.

---

## 5. Математичний фундамент і його прогалини

### 5.1 Reward (offline-only)

Канонічна формула:
$$
R_t = (PnL^{net}_{agent}(t) - \widehat{PnL}^{baseline}(t)) - \gamma \cdot S(t) - \lambda \cdot O(t) - \mu \cdot B(t)
$$
де:
- $PnL^{net}_{agent}$ — realized PnL за участю Neocortex (можливо з veto/modulate);
- $\widehat{PnL}^{baseline}$ — оцінка контрфактуального PnL без Neocortex (Doubly Robust OPE);
- $S(t)$ — stress-штраф (пропущені `EXECUTION_GUARD_BLOCKED`, slippage аномалії);
- $O(t)$ — opportunity cost (заблоковано прибутковий трейд);
- $B(t)$ — intervention budget violation (перевищено квоту втручань).

### 5.2 Невирішені питання (open math gaps)

| ID | Питання | Поточна позиція | Як знімається |
|----|---------|-----------------|---------------|
| M1 | Як саме оцінити $\widehat{PnL}^{baseline}$? | Doubly Robust OPE поверх gate-chain симуляції | пакет `baseline_estimator` + permutation tests |
| M2 | Як визначити `support_quality` для рядка? | propensity score behavior policy + KL до empirical | окремий `support_estimator` + bootstrap CI |
| M3 | Якими бути ваги $\gamma, \lambda, \mu$? | поки без значень; знаходяться cross-validation на витриманому фолді | `reward_weight_grid_search` |
| M4 | Як уникнути degenerate optimum «не втручатися ніколи»? | intervention budget + opportunity cost | sanity test: агент з нульовою активністю отримує R<baseline |
| M5 | Stateless-per-event vs sequence-aware? | поточно stateless; sequence потребує action-conditioned dynamics | пакет `world_model` після L3 GA |
| M6 | Як обмежити `modulate` overlay у часі? | TTL + bounded knobs | overlay-timing test (I8) |
| M7 | Як виміряти Sim2Real gap? | shadow → advisory drill з KL до behavior policy | rollout-promotion gate |

### 5.3 Самооскарження математики

- Сумнів: чи DR-OPE достатньо для нашого розрідженого `agency`?
  - Часткове «так»: DR — стандарт, але з ~96 втручань/добу варіанс буде високим. Захист: широкі CI + блок offline RL до досягнення мінімальної кількості рядків (≥ 5 000 з причинним часом і resolved lifecycle, як у [02_DATA_COLLECTION_PROTOCOL.md](02_DATA_COLLECTION_PROTOCOL.md) §4).
- Сумнів: чи можна спростити reward до $PnL_{agent} - PnL_{baseline}$?
  - Можна. Але без $S, O, B$ агент швидко вивчить «всеблок» або «жодного блоку». Стартова конфігурація: $\gamma = \lambda = 1.0$, $\mu = 10.0$ (intervention quota — м'який пріор, який ми готові послабити).

---

## 6. Конфіг-контракт (SSOT defaults)

### 6.1 Класифікація defaults (вимога I2)

Кожне поле в `config_models.py` має один з трьох тегів у docstring/Field metadata:

- `structural_safe` — порожній контейнер, опціональна підсистема, шлях.
- `runtime_behavior` — будь-який поріг, режим, seed, timeout, формула, dimension. **Заборонений** як implicit default; лише через YAML.
- `legacy_compat` — тільки для старих WAL/тестів; завжди потребує явного режиму legacy.

### 6.2 Нові обов'язкові ключі (з SSOT_v2 Appendix C)

- `neocortex.trust_enabled` (bool, default=`false`)
- `neocortex.authority.mode` (`shadow|advisory|gated`, default=`shadow`)
- `neocortex.authority.deadline_ms` (int, default=`10`)
- `neocortex.authority.fallback_policy` (default=`baseline_yaml`)
- `neocortex.authority.max_inflight_per_symbol` (int, default=`1`)
- `neocortex.authority.modulation_allowlist` (list, default=`["decision_making.signal_threshold_bias","decision_making.cooldown_mult"]`)
- `neocortex.authority.signal_threshold_bias_bounds` (default=`[-0.10, 0.10]`)
- `neocortex.authority.cooldown_mult_bounds` (default=`[1.0, 3.0]`)

### 6.3 Self-test

- Reflection-test іде по всіх Pydantic field defaults; падає, якщо новий `runtime_behavior` field має implicit default.
- Production-shadow startup-gate перевіряє наявність ключів §6.2, інакше `FATAL_STARTUP`.

---

## 7. Спостережуваність як перший клас

### 7.1 Лічильники, які мусять існувати

- `neocortex.authority.requests_total{mode,symbol,apply_result}`
- `neocortex.authority.deadline_misses_total`
- `neocortex.authority.late_responses_total`
- `neocortex.authority.kill_switch_active{1|0}`
- `neocortex.dataset.rows_total{causal,resolved,trainable}`
- `neocortex.dataset.invalid_total{reason_code}`
- `neocortex.bridge.queue_depth`, `..._drops_total`
- `neocortex.telemetry.bounded_queue_drops_total{sink}`

### 7.2 Tracе

- `decision_id` — корелятор скрізь (request/response/ledger/journal/telemetry).
- `rid`, `lifecycle_id`, `trade_id` — допоміжні шви.

### 7.3 Алерти

- `late_responses_total > 0` за 5 хвилин у `gated` → автоматичний downgrade у `advisory`.
- `kill_switch_active=1` довше 60s без ручного підтвердження → ескалація.
- `dataset.invalid_total{reason_code=NON_CAUSAL_TIME}` росте → блок dataset cutover.

---

## 8. Definition of Done — повний бінарний чекліст

### 8.1 Layer DoD

- **L0** ✅ коли:
  - усі парсери ставлять `CausalTimeProvenance`;
  - production-shadow конфіг падає при `feature_missing_timestamp_policy=legacy_non_causal_file_offset`;
  - 100% гілкове покриття failure-режимів парсера.
- **L1** ✅ коли:
  - state-vector passport існує, alias-reconciliation покритий;
  - `ObservationEnvelope` будується тільки з причинного стану.
- **L2** ✅ коли:
  - артефакт baseline моделі має повний `schema_passport`;
  - усі ML-fail шляхи піднімають типізовані помилки (вже частково виконано згідно [NEOCORTEX_FAIL_CLOSED_REFACTOR_REPORT.md](NEOCORTEX_FAIL_CLOSED_REFACTOR_REPORT.md)).
- **L3** ✅ коли:
  - bridge синхронний, deadline-driven, kill-switch перевірений drill-ом;
  - 99.5%+ deadline hit-rate під load-fixture.
- **L4** ✅ коли:
  - кожен `decision_id` дає рівно один термінальний рядок;
  - 0 «open»-рядків старших за 24 год у фікстур-замірі.
- **L5** ✅ коли:
  - baseline estimator існує, OPE рахує DR з CI;
  - permutation test → α≈0;
  - `reward_valid=true` тільки на рядках з resolved lifecycle і pass support gate.

### 8.2 Cross-cutting DoD

- C1 — Type & Static: `mypy apps/reference/domains/neocortex/` (у venv з установленим mypy) → 0 помилок на hot-path модулях.
- C2 — Coverage: branch coverage ≥ 100% на declared hot-path; legacy виключений з метрики.
- C3 — Tests: `pytest tests/domains/neocortex -q` → 100% pass; включно з: `test_import_boundaries`, `test_shadow_gates`, `test_bridge_timeouts`, `test_baseline_inference`, `test_decision_ledger_terminalization`, `test_modulation_overlay_timing`, `test_alias_reconciliation`.
- C4 — Config: reflection test → 0 неклассифікованих defaults; real-config startup → ok.
- C5 — Telemetry: усі лічильники §7.1 емітуються; bounded queues тестовані.
- C6 — Adapter quarantine: `transport/adapter.py`, `multi_tailer.py`, `brain/core.py`, `brain/bridge.py`, `dreamer.py`, PPO — або quarantined facade, або видалені, або `offline_only`. Hot path їх не імпортує.
- C7 — Документація: 06 (цей) + 07 (roadmap) live; SSOT_v2 не має розбіжностей з кодом (контракт-тест порівнює).

### 8.3 Глобальний 100%-критерій

Усі L-DoD зелені **AND** усі C-DoD зелені **AND** rollout у `gated` тримається ≥ 14 днів без алертів §7.3 **AND** баседж offline RL виконав один повний цикл навчання на real WAL з `reward_valid=true` рядках і пройшов permutation test.

> Якщо хоч один пункт не зелений, проєкт не «на 100%».
> Часткове виконання — OK, але не «зроблено».

---

## 9. Антипатерни і явно заборонене

- **A1.** «Спочатку розрубаємо моноліт, потім напишемо контракти» → заборонено (див. [05_TECH_DEBT_ERADICATION_PLAN_V2_IDEAL.md](05_TECH_DEBT_ERADICATION_PLAN_V2_IDEAL.md), Phase 0).
- **A2.** «Поверну `FLAT` як безпечний дефолт при збої PPO» → заборонено (I4).
- **A3.** «У легасі тестах залишимо `0.0` для пропущеної фічі — потім виправимо» → заборонено (I3, I11).
- **A4.** «Async-таски без timeout, бо так робив попередній код» → заборонено (I12 + Phase 7 з 05).
- **A5.** «`modulate` змінить кількість/напрям» → заборонено (Section 1.3 + SSOT_v2 §5.4).
- **A6.** «Ввімкнемо PPO production раніше, бо торч встав» → заборонено до закриття всіх C/L DoD.

---

## 10. Open-question registry (чесний перелік)

| ID | Питання | Власник | Тригер для закриття |
|----|---------|---------|---------------------|
| Q1 | Чи приймемо ми DR-OPE як єдиний оцінювач baseline_pnl? | research | Phase 5 roadmap |
| Q2 | Який мінімум `decision_id` рядків для надійного OPE? | research | Phase 5; орієнтир ≥ 5 000 |
| Q3 | Чи лишаємо PPO як `offline_only` чи видаляємо? | engineering | після Phase 8 в 05 |
| Q4 | Як живе `ModulationStoreRecord` після рестарту? | engineering | overlay-replay test |
| Q5 | Чи потрібен per-symbol `intervention_budget`, чи глобальний? | research | sanity test перед `gated` |
| Q6 | Як інтегрувати `regime_oracle` reward з offline RL reward? | research | Phase 5; вирішення в 07 |
| Q7 | Які саме freshness-вікна для feature аліасів? | engineering | контрактний тест L1 |

---

## 11. Самооскарження блюпринта

> Цей розділ — обов'язковий. Без нього 06 не має права бути SSOT.

- **Може бути не так:** надмірна жорсткість I3 заблокує прийом легасі-логів і змусить переписати парсери. **Захист:** legacy_compat режим існує і явно описаний у §4.1.
- **Може бути не так:** offline reward (§5.1) надто складний, щоб бути валідованим у розумний термін. **Захист:** L5 заблокований через I10; ми чесно блокуємо, а не обманюємося.
- **Може бути не так:** authority deadline 10 ms на синхронному хуці уповільнить decision_making під piк навантаження. **Захист:** §4.4 вимагає load-fixture доказу; якщо < 99.5% — піднімемо до 15-20 мс і зафіксуємо в YAML, не в коді.
- **Може бути не так:** ми оголошуємо «ML-failure → fallback», але fallback сам має формулу. **Відповідь:** так. Fallback = baseline YAML, тобто вже існуюча гілка `decision_making` без Neocortex. Це не нова формула; це шлях, який існував до Neocortex.
- **Може бути не так:** «100% реалізовано» вимагає 14 днів `gated` rollout — занадто довго? **Відповідь:** так, навмисно. Без cooling-period немає доказу Sim2Real стійкості. Скоротити = згенерувати ризик, який не покриється OPE.

---

## 12. Як читати решту документів

- Перш ніж планувати фазу — звіряйся з §2 (інваріанти) і §8 (DoD).
- Перш ніж писати контракт — перечитай SSOT_v2 §4.
- Перш ніж заявляти «фаза готова» — перевір L-DoD і C-DoD.
- Перш ніж казати «100%» — пройди §8.3.

> Решта — у [07_NEOCORTEX_EXECUTION_ROADMAP.md](07_NEOCORTEX_EXECUTION_ROADMAP.md).
