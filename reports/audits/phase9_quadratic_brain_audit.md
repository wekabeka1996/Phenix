# Aurora Phase 9 Audit — Quadratic Brain Forensic Review

Дата аудиту: 2026-02-14
Область: Pillars → Quadratic Core → Shields → Money Management → Execution Protocols
Метод: contract-first (config/model → runtime usage → tests)

## 1. Executive Summary

- **Загальний вердикт:** **`Hybrid conflict risk`**. Phase 9 артефакти додані, але повний production-ланцюг не є clean replacement.
- **P0:** Pillars не вбудовані в runtime-емісію FE (`features` не містить `pillar_sum`/`pillar_contribs`), а Quadratic kernel fail-closed без `pillar_sum`. Доказ: `apps/reference/domains/feature_engineering/feature_engineering.py:801`, `apps/reference/domains/decision_making/quadratic_scoring_kernel.py:128`.
- **P0:** Контракт H4/D1 для Pillars конфліктує з моделлю таймфреймів (`enabled_timeframes_sec` обмежено `<=3600`), тому H4=14400/D1=86400 неможливі як штатні TF. Доказ: `apps/reference/config_models.py:2121`, `config/aurora/domains.yaml:123`, `config/aurora/domains.yaml:318`.
- **P0:** MemoryShield неконсистентний з BaseShield (абстрактні `name/evaluate` не імплементовані) і ламає shield unit tests. Доказ: `apps/reference/domains/decision_making/shields/base.py:48`, `apps/reference/domains/decision_making/shields/memory_shield.py:10`; test fail у `tests/test_shield_system.py:100`.
- **P0:** Danger zone в handler визначається по `"DANGER_ZONE"`, але DangerShield повертає причини з префіксом `"DANGER:"`; логіка danger в Exit/Gate фактично не активується як задумано. Доказ: `apps/reference/domains/decision_making/aurora_handler.py:1155`, `apps/reference/domains/decision_making/shields/danger_zone.py:70`.
- **P1:** Money management (risk-based sizing) існує як моделі/утиліти, але в runtime gateway реально працює margin-first sizing. Доказ: `apps/reference/config_models.py:1194`, `apps/reference/domains/decision_making/decision_making.py:2571`.
- **P1:** Execution/Exit у Strategy DecisionConfig відсутні в SSOT Aurora YAML; handler мовчки підставляє дефолтні `ExecutionGateConfig/ExitManagerConfig`. Доказ: `config/aurora/strategies/aurora.yaml:30`, `apps/reference/domains/decision_making/aurora_handler.py:360`.
- **P1:** Legacy/fallback шари ще активні (legacy config path, legacy TP/SL fallback, strategy gateway після handler), тому стара логіка не є повністю відключеною. Доказ: `apps/reference/domains/decision_making/aurora_handler.py:251`, `apps/reference/domains/decision_making/aurora_handler.py:2310`, `apps/reference/domains/decision_making/decision_making.py:392`.
- **P2:** Реєстри/словники частково розсинхронені з runtime emit/listen (особливо domain_dict vs global registry).

## 2. System Map (config → model → code)

| Config поле | Pydantic модель | Runtime usage | Статус |
|---|---|---|---|
| `domains.feature_engineering.pillars.*` (`config/aurora/domains.yaml:321`) | `FeatureEngineeringDomainConfig.pillars` (`apps/reference/config_models.py:2204`) + `PillarsConfig` (`apps/reference/config_models.py:1993`) | Обчислення є в `CalculationEngine.compute_pillars` (`apps/reference/domains/feature_engineering/calculation_engine.py:1193`), але FE emit path не додає у `features` (`apps/reference/domains/feature_engineering/feature_engineering.py:801`) | **NOT WIRED** |
| `domains.feature_engineering.enabled_timeframes_sec` (`config/aurora/domains.yaml:123`) | `FeatureEngineeringDomainConfig.enabled_timeframes_sec` (`apps/reference/config_models.py:2116`) | Валідатор дозволяє тільки 60..3600 (`apps/reference/config_models.py:2121`) | **CONTRACT CONFLICT** з H4/D1 |
| `strategies.aurora.decision.scoring_version` (`config/aurora/strategies/aurora.yaml:95`) | `DecisionConfig.scoring_version` (`apps/reference/config_models.py:677`) | Routing у handler: `quadratic` → `QuadraticScoringKernel` (`apps/reference/domains/decision_making/aurora_handler.py:273`) | **ACTIVE FLAG**, зараз `v2` |
| `strategies.aurora.decision.scoring_engine` (відсутнє в YAML) | `DecisionConfig.scoring_engine` (`apps/reference/config_models.py:684`) + `ScoringEngineConfig` (`apps/reference/config_models.py:2076`) | Читається у `_scoring_engine_cfg` (`apps/reference/domains/decision_making/aurora_handler.py:276`), shield cascade будується (`apps/reference/domains/decision_making/aurora_handler.py:2046`) | **MISSING IN SSOT** |
| `scoring_engine.context_shield/memory_shield/danger_zone_shield` | `ContextShieldConfig` (`apps/reference/config_models.py:2008`), `MemoryShieldConfig` (`apps/reference/config_models.py:2032`), `DangerZoneShieldConfig` (`apps/reference/config_models.py:2057`) | Реалізації: `context_shield.py`, `memory_shield.py`, `danger_zone.py`; каскад `ShieldCascade` (`apps/reference/domains/decision_making/shields/base.py:85`) | **PARTIAL/BROKEN (Memory)** |
| `domains.decision_making.entry_plan` (`config/aurora/domains.yaml:17`) | `DecisionMakingDomainConfig.entry_plan` required (`apps/reference/config_models.py:1388`) | Використовується в strategy gateway fallback (`apps/reference/domains/decision_making/decision_making.py:1108`) | **USED (gateway)** |
| `strategies.aurora.decision.entry_plan` (відсутнє в YAML) | `DecisionConfig.entry_plan` optional (`apps/reference/config_models.py:699`) | Використовується в AuroraHandler (`apps/reference/domains/decision_making/aurora_handler.py:364`); якщо відсутнє → warning (`apps/reference/domains/decision_making/aurora_handler.py:387`) | **MISSING IN SSOT** |
| `strategies.aurora.decision.money_management` (відсутнє) | `DecisionConfig.money_management` (`apps/reference/config_models.py:702`) + `MoneyManagementConfig` (`apps/reference/config_models.py:1194`) | Runtime usage відсутній (нема викликів з handler/gateway) | **DECLARED, NOT INTEGRATED** |
| `strategies.aurora.decision.execution/exit` (відсутні) | `DecisionConfig.execution` (`apps/reference/config_models.py:708`), `DecisionConfig.exit` (`apps/reference/config_models.py:712`) | Handler підставляє дефолти: `ExecutionGateConfig()` / `ExitManagerConfig()` (`apps/reference/domains/decision_making/aurora_handler.py:360`) | **FAIL-OPEN DEFAULTING** |

Додатково:
- Compatibility fallback може тихо видалити `domains.feature_engineering.pillars` при валідації: `apps/reference/config_loader.py:1091`.

## 3. Phase 1–5 Evidence

### Phase 1 — Pillars

- **Файли:**
  - `apps/reference/domains/feature_engineering/pillar_indicators.py`
  - `apps/reference/domains/feature_engineering/pillar_backfill.py`
  - `apps/reference/domains/feature_engineering/calculation_engine.py`
  - `apps/reference/domains/feature_engineering/feature_engineering.py`
- **Public API:**
  - `compute_tactician/compute_operator/compute_strategist/aggregate_pillars` (`pillar_indicators.py:82`, `:256`, `:316`, `:356`).
  - `update_pillar_candle/compute_pillars` (`calculation_engine.py:1159`, `:1193`).
  - `PillarBackfillService.warmup_pillars` (`pillar_backfill.py:206`).
- **Інваріанти/контракти:**
  - Нормалізація через `tanh` у `[-1,1]`: `pillar_indicators.py:26`.
  - `aggregate_pillars` повертає `None`, якщо будь-який pillar `None`: `pillar_indicators.py:379`.
- **Інтеграція:**
  - FE runtime формує `features` без pillar-ключів: `feature_engineering.py:801`.
  - Payload `EVT:FEATURES_CALCULATED` містить `features`, `warmup`, `price_motion`, але не `pillar_sum`: `feature_engineering.py:1176`.
  - Викликів `update_pillar_candle/compute_pillars` у runtime path не знайдено (тільки дефініції).
- **Тести:**
  - `tests/test_pillar_indicators.py` (формули/edge cases) — pass.
- **Ризики/edge cases:**
  - H4/D1 не можуть бути штатно в `enabled_timeframes_sec` через validator `<=3600`.
  - `aggregate_pillars` має silent defaults по вагах (`pillar_indicators.py:382`), не strict fail-closed.

### Phase 2 — Quadratic Core

- **Файли:**
  - `apps/reference/domains/decision_making/quadratic_scoring_kernel.py`
  - `apps/reference/domains/decision_making/aurora_handler.py` (routing)
- **Public API:**
  - `QuadraticScoringKernel.compute(...)` (`quadratic_scoring_kernel.py:84`).
- **Інваріанти/контракти:**
  - Fail-closed якщо `pillar_sum` відсутній/invalid/NaN: `quadratic_scoring_kernel.py:128`, `:137`, `:141`.
  - Формула: `sign(Σ)*Σ²`, далі shield multiplier: `quadratic_scoring_kernel.py:148`, `:155`.
- **Інтеграція:**
  - Handler перемикається на quadratic тільки при `scoring_version == "quadratic"`: `aurora_handler.py:273`.
  - Поточний SSOT: `scoring_version: v2`: `config/aurora/strategies/aurora.yaml:95`.
- **Тести:**
  - `tests/test_quadratic_scoring_kernel.py` — pass.
- **Ризики/edge cases:**
  - FE не подає `pillar_sum` в `features` (`feature_engineering.py:801`), тому при ввімкненні quadratic буде масовий defer.
  - `ScoringEngineConfig.exposure_cap/min_pillar_confidence` моделюються, але не застосовані в kernel path.

### Phase 3 — Shields

- **Файли:**
  - `apps/reference/domains/decision_making/shields/base.py`
  - `apps/reference/domains/decision_making/shields/context_shield.py`
  - `apps/reference/domains/decision_making/shields/memory_shield.py`
  - `apps/reference/domains/decision_making/shields/danger_zone.py`
  - integration у `aurora_handler.py` (`_build_shield_cascade`)
- **Public API:**
  - `BaseShield.evaluate(...)` + call adapter (`base.py:55`, `:65`).
  - `ShieldCascade.evaluate(...)` (`base.py:104`).
- **Інваріанти/контракти:**
  - Множники clamp `[0,1]` у Base/Cascade: `base.py:75`, `:117`.
- **Інтеграція:**
  - Побудова cascade: `aurora_handler.py:2046`.
  - `DangerZoneShield` читає `volatility_state`, `spread_bps`, `price_motion_norm`: `danger_zone.py:64`, `:81`, `:98`.
- **Тести:**
  - `tests/test_shield_system.py` — **fail** (MemoryShield неінстанційовний).
- **Ризики/edge cases:**
  - `MemoryShield` не реалізує абстрактні `name/evaluate` (див. `base.py:48`, `memory_shield.py:10`) → TypeError при інстанціюванні.
  - Danger reasons mismatch: shield пише `DANGER:*` (`danger_zone.py:70`), handler шукає `DANGER_ZONE` (`aurora_handler.py:1155`).

### Phase 4 — Money Management / EntryPlan

- **Файли:**
  - `apps/reference/domains/decision_making/instrument_quantizer.py`
  - `apps/reference/domains/decision_making/sizing_margin_first.py`
  - `apps/reference/domains/decision_making/entry_plan.py`
- **Public API:**
  - `quantize_exposure`, `compute_risk_adjusted_notional` (`instrument_quantizer.py:76`, `:165`).
  - `compute_notional_target`, `compute_exposure_based_qty` (`sizing_margin_first.py:28`, `:89`).
  - `EntryPlan.compute` (`entry_plan.py:156`).
- **Інваріанти/контракти:**
  - EntryPlan validation fail-closed (`entry_plan.py:116`).
  - Dynamic structural stop у EntryPlan (`entry_plan.py:260`).
- **Інтеграція:**
  - AuroraHandler використовує `decision.entry_plan` (strategy config): `aurora_handler.py:364`.
  - DecisionMaking gateway використовує `domains.decision_making.entry_plan` як fallback: `decision_making.py:1108`.
  - Реальний sizing у gateway — margin-first: `decision_making.py:2571`.
- **Тести:**
  - `tests/test_money_management.py` — pass.
  - `tests/integration/test_ep01_2_entry_plan.py` — pass.
- **Ризики/edge cases:**
  - Hardcoded emergency floor `ref*0.0001` у EntryPlan: `entry_plan.py:250`.
  - `money_management` поля моделі не підключені до runtime routing.

### Phase 5 — Execution Protocols

- **Файли:**
  - `apps/reference/domains/decision_making/execution_gate.py`
  - `apps/reference/domains/decision_making/exit_manager.py`
  - integration у `aurora_handler.py`
- **Public API:**
  - `ExecutionGate.check_entry(...)` (`execution_gate.py:25`).
  - `ExitManager.check_exit(...)` (`exit_manager.py:25`).
- **Інваріанти/контракти:**
  - Threshold gate працює по `final_score`: `execution_gate.py:75`.
  - Shield invariant check (`execution_gate.py:82`).
- **Інтеграція:**
  - Handler викликає ExitManager до gate (`aurora_handler.py:1009`).
  - Далі ExecutionGate (`aurora_handler.py:1180`).
- **Тести:**
  - `tests/test_execution_gate.py` — pass.
  - `tests/test_exit_manager.py` — pass.
- **Ризики/edge cases:**
  - `ExecutionGateConfig` за замовчуванням містить `LIQUIDITY` (`config_models.py:1259`), але `check_entry` не має цієї стадії.
  - Direction gate очікує `pillar_operator_trend/pillar_strategist_trend`, яких FE не емiтить (`execution_gate.py:137`, `feature_engineering.py:801`).

## 4. Formula & Logic Audit

### 4.1 Pillars

| Перевірка | Вердикт | Доказ |
|---|---|---|
| ROC(M15) формула + нормалізація `[-1,1]` | **OK** | `pillar_indicators.py:74`, `pillar_indicators.py:101` |
| LinReg slope + ADX: direction з slope, strength через ADX | **OK (частково)** | `pillar_indicators.py:153`, `pillar_indicators.py:290` |
| Комбінування collinearity-safe | **UNCLEAR** | Є тільки `raw = slope*(adx/50)`; окремого decorrelation механізму нема (`pillar_indicators.py:291`) |
| SMA200 startup/backfill/lookahead safety | **NOT OK (integration)** | Backfill service існує (`pillar_backfill.py:206`), але не інтегровано в FE runtime emit path (`feature_engineering.py:801`) |
| Multi-TF resampling без leakage/partial bar | **NOT OK** | TF validator блокує >3600 (`config_models.py:2121`), config має лише `[180,300,900]` (`domains.yaml:123`) |

### 4.2 Quadratic Core

| Перевірка | Вердикт | Доказ |
|---|---|---|
| `final = sign(sum)*sum^2*Π(shields)` | **OK** | `quadratic_scoring_kernel.py:148`, `:155`; cascade product `base.py:118` |
| Threshold до `final_score` | **OK** | `execution_gate.py:75`, handler передає `result.score` (`aurora_handler.py:1184`) |
| Ваги сумуються в 1.0 / fail-closed якщо ні | **NOT OK** | Модель прямо допускає non-1.0 (`config_models.py:1948`), strict check відсутній |
| Saturation `final_score` в `[-1,1]` | **NOT OK** | Явного clamp final exposure нема (`quadratic_scoring_kernel.py:155`) |

### 4.3 Shields

| Перевірка | Вердикт | Доказ |
|---|---|---|
| `0<=m<=1` інваріант | **OK (core)** | clamp у Base/Cascade/Quadratic (`base.py:75`, `base.py:117`, `quadratic_scoring_kernel.py:153`) |
| Context mapping regime→severity | **OK** | `context_shield.py:57` |
| Дублювання зі старим regime gating | **NOT OK (dup risk)** | ContextShield + regime threshold factor + allowlist/kill-switch (`context_shield.py:57`, `quadratic_scoring_kernel.py:190`, `aurora_handler.py:972`, `aurora_handler.py:1061`) |
| Memory state hash buckets + decay doctrine | **NOT OK** | Key лише `symbol:regime` (`memory_shield.py:56`), decay formula не використана, config `decay_rate` є (`config_models.py:2040`) |
| LIVE persistent / BACKTEST RAM-only reset | **UNCLEAR/NOT OK** | Є тільки ad-hoc `state_manager`/local dict (`memory_shield.py:30`, `:41`), lifecycle/reset контракту нема |
| Danger trigger baseline/fail-closed | **NOT OK** | Trigger тільки пороги по feature values (`danger_zone.py:64`, `:81`, `:98`), baseline ATR contract відсутній |
| Danger action: block OPEN, allow CLOSE/REDUCE | **NOT OK** | Hard veto блокує при danger активності (`execution_gate.py:108`), а forced-exit path проходить через той самий gate (`aurora_handler.py:1021`, `:1180`) |
| Tighten stops тільки при `PnL>0` | **NOT OK** | Перевірки PnL немає (`exit_manager.py:64`) |

### 4.4 Money Management / EntryPlan

| Перевірка | Вердикт | Доказ |
|---|---|---|
| `stop_dist = max(2*ATR, structural_swing_dist)` | **NOT OK** | Реалізовано іншу формулу dynamic ATR + bps floor (`entry_plan.py:260`, `:269`) |
| Risk-based qty `equity*risk_pct*|final_score|` | **NOT OK (runtime)** | Формула є в утиліті (`instrument_quantizer.py:198`), але gateway використовує margin-first (`decision_making.py:2571`) |
| Quantizer: min_qty/step/min_notional/tick_size | **OK (lib)** | `instrument_quantizer.py:36`, `:67`, `:143`, `:149` |
| Нема тихих констант | **NOT OK** | `ref*0.0001` fallback у EntryPlan (`entry_plan.py:250`), також safety floors у коді |

### 4.5 Execution Protocols

| Перевірка | Вердикт | Доказ |
|---|---|---|
| Stage0 hard veto (oracle/danger/missing critical) | **PARTIAL** | Є oracle/danger/entryplan (`execution_gate.py:107`), але не всі critical data checks |
| Direction/Conflict/Knife override | **PARTIAL/NOT OK** | Operator+Strategist conflict є (`execution_gate.py:152`), Knife логіка TODO (`execution_gate.py:176`) |
| Threshold по final_score | **OK** | `execution_gate.py:75` |
| Shield stage invariant + reason | **OK** | `execution_gate.py:82` |
| Structural мін R/R (fees) | **PARTIAL** | R/R є (`execution_gate.py:193`), fees не враховуються |
| Exit reversal hysteresis/band | **NOT OK** | Однопороговий check без band (`exit_manager.py:94`) |
| Time exit у секундах | **OK** | `exit_manager.py:90`, model `max_hold_time_sec` (`config_models.py:1278`) |
| Danger logic без panicky forced exit | **PARTIAL/NOT OK** | Можливий `CLOSE_POSITION` (`exit_manager.py:61`), і конфлікт з hard veto |

## 5. Conflict Map (Decision vs Execution)

### Виявлені дублювання

- **Warmup/readiness перевіряється двічі:**
  - AuroraHandler (`aurora_handler.py:751`)
  - DecisionMaking strategy gateway (`decision_making.py:1016`, `decision_making.py:2473`)
- **EntryPlan двічі:**
  - AuroraHandler compute (`aurora_handler.py:1158`)
  - DecisionMaking fallback compute (`decision_making.py:1099`)
- **Liquidity/gating множинно:**
  - AuroraHandler liquidity gate (`aurora_handler.py:821`)
  - Далі DecisionMaking gateway risk/QoS/exposure/TTL/warmup (`decision_making.py:554`, `:845`, `:901`, `:981`, `:1016`)

### Конфлікти дозволу/заборони

- Strategy може пройти AuroraHandler scoring/execution gate, але бути заблокованою downstream у DecisionMaking gateway.
- ExitManager може сформувати forced-exit side, але `ExecutionGate` може це заблокувати через hard-veto.

### Legacy/parallel path evidence

- DecisionMaking все ще слухає `EVT:STRATEGY_SIGNAL_PRODUCED`: `decision_making.py:392`.
- AuroraHandler має legacy-compatible гілку з дефолтами: `aurora_handler.py:251`.
- `_emit_signal` має legacy TP/SL fallback: `aurora_handler.py:2310`.
- Є dead helper `_shadow_compare_kernel` без call sites: `decision_making.py:1464`.
- Plugin декларує “legacy path removed”, але runtime лишається gateway-hybrid: `apps/reference/domains/strategies/plugins/aurora_builtin.py:27`.

### Verdict

**`Hybrid conflict risk`** (не clean replacement і не повний wrapped-only, а активний змішаний контур).

## 6. Events & Registries Audit

### Нові/релевантні EVT/CMD у runtime

- `EVT:STRATEGY_DECISION_BLOCKED` emit: `aurora_handler.py:551`
- `EVT:STRATEGY_SIGNAL_PRODUCED` emit: `aurora_handler.py:2436`
- `EVT:STRATEGY_SIGNAL_PRODUCED` subscribe: `decision_making.py:392`
- `CMD:PROCESS_STRATEGY` emit: `feature_engineering.py:1341`
- `EVT:PROCESS_STRATEGY_BLOCKED` emit: `feature_engineering.py:1205`

### Реєстрація в словниках

- Global verb registry містить `EVT:STRATEGY_DECISION_BLOCKED` / `EVT:STRATEGY_SIGNAL_PRODUCED`: `apps/reference/dictionaries/verb_registry_v1.yaml:286`, `:292`.
- `CMD:PROCESS_STRATEGY` зареєстрований: `apps/reference/dictionaries/verb_registry_v1.yaml:16`.
- `decision_making/domain_dict.json` **не містить** `EVT:STRATEGY_*` у exports (тільки `TRADE_INTENT_PROPOSED`, `ALPHA_SCORE_CALCULATED`, `CMD:CLOSE`): `apps/reference/domains/decision_making/domain_dict.json:38`.
- `feature_engineering/domain_dict.json` **не містить** `CMD:PROCESS_STRATEGY`/`EVT:PROCESS_STRATEGY_BLOCKED`: `apps/reference/domains/feature_engineering/domain_dict.json:16`.

### Тестування подій/реєстрів

- Є контракти для `verb_registry_v1.yaml`: `tests/ops/test_verb_registry_contracts.py:25` (pass).
- `domain_dict` тести лише на JSON validity, не на semantic coverage emit/listen: `tests/vfoundation/test_dictionaries_valid.py:28`.

### Verdict

- `EVT:STRATEGY_SIGNAL_PRODUCED`, `EVT:STRATEGY_DECISION_BLOCKED`: **Registered (global) but domain-dictionary desynced**.
- `CMD:PROCESS_STRATEGY`: **All registered & tested** (global registry + tests).
- `EVT:PROCESS_STRATEGY_BLOCKED`: **Not registered (global/domain registry mismatch)**.

## 7. Test Coverage & Gaps

### Виконані команди і результати

1. `pytest -q tests/test_pillar_indicators.py tests/test_quadratic_scoring_kernel.py tests/test_shield_system.py tests/test_money_management.py tests/test_execution_gate.py tests/test_exit_manager.py`
- **FAIL**: `tests/test_shield_system.py` (5 failures) — `MemoryShield` abstract class instantiation error.

2. `pytest -q tests/test_pillar_indicators.py tests/test_quadratic_scoring_kernel.py tests/test_money_management.py tests/test_execution_gate.py tests/test_exit_manager.py`
- **PASS**: `96 passed`.

3. `pytest -q tests/domains/decision_making/test_aurora_handler.py`
- **PASS/SKIP**: `6 passed, 3 skipped`.

4. `pytest -q tests/integration/test_ep01_2_entry_plan.py`
- **PASS**: `22 passed`.

5. `pytest -q tests/integration/test_t2b07_e2e_tick_to_signal.py`
- **PASS**: `6 passed`.

6. `pytest -q tests/integration/test_e2e_decision_pipeline.py`
- **PASS**: `5 passed`.

7. `pytest -q tests/integration/test_strategy_aware_gates_integration.py`
- **PASS**: `10 passed`.

8. `pytest -q tests/e2e/test_e2e_bar_to_order_placement.py`
- **SKIP**: `14 skipped`.

9. `pytest -q tests/integration/test_features_full_chain_happy.py`
- **SKIP**: `1 skipped`.

10. `pytest -q tests/ops/test_verb_registry_contracts.py`
- **PASS**: `7 passed`.

### Покриття vs вимога E2E

- Unit-покриття формул Phase 1/2/4/5 є.
- Shield-покриття є, але зламане на MemoryShield API.
- Повний E2E Aurora chain з реальним Quadratic+Pillars+Shields+ExecutionGate у прод-режимі **не підтверджений** (частина релевантних E2E скіпнута; Quadratic у SSOT не активований).

## 8. Required Fixes (P0/P1/P2)

### P0 (блокери)

1. **Підключити Pillars у FE runtime emit path**
- У `FeatureEngineering._calculate_and_emit_features_for_tf` додати виклики `update_pillar_candle/compute_pillars` і емісію `features["pillar_sum"]`, `features["pillar_contribs"]`.
- Вирівняти readiness contract для pillar readiness.

2. **Зняти TF-конфлікт H4/D1**
- Переглянути validator `enabled_timeframes_sec` (`<=3600`) або ввести окремий канал для pillar TF (H4/D1) поза цим обмеженням.

3. **Виправити MemoryShield контракт**
- Реалізувати `name` та `evaluate` згідно `BaseShield`.
- Узгодити один API (не dual-style `check(...)` vs `evaluate(...)`).
- Зробити тест `tests/test_shield_system.py` зеленим.

4. **Виправити danger reason contract**
- Уніфікувати reason-коди між `DangerZoneShield` і `AuroraHandler` (`DANGER_ZONE_*` або інший єдиний формат).

### P1 (високий пріоритет)

1. **Прибрати silent defaults у critical config path**
- Для `decision.execution/decision.exit` прибрати `or ExecutionGateConfig()/ExitManagerConfig()` або зробити explicit fail-closed при відсутності.

2. **Вирівняти MoneyManagement runtime integration**
- Підключити `DecisionConfig.money_management` до фактичного sizing у gateway (або явно deprecate моделі/утиліти).

3. **Зняти подвійний EntryPlan compute**
- Визначити один SSOT для EntryPlan (strategy-level або domain-level) і прибрати дублювання handler/gateway.

4. **Direction gate data contract**
- Або емiтити `pillar_operator_trend/pillar_strategist_trend`, або переписати direction gate на наявні поля.

5. **ExecutionGate LIQUIDITY stage parity**
- Реалізувати LIQUIDITY stage або прибрати його з дефолтного `gates_enabled`.

### P2 (середній пріоритет)

1. **Registry/domain_dict синхронізація**
- Оновити `decision_making/domain_dict.json` і `feature_engineering/domain_dict.json` під фактичні emit/listen.
- Додати semantic tests на відповідність runtime emit/listen ↔ domain/global dictionaries.

2. **Legacy cleanup**
- Прибрати dead code (`_shadow_compare_kernel`) і legacy fallback гілки після міграції.
- Додати явні warning logs при legacy fallback-режимах.

3. **ExitManager hardening**
- Додати hysteresis/band для signal reversal.
- Додати guard `tighten stops only if unrealized PnL > 0`.

## 9. Appendix

### 9.1 Key snippets/paths (forensic anchors)

- Quadratic formula and shield multiply: `apps/reference/domains/decision_making/quadratic_scoring_kernel.py:148`, `apps/reference/domains/decision_making/quadratic_scoring_kernel.py:155`
- Quadratic requires pillar_sum: `apps/reference/domains/decision_making/quadratic_scoring_kernel.py:128`
- FE features map without pillars: `apps/reference/domains/feature_engineering/feature_engineering.py:801`
- Timeframe validator upper bound 3600: `apps/reference/config_models.py:2121`
- Pillars config expects H4/D1: `config/aurora/domains.yaml:318`
- Handler scoring routing flag: `apps/reference/domains/decision_making/aurora_handler.py:273`
- Current SSOT scoring version: `config/aurora/strategies/aurora.yaml:95`
- Execution/Exit defaulting in handler: `apps/reference/domains/decision_making/aurora_handler.py:360`
- Decision gateway still active: `apps/reference/domains/decision_making/decision_making.py:392`
- Legacy TP/SL fallback in emit: `apps/reference/domains/decision_making/aurora_handler.py:2310`
- MemoryShield abstract-contract mismatch anchor: `apps/reference/domains/decision_making/shields/base.py:48`, `apps/reference/domains/decision_making/shields/memory_shield.py:10`
- Danger reason mismatch anchor: `apps/reference/domains/decision_making/aurora_handler.py:1155`, `apps/reference/domains/decision_making/shields/danger_zone.py:70`

### 9.2 Checked files (основні)

- `config/aurora/domains.yaml`
- `config/aurora/strategies/aurora.yaml`
- `apps/reference/config_models.py`
- `apps/reference/config_loader.py`
- `apps/reference/domains/feature_engineering/feature_engineering.py`
- `apps/reference/domains/feature_engineering/calculation_engine.py`
- `apps/reference/domains/feature_engineering/pillar_indicators.py`
- `apps/reference/domains/feature_engineering/pillar_backfill.py`
- `apps/reference/domains/feature_engineering/types.py`
- `apps/reference/domains/decision_making/aurora_handler.py`
- `apps/reference/domains/decision_making/decision_making.py`
- `apps/reference/domains/decision_making/quadratic_scoring_kernel.py`
- `apps/reference/domains/decision_making/execution_gate.py`
- `apps/reference/domains/decision_making/exit_manager.py`
- `apps/reference/domains/decision_making/instrument_quantizer.py`
- `apps/reference/domains/decision_making/sizing_margin_first.py`
- `apps/reference/domains/decision_making/entry_plan.py`
- `apps/reference/domains/decision_making/shields/base.py`
- `apps/reference/domains/decision_making/shields/context_shield.py`
- `apps/reference/domains/decision_making/shields/memory_shield.py`
- `apps/reference/domains/decision_making/shields/danger_zone.py`
- `apps/reference/domains/decision_making/domain_dict.json`
- `apps/reference/domains/feature_engineering/domain_dict.json`
- `apps/reference/dictionaries/verb_registry_v1.yaml`
- `tests/test_pillar_indicators.py`
- `tests/test_quadratic_scoring_kernel.py`
- `tests/test_shield_system.py`
- `tests/test_money_management.py`
- `tests/test_execution_gate.py`
- `tests/test_exit_manager.py`
- `tests/integration/test_ep01_2_entry_plan.py`
- `tests/integration/test_t2b07_e2e_tick_to_signal.py`
- `tests/integration/test_e2e_decision_pipeline.py`
- `tests/integration/test_strategy_aware_gates_integration.py`
- `tests/e2e/test_e2e_bar_to_order_placement.py`
- `tests/ops/test_verb_registry_contracts.py`
- `tests/vfoundation/test_dictionaries_valid.py`

### 9.3 Changed files in this audit task

- `reports/audits/phase9_quadratic_brain_audit.md` (created)

