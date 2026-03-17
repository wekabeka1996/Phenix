# FORENSIC DEAD-STATE PROOF (2026-03-16)

## 1) Scope and constraints
- Goal: prove why live trading is effectively blocked.
- Evidence sources only: code + WAL + simulation tests.
- No runtime code changes, no WAL edits.
- Branch/context: Phenix_v2.

## 2) Simulation test evidence (executed now)
### 2.1 Contract + startup hydration tests
Command:
- `pytest -q tests/integration/test_fe_emits_cmd_process_strategy.py tests/bootstrap/test_startup_basis_hydrator.py tests/bootstrap/test_startup_basis_real_path.py`

Result:
- `30 passed, 2 skipped`.

Interpretation:
- FE command contract and hydration logic are valid in test harness.
- This does NOT disprove live failure; it means the failure is environment/path provenance dependent.

### 2.2 Alpha-search synthetic path tests
Command:
- `pytest -q tests/apps/reference/domains/alpha_search/tests/test_scenario_worker.py`

Result:
- `25 passed`.

Interpretation:
- Synthetic ScenarioWorker pipeline is active and valid in isolation.
- ScenarioWorker emits `CMD:PROCESS_STRATEGY` payload that is intentionally minimal (no full `bar`, no `features`, no `warmup` in phase-2 command payload), see code chain below.

## 3) Code chain proof (producer -> routing -> consumer)

### 3.1 SSOT and FE contract path
- Verb registry points to FE schema for `CMD:PROCESS_STRATEGY`:
  - `apps/reference/dictionaries/verb_registry_v1.yaml:22`
  - `apps/reference/dictionaries/verb_registry_v1.yaml:25`
- Schema requires `tf_sec` and constrains `tf_sec >= 60`:
  - `apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json:11`
  - `apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json:341`

### 3.2 FE live emitter is fail-closed for bad tf/bar
- FE gate `tf_sec < 60` blocks command:
  - `apps/reference/domains/feature_engineering/feature_engineering.py:1668`
- FE gate for missing bar_close_ts / missing OHLCV blocks command:
  - `apps/reference/domains/feature_engineering/feature_engineering.py:1708`
  - `apps/reference/domains/feature_engineering/feature_engineering.py:1719`
- FE emits `CMD:PROCESS_STRATEGY` only after all gates:
  - `apps/reference/domains/feature_engineering/feature_engineering.py:1819`

### 3.3 Alternative synthetic emitter path exists
- ScenarioWorker explicitly emits `CMD:PROCESS_STRATEGY` in phase-2 with minimal payload:
  - `apps/reference/domains/alpha_search/runtime/scenario_worker.py:141`
  - `apps/reference/domains/alpha_search/runtime/scenario_worker.py:150`
- In this synthetic path, payload includes `symbol/tf_sec/bar_close_ts/regime` only; it does not include full FE bar/features/warmup payload.

### 3.4 Consumer fail-closed behavior
- Aurora rejects when `tf_sec` missing or `tf_sec=0`:
  - `apps/reference/domains/decision_making/aurora_handler.py:633`
  - `apps/reference/domains/decision_making/aurora_handler.py:649`
- Mean reversion rejects when `tf_sec` missing or bar missing:
  - `apps/reference/domains/decision_making/mean_reversion_handler.py:1421`
  - `apps/reference/domains/decision_making/mean_reversion_handler.py:1469`

## 4) WAL proof (2026-03-16)

### 4.1 Command-contract failure evidence
Computed from WAL:
- `TOTAL_REJECT=2558`
- `BAD_TF=294` (NRR-046 with missing/zero tf_sec patterns)
- `LIVE_BAD_TF=273`
- `SYNTH_BAD_TF=21`

Meaning:
- tf_sec contract break is large and present in live timestamp segment, not only synthetic.

### 4.2 Synthetic contamination markers in same WAL
Computed from WAL:
- `TINY_TS_EVENTS=6873` (timestamps far below live epoch range)
- `RID_NUMERIC_EVENTS=42` (patterns like `rid-1`, `rid-2`)
- `TRADE_INTENT_PROPOSED` strategy groups:
  - `mean_reversion: 44`
  - `strat_A: 14`

Meaning:
- same WAL stream contains both live-like and synthetic/test-like producers.
- presence of `strat_A`/`rid-1` style markers proves mixed provenance.

### 4.3 Readiness/cold-start persistence evidence
Observed in WAL reject payloads:
- repeated `BARS_REQUIRED_COLD_START` with low counters like `4/301`, `5/301` etc.

Meaning:
- startup seed/hydration did not materialize enough local readiness bars for active handler counters before trading loop.

## 5) Root-cause classification
Primary classification: **D + C**
- **D (orchestration/routing/provenance mixing)**: mixed producer provenance in same runtime/WAL stream.
- **C (both A and B simultaneously)**:
  - **A**: command contract breaks (`missing tf_sec`, `tf_sec=0`, missing bar context).
  - **B**: startup readiness remains cold (`BARS_REQUIRED_COLD_START`) due to insufficient effective seeding.

Why system does not trade:
1. invalid command payloads are rejected fail-closed before signal generation;
2. even valid cadence hits readiness gate due to low `bars_seen_since_restart` vs required basis bars.

## 6) Non-fantasy boundary (what is and is not proven)
Proven directly by code + WAL + tests:
- FE production path itself has strict gates and cannot intentionally emit tf_sec<60.
- alternative synthetic command producer exists and is tested.
- mixed provenance markers exist in the same WAL day.
- fail-closed rejects and cold-start rejects are both active at high volume.

Not claimed without extra instrumentation:
- exact single process/thread that injected each malformed command event in live run.

## 7) Fix plan (phased, code targets)

### Phase 1: Producer provenance isolation (highest priority)
- Add mandatory provenance tags for `CMD:PROCESS_STRATEGY` (`producer_id`, `source_mode`, `ingress_path`).
- Enforce routing policy: synthetic/standalone producers cannot publish into live decision bus.
- Targets:
  - `apps/reference/main.py`
  - `apps/reference/domains/alpha_search/runtime/scenario_worker.py`
  - bus ingress wrappers around `fsm.emit`.

### Phase 2: Ingress schema hard-fail for CMD in live mode
- At decision ingress, reject any CMD lacking full required contract in live mode before strategy handlers.
- Targets:
  - `vfoundation/core/fsm_core.py` validation policy wiring
  - `apps/reference/domains/decision_making/*` ingress guards.

### Phase 3: Startup seed materialization gate
- Do not release startup warmup gate until handler diagnostics confirm seeded bars are materialized for each required strategy/symbol/timeframe.
- Targets:
  - `apps/reference/bootstrap/startup_basis_hydrator.py`
  - `apps/reference/main.py` startup gate release branch.

### Phase 4: Regression tests to prevent recurrence
- Add tests for:
  1) no synthetic CMD on live bus,
  2) mandatory provenance fields for CMD,
  3) startup gate release blocked when seeded<required,
  4) WAL audit checker for mixed tiny-ts/rid synthetic markers in live sessions.

## 8) Operational verification checklist after fixes
1. WAL for live day shows zero `strat_A`/`rid-1` style artifacts.
2. `NRR-046` from missing/zero tf_sec drops to zero.
3. First post-start basis counters are near required threshold (not 1/301, 4/301).
4. Trade intents from intended live strategies only.

---
Generated from direct repo code inspection, executed pytest sessions, and WAL queries on `ops/wal/2026-03-16.jsonl`.
