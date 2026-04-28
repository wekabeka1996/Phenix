# 07 — Neocortex Execution Roadmap (HOW & WHEN)

> Послідовний план дій, який доводить домен `apps/reference/domains/neocortex/`
> до стану «100% реалізовано» згідно з [06_NEOCORTEX_MASTER_BLUEPRINT.md](06_NEOCORTEX_MASTER_BLUEPRINT.md).
> Кожна фаза — мала, реверсивна, з прийомним воротами і само-оскарженням.

- Статус: `ACTIVE_ROADMAP`
- Парний документ (контракт): [06_NEOCORTEX_MASTER_BLUEPRINT.md](06_NEOCORTEX_MASTER_BLUEPRINT.md)
- Поглинає та продовжує: [05_TECH_DEBT_ERADICATION_PLAN_V2_IDEAL.md](05_TECH_DEBT_ERADICATION_PLAN_V2_IDEAL.md), [04_TECH_DEBT_ERADICATION_PLAN_V1.md](04_TECH_DEBT_ERADICATION_PLAN_V1.md) (архівний)
- Зважає на аудит: [NEOCORTEX_CODE_QUALITY_AUDIT_2026-04-28.md](NEOCORTEX_CODE_QUALITY_AUDIT_2026-04-28.md)
- Вже виконане ціновим попереднім кроком: [NEOCORTEX_FAIL_CLOSED_REFACTOR_REPORT.md](NEOCORTEX_FAIL_CLOSED_REFACTOR_REPORT.md)
- Інтеграційний контракт: [NEOCORTEX_IMPLEMENTATION_SSOT_v2.md](NEOCORTEX_IMPLEMENTATION_SSOT_v2.md)

---

## 0. Принципи виконання

1. **Контракт перед поділом.** Спочатку інваріант + тест, лише потім розпил коду.
2. **Мала зворотна одиниця.** Кожна фаза = одна-дві пакетні зміни, які можна відкотити одним `git revert`.
3. **Fail-closed first.** Спочатку прибираємо синтетику й мовчазні фолбеки, потім додаємо нову поведінку.
4. **Доказова прийомка.** Жодна фаза не «готова», поки не зелені визначені тести і артефакти.
5. **Без часових оцінок.** Ми міряємо проходження воріт, не дні.
6. **Self-attack кожної фази.** Перш ніж закривати фазу — спробуй довести, що вона зламана. Якщо не можеш — закривай.

---

## 1. Глобальна послідовність

```
Phase 0 — Inventory & Boundary Freeze
    ↓
Phase 1 — Causal Time Hard-Gate           (L0 done)
    ↓
Phase 2 — Config Sterilization            (I2 done)
    ↓
Phase 3 — Failure Taxonomy & Fallback Ledger (I4, I11 done)
    ↓
Phase 4 — Hot-Path Coverage & Static Closure (C1, C2, C3 done; L1, L2 done)
    ↓
Phase 5 — Authority Seam (L3 done) ─────────┐
    ↓                                       ├── (паралельно дозволено)
Phase 6 — Decision Outcome Ledger (L4 done)─┘
    ↓
Phase 7 — Observability, Bounded Queues, Async Lifecycle (C5, I12 done)
    ↓
Phase 8 — Adapter Quarantine → Surgical Extraction (C6 done)
    ↓
Phase 9 — Replay/WAL Compatibility Matrix
    ↓
Phase 10 — Offline Loop, Baseline Estimator, OPE (L5 done; I10 знятий)
    ↓
Phase 11 — Rollout Promotion: shadow → advisory → gated
    ↓
Phase 12 — Final Closure (§8.3 з 06)
```

Жодна фаза не може стартувати, доки контрактні артефакти попередньої не зелені.

---

## 2. Phase 0 — Inventory & Boundary Freeze

### Мета
Зробити неможливим змішування активного runtime, legacy і досліджень.

### Передумови
- читаний 06 §1, §2;
- доступ до venv з `pytest`.

### Кроки
1. Згенерувати інвентар модулів `apps/reference/domains/neocortex/**/*.py` з тегом одного з: `hot_path | legacy_runtime | offline_research | tests_only`. Артефакт: `docs/DeepMind/inventory/neocortex_surface_inventory.md`.
2. Імпортний boundary-тест: `tests/domains/neocortex/architecture/test_import_boundaries.py` (вже існує — розширити, щоб чіпляв ВСІ модулі з тегом `legacy_runtime`).
3. Помітити quarantine у файлах: `transport/adapter.py`, `logic/ingest/multi_tailer.py`, `logic/ingest/tailer.py`, `logic/ingest/wal_replayer.py`, `logic/dreamer.py`, `logic/brain/core.py`, `logic/brain/bridge.py`, `PPO/**`. Додати top-level docstring `# QUARANTINED: legacy_runtime` + module-level marker.
4. Підготувати `compat shim` (тонкий wrapper) для тих legacy-API, які потрібні офлайн-тестам. Жодного нового імпорту в hot path.

### Прийомні ворота
- `pytest tests/domains/neocortex/architecture/test_import_boundaries.py -q` → 0 fails.
- Інвентар-файл присутній і покриває весь домен.

### Артефакти
- `docs/DeepMind/inventory/neocortex_surface_inventory.md`
- розширений `test_import_boundaries.py`

### Self-attack
- Q: «А якщо новий тест тимчасово ламає реальний legacy use case в офлайні?»
  A: дозволено лише через `compat shim`. Сам факт, що це коштує зусиль — корисний сигнал.
- Q: «Чи не варто одразу видалити quarantined?»
  A: ні. Спочатку Phase 8 закриє контракти, тоді видалення стає безризиковим.

### Відкат
Один `git revert` на коміт із markers; нічого runtime-критичного не змінено.

---

## 3. Phase 1 — Causal Time Hard-Gate

### Мета
Виконати інваріант I3 ([06 §2](06_NEOCORTEX_MASTER_BLUEPRINT.md#2-канонічні-інваріанти-i1i12)).

### Кроки
1. Додати enum `CausalTimeProvenance` (значення: `exchange_event | aurora_event | bar_end | captured_wallclock | file_offset_legacy | unknown`) у `apps/reference/domains/neocortex/contracts/causal_time.py`.
2. У парсерах (`logic/ingest/parsers/feature_parser.py`, `order_parser.py`, `core_parser.py`, `state_aggregator_v2.py`) кожен emitted рядок отримує `event_time_source` + `event_time_is_causal`.
3. У `main.py` нормалізація: `captured_ts_ms`/`frame.ts` НІКОЛИ не перетворюються на `event_ts_ms` для production-shadow і training. У `replay.diagnostics_legacy=true` дозволено, але `trainable=false`.
4. Контрактні тести: `tests/domains/neocortex/contract/test_causal_time_provenance.py` — рядки з кожним джерелом, перевірка trainability.
5. Production-shadow startup-gate: відмова при `feature_missing_timestamp_policy=legacy_non_causal_file_offset`.

### Прийомні ворота
- усі парсерські тести зелені;
- L0 DoD з [06 §8.1](06_NEOCORTEX_MASTER_BLUEPRINT.md#81-layer-dod) виконаний;
- alert-counter `dataset.invalid_total{reason_code=NON_CAUSAL_TIME}` емітується.

### Self-attack
- Q: «Що якщо exchange іноді шле подію без `T` поля?»
  A: рядок отримує `unknown` provenance і `trainable=false`. Жодного синтетичного підставлення.
- Q: «А legacy WAL з file-offset часом?»
  A: дозволено в `diagnostic_legacy` режимі, але не може потрапити в datasets з `dataset_visibility=trainable`.

### Відкат
Видалити enum + ревертнути зміни парсерів. Hot path лишається в попередньому стані; жодних збитків даних.

---

## 4. Phase 2 — Config Sterilization

### Мета
Виконати I2: жодного implicit business-default.

### Кроки
1. Класифікувати кожен `Field(...)` у `apps/reference/domains/neocortex/config_models.py` тегом `structural_safe | runtime_behavior | legacy_compat`. Зберігати тег у `Field.json_schema_extra={"default_class": "..."}`.
2. Винести всі `runtime_behavior` дефолти в YAML (`config/aurora/*.yaml` або `apps/reference/domains/neocortex/config/*.yaml`) і вимагати в Pydantic через `...` (no default).
3. Додати reflection-тест: `tests/domains/neocortex/contract/test_config_default_classification.py` — падає, якщо `runtime_behavior` має implicit default.
4. Додати real-config startup-test: завантажує всі YAML і виконує `ShadowGateEvaluator`.
5. Додати нові ключі з [06 §6.2](06_NEOCORTEX_MASTER_BLUEPRINT.md#62-нові-обовязкові-ключі-з-ssotv2-appendix-c).

### Прийомні ворота
- 0 неклассифікованих defaults;
- C4 з [06 §8.2](06_NEOCORTEX_MASTER_BLUEPRINT.md#82-cross-cutting-dod);
- production-shadow падає при відсутності будь-якого з ключів §6.2.

### Self-attack
- Q: «Чи не зламає це SSO старі тести, які покладались на defaults?»
  A: зламає, і це бажано. Тести мають описати свій конфіг явно — це сигнал, що до того тест мав хибну презумпцію SSOT.

### Відкат
Реверт коміта; YAML лишається, тести червоніють — сигнал не повертатися назад без справжньої причини.

---

## 5. Phase 3 — Failure Taxonomy & Fallback Ledger

### Мета
Закрити I4 і I11.

### Кроки
1. Додати enum `FailureOutcomeTaxonomy` (значення з [06 §4.5](06_NEOCORTEX_MASTER_BLUEPRINT.md#45-шар-l4--outcome-ledger)).
2. Замінити всі `except Exception:` у hot-path модулях на типізовані outcomes + counter.
3. Додати reason codes для `SKIP_ROW`: `NON_CAUSAL_TIME`, `MISSING_REQUIRED_STATE`, `UNJOINABLE_LIFECYCLE`, `LOW_SUPPORT`, `BASELINE_UNAVAILABLE`, `MALFORMED_JSON`, `HANDLER_FAILURE`.
4. Тести-провокатори: malformed JSON, I/O fail, bridge timeout, baseline artifact mismatch, telemetry flush fail.
5. У `WALReplayer` ввімкнути strict-mode за замовчуванням для тренувальних режимів.

### Прийомні ворота
- жодного `except Exception:` у hot-path (lint-policy + test);
- counter `failure_outcomes_total{taxonomy,reason_code}` емітується;
- 122 існуючих тестів з [NEOCORTEX_FAIL_CLOSED_REFACTOR_REPORT.md](NEOCORTEX_FAIL_CLOSED_REFACTOR_REPORT.md) лишаються зеленими.

### Self-attack
- Q: «Чи не задушимо ми shadow-runtime fail-fast'ом?»
  A: shadow може продовжити працювати при `DEGRADED_OBSERVABILITY`. `FATAL_STARTUP` — лише для startup-gate і конфіг-провалу.

---

## 6. Phase 4 — Hot-Path Coverage & Static Closure

### Мета
C1, C2, C3 (06 §8.2) на hot-path.

### Кроки
1. Зафіксувати hot-path scope (06 §1.1): `main.py`, `state_aggregator_v2.py`, `baseline_inference.py`, `gates/shadow.py`, новий `authority_bridge.py` (з Phase 5 — стаб тут), shadow WAL append.
2. Покрити branch coverage до 100% для hot-path.
3. Встановити `mypy` у venv (`.venv/Scripts/python -m pip install mypy==<version>`); зафіксувати у `dev-requirements.txt`.
4. Прогнати `mypy apps/reference/domains/neocortex/` обмежено по hot-path; виправити помилки.
5. Замінити `dict[str, Any]` на типізовані dataclass / Pydantic усередині hot-path; залишити `Any` лише на JSON-кордоні (ingress/egress).

### Прийомні ворота
- `pytest <hot-path-tests> --cov=<hot-path-modules> --cov-fail-under=100` зелений;
- `mypy` 0 помилок;
- VS Code diagnostics — 0 для hot-path файлів.

### Self-attack
- Q: «100% покриття не значить правильна логіка.»
  A: правда. Тому combinujemo з контрактними тестами Phase 1-3 і property-based тестами для аліасів/нормалізації.

---

## 7. Phase 5 — Authority Seam (синхронний bridge)

### Мета
L3 DoD (06 §4.4) + інваріанти I5, I6.

### Кроки
1. Контрактні моделі:
   - `apps/reference/domains/neocortex/contracts/observation_envelope.py`
   - `apps/reference/domains/neocortex/contracts/control_decision.py` (request/response, AuthorityMode)
2. У `decision_making.strategy_gateway` після успіху gate-chain і перед `_propose_trade_intent()`:
   - збудувати `ObservationEnvelope`;
   - якщо `neocortex.trust_enabled=true` і `mode != shadow_record_only` — викликати `NeocortexAuthorityBridge.decide(...)`;
   - врахувати `expires_at_ms`, `LATE`-логіку, fallback.
3. `NeocortexAuthorityBridge` (новий клас у `apps/reference/domains/neocortex/transport/authority_bridge.py`):
   - синхронний `decide(...)`;
   - kill-switch перевіряється першим (`< 1ms` шлях);
   - bounded inflight `max_inflight_per_symbol=1`.
4. Журнали:
   - `authority_request_journal_v1.jsonl`
   - `authority_response_journal_v1.jsonl`
   - дописується `authority_context` (decision_id, authority_mode, apply_result) у emitted intent.
5. `ModulationStoreRecord` (out-of-scope для перших v2 знімань `gated`, але контракт уже зафіксований):
   - схема + WAL persistence;
   - використання тільки з наступного семантичного тіку.

### Прийомні ворота
- load-fixture: ≥ 99.5% deadline hit-rate за `deadline_ms=10`;
- kill-switch drill: `trust_enabled=false` → `fallback` за `< 1ms`, без побічних ефектів;
- L3 DoD зелений.

### Self-attack
- Q: «А якщо `decision_making` уже зайнятий emit-ом і неможна синхронно блокуватись?»
  A: `FSMCore.emit()` інлайн (SSOT_v2 §3.4 + Reality Baseline). Тому інлайн bridge — найдешевший і найдетермінованіший шлях; асинхронна шина дала б нам спізнілий критик.
- Q: «Що, якщо bridge сам впав?»
  A: typed `RuntimeError` → fallback → `apply_result=fallback`, `fallback_reason=BRIDGE_UNAVAILABLE`. Це покрите Phase 3 taxonomy.

---

## 8. Phase 6 — Decision Outcome Ledger

### Мета
L4 DoD (06 §4.5) + I7.

### Кроки
1. `apps/reference/domains/neocortex/logic/ledger/decision_outcome_ledger.py`:
   - стейджинг рядка під час bridge request;
   - доповнення на response;
   - фіналізація на close-event або фатальний reject.
2. Шви join: `decision_id` (primary), `rid`, `lifecycle_id`, `trade_id`.
3. Тести:
   - `test_decision_ledger_terminalization.py` — рівно один термінальний рядок на `decision_id`;
   - `test_alias_reconciliation.py` — `rid/lifecycle_id/idempotent_key/reservation_id/corr_id` resolve детерміновано.
4. Метрики §7.1 з 06.

### Прийомні ворота
- 0 «open»-рядків старших за TTL fixture;
- усі стани `terminal_status` покриті тестами.

### Self-attack
- Q: «Що, якщо `execution_position` емітить close без `trade_id`?»
  A: рядок отримує `INVALID_FOR_DATASET` з `UNJOINABLE_LIFECYCLE`. Без синтетики.

---

## 9. Phase 7 — Observability & Bounded Queues

### Мета
C5 + I12.

### Кроки
1. Кожен sink (`telemetry.py`, shadow JSONL, ledger WAL, modulation journal) — bounded queue з drop counter і явною policy (`block | drop_oldest | drop_newest`).
2. Async lifecycle audit: кожна `asyncio.Task` має `name`, `owner`, `shutdown path`, `timeout`, exception propagation тест.
3. Soak-тест: синтетичний burst 60 секунд.
4. SQLite causal graph (`logic/memory/graph.py`): single-writer enforce, timeout config-driven, lock-contention test (тільки якщо буде reconnect Dreamer).

### Прийомні ворота
- bounded-queue тести зелені;
- async shutdown тест: 0 pending tasks після cancellation.

### Self-attack
- Q: «Чи не виходить, що ми перевигадуємо message-broker?»
  A: ні. Це in-process bounded `asyncio.Queue` + контракт. Без cross-process delivery.

---

## 10. Phase 8 — Adapter Quarantine → Surgical Extraction

### Мета
C6: моноліт `transport/adapter.py` зникає, без втрати функцій.

### Кроки
1. Витягуємо чисті функції: timestamp normalization, feature-map extraction, shadow-intent serialization, objective-family classification → у малі модулі з тестами.
2. Витягуємо sinks: telemetry CSV sink, shadow JSONL sink, alert emitter — як окремі сервіси з bounded queues (Phase 7 готує ґрунт).
3. Витягуємо stateful: normalizer state, dataset admission, oracle settlement, policy sample buffering.
4. Лишаємо тонкий `NeocortexAdapter` facade лише для legacy тестів і офлайн-команд.
5. Видаляємо facade, як тільки прямі тести `adapter.*` мігровано / помічено `legacy_test_only`.

### Прийомні ворота
- import-boundary тест: hot path не імпортує `transport.adapter`;
- кожна екстракція має before/after golden-test;
- 0 приватних-полів-asserts у нових сервісах.

### Self-attack
- Q: «А якщо старі тести зламано і переписувати їх не варто?»
  A: помітити `@pytest.mark.legacy` + виключити з hot-path coverage. Не зливаємо їхні асерти у нову реальність.

---

## 11. Phase 9 — Replay/WAL Compatibility Matrix

### Мета
Backward compatibility без отруєння training.

### Кроки
1. Версії WAL і aliases: `event_ts_ms | timestamp_ms | timestamp | ts_ms | ts | rid | lifecycle_id | idempotent_key | reservation_id | corr_id | trade_id`.
2. Матриця:
   - old + causal time → trainable, якщо інші ворота пройдено;
   - old без causal → diagnostics-only;
   - alias drift → resolvable, якщо детерміновано і записано;
   - malformed → skip або fail (за strictness).
3. Replay reports: лічники accepted / skipped / diagnostics-only / malformed / non-causal / unresolved-lifecycle / trainable.
4. Fixture WAL для кожного кейсу.

### Прийомні ворота
- strict mode падає на non-causal trainable рядку;
- diagnostic mode завершується і видає звіт.

### Self-attack
- Q: «Чи не консервуємо ми застарілі формати назавжди?»
  A: ні. Кожна `legacy_compat` гілка має `sunset_after_version`; у Phase 12 робимо grand-cleanup.

---

## 12. Phase 10 — Offline Loop, Baseline Estimator & OPE

### Мета
L5 DoD (06 §4.6); зняття I10.

### Кроки
1. `dataset_builder` поверх `DecisionOutcomeLedgerRow + ObservationEnvelope` з event-time merge і support-quality маркерами.
2. `baseline_pnl_estimator` (DR-OPE):
   - propensity score з behavior policy (gate chain decisions log);
   - direct method від виміряного PnL;
   - DR combine + bootstrap CI.
3. Reward calc (offline) за формулою з [06 §5.1](06_NEOCORTEX_MASTER_BLUEPRINT.md#51-reward-offline-only).
4. Permutation test → α≈0 на перемішаних мітках.
5. Sanity: «нульовий агент» (ніколи не блокує) має $R \le 0$ після внеску $S, O, B$.
6. Доки не виконано — `reward_valid=false` для всіх рядків.

### Прийомні ворота
- ≥ 5 000 trainable рядків з resolved lifecycle;
- DR-OPE CI вужчий за поріг (`width < 0.20` для нормалізованого uplift, або інший — задокументувати в YAML);
- permutation test пройдений.

### Self-attack
- Q: «А раптом 5 000 — недостатньо?»
  A: підвищуємо до 10 000 і фіксуємо у YAML. Не запускаємо `gated` без CI задовільного розміру.
- Q: «Чи DR-OPE достатньо коректний для наших розріджень?»
  A: відкритий Q1 з [06 §10](06_NEOCORTEX_MASTER_BLUEPRINT.md#10-open-question-registry-чесний-перелік). Якщо ні — додаємо weighted importance sampling як другий estimator.

---

## 13. Phase 11 — Rollout Promotion

### Мета
shadow → advisory → gated за матрицею з SSOT_v2 §8.

### Ворота переходів

#### shadow → advisory
- усі L0–L4 DoD зелені;
- ledger completeness ≥ 99.9%;
- 0 алертів §7.3 за 7 днів shadow-running.

#### advisory → gated
- advisory drill: оператор бачить authority trace, прийнято/відхилено вручну ≥ 200 кейсів;
- deadline hit-rate ≥ 99.5%;
- kill-switch drill зелений (`< 1ms`);
- offline reward valid (Phase 10).

#### gated утримується
- ≥ 14 днів без алертів §7.3;
- drawdown monitor у межах;
- drift monitor у межах;
- intervention budget не перевищено.

### Self-attack
- Q: «А якщо за 14 днів не виникне жодного інтенсивного ринкового моменту?»
  A: розтягуємо вікно або вимагаємо синтетичного stress-test реплея на історичних шоках. Не скорочуємо вікно.

---

## 14. Phase 12 — Final Closure (100%)

### Мета
Закрити §8.3 з 06.

### Дії
1. Прогнати повний DoD-чекліст (06 §8); 0 жовтих/червоних.
2. Видалити всі `legacy_compat` шляхи, у яких настав `sunset_after_version`.
3. Видалити `transport/adapter.py` facade, якщо нема callers.
4. Прийняти рішення по PPO/Dreamer (Q3 у 06): `delete | archive | offline_only | reconnect`. Якщо `reconnect` — окремий мікро-проєкт з власною roadmap.
5. Опублікувати фінальний SSOT-passport: `docs/DeepMind/CLOSURE_REPORT_<date>.md`, у якому посилання на тестові артефакти, метрики, журнали.

### Прийомні ворота 100%
- усі L-DoD зелені;
- усі C-DoD зелені;
- gated rollout ≥ 14 днів;
- offline RL виконав один цикл навчання на real WAL з permutation test;
- closure report підписаний (git tag).

### Self-attack
- Q: «Що, якщо хтось завтра додасть новий feature і дефолти?»
  A: reflection-тест Phase 2 його зловить. Якщо ні — це регресія DoD, відкочуємо.

---

## 15. Cross-cutting обов'язки

### 15.1 Документація
- 06 і 07 — живі. Будь-яка зміна контракту змінює 06 і додає підпункт у 07 з новим прийомним воротом.
- SSOT_v2, audit і fail-closed report — frozen reference (immutable).

### 15.2 Спостережуваність
- Усі лічники з [06 §7.1](06_NEOCORTEX_MASTER_BLUEPRINT.md#71-лічильники-які-мусять-існувати) додаються інкрементально починаючи з Phase 5.

### 15.3 Конфіг-зміни
- Кожен новий ключ → reflection-test + миграційна нотатка у YAML коментарі.

### 15.4 Тестові набори
- `tests/domains/neocortex/architecture/` — boundary/import/quarantine.
- `tests/domains/neocortex/contract/` — контракти і провенанс.
- `tests/domains/neocortex/integration/` — bridge, ledger, telemetry.
- `tests/domains/neocortex/property/` — property-based для аліасів і час.
- `tests/domains/neocortex/load/` — deadline / queue burst (опційно, але потрібно для Phase 5/7 ворот).

---

## 16. Залежності між фазами (паралелізм)

- Phase 0 — обов'язково перша.
- Phase 1, 2, 3 — можна виконувати по черзі або злегка перекриватися; усі ─ передумова для 4.
- Phase 5 і 6 — паралельні після Phase 4.
- Phase 7 — починається паралельно з 5/6, але закривається після них.
- Phase 8 — стартує лише коли Phase 7 (bounded queues) пройдено.
- Phase 9 — паралельно з 8.
- Phase 10 — залежить від 6 (ledger) і 9 (compat matrix).
- Phase 11 — залежить від 5, 6, 7, 10.
- Phase 12 — фінальна.

Не починати фазу N+1, якщо ворота N не зелені — інакше ризики переносяться, а не вирішуються (саме ця помилка описана в [05 § «Brutally Honest Verdict»](05_TECH_DEBT_ERADICATION_PLAN_V2_IDEAL.md#brutally-honest-verdict)).

---

## 17. Відкат і безпека

- Кожна фаза = окремий PR/коміт.
- Кожен коміт супроводжується test-suite, який доводить ворота.
- При rollback — викликаємо `git revert <commit>`; runtime повертається у попередній стійкий стан (Stage 0.3 shadow).
- Hot-path не може регресувати в пройдений DoD: будь-який test-fail на існуючий L-DoD блокує merge.

---

## 18. Само-оскарження плану

- **План занадто лінійний?** Так, навмисно. Ми виявили в [05](05_TECH_DEBT_ERADICATION_PLAN_V2_IDEAL.md), що паралельні рефакторинги без контрактів призводять до «менших коробок з тією ж двозначністю». Лінійність тут — це особливість, не баг.
- **План занадто повільний?** Можливо. Але «100% реалізовано» — це властивість, яку швидкими шляхами не отримати. Можна паралельно (§16), не можна пропустити.
- **План залежить від невирішених math-question?** Так (Phase 10). Ми чесно блокуємо L5, поки не знятий I10. Це і є простота-через-чесність.
- **Що, якщо в process'і виявимо, що SSOT_v2 хибний?** Тоді редагуємо 06, потім додаємо нову фазу в 07. Ніколи не «виправляємо в коді мовчки».
- **Що, якщо в реальності щось зламається в shadow під час `gated`-rollout?** Алерт §7.3 з 06 → автоматичний downgrade у `advisory` → інцидент → новий phase з причиною. Це не провал — це штатна процедура.

---

## 19. Як зрозуміти, що ми «на 100%»

Тільки якщо одночасно виконано всі три:

1. ✅ Усі ворота фаз 0..12 зелені і збережений артефакт-доказ.
2. ✅ §8.3 з [06_NEOCORTEX_MASTER_BLUEPRINT.md](06_NEOCORTEX_MASTER_BLUEPRINT.md#83-глобальний-100-критерій) виконаний.
3. ✅ Closure report (Phase 12) підписаний git-тегом і його чек-лист пройдений в CI.

Будь-яке інше формулювання («майже все зроблено», «99%», «лишилось декілька дрібниць») — означає, що ми ще не закінчили.
