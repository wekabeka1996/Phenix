# R2 A vs B3 (patched3) — Ручний запуск: покроковий посібник

> **Версія:** patched3 | **Вікно:** R2 (2023-06-01..2023-07-31) | **Дата підготовки:** 2026-03-03

---

## Зміст

1. [Передумови](#1-передумови)
2. [Що змінилось у patched3](#2-що-змінилось-у-patched3)
3. [Валідація конфігу перед запуском](#3-валідація-конфігу-перед-запуском)
4. [Запуск A (baseline)](#4-запуск-a-baseline)
5. [Запуск B3 (patched3)](#5-запуск-b3-patched3)
6. [Де зберігаються результати](#6-де-зберігаються-результати)
7. [Пост-запускний чекліст](#7-пост-запускний-чекліст)
8. [Шаблон повідомлення для ревʼю](#8-шаблон-повідомлення-для-ревʼю)
9. [Усунення несправностей](#9-усунення-несправностей)

---

## 1. Передумови

### 1.1 Термінальне середовище

```bat
:: Відкрий НОВИЙ термінал (PowerShell або cmd) — не той, де щось вже запущено
cd C:\Users\wekab\Music\Phenix
.venv\Scripts\activate
python -V
:: Очікується: Python 3.11.x або 3.12.x
```

### 1.2 Критичні правила

| Правило | Причина |
|---|---|
| **Один процес = один прогін** | Два виклики `run_backtest_simulation()` в одному процесі → state leakage → 0 угод у другому |
| **Не використовуй `\| head`, `\| tail`** | Pipe обриває stdout → файл результатів частковий або 0 байт |
| **Завжди `> file.txt 2>&1`** | Stderr іде разом зі stdout — без цього помилки втрачаються |
| **Дочекайся `Exit code: 0`** | До цього JSON-звіту не існує |
| **A та B3 — окремі cmd-вікна, не паралельно** | Можливі конфлікти WAL / lock-файлів |

### 1.3 Перевір parquet-дані

```bat
python -X utf8 -c "
from pathlib import Path
syms=['BTCUSDT','ETHUSDT','BNBUSDT','DOGEUSDT','1000PEPEUSDT']
for s in syms:
    files=sorted(Path(f'data/processed/{s}/5m').glob('*_enriched.parquet')) if Path(f'data/processed/{s}/5m').exists() else []
    print(f'{s}: {len(files)} файлів — {[f.name for f in files[:3]]}...')
"
:: Для R2 потрібні файли за 2023-06 та 2023-07
```

---

## 2. Що змінилось у patched3

### 2.1 Кумулятивні зміни (порівняно з A baseline)

| # | Файл | Параметр | A (aurora_baseline) | B3 (aurora / patched3) |
|---|---|---|---|---|
| 1 | `regime.yaml` | `models.sma_trend.sma_short_period` | 24 | **48** |
| 2 | `regime.yaml` | `models.sma_trend.sma_long_period` | 96 | **192** |
| 3 | `strategies/aurora.yaml` | `decision.regime_threshold_multipliers.TREND_UP` | 0.85 | **1.50** |
| 4 | `strategies/aurora.yaml` | `ETHUSDT.allowed_regimes` | включає TREND_UP | **без TREND_UP** |
| 5 | `strategies/aurora.yaml` | `BNBUSDT.allowed_regimes` | включає TREND_UP, TREND_DOWN | **тільки LOW_VOL, FLAT_NORMAL, MR** ← NEW |
| 6 | `strategies/aurora.yaml` | `BTCUSDT.regime_sizing.HIGH_VOLATILITY` | 0.50 | **0.50** (revert з 0.65) |

### 2.2 Новий патч patched3 (лише ця зміна)

```
Файл   : config/aurora/strategies/aurora.yaml
Шлях   : aurora.assets.BNBUSDT.allowed_regimes

БУЛО   (patched2): ["TREND_DOWN", "LOW_VOLATILITY", "FLAT_NORMAL", "MEAN_REVERSION"]
СТАЛО  (patched3): ["LOW_VOLATILITY", "FLAT_NORMAL", "MEAN_REVERSION"]
```

**Обґрунтування:**
- B2 (patched2): BNBUSDT × TREND_DOWN → **-215.51 USDT, 44 угоди, EV/t = -4.90**
- Причина: SMA 48/192 визначає TREND_DOWN із запізненням → вхід після розвороту
- В A baseline: BNB × TREND_DOWN = +49 USDT (+1.64 EV/t) при SMA 24/96

### 2.3 Overlay-файли (reference)

```
config/overlays/r2_window.yaml                    ← дати R2 вікна
config/overlays/patched3_bnb_block_trend_down.yaml ← документація diff + revert-інструкції
```

> **Увага:** overlay-файли — це документація, а не автоматично підвантажувані файли.
> `ConfigLoader` не читає `config/overlays/` автоматично. Зміни вже внесені напряму
> в `config/aurora/strategies/aurora.yaml`.

---

## 3. Валідація конфігу перед запуском

Виконай один раз перед запуском обох прогонів:

```bat
python -X utf8 -c "
import yaml
p='config/aurora/strategies/aurora.yaml'; r='config/aurora/regime.yaml'
a=yaml.safe_load(open(p,encoding='utf-8'))['aurora']
g=yaml.safe_load(open(r,encoding='utf-8'))
sma_s=g['models']['sma_trend']['sma_short_period']
sma_l=g['models']['sma_trend']['sma_long_period']
rtm=a['decision']['regime_threshold_multipliers']
bnb_ar=a['assets']['BNBUSDT']['allowed_regimes']
btc_hv=a['assets']['BTCUSDT']['regime_sizing']['HIGH_VOLATILITY']
eth_ar=a['assets']['ETHUSDT']['allowed_regimes']
ok=True
def chk(label,val,cond,expect):
    global ok
    s='OK' if cond else 'FAIL'
    if not cond: ok=False
    print(f'  [{s}] {label}: {val!r}  (expect {expect})')
chk('SMA short',sma_s,sma_s==48,'48')
chk('SMA long',sma_l,sma_l==192,'192')
chk('TREND_UP mult',rtm.get('TREND_UP'),rtm.get('TREND_UP')==1.5,'1.50')
chk('ETH TREND_UP absent','TREND_UP' not in eth_ar,'TREND_UP' not in eth_ar,'absent')
chk('BNB TREND_UP absent','TREND_UP' not in bnb_ar,'TREND_UP' not in bnb_ar,'absent')
chk('BNB TREND_DOWN absent','TREND_DOWN' not in bnb_ar,'TREND_DOWN' not in bnb_ar,'absent')
chk('BNB allowed_regimes',bnb_ar,set(bnb_ar)=={'LOW_VOLATILITY','FLAT_NORMAL','MEAN_REVERSION'},'[LOW_VOL,FLAT_NORMAL,MR]')
chk('BTC HIGH_VOL sizing',btc_hv,btc_hv==0.50,'0.50')
print(); print('RESULT:','ALL CHECKS PASSED' if ok else 'SOME CHECKS FAILED -- STOP, do not run backtest')
"
```

**Очікуваний вивід:**
```
  [OK] SMA short: 48  (expect 48)
  [OK] SMA long: 192  (expect 192)
  [OK] TREND_UP mult: 1.5  (expect 1.50)
  [OK] ETH TREND_UP absent: True  (expect absent)
  [OK] BNB TREND_UP absent: True  (expect absent)
  [OK] BNB TREND_DOWN absent: True  (expect absent)
  [OK] BNB allowed_regimes: [...]  (expect [LOW_VOL,FLAT_NORMAL,MR])
  [OK] BTC HIGH_VOL sizing: 0.5  (expect 0.50)

RESULT: ALL CHECKS PASSED
```

Якщо будь-який `[FAIL]` — **СТОП**, не запускай прогін.

---

## 4. Запуск A (baseline)

> Config: `config/aurora_baseline/` (SMA 24/96, незмінний)

**Відкрий нове cmd/PowerShell вікно:**

```bat
cd C:\Users\wekab\Music\Phenix
.venv\Scripts\activate

python -X utf8 scripts\diagnostics\run_single_backtest.py ^
  --side A --rung 2 ^
  > reports\backtests\R2_A_B3_stdout.txt 2>&1

echo Exit code: %ERRORLEVEL%
```

> `--rung 2` автоматично встановлює `start_date=2023-06-01`, `end_date=2023-07-31`.
> Конфіг A = `config/aurora_baseline/` — launcher обирає його за `--side A`.
> **Не редагуй** `config/aurora_baseline/` перед запуском.

**Час виконання:** ~3–10 годин (залежно від кількості логів).

**Перевірка що прогін запустився** (в іншому вікні, через ~30 сек):
```bat
python -X utf8 -c "
from pathlib import Path; import time
p=Path('reports/backtests/R2_A_B3_stdout.txt')
print('Розмір:', p.stat().st_size, 'байт' if p.exists() else 'ФАЙЛ НЕ ЗНАЙДЕНО')
"
```

---

## 5. Запуск B3 (patched3)

> Config: `config/aurora/` (SMA 48/192 + patched3 — вже внесено)
> **Запускай ТІЛЬКИ після завершення A (exit code 0).**

**Відкрий НОВИЙ cmd/PowerShell вікно:**

```bat
cd C:\Users\wekab\Music\Phenix
.venv\Scripts\activate

python -X utf8 scripts\diagnostics\run_single_backtest.py ^
  --side B --rung 2 ^
  > reports\backtests\R2_B3_stdout.txt 2>&1

echo Exit code: %ERRORLEVEL%
```

> `--side B` використовує `config/aurora/` з patched3-змінами що вже застосовані.

**Перевірка прогресу** (поки виконується):
```bat
python -X utf8 -c "
from pathlib import Path; import time
p=Path('reports/backtests/R2_B3_stdout.txt')
if p.exists():
    data=p.read_bytes()[-6000:].decode('utf-16-le',errors='replace')
    for l in data.splitlines()[-15:]: print(l)
"
```

---

## 6. Де зберігаються результати

| Артефакт | Шлях | Примітка |
|---|---|---|
| JSON-звіт (A) | `reports/backtests/backtest_<run_id_A>.json` | run_id = timestamp запуску |
| JSON-звіт (B3) | `reports/backtests/backtest_<run_id_B3>.json` | |
| stdout A | `reports/backtests/R2_A_B3_stdout.txt` | UTF-16 (PowerShell) |
| stdout B3 | `reports/backtests/R2_B3_stdout.txt` | UTF-16 (PowerShell) |
| Логи домену | `logs/domain_*.log` | перезаписуються при кожному запуску |
| WAL backtest | `ops/wal/backtest/<run_id>/` | ізольований per-run |

**Знайти свіжий JSON після завершення:**
```bat
python -X utf8 -c "
from pathlib import Path; import time
d=Path('reports/backtests')
files=sorted([f for f in d.glob('backtest_*.json')],key=lambda x:x.stat().st_mtime,reverse=True)[:5]
for f in files:
    mt=time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(f.stat().st_mtime))
    print(mt, f'{f.stat().st_size:>10}', f.name)
"
```

---

## 7. Пост-запускний чекліст

Виконай після того як **обидва** прогони завершились із `Exit code: 0`.

### 7.1 Підтвердити що JSON не порожній

```bat
python -X utf8 -c "
from pathlib import Path
import json, time

d = Path('reports/backtests')
recent = sorted(d.glob('backtest_*.json'), key=lambda f: f.stat().st_mtime, reverse=True)[:2]
for f in recent:
    sz = f.stat().st_size
    mt = time.strftime('%H:%M:%S', time.localtime(f.stat().st_mtime))
    status = 'OK' if sz > 100_000 else 'WARN: малий файл'
    print(f'{mt}  {sz:>10} bytes  {status}  {f.name}')
"
```

### 7.2 Витягти ключові метрики

```bat
python -X utf8 -c "
import json, sys
from pathlib import Path

def safe_float(v):
    if v is None: return 0.0
    try: return float(v)
    except:
        try: return complex(str(v)).real
        except: return 0.0

d = Path('reports/backtests')
files = sorted(d.glob('backtest_*.json'), key=lambda f: f.stat().st_mtime, reverse=True)[:2]

for f in files:
    rep = json.loads(f.read_text(encoding='utf-8'))
    m = rep.get('metrics', {})
    meta = rep.get('metadata', {})
    cfg = meta.get('config_name', '?')
    print(f'--- {f.name} (config={cfg}) ---')
    print(f'  total_pnl       : {safe_float(m.get(\"total_pnl\")):.2f} USDT')
    print(f'  roi_pct         : {safe_float(m.get(\"roi_pct\")):.2f}%')
    print(f'  max_drawdown    : {safe_float(m.get(\"max_drawdown\"))*100:.2f}%')
    print(f'  total_trades    : {m.get(\"total_trades\")}')
    print(f'  win_rate        : {safe_float(m.get(\"win_rate\"))*100:.1f}%')
    print(f'  sharpe_ratio    : {safe_float(m.get(\"sharpe_ratio\")):.4f}')
    print(f'  end_balance     : {safe_float(m.get(\"end_balance\")):.2f} USDT')
    print()
"
```

### 7.3 Перевірити BNBUSDT per-regime (B3 тільки)

```bat
python -X utf8 -c "
import json
from pathlib import Path
from collections import defaultdict

def safe_float(v):
    try: return float(v)
    except: return 0.0

d = Path('reports/backtests')
# Бери найновіший JSON
f = max(d.glob('backtest_*.json'), key=lambda x: x.stat().st_mtime)
print('Аналіз:', f.name)
rep = json.loads(f.read_text(encoding='utf-8'))
trades = rep.get('trades', [])

bnb = defaultdict(lambda: {'pnl':0.0,'n':0})
for t in trades:
    if t.get('symbol') != 'BNBUSDT': continue
    r = t.get('market_regime','?')
    p = safe_float(t.get('pnl_usdt_net',0))
    bnb[r]['pnl'] += p; bnb[r]['n'] += 1

print('BNBUSDT per-regime:')
for reg, s in sorted(bnb.items(), key=lambda x: x[1]['pnl']):
    ev = s['pnl']/s['n'] if s['n'] else 0
    print(f'  {reg:20} pnl={s[\"pnl\"]:>8.2f}  n={s[\"n\"]:>4}  ev/t={ev:>7.2f}')

td_n = bnb.get('TREND_DOWN',{}).get('n',0)
td_pnl = bnb.get('TREND_DOWN',{}).get('pnl',0)
print()
if td_n == 0:
    print('  ПЕРЕВІРКА: TREND_DOWN заблоковано (0 угод) -- OK')
else:
    print(f'  УВАГА: TREND_DOWN не заблоковано! {td_n} угод, {td_pnl:.2f} USDT')
"
```

### 7.4 Порівняти A vs B3

```bat
python -X utf8 -c "
import json, time
from pathlib import Path
from collections import defaultdict

def safe_float(v):
    try: return float(v)
    except:
        try: return complex(str(v)).real
        except: return 0.0

d = Path('reports/backtests')
files = sorted(d.glob('backtest_*.json'), key=lambda f: f.stat().st_mtime, reverse=True)[:2]
if len(files) < 2:
    print('Потрібно 2 JSON файли'); exit()

reps = [json.loads(f.read_text(encoding='utf-8')) for f in files]
# Впорядкуй: A (aurora_baseline) перший
reps.sort(key=lambda r: r.get('metadata',{}).get('config_name',''))

labels = [r.get('metadata',{}).get('config_name','?') for r in reps]
ma, mb = [r.get('metrics',{}) for r in reps]

print(f'  {\"\":25} {labels[0]:>18} {labels[1]:>18} {\"delta\":>12}')
for key, label, mult in [
    (\"total_pnl\",\"total_pnl USDT\",1),
    (\"roi_pct\",\"roi_pct %\",1),
    (\"max_drawdown\",\"max_drawdown %\",100),
    (\"total_trades\",\"total_trades\",1),
    (\"win_rate\",\"win_rate\",1),
    (\"sharpe_ratio\",\"sharpe_ratio\",1),
    (\"end_balance\",\"end_balance USDT\",1),
]:
    va = safe_float(ma.get(key)) * mult
    vb = safe_float(mb.get(key)) * mult
    print(f'  {label:25} {va:>18.4f} {vb:>18.4f} {vb-va:>+12.4f}')
"
```

---

## 8. Шаблон повідомлення для ревʼю

Після завершення скопіюй та заповни:

```
=== R2 A vs B3 (patched3) — РЕЗУЛЬТАТИ ===

Вікно   : 2023-06-01..2023-07-31

A (aurora_baseline, SMA 24/96):
  run_id       : backtest_YYYYMMDD_HHMMSS
  total_pnl    : ___.___ USDT
  max_drawdown : ___.___ %
  total_trades : ___
  win_rate     : ___.___ %
  sharpe_ratio : ___._____
  end_balance  : ___.___ USDT

B3 (aurora, SMA 48/192, patched3):
  run_id       : backtest_YYYYMMDD_HHMMSS
  total_pnl    : ___.___ USDT
  max_drawdown : ___.___ %
  total_trades : ___
  win_rate     : ___.___ %
  sharpe_ratio : ___._____
  end_balance  : ___.___ USDT

BNBUSDT TREND_DOWN (B3):
  угоди        : ___ (очікується 0)
  pnl          : ___.___ USDT

Delta B3 vs A:
  total_pnl    : +___.___ USDT
  max_drawdown : ___.___ pp

Exit codes    : A=_  B3=_
JSON розміри  : A=___ KB  B3=___ KB
```

---

## 9. Усунення несправностей

| Симптом | Причина | Дія |
|---|---|---|
| `Exit code: 1` в перші секунди | YAML помилка / schema mismatch | Перевір `[FAIL]` у validation one-liner (п.3) |
| JSON файл < 100 KB або 0 байт | Backtest впав до збереження | Прочитай кінець stdout (`reports/backtests/R2_*_stdout.txt`) |
| Прогін > 12 годин | Надмірний DEBUG logging | Нормально — дочекайся `Exit code: 0` |
| `0 trades` у JSON | State leakage (два виклики в одному процесі) | Переконайся що використовуєш `run_single_backtest.py`, не `run_backtest_ladder.py` |
| BNBUSDT TREND_DOWN > 0 угод | Patched3 не застосовано | Перезапусти validation (п.3), перевір `aurora.yaml:673` |
| `WARMUP_NOT_FULL_READY` > 95% | State leakage з попереднього прогону | Відкрий новий термінал, запусти `run_single_backtest.py` заново |
| `calmar_ratio` = complex string | DD > 100% (blown account) | Рахуй `complex(s).real`; стратегія blown — перевір BNB/BTC sizing |
| PowerShell stdout = UTF-16 | PowerShell redirect за замовчуванням UTF-16 | Нормально — файл читається через `.decode('utf-16-le')` |

### Реверт patched3 (якщо потрібно відкотити BNB TREND_DOWN зміну)

```bat
:: В aurora.yaml рядок ~673 змінити вручну:
::
:: БУЛО  (patched3): allowed_regimes: ["LOW_VOLATILITY", "FLAT_NORMAL", "MEAN_REVERSION"]
:: СТАЛО (patched2): allowed_regimes: ["TREND_DOWN", "LOW_VOLATILITY", "FLAT_NORMAL", "MEAN_REVERSION"]
::
:: Референс: config/overlays/patched3_bnb_block_trend_down.yaml (секція BEFORE)
```

---

*Підготовлено: Backtest Ops Engineer | Phenix/Aurora B3 patched3*
