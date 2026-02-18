# NEOCORTEX R2 Observability SLO

## 1. Scope
- Scope: `execution_position -> neocortex` reward contract, shadow inference stability, and training loop health in R2 Shadow mode.
- Applies to staging canary and production shadow rollout.
- Reward policy: **Structured Only** (`EVT:POSITION_CLOSED.realized_pnl_net`), no proxy fallback.

## 2. Data Sources
- `EVT:NEOCORTEX_ALERT` stream.
- `NeocortexAdapter.stats` snapshot fields:
  - `buffer_size`
  - `inflight_tasks`
  - `backpressure_events`
  - `waiting_for_reward_source`
  - `total_train_steps`
  - `shadow_intents_emitted`
- `logs/neocortex_metrics.csv` from `TelemetryLogger`.
- Contract integration tests:
  - `tests/domains/execution_position/test_execpos_position_closed_emission_v1.py`
  - `tests/domains/execution_position/test_execpos_to_neocortex_position_closed_contract_v1.py`

## 3. SLI/SLO Table
| ID | SLI | Formula | SLO Target | Alert Threshold |
|---|---|---|---|---|
| SLI-01 | Structured Reward Coverage | `episodes_with_structured_reward / total_position_closed_events` | `100%` (R2 hard requirement) | `WARN < 100% for 5m`, `CRIT < 99.5% for 1m` |
| SLI-02 | Reward Source Readiness | `waiting_for_reward_source == false` during active close-flow | `>= 99.9% uptime` | `WARN state=true > 60s`, `CRIT > 300s` |
| SLI-03 | Backpressure Stability | delta(`backpressure_events`) over 5m | `< 50 / 5m` steady-state | `WARN >= 50`, `CRIT >= 200` |
| SLI-04 | Training Queue Health | `inflight_tasks / max_inflight_tasks` | `<= 0.85 p95` | `WARN > 0.90 for 5m`, `CRIT > 1.0 for 1m` |
| SLI-05 | Shadow Output Continuity | `shadow_intents_emitted` monotonic growth while features ingress active | no unexpected flatline > 5m | `WARN flatline > 5m` |
| SLI-06 | Contract Conformance | integration contract tests green on mandatory profile | `100% pass` | any failure = release blocker |

## 4. Error Budget Policy
- Budget window: 30 days.
- SLI-01 and SLI-06 are **hard gates** (zero budget).
- For SLI-02..SLI-05:
  - Warning budget burn > 30%: freeze feature rollout, continue shadow canary only.
  - Critical budget burn > 60%: stop Phase advancement, incident review required.

## 5. Gate G3 Exit Criteria
- 7 consecutive days on staging/canary with:
  - SLI-01 = 100%.
  - SLI-06 = 100%.
  - No unresolved CRIT alerts for SLI-02..SLI-05.
- Runbook drills completed for:
  - `NO_STRUCTURED_REWARD_RECEIVED`
  - `BRAIN_BRIDGE_UNAVAILABLE`
  - `BACKPRESSURE_SUSTAINED`
  - `TRAINING_QUEUE_SATURATED`

## 6. CPU/GPU Runtime Requirement
- CPU-only execution is allowed and supported.
- If GPU is unavailable or disabled, runtime must:
  - continue on CPU without crash,
  - emit warning-level logs/alerts,
  - keep ingestion active.
- This behavior is validated in `BrainCore._resolve_device()` and `brain.worker` startup logs.
