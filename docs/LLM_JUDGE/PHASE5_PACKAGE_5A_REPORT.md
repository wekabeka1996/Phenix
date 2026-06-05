# Phase 5 Package 5A Report

## 1. Executive Verdict

DONE WITH RESERVATIONS

Package 5A simulator foundation was implemented, the focused test slice passed, and no frozen Phase 1-4 production file was edited by this task. The reservation is repo-state evidence only: the working tree already contains unrelated modified forbidden files outside Package 5A paths, so I cannot honestly claim the entire current repo diff contains only Package 5A changes.

## 2. Scope Implemented

- Added a new offline-only simulator subpackage under alpha_search judge.
- Added a strict immutable SimulatorConfig model with fail-closed validation.
- Added a dedicated outcome input JSON schema for exact-cycle correlation.
- Added a verdict JSONL loader that parses line-by-line and skips malformed lines with warnings.
- Added a strict outcome data loader with JSON Schema validation and typed normalization.
- Added deterministic verdict-outcome correlation by exact key: strategy_id, symbol, tf_sec, bar_close_ts.
- Added a minimal directional accuracy computation layer.
- Added focused unit tests for config validation, schema loading, loader behavior, correlation, duplicates, malformed JSONL handling, and basic metrics.
- Added a standalone simulator config file that is not wired into live runtime.

## 3. FACTS

- Phase 5 SSOT is docs/LLM_JUDGE/LLM_JUDGE_PHASE5_IMPLEMENTATION_BLUEPRINT.md and it explicitly defines Phase 5 as Shadow Economic Simulator, offline only, with no runtime mode widening.
- The implemented simulator code lives only under apps/reference/domains/alpha_search/judge/simulator/.
- The implemented tests live only under tests/domains/alpha_search/judge/simulator/.
- The simulator config was added as a standalone file at config/judge_simulator.yaml and was not integrated into JudgeCortexConfig.
- The simulator loader uses JudgeVerdict for verdict-line validation but does not modify contracts.py.
- Verdict correlation uses JudgeVerdict.ts_ms as bar_close_ts, matching the Phase 4 timestamp alignment fix and the Phase 5 same-cycle correlation rule.
- Outcome input validation is strict: JSON Schema validation plus typed Pydantic normalization.
- Malformed verdict JSONL lines are skipped with logging warnings rather than crashing the full run.
- Duplicate outcome keys are handled deterministically by keeping the first outcome record for that key and warning.
- Duplicate verdict keys are handled deterministically by preserving input order, evaluating each verdict independently against the same exact-key outcome, and warning.
- Final focused validation passed:
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_config_models.py -q
  - result: 7 passed in 0.22s
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_simulator_engine.py -q
  - result: 16 passed in 0.35s

## 4. INFERENCES

- Using JudgeVerdict as the verdict-line validator is the narrowest way to stay aligned with Phase 4 output contracts without editing frozen contract surfaces.
- Keeping the simulator config standalone preserves the Phase 5 boundary that JudgeCortexConfig admission must remain frozen at off and shadow only.
- Exact-key correlation with no tolerance window satisfies the Phase 5A requirement and prevents hidden fuzzy matching behavior.
- First-record-wins handling for duplicate outcome keys is safer than silent overwrite because it is deterministic and explicit.
- Preserving duplicate verdict input order is the least-assumptive deterministic policy for Package 5A because it avoids silent deduplication of produced judge artifacts.

## 5. ASSUMPTIONS

- Phase 4 verdict JSONL files on disk are raw JudgeVerdict model_dump_json lines, not event-envelope wrappers. This matches the current write_jsonl_verdict_log implementation.
- JudgeVerdict.ts_ms is the same-cycle bar_close_ts identity for Package 5A correlation. This is supported by the Phase 4 timestamp alignment fix and existing integration tests.
- Operators will supply outcome data as a JSON document matching outcome_input_v1.json with one row per cycle identity.
- The standalone config file is a bounded Package 5A subset surface, not a promise that CLI/config wiring is complete.

## 6. UNKNOWNS

- Real-world verdict log volume, file rotation breadth, and directory size were not profiled in this package.
- The final Package 5B+ policy for duplicate verdict keys is still open; Package 5A only guarantees deterministic handling, not a calibrated business interpretation.
- Outcome source completeness for real production sessions remains an operator/data-pipeline question outside Package 5A.

## 7. Files Added

- apps/reference/domains/alpha_search/judge/simulator/__init__.py
- apps/reference/domains/alpha_search/judge/simulator/config_models.py
- apps/reference/domains/alpha_search/judge/simulator/simulator_engine.py
- apps/reference/domains/alpha_search/judge/simulator/schemas/outcome_input_v1.json
- config/judge_simulator.yaml
- tests/domains/alpha_search/judge/simulator/__init__.py
- tests/domains/alpha_search/judge/simulator/test_config_models.py
- tests/domains/alpha_search/judge/simulator/test_simulator_engine.py
- docs/LLM_JUDGE/PHASE5_PACKAGE_5A_REPORT.md

## 8. Files Modified

- None.

This task did not edit any existing repository file.

## 9. Exact API Implemented

- SimulatorConfig
- load_verdict_records(judge_logs_path: str | Path) -> list[VerdictRecord]
- load_outcome_data(outcome_data_path: str | Path) -> list[OutcomeRecord]
- correlate_verdicts_to_outcomes(verdicts: Sequence[VerdictRecord], outcomes: Sequence[OutcomeRecord]) -> tuple[CorrelatedVerdictOutcome, ...]
- compute_basic_accuracy(correlations: Sequence[CorrelatedVerdictOutcome]) -> BasicAccuracySummary
- run_simulation(config: SimulatorConfig) -> SimulationResult

Implemented result/data structures:

- CorrelationKey
- VerdictRecord
- OutcomeRecord
- CorrelatedVerdictOutcome
- AccuracyBucket
- BasicAccuracySummary
- SimulationResult

## 10. Outcome Input Schema Implemented

Schema file:

- apps/reference/domains/alpha_search/judge/simulator/schemas/outcome_input_v1.json

Top-level fields:

- schema_version = "1"
- outcomes = array

Per-outcome required identity fields:

- strategy_id
- symbol
- tf_sec
- bar_close_ts

Per-outcome required Package 5A fields:

- matched_trade
- entry_price when matched_trade=true
- exit_price when matched_trade=true
- exit_ts_ms when matched_trade=true

Behavior:

- exact-cycle identity only
- additionalProperties=false
- malformed or schema-invalid payloads fail loudly in the loader

## 11. Validation Evidence

Exact pytest commands:

- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_config_models.py -q
- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_simulator_engine.py -q

Pass/fail results:

- test_config_models.py: 7 passed, 0 failed
- test_simulator_engine.py: 16 passed, 0 failed

Proof of deterministic correlation:

- test_simulator_engine.py::TestCorrelation::test_exact_key_match_produces_matched_record
- test_simulator_engine.py::TestCorrelation::test_mismatch_by_identity_field_does_not_match
- test_simulator_engine.py::TestCorrelation::test_duplicate_verdict_keys_are_handled_deterministically
- test_simulator_engine.py::TestCorrelation::test_duplicate_outcome_keys_are_handled_deterministically

Proof malformed JSONL does not crash the run:

- test_simulator_engine.py::TestVerdictLoader::test_malformed_lines_skipped_with_warning
- test_simulator_engine.py::TestMetricsAndSimulationResult::test_run_simulation_does_not_crash_on_malformed_jsonl

Proof no Phase 1-4 production files were modified by this task:

- Targeted status command used:
  - git status --short -- apps/reference/domains/alpha_search/judge/simulator config/judge_simulator.yaml tests/domains/alpha_search/judge/simulator apps/reference/domains/alpha_search/judge/contracts.py apps/reference/domains/alpha_search/judge/config_models.py apps/reference/domains/alpha_search/judge/verdict/verdict_synthesizer.py apps/reference/domains/alpha_search/backtest_plugin.py apps/reference/domains/decision_making apps/reference/domains/execution_position apps/reference/main.py apps/reference/config_loader.py
- Status output for Package 5A paths:
  - ?? apps/reference/domains/alpha_search/judge/simulator/
  - ?? config/judge_simulator.yaml
  - ?? tests/domains/alpha_search/judge/simulator/
- No status entries appeared for:
  - apps/reference/domains/alpha_search/judge/contracts.py
  - apps/reference/domains/alpha_search/judge/config_models.py
  - apps/reference/domains/alpha_search/judge/verdict/verdict_synthesizer.py
  - apps/reference/domains/alpha_search/backtest_plugin.py
  - apps/reference/config_loader.py
- Reservation:
  - The same targeted status also showed pre-existing unrelated modified files outside Package 5A scope:
    - apps/reference/domains/decision_making/deferred_scheduler.py
    - apps/reference/domains/execution_position/limit_order_monitor.py
    - apps/reference/domains/execution_position/metrics_aggregator.py
    - apps/reference/main.py
  - Therefore the task-local proof is strong, but a repo-wide statement that the entire working tree contains only Package 5A changes would be false.

## 12. Regression Statement

- No live trading runtime behavior was modified.
- No simulator imports were added into live runtime modules.
- No new runtime events were added.
- No Phase 1-4 contracts or schemas were modified.
- JudgeCortexConfig admission remains unchanged because judge/config_models.py was not edited.
- The only executed validation was the focused Package 5A test slice; no broader repo regression suite was run in this task.

## 13. What Remains Deferred To Package 5B+

- Fee and slippage modeling beyond the minimal interface boundary.
- Per-expert accuracy aggregation.
- Disagreement analytics.
- Calibration dataset writing.
- Summary report writing.
- CLI harness and config-file runtime loading.
- Any integration with backtest_plugin.shutdown().
- Any decision_making advisory consumption.
- Any runtime mode admission widening.

## 14. Risks/Caveats

- Duplicate verdict keys are deterministic but not semantically resolved beyond Package 5A; later packages may need a stricter policy.
- The standalone config file exists, but Package 5A does not yet implement YAML loading or CLI execution.
- Accuracy logic is intentionally minimal and directional only; it is not an economic simulator, fee model, slippage model, or calibration pipeline yet.
- Because the repo already has unrelated modified forbidden files in the working tree, downstream reviewers should inspect only the Package 5A paths when reviewing this task.
