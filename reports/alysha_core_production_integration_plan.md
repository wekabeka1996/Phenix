# ALYSHA Core Production Integration Plan

## Scope

Цей документ не є планом "перетягнути `alysha_core` як є". Це план production-grade реалізації тих ідей `alysha_core`, які справді мають цінність для поточної Aurora/Phenix-системи:

- structured reward decomposition
- regime-adaptive weighting
- richer cost/risk accounting
- research-grade explainability, але в production-native формі

Цільовий runtime-контур:

- current branch як єдиний SSOT
- hybrid execution contour: live market data + testnet execution
- strict fail-closed schema/runtime contracts
- нуль неявних fallback-ів
- нуль hardcoded production coefficients у runtime-коді

Не-ціль:

- прямий runtime transplant `alysha_core/reward_engine_v3plus/*`
- пряме повернення RL/PPO bridge
- окремий паралельний decision owner
- дублювання поточного risk/execution ownership

## Evidence Base

План опирається на поточний код і на вже досліджений `alysha_core`.

Current Aurora evidence:

- [apps/reference/config_models.py](c:\Users\user\Music\Phenix\apps\reference\config_models.py)
- [apps/reference/domains/decision_making/aurora_scoring_kernel.py](c:\Users\user\Music\Phenix\apps\reference\domains\decision_making\aurora_scoring_kernel.py)
- [apps/reference/domains/decision_making/aurora_handler.py](c:\Users\user\Music\Phenix\apps\reference\domains\decision_making\aurora_handler.py)
- [apps/reference/domains/decision_making/strategy_gateway.py](c:\Users\user\Music\Phenix\apps\reference\domains\decision_making\strategy_gateway.py)
- [apps/reference/domains/decision_making/execution_gate.py](c:\Users\user\Music\Phenix\apps\reference\domains\decision_making\execution_gate.py)
- [apps/reference/domains/alpha_search/ensemble.py](c:\Users\user\Music\Phenix\apps\reference\domains\alpha_search\ensemble.py)
- [apps/reference/bootstrap/preflight.py](c:\Users\user\Music\Phenix\apps\reference\bootstrap\preflight.py)
- [apps/reference/domains/feature_engineering/regime_mapping.py](c:\Users\user\Music\Phenix\apps\reference\domains\feature_engineering\regime_mapping.py)

Current test contour evidence:

- [tests/config/test_decision_making_fail_closed.py](c:\Users\user\Music\Phenix\tests\config\test_decision_making_fail_closed.py)
- [tests/config/test_task28_hybrid_mode_config_contract.py](c:\Users\user\Music\Phenix\tests\config\test_task28_hybrid_mode_config_contract.py)
- [tests/config/test_llm_strategy_contract_fail_closed.py](c:\Users\user\Music\Phenix\tests\config\test_llm_strategy_contract_fail_closed.py)
- [tests/test_testnet_checks.py](c:\Users\user\Music\Phenix\tests\test_testnet_checks.py)
- [tests/simulation/test_strategy_primacy_e2e.py](c:\Users\user\Music\Phenix\tests\simulation\test_strategy_primacy_e2e.py)
- [tests/simulation/test_mean_reversion_simulation.py](c:\Users\user\Music\Phenix\tests\simulation\test_mean_reversion_simulation.py)
- [tests/simulation/test_strategy_aware_gates_simulation.py](c:\Users\user\Music\Phenix\tests\simulation\test_strategy_aware_gates_simulation.py)

Legacy source material:

- [alysha_core/reward_engine_v3plus/main_engine.py](c:\Users\user\Music\Phenix\alysha_core\reward_engine_v3plus\main_engine.py)
- [alysha_core/reward_engine_v3plus/data_types.py](c:\Users\user\Music\Phenix\alysha_core\reward_engine_v3plus\data_types.py)
- [alysha_core/reward_engine_v3plus/adaptive_weights_manager.py](c:\Users\user\Music\Phenix\alysha_core\reward_engine_v3plus\adaptive_weights_manager.py)
- [alysha_core/reward_engine_v3plus/xai_integration.py](c:\Users\user\Music\Phenix\alysha_core\reward_engine_v3plus\xai_integration.py)
- [alysha_core/reward_engine_v3plus/components](c:\Users\user\Music\Phenix\alysha_core\reward_engine_v3plus\components)

## Executive Summary

Висновок прямий:

`alysha_core` містить цінні ідеї, але не є готовим production runtime owner для поточної Aurora.

Правильна цільова реалізація:

1. Не переносити `alysha_core` у decision/execution як окремий engine-owner.
2. Реалізувати current-native `Objective Engine`, який:
   - не визначає side самостійно
   - не замінює risk/execution hard veto
   - модулює якість сигналу і додає richer diagnostics
   - дає realized trade-quality attribution для alpha-search і research feedback loop
3. Інтегрувати його в production path Aurora та `md_amr`, але з дуже жорсткими контрактами й повним hybrid/simulation acceptance контуром перед hard enforcement.

Що треба перенести з `alysha_core`:

- reward decomposition як objective decomposition
- regime-adaptive weighting як regime-conditioned quality weighting
- cost/risk accounting як pre-trade та post-trade quality accounting
- explainability як canonical objective trace в WAL/event payloads

Що не треба переносити в production path:

- PPO adapter
- RLX bridge
- exploration bonus
- policy-shaping у поточному вигляді
- target-trade-frequency behavior reward
- legacy `core.*` / `rlx.*` залежності

## Architectural Judgment

### Що намагався вирішити `alysha_core`

З математичної точки зору `alysha_core` намагався вирішити не одну проблему, а клас проблем, які майже завжди з'являються у trading/RL/research-системах:

- regime drift: те, що працює в одному режимі, деградує в іншому
- raw PnL myopia: модель може оптимізувати gross PnL і ігнорувати витрати, churn, execution drag
- weak risk awareness: гарний сигнал не дорівнює гарній угоді, якщо risk utilization або stop structure погані
- sparse feedback: сама кінцева PnL недостатня для розуміння, чому policy деградує
- poor explainability: без decomposition немає якісного post-mortem аналізу

### Чи ці проблеми існують у поточній Aurora

Так, але в іншій формі.

У current Aurora already є сильні сторони:

- deterministic signal score
- явний `ExecutionGate`
- strategy arbitration
- explicit risk/execution owners
- strict config validation
- `why_chain` / shield diagnostics

Але все ще лишаються системні gaps:

- недостатньо багатий quality accounting поверх самого signal score
- слабкий міст між pre-trade hypothesis і realized post-trade quality
- alpha-search ще не використовує повноцінний quality objective замість вузького performance proxy
- regime adaptation частково присутня, але не у формі canonical multi-component objective layer

Отже, цінність `alysha_core` для цього проекту є реальною, але не у вигляді raw transplant.

## Why Raw Transplant Is Wrong

Пряме вмонтування `alysha_core` в production runtime я не вважаю архітектурно коректним з таких причин:

1. Контрактний розрив.
   `alysha_core` очікує власні типи даних і RL-специфічні поля (`action_vector`, `prediction_vector`, `model_uncertainty`, `is_exploratory`), яких current Aurora live path не має як canonical contracts.

2. Regime taxonomy mismatch.
   `alysha_core` проектувався навколо іншої regime abstraction. Поточна Aurora має свою regime taxonomy, і вона вже deeply wired у strategy/risk logic.

3. Ownership conflict.
   Current Aurora вже має чітких owners:
   - strategy handler визначає direction
   - `ExecutionGate` і risk logic визначають hard veto
   - execution layers володіють order lifecycle

4. Математична неоднорідність.
   У `alysha_core` є цінні компоненти, але також є частини, де production correctness недостатньо доведений:
   - shaping formula не є беззаперечно policy-invariant у поданій формі
   - XAI пояснює не повністю той об'єкт, який реально агрегується
   - integration tests не доводять end-to-end correctness головної reward aggregation path

5. Dependency contamination.
   У поточному вигляді `alysha_core` залежить від `core.*`, `rlx.*` і старих допоміжних шарів, які не є canonical частиною current repo contracts.

## Target Production Design

### Core Principle

Production-реалізація має зберегти цей інваріант:

- direction owner залишається strategy kernel/handler
- objective owner оцінює quality та модулює aggressiveness / admissibility
- risk/execution owner зберігає hard veto
- execution layer не отримує другого незалежного policy owner

### Target Runtime Layers

1. `Strategy Direction Layer`
   Уже існує. Це Aurora kernel, `md_amr`, mean reversion та інші strategy handlers.

2. `Objective Engine`
   Новий current-native production subsystem.
   Завдання:
   - обчислити multi-component quality score
   - побудувати canonical breakdown
   - дати multiplier/gate result
   - емiтити explainability trace

3. `Risk and Execution Gate Layer`
   Уже існує. Hard veto не переноситься в objective engine.

4. `Realized Trade Quality Evaluator`
   Після закриття позиції будує realized decomposition і зберігає її як feedback signal.

5. `Alpha Search Adaptive Allocator`
   Використовує realized trade-quality metrics для regime-conditioned provider weighting.

## Mathematical Design

### 1. Pre-Trade Objective

Позначення:

- `D_t` — direction score від strategy kernel, `D_t ∈ [-1, 1]`
- `r_t` — current regime
- `s` — strategy id
- `z_t` — нормалізований component vector
- `w_{s,r}` — regime-conditioned weight vector для strategy `s`

Пропонована форма:

`O_t = Σ_i w_{s,r,i} * z_{t,i}`

де:

- `O_t ∈ [-1, 1]`
- `Σ_i |w_{s,r,i}| = 1`
- усі `w_{s,r,i}` задаються лише конфігом
- для кожного активного regime потрібен повний explicit weight block

Далі:

`M_t = clamp(1 + λ_{s,r} * O_t, m_min_{s,r}, m_max_{s,r})`

І:

`D*_t = D_t * M_t`

Інваріанти:

- `m_min_{s,r} > 0`, тому objective layer не перевертає sign direction score
- objective layer не може створити нову сторону, тільки attenuate/boost у межах policy
- `ExecutionGate` і risk logic працюють поверх `D*_t`, але hard veto залишаються окремими

### 2. Pre-Trade Components

#### `z_edge`

Мета: оцінити не просто sign signal, а чи має trade достатню структурну економіку.

Рекомендована форма:

- `rr_term = tanh((RR_expected - rr_neutral) / rr_scale)`
- `margin_term = tanh(score_margin / score_margin_scale)`
- `distance_term = tanh((tp_dist_atr - stop_dist_atr) / dist_scale)`

`z_edge = a1 * rr_term + a2 * margin_term + a3 * distance_term`

де:

- `RR_expected` рахується з `EntryPlan`
- `score_margin = |D_t| - threshold`
- `tp_dist_atr`, `stop_dist_atr` нормалізовані через ATR / current volatility scale

#### `z_cost`

Мета: penalize trades, де gross edge виглядає красиво, але execution drag його з'їсть.

Рекомендована форма:

- `cost_bps = fee_bps + expected_slippage_bps + spread_bps + funding_drag_bps`
- `edge_bps = projected_target_bps`
- `cost_ratio = cost_bps / max(edge_bps, edge_floor_bps)`
- `z_cost = -tanh((cost_ratio - cost_neutral) / cost_scale)`

Усі `edge_floor_bps`, `cost_neutral`, `cost_scale` мають бути explicit в config.

#### `z_risk`

Мета: карати не тільки за очевидний bad RR, а й за risk inefficiency.

Рекомендована форма:

- `risk_budget_headroom`
- `liquidation_buffer_score`
- `stop_efficiency_score`
- `exposure_pressure_score`

Наприклад:

`z_risk = b1 * tanh((headroom - headroom_neutral)/headroom_scale) + b2 * liq_buffer + b3 * stop_efficiency - b4 * exposure_pressure`

Компонент не дублює hard veto, а оцінює quality всередині допустимої області.

#### `z_information`

Мета: signal quality як функція повноти й надійності інформації.

Компоненти:

- readiness completeness
- regime confidence
- feature freshness
- model consensus / cross-signal agreement, якщо є

Приклад:

`z_information = c1 * readiness_ratio + c2 * regime_confidence + c3 * freshness_score + c4 * consensus_score`

#### `z_execution`

Мета: оцінити, наскільки trade executable без прихованого drag.

Компоненти:

- spread adequacy
- depth adequacy
- queue/fill feasibility
- signal age / entry staleness

Приклад:

`z_execution = d1 * depth_score - d2 * spread_penalty - d3 * age_penalty - d4 * queue_risk`

#### `z_behavior`

Тут важлива принципова зміна.

Я не рекомендую переносити RL-style "target trade frequency reward". Для production Aurora це надто непрозоро.

Натомість переносимо лише runtime-grounded discipline metrics:

- recent cancel/replace churn
- same-side supersede density
- re-entry churn
- blocked-intent density
- stale-intent generation rate

Тобто:

`z_behavior` має описувати discipline/anti-churn quality, а не штучно тягнути систему до цільової частоти угод.

### 3. Realized Trade Quality

Після закриття позиції рахується:

`Q_trade = Σ_j v_{s,r,j} * z_realized,j`

Де realized-компоненти:

- realized pnl efficiency
- realized cost drag
- realized MAE/MFE efficiency
- realized duration efficiency
- realized regime-path stability
- realized execution quality

Цей об'єкт потрібен для:

- alpha-search feedback
- strategy diagnostics
- live/testnet post-mortem
- calibrating regime weights

### 4. What Is Explicitly Not Ported

У production план не входять:

- `shaping.py` у поточному вигляді
- `ppo_adapter.py`
- `integration/rlx_bridge.py`
- exploration-related rewards
- модельні поля, яких у live contracts немає

## Proposed Aurora-Native Package Structure

Пропонована нова підсистема:

- [apps/reference/domains/objective_engine/__init__.py](c:\Users\user\Music\Phenix\apps\reference\domains\objective_engine\__init__.py)
- [apps/reference/domains/objective_engine/data_contracts.py](c:\Users\user\Music\Phenix\apps\reference\domains\objective_engine\data_contracts.py)
- [apps/reference/domains/objective_engine/regime_profiles.py](c:\Users\user\Music\Phenix\apps\reference\domains\objective_engine\regime_profiles.py)
- [apps/reference/domains/objective_engine/normalization.py](c:\Users\user\Music\Phenix\apps\reference\domains\objective_engine\normalization.py)
- [apps/reference/domains/objective_engine/pretrade_kernel.py](c:\Users\user\Music\Phenix\apps\reference\domains\objective_engine\pretrade_kernel.py)
- [apps/reference/domains/objective_engine/posttrade_evaluator.py](c:\Users\user\Music\Phenix\apps\reference\domains\objective_engine\posttrade_evaluator.py)
- [apps/reference/domains/objective_engine/explainability.py](c:\Users\user\Music\Phenix\apps\reference\domains\objective_engine\explainability.py)
- [apps/reference/domains/objective_engine/components/edge.py](c:\Users\user\Music\Phenix\apps\reference\domains\objective_engine\components\edge.py)
- [apps/reference/domains/objective_engine/components/cost.py](c:\Users\user\Music\Phenix\apps\reference\domains\objective_engine\components\cost.py)
- [apps/reference/domains/objective_engine/components/risk.py](c:\Users\user\Music\Phenix\apps\reference\domains\objective_engine\components\risk.py)
- [apps/reference/domains/objective_engine/components/information.py](c:\Users\user\Music\Phenix\apps\reference\domains\objective_engine\components\information.py)
- [apps/reference/domains/objective_engine/components/execution.py](c:\Users\user\Music\Phenix\apps\reference\domains\objective_engine\components\execution.py)
- [apps/reference/domains/objective_engine/components/behavior.py](c:\Users\user\Music\Phenix\apps\reference\domains\objective_engine\components\behavior.py)

Ключова вимога:

жоден із цих модулів не має імпортувати `alysha_core` runtime-напряму в production path.

`alysha_core` тут використовується як математичне джерело ідей, а не як SSOT-реалізація.

## Config and Schema Plan

### Shared Domain Config

У [apps/reference/config_models.py](c:\Users\user\Music\Phenix\apps\reference\config_models.py) потрібно додати:

- `ObjectiveEngineDomainConfig`
- `ObjectiveNormalizationConfig`
- `ObjectiveComponentConfig`
- `ObjectiveDataRequirementsConfig`
- `ObjectiveExplainabilityConfig`

SSOT path:

- `config/aurora/domains.yaml`

Що тут має жити:

- allowed component set
- component normalizers
- regime namespace contract
- data requirement flags
- explainability emission policy
- realized-trade accounting settings

### Strategy-Level Objective Config

У strategy profiles потрібно додати:

- `StrategyObjectiveConfig`
- `StrategyObjectiveRegimeProfile`
- `StrategyObjectiveGateConfig`
- `StrategyObjectiveMultiplierConfig`

SSOT paths:

- `config/aurora/strategies/aurora.yaml`
- `config/aurora/strategies/md_amr.yaml`
- згодом `config/aurora/strategies/mean_reversion.yaml`, якщо strategy буде підключена до objective layer

Що тут має жити:

- weights by regime
- per-regime multiplier parameters
- min objective thresholds
- enforcement mode
- enabled components

### Alpha Search Config

`alpha_search` не слід тягнути в `domains.yaml`.

SSOT:

- `config/alpha_search.yaml`

Потрібен новий config block типу:

- `alpha_search.objective_feedback`

Що там має бути:

- realized quality attribution window
- regime-conditioned provider reweighting config
- cost/risk-aware performance target

## No-Fallback / No-Hardcode Requirements

Це production-критично.

1. Для кожної активної strategy/regime пари потрібен explicit weight block.
2. Для кожного enabled component потрібні explicit normalizer params.
3. Для кожного enabled realized metric потрібні explicit coefficients.
4. Якщо required input відсутній, runtime:
   - або defer
   - або reject
   - але ніколи не підставляє неявне значення
5. Заборонені:
   - `or 0.0`
   - `or 1.0`
   - `DEFAULT` regime coefficients для active live path
   - hardcoded fee/slippage caps
   - implicit neutral weights

Потрібно додати окремі тести-скани на заборонені fallback patterns, аналогічно current fail-closed practice.

## Runtime Wiring Plan

### 1. Aurora Integration

Точки інтеграції:

- [apps/reference/domains/decision_making/aurora_handler.py](c:\Users\user\Music\Phenix\apps\reference\domains\decision_making\aurora_handler.py)
- [apps/reference/domains/decision_making/aurora_scoring_kernel.py](c:\Users\user\Music\Phenix\apps\reference\domains\decision_making\aurora_scoring_kernel.py)
- [apps/reference/domains/decision_making/execution_gate.py](c:\Users\user\Music\Phenix\apps\reference\domains\decision_making\execution_gate.py)

Порядок:

1. strategy kernel рахує direction score `D_t`
2. strategy/runtime already будує `EntryPlan`
3. `ObjectiveEngine` рахує `O_t`, `M_t`, breakdown, readiness
4. якщо component readiness не виконана, signal не проходить далі
5. `D*_t = D_t * M_t`
6. `ExecutionGate` працює на `D*_t`
7. strategy signal / trade intent payload отримує canonical objective trace

### 2. `md_amr` Integration

Точки інтеграції:

- [apps/reference/domains/decision_making/md_amr_handler.py](c:\Users\user\Music\Phenix\apps\reference\domains\decision_making\md_amr_handler.py)
- [apps/reference/domains/decision_making/strategy_gateway.py](c:\Users\user\Music\Phenix\apps\reference\domains\decision_making\strategy_gateway.py)

Потрібно:

- розширити `md_amr` trace contract
- додати `objective_trace`
- валідувати його fail-closed у gateway
- не допустити обходу через incomplete trace

### 3. Realized Trade Capture

Точки інтеграції:

- execution close/fill lifecycle
- TP/SL close
- forced close
- partial close

Практично:

- з моменту відкриття позиції зберігається minimal immutable objective snapshot
- при закритті позиції `posttrade_evaluator` отримує:
  - entry context
  - realized fills
  - realized fees/slippage
  - MAE/MFE path
  - regime path
  - close reason

### 4. Alpha Search Integration

Точка інтеграції:

- [apps/reference/domains/alpha_search/ensemble.py](c:\Users\user\Music\Phenix\apps\reference\domains\alpha_search\ensemble.py)

Потрібно:

- відійти від вузького performance attribution
- додати realized objective attribution
- reweight providers по regime-conditioned realized quality, а не лише по plain outcome

## Mapping From ALYSHA Concepts to Aurora-Native Owners

| ALYSHA concept | Restore as-is | Aurora-native target | Recommendation |
| --- | --- | --- | --- |
| structured reward decomposition | No | `ObjectiveEngine.pretrade_kernel` + `posttrade_evaluator` | Implement natively |
| adaptive weights manager | No | `regime_profiles.py` + strategy config weights | Implement natively |
| cost component | No | pre-trade `cost.py` + realized cost attribution | Implement natively |
| risk component | No | quality-level risk efficiency layer | Implement natively |
| behavior component | No | discipline/churn metrics only | Redesign |
| information component | Partial | readiness/freshness/confidence component | Implement natively |
| event reward | Partial | realized lifecycle tagging only | Redesign narrowly |
| shaping | No | none in production path | Do not port |
| PPO bridge | No | none | Do not port |
| XAI | No direct restore | objective explainability trace | Rebuild |

## Production Rollout Logic

Тут я не погоджуюсь із ідеєю "одразу жорстко ввімкнути нову objective math без acceptance contour".

Цільовий стан справді production.
Але перший hybrid запуск має бути acceptance-driven, інакше ризик regression буде зайвим.

Коректний rollout:

### Phase 0. Formalization

- зафіксувати canonical formulas
- зафіксувати all-required inputs
- зафіксувати config schema
- зафіксувати reject/defer contract на missing data

### Phase 1. Pre-Trade Objective For Aurora + `md_amr`

- реалізувати pretrade kernel
- інтегрувати в `aurora_handler` і `md_amr_handler`
- емiтити `objective_trace`
- ще не робити objective layer окремим policy owner

### Phase 2. Realized Trade Quality

- інтегрувати post-trade evaluator
- зібрати realized decomposition
- прив'язати його до closed trades

### Phase 3. Alpha Search Feedback

- додати objective-driven realized attribution у `alpha_search`
- провести regime-by-regime comparison

### Phase 4. Hard Enforcement

Тільки після проходження hybrid acceptance suite:

- objective score стає жорсткою частиною entry admissibility
- thresholds frozen у config
- strategy profiles versioned

## Full Test Plan

### A. Mathematical Unit Tests

Нові suites:

- `tests/unit/objective_engine/test_edge_component.py`
- `tests/unit/objective_engine/test_cost_component.py`
- `tests/unit/objective_engine/test_risk_component.py`
- `tests/unit/objective_engine/test_information_component.py`
- `tests/unit/objective_engine/test_execution_component.py`
- `tests/unit/objective_engine/test_behavior_component.py`
- `tests/unit/objective_engine/test_pretrade_kernel.py`
- `tests/unit/objective_engine/test_posttrade_evaluator.py`

Що перевіряти:

- monotonicity
- bounded output
- normalization invariants
- sign invariants
- no-side-flip invariant
- missing-input fail-closed behavior

### B. Config Contract Tests

Нові suites:

- `tests/config/test_objective_engine_schema.py`
- `tests/config/test_objective_engine_no_fallbacks.py`
- `tests/config/test_strategy_objective_profiles_complete.py`
- `tests/config/test_alpha_search_objective_feedback_schema.py`

Що перевіряти:

- explicit regime coverage
- no unknown keys
- no omitted coefficients for enabled components
- no default regime fallback for active profiles

### C. Strategy Runtime Tests

Нові suites:

- `tests/domains/decision_making/test_aurora_objective_integration.py`
- `tests/domains/decision_making/test_md_amr_objective_integration.py`
- `tests/domains/decision_making/test_objective_trace_contract.py`

Що перевіряти:

- objective trace emitted on valid signal
- reject/defer on missing required inputs
- hard veto precedence preserved
- direction sign preserved
- threshold logic uses adjusted score deterministically

### D. Execution Lifecycle Tests

Нові suites:

- `tests/domains/execution_position/test_realized_trade_quality_capture.py`
- `tests/domains/execution_position/test_partial_close_quality_attribution.py`
- `tests/domains/execution_position/test_tpsl_close_quality_attribution.py`

Що перевіряти:

- objective snapshot survives through order lifecycle
- close reason enters realized evaluator correctly
- partial close aggregation deterministic
- no duplication on retries/reconciliation

### E. Alpha Search Tests

Нові suites:

- `tests/domains/alpha_search/test_objective_feedback_allocator.py`
- `tests/domains/alpha_search/test_regime_conditioned_objective_reweighting.py`

Що перевіряти:

- provider weights update from realized objective metrics
- poor raw PnL but good quality vs good raw PnL but toxic cost/risk trades are distinguished
- no schema drift with existing alpha search loader

### F. Simulation Scenarios

Обов'язкові simulation suites:

1. Regime drift scenario
   Objective weights повинні коректно переключатись між regimes.

2. Cost trap scenario
   Сигнал хороший по raw score, але spread/slippage drag робить trade неякісним.

3. Overtrading/churn scenario
   Objective behavior component має penalize дисциплінарну деградацію.

4. Structural RR mismatch scenario
   Edge/risk decomposition має відсікти косметично сильні, але структурно погані trades.

5. Fast adverse excursion scenario
   Realized evaluator має відобразити слабку trade quality навіть при невеликому nominal PnL.

6. High-volatility regime transition scenario
   Adaptive weights не повинні ламати sign logic або bypass risk gate.

### G. Hybrid Acceptance Contour

Обов'язковий hybrid contour:

- live data
- testnet execution
- current preflight coherence must pass через [apps/reference/bootstrap/preflight.py](c:\Users\user\Music\Phenix\apps\reference\bootstrap\preflight.py)

Acceptance metrics:

- decision count delta vs baseline
- reject reason distribution delta
- average projected cost ratio
- realized cost drag delta
- MAE/MFE efficiency delta
- cancel/replace churn delta
- realized quality per regime
- no increase in risk veto misses

## Implementation Sequence

### Wave 1. Mathematical Canonicalization

- винести exact formulas і invariants у code comments/spec
- зафіксувати inputs per component
- зафіксувати regime namespace

### Wave 2. Schema and Config

- додати `ObjectiveEngineDomainConfig`
- додати strategy-level objective profiles
- додати alpha-search objective feedback config

### Wave 3. Pre-Trade Runtime

- додати `objective_engine` package
- інтегрувати в Aurora і `md_amr`
- додати objective trace

### Wave 4. Post-Trade Runtime

- realized quality evaluator
- lifecycle binding
- WAL/report exports

### Wave 5. Alpha Search Feedback

- objective-driven provider attribution
- regime-conditioned allocator

### Wave 6. Full Regression and Hybrid Acceptance

- full pytest
- targeted simulation suite
- hybrid live-data/testnet-exec runbook

## Practical Recommendations

### Що я рекомендую імплементувати обов'язково

- current-native `Objective Engine`
- pre-trade quality decomposition
- realized trade-quality evaluator
- regime-conditioned weights per strategy
- objective trace in signals/intents/WAL
- alpha-search realized quality feedback

### Що я рекомендую не імплементувати

- `alysha_core` як прямий runtime dependency
- RL adapters у production path
- shaping
- exploration reward
- target-frequency behavior reward

### Що я рекомендую переписати, а не переносити

- behavior component
- XAI layer
- event component

## Final Conclusion

Так, у `alysha_core` є справді цінна логіка, і вона потрібна поточному проекту.

Але потрібна не в старому вигляді.

Production-grade реалізація для Aurora має бути такою:

- direction лишається у current strategy kernels
- risk/execution hard veto лишається у current owners
- `alysha_core`-ideas стають `Objective Engine`
- realized trade quality стає canonical feedback object
- alpha-search отримує regime-aware, cost/risk-aware feedback loop

Якщо робити це саме так, то ми отримуємо:

- математично сильнішу оцінку якості угод
- кращу адаптацію до regime drift
- кращу explainability
- менший risk of raw-PnL overfitting
- production-compatible інтеграцію без dual runtime owners

Якщо ж спробувати "просто підключити `alysha_core` у runtime", то це майже напевно створить:

- contract mismatch
- state drift
- explainability drift
- policy ambiguity
- і важковідловлювані regressions у hybrid/live-like execution
