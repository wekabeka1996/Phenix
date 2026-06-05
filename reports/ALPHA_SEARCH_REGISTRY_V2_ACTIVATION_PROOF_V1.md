# ALPHA_SEARCH_REGISTRY_V2_ACTIVATION_PROOF_V1

## Scope
Task: ALPHA_SEARCH_REGISTRY_V2_AND_TA_PLANE_ACTIVATION_P0

## Facts
- launcher default config now resolves config/alpha_search/scenario_registry_v2.yaml.
- load_matrix_config(default_registry_path) produced matrix_id=registry:shadow_expansion_v2_20260516:v2 with 30 enabled scenarios.
- Synthetic registry_v2 TA probe session: 20260518_115438_registry_v2_ta_probe
- Default launcher partial replay session: 20260518_114623
- Synthetic probe runtime matrix rows: 30
- Synthetic probe ta_features_missing_for_bar rows: 0
- Synthetic probe non-neutral materialized result rows: 33
- Synthetic probe authority violations: 0
- Default launcher partial replay runtime matrix rows: 30
- Default launcher partial replay ta_features_missing_for_bar rows: 30
- Default launcher partial replay authority violations: 0

## Inferences
- registry_v2 is active on the standalone loader path and produces a full 30-scenario runtime manifest.
- TA-populated alpha_input snapshots are now sufficient for alpha_search ScenarioWorker to emit synthetic EVT:TA_FEATURES_CALCULATED and avoid fail-closed ta_features_missing_for_bar outcomes.
- Historical replay input under logs/alpha_input/alpha_input_v1.jsonl still reflects pre-fix data; its fail-closed TA warnings are evidence about stale artifacts, not about the new mirror-writer code path.

## Unproven
- A fresh end-to-end apps/reference/main.py run that regenerates alpha_input_v1.jsonl from the live event bus was not executed here.

## Validation
- Focused pytest slices covering launcher, feature_mirror_writer, registry adapter, scenario worker, scenario manager, reporting, and contracts passed.
- Broader alpha_search suite result: 306 passed, 1 failed, 18 skipped.
- Residual unrelated failure: tests/apps/reference/domains/alpha_search/tests/test_regression.py::TestThresholdSync::test_aurora_threshold_scales_with_regime (expected 0.18, obtained 0.0216).

## Artifacts
- reports/ALPHA_SEARCH_REGISTRY_V2_LOAD_MATRIX_V1.csv
- reports/ALPHA_SEARCH_TA_PLANE_ACTIVATION_PROOF_V1.csv
- reports/ALPHA_SEARCH_REGISTRY_V2_SIGNAL_MATERIALIZATION_V1.csv
- reports/ALPHA_SEARCH_REGISTRY_V2_AUTHORITY_AUDIT_V1.json
- reports/ALPHA_SEARCH_REGISTRY_V2_ACTIVATION_SUMMARY_V1.json
