# Alpha Search Testing

## 1. Test Strategy

The current test surface mirrors the current domain shape. alpha_search is no longer covered by only model-level tests.

The suite now spans four layers:

1. core alpha scoring and plugin behavior
2. judge contracts, experts, chamber, envelope, and verdict flow
3. Phase 5 simulator and shutdown export
4. standalone runtime tooling under runtime/

That split matters. A change can easily look local while actually touching one of the other three layers.

## 2. Main Test Families

### 2.1 Core Domain and Plugin Tests

Representative files under tests/domains/alpha_search/:

- test_backtest_plugin.py
- test_aurora_adapter.py
- test_ensemble_features_plumbing.py
- test_models_determinism.py
- test_objective_feedback.py
- test_registry_fail_closed.py

These tests cover provider scoring, feature plumbing, fail-closed behavior, and plugin-side feedback loops.

### 2.2 Judge Shadow Tests

Representative files under tests/domains/alpha_search/judge/:

- test_config.py
- test_shadow_mode_admission.py
- test_expert_provider_integration.py
- chamber/test_chamber_aggregator.py
- envelope/test_envelope_assembler.py
- verdict/test_verdict_synthesizer.py

These tests are the authority for shadow-only admission, expert-output flow, chamber aggregation, evidence envelopes, and verdict synthesis.

### 2.3 Simulator Tests

Representative files under tests/domains/alpha_search/judge/simulator/:

- test_cli.py
- test_simulator_engine.py
- test_calibration_dataset_writer.py
- test_summary_report_writer.py
- test_shutdown_integration.py
- test_config_schema_validator.py

These tests prove the offline simulator line, including the bounded shutdown export seam.

### 2.4 Standalone Runtime Tests

Representative files under tests/apps/reference/domains/alpha_search/tests/:

- test_launcher.py
- test_scenario_manager.py
- test_scenario_worker.py
- test_feature_mirror_writer.py
- test_reporting.py
- test_backtest_plugin_integration.py

These tests cover the historical standalone runtime path, scenario orchestration, reporting, and compatibility tooling.

## 3. What Must Be Verified for Code Changes

### 3.1 Scoring or Provider Changes

Prioritize:

- core domain tests under tests/domains/alpha_search/
- any provider-specific or adapter-specific tests
- fail-closed and determinism checks

### 3.2 Judge Pipeline Changes

Prioritize:

- tests/domains/alpha_search/judge/
- verb and mode-admission tests
- shadow-only regression coverage

### 3.3 Simulator Changes

Prioritize:

- tests/domains/alpha_search/judge/simulator/
- shutdown integration coverage when touching plugin shutdown export

### 3.4 Standalone Runtime Changes

Prioritize:

- tests/apps/reference/domains/alpha_search/tests/
- launcher, contracts, mirror writer, reporting, and scenario tests tied to the runtime module being changed

## 4. Practical Test Slices

Typical focused runs are:

- pytest tests/domains/alpha_search
- pytest tests/domains/alpha_search/judge
- pytest tests/domains/alpha_search/judge/simulator
- pytest tests/apps/reference/domains/alpha_search/tests

The important rule is not to assume one slice covers the full domain. The current test layout is intentionally split because the runtime surfaces are split.

## 5. Persistent Gap Pattern

The main verification risk is undersampling the domain.

If a change touches embedded plugin flow, standalone runtime flow, or shutdown export boundaries, run the slice that matches that surface explicitly. alpha_search is now too broad for the old model-only test mental model.
