# AGENT_REPORT_V1

## Executive Summary
`BOUNDED_ENABLE_ACTIVE_ECONOMIC_EDGE_UNPROVEN`

PositionPolicySidecar в текущем дереве проекта является не “общим sidecar-модулем”, а строго ограниченным exit-collaborator внутри execution_position. Он уже работает в режиме `enable`, получает живые входы из portfolio/features/regime/fill/order-state/reconcile, умеет выпускать bounded soft-close request, но не владеет execution truth и не имеет права на partial reduce, bracket mutation или exact targeting.

Его математика сильна по explainability и fail-closed дисциплине, но средняя по экономической выразительности: основной live-authority score не содержит явного fee/slippage term, а текущий profitability guard фактически делает основной live path `loss-only`. Отдельная fee-aware shadow ветка уже считает экономику намного лучше, но пока остаётся строго неавторитетной observability surface.

Актуальное состояние по последнему доступному frozen capture `sidecar_manageflow_capture_20260510T200250Z`: sidecar жив, bootstrap подтверждён, весь агрегированный capture содержит `11` рекомендаций и `11` close requests, но в самом последнем restart slice рекомендаций уже `0`, максимум `soft_close_pressure = 0.29318 < 0.3`, а основной текущий blocker у свежих кандидатов — `features_snapshot_missing_or_stale`. Это означает: path работает, но именно в последнем срезе он не доводит кандидатов до threshold crossing.

## Proven Facts
- Авторитетный config surface sidecar находится в `config/aurora/domains.yaml`, ключ `execution_position.position_policy_sidecar`.
- Текущее значение `mode` = `enable`.
- Текущий bounded action scope:
  - `soft_close_symbol_current_net_only = true`
  - `partial_reduce = false`
  - `bracket_mutation = false`
  - `exact_targeting = false`
- Pydantic-модель `PositionPolicySidecarConfig` fail-closed запрещает `partial_reduce`, `bracket_mutation`, `exact_targeting`; это не runtime-конвенция, а startup contract.
- `ExecPosFSM` создаёт sidecar только если `mode != disable`, передаёт ему getters на manage_flow, known_symbols и accumulated symbol lifecycle fees.
- Sidecar получает входы из:
  - `EVT:PORTFOLIO_STATE_UPDATED`
  - `EVT:FEATURES_CALCULATED`
  - `EVT:REGIME_DETECTED`
  - `EVT:ORDER_STATE_CHANGED`
  - `EVT:TRADE_EXECUTED`
  - `EVT:ORDER_FILL`
  - `EVT:EXECUTION_CLOSE_RECONCILED`
- `TRADE_EXECUTED` и `ORDER_FILL` попадают в sidecar не через обычный event forward, а через `fill_ingress_coordinator`, который передаёт canonical fill ingress в `on_trade_executed()` или `on_order_fill()`.
- Sidecar не отправляет ордера на биржу напрямую. Он публикует только `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`, который затем проверяется mediator-ом и конвертируется в стандартный `CMD:CLOSE`.
- Mediator дополнительно fail-closed проверяет:
  - `policy_source`
  - `requested_action == SOFT_CLOSE`
  - `target_mode == symbol_current_net_only`
  - отсутствие `requested_qty`
  - текущий allowed scope
  - наличие active lifecycle
  - не-`FLAT` portfolio state
  - решение execution truth hardening
- В registry sidecar surface mostly experimental:
  - `POSITION_POLICY_SIDECAR_SUPPRESSED` = `active`
  - `POSITION_POLICY_SIDECAR_MODE_ACTIVE`, `EVALUATED`, `SCORES`, `FEE_AWARE_SHADOW_ARM_STATE`, `RECOMMENDED`, `CLOSE_REQUEST`, `CLOSE_REQUEST_STATE` = `experimental`
  - `POSITION_POLICY_SIDECAR_ACTION_SKIPPED` = `experimental`, но прямо помечен как reserved / no runtime emitter exists.
- Текущий forensic validation по frozen capture `20260510T200250Z` дал:
  - `policy_row_count = 115147`
  - `POSITION_POLICY_SIDECAR_SUPPRESSED = 113317`
  - `POSITION_POLICY_SIDECAR_EVALUATED = 863`
  - `POSITION_POLICY_SIDECAR_RECOMMENDED = 11`
  - `POSITION_POLICY_SIDECAR_CLOSE_REQUESTED = 11`
  - `POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE = 32`
  - `recommendation_truth_classification = recommendations_matched`
  - `action_skipped_count = 0`
- Последний restart slice этого же capture дал:
  - `evaluated_count = 27`
  - `recommendation_count = 0`
  - `threshold_crossing_evaluated_count = 0`
  - `max_evaluated_soft_close_pressure = 0.29318181818181815`
  - `fill_ingress_transition_verdict = candidate_existed_then_degraded`
  - два свежих fill-ingress symbols: `BNBUSDT`, `XRPUSDT`
  - оба получили `operator_verdict = evaluated_then_decayed`
  - latest blocker у обоих: `features_snapshot_missing_or_stale`
- Узкий текущий test slice прошёл полностью: `48 passed in 2.10s`.

## Inferred Findings
- Sidecar уже нельзя корректно описывать как purely shadow-only surface: action path в коде и в runtime существует.
- При этом execution truth всё ещё полностью остаётся у execution_position; sidecar — не executor, а bounded request producer.
- Главный live-authority path математически ориентирован на cut losses, а не на harvest profits.
- Текущая runtime деградация в последнем restart slice выглядит не как поломка bridge path, а как деградация доступности/свежести входных данных, прежде всего features.
- Fee-aware shadow ветка уже сейчас более экономически осмысленна, чем основной authority score, но намеренно не переведена в authority.

## Contradictions / Evidence Gaps
- Aggregate capture подтверждает `11` рекомендаций и `11` close requests, но latest slice показывает `0` threshold crossings; значит “работает в capture вообще” и “сейчас в последнем срезе активно рекомендует” — это не одно и то же.
- Текущий validator честно предупреждает о blind spots: он видит только Sidecar rows и не может доказать промежуточные truth transitions, если они не были sidecar-emitted.
- Позитивная expectancy sidecar всё ещё не доказана: код и runtime path подтверждены, экономическое превосходство над bracket/hold — нет.
- Peak-giveback code path доказан тестами и кодом, но в текущем latest slice нет runtime evidence, что именно эта ветка сейчас активна как источник рекомендаций.

## Root Cause Candidates
- Поздние или редкие рекомендации в live path, вероятно, связаны не с одной причиной, а с комбинацией:
  - сильные freshness gates
  - `profitability_guard`, который почти целиком закрывает неубыточные состояния
  - достаточно низкая, но всё же составная threshold логика (`0.3`) при четырёх компонентах
  - отсутствие явного fee/slippage term в authoritative score
- Для small-edge trades live peak-giveback arming threshold `$25` может быть грубым и слишком поздним.

## Operational Risk
- Runtime
- Correctness
- Capital
- Observability Gap

## Files / Areas Touched
- Новый документ:
  - `POSITION_POLICY_SIDECAR_LOGIC_CHAIN_DEEP_RESEARCH_REPORT_2026-05-11.md`
- Код и артефакты, на которых основан анализ:
  - `apps/reference/config/domains/execution_position.py`
  - `config/aurora/domains.yaml`
  - `apps/reference/domains/execution_position/fsm.py`
  - `apps/reference/domains/execution_position/orchestration/fill_ingress_coordinator.py`
  - `apps/reference/domains/execution_position/sidecar/position_policy_sidecar.py`
  - `apps/reference/domains/execution_position/sidecar/position_policy_mediator.py`
  - `apps/reference/domains/execution_position/flows/manage/fsm_manage.py`
  - `apps/reference/domains/execution_position/flows/close/close_executor.py`
  - `apps/reference/dictionaries/verb_registry_v1.yaml`
  - `tools/forensics/position_policy_sidecar_validation.py`
  - `artifacts/position_policy_sidecar/current_capture_20260510T200250Z_validation_summary.json`
  - `POST_ENTRY_GIVEBACK_SIDECAR_DEEP_RESEARCH_REPORT.md`
  - `SIDECAR_ENABLE_GOVERNANCE_AUDIT_REPORT.md`

## Validation Performed
- Forensic validation on latest available frozen capture:

```powershell
Set-Location "c:/Users/user/Music/Phenix"
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m tools.forensics.position_policy_sidecar_validation \
  --trade-lifecycle frozen/sidecar_manageflow_capture_20260510T200250Z/logs/trade_lifecycle.jsonl \
  --order-log frozen/sidecar_manageflow_capture_20260510T200250Z/logs/order_log_v1.jsonl \
  --output-json artifacts/position_policy_sidecar/current_capture_20260510T200250Z_validation_summary.json
```

- Focused executable proof for the current sidecar contracts:

```powershell
Set-Location "c:/Users/user/Music/Phenix"
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest \
  tests/domains/execution_position/test_position_policy_sidecar.py \
  tests/domains/execution_position/test_position_policy_sidecar_peak_giveback.py \
  tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py \
  tests/tools/test_position_policy_sidecar_validation.py -q

# Result:
# 48 passed in 2.10s
```

## Residual Risk
- Latest slice currently degrades from fresh candidate to stale-features suppression; if feature freshness remains unstable, the mathematical quality of the score becomes secondary because the policy will stay mostly suppressed.
- Main authoritative score remains fee-blind, so its recommendation quality can diverge from realized net PnL even when the score is internally consistent.
- The reserved `ACTION_SKIPPED` surface is still dead; this is not a path breaker, but it continues to widen the gap between registry and live runtime semantics.

## What Remains Unproven
- Positive expectancy of live sidecar closes relative to bracket-only handling.
- Economic superiority of the current `soft_close_pressure` threshold.
- Runtime benefit of promoting fee-aware shadow logic into authority.
- Whether the current `$25` peak-giveback arm threshold is calibrated to the actual edge distribution of the traded symbols.

## Minimal Safe Verdict
`MAINTAIN_BOUNDED_ENABLE_NO_AUTHORITY_EXPANSION`

Сохранять sidecar в текущем bounded enable можно, потому что bridge path доказан и жёстко ограничен. Расширять authority нельзя, потому что current live-authority math ещё не доказывает экономическое преимущество, а latest slice прямо показывает degradation-by-staleness вместо активного threshold crossing.

## 1. Что такое текущий sidecar в проекте

Это explainable policy engine для уже открытых позиций. Он не принимает решение об открытии, не управляет bracket orders и не ведёт exchange execution сам. Его узкая задача — наблюдать уже живую позицию и, если накопится достаточное давление на soft close, выпустить bounded internal close request.

Главная граница ответственности:
- execution_position владеет lifecycle truth и close execution
- sidecar владеет только derived evaluation и bounded close recommendation/request
- mediator является admissibility gate между этими слоями

Практический смысл этого дизайна:
- sidecar можно развивать как policy layer
- execution truth остаётся жёстко централизованным
- любые ошибки sidecar не должны превращаться в свободный, неограниченный execution surface

## 2. Какие данные sidecar потребляет для решений

### 2.1 Прямые входы событий

1. `EVT:PORTFOLIO_STATE_UPDATED`
   - Даёт снимок positions по символам.
   - Из него sidecar берёт `positionAmt`, `entryPrice`, `markPrice`, `unrealizedProfit` и факт присутствия/отсутствия символа в portfolio snapshot.

2. `EVT:FEATURES_CALCULATED`
   - Даёт market-feature surface.
   - Из него используются либо прямые policy-friendly поля (`microstructure_adverse_pressure`, `conviction_decay`), либо исходные признаки для их восстановления (`orderbook_imbalance`, `price_vs_vwap_bps`, `signal_score`).

3. `EVT:REGIME_DETECTED`
   - Даёт regime label и confidence.
   - Используется либо прямой `regime_exhaustion_hint`, либо реконструкция через `regime_confidence` и adverse regime label.

4. `EVT:TRADE_EXECUTED` и `EVT:ORDER_FILL`
   - Даются через canonical fill ingress.
   - Используются для:
     - lifecycle reset на новой entry fill
     - post-fill grace
     - correlation payload
     - fill fee lookup fallback

5. `EVT:ORDER_STATE_CHANGED`
   - Нужен как suppressor/gate signal.
   - Недавний terminal non-fill order state может временно заблокировать evaluation.

6. `EVT:EXECUTION_CLOSE_RECONCILED`
   - Это authoritative signal, что close truth уже подтверждён.
   - После него sidecar обязан fail-closed перестать рекомендовать closing по этому lifecycle.

### 2.2 Локальные и производные входы

1. `ManageFlowFSM`
   - `state`
   - `_closing_position`
   - `position_side`
   - `position_qty`
   - `position_entry_price`
   - `position_open_ts`
   - `has_active_lifecycle()`

2. Portfolio-derived snapshot
   - `portfolio_symbol_present`
   - `portfolio_snapshot_status`
   - `portfolio_position_amt`
   - `unrealized_pnl_usdt`
   - `unrealized_pnl_pct`

3. Fee input
   - Primary source: accumulated lifecycle fee per symbol, injected через `lifecycle_fee_getter`
   - Fallback: fee from last fill payload / order log field
   - Final fallback: configured fee model, но сейчас он выключен

### 2.3 Что реально влияет на decision, а что только на gating/correlation

На сам score напрямую влияют только:
- features
- regime
- position economics

На gating, dedup, truth hygiene и traceability влияют:
- portfolio freshness
- order state freshness
- fill ingress
- close reconcile
- manage_flow lifecycle presence
- fee snapshots в shadow surface

## 3. Полная цепочка работы sidecar

### 3.1 Bootstrap

1. `ExecPosFSM` поднимается и читает strict typed config.
2. Если `position_policy_sidecar.mode == disable`, sidecar не создаётся.
3. Если mode = `shadow` или `enable`, FSM создаёт `PositionPolicySidecar`.
4. Сразу после создания sidecar публикует `POSITION_POLICY_SIDECAR_MODE_ACTIVE`.

### 3.2 Event ingress

1. Portfolio, features, regime, order-state и reconcile приходят через bus listeners FSM.
2. Fill ingress идёт отдельно через `fill_ingress_coordinator`, который передаёт canonical fill event в sidecar только если canonical result не завершился ошибкой.

### 3.3 Internal state model

На каждый symbol sidecar ведёт `_SymbolState`, где хранятся envelope-объекты:
- `portfolio`
- `features`
- `regime`
- `order_state`
- `last_fill`

И дополнительные policy states:
- `last_reconcile_ts_ms`
- last recommendation signature для dedup
- `peak_edge_usd` и `is_armed` для live peak-giveback
- candidate states для percent-notional и fee-aware shadow arms

### 3.4 Evaluation pipeline

При каждом relevant ingress sidecar вызывает `_evaluate_symbol(symbol, trigger_event=...)`.

Порядок:
1. Собирает `base_payload`.
2. Считает freshness snapshot.
3. Прогоняет suppression chain.
4. Даже при `profitable_guard` отдельно пытается оценить peak-giveback.
5. Если есть жёсткая suppression beyond profitable_guard, рекомендация не проходит.
6. Если suppressions нет, считает `score_snapshot`.
7. Эмитит `SCORES` и `EVALUATED`.
8. Если `soft_close_pressure < recommend_soft_close_at`, на этом evaluation заканчивается.
9. Если threshold достигнут, строит recommendation signature и отсекает duplicate same-state recommendations.
10. Эмитит `RECOMMENDED`.
11. Если mode = `enable`, строит typed `PositionPolicyCloseRequest` и публикует `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`.

### 3.5 Mediator chain

Mediator проверяет, что request:
- sidecar-originated
- soft-close only
- without exact target qty
- в разрешённом scope
- для symbol с active lifecycle
- без активного close-in-progress
- не подавлен execution truth hardening

Если guard chain пройдена:
- mediator переводит это в стандартный `CMD:CLOSE`
- execution_position выполняет уже обычную close path
- close_executor и guardian формируют authoritative outcome
- mediator emits `POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE`

### 3.6 Где заканчивается authority sidecar

Sidecar authority заканчивается на моменте публикации bounded close request. Всё дальше — execution-owned truth path.

## 4. Подробная математика

## 4.1 Freshness и warmup math

Для каждого envelope считается age:

```text
portfolio_age_ms = now_ms - portfolio.ts_ms
features_age_ms  = now_ms - features.ts_ms
regime_age_ms    = now_ms - regime.ts_ms
order_state_age_ms = now_ms - order_state.ts_ms
```

Freshness flags:

```text
portfolio_fresh   = portfolio_age_ms <= portfolio_max_age_ms
features_fresh    = features_age_ms  <= features_max_age_ms
regime_fresh      = regime_age_ms    <= regime_max_age_ms
order_state_fresh = order_state_age_ms <= order_state_max_age_ms
```

В текущем config:
- portfolio_max_age_ms = `60000`
- features_max_age_ms = `15000`
- regime_max_age_ms = `30000`
- order_state_max_age_ms = `15000`

Дополнительные fail-closed gates:
- `startup_grace_ms = 30000`
- `post_fill_grace_ms = 15000`
- minimum update counts для portfolio/features/regime = `1/1/1`

Это означает: даже идеальная математика score не будет использована, если input freshness/warmup не удовлетворены.

## 4.2 Построение position snapshot и PnL math

`unrealized_pnl_pct` определяется в таком порядке:

1. Если уже есть прямое поле `unrealized_pnl_pct` или `unrealizedPnlPct`, оно используется как есть.
2. Иначе, если известны `unrealized_pnl_usdt`, `entry_price` и `position_amt`:

```text
notional = abs(position_amt) * entry_price
unrealized_pnl_pct = (unrealized_pnl_usdt / notional) * 100
```

3. Иначе, если известны `entry_price`, `mark_price`, `side`:

```text
side_sign = +1 for BUY, -1 for SELL
unrealized_pnl_pct = side_sign * ((mark_price - entry_price) / entry_price) * 100
```

Это простая и корректная нормализация: live economics выражаются либо через realised PnL relative to notional, либо через signed price delta.

## 4.3 Profitability guard

Правило:

```text
profitable =
    unrealized_pnl_pct  >= min_unrealized_pnl_pct
    OR
    unrealized_pnl_usdt >= min_unrealized_pnl_usdt
```

Текущие параметры:
- `enabled = true`
- `min_unrealized_pnl_pct = 0.25`
- `min_unrealized_pnl_usdt = 0.0`

Критически важное следствие:

```text
Любой unrealized_pnl_usdt >= 0.0 уже активирует profitable_guard.
```

То есть при текущем config основной authority score path практически не предназначен для фиксации небольшой прибыли или breakeven выхода. Он математически настроен как loss-cut surface.

Это сильное архитектурное решение, а не случайный побочный эффект.

## 4.4 Основной soft-close score

### 4.4.1 Microstructure adverse pressure

Если feature payload уже содержит прямой `microstructure_adverse_pressure`, то он просто clamp’ится в `[0, 1]`.

Иначе он восстанавливается так:

```text
side_sign = +1 for BUY, -1 for SELL

imbalance_pressure = clamp(max(0, -side_sign * imbalance) / book_imbalance_full_pressure)
distance_pressure  = clamp(max(0, -side_sign * adverse_price_distance_bps) / adverse_price_distance_bps_full_pressure)

microstructure_adverse_pressure = max(imbalance_pressure, distance_pressure)
```

Смысл:
- adverse imbalance против позиции повышает pressure
- adverse distance vs VWAP тоже повышает pressure
- берётся худший из двух microstructure signals

Текущие пороги:
- `book_imbalance_full_pressure = 0.35`
- `adverse_price_distance_bps_full_pressure = 25.0`

### 4.4.2 Regime exhaustion hint

Если payload already даёт `regime_exhaustion_hint`, он clamp’ится в `[0, 1]`.

Иначе:

```text
confidence_pressure = clamp((regime_confidence_floor - regime_confidence) / regime_confidence_floor)
adverse_label_pressure = 1.0 if regime_label in adverse_regimes_for_side else 0.0

regime_exhaustion_hint = max(confidence_pressure, adverse_label_pressure)
```

Текущие параметры:
- `regime_confidence_floor = 0.55`
- adverse regime for long = `TREND_DOWN`
- adverse regime for short = `TREND_UP`

Практически это даёт два механизма давления:
- низкая уверенность regime-классификации
- структурно неблагоприятный regime label

### 4.4.3 Conviction decay

Если feature payload уже содержит `conviction_decay`, он clamp’ится.

Иначе:

```text
if signal_score < signal_score_floor:
    conviction_decay = clamp((signal_score_floor - signal_score) / abs(signal_score_floor or 1.0))
else:
    conviction_decay = 0
```

Текущий `signal_score_floor = 0.0`.

Следствие:
- все non-negative `signal_score` не создают conviction decay
- отрицательные `signal_score` линейно превращаются в pressure

### 4.4.4 Unrealized loss pressure

```text
if unrealized_pnl_pct < 0:
    loss_bps = abs(unrealized_pnl_pct) * 100
    unrealized_loss_pressure = clamp(loss_bps / loss_bps_full_pressure)
else:
    unrealized_loss_pressure = 0
```

Почему `* 100`:
- `unrealized_pnl_pct` хранится в процентах
- `loss_bps_full_pressure` задан в bps
- поэтому `-0.5%` становится `50 bps`

Текущий `loss_bps_full_pressure = 50.0`, то есть full pressure по этой компоненте достигается уже примерно на `-0.5%` unrealized loss.

### 4.4.5 Аггрегация score

Текущие веса:
- microstructure = `0.30`
- regime = `0.30`
- conviction = `0.15`
- loss = `0.25`

Текущие caps:
- все равны `1.0`

Формула:

```text
weighted_micro = min(microstructure_adverse_pressure, cap_micro) * weight_micro
weighted_regime = min(regime_exhaustion_hint, cap_regime) * weight_regime
weighted_decay = min(conviction_decay, cap_decay) * weight_decay
weighted_loss = min(unrealized_loss_pressure, cap_loss) * weight_loss

exit_pressure_score = clamp(weighted_micro + weighted_regime + weighted_decay + weighted_loss)
soft_close_pressure = exit_pressure_score
hold_confidence = clamp(1 - exit_pressure_score)
position_health_score = clamp(1 - soft_close_pressure)
```

В текущем config веса суммируются ровно в `1.0`, а caps все равны `1.0`, значит `soft_close_pressure` является интерпретируемой convex-like смесью четырёх нормализованных компонент.

### 4.4.6 Recommendation threshold

```text
recommend if soft_close_pressure >= 0.3
```

Это довольно низкий threshold, но из-за profitability guard и freshness gates фактический runtime surface оказывается сильно уже, чем кажется по одной цифре `0.3`.

## 4.5 Peak-giveback mathematics

Это отдельная ветка, не равная основному score.

1. Sidecar ведёт `peak_edge_usd` только по положительным `unrealized_pnl_usdt`.
2. Arm:

```text
if peak_edge_usd >= edge_arm_usd:
    is_armed = true
```

3. Trigger:

```text
giveback_usd = peak_edge_usd - current_pnl_usdt
giveback_pct = (giveback_usd / peak_edge_usd) * 100

trigger if giveback_pct >= giveback_trigger_pct
```

Текущий config:
- `edge_arm_usd = 25.0`
- `giveback_trigger_pct = 50.0`

Важная особенность:
- эта ветка может сработать даже если основной suppression = `profitable_guard`
- но не сработает при жёстких suppressions вроде close-in-progress или stale critical inputs

То есть это profit-protection branch, отделённая от loss-cut composite score.

## 4.6 Shadow percent-notional arm

Это не live-authority action, а observability surface.

Для каждого `candidate_pct`:

```text
arm_threshold_usd = position_notional_usdt * candidate_pct / 100
```

Текущие кандидаты:
- `0.02`
- `0.05`
- `0.07`

Важно: это именно percent units, не ratio. То есть `0.02` означает `0.02%`, а не `2%`.

После arming используется тот же live giveback trigger percentage (`50%`) для ответа на вопрос `would_trigger`.

## 4.7 Shadow fee-aware arm

Это самая экономически осмысленная часть sidecar, но пока только shadow.

### 4.7.1 Оценка required edge

Сначала оценивается `estimated_fee_usd` по приоритету:
1. `realized_lifecycle_fee`
2. `order_log_fee`
3. `configured_fee_model`

Затем для каждого `fee_multiple` и optional percent floor:

```text
fee_floor_required_edge = estimated_fee_usd * fee_multiple
optional_pct_required_edge = position_notional_usdt * optional_pct_floor / 100

required_edge_usd = max(fee_floor_required_edge, optional_pct_required_edge)
```

Текущий config:
- `candidate_fee_multiples = [1.0, 1.5, 2.0]`
- configured fee model disabled
- optional pct floors enabled: `[0.02, 0.05]`

### 4.7.2 Trigger logic

Arming:

```text
if peak_edge_usd >= required_edge_usd:
    candidate.is_armed = true
```

Trigger check:

```text
would_trigger = candidate.is_armed and giveback_pct >= live_giveback_trigger_pct
```

Ключевое свойство:
- shadow branch уже использует unit-economics through fee floor
- но payload явно маркируется как `shadow_only = true`, `authority_applied = false`, `no_effect = true`

## 5. Оценка математики

### 5.1 Моя оценка

Я оцениваю текущую математику так:

- Explainability и boundedness: `8/10`
- Runtime safety / fail-closed discipline: `8/10`
- Economic grounding live-authority path: `5/10`
- Practical decision readiness в текущем проектном состоянии: `6/10`
- Итоговая совокупная оценка: `6.5/10`

### 5.2 Почему оценка не ниже

1. Формулы простые, монотонные и проверяемые.
2. Все величины нормализуются в `[0, 1]`, веса суммируются в `1.0`, интерпретация понятна.
3. Система fail-closed по stale data, missing lifecycle и invalid action scope.
4. Authority surface жёстко ограничена и трижды зафиксирована: YAML, Pydantic, mediator guards.
5. Есть отдельная, уже полезная, экономическая shadow ветка для наблюдения.

### 5.3 Почему оценка не выше

1. Основной live-authority score fee-blind.
   - В нём нет ни комиссии, ни slippage, ни latency-cost, ни time-to-close cost.
   - Для exit policy это серьёзное ограничение.

2. Текущий profitability guard делает live main path фактически `loss-only`.
   - Это допустимо как design choice.
   - Но тогда нельзя называть основной live path универсальной post-entry profit-protection математикой.

3. Threshold crossing в latest slice отсутствует.
   - Значит current runtime usefulness сейчас упирается не в абстрактную корректность формул, а в то, что real input surface деградирует до stale-features.

4. Peak-giveback arming coarse.
   - `$25` arm threshold может быть слишком велик для symbols/windows с маленьким protectable edge.

5. Economic superiority не доказана.
   - Детерминированность формулы не равна доказанной экономической эффективности.

### 5.4 Ключевой вывод по математике

Текущая математика лучше всего описывается так:

`объяснимая, безопасная, bounded, но пока не полностью экономически зрелая`

Она подходит для controlled runtime experimentation и observability-driven calibration, но недостаточно доказана для расширения authority beyond current bounded soft-close.

## 6. Актуальный статус sidecar в проекте

### 6.1 Что актуально прямо сейчас

- Sidecar включён (`enable`), а не выключен и не purely shadow.
- Его action surface остаётся очень узким.
- Fee-aware shadow остаётся неавторитетным.
- `ACTION_SKIPPED` остаётся зарезервированной, но мёртвой surface.
- Последний доступный capture не показывает path breakage.
- Последний доступный capture показывает local degradation в latest slice: есть свежие кандидаты, есть evaluation, но нет threshold crossing из-за комбинации слабого pressure и stale features.

### 6.2 Что внутри sidecar всё ещё остаётся shadow

Важно различать две разные вещи:
- глобальный runtime mode sidecar
- внутренние policy surfaces внутри самого sidecar

Глобально current sidecar уже не shadow-only, потому что весь модуль работает в `enable` и способен выпускать реальные bounded close requests.

При этом внутри него остаются shadow-only ветки:

1. `shadow_percent_notional_arm`
   - Это observational/calibration surface.
   - Она считает альтернативные arm thresholds как процент от notional и отвечает на вопрос, сработал бы такой порог или нет.
   - Эта ветка не публикует `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST` и не имеет собственной authority.
   - Практически это встроенный what-if слой для калибровки альтернативной post-entry логики.

2. `shadow_fee_aware_arm`
   - Это тоже shadow-only surface, но более экономически содержательная.
   - Она считает fee-aware required edge, отслеживает arm/trigger состояния и публикует отдельное observational event `POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE`.
   - Эта ветка прямо маркируется runtime-полями `shadow_only = true`, `authority_applied = false`, `no_effect = true`.
   - То есть она может сказать: “при fee-aware логике здесь был бы arm/trigger”, но не может инициировать реальное закрытие позиции.

3. `peak_giveback_shadow_arms`
   - Это не отдельный live execution path, а контейнер наблюдательных candidate surfaces внутри peak-giveback snapshot.
   - В него складываются именно shadow percent-notional и shadow fee-aware candidate states.
   - Он нужен для анализа и сравнения альтернативных порогов, а не для прямого action routing.

### 6.3 Что уже не shadow, а live-authority surface

1. Основной `soft_close_pressure` path
   - Когда composite score достигает `recommend_soft_close_at`, sidecar эмитит `POSITION_POLICY_SIDECAR_RECOMMENDED`.
   - В режиме `enable` после этого он публикует реальный `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`.
   - Значит основной score path уже является live bounded action surface, а не shadow telemetry.

2. `peak_giveback_close`
   - Это отдельная live ветка внутри sidecar.
   - Если peak edge armed и затем giveback пересекает trigger threshold, sidecar формирует рекомендацию и в `enable`-режиме также публикует реальный bounded close request.
   - Следовательно, current peak-giveback path тоже уже не shadow, даже если его runtime usefulness пока отдельно не доказан.

Итогово current sidecar работает в смешанном внутреннем режиме:
- live-authority для bounded soft-close и peak-giveback close
- shadow-only для percent-notional calibration и fee-aware calibration

### 6.4 Что не shadow, но и не live-action

Отдельно от shadow surfaces остаётся ещё одна категория: `reserved/dead surface`.

Сейчас к ней относится `POSITION_POLICY_SIDECAR_ACTION_SKIPPED`:
- surface описан в registry и schema
- runtime emitter в текущем коде не найден
- в forensic capture count равен `0`

Это не shadow-логика и не рабочий action path. Это просто зарезервированная, но пока не реализованная поверхность.

### 6.5 Что это значит practically

1. С точки зрения architecture и plumbing sidecar жив и встроен в execution_position корректно.
2. С точки зрения mathematics и policy usefulness sidecar жив, но в последнем срезе не дотягивает до recommendation surface.
3. С точки зрения economics проект ещё находится в режиме calibration/forensics, а не в режиме доказанной optimization.

### 6.6 Самая честная короткая формулировка статуса

`Сейчас sidecar в проекте — это активный bounded soft-close policy engine с доказанным execution bridge, но с недоказанной экономической эффективностью и с текущей деградацией latest-slice inputs на feature freshness.`

## 7. Что я считаю главным выводом для дальнейшей работы

Если цель — понять именно “почему сейчас sidecar мало рекомендует”, то главный кандидат в root node не математика как таковая, а свежесть и availability входов, прежде всего feature snapshot surface.

Если цель — понять “готова ли его математика к расширению authority”, то ответ отрицательный: сперва нужно доказать, что fee-aware / percent-notional / peak-giveback calibration улучшают realized net outcomes, а не просто красивее выглядят как observability surface.

Если цель — понять “актуально ли sidecar вообще работает”, то ответ положительный: работает, включён, wired, тестово подтверждён, forensic-данные присутствуют, bounded action path подтверждён.
