# Runbook: patched5 Q4 Research — Oct / Nov / Dec / Q4 cumulative
**Baseline:** patched5 | **Мета:** статистична валідація ETH MR, BNB MR, ETH TREND_DOWN на Q4 2023
**Дата підготовки:** 2026-03-09

---

## 1. Передумови

```powershell
cd C:\Users\wekab\Music\Phenix
python -V
.venv\Scripts\Activate.ps1
New-Item -ItemType Directory -Force -Path reports/backtests
```

## 2. Валідація конфігу (перед КОЖНИМ прогоном)

```powershell
python -X utf8 -c "import yaml; s=yaml.safe_load(open('config/aurora/strategies/aurora.yaml',encoding='utf-8').read()); r=yaml.safe_load(open('config/aurora/regime.yaml',encoding='utf-8').read()); a=s['aurora']['assets']; d=s['aurora']['decision']; print('ETH:', a['ETHUSDT']['allowed_regimes']); print('BNB:', a['BNBUSDT']['allowed_regimes']); print('BTC allowed_regimes:', a['BTCUSDT']['allowed_regimes']); print('PEPE allowed_regimes:', a['1000PEPEUSDT']['allowed_regimes']); print('BTC in tracking:', 'BTCUSDT' in d['symbols_to_track']); print('SMA:', r['models']['sma_trend']['sma_short_period'], '/', r['models']['sma_trend']['sma_long_period'])"
```

**Очікуваний вивід:**
```
ETH: ['TREND_DOWN', 'FLAT_LOW', 'FLAT_NORMAL', 'MEAN_REVERSION']
BNB: ['FLAT_NORMAL', 'MEAN_REVERSION']
BTC allowed_regimes: []
PEPE allowed_regimes: []
BTC in tracking: False
SMA: 48 / 192
```

Якщо відрізняється — **зупинити**, не запускати.

---

## 3. Команди запуску (по одному — чекати завершення кожного)

### Прогін 1 — October-only
```powershell
python scripts/diagnostics/run_single_backtest.py --side B --start 2023-10-01 --end 2023-10-31 2>&1 | Tee-Object reports/backtests/OCT_patched5_stdout.txt
echo "Exit: $LASTEXITCODE"
```

### Прогін 2 — November-only
```powershell
python scripts/diagnostics/run_single_backtest.py --side B --start 2023-11-01 --end 2023-11-30 2>&1 | Tee-Object reports/backtests/NOV_patched5_stdout.txt
echo "Exit: $LASTEXITCODE"
```

### Прогін 3 — December-only
```powershell
python scripts/diagnostics/run_single_backtest.py --side B --start 2023-12-01 --end 2023-12-31 2>&1 | Tee-Object reports/backtests/DEC_patched5_stdout.txt
echo "Exit: $LASTEXITCODE"
```

### Прогін 4 — Q4 cumulative
```powershell
python scripts/diagnostics/run_single_backtest.py --side B --start 2023-10-01 --end 2023-12-31 2>&1 | Tee-Object reports/backtests/Q4_patched5_stdout.txt
echo "Exit: $LASTEXITCODE"
```

### Прогін 5 — Extended CUM Jun-Dec (опціонально, після 1-4)
```powershell
python scripts/diagnostics/run_single_backtest.py --side B --start 2023-06-01 --end 2023-12-31 2>&1 | Tee-Object reports/backtests/EXTCUM_patched5_stdout.txt
echo "Exit: $LASTEXITCODE"
```

---

## 4. Пост-прогін аналіз (запускати після кожного прогону)

```powershell
python -X utf8 -c "
import json, pathlib, glob, collections, statistics, datetime

files = sorted(glob.glob('reports/backtests/backtest_*.json'), key=lambda f: pathlib.Path(f).stat().st_mtime)
data = json.loads(pathlib.Path(files[-1]).read_text(encoding='utf-8'))
trades = data.get('trades', [])
m = data.get('metrics', {})
closed = [t for t in trades if t.get('close_reason')]
open_pos = [t for t in trades if not t.get('close_reason')]

print('file:', pathlib.Path(files[-1]).name)
print('total_pnl:', round(m.get('total_pnl',0), 4))
print('roi_pct:', round(m.get('roi_pct',0), 4))
print('max_drawdown_pct:', round(m.get('max_drawdown',0)*100, 2))
print('total_trades:', m.get('total_trades'))
print('closed_trades:', len(closed))
print('win_rate:', round(m.get('win_rate',0), 4))
print('sharpe_ratio:', round(m.get('sharpe_ratio',0) if m.get('sharpe_ratio') else 0, 4))
print('end_balance:', round(m.get('end_balance',0), 4))
print('open_at_end:', len(open_pos))

syms = collections.defaultdict(float)
sym_n = collections.defaultdict(int)
sym_wins = collections.defaultdict(int)
sym_sl = collections.defaultdict(int)
sym_tp = collections.defaultdict(int)
for t in closed:
    s = t.get('symbol','?')
    p = t.get('pnl_usdt_net',0) or 0
    cr = t.get('close_reason','?')
    syms[s]+=p; sym_n[s]+=1
    if p>0: sym_wins[s]+=1
    if cr=='SL': sym_sl[s]+=1
    if cr=='TP': sym_tp[s]+=1
print()
print('pnl_by_symbol:')
for s in sorted(syms, key=lambda x: syms[x]):
    wr=sym_wins[s]/sym_n[s] if sym_n[s] else 0
    ev=syms[s]/sym_n[s] if sym_n[s] else 0
    print(f'  {s}: n={sym_n[s]} pnl={syms[s]:.2f} ev={ev:.2f} WR={wr:.2%} SL={sym_sl[s]} TP={sym_tp[s]}')

# Validity checks
print()
print('=== VALIDITY ===')
print('BTC trades:', sym_n.get('BTCUSDT',0), '<- MUST BE 0')
print('PEPE trades:', sym_n.get('1000PEPEUSDT',0), '<- MUST BE 0')

reg_data = collections.defaultdict(lambda: {'n':0,'pnl':0.0,'sl':0,'tp':0,'wins':0,'losses':0})
for t in closed:
    k=(t.get('symbol','?'), t.get('market_regime','?'))
    p=t.get('pnl_usdt_net',0) or 0
    cr=t.get('close_reason','?')
    reg_data[k]['n']+=1; reg_data[k]['pnl']+=p
    if p>0: reg_data[k]['wins']+=1
    else: reg_data[k]['losses']+=1
    if cr=='SL': reg_data[k]['sl']+=1
    if cr=='TP': reg_data[k]['tp']+=1
eth_lv=reg_data[('ETHUSDT','LOW_VOLATILITY')]
bnb_lv=reg_data[('BNBUSDT','LOW_VOLATILITY')]
print('ETH LOW_VOL trades:', eth_lv['n'], '<- MUST BE 0')
print('BNB LOW_VOL trades:', bnb_lv['n'], '<- MUST BE 0')

print()
print('=== PER-REGIME DETAIL ===')
for sym in ['ETHUSDT','BNBUSDT']:
    for reg in ['TREND_DOWN','MEAN_REVERSION','FLAT_NORMAL','FLAT_LOW']:
        v=reg_data[(sym,reg)]
        if v['n']==0: continue
        ev=v['pnl']/v['n'] if v['n'] else 0
        wr=v['wins']/v['n'] if v['n'] else 0
        avg_win=(sum(t.get('pnl_usdt_net',0) for t in closed if t.get('symbol')==sym and t.get('market_regime')==reg and (t.get('pnl_usdt_net',0) or 0)>0) / max(v['wins'],1)) if v['wins'] else 0
        avg_loss=(sum(t.get('pnl_usdt_net',0) for t in closed if t.get('symbol')==sym and t.get('market_regime')==reg and (t.get('pnl_usdt_net',0) or 0)<=0) / max(v['losses'],1)) if v['losses'] else 0
        payoff=abs(avg_win/avg_loss) if avg_loss else 999
        print(f'  {sym} x {reg}: n={v[\"n\"]} pnl={v[\"pnl\"]:.2f} ev={ev:.2f} WR={wr:.2%} SL={v[\"sl\"]} TP={v[\"tp\"]} avg_win={avg_win:.2f} avg_loss={avg_loss:.2f} payoff={payoff:.3f}')

print()
print('=== HOLDING TIMES ===')
for sym in ['ETHUSDT','BNBUSDT']:
    holds=[]
    for t in closed:
        if t.get('symbol')!=sym: continue
        ets=(t.get('entry') or {}).get('ts_ms') or t.get('entry_ts_ms')
        xts=(t.get('exit') or {}).get('ts_ms') or t.get('exit_ts_ms')
        if ets and xts: holds.append((xts-ets)/60000)
    if holds:
        print(f'  {sym}: n={len(holds)} avg={statistics.mean(holds):.0f}m median={statistics.median(holds):.0f}m')
"
```

---

## 5. Шаблон результатів (один на прогін)

Копіювати в `patched5_q4_research.md` після кожного прогону:

```
=== [PERIOD] patched5 ===
run_id        :
period        :
total_pnl     :        USDT
roi_pct       :        %
max_drawdown  :        %
total_trades  :
closed_trades :
win_rate      :
sharpe_ratio  :
end_balance   :        USDT

VALIDITY: BTC=0 PEPE=0 ETH_LOW_VOL=0 BNB_LOW_VOL=0 → [ VALID / INVALID ]

pnl_by_symbol:
  ETH: n=  pnl=
  BNB: n=  pnl=

ETH TREND_DOWN:  n=  pnl=  ev=  WR=  SL=  TP=  payoff=
ETH MR:          n=  pnl=  ev=  WR=  SL=  TP=  payoff=
BNB MR:          n=  pnl=  ev=  WR=  SL=  TP=  payoff=
```

---

*Runbook: 2026-03-09 | patched5 Q4 Research*
