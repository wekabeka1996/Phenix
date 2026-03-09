# R4 Runbook — B3 (patched3): Cumulative та September-only
<!-- Backtest Ops Engineer | Aurora | Дата: 2026-03-06 -->

---

## Зміст

1. [Контекст і мета](#1-контекст-і-мета)
2. [Передумови](#2-передумови)
3. [Валідація конфігу B3](#3-валідація-конфігу-b3)
4. [Запуск R4 Cumulative (B3)](#4-запуск-r4-cumulative-b3)
5. [Запуск R4 September-only (B3)](#5-запуск-r4-september-only-b3)
6. [Де зберігаються результати](#6-де-зберігаються-результати)
7. [Пост-запускний чекліст](#7-пост-запускний-чекліст)
8. [Watchlist: рішення після R4](#8-watchlist-рішення-після-r4)
9. [Шаблон повідомлення для ревʼю](#9-шаблон-повідомлення-для-ревʼю)
10. [Усунення несправностей](#10-усунення-несправностей)

---

## 1. Контекст і мета

### 1.1 Поточний baseline: B3 (patched3) — без змін

Config: `config/aurora/` (SMA 48/192). **Нічого не змінювати.**

| Патч | Параметр | Значення |
|---|---|---|
| patched2 | `decision.regime_threshold_multipliers.TREND_UP` | 1.50 |
| patched2 | `ETHUSDT.allowed_regimes` | без TREND_UP |
| patched2 | `BNBUSDT.allowed_regimes` | без TREND_UP |
| patched3 | `BNBUSDT.allowed_regimes` | без TREND_DOWN |
| patched2 | `BTCUSDT.regime_sizing.HIGH_VOLATILITY` | 0.50 |

### 1.2 Ladder стан (факти)

| Вікно | total_pnl | DD | sharpe | end_balance |
|---|---|---|---|---|
| R2 B3 (Jun-Jul) | -171.37 | 42.91% | -0.0778 | 828.63 |
| R3 CUM (Jun-Aug) | -89.30 | 41.92% | **+0.0925** | 910.70 |
| R3 AUG-only | -50.40 | 25.79% | -0.1160 | 949.60 |

### 1.3 Watchlist — чому R4 без патчу

| Сигнал | Звідки | Деталі | Статус |
|---|---|---|---|
| **BTC серпень** | R3 AUG-only | BTC: -139.95 USDT (27 угод, ev/t ≈ -5.18) | Треба підтвердити у вересні |
| **BNB MR** | R3 CUM | CUM ev/t=-2.25 (n=27), AUG ev/t=+0.79 (n=7) | Нестабільний — треба вересень |

**Правило:** якщо вересень підтверджує обидва → patched4. Якщо ні → B3 стабільна, далі ladder.

### 1.4 Два варіанти запуску

| Варіант | Вікно | Команда |
|---|---|---|
| **R4 Cumulative** | 2023-06-01..2023-09-30 | `--side B --rung 4` |
| **R4 September-only** | 2023-09-01..2023-09-30 | `--side B --start 2023-09-01 --end 2023-09-30` |

---

## 2. Передумови

### 2.1 Термінал (PowerShell)

```powershell
# Відкрий НОВИЙ PowerShell — не той де щось вже запущено
cd C:\Users\wekab\Music\Phenix
.venv\Scripts\activate
python -V
# Очікується: Python 3.11.x або 3.12.x
```

### 2.2 Критичні правила

| Правило | Причина |
|---|---|
| **Один процес = один прогін** | 2 виклики в одному процесі → state leakage → 0 угод |
| **НЕ `\| head`, `\| tail`, `\| more`** | Pipe обриває stdout → неповний JSON |
| **Завжди `> file.txt 2>&1`** | Stderr без цього втрачається |
| **Дочекайся `Exit code: 0`** | До цього JSON-звіт не записано |
| **Cumulative і Sep-only — окремі вікна, послідовно** | Конфлікти WAL/lock |
| **НЕ `^` як line continuation** | Це cmd.exe, не PowerShell. Весь рядок одним рядком. |

### 2.3 Перевірка parquet-даних

```powershell
python -X utf8 -c "
from pathlib import Path
syms=['BTCUSDT','ETHUSDT','BNBUSDT','DOGEUSDT','1000PEPEUSDT']
months=['2023-06','2023-07','2023-08','2023-09']
for s in syms:
    base = Path(f'data/processed/{s}/5m')
    row = f'{s:<18}'
    for ym in months:
        p = base / f'{ym}_enriched.parquet'
        row += f'  {\"OK  \" if p.exists() else \"MISS\"}'
    print(row)
"
```

Всі 5 символів × 4 місяці мають бути `OK`.

### 2.4 Вихідна директорія

```powershell
mkdir -Force reports\backtests
```

---

## 3. Валідація конфігу B3

Виконай **один раз** перед будь-яким запуском:

```powershell
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
print('RESULT:','ALL CHECKS PASSED' if ok else '*** SOME CHECKS FAILED — STOP ***')
"
```

Якщо будь-який `[FAIL]` — **СТОП**.

---

## 4. Запуск R4 Cumulative (B3)

> **Вікно:** 2023-06-01 → 2023-09-30 | **Config:** `config/aurora/` (B3)
> `--rung 4` вже визначено в runner: `(4, 2023, 6, 2023, 9)`

**Відкрий НОВИЙ PowerShell:**

```powershell
cd C:\Users\wekab\Music\Phenix
.venv\Scripts\activate
python -X utf8 scripts\diagnostics\run_single_backtest.py --side B --rung 4 > reports\backtests\R4_cum_B3_stdout.txt 2>&1; echo "Exit code: $LASTEXITCODE"
```

**Лог:** `reports\backtests\R4_cum_B3_stdout.txt`

**Перевірка що запустився** (в іншому вікні, через ~30 сек):

```powershell
python -X utf8 -c "
from pathlib import Path
p=Path('reports/backtests/R4_cum_B3_stdout.txt')
print('Розмір:', p.stat().st_size, 'байт') if p.exists() else print('ФАЙЛ НЕ ЗНАЙДЕНО')
"
```

---

## 5. Запуск R4 September-only (B3)

> **Вікно:** 2023-09-01 → 2023-09-30 | **Config:** `config/aurora/` (B3)
> Немає predefined rung — використовуй `--start/--end`.
> **Запускай ТІЛЬКИ після завершення Cumulative (exit code 0).**

**Відкрий НОВИЙ PowerShell:**

```powershell
cd C:\Users\wekab\Music\Phenix
.venv\Scripts\activate
python -X utf8 scripts\diagnostics\run_single_backtest.py --side B --start 2023-09-01 --end 2023-09-30 > reports\backtests\R4_sep_B3_stdout.txt 2>&1; echo "Exit code: $LASTEXITCODE"
```

**Лог:** `reports\backtests\R4_sep_B3_stdout.txt`

---

## 6. Де зберігаються результати

| Артефакт | Шлях | Примітка |
|---|---|---|
| JSON-звіт (Cumulative) | `reports/backtests/backtest_<run_id_cum>.json` | run_id = timestamp старту |
| JSON-звіт (Sep-only) | `reports/backtests/backtest_<run_id_sep>.json` | |
| stdout Cumulative | `reports/backtests/R4_cum_B3_stdout.txt` | |
| stdout Sep-only | `reports/backtests/R4_sep_B3_stdout.txt` | |
| Логи домену | `logs/aurora_core.log` | перезаписується кожним запуском |
| Ордер-лог JSONL | `logs/backtests/order_log_<run_id>.jsonl` | ізольований per-run |

**Знайти свіжий JSON після завершення:**

```powershell
python -X utf8 -c "
from pathlib import Path
import time
d=Path('reports/backtests')
files=sorted(d.glob('backtest_*.json'),key=lambda f:f.stat().st_mtime,reverse=True)[:4]
for f in files:
    mt=time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(f.stat().st_mtime))
    print(mt, f'{f.stat().st_size:>10}', f.name)
"
```

---

## 7. Пост-запускний чекліст

Виконуй **окремо для кожного** прогону після `Exit code: 0`.

### 7.1 Підтвердити що JSON не порожній

```powershell
python -X utf8 -c "
from pathlib import Path
import time
d=Path('reports/backtests')
recent=sorted(d.glob('backtest_*.json'),key=lambda f:f.stat().st_mtime,reverse=True)[:3]
for f in recent:
    sz=f.stat().st_size
    mt=time.strftime('%H:%M:%S',time.localtime(f.stat().st_mtime))
    status='OK' if sz>500_000 else ('WARN<500KB' if sz>0 else 'FAIL:0bytes')
    print(f'{mt}  {sz:>10}  {status}  {f.name}')
"
```

### 7.2 Ключові метрики (замін RUN_ID)

```powershell
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

### 7.3 PnL по символах (замін RUN_ID)

```powershell
python -X utf8 -c "
import json
from pathlib import Path
from collections import defaultdict
RUN_ID = 'ЗАМІН_НА_RUN_ID'
rep = json.loads(Path(f'reports/backtests/backtest_{RUN_ID}.json').read_text(encoding='utf-8'))
trades = rep.get('trades', [])
def sf(v):
    try: return float(v)
    except:
        try: return complex(str(v)).real
        except: return 0.0
sym = defaultdict(lambda: {'pnl':0.0,'n':0})
for t in trades:
    s=t.get('symbol','?'); sym[s]['pnl']+=sf(t.get('pnl_usdt_net',0)); sym[s]['n']+=1
print('=== PnL PER SYMBOL ===')
for s,d in sorted(sym.items(),key=lambda x:x[1]['pnl']):
    ev=d['pnl']/d['n'] if d['n'] else 0
    print(f'  {s:<18} pnl={d[\"pnl\"]:>9.2f}  n={d[\"n\"]:>4}  ev/t={ev:>7.2f}')
"
```

### 7.4 BTCUSDT per-regime (Watchlist #1 — замін RUN_ID)

```powershell
python -X utf8 -c "
import json
from pathlib import Path
from collections import defaultdict
RUN_ID = 'ЗАМІН_НА_RUN_ID'
rep = json.loads(Path(f'reports/backtests/backtest_{RUN_ID}.json').read_text(encoding='utf-8'))
trades = rep.get('trades', [])
def sf(v):
    try: return float(v)
    except:
        try: return complex(str(v)).real
        except: return 0.0
btc = defaultdict(lambda: {'pnl':0.0,'n':0})
for t in trades:
    if t.get('symbol')!='BTCUSDT': continue
    r=t.get('market_regime','?'); btc[r]['pnl']+=sf(t.get('pnl_usdt_net',0)); btc[r]['n']+=1
btc_total = sum(d['pnl'] for d in btc.values())
btc_n     = sum(d['n']   for d in btc.values())
print(f'=== BTCUSDT PER-REGIME (total={btc_total:.2f} USDT, n={btc_n}) ===')
for r,d in sorted(btc.items(),key=lambda x:x[1]['pnl']):
    ev=d['pnl']/d['n'] if d['n'] else 0
    print(f'  {r:<20} pnl={d[\"pnl\"]:>9.2f}  n={d[\"n\"]:>4}  ev/t={ev:>7.2f}')
print()
if btc_total < -100 and btc_n >= 15:
    print('  [WATCHLIST] BTC: strongly negative (< -100 USDT, n>=15) — кандидат patched4')
elif btc_total < 0:
    print('  [MONITOR]   BTC: негативний але < threshold — стежити')
else:
    print('  [OK]        BTC: нейтральний або позитивний')
"
```

### 7.5 BNBUSDT per-regime + MR Payoff (Watchlist #2 — замін RUN_ID)

```powershell
python -X utf8 -c "
import json
from pathlib import Path
from collections import defaultdict
RUN_ID = 'ЗАМІН_НА_RUN_ID'
rep = json.loads(Path(f'reports/backtests/backtest_{RUN_ID}.json').read_text(encoding='utf-8'))
trades = rep.get('trades', [])
def sf(v):
    try: return float(v)
    except:
        try: return complex(str(v)).real
        except: return 0.0
bnb = defaultdict(lambda: {'pnl':0.0,'n':0})
for t in trades:
    if t.get('symbol')!='BNBUSDT': continue
    r=t.get('market_regime','?'); bnb[r]['pnl']+=sf(t.get('pnl_usdt_net',0)); bnb[r]['n']+=1
print('=== BNBUSDT PER-REGIME ===')
for r,d in sorted(bnb.items(),key=lambda x:x[1]['pnl']):
    ev=d['pnl']/d['n'] if d['n'] else 0
    td_flag = ' << FAIL: патч не спрацював!' if r in ('TREND_DOWN','TREND_UP') and d['n']>0 else ''
    mr_flag = ' << WATCHLIST' if r=='MEAN_REVERSION' else ''
    print(f'  {r:<20} pnl={d[\"pnl\"]:>8.2f}  n={d[\"n\"]:>4}  ev/t={ev:>7.2f}{td_flag}{mr_flag}')
td_n = bnb.get('TREND_DOWN',{'n':0})['n']
print()
print(f'  TREND_DOWN guard: n={td_n}', '  [OK]' if td_n==0 else '  [FAIL] патч не активний!')
print()
mr = [sf(t.get('pnl_usdt_net',0)) for t in trades
      if t.get('symbol')=='BNBUSDT' and t.get('market_regime')=='MEAN_REVERSION']
if not mr:
    print('  BNB MR: 0 угод')
else:
    wins=[p for p in mr if p>0]; losses=[p for p in mr if p<0]
    avg_w=sum(wins)/len(wins) if wins else 0
    avg_l=sum(losses)/len(losses) if losses else 0
    payoff=abs(avg_w/avg_l) if avg_l else float('inf')
    ev=sum(mr)/len(mr)
    print(f'  BNB MR: n={len(mr)}  total={sum(mr):.2f}  ev/t={ev:.2f}  wr={len(wins)/len(mr)*100:.1f}%  avg_win={avg_w:.2f}  avg_loss={avg_l:.2f}  payoff={payoff:.2f}')
    if ev < -2.0 and len(mr) >= 10:
        print('  [ЕСКАЛАЦІЯ] BNB MR: ev/t < -2.0 AND n >= 10 — кандидат patched4')
    elif ev < 0:
        print('  [MONITOR]   BNB MR: негативний але threshold не досягнуто')
    else:
        print('  [OK]        BNB MR: ev/t >= 0')
"
```

---

## 8. Watchlist: рішення після R4

Після обох прогонів заповни таблицю і прийми рішення:

### 8.1 BTC Watchlist

| Критерій | Sep-only pnl | Sep-only n | Вердикт |
|---|---|---|---|
| strongly negative | < -80 USDT | >= 15 | **patched4 candidate** |
| помірно негативний | -80..0 | будь-яке | monitor, ще одне вікно |
| нейтральний/позитивний | >= 0 | — | B3 стабільна по BTC |

**Якщо BTC Sep-only знову strongly negative:** у patched4 розглянути зниження `BTCUSDT.regime_sizing` для проблемних режимів або їх блокування.

### 8.2 BNB MR Watchlist

| Критерій | Sep-only ev/t | Sep-only n | Вердикт |
|---|---|---|---|
| ескалація | < -2.0 | >= 10 | **patched4: додати MR до BNBUSDT.allowed_regimes блокування** |
| monitor | < 0 | < 10 або ev/t > -2.0 | ще одне вікно |
| стабілізація | >= 0 | будь-яке | B3 стабільна по BNB MR |

### 8.3 Підсумкове рішення

```
Після заповнення Sep-only:

  BTC Sep-only pnl = ______  n = ______
  BNB MR Sep-only ev/t = ______  n = ______

  Якщо BTC strongly negative AND BNB MR ev/t < -2.0:
    → готувати patched4 (обидва кандидати)

  Якщо тільки ОДИН тригер:
    → готувати patched4 тільки для того що тригернуло

  Якщо жоден не тригернув:
    → B3 стабільна, продовжуємо ladder (R5: до жовтня)
```

---

## 9. Шаблон повідомлення для ревʼю

```
=== R4 B3 (patched3) — РЕЗУЛЬТАТИ ===

Версія конфігу : B3 (patched3, config/aurora/, SMA 48/192)

--- R4 CUMULATIVE (2023-06-01..2023-09-30) ---
  run_id         : backtest_YYYYMMDD_HHMMSS
  total_pnl      : ___.___ USDT
  max_drawdown   : ___.___ %
  total_trades   : ___
  win_rate       : ___.___ %
  sharpe_ratio   : ___._____
  end_balance    : ___.___ USDT
  bar_count      : ______
  Exit code      : _

--- R4 SEPTEMBER-ONLY (2023-09-01..2023-09-30) ---
  run_id         : backtest_YYYYMMDD_HHMMSS
  total_pnl      : ___.___ USDT
  max_drawdown   : ___.___ %
  total_trades   : ___
  win_rate       : ___.___ %
  sharpe_ratio   : ___._____
  end_balance    : ___.___ USDT
  bar_count      : ______
  Exit code      : _

--- PnL per symbol ---
         CUM:  BTC=_______  ETH=_______  BNB=_______
         SEP:  BTC=_______  ETH=_______  BNB=_______

--- BTCUSDT per-regime (Sep-only) ---
  TREND_UP        : pnl=_______  n=___
  TREND_DOWN      : pnl=_______  n=___
  HIGH_VOLATILITY : pnl=_______  n=___
  LOW_VOLATILITY  : pnl=_______  n=___
  MEAN_REVERSION  : pnl=_______  n=___

--- BNBUSDT TREND_DOWN guard ---
  CUM : n=___  (очікується 0)
  SEP : n=___  (очікується 0)

--- BNBUSDT × MEAN_REVERSION (Sep-only watchlist) ---
  n=___  ev/t=_____  wr=_____  payoff=_____  total=_______

--- WATCHLIST VERDICT ---
  BTC: [ strongly_negative | monitor | ok ]
  BNB MR: [ ескалація | monitor | ok ]
  Рішення: [ patched4 | continue_ladder ]

JSON paths:
  cum : reports/backtests/backtest_YYYYMMDD_HHMMSS.json
  sep : reports/backtests/backtest_YYYYMMDD_HHMMSS.json
```

---

## 10. Усунення несправностей

| Симптом | Причина | Дія |
|---|---|---|
| `Exit code: 1` одразу | YAML помилка / Pydantic error | Перевір `[FAIL]` у validation (п.3) |
| JSON < 500 KB або 0 байт | Backtest впав до збереження | Читай кінець stdout (сніппет нижче) |
| `0 trades` у JSON | State leakage (два виклики в одному процесі) | Відкрий новий термінал, `run_single_backtest.py` |
| BNB TREND_DOWN > 0 угод | patched3 не застосовано | Перечитай validation п.3, перевір `--side B` |
| `WARMUP_NOT_FULL_READY` > 95% | State leakage | Новий термінал, запусти заново |

**Читання кінця stdout при помилці:**

```powershell
python -X utf8 -c "
from pathlib import Path
p=Path('reports/backtests/R4_cum_B3_stdout.txt')
sz=p.stat().st_size
with open(p,'rb') as f:
    f.seek(max(0,sz-8192)); raw=f.read()
for enc in ['utf-16-le','utf-8','cp1252']:
    try:
        lines=raw.decode(enc,errors='replace').splitlines()
        errs=[l for l in lines if any(k in l for k in ['ERROR','Traceback','Exception','FAIL'])]
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

## Довідка: архітектура входу

```
scripts/diagnostics/run_single_backtest.py
  --side B       → config/aurora/          (B3 patched3, незмінний)
  --side A       → config/aurora_baseline/ (A baseline, незмінний)
  --rung 4       → start=2023-06-01, end=2023-09-30  (pre-defined)
  --start/--end  → кастомне вікно (Sep-only)

config/overlays/
  r4_window_cumulative.yaml       ← reference-документ для R4 cumulative датів
  r4_window_september_only.yaml   ← reference-документ для Sep-only датів
```

*Підготовлено: Backtest Ops Engineer | Phenix/Aurora B3 patched3 → R4*
