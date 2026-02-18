# NEOCORTEX R2 Dashboard Specification

## 1. Dashboard Set
- `Neocortex-R2-Overview`
- `Neocortex-R2-Reward-Contract`
- `Neocortex-R2-Training-Health`
- `Neocortex-R2-Alerts-Incidents`

## 2. Panel Contract (Required)
| Dashboard | Panel | Source | Visualization | Purpose |
|---|---|---|---|---|
| Overview | `buffer_size` | `adapter.stats` | line | Detect uncontrolled buffer growth |
| Overview | `inflight_tasks` | `adapter.stats` | line + max threshold | Detect queue saturation |
| Overview | `backpressure_events` (delta/5m) | `adapter.stats` | bar | Early deadlock/throughput signal |
| Overview | `shadow_intents_emitted` | `adapter.stats` | cumulative line | Shadow continuity |
| Reward Contract | Structured reward coverage | contract-test + runtime counters | gauge | Enforce Structured Only |
| Reward Contract | `waiting_for_reward_source` | `adapter.stats` | state timeline | Detect reward-source outages |
| Reward Contract | `WARN:NO_STRUCTURED_REWARD_RECEIVED` rate | `EVT:NEOCORTEX_ALERT` | bar | Upstream reward integrity |
| Training Health | `total_train_steps` | `adapter.stats` | cumulative line | Verify training progress |
| Training Health | `vae_loss`, `wm_loss`, `ppo_loss_*` | `neocortex_metrics.csv` | line | Model health baseline |
| Training Health | CPU fallback warning count | logs | stat | Capacity planning for no-GPU mode |
| Alerts | Alert volume by code | `EVT:NEOCORTEX_ALERT` | stacked bar | Incident pressure by class |
| Alerts | Open incidents SLA timer | incident tracker | table | Runbook execution control |

## 3. Alert-to-Panel Mapping
- `NO_STRUCTURED_REWARD_RECEIVED`:
  - Reward Contract dashboard (coverage and waiting state).
- `BRAIN_BRIDGE_UNAVAILABLE`:
  - Training Health dashboard (train steps flatline + warning spikes).
- `BACKPRESSURE_SUSTAINED`:
  - Overview dashboard (buffer/inflight/backpressure triple view).
- `TRAINING_QUEUE_SATURATED`:
  - Overview + Training Health dashboards.

## 4. Refresh and Retention
- Refresh interval:
  - Overview and Alerts: 10s.
  - Reward Contract and Training Health: 30s.
- Retention:
  - Raw events/metrics: 30 days.
  - Aggregated SLO snapshots: 90 days.

## 5. Dashboard DoD
- Every SLI in `NEOCORTEX_R2_OBSERVABILITY_SLO.md` has at least one directly mapped panel.
- Alert code -> panel route is one-to-one and documented.
- On-call can identify root-cause class within 5 minutes from dashboards only.
