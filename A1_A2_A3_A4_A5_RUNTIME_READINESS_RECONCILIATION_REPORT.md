# AGENT_REPORT_V1

## Executive Summary
`RUNTIME_READY_WITH_RESIDUALS`

Clean new runtime startup is admissible for the repaired A1/A3/A4/A5 critical paths and for the live A2 LOW_VOL gate path, but package closure is not uniformly green. The remaining failures are current-tree test or tooling drift, deferred A4 read-side cutover, and A5 dead-surface or frozen-snapshot residue. No evidence in this audit shows an active blocker on the write or execute critical path.

## Proven Facts
- A1 executable proof passed: `tests/domains/decision_making/test_intent_builder_payload_contract.py` finished `4 passed`.
- Current A2 config in `config/aurora/domains.yaml` uses `raw_signed_score_sources: [signal_score, final_score]`, `normalized_confidence_sources: [strategy_confidence]`, `judge_confidence_live_producer_required: false`, `min_raw_score_by_regime.LOW_VOLATILITY = 0.25`, and `min_normalized_confidence_by_regime.LOW_VOLATILITY = 0.25`.
- Current A2 config has no YAML `allowed_sources` key.
- The A2 model layer in `apps/reference/config/domains/decision_making.py` forbids unknown YAML keys and keeps `allowed_sources` only as a Python compatibility property, not as an accepted config input.
- A2 runtime-core suites passed `86 passed, 1 deselected`.
- Full focused A2 suite ran `97` tests and finished `92 passed, 5 failed`.
- A3 focused suites passed `33 passed`.
- A4 focused suites passed `10 passed`.
- Pure A5 governance, runtime, schema, and observability suites passed `210 passed`.
- Broader A5 suite ran `243` tests and finished `242 passed, 1 failed`; the failure was frozen-manifest drift in `tests/config/test_execution_position_contracts.py`, not sidecar runtime behavior.
- `ACTION_SKIPPED` is registered and schematized, but runtime tests assert it is not emitted in shadow mode and no runtime emitter was found in searched `execution_position` code.
- Workspace search under `apps/reference/domains/execution_position/**` found no `lifecycle_stats_ref` or `lifecycle_stats_source` fields.
- The A4 lifecycle stats writer remains execution-owned at `logs/execution_lifecycle_stats_v1.jsonl`.
- The A3 decision ledger remains canonical at `logs/shadow_telemetry/decision_ledger_v1.jsonl`.
- Sidecar allowed action scope remains bounded to `soft_close_symbol_current_net_only = true` with `partial_reduce = false`, `bracket_mutation = false`, and `exact_targeting = false`.
- `BRACKETS_PENDING` is explicitly covered by tests as an active lifecycle state, and pure A5 runtime suites pass with that contract intact.

## Inferred Findings
- The repaired runtime-critical path is materially cleaner than the surrounding harness layer: core A2 gate logic, A3 decision ledger, A4 lifecycle-stats write path, and A5 sidecar governance all have current executable proof.
- The dominant remaining risk is not missing runtime implementation; it is drift between current split contracts and older tests or tooling that still assume pre-split or pre-snapshot surfaces.
- A4 is ready for clean runtime write-side collection, but not for claiming full reader cutover, because `lifecycle_stats_ref` and `lifecycle_stats_source` are still absent.
- A5 is ready to remain enabled under the current bounded action scope. The remaining `ACTION_SKIPPED` surface is governance debt, not execution-owner expansion.

## Package Matrix

| Package | Runtime-critical status | Closure hygiene status | Evidence basis |
|---|---|---|---|
| A1 | PASS | PASS_WITH_RESIDUAL_DOC_TENSION | score-lineage payload suite `4 passed`; ownership map plus runtime trace contract align |
| A2 | PASS | FAIL | core runtime suites `86 passed`; full focused suite has `5` current failures from stale config or tooling expectations |
| A3 | PASS | PASS_WITH_EDGE_RESIDUAL | focused suites `33 passed`; unresolved note remains rid-first builder collapse edge |
| A4 | PASS | PASS_WITH_DEFERRED_READ_SIDE | focused suites `10 passed`; reader cutover fields are absent |
| A5 | PASS | PASS_WITH_RESIDUALS | pure governance surface `210 passed`; broader suite shows frozen snapshot drift and dead-surface residue |

## Surface Classification

| Surface | Current classification | Blocking to clean runtime? | Notes |
|---|---|---|---|
| `allowed_sources` | Legacy/property-only compatibility surface; forbidden as YAML input | No | stale A2 tooling and tests still send it |
| `min_direction_confidence_by_regime` | Migration alias still live in model and YAML | No | current YAML `LOW_VOLATILITY` value is `0.25`, not stale `0.51` |
| `min_direction_confidence_overrides_by_strategy_symbol` | Migration alias still present | No | split raw and normalized overrides also exist |
| `signal_score` | Compatibility raw-signed candidate surface | No | still routed under `raw_signed_score` family |
| `final_score_raw` | Deprecated alias / forensic surface | No | not canonical live authority |
| `score` | Compatibility alias | No | not canonical live authority |
| `judge_confidence` | Shadow-only normalized candidate; model allows it, YAML default excludes it | No | no live producer proof found in searched runtime |
| `ACTION_SKIPPED` | Schema and registry dead surface; unimplemented emitter | No | governance residual only |
| `lifecycle_stats_ref` / `lifecycle_stats_source` | Absent read-side fields | No for clean runtime write path | Yes for full A4 reader-cutover completeness |
| Sidecar-owned peak/path stats | Not present | No | good state; path stats remain execution-owned |

## Exact Current Failures

### A2 focused-suite failures
1. `tests/config/test_decision_making_contracts.py::test_current_aurora_config_loads_decision_making_contract`
   - Current-tree drift: the test expects `directional_sanity.max_regime_confidence_by_regime` to be `TREND_UP = 0.32` and `TREND_DOWN = 0.32`, while current `config/aurora/domains.yaml` is `TREND_UP = 0.43` and `TREND_DOWN = 0.40`.
   - Blocking classification: closure-hygiene failure, not runtime-path blocker.
2. `tests/tools/test_calibrate_nrr062_historical.py::test_evaluate_surface_uses_real_low_vol_gate_and_relaxed_rr_changes_result`
3. `tests/tools/test_calibrate_nrr062_historical.py::test_evaluate_surface_patched_contract_prefers_strategy_confidence`
4. `tests/tools/test_calibrate_nrr062_historical.py::test_build_unlock_cliff_table_groups_first_unlocking_surface`
5. `tests/tools/test_calibrate_nrr062_historical.py::test_build_raw_unlock_cliff_table_captures_outside_grid_requirements`
   - Current-tree drift: the helper still constructs `direction_confidence.allowed_sources`, which current model validation rejects as `extra_forbidden`.
   - Blocking classification: offline tooling or test failure, not live gate or write-path blocker.

### A5 broader-suite failure
1. `tests/config/test_execution_position_contracts.py::test_execution_position_extraction_preserves_model_contract`
   - Frozen manifest drift: `trade_executed_cutover_active` exists in the current execution-position config model, but not in the frozen extraction snapshot.
   - Blocking classification: config-extraction hygiene failure, not A5 governance runtime blocker.

### A5 ambiguous isolation-only signal
- `tests/config/test_position_policy_sidecar_config_contract.py::test_shadow_fee_aware_arm_uses_percent_units_not_ratio` failed once in a mixed isolation rerun on unrelated `ETHUSDT` leverage validation, then passed when rerun alone.
- Classification: ambiguous or order-dependent harness signal; do not treat as a stable blocker without dedicated follow-up.

## Contradictions / Evidence Gaps
- I did not prove a live Aurora producer for `strategy_confidence` or `judge_confidence` in the searched runtime path. Current YAML keeps `strategy_confidence` as the only normalized default candidate, but raw signed sources remain enabled and tested.
- A1 ownership docs and A2 runtime still carry compatibility tension around signed-score candidate surfaces. The current runtime is coherent under split families, but the surrounding terminology is not fully simplified.
- A3 builder latest-row collapse is still evidenced as rid-first; this audit did not prove decision_id-first safety for cross-decision rid collision edge cases.
- The earlier broad multi-suite `pytest` exit `0` came from prior session context, not from a rerun in this turn.

## Root Cause Candidates
- A2 contract split removed YAML `allowed_sources` faster than offline calibrator helpers and some current-config expectation tests were updated.
- A4 proving work closed the execution-owned writer before any reader-cutover field rollout.
- A5 preserved planned or experimental schema surfaces such as `ACTION_SKIPPED` without shipping a runtime emitter.
- Execution-position public contract snapshots lagged new model fields such as `trade_executed_cutover_active`.

## Operational Risk
- Correctness
- Observability Gap

## Files / Areas Touched
- `SCORE_FIELD_OWNERSHIP_MAP.md`
- `config/aurora/domains.yaml`
- `apps/reference/config/domains/decision_making.py`
- `apps/reference/shared/decision_primitives/score_lineage.py`
- `apps/reference/domains/decision_making/gates/low_vol_cost_floor.py`
- `apps/reference/domains/decision_making/gateway/strategy_gateway.py`
- `apps/reference/domains/decision_making/intent/payload_assembler.py`
- `apps/reference/domains/neocortex/contracts/decision_outcome_ledger.py`
- `apps/reference/domains/neocortex/logic/ledger/decision_outcome_ledger.py`
- `calibrators/datasets/builders/realized_outcome_builder.py`
- `apps/reference/domains/execution_position/telemetry/lifecycle_stats_ledger.py`
- `apps/reference/domains/execution_position/orchestration/event_handlers.py`
- `apps/reference/domains/execution_position/sidecar/position_policy_mediator.py`
- `apps/reference/domains/execution_position/sidecar/position_policy_sidecar.py`
- `tests/config/test_decision_making_contracts.py`
- `tests/tools/test_calibrate_nrr062_historical.py`
- `tests/config/test_execution_position_contracts.py`
- `tests/config/test_position_policy_sidecar_config_contract.py`
- `A1_A2_A3_A4_A5_RUNTIME_READINESS_RECONCILIATION_REPORT.md`

## Validation Performed

### A1 executable proof

```text
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/decision_making/test_intent_builder_payload_contract.py -q
4 passed in 5.17s
```

### A2 runtime-core proof

```text
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/config/test_decision_making_contracts.py tests/domains/decision_making/test_low_vol_direction_confidence_contract.py tests/domains/decision_making/test_low_vol_cost_floor_gate.py -k "not test_current_aurora_config_loads_decision_making_contract" -q
86 passed, 1 deselected in 15.99s
```

### A2 full focused suite

```text
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/config/test_decision_making_contracts.py tests/domains/decision_making/test_low_vol_direction_confidence_contract.py tests/domains/decision_making/test_low_vol_cost_floor_gate.py tests/tools/test_calibrate_nrr062_historical.py -q
92 passed, 5 failed in 20.83s
```

### A3 focused proof

```text
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/neocortex/contract/test_decision_outcome_ledger_contract.py tests/domains/shadow_telemetry/test_decision_ledger_join.py tests/calibrators/test_realized_outcome_builder.py -q
33 passed in 4.69s
```

### A4 focused proof

```text
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/execution_position/telemetry/test_lifecycle_stats_ledger.py tests/domains/execution_position/test_lifecycle_stats_ledger_wiring.py tests/domains/execution_position/test_close_producer_bridge_package6.py::test_position_policy_mediator_path_reaches_typed_close_bridge -q
10 passed in 3.56s
```

### A5 broader suite

```text
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/config/test_execution_position_contracts.py tests/config/test_position_policy_sidecar_config_contract.py tests/contracts/test_position_policy_sidecar_contracts.py tests/domains/execution_position/test_execution_position_schema_loads.py tests/domains/execution_position/test_position_policy_sidecar_schema_refs.py tests/domains/execution_position/test_position_policy_sidecar.py tests/domains/execution_position/test_sidecar_modes_disable_shadow_enable.py tests/domains/execution_position/test_position_policy_sidecar_peak_giveback.py tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py tests/domains/execution_position/test_position_policy_sidecar_recommendation_dedup.py tests/tools/test_position_policy_sidecar_validation.py -q
242 passed, 1 failed in 59.30s
```

### A5 pure governance surface

```text
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/contracts/test_position_policy_sidecar_contracts.py tests/domains/execution_position/test_execution_position_schema_loads.py tests/domains/execution_position/test_position_policy_sidecar_schema_refs.py tests/domains/execution_position/test_position_policy_sidecar.py tests/domains/execution_position/test_sidecar_modes_disable_shadow_enable.py tests/domains/execution_position/test_position_policy_sidecar_peak_giveback.py tests/domains/execution_position/test_position_policy_sidecar_fee_aware_shadow_observability.py tests/domains/execution_position/test_position_policy_sidecar_recommendation_dedup.py tests/tools/test_position_policy_sidecar_validation.py -q
210 passed in 14.71s
```

### A5 single-test disambiguation

```text
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/config/test_position_policy_sidecar_config_contract.py::test_shadow_fee_aware_arm_uses_percent_units_not_ratio -q
1 passed in 2.79s
```

## Residual Risk
- Closing A2 without updating stale tests and offline tooling will keep producing false negatives and will obscure genuine regressions.
- Claiming A4 as full cutover would be overstated until `lifecycle_stats_ref` and `lifecycle_stats_source` are either implemented or explicitly retired from expectations.
- `ACTION_SKIPPED` and frozen contract snapshot drift will keep audit noise high across future readiness reviews.

## What Remains Unproven
- Live new-runtime collection with actual JSONL output after restart or reset across A1-A5 in one continuous run.
- Proven live producer status for normalized `strategy_confidence` in the Aurora runtime path.
- Decision_id-first safety under rid-collision edge cases in the A3 builder seam.
- Whether `ACTION_SKIPPED` should be removed or emitted; the current repo only proves that it is dead.

## Minimal Safe Verdict
`RUNTIME_READY_WITH_RESIDUALS`

The clean-runtime decision should be treated as allowed for current write and execution critical paths, but not as package-closure-complete. The next closure pass should update stale A2 tests or tooling, decide the A4 reader-cutover fate explicitly, and either remove or implement the A5 `ACTION_SKIPPED` surface while refreshing frozen execution-position contract snapshots.
