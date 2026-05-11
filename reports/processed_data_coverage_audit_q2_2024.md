# Processed Data Coverage Audit for Q2 2024

## 0. Scope and Verdict

This audit covers only the current repository state.

Verdict:

- The blocker is real: processed 5m enriched coverage required for a valid Apr-Jun 2024 side B run is incomplete.
- For the canonical current patched baseline, the minimal clean universe is not the five-symbol shortlist from prior discussion. It is the six symbols present in strategies registry assignments.
- Missing processed coverage is not limited to April-June. Two symbols in the active registry universe, SOLUSDT and XRPUSDT, currently have no processed 5m enriched coverage at all.
- There is a working generation pipeline in the repo, but the repo currently lacks Apr-Jun raw inputs and also lacks Apr-Jun phase-1 processed inputs for all relevant symbols.

## 1. Coverage Audit: data/processed/{SYMBOL}/5m

Coverage was audited on disk for 5m enriched monthly parquet files.

Legend:

- Y = file exists
- N = file missing

| Symbol | Earliest available | Latest available | 2024-01 | 2024-02 | 2024-03 | 2024-04 | 2024-05 | 2024-06 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ETHUSDT | 2023-06 | 2024-03 | Y | Y | Y | N | N | N |
| BNBUSDT | 2023-06 | 2024-03 | Y | Y | Y | N | N | N |
| BTCUSDT | 2023-06 | 2024-03 | Y | Y | Y | N | N | N |
| 1000PEPEUSDT | 2023-06 | 2024-03 | Y | Y | Y | N | N | N |
| DOGEUSDT | 2023-06 | 2024-03 | Y | Y | Y | N | N | N |
| SOLUSDT | none | none | N | N | N | N | N | N |
| XRPUSDT | none | none | N | N | N | N | N | N |

### Missing-month diagnosis

For the current active patched baseline universe:

- ETHUSDT is missing 2024-04, 2024-05, 2024-06.
- BNBUSDT is missing 2024-04, 2024-05, 2024-06.
- BTCUSDT is missing 2024-04, 2024-05, 2024-06.
- 1000PEPEUSDT is missing 2024-04, 2024-05, 2024-06.
- SOLUSDT is missing all audited months including 2024-01 through 2024-06.
- XRPUSDT is missing all audited months including 2024-01 through 2024-06.

DOGEUSDT has Jan-Mar processed coverage, but it is not part of the canonical side B registry universe.

## 2. Active Universe Audit

### 2.1 Canonical active universe source of truth

Current SSOT for active symbols in backtest mode is strategies registry assignments.

Evidence:

- config/aurora/strategies.yaml defines strategies_registry.assignments.
- ConfigLoader derives trading.symbols_to_track from assignments keys.
- run_single_backtest.py side B loads config/aurora directly and does not apply a symbol lock or subset overlay.
- apps/reference/main.py uses config.trading.symbols_to_track as the backtest symbol list.

### 2.2 Registry-active symbols for current side B baseline

Current assignments keys in config/aurora/strategies.yaml:

- ETHUSDT
- SOLUSDT
- XRPUSDT
- BTCUSDT
- BNBUSDT
- 1000PEPEUSDT

### 2.3 Active versus blocked versus referenced

| Symbol | In strategies registry assignments | Trade-policy status in aurora assets | Referenced by loader/runtime | Conclusion for clean side B run |
| --- | --- | --- | --- | --- |
| ETHUSDT | Yes | Active | Yes | Required |
| BNBUSDT | Yes | Active | Yes | Required |
| BTCUSDT | Yes | Assigned but blocked by allowed_regimes: [] | Yes, and also used as anchor_symbol and macro anchor | Required |
| 1000PEPEUSDT | Yes | Assigned but blocked by enabled: false and allowed_regimes: [] | Yes | Required |
| SOLUSDT | Yes | Active | Yes | Required |
| XRPUSDT | Yes | Active | Yes | Required |
| DOGEUSDT | No | Asset block exists in aurora profile but not active in registry SSOT | No for canonical side B run | Not required |

### 2.4 Minimal required symbol list for the next clean Apr-Jun or Q2 run

For the current canonical side B baseline without config edits, the minimal required symbol list is:

- 1000PEPEUSDT
- BNBUSDT
- BTCUSDT
- ETHUSDT
- SOLUSDT
- XRPUSDT

Reason:

- The loader and backtest universe for side B are derived from registry assignment keys.
- BTCUSDT remains operationally required even if trade-policy blocked, because it is still assigned and is referenced by anchor logic.
- 1000PEPEUSDT remains operationally required even if trade-policy blocked, because it is still assigned and therefore still loaded.
- DOGEUSDT is not required because it was intentionally removed from assignments.

## 3. Raw and Phase-1 Input Audit for Apr-Jun 2024

The repo currently has no Apr-Jun 2024 source inputs for the required symbols.

Observed for 2024-04, 2024-05, 2024-06:

- No raw Binance ZIP or CSV inputs were found under data for ETHUSDT, BNBUSDT, BTCUSDT, 1000PEPEUSDT, SOLUSDT, or XRPUSDT.
- No phase-1 processed klines parquet was found for those months.
- No phase-1 processed aggTrades parquet was found for those months.
- No phase-1 processed bookTicker parquet was found for those months.

Operational implication:

- The repo already has the generation code.
- The immediate missing operational piece is the Apr-Jun raw market-data input set.

## 4. Backfill Pipeline Discovery

### 4.1 Real generator for enriched monthly parquet

Primary writer of final backtest inputs:

- backtest_engine/data_processing/enricher.py

What it does:

- Reads monthly processed klines parquet.
- Reads matching monthly processed aggTrades parquet.
- Optionally reads matching monthly processed bookTicker parquet.
- Writes final enriched output as data/processed/{symbol}/{timeframe}/YYYY-MM_enriched.parquet.

Important contract:

- Klines are required.
- aggTrades are required for enrichment.
- bookTicker is optional. If absent or malformed, enrichment continues without bookTicker fields.

### 4.2 Phase-1 converter for raw ZIP or CSV to monthly parquet

Primary converter module:

- backtest_engine/data_processing/data_converter.py

What it does:

- Converts raw Binance CSV or ZIP inputs into monthly parquet.
- Supports klines, aggTrades, bookTicker, fundingRate.
- Writes:
  - data/processed/{symbol}/klines/{timeframe}/YYYY-MM.parquet
  - data/processed/{symbol}/aggTrades/YYYY-MM.parquet
  - data/processed/{symbol}/bookTicker/YYYY-MM.parquet

### 4.3 Repo wrapper that orchestrates convert plus enrich

Preferred current repo wrapper for manual targeted generation:

- scripts/data/build_monthly_parquet.py

Why this is the best current manual path:

- It already imports the canonical DataConverter and Enricher modules.
- It performs ZIP scan, conversion, enrichment, and coverage reporting in one run.
- It supports symbol filtering with --symbols.
- It is designed specifically for monthly Binance ZIP inputs.

Inputs expected by this wrapper:

- A flat directory of Binance monthly ZIPs.
- Naming pattern:
  - SYMBOL-5m-YYYY-MM.zip for klines
  - SYMBOL-aggTrades-YYYY-MM.zip for aggTrades
  - SYMBOL-bookTicker-YYYY-MM.zip for bookTicker, optional

Limitations:

- It does not expose a direct month filter CLI flag.
- Therefore the clean operational pattern is to stage only the required Apr-Jun ZIPs in a dedicated input directory.

### 4.4 Secondary wrapper

Alternative wrapper:

- scripts/data/prepare_backtest_data.py

Role:

- Recursive scanner for data/raw style layouts.
- Converts and enriches, but does not support symbol filtering.

Assessment:

- Useful fallback when inputs are already organized recursively.
- Not the preferred minimal path for a controlled Q2-only symbol subset.

### 4.5 Non-generator tools that are not the answer to this blocker

- tools/parquet_pipeline/__main__.py is not the missing-data generator.
- It audits and analyzes already existing parquet data and writes research artifacts such as stress or regime-grid outputs.
- It does not create the canonical 5m YYYY-MM_enriched.parquet inputs required by BacktestEngine.

## 5. Minimal Required Backfill Scope

### 5.1 Minimal month range to generate now

Generate only:

- 2024-04
- 2024-05
- 2024-06

Reason:

- Jan-Mar already exist for ETHUSDT, BNBUSDT, BTCUSDT, and 1000PEPEUSDT.
- The current blocker proved that Apr-Jun are the missing months that invalidated the Mar-Jun run.
- The requested next research target is Apr-Jun or Q2.

### 5.2 Exact symbols to generate now

Generate Apr-Jun 2024 for:

- 1000PEPEUSDT
- BNBUSDT
- BTCUSDT
- ETHUSDT
- SOLUSDT
- XRPUSDT

Do not spend time on DOGEUSDT for the canonical side B run.

### 5.3 Exact operational requirement per symbol-month

To obtain YYYY-MM_enriched.parquet for a symbol-month, the pipeline minimally needs:

- SYMBOL-5m-YYYY-MM ZIP or CSV input
- SYMBOL-aggTrades-YYYY-MM ZIP or CSV input

Optional:

- SYMBOL-bookTicker-YYYY-MM ZIP or CSV input

If aggTrades is missing:

- the wrapper may still produce raw klines parquet,
- but the final enriched parquet will not be generated for that month.

## 6. Validation Before Backtest

### 6.1 Lightweight validation objective

Before any future backtest, validate that:

- all six required symbols exist under data/processed/{symbol}/5m
- all months 2024-04, 2024-05, 2024-06 exist as YYYY-MM_enriched.parquet
- no expected symbol-month pair is missing

### 6.2 Validation command

Use this PowerShell command after generation:

$symbols=@('1000PEPEUSDT','BNBUSDT','BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT'); $months=@('2024-04','2024-05','2024-06'); $rows=foreach($s in $symbols){ foreach($m in $months){ [pscustomobject]@{symbol=$s; month=$m; exists=Test-Path ("data/processed/$s/5m/${m}_enriched.parquet") } } }; $rows | Format-Table -AutoSize; $missing=$rows | Where-Object { -not $_.exists }; if($missing){ Write-Host ''; Write-Host 'MISSING FILES:'; $missing | Format-Table -AutoSize; exit 1 } else { Write-Host ''; Write-Host 'OK: required Q2 enriched coverage is complete.' }

## 7. Recommended Manual Generation Command

After placing only the required Apr-Jun Binance ZIPs into a clean flat staging directory, run:

python scripts/data/build_monthly_parquet.py --data-dir data/q2_2024_input --processed-dir data/processed --symbols 1000PEPEUSDT BNBUSDT BTCUSDT ETHUSDT SOLUSDT XRPUSDT --no-delete-zips --no-delete-raw

This is the preferred current repo path for manual targeted generation.