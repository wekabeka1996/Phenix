# Phase 5 Package 5D Report

## 1. Executive Verdict

DONE WITH RESERVATIONS

Package 5D calibration dataset shaping and JSONL writing were implemented on top of the accepted 5A, 5B, and 5C simulator foundation, the focused validation slice passed, and no frozen Phase 1-4 production file was edited by this task. The reservation remains repository-state only: the working tree still contains unrelated pre-existing changes under forbidden scope paths outside Package 5D, so a repo-wide claim that only Package 5D work is present would be false.

## 2. Scope Implemented

- Added a bounded calibration dataset writer module.
- Added a calibration dataset output schema for one JSONL record.
- Extended the simulator result path additively with calibration_records.
- Preserved exact-key correlation from 5A.
- Preserved fee/slippage economic enrichment from 5B.
- Preserved disagreement and expert-accuracy outputs from 5C.
- Added focused tests for cohort shaping, JSONL writing, invalid-input failure, and engine integration.

## 3. FACTS

- The approved Phase 5 SSOT still defines Phase 5 as an offline-only Shadow Economic Simulator with no runtime mode widening and no live/runtime integration.
- Package 5D is explicitly listed in the blueprint package order as calibration dataset writer work, dependent on 5A and 5C.
- The accepted 5A/5B/5C foundation already provides the simulator inputs needed for 5D:
  - exact-key verdict/outcome correlation
  - economic enrichment fields
  - bounded disagreement records
  - bounded expert accuracy records and summary
- Package 5D added a new writer module at apps/reference/domains/alpha_search/judge/simulator/calibration_dataset_writer.py.
- Package 5D added a new schema at apps/reference/domains/alpha_search/judge/simulator/schemas/calibration_dataset_v1.json.
- SimulationResult now carries additive calibration_records output.
- Calibration records are built only from already-produced simulator facts; unmatched verdicts are skipped because no outcome truth exists for required calibration fields.
- The implemented record shape includes the required fields from the task prompt:
  - strategy_id
  - symbol
  - tf_sec
  - bar_close_ts
  - verdict_id
  - entry_verdict
  - confidence
  - dissent_noted
  - matched_trade
  - raw_return
  - fee_cost
  - slippage_cost
  - net_return
  - optimal_action
  - has_disagreement
  - cohort
  - schema_version
- The writer creates parent directories, preserves caller record order, writes JSONL only, sorts JSON object keys deterministically, and fails closed if the target path already exists.
- The blueprint contains an internal format drift:
  - one earlier table mentions JSON files and CSV calibration datasets
  - the package validation and done criteria explicitly require JSON lines and deterministic output
- The current simulator config path already points calibration_dataset_path at a .jsonl target.
- The focused validation commands all passed:
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_config_models.py -q
  - result: 9 passed in 0.78s
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_fee_slippage_calculator.py -q
  - result: 14 passed in 0.71s
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_disagreement_analyzer.py -q
  - result: 12 passed in 0.67s
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_expert_accuracy_reporter.py -q
  - result: 5 passed in 0.63s
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_calibration_dataset_writer.py -q
  - result: 11 passed in 1.05s
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_simulator_engine.py -q
  - result: 26 passed in 1.34s

## 4. INFERENCES

- Building calibration rows from existing correlations plus disagreement ids is the narrowest additive 5D seam because it reuses accepted 5A/5B/5C outputs without reopening any earlier contract.
- Because the blueprint conflicts internally on CSV vs JSON lines, JSONL is the safer fail-closed 5D choice: it is the narrower package-local requirement in the validation and done-criteria sections, it matches the current config path, and it matches the task prompt.
- Treating unmatched verdicts as non-record-producing is safer than inventing calibration rows with missing outcome truth, because the minimum required fields include matched_trade and optimal_action semantics derived from realized outcomes.
- Keeping write_calibration_dataset separate from run_simulation preserves the package boundary: 5D exposes calibration_records but does not yet add summary writing, CLI behavior, or plugin integration.

## 5. ASSUMPTIONS

- Verdict ids are stable enough to act as the deterministic join key between calibration rows and 5C disagreement records.
- The current 5B fee/slippage model remains the correct economic source for the 5D optimal_action and cohort labels until a later SSOT says otherwise.
- Fail-closed file creation on existing targets is acceptable for 5D because the writer is an explicit offline artifact step, not an automatic runtime export path.
- The simulator subtree is still untracked in git, so logical package-by-package add-vs-modify classification inside that subtree is based on accepted 5A/5B/5C workspace state rather than on git history.

## 6. UNKNOWNS

- Whether later packages will require richer calibration fields such as regime, hold-duration, or explicit expert-summary references.
- Whether later packages will require append/replace semantics for calibration dataset output instead of the current fail-closed create-only writer policy.
- Whether the stale CSV mention in the blueprint will be formally cleaned up later, even though 5D-local validation authority resolves the current implementation choice to JSONL.

## 7. Files Added

- apps/reference/domains/alpha_search/judge/simulator/calibration_dataset_writer.py
- apps/reference/domains/alpha_search/judge/simulator/schemas/calibration_dataset_v1.json
- tests/domains/alpha_search/judge/simulator/test_calibration_dataset_writer.py
- docs/LLM_JUDGE/PHASE5_PACKAGE_5D_REPORT.md

## 8. Files Modified

- apps/reference/domains/alpha_search/judge/simulator/__init__.py
- apps/reference/domains/alpha_search/judge/simulator/simulator_engine.py
- tests/domains/alpha_search/judge/simulator/test_simulator_engine.py

## 9. Exact Calibration Writer API Implemented

- build_calibration_records(*, correlations: Sequence[CorrelatedVerdictOutcome], disagreements: Sequence[Mapping[str, object]], config: SimulatorConfig) -> list[dict[str, object]]
- write_calibration_dataset(*, records: Sequence[Mapping[str, object]], output_path: str | Path) -> Path

Implemented semantics:

- build_calibration_records consumes already-produced simulator outputs only
- record order matches caller correlation order deterministically
- unmatched verdicts produce no calibration row
- has_disagreement is derived deterministically from 5C disagreement verdict_id membership
- write_calibration_dataset validates every record, creates parent directories, requires .jsonl output, sorts JSON keys deterministically, and fails closed if the target file already exists

## 10. Exact Cohort Labeling Rule Implemented

- OPEN_LONG or OPEN_SHORT with entry_verdict equal to optimal_action -> CORRECT_ENTRY
- OPEN_LONG or OPEN_SHORT with entry_verdict different from optimal_action -> INCORRECT_ENTRY
- NO_ENTRY with optimal_action NO_ENTRY -> CORRECT_ABSTAIN
- NO_ENTRY with optimal_action OPEN_LONG or OPEN_SHORT -> MISSED_OPPORTUNITY
- UNKNOWN or SUPPRESS -> INCONCLUSIVE

The rule is mechanical and bounded. It does not introduce threshold tuning, promotion policy, or regime-aware branching.

## 11. Exact Engine Integration Implemented

- Package 5D did not add any runtime import path outside the offline simulator package.
- __init__.py now exports build_calibration_records and write_calibration_dataset.
- simulator_engine.py now imports build_calibration_records from the new writer module.
- SimulationResult gained additive calibration_records output.
- run_simulation() now performs, in order:
  - verdict loading
  - outcome loading
  - exact-key correlation
  - 5B economic enrichment
  - 5C disagreement construction
  - 5C expert-accuracy construction
  - 5D calibration record construction
  - existing accuracy summary and expert summary return path
- run_simulation() does not write calibration files to disk; it only exposes calibration_records.

## 12. Validation Evidence

Exact pytest commands:

- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_config_models.py -q
- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_fee_slippage_calculator.py -q
- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_disagreement_analyzer.py -q
- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_expert_accuracy_reporter.py -q
- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_calibration_dataset_writer.py -q
- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_simulator_engine.py -q

Pass/fail results:

- test_config_models.py: 9 passed, 0 failed
- test_fee_slippage_calculator.py: 14 passed, 0 failed
- test_disagreement_analyzer.py: 12 passed, 0 failed
- test_expert_accuracy_reporter.py: 5 passed, 0 failed
- test_calibration_dataset_writer.py: 11 passed, 0 failed
- test_simulator_engine.py: 26 passed, 0 failed

Proof calibration records are correct:

- test_calibration_dataset_writer.py::TestCalibrationSchemaAndRecords::test_actionable_correct_entry_case
- test_calibration_dataset_writer.py::TestCalibrationSchemaAndRecords::test_actionable_incorrect_entry_case
- test_calibration_dataset_writer.py::TestCalibrationSchemaAndRecords::test_no_entry_correct_abstain_case
- test_calibration_dataset_writer.py::TestCalibrationSchemaAndRecords::test_no_entry_missed_opportunity_case
- test_calibration_dataset_writer.py::TestCalibrationSchemaAndRecords::test_unknown_is_inconclusive
- test_calibration_dataset_writer.py::TestCalibrationSchemaAndRecords::test_suppress_is_inconclusive
- test_simulator_engine.py::TestMetricsAndSimulationResult::test_simulation_result_includes_disagreements_and_expert_accuracy

Proof writer output is deterministic JSONL:

- test_calibration_dataset_writer.py::TestCalibrationSchemaAndRecords::test_schema_compiles
- test_calibration_dataset_writer.py::TestCalibrationWriter::test_writes_jsonl_successfully_and_preserves_order
- test_calibration_dataset_writer.py::TestCalibrationWriter::test_parent_directory_creation_works
- test_calibration_dataset_writer.py::TestCalibrationWriter::test_invalid_record_input_rejected_loudly
- test_calibration_dataset_writer.py::TestCalibrationWriter::test_existing_target_file_rejected_loudly

Proof Package 5A/5B/5C behavior still works:

- test_config_models.py still passes after the 5D addition.
- test_fee_slippage_calculator.py still passes without changing the 5B economic contract.
- test_disagreement_analyzer.py still passes without changing the 5C disagreement contract.
- test_expert_accuracy_reporter.py still passes without changing the 5C expert-accuracy contract.
- test_simulator_engine.py still passes exact-key correlation, economic enrichment, disagreement integration, expert-accuracy integration, deterministic rerun behavior, and malformed JSONL non-crash behavior.

Proof no forbidden Phase 1-4 production files were modified by this task:

- Targeted status command used:
  - git status --short -- apps/reference/domains/alpha_search/judge/simulator config/judge_simulator.yaml tests/domains/alpha_search/judge/simulator docs/LLM_JUDGE/PHASE5_PACKAGE_5D_REPORT.md apps/reference/domains/alpha_search/judge/contracts.py apps/reference/domains/alpha_search/judge/config_models.py apps/reference/domains/alpha_search/judge/verdict/verdict_synthesizer.py apps/reference/domains/alpha_search/backtest_plugin.py apps/reference/domains/decision_making apps/reference/domains/execution_position apps/reference/main.py apps/reference/config_loader.py
- Status output showed no entries for:
  - apps/reference/domains/alpha_search/judge/contracts.py
  - apps/reference/domains/alpha_search/judge/config_models.py
  - apps/reference/domains/alpha_search/judge/verdict/verdict_synthesizer.py
  - apps/reference/domains/alpha_search/backtest_plugin.py
  - apps/reference/config_loader.py
- Reservation:
  - the same targeted status showed unrelated pre-existing modified or untracked files under forbidden scope outside Package 5D:
    - apps/reference/domains/decision_making/aurora_decision.py
    - apps/reference/domains/decision_making/aurora_handler.py
    - apps/reference/domains/decision_making/deferred_scheduler.py
    - apps/reference/domains/decision_making/boundary_mappers.py
    - apps/reference/domains/decision_making/boundary_models.py
    - apps/reference/domains/decision_making/core_models.py
    - apps/reference/domains/execution_position/intent_router.py
    - apps/reference/domains/execution_position/limit_order_monitor.py
    - apps/reference/domains/execution_position/metrics_aggregator.py
    - apps/reference/main.py
  - git continues to report the simulator subtree at directory level as untracked, so git can prove the frozen surfaces above were untouched but cannot distinguish add-vs-modify inside the simulator subtree.

## 13. Regression Statement

- No live trading runtime behavior was modified.
- No runtime events were added.
- No simulator imports were added into live runtime modules.
- No Phase 1-4 contracts or schemas were modified.
- JudgeCortexConfig mode admission remains unchanged because judge/config_models.py was not edited.
- Package 5A, 5B, and 5C public APIs remain present; Package 5D only extended them additively.

## 14. What Remains Deferred To Package 5E+

- Summary report generation.
- CLI harness.
- Any integration into backtest_plugin.shutdown().
- Any decision_making or runtime advisory work.
- Any mode admission changes.
- Any Phase 6 promotion logic or thresholds.
- Any richer calibration/promotion dataset semantics beyond the current bounded row shape.

## 15. Risks/Caveats

- Calibration rows are produced only for matched cycles with outcome truth; unmatched verdicts remain intentionally absent from calibration_records.
- The writer currently uses create-only fail-closed output semantics; rerunning to the same target path without cleanup will raise FileExistsError by design.
- The blueprint still contains one stale CSV mention even though the 5D-local validation and done criteria require JSON lines; this implementation follows the narrower JSONL contract.
- The working tree still contains unrelated forbidden-scope files outside this task, so reviewers should inspect only the Package 5D paths when validating this package.
