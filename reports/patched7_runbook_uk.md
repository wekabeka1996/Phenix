# Runbook: patched7 proposal-only

## 1. Статус

patched7 у поточному стані не є config-only.

Перед manual-run спочатку має бути реалізований мінімальний patch із [reports/patched7_minimal_patch_proposal.md](reports/patched7_minimal_patch_proposal.md).

## 2. Які файли підготовані

- [reports/patched7_minimal_patch_proposal.md](reports/patched7_minimal_patch_proposal.md)
- [config/overlays/patched7_march_only.yaml](config/overlays/patched7_march_only.yaml)
- [config/overlays/patched7_q1_cumulative.yaml](config/overlays/patched7_q1_cumulative.yaml)

## 3. Порядок після імплементації patch

1. Внести мінімальні зміни з proposal.
2. Оновити ETH config новим `entry_phase_guard`.
3. Прогнати коротку loader/schema smoke-перевірку.
4. Запустити March-only confirm-run.
5. Запустити Q1 cumulative confirm-run.

## 4. Коротка smoke-перевірка конфігу

```powershell
cd C:\Users\wekab\Music\Phenix
.venv\Scripts\Activate.ps1
python -X utf8 -c "from apps.reference.config_loader import ConfigLoader; cfg = ConfigLoader().load_config(); eth = cfg.strategies.aurora.assets['ETHUSDT']; g = getattr(eth, 'entry_phase_guard', None); print('entry_phase_guard exists:', g is not None); print(g)"
```

Очікування:
- loader не падає
- `entry_phase_guard exists: True`

## 5. March-only run

```powershell
python scripts/diagnostics/run_single_backtest.py --side B --start 2024-03-01 --end 2024-03-31 2>&1 | Tee-Object reports/backtests/March2024_patched7_stdout.txt
```

Підказка:
- window reference: [config/overlays/patched7_march_only.yaml](config/overlays/patched7_march_only.yaml)

## 6. Q1 cumulative run

```powershell
python scripts/diagnostics/run_single_backtest.py --side B --start 2024-01-01 --end 2024-03-31 2>&1 | Tee-Object reports/backtests/Q1_patched7_stdout.txt
```

Підказка:
- window reference: [config/overlays/patched7_q1_cumulative.yaml](config/overlays/patched7_q1_cumulative.yaml)

## 7. Який результат вважати успіхом

- March-only має покращитись відносно patched6 clean run
- Q1 cumulative не повинен зламати Jan+Feb carry
- перевіряється саме ETHUSDT x TREND_DOWN LONG anti-exhaustion veto, без супутніх змін у TP/SL або regime logic