# Aurora Validation Guide - February 2024

## Overview
This guide explains how to validate the optimized Aurora parameters on out-of-sample data from February 2024.

## ⚠️ Data Volume Warning
The raw data for February 2024 is extremely large, specifically the `bookTicker` files required for liquidity features:
- **BTCUSDT**: ~83 GB
- **ETHUSDT**: ~87 GB
- **SOLUSDT**: ~36 GB
- **XRPUSDT**: ~10 GB
- **DOGEUSDT**: ~8 GB
- **Total**: ~224 GB

Processing this data to create the "golden" 60s dataset takes significant time (hours) and disk I/O.

## Prerequisites
- Python 3.10+
- Pandas, Numpy
- At least 32GB RAM recommended
- SSD with >300GB free space

## Step 1: Build Golden Dataset (Raw -> 60s)
This step aggregates 1m Klines, AggTrades, and BookTicker into a single 60s resolution CSV.

```bash
# Run in parallel for all symbols (Recommended)
# This will launch 5 background processes. Monitor CPU/Disk usage.
python3 apps/research/aurora_optuna/build_golden_dataset_feb.py --symbol BTCUSDT &
python3 apps/research/aurora_optuna/build_golden_dataset_feb.py --symbol ETHUSDT &
python3 apps/research/aurora_optuna/build_golden_dataset_feb.py --symbol SOLUSDT &
python3 apps/research/aurora_optuna/build_golden_dataset_feb.py --symbol XRPUSDT &
python3 apps/research/aurora_optuna/build_golden_dataset_feb.py --symbol DOGEUSDT &
```

Output files will be created in `apps/research/momentum_backtest/data/`:
- `BTCUSDT-60s-golden-2024-02.csv`
- ...

## Step 2: Build Features
Once the golden datasets are ready (check file timestamps/sizes), generate the Aurora features.

```bash
# Run the parallel helper script
./apps/research/aurora_optuna/run_build_features_parallel.sh
```

## Step 3: Run Validation
Run the validation script to backtest the optimal configurations on the new data.

```bash
python3 apps/research/aurora_optuna/validate_feb_2024.py --month 02
```

## Sanity Check (January 2024)
We have verified the configuration and validation logic using January 2024 data (in-sample).

**Command:**
```bash
python3 apps/research/aurora_optuna/validate_feb_2024.py --month 01
```

**Results:**
- **SOLUSDT**: 100% Match ($201.60) ✅
- **ETHUSDT**: 99.1% Match ($104.90 vs $105.87) ✅
- **DOGEUSDT**: 100% Match ($85.89) ✅
- **XRPUSDT**: 100% Match ($28.96) ✅

This confirms that the `aurora_optimal_production_v1.yaml` configuration correctly reproduces the optimization results.
