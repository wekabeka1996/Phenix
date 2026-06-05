# Tools Directory

This directory contains maintenance, diagnostics, and research utilities grouped by domain.

Root-level Python and PowerShell files are compatibility launchers.
Canonical implementations now live in the subfolders below.

## analysis
Exploratory analysis and post-run reports.
- `analyze_features.py`
- `analyze_health.py`
- `async_ast_analyzer.py`
- `analyze_test_results.py`
- `bars_regime_analysis.py`
- `generate_async_report.py`
- `plot_dataset.py`
- `sl_fill_sensitivity.py`

## alpha_search
Alpha-search specific tooling.
- `alpha_search_report.py`
- `alpha_search_runtime_summary.py`
- `build_alpha_input.py`

## backtest
Backtest post-processing and diagnostics.
- `backtest_diagnostics.py`
- `backtest_summarize.py`

## calibration
Parameter calibration and selection tooling.
Canonical implementations now live under `calibrators/`.
Use `config/docs/CALIBRATION_STANDARD_V1.md` and `calibrators/README.md` for current governance and inventory.
Files left in `tools/calibration/` are compatibility wrappers.
- `calibrate_aurora_thresholds.py`
- `calibrate_aurora_regime_params.py`
- `calibrate_aurora_signal_weights.py`
- `calibrate_md_amr_weights.py`
- `calibrate_mean_reversion_params.py`
- `calibrate_objective_stack.py`
- `calibrate_system_stress_weights.py`

## ci_cd
Config validation and CI gate scripts.
- `audit_yaml_loading.py`
- `compare_run_config_snapshot.py`
- `inventory_config_defaults.py`
- `validate_configs.py`

## cli
Command-line entrypoints.
- `auroractl.py`

## diagnostics
Live checks, testnet probes, replay verification, and trace tooling.
- `check_orders.py`
- `check_positions.py`
- `diagnose_latent.py`
- `diagnose_execution.py`
- `execution_vs_upstream_trace_01.py`
- `feature_integrity_replay_check.py`
- `log_audit.py`
- `measure_api_latency.py`
- `quadratic_regime_repro.py`
- `smoke_tidy_gate.py`
- `validate_testnet.py`
- `verify_config.py`
- `verify_flip_config.py`

## docs_gen
Project atlas and config documentation generators.
- `build_project_atlas.py`
- `config_default_path_map.yaml`
- `generate_config_default_path_map.py`
- `generate_config_map.py`
- `generate_trading_config_audit.py`

## forensics
Incident analysis, WAL forensics, and post-mortem tooling.
- `bracket_coverage_report.py`
- `confidence_calibration.py`
- `deep_wal_forensics.py`
- `dir_strength_forensics.py`
- `entry_execution_report.py`
- `entry_fill_audit.py`
- `extract_last_trades.py`
- `forensic_analysis.py`
- `forensic_analysis_v2.py`
- `gate_effect_report.py`
- `log_forensics_cancel_audit.py`
- `pending_entry_counterfactuals.py`
- `pipeline_counts_report.py`
- `post_cancel_price_drift.py`
- `rid_duplicates_report.py`
- `wal_intent_summary.py`

## maintenance
Repository hygiene and one-off refactoring helpers.
- `autofill_config_defaults_into_yaml.py`
- `ascii_sanitize_repo.py`
- `batch_replace_tests.py`
- `rescue_brain.py`
- `reset_ppo.py`
- `rewire_config_models_remove_defaults.py`
- `sanitize_configs.py`
- `sanitize_repo_bytes.py`

## monitoring
Operational observability and recurring runtime checks.
- `analyze_log.ps1`
- `analyze_log_detail.ps1`
- `analyze_wal.py`
- `extract_equity_free_usdt.py`
- `live_observability_summary.py`
- `metrics_summary.py`
- `obs02_ctx_log_inventory.py`
- `parse_aurora_logs.py`
- `restart_shadow_telemetry.ps1`

## parquet_contract
Local parquet contract validation helpers.

## parquet_pipeline
Offline parquet dataset build, audit, stress, and preset tooling.

## regime_calibration
Low-level regime calibration support modules.

## system_stress_calibration
Offline helpers for system stress oracle construction, offline overlay replay, and weight grid search.

## simulation
Offline simulation, replay, and config tuning utilities.
- `config_tuner.py`
- `md_amr_data_adapter.py`
- `regime_replay.py`
- `strategy_replay.py`
- `synthetic_llm_intent_generator.py`

## testing
Ad-hoc test runners that are not part of the main pytest suite.
- `run_order_tests.py`
- `run_tests.py`
