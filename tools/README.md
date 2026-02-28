# Tools Directory

This directory contains utility functions and analytical tools, grouped by operational domain.

## 📂 analysis
Tools for examining outputs and test distributions.
- `analyze_health.py`: Checks the RL/Neocortex model health metrics.
- `analyze_test_results.py`: Parses JUnit XML reports for aggregated test failure patterns.
- `bars_regime_analysis.py`: Analyzes backtest results to build regime datasets.
- `sl_fill_sensitivity.py`: Backtest script simulating SL slippage sensitivity.
- `plot_dataset.py`: Visualizes OHLCV bars, regimes, and confidence with `matplotlib`.

## 📂 ci_cd
Integrations and automated checks used as CI/CD gates.
- `audit_yaml_loading.py`: Validates that Pydantic properly loads the `aurora` YAML configs.
- `inventory_config_defaults.py`: Checks AST definitions to ensure the "Zero Defaults" policy.
- `validate_configs.py`: High-level structural validation of configuration files.
- `compare_run_config_snapshot.py`: Compares a backtest config snapshot against the current branch.

## 📂 diagnostics
Scripts that poke the live system, the exchange, or perform deep traces.
- `check_orders.py` / `check_positions.py`: Binance connection tests to print active states.
- `diagnose_execution.py`: Guardian checks enforcing determinism and safety limits.
- `measure_api_latency.py`: RTT latency tests for `fapi.binance.com`.
- `validate_testnet.py`: E2E Binance Testnet validation for Orders/Margins.
- `smoke_tidy_gate.py`: Quick `grep` through the guardian logs.
- `verify_config.py` / `verify_flip_config.py`: Fast import smoke tests for config loads.
- `execution_vs_upstream_trace_01.py`: Compares execution traces vs decision-making intents.
- `log_audit.py`: Validates core invariants against logs (e.g. "DENY never becomes OPEN").
- `feature_integrity_replay_check.py`: WAL log sanity and replay integrity verification.

## 📂 monitoring
Operational observability scripts meant to be run periodically.
- `live_observability_summary.py`: Aggregates TTF, fill counts, and reject rates.
- `obs02_ctx_log_inventory.py`: Inventories JSONL logs to verify log formats.
- `extract_equity_free_usdt.py`: Extracts free equity balances from system logs.
- `analyze_wal.py`: Reads the WAL (Write-Ahead Log) to diagnose system deviations.
- `metrics_summary.py`: Extracts basic operational metrics.

## 📂 forensics
Deep incident investigation tooling.
- `forensic_analysis.py`: Post-mortem diagnostics, specifically for PPO loss checks.
- `dir_strength_forensics.py`: Focuses on scoring distributions (Direction vs Strength).
- `gate_effect_report.py`: Evaluates the drop-off rates due to liquidity/cost gates.
- `confidence_calibration.py`: Calibrates confidence thresholds against historical logs.
- `pipeline_counts_report.py` / `rid_duplicates_report.py`: Verifies the robustness of WAL logs.

## 📂 simulation
- `regime_replay.py`: Generates synthetic price data (trends, spikes) to test Regime Detection.
- `strategy_replay.py`: Re-evaluates DecisionMaking logic historically to verify gates offline.
- `config_tuner.py`: Simulates A/B tests with configs against historical feature logs.

## 📂 docs_gen
- `build_project_atlas.py`: Compiles the `PROJECT_ATLAS.md` from schemas and events.
- `generate_config_map.py` / `generate_trading_config_audit.py`: Generates config documentations.
- `generate_config_default_path_map.py`: Builds YAML mapping files.

## 📂 backtest
- `backtest_diagnostics.py` / `backtest_summarize.py`: Post-processing logic for backtest metrics.

## 📂 cli
- `auroractl.py`: A wrapper CLI for quick environment actions (config-validate, diff).
