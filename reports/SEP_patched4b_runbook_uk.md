# Runbook: SEP patched4b — ETH+BNB чистий baseline September
**Baseline:** patched4a_v2 + patched4b BTC block | **Дата:** 2026-03-07
**Ціль:** Ізольований Sep 2023 без BTC і PEPE — чистий сигнал ETH+BNB

---

## 1. Передумови (Preconditions)

```powershell
# 1. Корінь репозиторію
cd C:\Users\wekab\Music\Phenix

# 2. Python
python -V
# Очікується: Python 3.10+

# 3. venv
.venv\Scripts\Activate.ps1

# 4. Директорія результатів
New-Item -ItemType Directory -Force -Path reports/backtests
```

**Правила:**
- Тільки **один прогін за раз** (state leakage при двох викликах)
- **Не використовувати `| head`**

---

## 2. Валідація конфігу перед запуском

```powershell
python -X utf8 -c "import yaml; s=yaml.safe_load(open('config/aurora/strategies/aurora.yaml',encoding='utf-8').read()); r=yaml.safe_load(open('config/aurora/regime.yaml',encoding='utf-8').read()); a=s['aurora']['assets']; d=s['aurora']['decision']; print('BTC in symbols_to_track:', 'BTCUSDT' in d['symbols_to_track']); print('BTCUSDT.allowed_regimes:', a['BTCUSDT']['allowed_regimes']); print('ETHUSDT.allowed_regimes:', a['ETHUSDT']['allowed_regimes']); print('BNBUSDT.allowed_regimes:', a['BNBUSDT']['allowed_regimes']); print('SMA short/long:', r['models']['sma_trend']['sma_short_period'], '/', r['models']['sma_trend']['sma_long_period'])"
```

**Очікуваний вивід:**
```
BTC in symbols_to_track: False
BTCUSDT.allowed_regimes: []
ETHUSDT.allowed_regimes: ['TREND_DOWN', 'FLAT_LOW', 'FLAT_NORMAL', 'LOW_VOLATILITY', 'MEAN_REVERSION']
BNBUSDT.allowed_regimes: ['LOW_VOLATILITY', 'FLAT_NORMAL', 'MEAN_REVERSION']
SMA short/long: 48 / 192
```

Якщо `BTC in symbols_to_track: True` або `BTCUSDT.allowed_regimes` не порожній — **зупинити**, не запускати.

---

## 3. Команда запуску — September-only patched4b

```powershell
python scripts/diagnostics/run_single_backtest.py --side B --start 2023-09-01 --end 2023-09-30 2>&1 | Tee-Object reports/backtests/SEP_patched4b_stdout.txt
```

Перевірити exit code:
```powershell
echo "Exit code: $LASTEXITCODE"
```
Очікується: `Exit code: 0`

---

## 4. Де шукати результати

| Артефакт | Шлях |
|---|---|
| JSON-звіт | `reports/backtests/backtest_<run_id>.json` |
| Stdout/stderr | `reports/backtests/SEP_patched4b_stdout.txt` |
| Aurora лог | `logs/backtest/aurora_core.log` |

Знайти останній json:
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
print('pnl_by_symbol:')
for s in sorted(syms, key=lambda x: syms[x]):
    print(f'  {s}: n={sym_n[s]} pnl={syms[s]:.2f}')
print('BTCUSDT trades:', sym_n.get('BTCUSDT', 0), '<- має бути 0')
print('1000PEPEUSDT trades:', sym_n.get('1000PEPEUSDT', 0), '<- має бути 0')
"
```

**Критичні перевірки:**
- `BTCUSDT trades: 0` — якщо не 0, блок не спрацював
- `1000PEPEUSDT trades: 0` — має залишитись 0 з patched4a_v2
- `open_at_end: 0` — якщо є відкрита позиція, `total_pnl` може бути недостовірним

---

## 6. Шаблон звіту після прогону

```
=== SEP patched4b РЕЗУЛЬТАТ ===
run_id          :
period          : 2023-09-01 → 2023-09-30
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
  TREND_DOWN  : n=  pnl=
  LOW_VOL     : n=  pnl=
  MR          : n=  pnl=

BNB per-regime:
  MR          : n=  pnl=
  LOW_VOL     : n=  pnl=

exit code: 0
```

---

## 7. Порівняльна таблиця (заповнити після прогону)

| Метрика | patched4a_v2 Sep | **patched4b Sep** | Δ |
|---|---|---|---|
| total_pnl | −90.11 | ? | |
| BTC pnl | −86.79 | 0 (blocked) | |
| ETH pnl | +3.95 | ? | |
| BNB pnl | +3.87 | ? | |
| ETH+BNB | +7.82 | ? | |
| max_drawdown | 25.8% | ? | |
| win_rate | 51.3% | ? | |
| payoff | 0.802 | ? | |

---

## 8. Патч-дельта (patched4b vs patched4a_v2)

| Параметр | patched4a_v2 | patched4b | Обґрунтування |
|---|---|---|---|
| `BTCUSDT` в `symbols_to_track` | ✅ | **❌ видалено** | Sep: −86.79, 83% SL rate |
| `BTCUSDT.allowed_regimes` | `[TREND_UP, TREND_DOWN, ...]` | **`[]`** | реальний enforcement блок |
| ETH / BNB / SMA | без змін | без змін | |
| PEPE (з patched4a_v2) | `[]`, не в tracking | без змін | |

---

## 9. Файли overlay (документація змін)

| Файл | Призначення |
|---|---|
| `config/overlays/patched4b_sep_only.yaml` | Window документація (Sep 2023-09-01..09-30) |
| `config/overlays/patched4b_block_btc.yaml` | BEFORE/AFTER diff, BTC block, revert інструкції |
| `config/aurora/strategies/aurora.yaml` | **Реальний конфіг** (зміни застосовані inline) |

---

*Runbook підготовлено: 2026-03-07 | Aurora/Phenix patched4b Sep ETH+BNB baseline*
