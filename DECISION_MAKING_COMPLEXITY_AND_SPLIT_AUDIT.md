# Decision Making — Complexity & Split Feasibility Audit

Дата: 2026-04-24
Гілка: Phenix_v2
Режим: read-only (код не змінювався)
SSOT-джерела: `Copilot_Master_Roadmap.md`, `apps/reference/domains/decision_making/README.md`,
`DECISION_MAKING_SURFACE_MAP.md`, `DECISION_MAKING_CONTRADICTION_MATRIX.md`,
`DECISION_MAKING_LEGACY_DRIFT_AUDIT.md`, `DECISION_MAKING_CLEANUP_PLAN.md`,
`apps/reference/dictionaries/verb_registry_v1.yaml`,
repo memory (`decision_making_*`, `package3_final_deep_audit`, `execpos_fsm_decomposition_roadmap`).

## TL;DR

1. Так, домен **об'єктивно перероздутий**: 74 `.py` / ~20.6k LOC — найбільший неймспейс репо;
   три файли-монстри (`md_amr_handler.py` 2459, `mean_reversion_handler.py` 1903,
   `aurora_decision.py` 1594) дають ~29 % всього LOC.
2. Але це **не про "колишній один engine, що роздувся"**. Це **намішані дві природи коду**:
   - *(a)* домен-координатор (facade + gate-chain + intent truth-path),
   - *(b)* набір стратегій-рантаймів Aurora / MD-AMR / MeanReversion + їхня математика.
   Співрозміщення і створює ілюзію "складного одного домену".
3. **Розколювати як один моноліт — не треба і не можна безпечно.** Правильне рішення —
   **деконфлейт (de-conflation) по трьох осях** у вже існуючих кордонах репо:
   - стратегічні рантайми і мати strategy-math → `apps/reference/domains/strategies/`,
   - numeric/primitives (scoring, entry/exit plan, sizing, quantizer, shields) → розділені
     пакети всередині DM або підняті в `shared/`,
   - ядро (facade + gateway + intent builder/emitter + NRR/WAL) залишається вузьким
     "Decision Core" з чіткою відповідальністю "взяти сигнал → згенерувати `TRADE_INTENT_*`".
4. Це **не redesign, а bounded decomposition**: знижує когнітивну масу на 50–60 %
   без зміни runtime-контрактів. Рекомендація — 3 ітерації, кожна самодостатня і відкатна.
5. Перш ніж рухати файли — **обов'язково закрити 4 відомі контрактні дрейфи**
   (див. §6), бо вони маскують реальні межі відповідальностей.

---

## 1. Метрики складності (FACT)

### 1.1 Загальні розміри

| Метрика | Значення |
| --- | --- |
| Файлів `.py` (incl. `gates/`, `shields/`) | **74** |
| Сумарно LOC (python) | **20 629** |
| Файлів >500 LOC | **10** |
| Файлів >1000 LOC | **3** (`md_amr_handler`, `mean_reversion_handler`, `aurora_decision`) |
| Внутрішньо-пакетних `from .` / `from apps.reference.domains.decision_making.*` імпортів | **>120** (обрізано; межа пошуку 200) |
| Зовнішніх обертань до DM (весь repo, не тести) | **десятки модулів** у `main.py`, `bootstrap/`, `strategies/plugins/*`, `alpha_search/`, `objective_engine/`, `execution_position/`, `shared/types.py`, `contracts/quadratic_rollout.py` |
| Events consumed (згідно README) | 13 |
| Events emitted | 12 |
| Pydantic typed-config SSOT | `apps/reference/config/domains/decision_making.py` → `DecisionMakingDomainConfig` |

### 1.2 Top-15 файлів за LOC

| LOC | Файл | Реальна "природа" |
| ---: | --- | --- |
| 2459 | [md_amr_handler.py](apps/reference/domains/decision_making/md_amr_handler.py) | strategy runtime |
| 1903 | [mean_reversion_handler.py](apps/reference/domains/decision_making/mean_reversion_handler.py) | strategy runtime |
| 1594 | [aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py) | strategy runtime (mixin) |
| 871 | [aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py) | strategy runtime |
| 706 | [strategy_gateway.py](apps/reference/domains/decision_making/strategy_gateway.py) | **core** (gate chain owner) |
| 593 | [event_handlers.py](apps/reference/domains/decision_making/event_handlers.py) | **core** (ingress) |
| 587 | [safety_gates.py](apps/reference/domains/decision_making/safety_gates.py) | gate library |
| 570 | [decision_making.py](apps/reference/domains/decision_making/decision_making.py) | **core** facade |
| 565 | [normalized_reject_reasons.py](apps/reference/domains/decision_making/normalized_reject_reasons.py) | contract (NRR SSOT) |
| 482 | [intent_builder.py](apps/reference/domains/decision_making/intent_builder.py) | **core** (intent truth) |
| 477 | [aurora_tpsl.py](apps/reference/domains/decision_making/aurora_tpsl.py) | strategy numerics |
| 471 | [readiness_gates.py](apps/reference/domains/decision_making/readiness_gates.py) | gate library |
| 436 | [shields/memory_shield.py](apps/reference/domains/decision_making/shields/memory_shield.py) | scoring primitive |
| 426 | [aurora_config_loader.py](apps/reference/domains/decision_making/aurora_config_loader.py) | strategy config |
| 411 | [intent_emitter.py](apps/reference/domains/decision_making/intent_emitter.py) | **core** (reject/defer truth) |

**Інтерпретація**: лише ~5 з 15 найбільших — це справжнє ядро домену; інші 10 —
це стратегії та їхній сервіс.

### 1.3 Структурні "sensors" складності

| Сенсор | Доказ | Що це означає |
| --- | --- | --- |
| Mixin-"бог" | `AuroraHandler(AuroraTpslMixin, AuroraScoringHelpersMixin, AuroraDecisionMixin, AuroraConfigLoaderMixin, AuroraHoldingPeriodMixin)` — 5 mixin-ів, 2400+ сумарного LOC (див. import-блок `aurora_handler.py:41-45`) | класична ознака того, що "handler = 5 доменів в одному класі" |
| Three-tier gate overlap | `StrategyGateway` (gate_chain) → `decision_making._propose_trade_intent` (fallback safety_gate) → `aurora_decision` (local objective/execution gate) | жоден шар не є **єдиним** автором відмови (див. §6) |
| Dual-emit для одного verb | `ALPHA_SCORE_CALCULATED`: registry owner = alpha_search, але `event_handlers.py` теж emit-ить | runtime-truth розходиться з контрактом |
| Split truth на reject | `intent_emitter` канонічний; aurora/MR пишуть reject WAL напряму; MD-AMR emit-ить `TRADE_INTENT_REJECTED` без local shaping | одна сутність, 4 варіанти shaping |
| Tombstoned residue | `deferred_scheduler.py` логує `TOMBSTONE_HIT` на instance-time; експортується з `__init__.py` | мертвий код у публічній поверхні |
| Compat aliases | `DecisionMakingLogic = DecisionMaking`; `handle_tick` — now status-only | compatibility residue в головному файлі |
| Namespace-cross imports | `aurora_handler` імпортує `quadratic_scoring_kernel`, `shields/*`, `execution_gate`, `exit_manager`, `entry_plan`, `instrument_quantizer`, `position_queries`, `dashboard`, `trade_intent_reject_wal`, `decision_truth_artifacts` | handler тягне майже все ядро — межа "стратегія vs ядро" дифузна |
| Зовнішні "проривання" | `objective_engine/adapters.py` імпортує `entry_plan.EntryPlanResult` і `position_queries.PositionQueries`; `alpha_search/models/aurora_adapter.py` імпортує `quadratic_scoring_kernel`; `shared/types.py` імпортує `normalized_reject_reasons` | частина "внутрішніх" модулів DM фактично вже є **спільними** примітивами |

---

## 2. Карта відповідальностей (осі)

Домен сьогодні одночасно виконує 6 різних функцій:

| # | Вісь | Представники | Роль | Коріння |
| - | ---- | ------------ | ---- | ------- |
| A | **Core facade / orchestrator** | `decision_making.py`, `event_handlers.py`, `dm_state.py`, `dm_config_spec.py`, `config_resolver.py`, `decision_context.py`, `runtime_readiness_builder.py` | Отримати події, утримувати стан, диспечеризувати | FSM-інтеграція |
| B | **Gate chain (decision policy)** | `strategy_gateway.py`, `gate_chain.py`, `gate_protocol.py`, `gates/*` (9 gates), `safety_gates.py`, `execution_gate.py`, `inception_filter.py`, `objective_gate_evaluator.py`, `readiness_gates.py`, `regime_loss_embargo.py`, `regime_smoother.py`, `qos_rate_control.py`, `deferred_scheduler.py` (dead) | Єдиний канонічний gate-pipeline "signal → pass/defer/block/reject" | Phase 14A strangler fig |
| C | **Intent truth-path** | `intent_builder.py`, `intent_builder_policy.py`, `intent_builder_validators.py`, `intent_payload_assembler.py`, `intent_emitter.py`, `flip_orchestration.py`, `trade_intent_reject_wal.py`, `decision_truth_artifacts.py`, `schemas/*.json`, `schemas.py`, `schemas_decision_blocked.py` | Зібрати `TRADE_INTENT_*`, WAL, DECISION_TRACE | Контрактне ядро |
| D | **Strategy runtimes** (стратегії як рантайми) | `aurora_handler.py` + `aurora_{decision,math,policy,scoring_helpers,holding_period,tpsl,config_loader}.py`; `mean_reversion_handler.py` + `mean_reversion_logger.py`; `md_amr_handler.py` + `md_amr_entry_anchor_artifact.py`; `strategy_bridge.py` (re-export з FE) | Три незалежні рантайми, зарестровані через `strategies/plugins/*`; **ядру непотрібні**, споживають його | FE-DM-BOUNDARY-STABILIZATION 2026-03-15 |
| E | **Numeric / plan primitives** | `quadratic_scoring_kernel.py`, `aurora_math.py`, `aurora_policy.py`, `shields/*` (4 shields + base), `entry_plan.py`, `exit_manager.py`, `tpsl_owner.py`, `sizing_margin_first.py`, `instrument_quantizer.py` | Перевикористовуються зовні (`alpha_search`, `objective_engine`) — фактично **shared** | Історично приросли до Aurora |
| F | **Contracts & observability** | `normalized_reject_reasons.py` (NRR SSOT), `why_codes.py` (re-export), `schemas.py`, `schemas_decision_blocked.py`, `schemas/`, `dm_log_adapter.py`, `dashboard.py`, `domain_dict.json`, `boundary_models.py`, `boundary_mappers.py`, `core_models.py` | Контракти і DTO, частково експортовані з DM як SSOT | Історично |

> **Інсайт.** Тільки осі **A + B + C** — це справді "decision making". Осі **D**, **E**
> частково, і **F** частково — це інші відповідальності, що живуть в одному неймспейсі.

---

## 3. Чи якість страждає від розмірів?

**FACT**: тести домену (`tests/domains/decision_making/`) — зелені на структурному guardrails
(`test_dm_domain_structural_guardrails.py`, `test_verb_registry_contracts.py` проходять),
але 22 червоні з 787 залишаються на Package 3 final audit (див. repo memory
`package3_final_deep_audit_2026-04-19.md`). Природа 22 reds:

- 16 PRE_EXISTING_ORTHOGONAL (не викликані розміром домену),
- 6 PACKAGE_ADJACENT_UNPROVEN (виникають на семах між стратегіями та ядром — тобто саме там,
  де розмір і дифузія меж створюють крихкість).

**INFERENCE**: сам факт "1 великий домен" не руйнує тести, але **межі mixin-"бога"**
(`aurora_handler` з 5 mixins) і **дубль ownership для `TRADE_INTENT_REJECTED`** дають
стабільний шум по 6 reds на межах.

## 4. Чи ефективність страждає?

**Ні, не на рівні hot-path**:
- `decision_making.py` вже став thin facade (Phase 14A), P3.D landed
  (див. `decision_making_p3d_composition_slimming_2026-04-18`),
- imports ліниві де треба (`from ... import ProcessStrategyCmd  # noqa: PLC0415` у 3+ місцях `aurora_handler.py`, `aurora_decision.py`),
- gate chain — O(N) по gates, але N≤9 і короткозамкнутий.

**Так, на рівні cognitive load і change-blast-radius**:
- нова фіча в MD-AMR змушує читати 2459 LOC handler;
- додавання нового reject reason хопає 4 shaping-paths;
- рефакторинг `IntentBuilder` ризикує зачепити 3 стратегії через ре-експорти з `__init__.py`.

---

## 5. Чи "переріс свою роль"?

**Так, у точному сенсі**: роль декларована як "central decision engine" (README §Responsibility),
але **runtime-truth** показує що домен зараз є:

> namespace, що одночасно хостить **один domain-facade** і **три strategy-runtime-и**,
> плюс їхню спільну математику і кілька контрактних SSOT.

Це не баг і не деградація — це артефакт послідовних еволюцій (FE-DM boundary stabilization
2026-03-15, Phase 14A, Package 3.A/B/C/D). Але межа "decision_making як owner" вже
заведено штучна: див. `DECISION_MAKING_SURFACE_MAP.md §INFERENCES`:

> decision_making is not a single runtime owner. It is a namespace that currently contains
> both a general domain facade and multiple strategy-local runtimes.

---

## 6. Контрактні дрейфи — блокери будь-якого розколу (FACT)

З `DECISION_MAKING_CONTRADICTION_MATRIX.md` (не залежать від цього аудиту, підтверджені):

| # | Verb | Природа дрейфу | Що треба |
| - | ---- | -------------- | -------- |
| 1 | `ALPHA_SCORE_CALCULATED` | registry: owner=alpha_search; runtime: emit ще й з DM `event_handlers.py` | явно двокористувацький контракт або винести emission |
| 2 | `QUADRATIC_DECISION_TRACE` | emit у `aurora_decision.py`, export у `domain_dict.json`, **НЕ в `verb_registry_v1.yaml`** | зареєструвати або вилучити |
| 3 | `HANDLER_READINESS_DIAGNOSTICS` | registry+domain_dict declared active, **без runtime emitter** | реалізувати або вилучити |
| 4 | `TRADE_INTENT_REJECTED` | 4 shaping-paths (IntentEmitter canonical + aurora/MR WAL-direct + md_amr emit-direct) | уніфікувати через один Gateway-level емітер |

**Правило перед розколом**: ці 4 контракти мають бути або зафіксовані, або explicit multi-owner'ні.
Інакше будь-який фізичний move зробить truth-дивергенцію **видимою як bug** (а не як drift).

---

## 7. Варіанти майбутньої архітектури

### Варіант 0 — Status quo (robustness)
Залишити все як є, виправити 4 контрактні дрейфи (§6) і residue
(deferred_scheduler, `DecisionMakingLogic` alias, narrow `__init__.py`).
Це — *абсолютний мінімум*. Він рятує тести і чесність контрактів, але не знижує
когнітивну масу.

### Варіант A — Внутрішня модуляризація (рекомендований перший крок)

Розділити файли **всередині** `decision_making/` на підпакети з чітким API,
БЕЗ переносу в інші домени.

#### A.1 Цільовий скелет (фізичний)

```
apps/reference/domains/decision_making/
├── __init__.py                     # narrow re-exports (вузький публічний API)
│
├── core/                           # 7 файлів — orchestrator + state + config wiring
│   ├── __init__.py
│   ├── facade.py                   # ← decision_making.py
│   ├── event_handlers.py           # ← event_handlers.py
│   ├── state.py                    # ← dm_state.py
│   ├── config_spec.py              # ← dm_config_spec.py
│   ├── config_resolver.py          # ← config_resolver.py
│   ├── context.py                  # ← decision_context.py
│   └── runtime_readiness.py        # ← runtime_readiness_builder.py
│
├── gateway/                        # 3 файли — generic gate chain framework
│   ├── __init__.py
│   ├── protocol.py                 # ← gate_protocol.py
│   ├── chain.py                    # ← gate_chain.py
│   └── strategy_gateway.py         # ← strategy_gateway.py
│
├── gates/                          # 14 файлів — конкретні gate-реалізації
│   ├── __init__.py                 # ← gates/__init__.py
│   ├── arbitration_gate.py
│   ├── exposure_gate.py
│   ├── flip_gate.py
│   ├── qos_gate.py
│   ├── risk_gate.py
│   ├── risk_skew_gate.py
│   ├── safety_gate.py              # wrapper над safety_gates
│   ├── ttl_gate.py
│   ├── warmup_gate.py
│   ├── safety_gates.py             # ← safety_gates.py (library)
│   ├── execution_gate.py           # ← execution_gate.py
│   ├── inception_filter.py         # ← inception_filter.py
│   ├── objective_gate_evaluator.py # ← objective_gate_evaluator.py
│   ├── readiness_gates.py          # ← readiness_gates.py
│   ├── regime_loss_embargo.py      # ← regime_loss_embargo.py
│   ├── regime_smoother.py          # ← regime_smoother.py
│   ├── qos_rate_control.py         # ← qos_rate_control.py
│   └── deferred_scheduler.py       # ← [видалити у Пакеті 1, residue]
│
├── intent/                         # 9 файлів + schemas — truth-path
│   ├── __init__.py
│   ├── builder.py                  # ← intent_builder.py
│   ├── builder_policy.py           # ← intent_builder_policy.py
│   ├── builder_validators.py       # ← intent_builder_validators.py
│   ├── payload_assembler.py        # ← intent_payload_assembler.py
│   ├── emitter.py                  # ← intent_emitter.py
│   ├── flip.py                     # ← flip_orchestration.py
│   ├── truth_artifacts.py          # ← decision_truth_artifacts.py
│   ├── reject_wal.py               # ← trade_intent_reject_wal.py
│   └── schemas/                    # ← schemas/ (JSON-schemas)
│
├── strategies/                     # 12 файлів — тимчасовий хаб перед Варіантом B
│   ├── __init__.py
│   ├── bridge.py                   # ← strategy_bridge.py
│   ├── aurora/
│   │   ├── __init__.py
│   │   ├── handler.py              # ← aurora_handler.py
│   │   ├── decision.py             # ← aurora_decision.py
│   │   ├── tpsl.py                 # ← aurora_tpsl.py
│   │   ├── scoring_helpers.py      # ← aurora_scoring_helpers.py
│   │   ├── holding_period.py       # ← aurora_holding_period.py
│   │   ├── config_loader.py        # ← aurora_config_loader.py
│   │   └── policy.py               # ← aurora_policy.py
│   ├── mean_reversion/
│   │   ├── __init__.py
│   │   ├── handler.py              # ← mean_reversion_handler.py
│   │   └── logger.py               # ← mean_reversion_logger.py
│   └── md_amr/
│       ├── __init__.py
│       ├── handler.py              # ← md_amr_handler.py
│       └── entry_anchor_artifact.py# ← md_amr_entry_anchor_artifact.py
│
├── primitives/                     # 12 файлів — numeric/plan математика
│   ├── __init__.py
│   ├── scoring_kernel.py           # ← quadratic_scoring_kernel.py
│   ├── aurora_math.py              # ← aurora_math.py  (перейменувати на math_kernel.py у Варіанті B)
│   ├── entry_plan.py               # ← entry_plan.py
│   ├── exit_manager.py             # ← exit_manager.py
│   ├── tpsl_owner.py               # ← tpsl_owner.py
│   ├── sizing_margin_first.py      # ← sizing_margin_first.py
│   ├── instrument_quantizer.py     # ← instrument_quantizer.py
│   └── shields/                    # ← shields/ (5 файлів)
│       ├── __init__.py
│       ├── base.py
│       ├── null_shield.py
│       ├── context_shield.py
│       ├── memory_shield.py
│       └── danger_zone.py
│
├── contracts/                      # 7 файлів — SSOT + DTO
│   ├── __init__.py
│   ├── normalized_reject_reasons.py# ← normalized_reject_reasons.py  (NRR SSOT)
│   ├── why_codes.py                # ← why_codes.py (re-export shim)
│   ├── schemas.py                  # ← schemas.py
│   ├── schemas_decision_blocked.py # ← schemas_decision_blocked.py
│   ├── boundary_models.py          # ← boundary_models.py
│   ├── boundary_mappers.py         # ← boundary_mappers.py
│   ├── core_models.py              # ← core_models.py
│   └── domain_dict.json            # ← domain_dict.json
│
├── observability/                  # 2 файли
│   ├── __init__.py
│   ├── log_adapter.py              # ← dm_log_adapter.py
│   └── dashboard.py                # ← dashboard.py
│
└── docs/                           # без змін
```

#### A.2 Мапа переміщень (файл → новий шлях)

Повна 74-рядкова таблиця — у файлі [tools/migrations/dm_move_map.csv](tools/migrations/dm_move_map.csv)
(створюється на кроці §12). Стисла зведена таблиця за осями:

| Вісь | Файлів | Куди |
| --- | ---: | --- |
| core | 7 | `decision_making/core/` |
| gateway | 3 | `decision_making/gateway/` |
| gates | 14 (+1 до видалення) | `decision_making/gates/` |
| intent | 9 + schemas/ | `decision_making/intent/` |
| strategies/aurora | 7 | `decision_making/strategies/aurora/` |
| strategies/mean_reversion | 2 | `decision_making/strategies/mean_reversion/` |
| strategies/md_amr | 2 | `decision_making/strategies/md_amr/` |
| strategies (bridge) | 1 | `decision_making/strategies/` |
| primitives | 7 + shields(5) | `decision_making/primitives/` |
| contracts | 7 + domain_dict.json | `decision_making/contracts/` |
| observability | 2 | `decision_making/observability/` |

#### A.3 Правила видимості (guardrails)

- `core/*` **НЕ імпортує** з `strategies/*`, `aurora_*`, `md_amr_*`, `mean_reversion_*`.
- `gates/*` **НЕ імпортує** з `strategies/*`, `intent/builder*`, `intent/emitter*`.
- `intent/*` **НЕ імпортує** з `strategies/*`, `gates/*` (крім `gate_protocol`).
- `primitives/*` **НЕ імпортує** з `core/`, `gates/`, `intent/`, `strategies/`.
- `contracts/*` — листковий шар, імпортує тільки `vfoundation/*`.
- `strategies/*/handler.py` може імпортувати `primitives/`, `contracts/`, `gates/` (через protocol), `intent/emitter`, але НЕ з `core/facade`.

Ці правила перевіряються guardrail-тестом (див. §12.5).

**Переваги**
- Нульовий runtime-контрактний ризик (це перейменування імпортів).
- Моментальне зниження когнітивної маси: кожен підпакет ≤6–10 файлів.
- `__init__.py` стає вузьким і вичищеним від residue.
- Guardrail-тести на "хто що імпортує" стають простими (межа "core не імпортує strategies").

**Недоліки / ризики**
- Великий diff (74 переіменувань).
- `verb_registry_v1.yaml` все ще бачить `owner: decision_making` — ок, але
  потрібен `from apps.reference.domains.decision_making import ...` shim ≥ на
  один реліз для `DecisionMaking`, `NormalizedRejectReasons`, `DecisionBlockedPayload`,
  `DecisionLog`, `WhyCode` — вже експортованих з `__init__.py`.
- Зовнішні імпорти в `objective_engine`, `alpha_search`, `shared/types`,
  `execution_position`, `contracts/quadratic_rollout` мають оновитись або
  працювати через backward-compat shims.

### Варіант B — Декомпозиція на незалежні домени (цільова архітектура)

Після Варіанту A, розвести **природу D** і **природу E** у свої реальні домени.

#### B.1 Цільовий скелет

```
apps/reference/
├── domains/
│   ├── decision_making/              # ТОНКЕ ЯДРО (~25 файлів / ~5 500 LOC)
│   │   ├── __init__.py               # narrow re-exports (DecisionMaking, NRR, schemas)
│   │   ├── core/                     # 7 файлів (без змін з Варіанту A)
│   │   ├── gateway/                  # 3 файли
│   │   ├── gates/                    # 14 файлів
│   │   ├── intent/                   # 9 + schemas/
│   │   ├── contracts/                # 7 + domain_dict.json (NRR, WhyCode, schemas)
│   │   ├── observability/            # 2 файли
│   │   └── docs/
│   │
│   └── strategies/                   # ПЕРЕНЕСЕНО СЮДИ
│       ├── __init__.py
│       ├── registry.py               # (існує)
│       ├── plugins/                  # (існує) — тонкий plugin surface
│       │   ├── aurora_builtin.py
│       │   ├── mean_reversion.py
│       │   └── md_amr.py
│       └── runtimes/                 # НОВЕ: 12 файлів ← з decision_making/strategies/
│           ├── __init__.py
│           ├── bridge.py             # ← strategy_bridge.py
│           ├── aurora/
│           │   ├── __init__.py
│           │   ├── handler.py
│           │   ├── decision.py
│           │   ├── tpsl.py
│           │   ├── scoring_helpers.py
│           │   ├── holding_period.py
│           │   ├── config_loader.py
│           │   └── policy.py
│           ├── mean_reversion/
│           │   ├── __init__.py
│           │   ├── handler.py
│           │   └── logger.py
│           └── md_amr/
│               ├── __init__.py
│               ├── handler.py
│               └── entry_anchor_artifact.py
│
└── shared/
    ├── types.py                      # (існує)
    └── decision_primitives/          # НОВЕ: 12 файлів ← з decision_making/primitives/
        ├── __init__.py
        ├── scoring_kernel.py
        ├── math_kernel.py            # ← aurora_math.py (знеіменізовано)
        ├── entry_plan.py
        ├── exit_manager.py
        ├── tpsl_owner.py
        ├── sizing_margin_first.py
        ├── instrument_quantizer.py
        └── shields/
            ├── __init__.py
            ├── base.py
            ├── null_shield.py
            ├── context_shield.py
            ├── memory_shield.py
            └── danger_zone.py
```

#### B.2 Що міняється у зовнішніх споживачах

| Споживач | Було | Стане |
| --- | --- | --- |
| `apps/reference/domains/strategies/plugins/aurora_builtin.py` | `from apps.reference.domains.decision_making.aurora_handler import AuroraHandler` | `from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler` |
| `apps/reference/domains/strategies/plugins/mean_reversion.py` | `from apps.reference.domains.decision_making.mean_reversion_handler ...` | `from apps.reference.domains.strategies.runtimes.mean_reversion.handler ...` |
| `apps/reference/domains/strategies/plugins/md_amr.py` | `from apps.reference.domains.decision_making.md_amr_handler ...` | `from apps.reference.domains.strategies.runtimes.md_amr.handler ...` |
| `apps/reference/domains/alpha_search/models/aurora_adapter.py` | `from apps.reference.domains.decision_making.quadratic_scoring_kernel ...` | `from apps.reference.shared.decision_primitives.scoring_kernel ...` |
| `apps/reference/domains/objective_engine/adapters.py` | `from apps.reference.domains.decision_making.entry_plan ...` / `position_queries` | `from apps.reference.shared.decision_primitives.entry_plan ...` / лишити `position_queries` в DM |
| `apps/reference/contracts/quadratic_rollout.py` | `from apps.reference.domains.decision_making.quadratic_scoring_kernel ...` | `from apps.reference.shared.decision_primitives.scoring_kernel ...` |
| `apps/reference/shared/types.py` | `from apps.reference.domains.decision_making.normalized_reject_reasons ...` | залишається (NRR — SSOT DM) — **або** перенести NRR в `shared/` (решення §B.3) |
| `apps/reference/domains/execution_position/trade_intent_reject_contracts.py` | `from apps.reference.domains.decision_making.normalized_reject_reasons ...` | залишається (див. §B.3) |

#### B.3 Відкрите рішення: де жити NRR і WhyCode

Два варіанти:
1. **Залишити у `decision_making/contracts/`** — бо DM є емітером usage; зовнішні модулі
   продовжують читати звідти. Менший blast radius.
2. **Перенести в `vfoundation/core/`** (як вже зроблено з WhyCode) — бо `normalized_reject_reasons.py`
   використовується і з `execution_position/`, і з `shared/types.py`. Це усуне дворівневий
   SSOT "decision_making власник, всі читають".

**Рекомендація**: (1) у Варіанті B; (2) — як окремий ізольований Пакет 4 після.

#### B.4 Зміни в registry і guardrails

- `apps/reference/dictionaries/verb_registry_v1.yaml`:
  - `STRATEGY_SIGNAL_PRODUCED`, `STRATEGY_DECISION_BLOCKED` → `owner: strategies`
  - `TRADE_INTENT_REJECTED` strategy-path → або multi-owner, або єдиний owner `decision_making` (якщо reject shaping уніфікований у Пакеті 1).
- `apps/reference/domains/decision_making/contracts/domain_dict.json` — чистити стратегічні verb-и.
- `tests/domains/decision_making/test_fe_dm_boundary_guardrails.py`:
  - додати правило "DM production code MUST NOT import from strategies.runtimes";
  - `strategy_bridge`-check переноситься в `tests/domains/strategies/`.
- `tests/domains/decision_making/test_task32_dm_no_hardcoded_strategy_imports.py` — лишити, але оновити цільові модулі.

Після цього **`decision_making`** скорочується орієнтовно до **≤25 файлів / ≤5 500 LOC**
(ядро + gates + intent + contracts), що точно відповідає його декларованій ролі.

| Категорія | До | Після (B) |
| --- | ---: | ---: |
| Файлів | 74 | ~25 (DM) + ~30 (strategies/runtimes) + ~15 (shared/decision_primitives) |
| LOC в DM | 20 629 | ~5 500 |
| Макс. файл | 2 459 | `strategy_gateway.py` 706 |

**Переваги**
- DM стає справжнім "Decision Core", зрозумілим для нового інженера за години, а не дні.
- Стратегії стають first-class громадянами `strategies/` поруч із plugins-поверхнею,
  що вже їх активує (`apps/reference/domains/strategies/plugins/*.py:7`).
- Numeric примітиви стають явно shared (більше не "DM тягне до alpha_search").
- `verb_registry_v1.yaml` owner дозволяє uniformly перевести strategy-emitted verbs
  (`STRATEGY_SIGNAL_PRODUCED`, `STRATEGY_DECISION_BLOCKED`, `TRADE_INTENT_REJECTED` strat-path) на
  `owner: strategies/<name>`.

**Недоліки / ризики**
- Великий blast radius по імпортах (десятки зовнішніх файлів).
- Потрібна узгоджена зміна `verb_registry_v1.yaml`, `domain_dict.json`, guardrail-тестів
  (`test_fe_dm_boundary_guardrails.py`, `test_task32_dm_no_hardcoded_strategy_imports.py`).
- Ризик циклічних імпортів: `scoring_kernel` → `aurora_math` → `aurora_policy`; shields → memory; handlers ↔ entry_plan. Потребує dependency-graph санітизації *перед* move.
- Потрібне підтвердження SSOT-aggregator (`apps/reference/config/domains/_aggregator.py`)
  продовжує коректно бачити `DecisionMakingDomainConfig`.

## 8. Рекомендація

**Так, складність можна суттєво знизити БЕЗ втрати якості та ефективності.**
Рекомендована послідовність з 3 пакетів, кожен самодостатній і відкатний:

### Пакет 1 — Contract cleanup (блокер для будь-якого move)
Виконати `DECISION_MAKING_CLEANUP_PLAN.md` Package A+C:
- зафіксувати `ALPHA_SCORE_CALCULATED` (dual-owner або rename),
- зареєструвати або видалити `QUADRATIC_DECISION_TRACE`,
- реалізувати або видалити `HANDLER_READINESS_DIAGNOSTICS`,
- видалити `DeferredIntentScheduler` і пов'язані експорти,
- замінити `DecisionMakingLogic` alias,
- звузити `__init__.py` до фактично потрібного.

Сам собою цей пакет уже знижує "опір змін" на ~20 %.

### Пакет 2 — Variant A (internal modularization)
Фізичне переміщення файлів усередині `decision_making/` у 6 підпакетів
(`core/`, `gates/`, `intent/`, `strategies/`, `primitives/`, `contracts/`, `observability/`)
+ backward-compat shims у `__init__.py` на ≥1 реліз. Без змін contracts/runtime.
Додати guardrail-тест: `core/*` не має імпортувати з `strategies/*`.

### Пакет 3 — Variant B (фізичний domain split)
- `strategies/runtimes/` (aurora, mean_reversion, md_amr + strategy_bridge) → `apps/reference/domains/strategies/runtimes/`;
- `shared/decision_primitives/` (quadratic_scoring_kernel + aurora_math + aurora_policy + shields + entry_plan + exit_manager + tpsl_owner + sizing_margin_first + instrument_quantizer) → `apps/reference/shared/decision_primitives/`;
- оновити `verb_registry_v1.yaml` owner-и для stratery-emitted verbs;
- оновити `domain_dict.json` до проявленої runtime-truth.

Пакет 3 має йти **тільки після** закриття 22 red-тестів з Package 3 final
(зокрема Aurora fixture drift, TPSL fallback guardrail, regime_layering_contract).

---

## 9. Відповідь на конкретні питання запиту

| Питання | Відповідь |
| --- | --- |
| Чи можна зменшити складність без втрати якості та ефективності? | **Так.** Через bounded decomposition (Пакети 1→2→3). Якість зросте (чіткі межі, уніфікація reject-truth). Ефективність не змінюється (це в основному статичні межі коду, hot-path не зачіпається). |
| Чи домен перероздутий? | **Так, кількісно і за змістом.** 20 629 LOC / 74 файли / 6 осей відповідальностей. |
| Чи перебільшена складність в реалізації? | **Частково.** Ядро (facade + gate chain + intent) — пропорційне. Перебільшення — в mixin-"богу" `AuroraHandler`, 4 shaping-шляхах для одного verb-а, і tombstoned residue. |
| Чи переріс свою роль? | **Так.** Runtime-truth: хостить 1 core + 3 strategy-runtime-и + math ядро, тоді як декларована роль — лише "central decision engine". |
| Чи можна розділити на декілька незалежних доменів? | **Так, безпечно і з користю** — через Варіант B (strategies/runtimes + shared/decision_primitives + тонкий decision_making). Але тільки після Пакетів 1 і 2 і закриття 22 P3 reds. |

---

## 10. UNKNOWNS / обмеження цього аудиту

- Без live/replay прогонів: це структурний аудит, не продуктивний. Hot-path impact
  будь-якого переміщення не виміряний, але в межах Python import-graph — нульовий.
- Не аналізувалися зовнішні консьюмери за межами цього workspace (можуть існувати
  імпорти з `alysha_core/`, `backtest_engine/`, `tools/`).
- Не робилося контракт-diff між `verb_registry_v1.yaml` і всіма emission-точками —
  аудит спирається на вже існуючий `DECISION_MAKING_CONTRADICTION_MATRIX.md`.
- Оцінки LOC після розколу (~5 500 DM / ~30 strategies / ~15 shared) — приблизні, виведені
  з поточного inventory без врахування майбутніх shim-файлів.

## 11. Посилання

- [apps/reference/domains/decision_making/README.md](apps/reference/domains/decision_making/README.md)
- [DECISION_MAKING_SURFACE_MAP.md](DECISION_MAKING_SURFACE_MAP.md)
- [DECISION_MAKING_CONTRADICTION_MATRIX.md](DECISION_MAKING_CONTRADICTION_MATRIX.md)
- [DECISION_MAKING_LEGACY_DRIFT_AUDIT.md](DECISION_MAKING_LEGACY_DRIFT_AUDIT.md)
- [DECISION_MAKING_CLEANUP_PLAN.md](DECISION_MAKING_CLEANUP_PLAN.md)
- [apps/reference/dictionaries/verb_registry_v1.yaml](apps/reference/dictionaries/verb_registry_v1.yaml)
- [Copilot_Master_Roadmap.md](Copilot_Master_Roadmap.md)

---

## 12. Автоматизація міграції (скрипти)

**Коротка відповідь**: так, 85–90 % механічної роботи можна і треба автоматизувати.
Небезпечні ≤10 % — це:
- dynamic imports (`importlib.import_module("apps.reference.domains.decision_making...")`),
- string-based references у YAML/JSON/тестах,
- циклічні залежності, які тільки проявляться після розколу.
Їх треба ловити окремо статичним сканером (§12.2) і ручним рев'ю.

### 12.1 Архітектура інструментарію

Розмістити скрипти під `tools/migrations/dm_split/` — існуючий стиль репо для
bounded-міграцій.

```
tools/migrations/dm_split/
├── README.md
├── dm_move_map.csv                 # SSOT: source_path → target_path (74 рядки)
├── 01_collect_inventory.py         # inventory: всі .py у DM + LOC + імпортери
├── 02_build_rename_plan.py         # читає dm_move_map.csv → генерує rename_plan.json
│                                   # (old_module_fqn → new_module_fqn)
├── 03_audit_dynamic_imports.py     # шукає importlib / __import__ / string-based
│                                   # посилання на DM модулі у всьому repo
├── 04_rewrite_imports.py           # AST-based rewriter (libcst) по rename_plan.json
│                                   # cache-safe, idempotent, з dry-run
├── 05_move_files.py                # git mv за dm_move_map.csv; створює __init__.py
├── 06_write_shims.py               # генерує backward-compat shims у старих шляхах
├── 07_update_yaml_json.py          # оновлює verb_registry_v1.yaml, domain_dict.json,
│                                   # config/*.yaml string-based посилання
├── 08_verify.py                    # post-migration gate: import-resolve + cycles +
│                                   # guardrail-тести + pytest на focused subset
└── rollback.ps1                    # `git restore` по цільових шляхах
```

### 12.2 Аудит перед міграцією (`03_audit_dynamic_imports.py`)

Три класи ризикових посилань, які НЕ ловить AST-переписувач:

| Клас | Приклад | Інструмент |
| --- | --- | --- |
| Dynamic import | `importlib.import_module(f"apps.reference.domains.decision_making.{name}")` | regex `importlib\.(import_module\|__import__)` + `apps\.reference\.domains\.decision_making` |
| String у YAML/JSON | `owner: decision_making.aurora_handler` | `grep_search` по `*.yaml`/`*.json` |
| Pytest IDs / marker strings | `pytest.importorskip("apps.reference.domains.decision_making.deferred_scheduler")` | regex по `tests/**/*.py` |

Вихід скрипта — `tools/migrations/dm_split/audit_report.md` з рядком `BLOCKED:` якщо
знайдено ≥1 некерованих випадків.

### 12.3 Переписувач імпортів (`04_rewrite_imports.py`)

**Вибір технології**: `libcst` (Concrete Syntax Tree), а НЕ regex і НЕ `ast+unparse`.
Причини:
- `libcst` зберігає whitespace/коментарі/quote-style 1:1 → чистий diff;
- типобезпечні трансформери (`m.matches(node, m.ImportFrom(module=m.Attribute(...)))`);
- підтримує часткові імпорти (`from X import a, b as c`);
- вже вбудовано у pip-стек pytest-екосистеми, додається однією командою.

**Алгоритм**:
1. Читає `rename_plan.json` типу:
   ```json
   [
     {"old": "apps.reference.domains.decision_making.aurora_handler",
      "new": "apps.reference.domains.strategies.runtimes.aurora.handler"},
     {"old": "apps.reference.domains.decision_making.quadratic_scoring_kernel",
      "new": "apps.reference.shared.decision_primitives.scoring_kernel"}
   ]
   ```
2. Ходить по кожному `.py` файлу в `apps/`, `tests/`, `tools/`, `scripts/`,
   `backtest_engine/`, `alysha_core/`.
3. Для кожного `cst.ImportFrom` і `cst.Import`:
   - якщо `module.full_name` починається з `old` → замінює префікс на `new`;
   - зберігає alias-и, зірочкові імпорти, круглі дужки, trailing-коми.
4. Обробляє **relative imports усередині DM** (`from .foo import Bar`):
   - якщо файл теж переїжджає — перераховує `from ..parent.foo import Bar` згідно нового розташування;
   - для цього тримає `{old_abs_fqn: new_abs_fqn}` **і** віртуально резолвить relative → absolute перед replace.
5. Пропускає `noqa: PLC0415` локальні imports усередині функцій (вони теж `ImportFrom`, ловляться тим же матчером).
6. Idempotent: повторний прогін — no-op (перевіряє чи `old` ще присутній).
7. Має `--dry-run` + `--only=<glob>` + `--write-diff=diffs/` режими.

**Псевдокод ядра** (≈80 рядків, не імплементовано тут):

```python
import libcst as cst
import libcst.matchers as m

class ImportRewriter(cst.CSTTransformer):
    def __init__(self, plan: dict[str, str]) -> None:
        # longest prefix first, щоб не хапнути часткове співпадіння
        self.plan = sorted(plan.items(), key=lambda kv: -len(kv[0]))

    def _rewrite(self, dotted: str) -> str | None:
        for old, new in self.plan:
            if dotted == old or dotted.startswith(old + "."):
                return new + dotted[len(old):]
        return None

    def leave_ImportFrom(self, original, updated):
        if updated.module is None:  # relative import: обробляє окремий helper
            return updated
        dotted = _flatten_attribute(updated.module)
        new_dotted = self._rewrite(dotted)
        if new_dotted is None:
            return updated
        return updated.with_changes(module=_build_attribute(new_dotted))
```

### 12.4 Backward-compat shims (`06_write_shims.py`)

Для кожного модуля, який раніше був у публічному `__init__.py`, створити на старому
шляху файл-обгортку:

```python
# apps/reference/domains/decision_making/aurora_handler.py  (shim, deprecated)
"""Backward-compat shim. Removed target: apps.reference.domains.strategies.runtimes.aurora.handler"""
import warnings
warnings.warn(
    "apps.reference.domains.decision_making.aurora_handler is moved to "
    "apps.reference.domains.strategies.runtimes.aurora.handler",
    DeprecationWarning, stacklevel=2,
)
from apps.reference.domains.strategies.runtimes.aurora.handler import *  # noqa: F401,F403
from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler  # noqa: F401
```

Політика:
- Shim живе **один реліз**, потім видаляється.
- Shim-и створюються тільки для модулів, що були в попередньому `__init__.py`
  (`DecisionMaking`, `NormalizedRejectReasons`, `DecisionBlockedPayload`, `DecisionLog`,
  `WhyCode`, `MeanReversionHandler`) та для зовнішніх споживачів з §7.B `B.2`.
- Для внутрішніх модулів DM shim-и **не створюються** (імпортери перероблені AST-rewriter-ом).

### 12.5 Guardrail-тест видимості (`tests/domains/decision_making/test_layered_boundaries.py`)

Новий тест, запускається у Пакеті 2:

```python
LAYER_RULES = {
    "core":         {"forbid": ["strategies", "intent.builder", "intent.emitter"]},
    "gateway":      {"forbid": ["strategies"]},
    "gates":        {"forbid": ["strategies", "intent.builder", "intent.emitter"]},
    "intent":       {"forbid": ["strategies"]},
    "primitives":   {"forbid": ["core", "gates", "intent", "strategies"]},
    "contracts":    {"forbid": ["core", "gates", "intent", "strategies", "primitives"]},
    "observability":{"forbid": ["strategies"]},
}
```

Тест ходить по AST кожного `.py` і падає якщо знаходить forbidden-імпорт.
Це той самий стиль, що `test_fe_dm_boundary_guardrails.py`.

### 12.6 Послідовність запуску (runbook)

```powershell
# 0. Підготовка
python -m pip install libcst
git switch -c chore/dm-variant-a-move

# 1. Inventory + audit
python tools/migrations/dm_split/01_collect_inventory.py
python tools/migrations/dm_split/03_audit_dynamic_imports.py
# → якщо BLOCKED: виправити вручну і перезапустити

# 2. Plan
python tools/migrations/dm_split/02_build_rename_plan.py

# 3. Dry-run
python tools/migrations/dm_split/04_rewrite_imports.py --dry-run --write-diff=diffs/
# → перевірити diffs/, переконатися що нічого зайвого не чіпається

# 4. Move + rewrite
python tools/migrations/dm_split/05_move_files.py
python tools/migrations/dm_split/04_rewrite_imports.py
python tools/migrations/dm_split/06_write_shims.py
python tools/migrations/dm_split/07_update_yaml_json.py

# 5. Verify
python tools/migrations/dm_split/08_verify.py
pytest tests/domains/decision_making -q
pytest tests/ops/test_verb_registry_contracts.py -q
pytest -q  # повний прогін
```

### 12.7 Що зробить автоматика, а що — ручна робота

| Крок | Автоматика | Ручна робота |
| --- | :---: | --- |
| Створення підпапок і `__init__.py` | ✅ | — |
| `git mv` 74 файли | ✅ | — |
| Переписати всі `from apps.reference.domains.decision_making....` | ✅ | — |
| Переписати relative `from . / from ..` усередині DM | ✅ | — |
| Локальні (in-function) `noqa: PLC0415` imports | ✅ | — |
| Shim-файли для публічного API | ✅ | — |
| YAML/JSON string refs (`verb_registry_v1.yaml`, `domain_dict.json`) | ✅ (whitelist) | окремі кастомні значення |
| `importlib.import_module(...)` з f-string | — | ⚠ ручний огляд |
| Розв'язання циклічних залежностей після розколу | — | ⚠ ручний рефакторинг |
| Оновлення docs/README | частково (посилання) | текстові описи вручну |
| Нові guardrail-тести шарів | — | написати один раз |
| Pytest failure triage (22 P3 reds залишаються) | — | ручний аналіз |

### 12.8 Критерії успіху міграції

Міграція вважається успішною тоді і тільки тоді, коли:

1. `python -c "import apps.reference.domains.decision_making"` не кидає.
2. `pytest tests/domains/decision_making tests/ops/test_verb_registry_contracts.py` —
   той самий roster pass/fail, що і до міграції (±0 reds).
3. `tests/domains/decision_making/test_layered_boundaries.py` зелений.
4. `grep -r "from apps.reference.domains.decision_making.aurora_handler"` знаходить лише
   1 файл — сам shim (нуль у Варіанті B після дропу shim).
5. Run на `DeprecationWarning: decision_making.X is moved to ...` не дає falsely
   викликів зі свого ж коду (ловиться як `-W error::DeprecationWarning` у pytest).
6. Diff imports не перевищує ~400 рядків у жодному окремому not-DM файлі (інакше —
   підозра, що rewriter зачепив щось зайве).

### 12.9 Послідовність пакетів (з §8 + автоматика)

| Пакет | Ручна частина | Автоматика з §12 |
| --- | --- | --- |
| 1. Contract cleanup | Так (вирішення 4 дрейфів, NRR-060/061, residue) | `03_audit_dynamic_imports.py` для пошуку мертвих посилань |
| 2. Variant A (internal) | Guardrail-тест (§12.5), огляд diff | Повний runbook §12.6 |
| 3. Variant B (split) | NRR location рішення (§B.3), registry owner-updates, зовнішні споживачі (§B.2) | Повний runbook §12.6 з оновленим `dm_move_map.csv` |
| 4 (опційно). NRR/WhyCode → `vfoundation` | Рішення per-consumer | Той же rewriter, вузький plan |

**Оцінка обсягу коду rewriter-а**: ≈200–300 LOC Python (libcst), ще ~150 LOC на
orchestrator-скрипти 01–08. Це 1 PR розміром зі звичайний tool, не архітектурний bid.
