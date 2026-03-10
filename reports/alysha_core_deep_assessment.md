# ALYSHA Core Deep Assessment

## Scope

Цей звіт відповідає на питання:

- що таке `alysha_core` насправді з точки зору архітектури, математики і runtime-ролі;
- які проблеми ця логіка намагалася вирішити;
- чи існують ці проблеми в поточній Aurora/Phenix системі;
- чи потрібно інтегрувати `alysha_core` у current system;
- якщо так, то куди саме, в якій формі і чого точно не можна робити.

Аналіз спирається тільки на код у поточному workspace:

- `alysha_core/reward_engine_v3plus/*`
- current Aurora runtime у `apps/reference/*`
- current config/schema surface у `apps/reference/config_models.py`, `config/*`
- current FE / alpha / decision / execution owners.

## Executive conclusion

Мій висновок жорсткий:

`alysha_core` не є готовим кандидатом на пряме підключення в current live runtime як owner торгового рішення.

Це не "ще одна стратегія". Це reward engine / RL evaluation subsystem з домішкою adaptive weighting, reward shaping, XAI та PPO bridge.

Його сильна сторона:

- як research/shadow evaluator для альтернативних policy/objective;
- як лабораторія reward-дизайну;
- як джерело окремих ідей для backtest/scoring/telemetry.

Його слабка сторона:

- він архітектурно не збігається з current deterministic event-driven Aurora;
- вимагає іншого контракту стану;
- містить training-specific incentives, які небезпечно переносити в production decision path;
- має власні внутрішні неузгодженості, які вже в коді видно без інтеграції.

Практичний висновок:

- `alysha_core` не треба імплантувати в hot execution/decision path.
- Його треба або залишити ізольованим research engine, або переосмислити як `shadow_reward_evaluator`.
- До current system варто переносити не runtime форму, а лише вибрані semantics.

## What `alysha_core` actually is

По факту `alysha_core` зараз складається майже повністю з `reward_engine_v3plus`.

Ключова формула задекларована в `alysha_core/reward_engine_v3plus/main_engine.py`:

`R_t = Σ ω_i(S_t, Θ_t) * R̃_i,t(S_t, A_t) + R̃_Event,t(S_t) + R̃_Shaping,t(S_t, S_t+1)`

Тобто система побудована навколо:

- decomposition reward на компоненти;
- online normalization;
- regime-adaptive weights;
- event reward;
- shaping reward;
- PPO/RLX-compatible data bridge;
- XAI explanation layer.

Це типова архітектура не execution engine, а policy-learning / policy-evaluation substrate.

## Current Aurora architecture anchors

Current Aurora працює інакше.

### 1. Decision ownership

Current owner рішення:

- deterministic scoring kernel: `apps/reference/domains/decision_making/aurora_scoring_kernel.py`
- explicit execution gate chain: `apps/reference/domains/decision_making/execution_gate.py`
- strategy signal gateway: `apps/reference/domains/decision_making/strategy_gateway.py`
- strategy arbitration через `strategies.yaml`

Тобто зараз рішення приймається через:

- features -> score
- shields
- regime gates
- risk gates
- structural entry plan checks
- strategy arbitration

А не через reward maximization loop.

### 2. Risk ownership

Current risk already має свого owner:

- external risk score / trading allowed contract
- gateway-level fail-closed gate по `risk_score`
- execution structural gate по Risk/Reward
- current execution protections, holding period, supersede guard, TTL, brackets

### 3. Explainability ownership

Current explainability already exists у формі:

- `why_chain`
- shield breakdown
- normalized reject reasons
- explicit decision trace / WAL contracts

### 4. Alpha ownership

Current alpha side already має:

- `alpha_search`
- `ta_ensemble`
- dynamic ensemble weights
- separate strategy/runtime/config ownership

### 5. Feature ownership

Current FE already emits TA and market-state surface:

- RSI / MACD / stochastic / momentum / Bollinger outputs
- pillar features
- readiness contracts
- additive-only feature contract

Отже, у current system майже всі problem classes already існують, але вирішені через explicit contracts and gates, а не через RL reward engine.

## What problems `alysha_core` was trying to solve

З коду видно, що `alysha_core` намагався вирішити щонайменше 7 реальних проблем.

### 1. Sparse / delayed reward

PnL сам по собі дає рідкий і шумний signal для policy learning. Тому з'явилися:

- `pnl`
- `event`
- `shaping`
- `behavior`
- `information`

### 2. Market non-stationarity

Через `AdaptiveWeightsManager` логіка намагалася зробити reward regime-aware:

- різні ваги в bull/bear/flat/crisis/volatility

### 3. Risk blindness

Компоненти `risk` і `risk_reward` намагалися вшити risk discipline прямо в objective, а не лише у hard veto.

### 4. Cost blindness

Компонента `cost` намагалася штрафувати:

- spread
- fees
- slippage

### 5. Behavioral pathologies

Компонента `behavior` явно націлена на боротьбу з:

- churn
- хаотичними рішеннями
- latency-sensitive поганою поведінкою

### 6. Exploration / uncertainty handling

`information` і `shaping` намагалися працювати з:

- signal alignment
- model uncertainty
- exploratory actions
- novelty

### 7. Opaque RL policy

`xai_integration.py` намагався зробити reward explainable через component breakdown.

## Do these problems exist in current Aurora?

Так, але не всі в тій самій формі.

### Реально існують

- non-stationarity by regime
- execution costs and slippage realism
- risk discipline
- explainability
- anti-churn
- policy comparison in backtest/shadow

### Не існують як first-class current runtime problem

- online exploration bonus
- PPO action novelty reward
- reward shaping as driver of live trade decisions
- dict/ppo bridge as runtime dependency

Отже, `alysha_core` вирішує суміш двох різних світів:

- production-like trading constraints
- RL training optimization needs

У current Aurora production-ish path потрібен перший світ, але не другий.

## Mathematical assessment

## 1. Strong parts

### PnL / cost / risk decomposition

Ідея декомпозиції reward на:

- PnL
- cost
- risk

є математично адекватною для backtest / RL / shadow evaluation.

Це хороший спосіб уникати dumb optimization по gross PnL.

### Quadratic risk penalties

У `components/risk.py` risk перевищення лімітів караються квадратично:

- drawdown
- VaR
- CVaR
- volatility deviation
- inventory excess

Це хороша форма soft barrier:

- малі порушення не домінують;
- великі порушення караються агресивно.

### Normalization layer

Ідея online normalization для heterogeneous reward components теж логічна. Інакше PnL просто задавить усі інші компоненти scale-wise.

## 2. Weak parts

### Behavior reward is not a clean trading objective

`components/behavior.py` винагороджує:

- strategy consistency
- target trading frequency
- low execution latency

Це вже не market objective, а meta-regularization.

Проблема:

- consistency може винагороджувати stubbornness;
- target trading frequency може штучно заохочувати або пригнічувати churn;
- latency часто визначається інфраструктурою, а не policy quality.

Для RL-research це іноді допустимо.
Для live production objective це ризик "rewarding the proxy instead of the edge".

### Information reward is explicitly training-centric

`components/information.py` містить:

- signal alignment
- strategic exploration
- reward for exploratory action

Це корисно в RL-training.
Для live trading це майже завжди небезпечно.

Особливо exploration bonus:

- він прямо конфліктує з capital-preserving production logic.

### Shaping formulation is mathematically suspicious for policy invariance

У `components/shaping.py` shaping реалізовано як:

`κ × [Φ(s') - γ × Φ(s)]`

та саме так задокументовано у файлі.

Класична potential-based shaping, яка зберігає optimal policy, має форму:

`γ Φ(s') - Φ(s)`

Це не те саме, якщо `γ != 1`.

Тобто навіть якщо задум був теоретично правильний, поточна формула виглядає неканонічно і policy-invariance тут не доведена.

### Regime-adaptive weights are useful, but ontology-mismatched

`AdaptiveWeightsManager` працює з режимами на кшталт:

- `NORMAL`
- `BULL`
- `BEAR`
- `CRISIS`
- `VOLATILITY`
- `FLAT`

Current Aurora regime ontology інша:

- `TREND_UP`
- `TREND_DOWN`
- `MEAN_REVERSION`
- `HIGH_VOLATILITY`
- `LOW_VOLATILITY`
- `UNCERTAIN`
- `FLAT_LOW/FLAT_NORMAL/FLAT_HIGH`

Тобто математична ідея корисна.
Але поточна regime surface не сумісна один-в-один.

## 3. Internal mathematical/logical inconsistencies

### Event integration in the main engine is internally inconsistent

У `alysha_core/reward_engine_v3plus/main_engine.py`:

- `_calculate_event_reward(active_events_data)` очікує `ActiveEventsData`
- але якщо зареєстрований component `event`, engine викликає `self.components["event"].calculate(active_events_data)`

Проблема:

- `EventRewardComponent.calculate()` працює зі `StateData`, а не з `ActiveEventsData`

Тобто engine-level event wiring у поточному коді вже неузгоджене.

### XAI is not faithful to actual reward composition

У `xai_integration.py`:

- contribution та importance рахуються по `raw_value`
- feature importance змішує `abs(result.raw_value)` і `abs(weight - 1.0)`

Але фінальний reward формується через:

- normalized values
- adaptive weights
- weighted sum
- plus event/shaping

Отже XAI layer пояснює не зовсім той об'єкт, який реально оптимізується.

Це робить explanation informative, але не faithful.

### Integration tests are mostly component tests, not engine-contract tests

`alysha_core/reward_engine_v3plus/tests/test_phase3_integration.py` переважно:

- додає компоненти в engine;
- викликає `component.calculate_reward(sample_state)` напряму;
- не тестує повноцінно `calculate_total_reward()` як production composition path.

Це означає, що subsystem виглядає протестованим сильніше, ніж є насправді.

## Architecture fit assessment

## 1. Direct runtime integration into Aurora decision path

Моя оцінка: `No`.

Причини:

- current Aurora decision owner deterministic, fail-closed, contract-first;
- `alysha_core` policy-objective-first;
- `alysha_core` очікує інший state contract;
- `alysha_core` містить training-specific incentives;
- direct integration зламає ownership boundaries.

### Exact mismatch points

#### Contract mismatch

`alysha_core` expects first-class objects like:

- `AgentActionData`
- `ModelPredictionData`
- `action_vector`
- `prediction_vector`
- `is_exploratory`
- `model_uncertainty`

У current Aurora live path це не canonical event contract.

#### Regime mismatch

Regime taxonomies несумісні.

#### Risk ownership mismatch

Current risk is a gate.
`alysha_core` risk is a soft penalty inside objective.

Це різні philosophies:

- fail-closed rule system
- soft optimization objective

#### Explainability mismatch

Current Aurora explainability прив'язана до:

- why_chain
- reject reasons
- gate results
- shield breakdown

`alysha_core` пояснює reward decomposition, а не live gate reasoning.

## 2. Direct integration into execution layer

Моя оцінка: `Hard No`.

`alysha_core` не повинен опинитися в execution hot path.

В execution layer будь-який objective-style soft regularizer створює ризик:

- drift between visible config and actual runtime action;
- non-local behavior;
- важко верифікований side effect;
- прихований конфлікт із fail-closed logic.

## 3. Direct integration as a new strategy

Моя оцінка: `No in current form`.

Чому:

- це не strategy generator, а evaluator/objective stack;
- там немає current-native contract для `EVT:STRATEGY_SIGNAL_PRODUCED` як first-class owner;
- PPO/RLX bridge не має current runtime counterpart;
- current system already має strategy owners: `aurora`, `mean_reversion`, `md_amr`, `llm_microstructure`.

## 4. Integration as shadow evaluator / research subsystem

Моя оцінка: `Yes, this is the right shape`.

Саме тут `alysha_core` має сенс.

Правильна роль:

- читати current state snapshots;
- обчислювати alternative reward decomposition;
- не впливати на live decision;
- писати telemetry / diagnostics / backtest metrics;
- порівнювати objective з realized outcome.

Це дасть:

- більше розуміння quality current strategies;
- можливість шукати reward/objective misalignment;
- safe sandbox для ваших RL/advanced ideas.

## Overlap with current system

| ALYSHA concept | Current Aurora equivalent | Verdict |
| --- | --- | --- |
| PnL component | Backtest/position tracking/execution PnL | semantics reusable |
| Cost component | fees/slippage/spread already modeled in execution/backtest | reusable as analytics |
| Risk penalty | current risk score + hard gates | do not replace hard gates |
| Adaptive regime weights | regime thresholds, alpha ensemble weights, per-regime configs | port idea only |
| Behavior reward | holding-period, anti-churn, TTL, supersede logic | do not port objective |
| Information reward | alpha models / features / confidence / why_chain | exploration part should not port |
| Event reward | current event-driven system, reject reasons, detector outputs | use as telemetry only |
| Shaping reward | no current equivalent by design | redesign required; likely keep out of prod |
| XAI reward breakdown | current why_chain / shield breakdown / trace WAL | optional research addition |
| PPO/RLX bridge | no current runtime owner | do not integrate into prod runtime |

## External dependency and SSOT assessment

`alysha_core` не є current-native subsystem.

В коді є прямі імпорти:

- `from core.research.market_regime import MarketRegime`
- `from core.utils.canonical_config import ConfigManager`
- `from core.errors.config_errors import ConfigurationError`
- `from core.logging.unified_logger import get_logger`
- `from core.risk.risk_manager import RiskManager`
- `from rlx.utils.rms import RunningMeanStd`

Проблема:

- `core.*` тут не є canonical owner current Aurora config/runtime;
- `rlx` як runtime package у current repo відсутній;
- отже subsystem не просто "лежить без wiring", а залежить від чужої екосистеми понять.

Це прямий доказ, що сліпа реінтеграція буде не reintegration, а transplant між різними системами.

## My judgment by concept

## 1. What should not be integrated into current production runtime

### Do not integrate as-is

- PPO adapter
- RLX bridge
- behavior reward as live objective
- exploration reward
- action novelty / learning progress shaping
- shaping component in live decision path
- separate `alysha_reward_engine` config tree as another SSOT

### Why

- training incentives != trading invariants;
- це зруйнує current ownership boundaries;
- зросте ризик non-transparent behavior.

## 2. What may be worth integrating in adapted form

### Cost decomposition

Корисно перенести як:

- richer backtest diagnostics
- alpha_search evaluator penalties
- shadow telemetry metric

але не як live decision owner.

### Risk proximity / soft diagnostics

Корисно перенести як:

- dashboard metric
- shadow evaluator metric
- score annotation for backtests

але hard gates must remain primary owner.

### Regime-adaptive weighting idea

Це найцінніша концептуальна частина.

Правильне місце в current system:

- `alpha_search` provider weighting
- backtest scenario scoring
- shadow ensemble diagnostics

а не direct replacement Aurora scoring kernel.

### Reward breakdown XAI

Може бути корисно для:

- research reports
- shadow diagnostics
- model comparison

Але не треба змішувати з current `why_chain` і gate explanations.

## 3. What is worth building around it

Найкращий шлях:

створити current-native domain на кшталт:

- `shadow_reward_evaluator`
- або `research_policy_evaluator`

який:

1. читає current Aurora snapshots/events;
2. мапить їх у свій isolated evaluation state;
3. запускає adapted reward decomposition;
4. пише JSONL/WAL/report metrics;
5. ніколи не впливає на `TRADE_INTENT_PROPOSED` напряму.

## Recommended integration architecture

## Option A: Keep `alysha_core` isolated and add adapter from Aurora -> evaluator

Це мій preferred path.

### Shape

- new shadow/research adapter
- current event snapshots as input
- no runtime authority
- offline or shadow-only score output

### Benefits

- zero conflict with decision/execution ownership
- можна валідно порівнювати reward з realized PnL
- можна шукати, де current system overtrades / undertrades / misprices risk

### Risks

- треба чесно визначити mapping Aurora state -> evaluator state
- regime ontology треба переузгодити

## Option B: Port selected math into current owners

Це другий найкращий шлях.

### Що можна портити

- cost decomposition into backtest metrics
- regime-conditioned provider weighting in `alpha_search`
- risk proximity diagnostics
- richer explainability for research reports

### Що не можна портити

- exploration reward
- behavior frequency target
- shaping in live path
- PPO contracts

## Option C: Full reintegration into live runtime

Моя оцінка: `do not do this`.

## Exact blockers to direct integration

1. `alysha_core` не підключений до current event contracts.
2. Його state model не є Aurora SSOT.
3. Regime ontology mismatch.
4. External dependency mismatch (`core.*`, `rlx.*`).
5. Behavior/information/shaping містять RL-specific incentives.
6. XAI layer не faithfully explains final weighted normalized reward.
7. Engine-level event integration already looks internally broken.
8. Tests не доводять справжню end-to-end correctness engine composition.

## Final answer to the user question

### Чи потрібно інтегрувати `alysha_core` у current system?

Не в тому вигляді, в якому він зараз існує.

### Чи є в ньому цінна логіка?

Так, і доволі багато.

Найцінніше:

- structured reward decomposition
- regime-adaptive weighting idea
- richer cost/risk accounting
- research-oriented explainability

### Чи намагався він вирішити реальні проблеми, які є і у вас?

Так.

Особливо:

- regime drift
- over-optimization on raw PnL
- недооцінка cost/risk
- слабка explainability альтернативних policy

### Чи треба переносити його в live path?

Ні.

### Що треба робити замість цього?

1. Визнати `alysha_core` research/shadow subsystem, а не strategy/runtime owner.
2. Побудувати current-native Aurora adapter -> `shadow_reward_evaluator`.
3. Запустити його на:
   - backtest traces
   - hybrid live-data/testnet-order contour
   - shadow strategy comparisons
4. Після цього переносити у current owners лише окремі verified ideas.

## My practical recommendation

### Short version

- `alysha_core as production runtime owner`: no
- `alysha_core as shadow evaluator`: yes
- `alysha_core as source of selected math`: yes
- `alysha_core PPO/RLX bridge in current prod`: no

### If you want maximum value with minimum architectural damage

Починати треба не з "підключити `alysha_core` до рантайму", а з:

- побудови Aurora snapshot adapter;
- shadow запуску reward decomposition;
- correlation analysis:
  - reward vs realized pnl
  - reward vs blocked intents
  - reward vs churn
  - reward vs drawdown episodes

Саме так ми зрозуміємо, чи ця логіка реально додає edge, чи тільки створює красиву, але небезпечну мета-оптимізацію.
