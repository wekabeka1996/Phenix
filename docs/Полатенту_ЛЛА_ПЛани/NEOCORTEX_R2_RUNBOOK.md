# NEOCORTEX R2 Shadow Runbook

## 1. Purpose
- Operational response for R2 Shadow runtime incidents.
- Scope: ingestion/training pipeline, structured reward contract, shadow output continuity.

## 2. Preconditions
- Mandatory dashboards are available:
  - `NEOCORTEX_R2_DASHBOARDS_SPEC.md`
- SLO targets are active:
  - `NEOCORTEX_R2_OBSERVABILITY_SLO.md`
- Contract tests are in mandatory profile:
  - `tests/domains/execution_position/test_execpos_position_closed_emission_v1.py`
  - `tests/domains/execution_position/test_execpos_to_neocortex_position_closed_contract_v1.py`

## 3. Alert Playbooks

### 3.1 `WARN:NO_STRUCTURED_REWARD_RECEIVED`
- Impact: training is blocked by no-fallback policy; ingestion remains active.
- Verify:
  - `waiting_for_reward_source == true`
  - `EVT:POSITION_CLOSED` payloads missing `realized_pnl_net`
- Actions:
  1. Run contract tests for `execution_position -> neocortex`.
  2. Verify upstream close-event payload fields in staging logs/events.
  3. Keep training paused; do **not** enable equity-delta fallback.
  4. Escalate to `execution_position` owner if missing field rate > 0.
- Exit:
  - 50+ consecutive close events with complete structured payload.
  - `waiting_for_reward_source == false` stable for 10 minutes.

### 3.2 `WARN:BRAIN_BRIDGE_UNAVAILABLE`
- Impact: ingestion active, training degraded/paused.
- Verify:
  - Worker startup logs contain device/runtime failure details.
  - `total_train_steps` flatline while features still ingest.
- Actions:
  1. Check worker process lifecycle and checkpoint path permissions.
  2. Validate CPU fallback path:
     - If GPU unavailable, system must stay on CPU with warning only.
  3. Restart Neocortex domain if bridge failed during bootstrap.
  4. If repeated failure, disable training path and keep shadow ingestion for data continuity.
- Exit:
  - Worker healthy and `total_train_steps` increments.

### 3.3 `WARN:BACKPRESSURE_SUSTAINED`
- Impact: throughput pressure; risk of stale training loop.
- Verify:
  - Growth in `backpressure_events`.
  - `inflight_tasks` near capacity.
  - `buffer_size` trend not returning to baseline.
- Actions:
  1. Increase `brain_workers` only if CPU budget permits.
  2. Raise `dream_episode_threshold` (>=5 in production when dream enabled).
  3. Reduce training trigger frequency or batch pressure.
  4. Confirm no dead task leakage during shutdown/startup cycle.
- Exit:
  - `backpressure_events` delta below warning threshold for 15 minutes.

### 3.4 `WARN:TRAINING_QUEUE_SATURATED`
- Impact: new training batches are deferred.
- Verify:
  - `inflight_tasks == max_inflight_tasks` for sustained interval.
- Actions:
  1. Check slow batch root cause (`vae_loss/wm_loss` spikes, CPU starvation).
  2. Reduce concurrency or batch size to stabilize latency.
  3. Validate no stuck background tasks.
- Exit:
  - Queue utilization < 85% p95 over 15 minutes.

## 4. Incident Severity Model
- `P1`:
  - Structured reward contract broken in staging/prod.
  - Any attempted proxy-reward reintroduction.
- `P2`:
  - Training unavailable > 15 minutes with ingestion healthy.
- `P3`:
  - Intermittent backpressure saturation without data loss.

## 5. Rollback / Freeze Rules
- If SLI-01 or SLI-06 fail: block phase progression immediately.
- Rollback target: last known-good Neocortex build and checkpoint set.
- Allowed degraded mode:
  - bridge unavailable -> training off, ingestion on.
- Not allowed:
  - enabling equity-delta reward fallback for R2.

## 6. Postmortem Minimum
- Required fields:
  - trigger alert code
  - impacted SLI/SLO
  - time-to-detect
  - time-to-mitigate
  - prevention tasks with owners and ETA
