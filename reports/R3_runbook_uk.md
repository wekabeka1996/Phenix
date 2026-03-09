# R3 Runbook — B3 (patched3): Cumulative та August-only
<!-- Backtest Ops Engineer | Aurora | Дата: 2026-03-05 -->

---

## Зміст

1. [Контекст і мета](#1-контекст-і-мета)
2. [Передумови](#2-передумови)
3. [Валідація конфігу B3](#3-валідація-конфігу-b3)
4. [Запуск R3 Cumulative (B3)](#4-запуск-r3-cumulative-b3)
5. [Запуск R3 August-only (B3)](#5-запуск-r3-august-only-b3)
6. [Де зберігаються результати](#6-де-зберігаються-результати)
7. [Пост-запускний чекліст](#7-пост-запускний-чекліст)
8. [Watchlist: BNBUSDT × MEAN_REVERSION](#8-watchlist-bnbusdt--mean_reversion)
9. [Шаблон повідомлення для ревʼю](#9-шаблон-повідомлення-для-ревʼю)
10. [Усунення несправностей](#10-усунення-несправностей)

---

## 1. Контекст і мета

### 1.1 Прийнятий baseline: B3 (patched3)

Config: `config/aurora/` (SMA 48/192)

| Патч | Параметр | Значення |
|---|---|---|
| patched2 | `decision.regime_threshold_multipliers.TREND_UP` | 1.50 |
| patched2 | `ETHUSDT.allowed_regimes` | без TREND_UP |
| patched2 | `BNBUSDT.allowed_regimes` | без TREND_UP |
| patched3 | `BNBUSDT.allowed_regimes` | без TREND_DOWN (нова зміна) |
| patched2 | `BTCUSDT.regime_sizing.HIGH_VOLATILITY` | 0.50 |

### 1.2 Результати R2 (підтверджений бекграунд)

| | A (baseline) | B3 (patched3) | Delta |
|---|---|---|---|
| total_pnl | -631.74 | **-171.37** | +460.37 |
| max_drawdown | 66.52% | **42.91%** | -23.61pp |
| sharpe | -1.2311 | -0.0778 | +1.15 |

### 1.3 Мета R3

- Валідувати стабільність B3 за межами R2 (Серпень 2023)
- Відстежити: `BNBUSDT × MEAN_REVERSION` (B3: -69.31 USDT, 16 угод — потрібен моніторинг)

### 1.4 Два варіанти запуску

| Варіант | Вікно | Команда | Примітка |
|---|---|---|---|
| **R3 Cumulative** | 2023-06-01..2023-08-31 | `--side B --rung 3` | Rung 3 вже визначено в runner |
| **R3 August-only** | 2023-08-01..2023-08-31 | `--side B --start 2023-08-01 --end 2023-08-31` | Ізольований серпень |

> **Рекомендація:** запустити обидва послідовно. Cumulative дає ladder continuity;
> August-only ізолює generalization на нових даних.

---

## 2. Передумови

### 2.1 Термінал

```bat
:: Відкрий НОВИЙ термінал (cmd або PowerShell) — не той де щось вже запущено
cd C:\Users\wekab\Music\Phenix
.venv\Scripts\activate
python -V
:: Очікується: Python 3.11.x або 3.12.x
```

### 2.2 Критичні правила

| Правило | Причина |
|---|---|
| **Один процес = один прогін** | 2 виклики `run_backtest_simulation()` в одному процесі → state leakage → 0 угод у 2-му |
| **НЕ використовуй `\| head`, `\| tail`, `\| more`** | Pipe обриває stdout → JSON неповний або 0 байт |
| **Завжди `> file.txt 2>&1`** | Stderr без цього втрачається |
| **Дочекайся `Exit code: 0`** | До цього JSON-звіт не записано |
| **Cumulative і Aug-only — окремі вікна, послідовно** | Конфлікт WAL / lock-файлів при паралельному запуску |

### 2.3 Перевірка parquet-даних

```bat
python -X utf8 -c "
from pathlib import Path
syms=['BTCUSDT','ETHUSDT','BNBUSDT','DOGEUSDT','1000PEPEUSDT']
months=['2023-06','2023-07','2023-08']
print(f'  {chr(32)*18}', '  '.join(months))
for s in syms:
    base=Path(f'data/processed/{s}/5m')
    row=f'  {s:<18}'
    for ym in months:
        p=base/f'{ym}_enriched.parquet'
        row+=f'  {\"OK   \" if p.exists() else \"MISS \"}'
    print(row)
"
```

Всі 5 символів × 3 місяці мають бути `OK`.

### 2.4 Вихідна директорія

```bat
mkdir reports\backtests
```

---

## 3. Валідація конфігу B3

Виконай **один раз** перед будь-яким запуском:

```bat
python -X utf8 -c "
import yaml
p='config/aurora/strategies/aurora.yaml'
r='config/aurora/regime.yaml'
a=yaml.safe_load(open(p,encoding='utf-8'))['aurora']
g=yaml.safe_load(open(r,encoding='utf-8'))
sma_s=g['models']['sma_trend']['sma_short_period']
sma_l=g['models']['sma_trend']['sma_long_period']
rtm=a['decision']['regime_threshold_multipliers']
bnb_ar=a['assets']['BNBUSDT']['allowed_regimes']
eth_ar=a['assets']['ETHUSDT']['allowed_regimes']
btc_hv=a['assets']['BTCUSDT']['regime_sizing']['HIGH_VOLATILITY']
ok=True
def chk(label,val,cond,expect):
    global ok
    s='OK' if cond else 'FAIL'
    if not cond: ok=False
    print(f'  [{s}] {label}: {val!r}  (expect {expect})')
chk('SMA short',sma_s,sma_s==48,'48')
chk('SMA long',sma_l,sma_l==192,'192')
chk('TREND_UP mult',rtm.get('TREND_UP'),rtm.get('TREND_UP')==1.5,'1.50')
chk('ETH no TREND_UP','TREND_UP' not in eth_ar,'TREND_UP' not in eth_ar,'absent')
chk('BNB no TREND_UP','TREND_UP' not in bnb_ar,'TREND_UP' not in bnb_ar,'absent')
chk('BNB no TREND_DOWN','TREND_DOWN' not in bnb_ar,'TREND_DOWN' not in bnb_ar,'absent')
chk('BNB allowed_regimes',sorted(bnb_ar),set(bnb_ar)=={'LOW_VOLATILITY','FLAT_NORMAL','MEAN_REVERSION'},'[LOW_VOL,FLAT_NORMAL,MR]')
chk('BTC HIGH_VOL sizing',btc_hv,btc_hv==0.50,'0.50')
print()
print('RESULT:','ALL CHECKS PASSED' if ok else '*** SOME CHECKS FAILED — STOP, do not run backtest ***')
"
```

**Очікуваний вивід:**
```
  [OK] SMA short: 48  (expect 48)
  [OK] SMA long: 192  (expect 192)
  [OK] TREND_UP mult: 1.5  (expect 1.50)
  [OK] ETH no TREND_UP: True  (expect absent)
  [OK] BNB no TREND_UP: True  (expect absent)
  [OK] BNB no TREND_DOWN: True  (expect absent)
  [OK] BNB allowed_regimes: [...]  (expect [LOW_VOL,FLAT_NORMAL,MR])
  [OK] BTC HIGH_VOL sizing: 0.5  (expect 0.50)

RESULT: ALL CHECKS PASSED
```

Якщо будь-який `[FAIL]` — **СТОП**. Перевір `config/aurora/strategies/aurora.yaml` рядок ~673.

---

## 4. Запуск R3 Cumulative (B3)

> **Вікно:** 2023-06-01 → 2023-08-31 | **Config:** `config/aurora/` (B3)
> **Rung 3** вже визначено у runner: `--rung 3` автоматично підставляє ці дати.

**Відкрий НОВИЙ PowerShell:**

```powershell
cd C:\Users\wekab\Music\Phenix
.venv\Scripts\activate

python -X utf8 scripts\diagnostics\run_single_backtest.py --side B --rung 3 > reports\backtests\R3_cum_B3_stdout.txt 2>&1; echo "Exit code: $LASTEXITCODE"
```

**Лог:** `reports\backtests\R3_cum_B3_stdout.txt`

**Перевірка що запустився** (в іншому вікні, через ~30 сек):

```bat
python -X utf8 -c "
from pathlib import Path
p=Path('reports/backtests/R3_cum_B3_stdout.txt')
print('Розмір:', p.stat().st_size, 'байт') if p.exists() else print('ФАЙЛ НЕ ЗНАЙДЕНО')
"
```

---

## 5. Запуск R3 August-only (B3)

> **Вікно:** 2023-08-01 → 2023-08-31 | **Config:** `config/aurora/` (B3)
> Немає предефінованого rung — використовуй `--start/--end`.
> **Запускай ТІЛЬКИ після завершення Cumulative (exit code 0).**

**Відкрий НОВИЙ PowerShell:**

```powershell
cd C:\Users\wekab\Music\Phenix
.venv\Scripts\activate

python -X utf8 scripts\diagnostics\run_single_backtest.py --side B --start 2023-08-01 --end 2023-08-31 > reports\backtests\R3_aug_B3_stdout.txt 2>&1; echo "Exit code: $LASTEXITCODE"
```

**Лог:** `reports\backtests\R3_aug_B3_stdout.txt`

---

## 6. Де зберігаються результати

| Артефакт | Шлях | Примітка |
|---|---|---|
| JSON-звіт (Cumulative) | `reports/backtests/backtest_<run_id_cum>.json` | run_id = timestamp старту |
| JSON-звіт (Aug-only) | `reports/backtests/backtest_<run_id_aug>.json` | |
| stdout Cumulative | `reports/backtests/R3_cum_B3_stdout.txt` | |
| stdout Aug-only | `reports/backtests/R3_aug_B3_stdout.txt` | |
| Логи домену | `logs/aurora_core.log` | перезаписується при кожному запуску |
| Ордер-лог JSONL | `logs/backtests/order_log_<run_id>.jsonl` | per-run, не перезаписується |

**Знайти свіжий JSON після завершення:**

```bat
python -X utf8 -c "
from pathlib import Path
import time
d=Path('reports/backtests')
files=sorted([f for f in d.glob('backtest_*.json')],key=lambda x:x.stat().st_mtime,reverse=True)[:4]
for f in files:
    mt=time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(f.stat().st_mtime))
    print(mt, f'{f.stat().st_size:>10}', f.name)
"
```

---

## 7. Пост-запускний чекліст

Виконай окремо для кожного прогону після `Exit code: 0`.

### 7.1 Підтвердити що JSON не порожній

```bat
python -X utf8 -c "
from pathlib import Path
import time
d=Path('reports/backtests')
recent=sorted(d.glob('backtest_*.json'),key=lambda f:f.stat().st_mtime,reverse=True)[:3]
for f in recent:
    sz=f.stat().st_size
    mt=time.strftime('%H:%M:%S',time.localtime(f.stat().st_mtime))
    status='OK' if sz>500_000 else ('WARN: малий (<500KB)' if sz>0 else 'FAIL: 0 байт')
    print(f'{mt}  {sz:>10} bytes  {status}  {f.name}')
"
```

Розмір має бути **>500 000 байт** (типово 2–5 MB для 3-місячного вікна).

### 7.2 Витягти ключові метрики (замін RUN_ID)

```bat
python -X utf8 -c "
import json, sys
from pathlib import Path

RUN_ID = 'ЗАМІН_НА_RUN_ID'
p = Path(f'reports/backtests/backtest_{RUN_ID}.json')
if not p.exists():
    print('FAIL: файл не знайдено'); sys.exit(1)

def sf(v):
    if v is None: return 0.0
    try: return float(v)
    except:
        try: return complex(str(v)).real
        except: return 0.0

rep  = json.loads(p.read_text(encoding='utf-8'))
m    = rep.get('metrics', {})
meta = rep.get('metadata', {})
pipe = rep.get('pipeline', {})

print('=== METRICS ===')
print(f'  period         : {str(meta.get(\"start_date\",\"?\"))[:10]} -> {str(meta.get(\"end_date\",\"?\"))[:10]}')
print(f'  total_pnl      : {sf(m.get(\"total_pnl\")):.2f} USDT')
print(f'  roi_pct        : {sf(m.get(\"roi_pct\")):.2f}%')
print(f'  max_drawdown   : {sf(m.get(\"max_drawdown\"))*100:.2f}%')
print(f'  total_trades   : {m.get(\"total_trades\")}')
print(f'  win_rate       : {sf(m.get(\"win_rate\"))*100:.2f}%')
print(f'  sharpe_ratio   : {sf(m.get(\"sharpe_ratio\")):.4f}')
print(f'  calmar_ratio   : {sf(m.get(\"calmar_ratio\")):.4f}')
print(f'  end_balance    : {sf(m.get(\"end_balance\")):.2f} USDT')
print(f'  bar_count      : {pipe.get(\"bar_count\",\"?\")}')
"
```

### 7.3 PnL по символах + BNBUSDT per-regime

```bat
python -X utf8 -c "
import json
from pathlib import Path
from collections import defaultdict

RUN_ID = 'ЗАМІН_НА_RUN_ID'
p = Path(f'reports/backtests/backtest_{RUN_ID}.json')
rep = json.loads(p.read_text(encoding='utf-8'))
trades = rep.get('trades', [])

def sf(v):
    try: return float(v)
    except:
        try: return complex(str(v)).real
        except: return 0.0

# PnL per symbol
sym = defaultdict(lambda: {'pnl':0.0,'n':0})
for t in trades:
    s=t.get('symbol','?')
    sym[s]['pnl']+=sf(t.get('pnl_usdt_net',0))
    sym[s]['n']+=1
print('=== PnL PER SYMBOL ===')
for s,d in sorted(sym.items(),key=lambda x:x[1]['pnl']):
    ev=d['pnl']/d['n'] if d['n'] else 0
    print(f'  {s:<18} pnl={d[\"pnl\"]:>9.2f}  n={d[\"n\"]:>4}  ev/t={ev:>7.2f}')

# BNBUSDT per-regime
print()
print('=== BNBUSDT PER-REGIME ===')
bnb = defaultdict(lambda: {'pnl':0.0,'n':0})
for t in trades:
    if t.get('symbol')!='BNBUSDT': continue
    r=t.get('market_regime','?')
    bnb[r]['pnl']+=sf(t.get('pnl_usdt_net',0))
    bnb[r]['n']+=1
for r,d in sorted(bnb.items(),key=lambda x:x[1]['pnl']):
    ev=d['pnl']/d['n'] if d['n'] else 0
    td_mark=' << ПЕРЕВІР' if r in ('TREND_DOWN','TREND_UP') and d['n']>0 else ''
    mr_mark=' << WATCHLIST' if r=='MEAN_REVERSION' else ''
    print(f'  {r:<20} pnl={d[\"pnl\"]:>8.2f}  n={d[\"n\"]:>4}  ev/t={ev:>7.2f}{td_mark}{mr_mark}')

# TREND_DOWN guard
td=bnb.get('TREND_DOWN',{'n':0,'pnl':0.0})
print()
if td['n']==0:
    print('  [OK] BNB TREND_DOWN = 0 угод (патч активний)')
else:
    print(f'  [FAIL] BNB TREND_DOWN = {td[\"n\"]} угод! Патч не спрацював.')
"
```

---

## 8. Watchlist: BNBUSDT × MEAN_REVERSION

**R2 сигнал:** B3 дав -69.31 USDT (n=16, ev/t=-4.33) на BNB×MR — у A baseline це був майже 0.

Після кожного прогону виконуй повний payoff-аналіз:

```bat
python -X utf8 -c "
import json
from pathlib import Path

RUN_ID = 'ЗАМІН_НА_RUN_ID'
p = Path(f'reports/backtests/backtest_{RUN_ID}.json')
rep = json.loads(p.read_text(encoding='utf-8'))
trades = rep.get('trades', [])

def sf(v):
    try: return float(v)
    except:
        try: return complex(str(v)).real
        except: return 0.0

# Ізолюємо BNB × MEAN_REVERSION
mr = [sf(t.get('pnl_usdt_net',0)) for t in trades
      if t.get('symbol')=='BNBUSDT' and t.get('market_regime')=='MEAN_REVERSION']

if not mr:
    print('BNB × MEAN_REVERSION: 0 угод (немає даних)')
else:
    wins  = [p for p in mr if p > 0]
    losses= [p for p in mr if p < 0]
    avg_w = sum(wins)/len(wins)   if wins   else 0
    avg_l = sum(losses)/len(losses) if losses else 0
    payoff= abs(avg_w/avg_l) if avg_l else float('inf')
    ev    = sum(mr)/len(mr)
    wr    = len(wins)/len(mr)*100

    print(f'BNB × MEAN_REVERSION  (n={len(mr)})')
    print(f'  total_pnl  : {sum(mr):>9.2f} USDT')
    print(f'  ev/t       : {ev:>9.2f} USDT')
    print(f'  win_rate   : {wr:>9.1f}%  ({len(wins)}W / {len(losses)}L)')
    print(f'  avg_win    : {avg_w:>9.2f} USDT')
    print(f'  avg_loss   : {avg_l:>9.2f} USDT')
    print(f'  payoff     : {payoff:>9.2f}  (avg_win / |avg_loss|)')
    print()
    if ev < -2.0:
        print('  [WATCHLIST] EV/t < -2.0 — кандидат для блокування в patched4')
    elif ev < 0:
        print('  [MONITOR]   EV/t негативний але > -2.0 — стежити далі')
    else:
        print('  [OK]        EV/t >= 0 — BNB MR нейтральний або позитивний')
"
```

**Критерій ескалації:** якщо після R3 `ev/t < -2.0` і `n >= 10` → додати MEAN_REVERSION до блокування в patched4.

---

## 9. Шаблон повідомлення для ревʼю

Заповни після обох прогонів:

```
=== R3 B3 (patched3) — РЕЗУЛЬТАТИ ===

Версія конфігу : B3 (patched3, config/aurora/, SMA 48/192)

--- R3 CUMULATIVE (2023-06-01..2023-08-31) ---
  run_id         : backtest_YYYYMMDD_HHMMSS
  total_pnl      : ___.___ USDT
  max_drawdown   : ___.___ %
  total_trades   : ___
  win_rate       : ___.___ %
  sharpe_ratio   : ___._____
  end_balance    : ___.___ USDT
  bar_count      : ______
  Exit code      : _

--- R3 AUGUST-ONLY (2023-08-01..2023-08-31) ---
  run_id         : backtest_YYYYMMDD_HHMMSS
  total_pnl      : ___.___ USDT
  max_drawdown   : ___.___ %
  total_trades   : ___
  win_rate       : ___.___ %
  sharpe_ratio   : ___._____
  end_balance    : ___.___ USDT
  bar_count      : ______
  Exit code      : _

--- PnL per symbol (обидва прогони) ---
  BTCUSDT  cum=_______  aug=_______
  ETHUSDT  cum=_______  aug=_______
  BNBUSDT  cum=_______  aug=_______

--- BNBUSDT × MEAN_REVERSION watchlist ---
  Cumulative : n=___  ev/t=_____  payoff=_____  total=_______
  Aug-only   : n=___  ev/t=_____  payoff=_____  total=_______

--- BNBUSDT TREND_DOWN guard ---
  Cumulative : n=___  (очікується 0)
  Aug-only   : n=___  (очікується 0)

JSON paths:
  cum : reports/backtests/backtest_YYYYMMDD_HHMMSS.json
  aug : reports/backtests/backtest_YYYYMMDD_HHMMSS.json
```

---

## 10. Усунення несправностей

| Симптом | Причина | Дія |
|---|---|---|
| `Exit code: 1` одразу | YAML помилка / Pydantic error | Перевір `[FAIL]` у validation (п.3); читай `R3_*_stdout.txt` |
| JSON < 500 KB або 0 байт | Backtest впав до збереження | Читай кінець stdout-файлу (п.нижче) |
| `0 trades` у JSON | State leakage — два виклики в одному процесі | Використовуй `run_single_backtest.py`, не `run_backtest_ladder.py` |
| `WARMUP_NOT_FULL_READY` > 95% барів | State leakage з попереднього прогону | Відкрий НОВИЙ термінал, запусти заново |
| BNB TREND_DOWN > 0 угод | patched3 не застосовано або config не той | Перевір `--side B`, перечитай validation (п.3) |
| stdout-файл читається неправильно (крякозябри) | PowerShell пише UTF-16-LE | Нормально — читай через `.decode('utf-16-le')` |
| `calmar_ratio` = complex string | DD > 100% (blown) | Рахуй `complex(s).real`; стратегія blown — перевір BNB/BTC sizing |

**Читання кінця stdout при помилці (без pipe):**

```bat
python -X utf8 -c "
from pathlib import Path
p=Path('reports/backtests/R3_cum_B3_stdout.txt')
sz=p.stat().st_size
with open(p,'rb') as f:
    f.seek(max(0,sz-8192)); raw=f.read()
for enc in ['utf-16-le','utf-8','cp1252']:
    try:
        lines=raw.decode(enc,errors='replace').splitlines()
        errs=[l for l in lines if any(k in l for k in ['ERROR','Traceback','Exception','FAIL','exit'])]
        print(f'[{enc}] last 20 lines:')
        for l in lines[-20:]: print(' ',l)
        if errs:
            print('--- ERROR LINES ---')
            for l in errs[-10:]: print(' ',l)
        break
    except: pass
"
```

---

## Довідка: архітектура конфігу

```
scripts/diagnostics/run_single_backtest.py   ← точка входу
  --side B  → config/aurora/                 ← B3 (patched3)
  --side A  → config/aurora_baseline/        ← A baseline (SMA 24/96, незмінний)
  --rung 3  → start=2023-06-01, end=2023-08-31  (pre-defined у LADDER_RUNGS)
  --start/--end → кастомне вікно (для Aug-only)

config/overlays/
  r3_window_cumulative.yaml     ← reference-документ для R3 cumulative датів
  r3_window_august_only.yaml    ← reference-документ для Aug-only датів
  patched3_bnb_block_trend_down.yaml  ← diff + revert-інструкції для patched3
```

*Підготовлено: Backtest Ops Engineer | Phenix/Aurora B3 patched3 → R3*
