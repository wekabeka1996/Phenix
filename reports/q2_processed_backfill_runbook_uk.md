# Runbook: Q2 2024 Processed Backfill for Aurora Side B

## 1. Мета

Підготувати відсутні 5m enriched parquet для clean Apr-Jun або Q2 run без змін коду і без запуску бектесту.

Цільове покриття:

- 2024-04
- 2024-05
- 2024-06

Цільові symbols:

- 1000PEPEUSDT
- BNBUSDT
- BTCUSDT
- ETHUSDT
- SOLUSDT
- XRPUSDT

DOGEUSDT не потрібен для canonical side B run.

## 2. Prerequisites

У репо вже є working pipeline, але зараз бракує raw inputs за Apr-Jun.

Перед запуском команд підготуйте standard Binance monthly ZIP або CSV files для кожного symbol-month.

Мінімально потрібні inputs для кожного symbol і місяця:

- SYMBOL-5m-YYYY-MM.zip
- SYMBOL-aggTrades-YYYY-MM.zip

Опційно:

- SYMBOL-bookTicker-YYYY-MM.zip

Без aggTrades pipeline не зможе побудувати final YYYY-MM_enriched.parquet.

## 3. Recommended Manual Path

Preferred current repo entrypoint:

- scripts/data/build_monthly_parquet.py

Чому саме він:

- вже оркеструє conversion + enrichment
- підтримує --symbols
- пише саме ті outputs, які далі читає BacktestEngine

## 4. Directory Preparation

Створіть окремий staging directory і покладіть туди тільки Apr-Jun ZIP files для шести required symbols.

Command:

New-Item -ItemType Directory -Force data\q2_2024_input | Out-Null

Після цього вручну скопіюйте в data\q2_2024_input тільки потрібні Apr-Jun raw ZIP files.

## 5. Generate Missing Processed Parquet

Основна команда:

python scripts/data/build_monthly_parquet.py --data-dir data/q2_2024_input --processed-dir data/processed --symbols 1000PEPEUSDT BNBUSDT BTCUSDT ETHUSDT SOLUSDT XRPUSDT --no-delete-zips --no-delete-raw

Очікувана поведінка:

- script знайде Apr-Jun ZIP files у flat input directory
- сконвертує raw monthly inputs у processed raw parquet
- запустить enrichment
- збереже final files у data/processed/{SYMBOL}/5m/YYYY-MM_enriched.parquet

## 6. Expected Output Locations

Після успішного завершення ви маєте побачити такі files:

- data/processed/1000PEPEUSDT/5m/2024-04_enriched.parquet
- data/processed/1000PEPEUSDT/5m/2024-05_enriched.parquet
- data/processed/1000PEPEUSDT/5m/2024-06_enriched.parquet
- data/processed/BNBUSDT/5m/2024-04_enriched.parquet
- data/processed/BNBUSDT/5m/2024-05_enriched.parquet
- data/processed/BNBUSDT/5m/2024-06_enriched.parquet
- data/processed/BTCUSDT/5m/2024-04_enriched.parquet
- data/processed/BTCUSDT/5m/2024-05_enriched.parquet
- data/processed/BTCUSDT/5m/2024-06_enriched.parquet
- data/processed/ETHUSDT/5m/2024-04_enriched.parquet
- data/processed/ETHUSDT/5m/2024-05_enriched.parquet
- data/processed/ETHUSDT/5m/2024-06_enriched.parquet
- data/processed/SOLUSDT/5m/2024-04_enriched.parquet
- data/processed/SOLUSDT/5m/2024-05_enriched.parquet
- data/processed/SOLUSDT/5m/2024-06_enriched.parquet
- data/processed/XRPUSDT/5m/2024-04_enriched.parquet
- data/processed/XRPUSDT/5m/2024-05_enriched.parquet
- data/processed/XRPUSDT/5m/2024-06_enriched.parquet

## 7. Validation After Generation

Run this exact validation command:

$symbols=@('1000PEPEUSDT','BNBUSDT','BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT'); $months=@('2024-04','2024-05','2024-06'); $rows=foreach($s in $symbols){ foreach($m in $months){ [pscustomobject]@{symbol=$s; month=$m; exists=Test-Path ("data/processed/$s/5m/${m}_enriched.parquet") } } }; $rows | Format-Table -AutoSize; $missing=$rows | Where-Object { -not $_.exists }; if($missing){ Write-Host ''; Write-Host 'MISSING FILES:'; $missing | Format-Table -AutoSize; exit 1 } else { Write-Host ''; Write-Host 'OK: required Q2 enriched coverage is complete.' }

## 8. Optional Input Inventory Check Before Generation

If you want to verify that staging ZIP files are really there before running the pipeline:

Get-ChildItem data\q2_2024_input -File | Sort-Object Name | Select-Object Name, Length

## 9. What To Send Back After You Finish

Після завершення надішліть назад:

1. Повний stdout від build_monthly_parquet.py
2. Повний stdout від validation command
3. Якщо були failures, список missing symbol-month pairs
4. Якщо script пропустив months, відповідні warning lines зі stdout

## 10. Fallback Path If Your Inputs Are In data/raw Recursive Layout

Якщо у вас уже є recursive raw layout замість flat ZIP staging dir, fallback command:

python scripts/data/prepare_backtest_data.py --source data/raw --target data/processed --max-date 2024-06

Це fallback only.

Для контрольованого Q2-only symbol subset preferred path залишається build_monthly_parquet.py з окремим staging directory.