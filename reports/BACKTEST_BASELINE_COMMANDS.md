# BACKTEST BASELINE COMMANDS

## 0. Status

This file documents the safest current baseline commands that can be derived from the repository state.

Important distinction:

- a **reproducible** run is possible now for March 2024 side B
- a **canonical-clean full-universe** run is **not** currently possible for Q2 / Mar-Jun because processed coverage is incomplete

## 1. Preconditions

Run commands from repo root.

Current working assumption for reproducibility:

- `scripts/diagnostics/run_single_backtest.py` is the preferred launcher
- `config/aurora` is the current side B SSOT
- current processed data only fully supports a March-era degraded partial-universe replay

## 2. Config Smoke Command

Use this first to confirm what the loader currently thinks the side B universe is:

```powershell
python -X utf8 -c "from apps.reference.config_loader import ConfigLoader; cfg = ConfigLoader(config_dir='config/aurora').load_config(); print('symbols_to_track:', cfg.trading.symbols_to_track); print('assignments:', cfg.strategies_registry.assignments); print('scoring_version:', cfg.strategies.aurora.decision.scoring_version); print('normalize_signals_mode:', cfg.strategies.aurora.decision.signals.normalize_signals_mode)"
```

Expected high-level outcome today:

- symbols: `1000PEPEUSDT`, `BNBUSDT`, `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`
- scoring version: `quadratic`
- normalize mode: `signed_v2`

## 3. Current Reproducible Side B Baseline

### 3.1 March 2024 side B

This is the safest current reproduction command from existing data state:

```powershell
python scripts/diagnostics/run_single_backtest.py --side B --start 2024-03-01 --end 2024-03-31
```

What this command is good for:

- reproducing the current March-side-B behavior class
- validating code-path continuity after future non-data changes
- comparing against the existing March bundle family

What it is **not** good for:

- asserting full canonical six-symbol coverage
- asserting Q2 readiness

Reason:

- `SOLUSDT` and `XRPUSDT` have no current processed 5m enriched data
- `BacktestEngine` warns and skips missing symbols

So this command reproduces a **degraded partial-universe baseline**.

### 3.2 Output expectations

The run should produce:

- `reports/backtests/backtest_<run_id>.json`
- `reports/backtests/<run_id>/manifest.json`
- `reports/backtests/<run_id>/resolved_config.json`
- `reports/backtests/<run_id>/result.json`
- `logs/backtests/order_log_<run_id>.jsonl`

## 4. Current Reproducible Side A Reference

If you need the current baseline side A comparison command, use:

```powershell
python scripts/diagnostics/run_single_backtest.py --side A --start 2024-03-01 --end 2024-03-31
```

Use it only as an A/B control for the same degraded March data state.

## 5. Artifact Inspection Commands

### 5.1 Show the latest backtest JSON files

```powershell
Get-ChildItem reports/backtests/backtest_*.json | Sort-Object LastWriteTime | Select-Object -Last 5 Name, LastWriteTime
```

### 5.2 Inspect the latest report metrics quickly

```powershell
python -X utf8 -c "import glob, json, pathlib; p=sorted(glob.glob('reports/backtests/backtest_*.json'), key=lambda x: pathlib.Path(x).stat().st_mtime)[-1]; d=json.loads(pathlib.Path(p).read_text(encoding='utf-8')); print('file:', pathlib.Path(p).name); print('run_id:', d.get('run_id')); print('period:', d.get('metadata',{}).get('start_date'), '->', d.get('metadata',{}).get('end_date')); print('symbols:', d.get('metadata',{}).get('symbols')); print('total_pnl:', d.get('metrics',{}).get('total_pnl')); print('roi_pct:', d.get('metrics',{}).get('roi_pct')); print('total_trades:', d.get('metrics',{}).get('total_trades')); print('bar_count:', d.get('pipeline',{}).get('bar_count'))"
```

### 5.3 Check whether the latest run is degraded by missing symbols

```powershell
$symbols=@('1000PEPEUSDT','BNBUSDT','BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT'); foreach($s in $symbols){ Write-Host ($s + ': ' + (Test-Path ("data/processed/$s/5m/2024-03_enriched.parquet"))) }
```

Interpretation today:

- `SOLUSDT` and `XRPUSDT` will fail this check
- that is the evidence that a March run is not a full clean six-symbol replay

## 6. Commands That Must Not Be Treated As Valid Current Benchmarks

### 6.1 Mar-Jun / Q2 side B benchmark command

Do not treat this as valid **until** the processed coverage blocker is fixed:

```powershell
python scripts/diagnostics/run_single_backtest.py --side B --start 2024-03-01 --end 2024-06-30
```

Why not:

- existing forensics already proved a Mar-Jun-labeled run can degrade to March-only execution when Apr-Jun parquet is absent

### 6.2 Any full-universe claim without coverage validation

Do not claim “canonical current side B” from any new run unless all six symbols have required parquet for the requested window.

## 7. Q2 / Apr-Jun Readiness Commands

Before any Q2 benchmark, first validate coverage using the command already established in:

- `reports/processed_data_coverage_audit_q2_2024.md`
- `reports/q2_processed_backfill_runbook_uk.md`

Validation command:

```powershell
$symbols=@('1000PEPEUSDT','BNBUSDT','BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT'); $months=@('2024-04','2024-05','2024-06'); $rows=foreach($s in $symbols){ foreach($m in $months){ [pscustomobject]@{symbol=$s; month=$m; exists=Test-Path ("data/processed/$s/5m/${m}_enriched.parquet") } } }; $rows | Format-Table -AutoSize; $missing=$rows | Where-Object { -not $_.exists }; if($missing){ Write-Host ''; Write-Host 'MISSING FILES:'; $missing | Format-Table -AutoSize; exit 1 } else { Write-Host ''; Write-Host 'OK: required Q2 enriched coverage is complete.' }
```

Only after that passes should a Q2 benchmark command be treated as valid.

## 8. Minimal Baseline Verdict

Today’s minimal reproducible baseline is:

- March 2024 side B via `run_single_backtest.py`

Today’s canonical-clean Q2 baseline status is:

- blocked by processed coverage gaps