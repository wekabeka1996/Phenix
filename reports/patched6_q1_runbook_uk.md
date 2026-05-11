# Runbook: patched6 Q1 - DOGE blocked from active universe
**Baseline:** patched5 + patched6 DOGE block | **Дата:** 2026-03-12
**Ціль:** Підтвердити, що Q1 baseline без DOGEUSDT зберігає ETH/BNB внесок і прибирає registry gap

---

## 1. Передумови

```powershell
cd C:\Users\wekab\Music\Phenix
.venv\Scripts\Activate.ps1
New-Item -ItemType Directory -Force -Path reports/backtests
```

Правила:
- не запускати більше одного прогону одночасно
- не редагувати config між валідацією і запуском
- stdout кожного прогону зберігати окремо

---

## 2. Що саме є patched6

patched6 не змінює жодних runtime-параметрів, TP/SL, regime rules або sizing.

Єдина логічна зміна:
- DOGEUSDT прибрано з [config/aurora/strategies.yaml](config/aurora/strategies.yaml)

Причина:
- active universe виводиться з keys у `strategies_registry.assignments`
- варіант `DOGEUSDT: []` не прибирає символ із `symbols_to_track`
- тому для реального block потрібне саме видалення ключа DOGEUSDT

---

## 3. Передстартова валідація конфігу

### 3.1 Loader smoke: DOGE реально відсутній з active universe

```powershell
python -X utf8 -c "from apps.reference.config_loader import ConfigLoader; cfg = ConfigLoader().load_config(); a = cfg.strategies_registry.assignments; print('DOGE in assignments:', 'DOGEUSDT' in a); print('tracked symbols:', cfg.trading.symbols_to_track); print('DOGE in symbols_to_track:', 'DOGEUSDT' in cfg.trading.symbols_to_track)"
```

Очікуваний вивід:

```text
DOGE in assignments: False
tracked symbols: ['1000PEPEUSDT', 'BNBUSDT', 'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT']
DOGE in symbols_to_track: False
```

Якщо `DOGE in assignments` або `DOGE in symbols_to_track` дорівнює `True`:
- зупинити процес
- не запускати backtest

### 3.2 SSOT contract smoke

```powershell
python -m pytest -q tests/config/test_sizing_margin_first_ssot.py
```

Очікуваний результат:

```text
2 passed
```

---

## 4. Команда ручного Q1 confirm-run

```powershell
python scripts/diagnostics/run_single_backtest.py --side B --start 2024-01-01 --end 2024-03-31 2>&1 | Tee-Object reports/backtests/Q1_patched6_stdout.txt
```

Після завершення:

```powershell
echo "Exit code: $LASTEXITCODE"
```

---

## 5. Де чекати результати

```powershell
Get-ChildItem reports/backtests/backtest_*.json | Sort-Object LastWriteTime | Select-Object -Last 3
```

Основні артефакти:
- stdout: `reports/backtests/Q1_patched6_stdout.txt`
- json report: `reports/backtests/backtest_<run_id>.json`

---

## 6. Швидкий пост-run розбір

```powershell
python -X utf8 -c "import json, pathlib, glob, collections; f = sorted(glob.glob('reports/backtests/backtest_*.json'), key=lambda p: pathlib.Path(p).stat().st_mtime)[-1]; data = json.loads(pathlib.Path(f).read_text(encoding='utf-8')); trades = [t for t in data.get('trades', []) if t.get('close_reason')]; by_sym = collections.defaultdict(lambda: {'n': 0, 'pnl': 0.0}); [by_sym[t.get('symbol','?')].update(n=by_sym[t.get('symbol','?')]['n'] + 1, pnl=by_sym[t.get('symbol','?')]['pnl'] + float(t.get('pnl_usdt_net', 0) or 0)) for t in trades]; print('file:', pathlib.Path(f).name); print('total_pnl:', data.get('metrics', {}).get('total_pnl')); print('roi_pct:', data.get('metrics', {}).get('roi_pct')); print('DOGE trades:', by_sym['DOGEUSDT']['n']); print('DOGE pnl:', round(by_sym['DOGEUSDT']['pnl'], 2)); print('ETH trades/pnl:', by_sym['ETHUSDT']['n'], round(by_sym['ETHUSDT']['pnl'], 2)); print('BNB trades/pnl:', by_sym['BNBUSDT']['n'], round(by_sym['BNBUSDT']['pnl'], 2))"
```

Очікування для patched6 confirm:
- DOGE trades = 0
- DOGE pnl = 0.0
- Q1 CUM має наблизитись до ETH+BNB компоненти, тобто близько +89.77 USDT

---

## 7. Що не змінювати в цьому циклі

- не чіпати ETH TREND_DOWN
- не чіпати ETH MR
- не чіпати BNB MR
- не міняти TP/SL
- не міняти regime detector

---

*Runbook підготовлено: 2026-03-12 | Aurora/Phenix patched6 DOGE block*
