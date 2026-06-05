# Phase 5 Package 5C Report

## 1. Executive Verdict

DONE WITH RESERVATIONS

Package 5C disagreement analysis and per-expert accuracy computation were implemented on top of the accepted 5A and 5B simulator foundation, the focused validation slice passed, and no forbidden Phase 1-4 production file was edited by this task. The reservation remains repository-state only: the working tree still contains unrelated pre-existing modified forbidden files outside Package 5C scope, so a repo-wide claim that only Package 5C work is present would be false.

## 2. Scope Implemented

- Added a bounded disagreement analyzer module.
- Added a bounded expert accuracy reporter module.
- Extended the simulator result path additively with disagreement records, per-cycle expert accuracy records, and aggregate expert accuracy summary.
- Preserved exact-key correlation from 5A.
- Preserved fee/slippage economic enrichment from 5B.
- Added focused unit tests for disagreement rules, optimal-action derivation, expert accuracy computation, aggregation, and engine integration.

## 3. FACTS

- The approved Phase 5 SSOT still defines Phase 5 as offline-only Shadow Economic Simulator work with no runtime mode widening and no live/runtime integration.
- The current workspace already contains the accepted 5A/5B foundation: standalone simulator config, exact-key verdict/outcome correlation, and 5B fee/slippage enrichment.
- Package 5C added new pure-analysis modules at apps/reference/domains/alpha_search/judge/simulator/disagreement_analyzer.py and apps/reference/domains/alpha_search/judge/simulator/expert_accuracy_reporter.py.
- Package 5C extended simulator_engine.py without touching contracts.py, judge/config_models.py, verdict_synthesizer.py, backtest_plugin.py, decision_making, execution_position, main.py, or config_loader.py.
- VerdictRecord now carries additive dissent_noted data copied from JudgeVerdict.
- SimulationResult now carries additive outputs:
  - disagreements
  - expert_accuracy_records
  - expert_accuracy_summary
- Engine integration loads envelope JSONL only as an offline artifact source for preserved expert_outputs; it does not add any runtime import path or runtime coupling.
- The implemented optimal-action rule is deterministic and bounded:
  - compute modeled LONG and SHORT net returns from the realized price path using the 5B fee/slippage model
  - choose OPEN_LONG only if long net return is strictly positive and strictly greater than short net return
  - choose OPEN_SHORT only if short net return is strictly positive and strictly greater than long net return
  - otherwise choose NO_ENTRY
- UNKNOWN and SUPPRESS are treated explicitly as non-actionable for disagreement analysis and do not produce disagreement records.
- Expert accuracy computation does not invent expert records when envelope/chamber expert outputs are absent.
- Duplicate expert ids inside one cycle are handled deterministically by keeping the first occurrence.
- The focused validation commands all passed:
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_config_models.py -q
  - result: 9 passed in 0.43s
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_fee_slippage_calculator.py -q
  - result: 14 passed in 0.35s
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_disagreement_analyzer.py -q
  - result: 12 passed in 0.53s
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_expert_accuracy_reporter.py -q
  - result: 5 passed in 0.35s
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_simulator_engine.py -q
  - result: 26 passed in 1.02s

## 4. INFERENCES

- Loading expert outputs from envelope JSONL is the narrowest compatible way to compute per-expert accuracy because envelopes already preserve strategy_id and chamber_aggregate.expert_outputs without modifying frozen Phase 4 contracts.
- Keeping disagreement analysis separate from 5B economic enrichment preserves the 5A/5B result flow while allowing 5C to extend it additively.
- Treating UNKNOWN and SUPPRESS as non-actionable in disagreement analysis is safer than coercing them into economic trades because the task explicitly forbids fabricating actionable trades for those verdict classes.
- First-record-wins handling for duplicate expert ids is the least-assumptive deterministic policy for 5C because it avoids silently double-counting the same expert identity within one cycle.

## 5. ASSUMPTIONS

- Envelope JSONL files are written as raw JudgeEvidenceEnvelope model_dump_json lines under the same offline log root used by verdict JSONL files.
- Using the 5B fee/slippage model to compute counterfactual LONG and SHORT net returns is sufficient for the bounded 5C optimal-action rule.
- When no envelope file exists for a matched cycle, returning no expert accuracy records is the correct fail-closed policy for 5C.
- Because the simulator subtree is still untracked in git, task-local add-vs-modify classification inside that subtree is based on the accepted 5A/5B workspace foundation, not on git history.

## 6. UNKNOWNS

- Whether later packages will require storing richer disagreement payloads such as optimal_net_return or verdict_net_return in the public record shape.
- Whether later packages will require a stricter duplicate-expert-id policy than first-record-wins.
- Whether real replay datasets will always retain envelope logs alongside verdict logs for every analyzed cycle.

## 7. Files Added

- apps/reference/domains/alpha_search/judge/simulator/disagreement_analyzer.py
- apps/reference/domains/alpha_search/judge/simulator/expert_accuracy_reporter.py
- tests/domains/alpha_search/judge/simulator/test_disagreement_analyzer.py
- tests/domains/alpha_search/judge/simulator/test_expert_accuracy_reporter.py
- docs/LLM_JUDGE/PHASE5_PACKAGE_5C_REPORT.md

## 8. Files Modified

- apps/reference/domains/alpha_search/judge/simulator/__init__.py
- apps/reference/domains/alpha_search/judge/simulator/simulator_engine.py
- tests/domains/alpha_search/judge/simulator/test_simulator_engine.py

## 9. Exact Disagreement API Implemented

- determine_optimal_action(*, matched_trade: bool, entry_price: float | None, exit_price: float | None, fee_per_cycle_bps: float, slippage_pct: float) -> str
- compute_disagreement(*, verdict_action: str, matched_trade: bool, entry_price: float | None, exit_price: float | None, fee_per_cycle_bps: float, slippage_pct: float, verdict_net_return: float | None = None) -> dict | None
- build_disagreement_record(*, verdict_id: str, strategy_id: str, symbol: str, tf_sec: int, bar_close_ts: int, verdict_action: str, optimal_action: str, cost_of_disagreement: float, confidence: float, dissent_noted: bool) -> dict

Implemented semantics:

- optimal action vocabulary is strictly OPEN_LONG, OPEN_SHORT, NO_ENTRY
- optimal action is derived from realized economic outcome using the 5B net-return model, not from the verdict preference
- mismatch produces a bounded deterministic record
- exact match produces None
- UNKNOWN and SUPPRESS produce None explicitly and are not fabricated into actionable disagreement records
- cost_of_disagreement is deterministic and equals optimal action value minus verdict action value, floored at 0.0

## 10. Exact Expert Accuracy API Implemented

- compute_expert_accuracy_for_cycle(*, strategy_id: str, symbol: str, tf_sec: int, bar_close_ts: int, expert_outputs: Sequence[ExpertOutput] | None, optimal_action: str) -> list[dict]
- aggregate_expert_accuracy(records: Sequence[dict]) -> dict

Implemented semantics:

- per-cycle records are built only from preserved expert_outputs when available
- duplicate expert ids in one cycle are handled deterministically by keeping the first record
- OPEN_LONG, OPEN_SHORT, and NO_ENTRY are evaluated against optimal_action
- UNKNOWN and SUPPRESS remain explicit non-actionable expert records with evaluated=false and is_correct=None
- aggregation reports overall counts and per-expert counts:
  - total_count
  - correct_count
  - accuracy_rate
  - skipped_count
  - by_expert

## 11. Exact Engine Integration Implemented

- VerdictRecord gained additive dissent_noted propagation from JudgeVerdict.
- Internal offline envelope loading was added to simulator_engine.py to recover preserved expert_outputs from envelope JSONL.
- New additive engine seams were added:
  - build_disagreement_records(correlations, config)
  - build_expert_accuracy_records(correlations, judge_logs_path, config)
- run_simulation() now performs:
  - verdict loading
  - outcome loading
  - exact-key correlation
  - 5B economic enrichment
  - 5A basic accuracy summary
  - 5C disagreement record construction
  - 5C expert accuracy record construction
  - 5C aggregate expert accuracy summary
- SimulationResult now exposes:
  - disagreements
  - expert_accuracy_records
  - expert_accuracy_summary

## 12. Validation Evidence

Exact pytest commands:

- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_config_models.py -q
- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_fee_slippage_calculator.py -q
- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_disagreement_analyzer.py -q
- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_expert_accuracy_reporter.py -q
- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_simulator_engine.py -q

Pass/fail results:

- test_config_models.py: 9 passed, 0 failed
- test_fee_slippage_calculator.py: 14 passed, 0 failed
- test_disagreement_analyzer.py: 12 passed, 0 failed
- test_expert_accuracy_reporter.py: 5 passed, 0 failed
- test_simulator_engine.py: 26 passed, 0 failed

Proof disagreement detection is correct:

- test_disagreement_analyzer.py::TestComputeDisagreement::test_no_disagreement_when_verdict_matches_optimal_action
- test_disagreement_analyzer.py::TestComputeDisagreement::test_open_long_mismatch_case
- test_disagreement_analyzer.py::TestComputeDisagreement::test_open_short_mismatch_case
- test_disagreement_analyzer.py::TestComputeDisagreement::test_no_entry_mismatch_abstain_case
- test_disagreement_analyzer.py::TestComputeDisagreement::test_cost_of_disagreement_uses_5b_net_return_when_available
- test_disagreement_analyzer.py::TestComputeDisagreement::test_non_actionable_verdict_treatment_is_explicit
- test_simulator_engine.py::TestMetricsAndSimulationResult::test_simulation_result_includes_disagreements_and_expert_accuracy
- test_simulator_engine.py::TestMetricsAndSimulationResult::test_no_entry_disagreement_record_emitted_when_long_is_optimal

Proof optimal-action rule is correct:

- test_disagreement_analyzer.py::TestDetermineOptimalAction::test_positive_long_outcome_case
- test_disagreement_analyzer.py::TestDetermineOptimalAction::test_positive_short_outcome_case
- test_disagreement_analyzer.py::TestDetermineOptimalAction::test_abstain_no_trade_case
- test_disagreement_analyzer.py::TestDetermineOptimalAction::test_negative_actionable_outcome_can_resolve_to_no_entry
- test_disagreement_analyzer.py::TestDetermineOptimalAction::test_deterministic_rerun_behavior

Proof expert accuracy aggregation is correct:

- test_expert_accuracy_reporter.py::TestComputeExpertAccuracyForCycle::test_per_cycle_expert_accuracy_computed_correctly
- test_expert_accuracy_reporter.py::TestComputeExpertAccuracyForCycle::test_missing_expert_outputs_handled_explicitly
- test_expert_accuracy_reporter.py::TestComputeExpertAccuracyForCycle::test_duplicate_expert_ids_handled_deterministically
- test_expert_accuracy_reporter.py::TestComputeExpertAccuracyForCycle::test_no_fabricated_expert_correctness_when_data_absent
- test_expert_accuracy_reporter.py::TestAggregateExpertAccuracy::test_aggregation_total_correct_accuracy_rate_correct
- test_simulator_engine.py::TestMetricsAndSimulationResult::test_simulation_result_includes_disagreements_and_expert_accuracy

Proof Package 5A/5B behavior still works:

- test_config_models.py still passes after the 5C engine extension.
- test_fee_slippage_calculator.py still passes without modification to the 5B math contract.
- test_simulator_engine.py still covers and passes exact-key correlation, duplicate-key deterministic handling, non-entry economic non-fabrication, unmatched verdict behavior, deterministic rerun behavior, and malformed JSONL non-crash behavior.

Proof malformed verdict JSONL still does not crash the run:

- test_simulator_engine.py::TestVerdictLoader::test_malformed_lines_skipped_with_warning
- test_simulator_engine.py::TestMetricsAndSimulationResult::test_run_simulation_does_not_crash_on_malformed_jsonl

Proof no forbidden Phase 1-4 production files were modified by this task:

- Targeted status command used:
  - git status --short -- apps/reference/domains/alpha_search/judge/simulator config/judge_simulator.yaml tests/domains/alpha_search/judge/simulator docs/LLM_JUDGE/PHASE5_PACKAGE_5C_REPORT.md apps/reference/domains/alpha_search/judge/contracts.py apps/reference/domains/alpha_search/judge/config_models.py apps/reference/domains/alpha_search/judge/verdict/verdict_synthesizer.py apps/reference/domains/alpha_search/backtest_plugin.py apps/reference/domains/decision_making apps/reference/domains/execution_position apps/reference/main.py apps/reference/config_loader.py
- Status output showed no entries for:
  - apps/reference/domains/alpha_search/judge/contracts.py
  - apps/reference/domains/alpha_search/judge/config_models.py
  - apps/reference/domains/alpha_search/judge/verdict/verdict_synthesizer.py
  - apps/reference/domains/alpha_search/backtest_plugin.py
  - apps/reference/config_loader.py
- The same targeted status showed unrelated pre-existing modified forbidden files outside Package 5C scope:
  - apps/reference/domains/decision_making/deferred_scheduler.py
  - apps/reference/domains/execution_position/limit_order_monitor.py
  - apps/reference/domains/execution_position/metrics_aggregator.py
  - apps/reference/main.py
- Git currently reports the simulator subtree as untracked at directory level, so git status proves the forbidden surfaces were untouched but does not distinguish add-vs-modify inside the untracked simulator subtree.

## 13. Regression Statement

- No live trading runtime behavior was modified.
- No runtime events were added.
- No simulator imports were added into live runtime modules.
- No Phase 1-4 contracts or schemas were modified.
- JudgeCortexConfig mode admission remains unchanged because judge/config_models.py was not edited.
- Package 5A and 5B public APIs remain present; Package 5C extended them additively.

## 14. What Remains Deferred To Package 5D+

- Calibration dataset writer.
- Summary writer.
- CLI harness.
- Any integration into backtest_plugin.shutdown().
- Any decision_making or runtime advisory work.
- Any mode admission changes.
- Any Phase 6 promotion logic.

## 15. Risks/Caveats

- The optimal-action rule is intentionally mechanical and bounded; it is not a calibration policy and does not attempt regime-aware thresholds.
- Expert accuracy depends on envelope JSONL availability; when envelopes are absent, 5C correctly returns no expert accuracy records rather than inferring them.
- Because the simulator subtree is not yet tracked in git, git-level file classification inside that subtree is coarser than the logical package-by-package classification used in this report.
- The working tree still contains unrelated forbidden-file modifications outside this task, so reviewers should inspect only the Package 5C paths when validating this package.
