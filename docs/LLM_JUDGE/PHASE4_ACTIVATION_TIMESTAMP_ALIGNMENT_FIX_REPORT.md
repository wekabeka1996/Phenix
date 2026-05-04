# LLM Judge Phase 4 — Activation + Timestamp Alignment Corrective Package

## 1. Executive Verdict

DONE

## 2. Scope Implemented

This package implemented exactly two bounded corrections inside alpha_search:

- closed the repo-resident SSOT activation gap by adding explicit judge provider entries to `config/alpha_search.yaml`
- closed the ExpertOutput timestamp alignment gap by passing the decision-cycle `bar_close_ts` into `alpha_score_to_expert_output()` in the real provider path

No Phase 1, Phase 2, Phase 3, or Phase 5 redesign work was performed.

## 3. Root Cause

Issue A: SSOT activation gap

- `config/alpha_search.yaml` shipped a complete `judge:` block for experts, chamber, and verdict
- the shipped `providers:` block still declared only `aurora` and `ta_ensemble`
- runtime judge expert instantiation in `backtest_plugin.py` is provider-driven via `ProviderConfig.judge_expert`
- result: the repo-resident SSOT config did not structurally instantiate the implemented judge shadow pipeline without synthetic provider injection in tests

Issue B: timestamp alignment gap

- `backtest_plugin.py` called `alpha_score_to_expert_output()` without `ts_ms`
- `expert_output_bridge.py` therefore fell back to wall-clock time
- chamber, envelope, and verdict used decision-cycle `bar_close_ts`
- result: judge expert artifacts were not guaranteed to share the same replay key timestamp as downstream chamber and verdict artifacts

## 4. FACTS

- `config/alpha_search.yaml` now contains explicit `judge_sw` and `judge_fn` provider entries under `providers:` using the existing `judge_expert` provider branch only.
- rollout defaults remain `judge.enabled: false` and `judge.mode: "off"`.
- non-judge providers `aurora` and `ta_ensemble` remain present and unchanged in the shipped config.
- `apps/reference/domains/alpha_search/backtest_plugin.py` now passes `ts_ms=bar_close_ts` into `alpha_score_to_expert_output()` from `_process_judge_expert_score()`.
- `apps/reference/domains/alpha_search/judge/experts/expert_output_bridge.py` still retains the fallback `ts_ms is None -> wall clock` behavior for non-plugin callers.
- `tests/domains/alpha_search/judge/test_config.py` now proves the shipped config structurally contains explicit judge provider entries.
- `tests/domains/alpha_search/judge/test_no_live_aurora_regression.py` now proves mode `off` keeps repo judge providers inert and that a disabled repo judge expert is not activated or solicited.
- `tests/domains/alpha_search/judge/test_expert_provider_integration.py` now proves the repo-resident config structure emits the real shadow chain when opt-in fields are enabled and that all judge artifacts share the same cycle timestamp.

## 5. INFERENCES

- the missing provider entries were the only SSOT structural blocker preventing the shipped config from fully describing the judge shadow pipeline
- explicit `ts_ms=bar_close_ts` propagation in the plugin is the narrowest fix for alignment because it closes the real runtime path while preserving the bridge fallback contract
- mode `off` safety remains intact because judge providers may exist in YAML while still not becoming active providers unless runtime admission allows them

## 6. ASSUMPTIONS

- the provider ids `judge_sw` and `judge_fn` are acceptable operator-facing baseline ids because they reuse the already-tested expert provider naming used in the existing integration suite
- preserving bridge fallback behavior for non-plugin callers is intentional and consistent with the task requirement to keep the fix narrow
- proving inert behavior through active provider initialization and runtime provider roster is sufficient evidence for the frozen rule that disabled experts are not solicited

## 7. UNKNOWNS

- no unresolved contradiction was found for the two audit notes addressed by this package
- external overlay configs outside the repository were not audited because the task scope was explicitly repo-resident SSOT alignment

## 8. Files Added

- `docs/LLM_JUDGE/PHASE4_ACTIVATION_TIMESTAMP_ALIGNMENT_FIX_REPORT.md`

## 9. Files Modified

- `config/alpha_search.yaml`
- `apps/reference/domains/alpha_search/backtest_plugin.py`
- `tests/domains/alpha_search/judge/test_config.py`
- `tests/domains/alpha_search/judge/test_no_live_aurora_regression.py`
- `tests/domains/alpha_search/judge/test_expert_provider_integration.py`

## 10. Exact Fix Description

YAML activation contract

- added explicit shipped judge provider entries under `alpha_search.providers`
- `judge_sw` maps to `judge_expert.expert_type: "signal_weights"`
- `judge_fn` maps to `judge_expert.expert_type: "feature_neutrals"`
- entries are shadow-safe because the shipped defaults remain `judge.enabled: false` and `judge.mode: "off"`
- non-judge providers were left intact

Provider timestamp propagation

- `_process_judge_expert_score()` in `apps/reference/domains/alpha_search/backtest_plugin.py` now calls `alpha_score_to_expert_output(..., ts_ms=bar_close_ts)`
- this removes reliance on implicit wall-clock fallback in the normal plugin execution path
- judge `ExpertOutput`, `ChamberAggregate`, `JudgeEvidenceEnvelope`, and `JudgeVerdict` now align on the same decision-cycle timestamp in the real provider path

## 11. Validation Evidence

Exact pytest commands

- `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search/judge -q`
- `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/alpha_search -q`

Pass/fail results

- `tests/domains/alpha_search/judge`: 362 passed, 0 failed
- `tests/domains/alpha_search`: 396 passed, 0 failed

Proof that shipped SSOT config structurally instantiates judge providers

- `tests/domains/alpha_search/judge/test_config.py::TestAlphaSearchConfigIntegration::test_repo_config_includes_explicit_judge_providers`
- `tests/domains/alpha_search/judge/test_no_live_aurora_regression.py::TestQuadraticKernelUnaffected::test_repo_config_declares_explicit_judge_providers`

Proof that runtime opt-in semantics remain safe

- `tests/domains/alpha_search/judge/test_no_live_aurora_regression.py::TestQuadraticKernelUnaffected::test_mode_off_keeps_repo_judge_providers_inert`
- `tests/domains/alpha_search/judge/test_no_live_aurora_regression.py::TestConfigLoadStability::test_judge_defaults_safe`
- `tests/domains/alpha_search/judge/test_no_live_aurora_regression.py::TestQuadraticKernelUnaffected::test_disabled_repo_expert_is_not_initialized_or_solicited`

Proof that `ExpertOutput.ts_ms == cycle timestamp` in the real provider path

- `tests/domains/alpha_search/judge/test_expert_provider_integration.py::TestRepoResidentShadowActivation::test_repo_config_opt_in_emits_full_shadow_chain_with_aligned_timestamps`

Proof that chamber, envelope, and verdict stay timestamp-aligned

- the same integration test asserts `ExpertOutput.ts_ms`, `ChamberAggregate.ts_ms`, `JudgeEvidenceEnvelope.ts_ms`, `JudgeEvidenceEnvelope.chamber_aggregate.ts_ms`, and `JudgeVerdict.ts_ms` all equal the same `bar_close_ts`

Proof that non-judge paths are unchanged

- `tests/domains/alpha_search/judge/test_no_live_aurora_regression.py::TestQuadraticKernelUnaffected::test_aurora_adapter_still_works`
- `tests/domains/alpha_search/judge/test_no_live_aurora_regression.py::TestQuadraticKernelUnaffected::test_ta_ensemble_still_works`
- `tests/domains/alpha_search/judge/test_expert_provider_integration.py::TestNonJudgeProviderUnchanged::test_non_judge_provider_emits_alpha_score_calculated`
- `tests/domains/alpha_search/judge/test_expert_provider_integration.py::TestRepoResidentShadowActivation::test_repo_config_opt_in_emits_full_shadow_chain_with_aligned_timestamps`

## 12. Regression Evidence

- the full `tests/domains/alpha_search/judge` slice passed after the package: 362/362
- the full `tests/domains/alpha_search` slice passed after the package: 396/396
- this broader slice includes non-judge plugin tests, aurora adapter tests, ensemble plumbing tests, model determinism tests, objective feedback tests, and registry fail-closed tests

## 13. Explicit Proof That Guarded Surfaces Were Not Changed

This package changed exactly the five implementation/test files listed in Section 9 plus this report file.

The following guarded surfaces were not changed by this package:

- `apps/reference/main.py`
- `apps/reference/config_loader.py`
- `apps/reference/config_models.py`
- `apps/reference/domains/decision_making/`
- `apps/reference/domains/execution_position/`
- `apps/reference/domains/alpha_search/judge/contracts.py`
- `apps/reference/domains/alpha_search/judge/schemas/`
- `apps/reference/domains/decision_making/quadratic_scoring_kernel.py`

No schema contract, no frozen judge contract, and no Layer 1 scoring module was modified.

## 14. Whether the Phase 4 Audit Notes Can Now Be Cleared

Yes.

- Audit note A is closed because the repo-resident SSOT config now explicitly declares the implemented judge provider structure.
- Audit note B is closed because the real judge provider path now propagates decision-cycle `bar_close_ts` into `ExpertOutput`, and end-to-end tests prove timestamp alignment across expert, chamber, envelope, and verdict artifacts.
