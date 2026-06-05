<<<<<<< HEAD
# Контракти подій домену Alpha Search

## Вихідні події (Outbound)

### EVT:ALPHA_SCORE_CALCULATED
Головна подія домену, що несе торговий імпульс.

**Payload Схема:**
| Поле | Тип | Опис |
|------|-----|------|
| `model_name` | string | Назва моделі або `ensemble_X_models`. |
| `symbol` | string | Торговий тикер (напр. BTCUSDT). |
| `score` | Decimal | Оцінка напрямку [-1.0, 1.0]. |
| `confidence` | Decimal | Впевненість у сигналі [0.0, 1.0]. |
| `features_used` | list | Список назв ознак, використаних у розрахунку. |
| `why` | list | Ланцюжок логічних кроків (reasoning chain). |
| `contributions` | dict | (Опційно для Ensemble) Внесок кожної моделі (weight, score). |

**Приклад:**
```json
{
  "model_name": "ensemble_3_models",
  "symbol": "BTCUSDT",
  "score": 0.65,
  "confidence": 0.82,
  "why": ["Trend is up", "RSI is not overbought", "Volume confirms move"],
  "contributions": {
    "momentum": {"weight": 0.5, "score": 0.8},
    "mean_reversion": {"weight": 0.5, "score": 0.5}
  }
}
```

## Вхідні події (Inbound)

### EVT:FEATURES_CALCULATED
- **Джерело**: `feature_engineering`.
- **Дані**: Словник обчислених метрик.
- **Дія**: Запускає розрахунок альфа-сигналів.
=======
# Alpha Search Event Contracts

## 1. Scope

This document covers the runtime event surface owned by alpha_search in the current tree.

It also records nearby non-event contracts so readers do not confuse standalone file inputs, simulator artifacts, or shutdown automation with FSM events.

Contract discipline for this document:

- event names and emission conditions are taken from backtest_plugin.py and verb_registry_v1.yaml
- field-level payload details are documented only where they are explicitly assembled in code
- Phase 5 simulator outputs are treated as offline artifacts, not runtime events

## 2. Inbound Runtime Events

| Event surface | Default name | Purpose | Notes |
|---------------|--------------|---------|-------|
| configured feature_event | EVT:FEATURES_CALCULATED | cache feature snapshots | primary feature ingress for scoring |
| configured ta_feature_event | EVT:TA_FEATURES_CALCULATED | cache supplemental TA features | used when provider setup needs the separate TA plane |
| configured decision_event | CMD:PROCESS_STRATEGY | trigger scoring against cached same-bar features | scoring happens on this trigger, not on feature ingress |
| fixed runtime event | EVT:TRADE_EXECUTED | update shadow PnL and provider stats | not a scoring trigger |
| optional runtime event | EVT:OBJECTIVE_REALIZED_V1 | apply objective feedback | only listened to when objective feedback is enabled |

## 3. Outbound Runtime Events

| Event | Payload source | Emitted when | Boundary note |
|-------|----------------|--------------|---------------|
| configured emit_event, default EVT:ALPHA_SCORE_CALCULATED | explicit dict in _emit_score_event(...) and _emit_fail_closed_score(...) | a standard provider scores, or a fail-closed neutral score is emitted | judge expert providers are suppressed from this stream |
| EVT:JUDGE_EXPERT_PRODUCED_V1 | ExpertOutput.model_dump() | a judge expert provider runs in judge.mode=shadow | shadow-only evidence event |
| EVT:JUDGE_CHAMBER_AGGREGATED_V1 | chamber aggregation DTO model_dump() | entry chamber runs, and lifecycle chamber when enabled | shadow-only; not a decision_making input |
| EVT:JUDGE_EVIDENCE_ASSEMBLED_V1 | evidence envelope model_dump() | envelope assembly succeeds for a chamber result | shadow-only evidence envelope |
| EVT:JUDGE_ENTRY_VERDICT_V1 | synthesized verdict model_dump() | entry verdict synthesis succeeds and entry verdicts are enabled | shadow-only; no execution authority |
| EVT:JUDGE_LIFECYCLE_VERDICT_V1 | synthesized verdict model_dump() | lifecycle verdict synthesis succeeds and lifecycle verdicts are enabled | shadow-only; no execution authority |

## 4. Verified Payload Fields for EVT:ALPHA_SCORE_CALCULATED

The generic alpha-score event is the only alpha_search runtime event whose payload is assembled as a plain dict in the plugin. The verified fields are:

| Field | Meaning |
|-------|---------|
| provider_id | emitting provider key |
| model_name | model or fail-closed label |
| symbol | trading symbol |
| tf_sec | timeframe in seconds |
| bar_close_ts | normalized bar close timestamp |
| score | floating alpha score |
| confidence | floating confidence score |
| threshold | provider threshold used for interpretation |
| shadow | whether the plugin is running in shadow mode |
| signal_id | signal identifier for the score |
| why | truncated reasoning chain |
| features_used | feature names used by the provider |

Two important rules:

- judge expert providers must not leak into EVT:ALPHA_SCORE_CALCULATED
- fail-closed scoring may emit a neutral alpha event instead of raising or crashing the runtime

## 5. Shadow Event Semantics

The JUDGE_* event line belongs to alpha_search ownership in the current tree, but it is intentionally bounded.

- it is emitted only by the embedded plugin path
- it requires judge.mode=shadow
- it is evidence production, not trade-admission logic
- the current documented and runtime boundary treats these events as shadow-only and outside the decision_making trade-admission flow

This is the main place where earlier alpha_search docs were incomplete. The domain now owns more than the generic alpha-score stream.

## 6. Adjacent Non-Event Contracts

These are important alpha_search contracts, but they are not FSM events:

- alpha_input_v1.jsonl-style standalone inputs written or consumed by the historical runtime path
- config/judge_simulator.yaml for the offline simulator
- calibration dataset output written by the Phase 5 simulator
- summary report output written by the Phase 5 simulator
- simulator shutdown export itself, which is a shutdown hook and not an event emission surface

## 7. Non-Goals and Exclusions

The following should not be inferred from the event surface:

- no hybrid_advisory or live advisory mode exists in JudgeCortexConfig
- no JUDGE_* event grants execution_position or order-management authority
- no offline simulator step emits live FSM events back into the runtime loop
- no Phase 6 recommendation contract is implied by Phase 5 summary output
>>>>>>> 099d495c4eee1837ba188384663f5ef7ba426a9b
