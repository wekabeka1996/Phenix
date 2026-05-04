# Phase 5 Package 5B Report

## 1. Executive Verdict

DONE WITH RESERVATIONS

Package 5B fee/slippage modeling was implemented on top of the existing Package 5A foundation, all focused simulator tests passed, and no forbidden Phase 1-4 production file was edited by this task. The reservation is repository-state only: the working tree still contains unrelated pre-existing modified forbidden files outside Package 5B scope, so a repo-wide claim that only Package 5B work is present would be false.

## 2. Scope Implemented

- Added a pure fee/slippage calculator module for deterministic LONG and SHORT return modeling.
- Extended the standalone simulator config with explicit fee_per_cycle_bps and slippage_pct fields.
- Extended the simulator result path so matched actionable verdicts now carry modeled economic fields.
- Preserved exact-key correlation behavior from Package 5A.
- Preserved non-entry behavior by not fabricating trade economics for NO_ENTRY, UNKNOWN, or SUPPRESS verdicts.
- Added focused tests for calculator behavior, config validation, economic integration, deterministic rerun behavior, and malformed JSONL non-crash behavior.

## 3. FACTS

- The approved SSOT still defines Phase 5 as an offline-only Shadow Economic Simulator with no runtime mode widening and no live runtime integration.
- Package 5A already shipped a standalone simulator config, verdict JSONL loader, outcome data loader, exact-key correlation, and minimal accuracy summary.
- Package 5A config was flat, not nested under input/modeling/output blocks, so Package 5B extended that existing shape instead of rewriting it.
- The new fee/slippage module was added at apps/reference/domains/alpha_search/judge/simulator/fee_slippage_calculator.py.
- SimulatorConfig now includes explicit fee_per_cycle_bps and slippage_pct fields with non-negative validation.
- run_simulation() now enriches exact-key correlations with additive economic fields for matched actionable verdicts.
- Actionable verdicts are OPEN_LONG and OPEN_SHORT.
- Non-actionable verdicts remain non-economic in Package 5B: NO_ENTRY, UNKNOWN, and SUPPRESS produce None economic fields even if an outcome row exists.
- The focused validation commands all passed:
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_config_models.py -q
  - result: 9 passed in 0.27s
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_fee_slippage_calculator.py -q
  - result: 14 passed in 0.20s
  - c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_simulator_engine.py -q
  - result: 22 passed in 0.77s

## 4. INFERENCES

- Extending the existing flat 5A config was the narrowest compatible choice because the task explicitly said to build on the accepted 5A foundation rather than redesign it.
- Modeling fee and slippage as explicit config-backed costs, converted to decimal return deductions, satisfies the Package 5B scope without introducing exchange-specific complexity.
- Keeping exact-key correlation separate from economic enrichment preserves the 5A deterministic matching contract while allowing 5B to extend the output path compatibly.
- Treating SUPPRESS as non-actionable is the most coherent Package 5B policy because it is a non-entry verdict in practice and should not fabricate trade economics.

## 5. ASSUMPTIONS

- fee_per_cycle_bps is a full per-cycle cost and should therefore be subtracted once as a decimal return cost.
- slippage_pct is a simple round-trip percentage-point cost and should therefore be subtracted once as a decimal return cost.
- The minimal Package 5B model is intentionally generic and not exchange-specific; future packages may replace it with more detailed modeling if Phase 5 evidence requires it.
- Reusing the existing 5A flat config layout is acceptable because the user explicitly forbade redesigning the Phase 5 foundation mid-package.

## 6. UNKNOWNS

- Whether later packages will require separate entry and exit fee/slippage components instead of the current one-line per-cycle model.
- Whether real outcome datasets will always carry matched_trade=false for abstain cycles, or sometimes carry realized trades despite NO_ENTRY or UNKNOWN verdicts.
- Whether future calibration/report packages will want aggregate fee/slippage totals in SimulationResult in addition to per-correlation fields.

## 7. Files Added

- apps/reference/domains/alpha_search/judge/simulator/fee_slippage_calculator.py
- tests/domains/alpha_search/judge/simulator/test_fee_slippage_calculator.py
- docs/LLM_JUDGE/PHASE5_PACKAGE_5B_REPORT.md

## 8. Files Modified

- apps/reference/domains/alpha_search/judge/simulator/__init__.py
- apps/reference/domains/alpha_search/judge/simulator/config_models.py
- apps/reference/domains/alpha_search/judge/simulator/simulator_engine.py
- config/judge_simulator.yaml
- tests/domains/alpha_search/judge/simulator/test_config_models.py
- tests/domains/alpha_search/judge/simulator/test_simulator_engine.py

## 9. Exact Fee/Slippage API Implemented

- compute_fee_cost_bps(fee_per_cycle_bps: float) -> float
- compute_slippage_cost_pct(slippage_pct: float) -> float
- compute_net_return(entry_price: float, exit_price: float, side: str, fee_per_cycle_bps: float, slippage_pct: float) -> float

Implemented semantics:

- LONG raw return = (exit_price - entry_price) / entry_price
- SHORT raw return = (entry_price - exit_price) / entry_price
- fee cost = fee_per_cycle_bps / 10000.0
- slippage cost = slippage_pct / 100.0
- net return = raw return - fee cost - slippage cost
- invalid side values are rejected
- non-positive entry and exit prices are rejected

## 10. Exact Engine Integration Implemented

- SimulatorConfig now exposes fee_per_cycle_bps and slippage_pct.
- CorrelatedVerdictOutcome now carries additive optional fields:
  - side
  - entry_price
  - exit_price
  - raw_return
  - fee_cost
  - slippage_cost
  - net_return
- enrich_correlations_with_economics(correlations, config) was added as the bounded 5B integration seam.
- run_simulation() now performs:
  - verdict loading
  - outcome loading
  - exact-key correlation
  - economic enrichment using config-backed fee/slippage inputs
  - unchanged basic accuracy computation

Behavioral rules implemented:

- OPEN_LONG maps to LONG and can receive economic fields when matched_trade=true and prices exist.
- OPEN_SHORT maps to SHORT and can receive economic fields when matched_trade=true and prices exist.
- NO_ENTRY, UNKNOWN, and SUPPRESS do not fabricate economic trade fields.
- unmatched verdicts remain unmatched and keep economic fields as None.

## 11. Validation Evidence

Exact pytest commands:

- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_config_models.py -q
- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_fee_slippage_calculator.py -q
- c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge/simulator/test_simulator_engine.py -q

Pass/fail results:

- test_config_models.py: 9 passed, 0 failed
- test_fee_slippage_calculator.py: 14 passed, 0 failed
- test_simulator_engine.py: 22 passed, 0 failed

Proof LONG/SHORT economics are correct:

- test_fee_slippage_calculator.py::TestFeeSlippageCalculator::test_long_positive_case
- test_fee_slippage_calculator.py::TestFeeSlippageCalculator::test_long_negative_case
- test_fee_slippage_calculator.py::TestFeeSlippageCalculator::test_short_positive_case
- test_fee_slippage_calculator.py::TestFeeSlippageCalculator::test_short_negative_case
- test_fee_slippage_calculator.py::TestFeeSlippageCalculator::test_nonzero_fee_reduces_return_correctly
- test_fee_slippage_calculator.py::TestFeeSlippageCalculator::test_nonzero_slippage_reduces_return_correctly
- test_simulator_engine.py::TestMetricsAndSimulationResult::test_matched_open_long_gets_economic_fields
- test_simulator_engine.py::TestMetricsAndSimulationResult::test_matched_open_short_gets_economic_fields

Proof NO_ENTRY / UNKNOWN do not fabricate trade economics:

- test_simulator_engine.py::TestMetricsAndSimulationResult::test_matched_no_entry_does_not_fabricate_economics
- test_simulator_engine.py::TestMetricsAndSimulationResult::test_matched_unknown_does_not_fabricate_economics
- test_simulator_engine.py::TestMetricsAndSimulationResult::test_matched_unmatched_counts_and_accuracy_summary

Proof Package 5A behavior still works:

- test_config_models.py still passes after config extension.
- test_simulator_engine.py still passes after economic enrichment.
- Exact-key correlation, duplicate-key deterministic handling, and malformed JSONL non-crash behavior remain covered by the existing 5A-derived tests in test_simulator_engine.py.

Proof malformed verdict JSONL still does not crash the run:

- test_simulator_engine.py::TestVerdictLoader::test_malformed_lines_skipped_with_warning
- test_simulator_engine.py::TestMetricsAndSimulationResult::test_run_simulation_does_not_crash_on_malformed_jsonl

Proof deterministic behavior preserved:

- test_simulator_engine.py::TestMetricsAndSimulationResult::test_deterministic_behavior_preserved

Proof no forbidden Phase 1-4 production files were modified by this task:

- Targeted status command used:
  - git status --short -- apps/reference/domains/alpha_search/judge/simulator config/judge_simulator.yaml tests/domains/alpha_search/judge/simulator docs/LLM_JUDGE/PHASE5_PACKAGE_5B_REPORT.md apps/reference/domains/alpha_search/judge/contracts.py apps/reference/domains/alpha_search/judge/config_models.py apps/reference/domains/alpha_search/judge/verdict/verdict_synthesizer.py apps/reference/domains/alpha_search/backtest_plugin.py apps/reference/domains/decision_making apps/reference/domains/execution_position apps/reference/main.py apps/reference/config_loader.py
- Status output showed only:
  - ?? apps/reference/domains/alpha_search/judge/simulator/
  - ?? config/judge_simulator.yaml
  - ?? docs/LLM_JUDGE/PHASE5_PACKAGE_5B_REPORT.md
  - ?? tests/domains/alpha_search/judge/simulator/
- No status entries appeared for:
  - apps/reference/domains/alpha_search/judge/contracts.py
  - apps/reference/domains/alpha_search/judge/config_models.py
  - apps/reference/domains/alpha_search/judge/verdict/verdict_synthesizer.py
  - apps/reference/domains/alpha_search/backtest_plugin.py
  - apps/reference/config_loader.py
- Reservation:
  - the same targeted status showed unrelated pre-existing modified forbidden files outside Package 5B scope:
    - apps/reference/domains/decision_making/deferred_scheduler.py
    - apps/reference/domains/execution_position/limit_order_monitor.py
    - apps/reference/domains/execution_position/metrics_aggregator.py
    - apps/reference/main.py

## 12. Regression Statement

- No live trading runtime behavior was modified.
- No runtime events were added.
- No simulator imports were added into live runtime modules.
- No Phase 1-4 contract or schema file was modified.
- JudgeCortexConfig mode admission remains unchanged because judge/config_models.py was not edited.
- Package 5A public API remains present; Package 5B only extended it additively.

## 13. What Remains Deferred To Package 5C+

- Per-expert accuracy aggregation.
- Disagreement analytics.
- Calibration dataset writing.
- Summary writer and aggregate reporting outputs.
- CLI harness.
- Any integration with backtest_plugin.shutdown().
- Any decision_making or runtime advisory work.
- Any mode admission changes.
- Any exchange-specific or multi-leg fee/slippage modeling.

## 14. Risks/Caveats

- The current fee/slippage model is intentionally minimal and subtracts one per-cycle fee cost and one per-cycle slippage cost from raw return.
- Because the current simulator config remained flat for compatibility with Package 5A, it does not yet mirror the richer nested blueprint examples.
- Non-actionable verdicts intentionally keep economic fields as None even if an outcome row contains trade data; that is a policy choice for Package 5B and should be revisited only if a later SSOT requires counterfactual abstain economics.
- The working tree still contains unrelated forbidden-file modifications outside this task, so reviewers should inspect only the Package 5B paths when validating this package.
