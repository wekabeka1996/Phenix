# BACKTEST GROUND-TRUTH REPORT

## 0. Scope and Method

This report treats current code, current YAML, current test-facing loaders, and concrete artifacts on disk as source of truth.

Older passports, runbooks, and design docs are used only as secondary hints unless they are backed by current runtime code or primary artifacts still present in the repository.

## 1. Executive Verdict

The real current backtest path is a bar-driven Aurora backtest centered on `apps/reference/main.py::run_backtest_simulation()`.

Current canonical side B is **Aurora-only**, with active universe derived from `strategies_registry.assignments` in `config/aurora/strategies.yaml`.

Current Aurora scoring intent is **Quadratic + signed_v2**, but the runtime still contains a local fail-open scoring fallback from `QuadraticScoringKernel` to `AuroraScoringKernel`.

Current backtests are reproducible, but they are **not guaranteed to be canonical-clean**, because `BacktestEngine.load_data()` warns and skips symbols with missing parquet instead of failing the run.

That behavior is the critical reason why existing backtest artifacts must be interpreted through a data-coverage lens first.

## 2. Real Entrypoints

### 2.1 Primary backtest launchers

The real CLI entrypoints present in the repo are:

- `scripts/diagnostics/run_single_backtest.py`
- `scripts/diagnostics/run_backtest_ladder.py`
- `scripts/diagnostics/run_mr_backtest.py`
- `scripts/optimization/run_optuna.py`
- `python -m apps.reference` via `apps/reference/main.py`

For practical current-side-B reproduction, the main launcher is `scripts/diagnostics/run_single_backtest.py`.

### 2.2 Why `run_single_backtest.py` matters

`run_single_backtest.py` explicitly documents a state-leakage problem if `run_backtest_simulation()` is called twice in one process. It therefore acts as the safest manual baseline launcher for A/B single-window runs.

It selects config dir by side:

- side A → `config/aurora_baseline`
- side B → `config/aurora`

Then it:

1. loads config through `ConfigLoader(config_dir=...)`
2. mutates `config.trading.backtest.start_date`
3. mutates `config.trading.backtest.end_date`
4. mutates `config.trading.backtest.initial_balance`
5. wires logging
6. calls `run_backtest_simulation(config, return_result=True)`

This means the launcher is intentionally thin. The runtime truth is in `run_backtest_simulation()` and below.

## 3. Config Resolution Truth

### 3.1 Loader chain

`ConfigLoader.load_config()` merges the canonical YAML fragments in this order:

1. `system.yaml`
2. `trading.yaml`
3. `regime.yaml`
4. `domains.yaml`
5. `instruments.yaml`
6. `strategies.yaml`

Then it applies:

- environment variable resolution
- backtest symbol filtering if an explicit backtest subset is requested
- mode-specific overrides
- SSOT derivation of `trading.symbols_to_track`
- strict validation and contract checks

### 3.2 Current universe SSOT

The important invariant is not the old comments inside `aurora.yaml`. It is the registry.

`ConfigLoader._derive_symbols_to_track_ssot()` derives `trading.symbols_to_track` from `strategies_registry.assignments` keys.

Current canonical side B assignments are:

- `ETHUSDT: [aurora]`
- `SOLUSDT: [aurora]`
- `XRPUSDT: [aurora]`
- `BTCUSDT: [aurora]`
- `BNBUSDT: [aurora]`
- `1000PEPEUSDT: [aurora]`

This establishes the current side B six-symbol universe.

## 4. Actual Runtime Call Chain

### 4.1 Backtest bootstrap

`run_backtest_simulation()` does the following:

1. creates run id
2. isolates WAL to `ops/wal/backtest/<run_id>`
3. resolves `trading.backtest.backtest_mode` (`strict` or `relaxed`)
4. wires `MockClock` globally through `set_clock()`
5. redirects order logger to `logs/backtests/order_log_<run_id>.jsonl`
6. reads start/end dates and initial balance from `config.trading.backtest`
7. resolves symbols from `config.trading.symbols_to_track`
8. constructs `BacktestEngine`
9. registers backtest domains and strategy plugins
10. executes `engine.run()`
11. builds `backtest_<run_id>.json` and the run bundle directory

### 4.2 Domains actually wired in backtest

Backtest mode registers:

- `FeatureEngineering`
- `RegimeDetector`
- `SystemStressOverlay`
- `RiskManagement`
- `DecisionMaking`
- `BacktestExecPosFSM`

Notably, live `PositionTracking` is not used as the portfolio truth source in backtest. Instead, the backtest engine itself emits portfolio updates to prevent deadlock on `NRR-PORTFOLIO-UNKNOWN`.

### 4.3 Strategy handlers actually wired

Backtest mode attempts to register:

- `AuroraBuiltinPlugin`
- `MeanReversionPlugin`
- `AlphaSearchBacktestPlugin`

But the registry decides whether a strategy is actually used for signals.

Current side B registry assigns only `aurora`, so the effective live path for current canonical side B is Aurora-only.

Mean Reversion is currently **wired but inactive** in canonical side B.

AlphaSearch is explicitly optional and warning-only on init failure.

## 5. Strategy, Regime, and Scoring Truth

### 5.1 Strategy truth

Current side B strategy truth:

- Aurora is active
- Mean Reversion is registered but inactive in the current registry
- Arbitration is configured, but with current assignments there is no real multi-strategy contest on side B

### 5.2 Regime truth

Current regime basis is the 5m bar path with `basis_tf_sec: 300` in `config/aurora/regime.yaml`.

Key current regime parameters visible in YAML:

- `basis_tf_sec: 300`
- `uncertain_cutoff: 0.22`
- `hysteresis_bars: 3`
- `models.sma_trend.sma_short_period: 48`
- `models.sma_trend.sma_long_period: 192`
- `models.volatility.atr_period: 14`
- `models.volatility.atr_sma_length: 288`

System stress exists in config but is currently disabled by default:

- `system_stress.enabled: false`

So the current regime stack is present and wired, but stress attenuation does not materially affect default current backtests unless explicitly enabled.

### 5.3 Scoring truth

Current Aurora scoring config in `config/aurora/strategies/aurora.yaml` sets:

- `signals.normalize_signals_mode: signed_v2`
- `decision.scoring_version: quadratic`

`AuroraConfigLoaderMixin` activates `QuadraticScoringKernel` when scoring version is `quadratic`.

But `aurora_decision.py` still contains this runtime behavior:

- try quadratic compute
- if it raises, log `QUADRATIC_FALLBACK`
- recompute locally with `AuroraScoringKernel`

Therefore the true statement is:

- current side B intends to run quadratic scoring
- current side B can still partially degrade to linear scoring without aborting the entire run

That fallback is highly relevant when interpreting any backtest result as “Quadratic Brain” evidence.

## 6. Execution Realism Truth

### 6.1 Data driver

`BacktestEngine` is a bar-replay engine over processed parquet data, defaulting to `timeframe="5m"` in the current main backtest path.

It prefers `*_enriched.parquet` and falls back to plain monthly parquet if enriched files are not present.

### 6.2 Warmup and HTF

The engine extends its data load backward by 210 days for warmup and attempts HTF warmup through `HTFHistoryProvider`.

If HTF provider loading fails, the run continues with a warning.

### 6.3 Fill model

Backtest execution realism is candle-based, not tick-perfect.

The engine passes each bar to `MockBroker.process_data(row)` and the broker processes fills in this order:

1. stop-loss first
2. take-profit second
3. other orders after that

This is a conservative same-bar ordering choice that matters when SL and TP are both reachable in one candle.

### 6.4 Portfolio and order lifecycle

The backtest path emits:

- `EVT:ORDER_FILL`
- `EVT:TRADE_EXECUTED`
- backtest portfolio heartbeats

It intentionally skips the live backtest order-index guard to avoid blocking all subsequent entries in a replay environment.

## 7. Critical Fail-Open / Fail-Closed Behaviors

### 7.1 Good fail-closed behaviors

The current backtest path is fail-closed on:

- invalid backtest mode values
- invalid date format parsing in backtest config
- duplicate config paths under strict mode
- OHLCV data contract violations after parquet load
- zero loaded frames across all symbols

### 7.2 Dangerous fail-open behaviors

The current path is still fail-open on several important degradations:

1. Missing symbol parquet in `BacktestEngine.load_data()` is a warning, not a hard failure.
2. Missing HTF warmup provider is a warning, not a hard failure.
3. AlphaSearch plugin init failure is a warning, not a hard failure.
4. Quadratic scoring failure is logged and locally downgraded to linear Aurora scoring.

The most operationally important one is symbol skip-on-warning. It allows a run to complete on a partial universe while keeping metadata that still lists the full configured symbol set.

## 8. Current Baseline Status

### 8.1 Best current side B reference artifact

The most useful current March side B reference artifact is:

- `reports/backtests/backtest_20260312_132130.json`

Why this one:

- it is a finished run bundle with report + manifest + resolved config + result + order log
- it matches the currently available March processed coverage window
- it already reflects the current six-symbol configured side B universe in metadata

### 8.2 Why it is not canonical-clean

It is still not a full-universe clean benchmark because:

- `SOLUSDT` has no processed 5m enriched coverage
- `XRPUSDT` has no processed 5m enriched coverage
- `BacktestEngine` skips symbols with missing parquet by warning

So March side B runs are reproducible, but they are reproducible in a degraded partial-universe state.

### 8.3 Q2 and Mar-Jun status

Q2 / Mar-Jun canonical research remains blocked by processed coverage gaps already established in:

- `reports/processed_data_coverage_audit_q2_2024.md`
- `reports/q2_processed_backfill_runbook_uk.md`
- `reports/run_integrity_audit_20260312_132130_vs_20260313_031152.md`

## 9. Final Ground-Truth Conclusions

1. The repo’s real backtest engine today is the Aurora bar-driven backtest path through `run_backtest_simulation()`.
2. Current canonical side B is Aurora-only, not Aurora+MR.
3. Current scoring intent is quadratic, but runtime truth includes local linear fallback.
4. Current backtests are reproducible only with strong caution about data coverage and silent symbol skipping.
5. Any future strategy research should treat current March runs as partial-universe forensic evidence, not as canonical full-universe baselines.