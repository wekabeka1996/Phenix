# Calibrators Inventory

Generated at: 2026-05-07T10:40:59.9867185Z
Repo commit: 46eda09769a5744a993f5d8b37bcc6429af66d70

This inventory covers the calibrator-like files explicitly inspected for CALIBRATORS_FOUNDATION_PACKAGE_01 and CALIBRATORS_FOUNDATION_PACKAGE_01B.

## Moved Definite Calibrators

| Status | Old Path | New Path | Category | Scope | CLI | Writes Config? | Inputs | Outputs | Tests | Move Risk | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| moved_with_wrapper | tools/calibration/calibrate_aurora_thresholds.py | calibrators/strategies/calibrate_aurora_thresholds.py | definite_calibrator | strategies | yes | no | aurora.yaml; recorder-features-v2; aurora-logs | candidate_aurora_threshold_overlay.yaml; run_manifest.json; baseline/candidate/validation/forward metrics; report.md | tests/tools/test_aurora_threshold_calibrator.py | LOW | Production Aurora threshold surface; old path kept as wrapper; active references retargeted to canonical module where safe |
| moved_with_wrapper | tools/calibration/calibrate_aurora_regime_params.py | calibrators/regimes/calibrate_aurora_regime_params.py | definite_calibrator | regimes | yes | no | data/recorder; symbol/date window; regime_calibration helpers | candidate_regime_overlay.yaml; best_trial.json; report.md | none found | MEDIUM | Research regime overlay search; depends on tools/regime_calibration support package |
| moved_with_wrapper | tools/calibration/calibrate_aurora_signal_weights.py | calibrators/strategies/calibrate_aurora_signal_weights.py | definite_calibrator | strategies | yes | no | aurora.yaml; recorder CSV; optional sklearn/scipy deps | legacy Aurora overlay candidates; report artifacts | none found | MEDIUM | Legacy research-only Aurora surface; not active production path |
| moved_with_wrapper | tools/calibration/calibrate_md_amr_weights.py | calibrators/strategies/calibrate_md_amr_weights.py | definite_calibrator | strategies | yes | no | md_amr.yaml; strategies.yaml; recorder 900s bars; optional Binance hydration | candidate overlay YAML; candidate_bundle.json; best_trial.json; run_manifest.json; metrics JSON; report.md | tests/tools/test_md_amr_weight_calibrator.py | LOW | Production-aligned md_amr calibrator; wrappers preserve old import and CLI path |
| moved_with_wrapper | tools/calibration/calibrate_mean_reversion_params.py | calibrators/strategies/calibrate_mean_reversion_params.py | definite_calibrator | strategies | yes | no | mean_reversion.yaml; strategies registry; recorder bars | candidate_mean_reversion_overlay.yaml; candidate bundle; metrics JSON; report.md | tests/tools/test_mean_reversion_param_calibrator.py | LOW | Production-aligned MR parameter calibrator with train/validation/forward windows |
| moved_with_wrapper | tools/calibration/calibrate_nrr062_historical.py | calibrators/policy_gates/calibrate_nrr062_historical.py | definite_calibrator | policy_gates | yes | no | config/aurora; data/raw/binance_um_klines; Binance klines; runtime decision primitives | processed calibration data; results.json; markdown report; YAML patch candidate | tests/tools/test_calibrate_nrr062_historical.py | MEDIUM | Policy-gate calibrator with cross-domain imports and external Binance input |
| moved_with_wrapper | tools/calibration/calibrate_objective_stack.py | calibrators/strategies/calibrate_objective_stack.py | definite_calibrator | strategies | yes | no | config root; stage-1 candidate overlays; objective dataset inputs; WAL and ledger for dataset build | dataset bundle; candidate_bundle.json; overlay bundle; best_trial.json; report.md | tests/tools/test_objective_calibration.py | MEDIUM | Meta/stage-2 orchestrator over stage-1 outputs; objective_calibration support stays in tools |
| moved_with_wrapper | tools/calibration/calibrate_system_stress_weights.py | calibrators/policy_gates/calibrate_system_stress_weights.py | definite_calibrator | policy_gates | yes | no | data/recorder; config_loader; dataset manifest; walk-forward/oracle options | candidate_summary.json; candidate_metrics.json; walkforward_metrics.csv; yaml_patch_snippet.yaml; report.md | tests/test_system_stress_calibration.py | MEDIUM | Policy gate calibrator backed by tools/system_stress_calibration core |
| moved_with_wrapper | tools/calibration/run_md_amr_phase2b_aggression_grid.py | calibrators/strategies/run_md_amr_phase2b_aggression_grid.py | definite_calibrator | strategies | yes | no | recorder 900s bars; md_amr.yaml; strategies.yaml; md_amr calibrator | phase2b overlay artifacts; grid outputs; reports | tests/tools/test_md_amr_phase2b_aggression_grid.py | MEDIUM | Analysis-only orchestration layer over md_amr calibrator; canonical import updated |
| moved_with_wrapper | scripts/calibration/calibrate_low_vol_cost_floor.py | calibrators/policy_gates/calibrate_low_vol_cost_floor.py | definite_calibrator | policy_gates | yes | no | reports/*.csv; logs/*.jsonl; data/recorder; fee/slippage CLI parameters | low_vol_trade_dataset.csv; low_vol_threshold_candidates.json; low_vol_candidate_yaml_patch.yaml; LOW_VOL reports | tests/test_calibrate_low_vol_cost_floor.py | MEDIUM | Residual definite calibrator from Package 01; moved into canonical layer with old scripts/calibration path preserved as a thin wrapper |

## Definite Calibrators Not Moved In This Package

No additional definite calibrators remain outside the canonical calibrators layer in the currently inspected set.

## Calibration Support Not Moved

| Status | Old Path | New Path | Category | Scope | CLI | Writes Config? | Inputs | Outputs | Tests | Move Risk | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| not_moved_support_library | tools/objective_calibration/dataset.py | - | calibration_support | shared | no | no | recorder; WAL; ledger | dataset objects and written dataset bundles | indirect via tests/tools/test_objective_calibration.py | HIGH | Shared library used by calibrate_objective_stack; moving it would widen the package beyond entrypoint relocation |
| not_moved_support_library | tools/objective_calibration/overlay.py | - | calibration_support | shared | no | no | candidate structures | overlay bundle files | indirect via tests/tools/test_objective_calibration.py | HIGH | Objective overlay writer library |
| not_moved_support_library | tools/objective_calibration/report.py | - | calibration_support | shared | no | no | best candidate; dataset manifest; overlay paths | objective calibration markdown report | indirect via tests/tools/test_objective_calibration.py | HIGH | Objective report renderer library |
| not_moved_support_library | tools/objective_calibration/search.py | - | calibration_support | shared | no | no | realized/attempted datasets; config root; strategy bundle | candidate rankings and metrics | indirect via tests/tools/test_objective_calibration.py | HIGH | Objective candidate search library |
| not_moved_support_library | tools/regime_calibration/io.py | - | calibration_support | shared | no | no | recorder files | loaded recorder DataFrame | indirect via calibrate_aurora_regime_params.py | HIGH | Regime calibration IO helper |
| not_moved_support_library | tools/regime_calibration/metrics.py | - | calibration_support | shared | no | no | confusion/label series | metrics and confusion summaries | indirect via calibrate_aurora_regime_params.py | HIGH | Regime metrics helper |
| not_moved_support_library | tools/regime_calibration/oracle.py | - | calibration_support | shared | no | no | forward bars and labels | oracle labels | indirect via calibrate_aurora_regime_params.py | HIGH | Regime oracle helper |
| not_moved_support_library | tools/regime_calibration/search.py | - | calibration_support | shared | no | no | regime overlays and datasets | candidate overlay evaluation | indirect via calibrate_aurora_regime_params.py | HIGH | Regime search helper |
| not_moved_support_library | tools/system_stress_calibration/core.py | - | calibration_support | shared | no | no | recorder data; oracle and walk-forward config | candidate specs; metrics; ranking tuples | indirect via tests/test_system_stress_calibration.py | HIGH | System stress calibration core library |

## Audit-Only Files Not Moved

| Status | Old Path | New Path | Category | Scope | CLI | Writes Config? | Inputs | Outputs | Tests | Move Risk | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| not_moved_audit_only | tools/forensics/confidence_calibration.py | - | audit_only | unknown | yes | no | runtime logs and confidence traces | ECE/Brier style diagnostics and recommendations | none found | HIGH | Post-hoc forensics, not a primary calibrator entrypoint |
| not_moved_audit_only | tools/forensics/full_surface_calibration.py | - | audit_only | unknown | yes | no | recorder and backtest-style study inputs | analysis reports | none found | HIGH | Forensics study surface, not a canonical calibrator |
| not_moved_audit_only | tools/forensics/mr_calibration_from_logs.py | - | audit_only | unknown | yes | no | bars_300s.jsonl and log-derived signals | MR replay/audit outputs | none found | HIGH | Log-driven forensics script, not stage-1 calibrator |
| not_moved_audit_only | tools/forensics/shadow_regime_aurora_calibration.py | - | audit_only | unknown | yes | no | shadow telemetry and regime labels | shadow calibration/audit outputs | none found | HIGH | Shadow-telemetry forensic analysis |
| not_moved_audit_only | scripts/forensics/nrr027_per_regime_calibrator.py | - | audit_only | unknown | yes | no | NRR-027 gate data slices and replay inputs | regime-stratified audit outputs | none found | HIGH | Forensics script under scripts/, not part of the safe tools/ relocation set |

## Candidate-Uncertain Files Not Moved

| Status | Old Path | New Path | Category | Scope | CLI | Writes Config? | Inputs | Outputs | Tests | Move Risk | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| not_moved_uncertain | tools/parquet_pipeline/tune_presets.py | - | candidate_uncertain | unknown | yes | no | parquet stress inputs; preset grids | report.md and analysis outputs | none found | HIGH | Tuning-oriented analysis utility; not proven as canonical calibrator |
| not_moved_uncertain | tools/parquet_pipeline/regime_grid.py | - | candidate_uncertain | unknown | no | no | parquet/polars regime grid inputs | grid-search helper outputs | none found | HIGH | Grid-search logic exists, but package role is still uncertain and was not moved automatically |

## Summary

- definite_calibrator: 10
- calibration_support: 9
- replay_or_data_input: 0
- audit_only: 5
- not_calibrator: 0
- candidate_uncertain: 2
- moved: 10
- not moved: 16
