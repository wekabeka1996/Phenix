# Scripts Directory

This directory contains standalone executable scripts grouped by purpose.

Root-level Python files are compatibility launchers.
Canonical implementations now live in the subfolders below.

## analysis
One-off analytical utilities and post-run investigations.
- `analyze_alpha_search_log_pnl.py`
- `analyze_reject_forensics_72h.py`
- `analyze_testnet_transactions_md.py`

## benchmarks
Strategy and market benchmark runners.
- `analyze_alpha_performance.py`
- `btcusdt_benchmark.py`
- `multi_day_benchmark.py`
- `real_market_benchmark.py`

## data
ETL and backtest dataset preparation.
- `data_converter.py`
- `prepare_backtest_data.py`

## diagnostics
Connectivity checks, probes, and backtest diagnostics.
- `backtest_log_stats.py`
- `config_forensics.py`
- `diagnose_binance_api.py`
- `fetch_binance_testnet_transactions_md.py`
- `mr_restore_002_probe.py`
- `run_backtest_ladder.py`
- `run_mr_backtest.py`
- `run_single_backtest.py`

## docs_gen
Documentation synthesis helpers.
- `synthesize_ssot_docs.py`

## forensics
Broader incident and audit reporting.
- `analyze_live_wal_trades.py`
- `aurora_forensic_report.py`

## maintenance
Migration and cleanup helpers.
- `migrate_config_get_calls.py`
- `remove_failed_tests.py`
- `rename_mean_reversion_1m_to_mean_reversion.py`

## optimization
Optimization runners and experiment entrypoints.
- `run_optuna.py`
- `run_research_optuna.py`

## runners
Standalone domain runners.
- `run_alpha_search_domain.py`

## simulation
Local simulation utilities.
- `neocortex_shadow_simulator.py`

## testing
Ad-hoc test execution outside pytest.
- `test_simulated_adapter.py`

## tmp
Temporary research helpers kept out of the main root listing.
- `tmp_alpha_search_fee_adjusted_pnl.py`
- `tmp_neocortex_runtime_report.py`
