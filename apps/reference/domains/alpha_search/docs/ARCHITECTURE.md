<<<<<<< HEAD
# Архітектура домену Alpha Search

## 1. Модельний фреймворк
Домен побудований на принципах плагінної архітектури. Кожна альфа-модель успадковується від `AlphaModel` і реалізує метод `calculate_alpha`.

### Ключові абстракції:
- **AlphaScore**: Контейнер для результату (score), впевненості (confidence) та ланцюжка обґрунтування (why).
- **AlphaModelRegistry**: Синхронізує розрахунок усіх активних моделей для конкретного символу.

## 2. Ensemble (Ансамбль)
`EnsembleModel` є спеціальним типом `AlphaModel`, який не розраховує власний сигнал, а агрегує результати інших моделей.

### Механізм зважування:
1. **Initial**: Рівні ваги для всіх моделей.
2. **Performance Tracking**: Збереження історії впевненості (proxy) або реального PnL (через feedback від `virtual_trader`).
3. **Rebalancing**: Періодичне (напр. раз на 7 днів) перерахування ваг за формулою нормалізованої продуктивності.

## 3. Конфігурація та Fail-Closed
Використовується сувора валідація через Pydantic (`AlphaSearchConfig`).
- **Extra="forbid"**: Забороняє невідомі поля в YAML, щоб уникнути помилок конфігурації.
- **Fail-Closed**: Якщо для моделі відсутні критичні ознаки (essential features), вона повертає score=0 з поясненням у полі `why`, замість зупинки всієї системи.

## 4. Життєвий цикл сигналу
1. **Trigger**: Отримання події `EVT:FEATURES_CALCULATED`.
2. **Validation**: Перевірка наявності необхідних ознак (`is_ready`).
3. **Calculation**: Паралельний або послідовний виклик `calculate_alpha` для всіх моделей у реєстрі.
4. **Ensembling**: Зважування сигналів в `EnsembleModel`.
5. **Emission**: Публікація `EVT:ALPHA_SCORE_CALCULATED`.
=======
# Alpha Search Architecture

## 1. Runtime Shapes and Entry Surfaces

alpha_search currently has two primary runtime shapes and five total architectural entry or operation surfaces:

1. embedded startup in apps/reference/main.py
2. historical standalone runtime under runtime/
3. offline simulator CLI under judge/simulator/cli.py
4. offline review CLI under judge/review/cli.py
5. optional shutdown-time automation from AlphaSearchBacktestPlugin.shutdown()

The important design fact is that these are related surfaces of one domain, not separate products. The current tree preserves the original standalone path while also exposing a configured embedded startup path in the main runtime.

## 2. Config Topology

alpha_search does not load through Aurora DomainsConfig.

- config/alpha_search.yaml loads into AlphaSearchConfig
- AlphaSearchConfig includes provider settings, trigger wiring, virtual-trader feedback, optional judge config, and optional simulator_shutdown_export
- judge runtime mode still comes from JudgeCortexConfig and remains bounded to off or shadow
- config/judge_simulator.yaml loads into the offline simulator config and stays outside JudgeCortexConfig
- config/judge_review.yaml loads review-only output and segmentation controls and reuses config/judge_simulator.yaml for bounded input authority

That split matters. The simulator and review tooling are owned by alpha_search, but they are not live runtime modes and they are not configured through the Aurora domain registry.

## 3. Embedded Plugin Flow

### 3.1 Feature Acquisition

AlphaSearchBacktestPlugin caches feature snapshots from the configured feature_event and, when needed, the configured ta_feature_event.

The cache is keyed by symbol, tf_sec, and normalized bar_close_ts so that scoring happens against the correct same-bar snapshot.

### 3.2 Decision-Time Scoring

When the configured decision_event arrives, the plugin resolves the cached snapshot for that bar and scores each enabled provider.

- standard providers emit EVT:ALPHA_SCORE_CALCULATED
- fail-closed scoring emits a neutral alpha event when configured to do so
- judge expert providers are explicitly suppressed from the generic alpha-score stream

This means alpha_search is not just a pure model registry anymore. In the embedded path it is a runtime bridge from cached features to scoring decisions and shadow evidence.

### 3.3 Virtual Feedback and Stats

The plugin also listens to EVT:TRADE_EXECUTED and optionally EVT:OBJECTIVE_REALIZED_V1.

These inputs update shadow PnL tracking, provider stats, and objective-feedback summaries. They do not grant alpha_search execution authority.

### 3.4 Judge Shadow Chain

When judge.mode=shadow, judge expert providers follow a separate path:

1. AlphaScore is translated into expert output
2. EVT:JUDGE_EXPERT_PRODUCED_V1 is emitted
3. chamber aggregation emits EVT:JUDGE_CHAMBER_AGGREGATED_V1
4. evidence assembly emits EVT:JUDGE_EVIDENCE_ASSEMBLED_V1
5. verdict synthesis emits EVT:JUDGE_ENTRY_VERDICT_V1 and optionally EVT:JUDGE_LIFECYCLE_VERDICT_V1

This chain is shadow-only. The current documented and runtime boundary treats it as evidence production, not as part of the decision_making trade-admission flow or any execution_position input line.

### 3.5 Bounded Failure Semantics

Failure behavior in the embedded path is intentionally bounded.

- if no same-bar snapshot is available, standard providers can emit fail-closed neutral scores instead of widening behavior silently
- if required TA or provider features are missing, the provider is skipped or fail-closed according to config
- judge expert providers are suppressed from the generic alpha-score stream when fail-closed conditions occur
- if chamber aggregation is not admitted because judge.mode is not shadow, the shadow chain simply does not widen further
- if evidence assembly or verdict synthesis fails, the chamber event can already exist but later evidence or verdict emission is skipped fail-closed

These failures stay bounded to shadow scoring and evidence production. They do not widen into live decision or execution authority.

### 3.6 Shutdown Export

AlphaSearchBacktestPlugin.shutdown() always performs plugin cleanup and may optionally invoke _run_simulator_shutdown_export().

When simulator_shutdown_export.enabled=true:

- the plugin loads config/judge_simulator.yaml through the existing simulator loader
- it reuses the same run_from_config(...) path as the standalone CLI
- it writes calibration and summary artifacts through the existing Phase 5 writers
- it fails closed and does not crash broader shutdown on simulator errors

Architecturally, this is bounded post-run automation of the offline simulator. It is not a live simulator mode.

## 4. Historical Standalone Runtime

The runtime/ subtree still matters because it preserves the original alpha_search operating model.

- runtime/feature_mirror_writer.py bridges mirrored feature snapshots into file-based inputs
- runtime/contracts.py defines the standalone input contract
- runtime/launcher.py executes standalone scoring
- scripts/runners/run_alpha_search_domain.py exposes the runner

This path is still the right mental model for isolated replay or shadow analysis. The embedded plugin path did not replace it; it added a second supported runtime shape.

## 5. Offline Evidence Tooling Architecture

### 5.1 Phase 5 Simulator

The Phase 5 simulator is a separate offline pipeline under judge/simulator/.

- CLI and programmatic orchestration live in cli.py
- exact-key correlation joins judge outputs to realized outcomes
- calibration and summary writers persist deterministic artifacts
- config, schema, and path validation are kept as bounded tooling

The simulator does not emit live FSM events and does not widen JudgeCortexConfig beyond off or shadow.

### 5.2 Phase 6 Review Tooling

The Phase 6 review tooling is a separate offline pipeline under judge/review/.

- CLI and programmatic orchestration live in judge/review/cli.py and judge/review/engine.py
- config/judge_review.yaml adds review-only output and segmentation controls
- the review config reuses config/judge_simulator.yaml instead of redefining verdict or outcome input authority
- bundle and CSV outputs summarize evidence coverage, chamber-only vs final-judge comparisons, suppression or UNKNOWN accounting, disagreement buckets, and calibration slices
- the review bundle must not emit a promotion verdict automatically

This tooling remains bounded to artifact generation. It does not change JudgeCortexConfig admission and does not add live decision or execution authority.

## 6. Stable Boundaries

The following architectural boundaries are deliberate and still authoritative:

- alpha_search has a configured embedded startup path in main.py but is still outside Aurora DomainsConfig
- judge shadow verdicts are evidence artifacts, not trade-admission authority
- the simulator and review tooling are offline-only even when the simulator is launched from shutdown export
- decision_making and execution_position remain outside alpha_search ownership
- Phase 6 semantics remain outside Phase 5 and outside the simulator summary contract

## 7. Why the Documentation Needed Rewriting

Earlier internal docs described alpha_search mostly as a model framework that emits EVT:ALPHA_SCORE_CALCULATED. That is historically incomplete under the current tree.

The correct architecture model is broader: alpha_search is now a dual-shape strategy-analysis domain with an embedded plugin path, a preserved standalone path, a shadow judge evidence chain, and an offline simulator plus bounded shutdown handoff.
>>>>>>> 099d495c4eee1837ba188384663f5ef7ba426a9b
