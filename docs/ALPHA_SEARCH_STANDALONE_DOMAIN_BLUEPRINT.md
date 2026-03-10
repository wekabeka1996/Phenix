# ALPHA SEARCH: Standalone Domain Blueprint v2.1 (Fixed)

**Status:** FINAL IMPLEMENTATION PLAN
**Date:** 2026-02-23
**Owner:** Alpha Search Domain
**Applies to:** `apps/reference/domains/alpha_search/`

---

## 0. Objective and Non-Negotiable Requirements

This blueprint defines a production-grade expansion of `alpha_search` into a standalone domain process with zero runtime dependency on `apps/reference/main.py`.

Mandatory requirements:

1. Standalone launcher and reactor, independent from `apps/reference/main.py`.
2. Shadow mode execution with virtual PnL only (no order routing).
3. Concurrent scenario matrix with **10 scenarios now**, configurable scale to **20+** without code changes.
4. Scenario matrix must include **Aurora**, **Mean Reversion**, and **Ensemble** strategy variants.
5. Each scenario must support:
   - dedicated config identity,
   - dedicated log folder,
   - dedicated metrics and PnL state.
6. Scenario config support in two modes:
   - `override` mode (fast deltas),
   - `full_config` mode (full config files identical in structure to `config/aurora/*`).
7. Runtime must subscribe (via replay or mirror stream) to all required features/events for scoring and decision simulation.
8. Hot-reload of scenario matrix/configs for live shadow sessions, with safe swap and rollback.

Out of scope for this plan:

- Real order execution from standalone runtime.
- Replacing production DecisionMaking in this phase.

---

## 1. Current-State Audit (Fact Baseline)

Key baseline facts from repository state:

- `alpha_search` is initialized from `apps/reference/main.py` and not independently launched today.
- `alpha_search` provider stack already supports `aurora` and `ta_ensemble` in `config/alpha_search.yaml`.
- Mean reversion strategy config exists as first-class strategy profile:
  - `config/aurora/strategies/mean_reversion.yaml`
- Aurora strategy SSOT exists:
  - `config/aurora/strategies/aurora.yaml`
- Model parameter SSOT for TA stack exists:
  - `config/alpha_search_system.yaml`
- Current blueprint v2.0 is strong on Aurora fan-out but under-specifies:
  - mean reversion and ensemble scenario axes,
  - scale controls for 20+ scenarios,
  - per-scenario log folders,
  - full-config scenario mode,
  - live feature subscription contract depth,
  - operational hot reload.

---

## 2. Gap Closure Matrix (v2.0 -> v2.1)

| Gap | v2.1 Resolution |
|---|---|
| Mean reversion not explicit axis | Add `strategy_type: aurora | mean_reversion | ensemble`; scenario matrix includes all 3 families |
| 10 -> 20 scaling only implicit | Add runtime capacity block: `max_scenarios`, `max_concurrent_scenarios`, `parallelism`, `max_workers`, memory budget, timeouts, backpressure |
| Per-scenario logging weak | Add required directory schema and scenario logger factory with rotating handlers per scenario |
| Only flat overrides | Add dual mode: `override` and `full_config`; full mode loads full files from scenario folder |
| Feature subscription incomplete | Define `alpha_input_v1` required fields and mirror subscriptions including regime/warmup/decision context |
| No hot reload | Add config watcher + safe-swap generation model + rollback rules |

---

## 3. Target Architecture (Standalone Domain)

```
                         +-------------------------------------------+
                         | alpha_search standalone process            |
                         | scripts/run_alpha_search_domain.py         |
                         +----------------------+--------------------+
                                                |
                       +------------------------v-------------------------+
                       | Ingest Gateway                                  |
                       | replay CSV/JSONL OR live mirror tail stream     |
                       +------------------------+-------------------------+
                                                |
                         validates alpha_input_v1 (fail-closed)
                                                |
                       +------------------------v-------------------------+
                       | Scenario Manager                                 |
                       | - loads matrix                                   |
                       | - owns worker pool                               |
                       | - hot reload safe swap                           |
                       +---------+----------------------+-----------------+
                                 |                      |
                 +---------------v----+      +----------v---------------+
                 | Scenario Worker S01| ...  | Scenario Worker SN       |
                 | type=aurora/mr/ens |      | isolated state           |
                 | shadow_book + stats |      | shadow_book + stats      |
                 +----------+----------+      +-----------+-------------+
                            |                                 |
             +--------------v---------------+  +-------------v--------------+
             | logs/.../S01/...             |  | logs/.../SN/...            |
             | scores,trades,metrics,health |  | scores,trades,metrics      |
             +------------------------------+  +----------------------------+

Aggregate writer -> reports/alpha_search_runtime/<session>/aggregate/*
```

Hard boundaries:

- Runtime MUST NOT import `apps/reference/main.py`.
- Runtime MUST NOT emit execution commands.
- Any invalid scenario config or contract violation MUST fail closed.

---

## 4. Scenario System Design (Aurora + MR + Ensemble)

### 4.1 Strategy Types

Each scenario is one of:

- `aurora`: uses Aurora scoring config shape from `config/aurora/strategies/aurora.yaml`.
- `mean_reversion`: uses MR strategy config shape from `config/aurora/strategies/mean_reversion.yaml` and TA model params from `config/alpha_search_system.yaml`.
- `ensemble`: uses combined TA model weights and model toggles from `config/alpha_search.yaml` + `config/alpha_search_system.yaml`.

### 4.2 Scenario Matrix File (SSOT)

Rename matrix to non-hardcoded filename:

- `config/alpha_search/scenario_matrix.yaml`

Example skeleton:

```yaml
matrix_id: alpha_search_shadow_v2
version: 2

runtime:
  min_scenarios: 10
  max_scenarios: 20
  max_concurrent_scenarios: 20
  parallelism: process_pool        # sequential | thread_pool | process_pool
  max_workers: 4
  queue_maxsize: 4000
  backpressure_policy: drop_oldest # drop_oldest | drop_newest | block
  memory_budget_mb_per_scenario: 50
  scenario_timeout_sec: 5
  health_heartbeat_sec: 30
  hot_reload:
    enabled: true
    mode: safe_swap
    poll_interval_sec: 5
    debounce_sec: 2
    rollback_on_error: true

input:
  source_mode: replay_or_live_shadow
  stream_path: logs/alpha_input/alpha_input_v1.jsonl

scenarios:
  - scenario_id: S01_AURORA_BASELINE
    enabled: true
    strategy_type: aurora
    config_mode: full_config
    scenario_config_dir: config/alpha_search/scenarios/S01_AURORA_BASELINE

  - scenario_id: S02_AURORA_AGGRESSIVE
    enabled: true
    strategy_type: aurora
    config_mode: override
    base_refs:
      aurora: config/aurora/strategies/aurora.yaml
      alpha_search: config/alpha_search.yaml
    overrides:
      aurora.decision.signal_threshold: 0.12
      aurora.decision.gates.anti_flat_sigma: 0.35

  - scenario_id: S11_MR_AGGRESSIVE_BB
    enabled: true
    strategy_type: mean_reversion
    config_mode: override
    base_refs:
      mean_reversion: config/aurora/strategies/mean_reversion.yaml
      alpha_search_system: config/alpha_search_system.yaml
    overrides:
      alpha_search_system.mean_reversion.weights.bb: 0.6
      alpha_search_system.mean_reversion.weights.rsi: 0.2

  - scenario_id: S12_MR_RSI_25_75
    enabled: true
    strategy_type: mean_reversion
    config_mode: override
    base_refs:
      mean_reversion: config/aurora/strategies/mean_reversion.yaml
      alpha_search_system: config/alpha_search_system.yaml
    overrides:
      alpha_search_system.mean_reversion.rsi.oversold: 25
      alpha_search_system.mean_reversion.rsi.overbought: 75

  - scenario_id: S15_ENSEMBLE_MR_DOMINANT
    enabled: true
    strategy_type: ensemble
    config_mode: override
    base_refs:
      alpha_search: config/alpha_search.yaml
      alpha_search_system: config/alpha_search_system.yaml
    overrides:
      alpha_search.providers.ta_ensemble.ensemble.models.mean_reversion_v1.enabled: true
      alpha_search.providers.ta_ensemble.ensemble.models.momentum_v1.enabled: true
      alpha_search.providers.ta_ensemble.ensemble.models.volatility_v1.enabled: true
      alpha_search_system.ensemble.model_weights.mean_reversion_v1: 0.7
      alpha_search_system.ensemble.model_weights.momentum_v1: 0.2
      alpha_search_system.ensemble.model_weights.volatility_v1: 0.1
```

### 4.3 Config Modes

`override` mode:

- Start from base refs.
- Apply allowlisted overrides.
- Validate via strict Pydantic schemas.
- Persist resolved effective config to runtime manifest.

`full_config` mode:

- Load full config files from scenario directory.
- Enforce file shape parity with corresponding base SSOT structures.
- No implicit inheritance unless explicitly declared.

Scenario directory pattern:

```
config/alpha_search/scenarios/
  S01_AURORA_BASELINE/
    aurora.yaml
    alpha_search.yaml
    alpha_search_system.yaml
    virtual_trader.yaml
  S11_MR_AGGRESSIVE_BB/
    mean_reversion.yaml
    alpha_search_system.yaml
    virtual_trader.yaml
```

---

## 5. Logging and Artifact Isolation (Per Scenario)

Required runtime output layout:

```
logs/alpha_search_runtime/
  <session_id>/
    aggregate/
      aggregate.jsonl
      aggregate_metrics.csv
      health.jsonl
    S01_AURORA_BASELINE/
      scores.jsonl
      trades.jsonl
      metrics.csv
      config_effective.yaml
      health.jsonl
    S02_AURORA_AGGRESSIVE/
      scores.jsonl
      trades.jsonl
      metrics.csv
      config_effective.yaml
      health.jsonl
    ...
```

Implementation requirements:

- `ScenarioLoggerFactory` creates dedicated logger per `scenario_id`.
- Each scenario logger gets its own rotating file handlers.
- No shared write handler across scenarios except aggregate channel.

---

## 6. Input Contract and Feature Subscription

### 6.1 `alpha_input_v1` (Required Fields)

Minimum required fields (strict):

- `ts_ms`, `symbol`, `tf_sec`, `bar_close_ts`, `price`
- `features` object (required feature subset by strategy type)
- `regime` (required in live mode)
- `warmup_status` (required in live mode)
- `source_verb` and `source_trace_id`

Strategy-specific required feature sets:

- Aurora: `obi`, `delta_price`, `macro_resid` (+ optional directional/strength extras)
- Mean reversion: `bb_position`, `bb_width`, `rsi_14`, `price_sma_20_deviation`, `stoch_k`, `stoch_d`
- Ensemble: union of enabled TA model required features

### 6.2 Ingestion Modes

Phase A (replay):

- Use existing recorder outputs and convert to `alpha_input_v1.jsonl`.

Phase B (live shadow):

- Add `FeatureMirrorWriter` plugin in main process.
- Mirror writer subscribes to:
  - `EVT:FEATURES_CALCULATED`
  - `EVT:REGIME_DETECTED`
  - `EVT:BAR_CLOSED`
  - optional `CMD:PROCESS_STRATEGY` metadata when available
- Mirror writer emits a canonical JSONL stream consumed by standalone runtime.

Failure policy:

- Missing required fields for active strategy type -> reject snapshot.
- Input validation error rate above threshold -> fail closed.

---

## 7. Concurrency, Capacity, and Backpressure

Execution model config:

- `parallelism`: `sequential`, `thread_pool`, `process_pool`
- `max_workers`: explicit worker cap
- `max_concurrent_scenarios`: hard limit for active workers
- `scenario_timeout_sec`: per snapshot per worker timeout

Backpressure policy:

- bounded ingest queue (`queue_maxsize`)
- policy-driven overflow handling:
  - `drop_oldest` for live low-latency mode (default)
  - `block` for deterministic replay

Scale guarantees:

- v1 target: stable at 10 concurrent scenarios
- v1.1 target: stable at 20 concurrent scenarios with process pool and bounded memory

Resource controls:

- enforce per-scenario memory budget
- periodic memory sampling per worker
- auto-degrade strategy when budget exceeded (mark scenario degraded, no global crash)

---

## 8. Hot Reload Design (Live Shadow)

Hot reload goals:

- change scenario count (10 -> 20, 20 -> 12) without process restart
- change scenario configs without stopping other healthy scenarios

Mechanism:

1. `ConfigWatcher` polls matrix and scenario dirs.
2. On content hash change, build `generation=N+1` candidate plan.
3. Validate all changed scenarios first (dry-run parse + schema validation).
4. Apply with safe swap:
   - new/changed scenarios: start new workers,
   - removed scenarios: drain and finalize,
   - unchanged scenarios: continue.
5. If any validation/apply step fails, rollback to last healthy generation.

Observability:

- emit reload events to aggregate health log:
  - `RELOAD_DETECTED`, `RELOAD_APPLIED`, `RELOAD_ROLLBACK`.

---

## 9. Implementation Roadmap (Fixed)

### Phase 0: Contracts and Schema Freeze

Scope:

1. Finalize `alpha_input_v1` and `alpha_shadow_result_v1` schemas.
2. Introduce strict matrix schema v2 with strategy types and dual config mode.
3. Define override allowlists per strategy type.

DoD:

- Contract tests pass.
- Matrix v2 validates mixed Aurora/MR/Ensemble scenarios.

### Phase 1: Standalone Runtime Skeleton + Baseline Parity

Scope:

1. Build launcher and ingest gateway.
2. Implement single scenario worker for `S01_AURORA_BASELINE`.
3. Verify score parity against current plugin for baseline snapshots.

DoD:

- Standalone replay works.
- No imports from `apps/reference/main.py`.
- Baseline parity tests pass.

### Phase 2: Mixed Strategy Matrix + Per-Scenario Isolation

Scope:

1. Implement scenario manager for mixed strategy types.
2. Add shadow books per scenario.
3. Add per-scenario logging directory and logger factory.
4. Add `full_config` mode and effective config materialization.

DoD:

- 10 mixed scenarios run concurrently.
- Per-scenario logs and PnL are isolated.
- Full-config and override modes both validated.

### Phase 3: 20+ Scaling and Runtime Controls

Scope:

1. Add configurable parallelism backend.
2. Add bounded queue + backpressure policies.
3. Add timeout, memory budget, and degradation controls.

DoD:

- Stable replay/live at 20 configured scenarios.
- No global crash on single-scenario timeout/failure.

### Phase 4: Live Shadow Feature Mirror

Scope:

1. Implement `FeatureMirrorWriter` subscriptions.
2. Feed standalone runtime via canonical stream.
3. Add lag telemetry and health heartbeat.

DoD:

- Live shadow runs continuously with required event coverage.
- Processing lag and data quality SLO met.

### Phase 5: Hot Reload + Operations Hardening

Scope:

1. Add config watcher with safe swap.
2. Add rollback behavior and reload event audit.
3. Finalize runbook.

DoD:

- Matrix/config changes apply without restart.
- Bad reload safely rolls back.

---

## 10. File-Level Backlog

New files:

- `apps/reference/domains/alpha_search/runtime/launcher.py`
- `apps/reference/domains/alpha_search/runtime/ingest.py`
- `apps/reference/domains/alpha_search/runtime/scenario_manager.py`
- `apps/reference/domains/alpha_search/runtime/scenario_worker.py`
- `apps/reference/domains/alpha_search/runtime/shadow_book.py`
- `apps/reference/domains/alpha_search/runtime/logger_factory.py`
- `apps/reference/domains/alpha_search/runtime/hot_reload.py`
- `apps/reference/domains/alpha_search/runtime/reporting.py`
- `scripts/run_alpha_search_domain.py`
- `config/alpha_search/scenario_matrix.yaml`
- `schemas/alpha_input_v1.json`
- `schemas/alpha_shadow_result_v1.json`

Changed files:

- `apps/reference/domains/alpha_search/config_models.py`
- `apps/reference/domains/alpha_search/models/aurora_adapter.py`
- `apps/reference/main.py` (only for optional `FeatureMirrorWriter` plugin)

Config folders to add:

- `config/alpha_search/scenarios/<SCENARIO_ID>/...`

---

## 11. Testing Strategy

Unit:

- matrix schema validation (mixed strategy types)
- override allowlist enforcement by strategy type
- full-config parity validation
- scenario logger path isolation
- hot reload diff planning and rollback

Integration:

- replay 10 mixed scenarios
- replay 20 scenarios with process pool
- baseline parity (`S01_AURORA_BASELINE`)
- live shadow ingest from mirror stream

Failure and safety:

- malformed input stream
- unknown override path
- scenario timeout and worker crash isolation
- reload with invalid config -> rollback

Performance:

- p95 end-to-end snapshot latency under 10 and 20 scenarios
- memory stability over long session
- queue pressure and drop policy behavior

---

## 12. SLO and Capacity Targets (v2.1)

| Metric | Target |
|---|---|
| Replay determinism | exact output match for same input |
| p95 processing lag (10 scenarios) | <= 500 ms |
| p95 processing lag (20 scenarios) | <= 1200 ms |
| Runtime availability (live shadow) | >= 99.5% |
| Invalid snapshot reject behavior | fail closed, no silent fallback |
| Scenario isolation | strict (one scenario failure does not crash others) |
| Memory growth | <= 50 MB/hour under nominal load |

---

## 13. Acceptance Checklist

- [ ] Standalone launch works without `apps/reference/main.py` dependency.
- [ ] Scenario matrix supports Aurora, Mean Reversion, Ensemble types.
- [ ] 10 scenarios run concurrently in shadow mode.
- [ ] 20 scenario scale works via config controls.
- [ ] Both config modes work: `override` and `full_config`.
- [ ] Every scenario writes to its own log directory.
- [ ] Input contract includes all required feature and regime context.
- [ ] Live mirror subscriptions cover required upstream events.
- [ ] Hot reload applies safe changes and rolls back on invalid update.
- [ ] Baseline parity test passes for `S01_AURORA_BASELINE`.

---

## 14. Recommended Initial Scenario Set (10)

Aurora family:

1. `S01_AURORA_BASELINE`
2. `S02_AURORA_AGGRESSIVE`
3. `S03_AURORA_CONSERVATIVE`
4. `S04_AURORA_OBI_HEAVY`

Mean reversion family:

5. `S11_MR_BASELINE`
6. `S12_MR_RSI_25_75`
7. `S13_MR_BB_HEAVY`

Ensemble family:

8. `S15_ENSEMBLE_BALANCED`
9. `S16_ENSEMBLE_MR_DOMINANT`
10. `S17_ENSEMBLE_MOMENTUM_DOMINANT`

This 4/3/3 split gives immediate coverage of all requested strategy axes while keeping baseline comparability.

---

## 15. Key Repository References

- `apps/reference/main.py`
- `apps/reference/domains/alpha_search/backtest_plugin.py`
- `apps/reference/domains/alpha_search/models/aurora_adapter.py`
- `apps/reference/domains/alpha_search/models/mean_reversion.py`
- `apps/reference/domains/alpha_search/ensemble.py`
- `config/alpha_search.yaml`
- `config/alpha_search_system.yaml`
- `config/aurora/strategies/aurora.yaml`
- `config/aurora/strategies/mean_reversion.yaml`
- `apps/reference/domains/neocortex/main.py`

