# Scripts Directory

This directory contains standalone execution scripts categorized by their function.

## 📂 data
ETL pipelines and backtest data preparation.
- `build_monthly_parquet.py`: Converts Binance ZIPs to Parquet, deletes raw zips.
- `data_converter.py`: Phase 1 raw CSV -> Parquet converter.
- `prepare_backtest_data.py`: Orchestrates the backtest data generation process.

## 📂 benchmarks
Testing model performance vs baseline.
- `multi_day_benchmark.py`: Extended benchmark evaluating PPO model vs Standard bots over days.
- `real_market_benchmark.py`: Evaluates the bot against real historical market data.
- `analyze_alpha_performance.py`: Analyzes Alpha scores from logs to generate markdown reports.

## 📂 diagnostics
Scripts for deep probing or verifying the system environment.
- `diagnose_binance_api.py`: Validates API connectivity, leverage, and margin endpoints.
- `mr_restore_002_probe.py`: Proof-probe for MeanReversion event forwarding.
- `config_forensics.py`: Audits YAML configs for key overlaps and conflicting entries.
- `backtest_log_stats.py`: Parses backtest order logs to generate win rates, ROI, etc.

## 📂 optimization
- `run_optuna.py`: Entry point for Hyperparameter tuning of the Aurora strategy using Optuna.

## 📂 testing
- `test_simulated_adapter.py`: E2E Smoke test for SimulatedExecutionAdapter outside `pytest`.

## 📂 docs_gen
- `synthesize_ssot_docs.py`: Aggregates configs and writes them into `docs/CONFIG_MAP_SSOT.md`.
