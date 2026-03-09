# Runbook: patched5 — ETH+BNB без LOW_VOLATILITY
**Baseline:** patched4b + patched5 LOW_VOL block | **Дата:** 2026-03-08
**Ціль:** Усунути головний структурний збиток (LOW_VOL -486 USDT в CUM), підтвердити ETH TREND_DOWN і BNB MR

---

## 1. Передумови (Preconditions)

```powershell
cd C:\Users\wekab\Music\Phenix
python -V
.venv\Scripts\Activate.ps1
New-Item -ItemType Directory -Force -Path reports/backtests
```

**Правила:** один прогін за раз, не використовувати `| head`

---

## 2. Валідація конфігу перед запуском

```powershell
python -X utf8 -c "import yaml; s=yaml.safe_load(open('config/aurora/strategies/aurora.yaml',encoding='utf-8').read()); r=yaml.safe_load(open('config/aurora/regime.yaml',encoding='utf-8').read()); a=s['aurora']['assets']; d=s['aurora']['decision']; print('ETH allowed_regimes:', a['ETHUSDT']['allowed_regimes']); print('BNB allowed_regimes:', a['BNBUSDT']['allowed_regimes']); print('BTC allowed_regimes:', a['BTCUSDT']['allowed_regimes']); print('PEPE allowed_regimes:', a['1000PEPEUSDT']['allowed_regimes']); print('BTC in tracking:', 'BTCUSDT' in d['symbols_to_track']); print('SMA short/long:', r['models']['sma_trend']['sma_short_period'], '/', r['models']['sma_trend']['sma_long_period'])"
```

**Очікуваний вивід:**
```
ETH allowed_regimes: ['TREND_DOWN', 'FLAT_LOW', 'FLAT_NORMAL', 'MEAN_REVERSION']
BNB allowed_regimes: ['FLAT_NORMAL', 'MEAN_REVERSION']
BTC allowed_regimes: []
PEPE allowed_regimes: []
BTC in tracking: False
SMA short/long: 48 / 192
```

Якщо `LOW_VOLATILITY` присутній у ETH або BNB — **зупинити**, не запускати.

---

## 3. Команди запуску

### 3.1 September-only patched5 (перший запуск)

```powershell
python scripts/diagnostics/run_single_backtest.py --side B --start 2023-09-01 --end 2023-09-30 2>&1 | Tee-Object reports/backtests/SEP_patched5_stdout.txt
```

```powershell
echo "Exit code: $LASTEXITCODE"
```

### 3.2 Cumulative Jun-Sep patched5 (другий запуск — після завершення першого)

```powershell
python scripts/diagnostics/run_single_backtest.py --side B --start 2023-06-01 --end 2023-09-30 2>&1 | Tee-Object reports/backtests/CUM_patched5_stdout.txt
```

```powershell
echo "Exit code: $LASTEXITCODE"
```

---

## 4. Де шукати результати

| Артефакт | Шлях |
|---|---|
| JSON-звіт | `reports/backtests/backtest_<run_id>.json` |
| Sep stdout | `reports/backtests/SEP_patched5_stdout.txt` |
| CUM stdout | `reports/backtests/CUM_patched5_stdout.txt` |

```powershell
Get-ChildItem reports/backtests/backtest_*.json | Sort-Object LastWriteTime | Select-Object -Last 2
```

---

## 5. Що перевірити після завершення

```powershell
python -X utf8 -c "
import json, pathlib, glob, collections
files = sorted(glob.glob('reports/backtests/backtest_*.json'), key=lambda f: pathlib.Path(f).stat().st_mtime)

for fpath in files[-2:]:
    data = json.loads(pathlib.Path(fpath).read_text(encoding='utf-8'))
    trades = data.get('trades', [])
    m = data.get('metrics', {})
    closed = [t for t in trades if t.get('close_reason')]
    pipeline = data.get('pipeline') or data.get('report', {}).get('pipeline', {}) or {}

    print('=' * 55)
    print('file:', pathlib.Path(fpath).name)
    print('total_pnl:', m.get('total_pnl'))
    print('roi_pct:', m.get('roi_pct'))
    print('max_drawdown_pct:', round(m.get('max_drawdown',0)*100, 2))
    print('total_trades (metrics):', m.get('total_trades'))
    print('closed_trades (log):', len(closed))
    print('win_rate:', m.get('win_rate'))
    print('sharpe_ratio:', m.get('sharpe_ratio'))
    print('end_balance:', m.get('end_balance'))

    syms = collections.defaultdict(float)
    sym_n = collections.defaultdict(int)
    for t in closed:
        s = t.get('symbol','?')
        syms[s] += t.get('pnl_usdt_net', 0) or 0
        sym_n[s] += 1
    print('pnl_by_symbol:')
    for s in sorted(syms, key=lambda x: syms[x]):
        print(f'  {s}: n={sym_n[s]} pnl={syms[s]:.2f}')
    print('BTCUSDT trades:', sym_n.get('BTCUSDT', 0), '<- має бути 0')
    print('1000PEPEUSDT trades:', sym_n.get('1000PEPEUSDT', 0), '<- має бути 0')

    reg_data = collections.defaultdict(lambda: {'n':0,'pnl':0.0})
    for t in closed:
        k = (t.get('symbol','?'), t.get('market_regime','?'))
        reg_data[k]['n'] += 1
        reg_data[k]['pnl'] += t.get('pnl_usdt_net',0) or 0
    eth_low = reg_data.get(('ETHUSDT','LOW_VOLATILITY'), {'n':0,'pnl':0.0})
    bnb_low = reg_data.get(('BNBUSDT','LOW_VOLATILITY'), {'n':0,'pnl':0.0})
    eth_td  = reg_data.get(('ETHUSDT','TREND_DOWN'), {'n':0,'pnl':0.0})
    bnb_mr  = reg_data.get(('BNBUSDT','MEAN_REVERSION'), {'n':0,'pnl':0.0})
    print('ETH LOW_VOLATILITY: n=' + str(eth_low['n']) + ' <- має бути 0')
    print('BNB LOW_VOLATILITY: n=' + str(bnb_low['n']) + ' <- має бути 0')
    print('ETH TREND_DOWN: n=' + str(eth_td['n']) + ' pnl=' + f\"{eth_td['pnl']:.2f}\")
    print('BNB MR: n=' + str(bnb_mr['n']) + ' pnl=' + f\"{bnb_mr['pnl']:.2f}\")
"
```

---

## 6. Шаблон звіту після прогонів

```
=== SEP patched5 (Sep-only) ===
run_id          :
period          : 2023-09-01 → 2023-09-30
total_pnl       :          USDT
roi_pct         :          %
max_drawdown    :          %
total_trades    :
win_rate        :
sharpe_ratio    :
end_balance     :          USDT

pnl_by_symbol:
  ETHUSDT   :          USDT (n=)
  BNBUSDT   :          USDT (n=)
  BTCUSDT   : 0 trades ← підтвердження
  PEPE      : 0 trades ← підтвердження

ETH LOW_VOL  : 0 trades ← підтвердження
BNB LOW_VOL  : 0 trades ← підтвердження
ETH TREND_DOWN : n=  pnl=
BNB MR         : n=  pnl=

=== CUM patched5 (Jun-Sep) ===
run_id          :
period          : 2023-06-01 → 2023-09-30
total_pnl       :          USDT  [patched4b CUM було -403.70]
roi_pct         :          %
max_drawdown    :          %
total_trades    :
win_rate        :
sharpe_ratio    :
end_balance     :          USDT

pnl_by_symbol:
  ETHUSDT   :          USDT (n=)
  BNBUSDT   :          USDT (n=)
  BTCUSDT   : 0 trades ← підтвердження
  PEPE      : 0 trades ← підтвердження

ETH LOW_VOL  : 0 trades ← підтвердження
BNB LOW_VOL  : 0 trades ← підтвердження
ETH TREND_DOWN : n=  pnl=
BNB MR         : n=  pnl=

exit code (SEP): 0
exit code (CUM): 0
```

---

## 7. Патч-дельта (patched5 vs patched4b)

| Параметр | patched4b | patched5 | Обґрунтування |
|---|---|---|---|
| `ETHUSDT.allowed_regimes` | `[..., LOW_VOLATILITY, ...]` | **без LOW_VOLATILITY** | CUM: n=29, -250.60 USDT, avg SL -28 USDT |
| `BNBUSDT.allowed_regimes` | `[LOW_VOLATILITY, ...]` | **без LOW_VOLATILITY** | CUM: n=67, -235.63 USDT |
| BTC, PEPE, SMA, TP/SL | без змін | без змін | успадковано з patched4b |

---

## 8. Очікувані результати (розрахунок)

| Метрика | patched4b CUM | patched5 CUM (прогноз) |
|---|---|---|
| total_pnl | −403.70 | ~+80 USDT |
| ETH pnl | −153.80 | ~+96 (−153 + 250.60 без LOW_VOL) |
| BNB pnl | −250.76 | ~−15 (−250 + 235.63 без LOW_VOL) |
| ETH TREND_DOWN | +143.45 | +143.45 (незмінний) |

---

*Runbook підготовлено: 2026-03-08 | Aurora/Phenix patched5 LOW_VOL block*
