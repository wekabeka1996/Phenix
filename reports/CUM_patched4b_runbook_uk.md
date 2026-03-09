# Runbook: CUM patched4b — Cumulative Jun-Sep ETH+BNB baseline
**Baseline:** patched4b (BTC blocked + PEPE blocked + SMA 48/192) | **Дата:** 2026-03-07
**Ціль:** Підтвердити, що Sep покращення (+60 USDT) тримається на повному Jun-Sep вікні

---

## 1. Передумови (Preconditions)

```powershell
cd C:\Users\wekab\Music\Phenix
python -V
.venv\Scripts\Activate.ps1
New-Item -ItemType Directory -Force -Path reports/backtests
```

**Правила:**
- Тільки **один прогін за раз** (state leakage при двох викликах)
- **Не використовувати `| head`**

---

## 2. Валідація конфігу перед запуском

```powershell
python -X utf8 -c "import yaml; s=yaml.safe_load(open('config/aurora/strategies/aurora.yaml',encoding='utf-8').read()); r=yaml.safe_load(open('config/aurora/regime.yaml',encoding='utf-8').read()); a=s['aurora']['assets']; d=s['aurora']['decision']; print('BTC in symbols_to_track:', 'BTCUSDT' in d['symbols_to_track']); print('PEPE in symbols_to_track:', '1000PEPEUSDT' in d['symbols_to_track']); print('BTCUSDT.allowed_regimes:', a['BTCUSDT']['allowed_regimes']); print('PEPE.allowed_regimes:', a['1000PEPEUSDT']['allowed_regimes']); print('ETHUSDT.allowed_regimes:', a['ETHUSDT']['allowed_regimes']); print('BNBUSDT.allowed_regimes:', a['BNBUSDT']['allowed_regimes']); print('SMA short/long:', r['models']['sma_trend']['sma_short_period'], '/', r['models']['sma_trend']['sma_long_period'])"
```

**Очікуваний вивід:**
```
BTC in symbols_to_track: False
PEPE in symbols_to_track: False
BTCUSDT.allowed_regimes: []
PEPE.allowed_regimes: []
ETHUSDT.allowed_regimes: ['TREND_DOWN', 'FLAT_LOW', 'FLAT_NORMAL', 'LOW_VOLATILITY', 'MEAN_REVERSION']
BNBUSDT.allowed_regimes: ['LOW_VOLATILITY', 'FLAT_NORMAL', 'MEAN_REVERSION']
SMA short/long: 48 / 192
```

Якщо `BTC in symbols_to_track: True` або `BTCUSDT.allowed_regimes` не порожній — **зупинити**.

---

## 3. Команда запуску — cumulative Jun-Sep patched4b

```powershell
python scripts/diagnostics/run_single_backtest.py --side B --start 2023-06-01 --end 2023-09-30 2>&1 | Tee-Object reports/backtests/CUM_patched4b_stdout.txt
```

```powershell
echo "Exit code: $LASTEXITCODE"
```
Очікується: `Exit code: 0`

---

## 4. Де шукати результати

| Артефакт | Шлях |
|---|---|
| JSON-звіт | `reports/backtests/backtest_<run_id>.json` |
| Stdout/stderr | `reports/backtests/CUM_patched4b_stdout.txt` |
| Aurora лог | `logs/backtest/aurora_core.log` |

```powershell
Get-ChildItem reports/backtests/backtest_*.json | Sort-Object LastWriteTime | Select-Object -Last 1
```

---

## 5. Що перевірити після завершення

```powershell
python -X utf8 -c "
import json, pathlib, glob, collections
files = sorted(glob.glob('reports/backtests/backtest_*.json'), key=lambda f: pathlib.Path(f).stat().st_mtime)
data = json.loads(pathlib.Path(files[-1]).read_text(encoding='utf-8'))
trades = data.get('trades', [])
m = data.get('metrics', {})
closed = [t for t in trades if t.get('close_reason')]
open_pos = [t for t in trades if not t.get('close_reason')]

print('file:', pathlib.Path(files[-1]).name)
print('total_pnl:', m.get('total_pnl'))
print('roi_pct:', m.get('roi_pct'))
print('max_drawdown_pct:', round(m.get('max_drawdown',0)*100, 2))
print('total_trades (metrics):', m.get('total_trades'))
print('closed_trades (log):', len(closed))
print('win_rate:', m.get('win_rate'))
print('sharpe_ratio:', m.get('sharpe_ratio'))
print('end_balance:', m.get('end_balance'))
print('open_at_end:', len(open_pos))

syms = collections.defaultdict(float)
sym_n = collections.defaultdict(int)
for t in closed:
    s = t.get('symbol','?')
    syms[s] += t.get('pnl_usdt_net', 0) or 0
    sym_n[s] += 1

print()
print('pnl_by_symbol:')
for s in sorted(syms, key=lambda x: syms[x]):
    print(f'  {s}: n={sym_n[s]} pnl={syms[s]:.2f}')
print('BTCUSDT trades:', sym_n.get('BTCUSDT', 0), '<- має бути 0')
print('1000PEPEUSDT trades:', sym_n.get('1000PEPEUSDT', 0), '<- має бути 0')

print()
print('ETH per-regime:')
eth_reg = collections.defaultdict(lambda: {'n':0,'pnl':0.0,'sl':0,'tp':0,'wins':0})
for t in closed:
    if t.get('symbol') != 'ETHUSDT': continue
    reg = t.get('market_regime','?')
    p = t.get('pnl_usdt_net',0) or 0
    cr = t.get('close_reason','?')
    eth_reg[reg]['n'] += 1
    eth_reg[reg]['pnl'] += p
    if p > 0: eth_reg[reg]['wins'] += 1
    if cr=='SL': eth_reg[reg]['sl'] += 1
    if cr=='TP': eth_reg[reg]['tp'] += 1
for reg, v in sorted(eth_reg.items(), key=lambda x: x[1]['pnl']):
    ev = v['pnl']/v['n']
    wr = v['wins']/v['n'] if v['n'] else 0
    print(f'  ETH x {reg}: n={v[\"n\"]} pnl={v[\"pnl\"]:.2f} ev={ev:.2f} WR={wr:.2%} SL={v[\"sl\"]} TP={v[\"tp\"]}')

print()
print('BNB per-regime:')
bnb_reg = collections.defaultdict(lambda: {'n':0,'pnl':0.0,'sl':0,'tp':0,'wins':0})
for t in closed:
    if t.get('symbol') != 'BNBUSDT': continue
    reg = t.get('market_regime','?')
    p = t.get('pnl_usdt_net',0) or 0
    cr = t.get('close_reason','?')
    bnb_reg[reg]['n'] += 1
    bnb_reg[reg]['pnl'] += p
    if p > 0: bnb_reg[reg]['wins'] += 1
    if cr=='SL': bnb_reg[reg]['sl'] += 1
    if cr=='TP': bnb_reg[reg]['tp'] += 1
for reg, v in sorted(bnb_reg.items(), key=lambda x: x[1]['pnl']):
    ev = v['pnl']/v['n']
    wr = v['wins']/v['n'] if v['n'] else 0
    print(f'  BNB x {reg}: n={v[\"n\"]} pnl={v[\"pnl\"]:.2f} ev={ev:.2f} WR={wr:.2%} SL={v[\"sl\"]} TP={v[\"tp\"]}')
"
```

---

## 6. Шаблон звіту після прогону

```
=== CUM patched4b (Jun-Sep) РЕЗУЛЬТАТ ===
run_id          :
period          : 2023-06-01 → 2023-09-30
side            : B (patched4b)
total_pnl       :          USDT
roi_pct         :          %
max_drawdown    :          %
total_trades    :
closed_trades   :
win_rate        :
sharpe_ratio    :
end_balance     :          USDT
open_at_end     :

pnl_by_symbol:
  ETHUSDT   :          USDT  (n=)
  BNBUSDT   :          USDT  (n=)
  BTCUSDT   : 0 trades  ← підтвердження блоку
  1000PEPEUSDT: 0 trades ← підтвердження блоку

ETH per-regime:
  TREND_DOWN   : n=  pnl=
  LOW_VOL      : n=  pnl=
  MR           : n=  pnl=
  FLAT_NORMAL  : n=  pnl=

BNB per-regime:
  MEAN_REVERSION : n=  pnl=
  LOW_VOL        : n=  pnl=

exit code: 0
```

---

## 7. Порівняльна таблиця (заповнити після прогону)

| Метрика | patched3 R4_CUM | patched4b Sep-only | **patched4b CUM** |
|---|---|---|---|
| total_pnl | −262.64 | +60.02 | ? |
| ETH pnl | +16.24 | +40.33 | ? |
| BNB pnl | −66.24 | +21.50 | ? |
| BTC pnl | −212.64 | 0 (blocked) | 0 (blocked) |
| max_drawdown | ~90% | 17.3% | ? |
| sharpe | негативний | +0.46 | ? |

---

## 8. Файли overlay

| Файл | Призначення |
|---|---|
| `config/overlays/patched4b_cumulative_jun_sep.yaml` | Window документація |
| `config/overlays/patched4b_block_btc.yaml` | BTC block documentation |
| `config/aurora/strategies/aurora.yaml` | Реальний конфіг (patched4b applied) |

---

*Runbook підготовлено: 2026-03-07 | Aurora/Phenix patched4b cumulative Jun-Sep*
