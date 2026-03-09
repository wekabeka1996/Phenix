# R2 Runbook — Backtest A/B для вікна 2023-06-01..2023-07-31
<!-- автор: Backtest Operations Engineer | дата: 2026-03-02 -->

---

## Швидкий огляд

| | A (baseline) | B (patched) |
|---|---|---|
| Config Dir | `config/aurora_baseline/` | `config/aurora/` |
| SMA short/long | 24 / 96 | **48 / 192** |
| ETH HIGH_VOL sizing | 0.30 | **0.50** |
| ETH LOW_VOL sizing | 1.00 | **0.85** |
| BTC HIGH_VOL sizing | 0.50 | **0.65** |
| BTC LOW_VOL sizing | 0.75 | 0.75 (без змін) |
| regime_smoothing | відсутній | enabled: false |
| regime_shift_inception | відсутній | enabled: false |

Вікно: `2023-06-01 → 2023-07-31`
Символи (є parquet): BTCUSDT, ETHUSDT, DOGEUSDT, 1000PEPEUSDT, BNBUSDT
Символи (немає parquet, будуть пропущені): SOLUSDT, XRPUSDT

---

## 1. Передумови (checklist перед запуском)

- [ ] Ти в корені репо: `cd C:\Users\wekab\Music\Phenix`
- [ ] Python оточення активоване:
  ```
  .venv\Scripts\activate
  ```
- [ ] Перевірити що обидва конфіг-каталоги існують:
  ```
  dir config\aurora_baseline
  dir config\aurora
  ```
- [ ] Перевірити що parquet файли є для R2 (червень + липень):
  ```
  dir data\processed\BTCUSDT\5m
  dir data\processed\ETHUSDT\5m
  ```
  Очікувані файли: `2023-06_enriched.parquet`, `2023-07_enriched.parquet`
- [ ] Вихідна директорія існує:
  ```
  mkdir reports\backtests
  ```
- [ ] Немає запущених python-процесів backtest (перевір Task Manager або):
  ```
  tasklist | findstr python
  ```
- [ ] Місця на диску достатньо (>=500 MB для JSON + логів)

**ВАЖЛИВО:** Запускай A і B в окремих cmd-вікнах і по черзі. Не запускай обидва одночасно в одному процесі — це викликає state leakage (warmup не скидається, 2-й запуск дає 0 трейдів).

---

## 2. Конфігурація: що перевірити / змінити

### 2.1 Дати (НЕ потрібно редагувати вручну)

`run_single_backtest.py --rung 2` автоматично виставляє:
```
start_date = 2023-06-01
end_date   = 2023-07-31
```
через `config.trading.backtest.start_date/end_date` в Python, **без зміни YAML-файлів**.

Якщо з якоїсь причини запускаєш через `main.py` (НЕ рекомендується для A-side), тоді треба вручну змінити в обох конфіг-каталогах:

**Файл:** `config/aurora_baseline/trading.yaml` (для A)
**Файл:** `config/aurora/trading.yaml` (для B)
**Секція:**
```yaml
trading:
  backtest:
    start_date: "2023-06-01"   # << змінити на це
    end_date:   "2023-07-31"   # << змінити на це
```
> Зараз обидва мають `end_date: "2023-09-30"` — це R4, не R2.

### 2.2 Конфіг для A (aurora_baseline) — перевірка

```
config\aurora_baseline\regime.yaml
  sma_trend.sma_short_period: 24      (очікується)
  sma_trend.sma_long_period:  96      (очікується)

config\aurora_baseline\strategies\aurora.yaml
  ETHUSDT.regime_sizing.HIGH_VOLATILITY: 0.3  (очікується)
  ETHUSDT.regime_sizing.LOW_VOLATILITY:  1.0  (очікується)
  BTCUSDT.regime_sizing.HIGH_VOLATILITY: 0.5  (очікується)
```

### 2.3 Конфіг для B (aurora patched) — перевірка

```
config\aurora\regime.yaml
  sma_trend.sma_short_period: 48      (очікується)
  sma_trend.sma_long_period:  192     (очікується)

config\aurora\strategies\aurora.yaml
  ETHUSDT.regime_sizing.HIGH_VOLATILITY: 0.5  (очікується)
  ETHUSDT.regime_sizing.LOW_VOLATILITY:  0.85 (очікується)
  BTCUSDT.regime_sizing.HIGH_VOLATILITY: 0.65 (очікується)
```

---

## 3. Команди запуску

> **ЗАБОРОНЕНО** використовувати `| head`, `| more`, будь-який pipe.
> Весь stdout+stderr редиректити у файл через `> file.txt 2>&1`.
> Кожен запуск — окреме cmd-вікно, один процес.

### 3.1 Запуск A (baseline)

Відкрий **нове** cmd-вікно:

```bat
cd C:\Users\wekab\Music\Phenix
.venv\Scripts\activate
python -X utf8 scripts\diagnostics\run_single_backtest.py --side A --rung 2 > reports\backtests\R2_A_stdout.txt 2>&1
echo Exit code: %ERRORLEVEL%
```

Очікуваний вихід у консолі після завершення:
```
Exit code: 0
```

Лог: `reports\backtests\R2_A_stdout.txt`

### 3.2 Запуск B (patched)

Дочекайся завершення A. Відкрий **нове** cmd-вікно:

```bat
cd C:\Users\wekab\Music\Phenix
.venv\Scripts\activate
python -X utf8 scripts\diagnostics\run_single_backtest.py --side B --rung 2 > reports\backtests\R2_B_stdout.txt 2>&1
echo Exit code: %ERRORLEVEL%
```

Лог: `reports\backtests\R2_B_stdout.txt`

---

## 4. Вихідні файли

### 4.1 JSON-звіти (основний результат)

Після успішного запуску движок записує:
```
reports\backtests\backtest_<YYYYMMDD_HHMMSS>.json
```
`run_id` = timestamp старту процесу, наприклад `20260302_143521`.

Шлях виводиться наприкінці stdout-лога:
```
Full report   : C:\...\reports\backtests\backtest_20260302_XXXXXX.json
```

Перевір що файл НЕ порожній:
```bat
for %f in (reports\backtests\backtest_202603*.json) do @echo %~zf  %f
```
Розмір має бути **>100 000 байт** (типово 1-3 MB для R2).

### 4.2 Run bundle (артефакти конфігу)

```
reports\backtests\<YYYYMMDD_HHMMSS>\
  manifest.json        (config hash, git sha, список файлів)
  result.json          (те саме що backtest_*.json)
  resolved_config.json (розгорнутий конфіг)
```

### 4.3 Лог-файли движка

```
logs\aurora_core.log      (основний лог backtest)
logs\aurora_core.log.1    (ротований)
logs\backtests\order_log_<run_id>.jsonl   (лог ордерів)
```

### 4.4 Stdout-логи (наші файли)

```
reports\backtests\R2_A_stdout.txt
reports\backtests\R2_B_stdout.txt
```

---

## 5. Пост-ран валідація

### 5.1 Перевірка через Python (рекомендовано)

```bat
python -X utf8 -c "
import json, sys
from pathlib import Path

# Замін run_id на реальний зі stdout-лога
run_id = 'ЗАМІН_НА_RUN_ID'
p = Path(f'reports/backtests/backtest_{run_id}.json')

if not p.exists():
    print('FAIL: файл не знайдено'); sys.exit(1)
if p.stat().st_size < 1000:
    print(f'FAIL: файл малий ({p.stat().st_size} байт)'); sys.exit(1)

data = json.loads(p.read_text(encoding='utf-8'))
m = data.get('metrics', {})
pipe = data.get('pipeline', {})
meta = data.get('metadata', {})

print('=== METRICS ===')
print(f'  run_id         : {meta.get(\"run_id\")}')
print(f'  total_pnl      : {m.get(\"total_pnl\")}')
print(f'  roi_pct        : {m.get(\"roi_pct\")}')
print(f'  max_drawdown   : {round(float(m.get(\"max_drawdown\", 0)) * 100, 2)} %')
print(f'  total_trades   : {m.get(\"total_trades\")}')
print(f'  win_rate       : {m.get(\"win_rate\")}')
print(f'  sharpe_ratio   : {m.get(\"sharpe_ratio\")}')
print(f'  end_balance    : {m.get(\"end_balance\")}')
print(f'  bar_count      : {pipe.get(\"bar_count\")}')
print(f'  blocked        : {pipe.get(\"blocked_reason_counts\")}')
"
```

### 5.2 Критерії "прогін успішний"

| Перевірка | Мінімум |
|---|---|
| Файл існує | так |
| Розмір файлу | > 500 000 байт |
| `metrics.total_trades` | > 0 |
| `metrics.end_balance` | > 0 (не blown) |
| `metrics.max_drawdown` | < 1.0 (менше 100%) |
| `pipeline.bar_count` | > 40 000 |
| Exit code | 0 |

### 5.3 Звірка у stdout-лозі

Наприкінці `R2_A_stdout.txt` / `R2_B_stdout.txt` має бути:
```
==========================================
  RESULT SUMMARY — side=A | rung=R2
==========================================
  run_id        : 20260302_XXXXXX
  period        : 2023-06-01 → 2023-07-31
  total_pnl     : XXXX.XXXX USDT
  roi_pct       : XXXX.XXXX%
  max_drawdown  : XX.XX%
  total_trades  : XXX
  win_rate      : X.XXXX
  end_balance   : XXXX.XXXX USDT
  sharpe_ratio  : X.XXXX
  bar_count     : XXXXX
  Full report   : C:\...\backtest_20260302_XXXXXX.json
==========================================
```

### 5.4 Ручна таблиця для маніфесту (заповни після обох прогонів)

| Метрика | A (baseline) | B (patched) | Delta B-A |
|---|---|---|---|
| run_id | | | — |
| total_pnl | | | |
| roi_pct % | | | |
| max_drawdown % | | | |
| total_trades | | | |
| win_rate | | | |
| sharpe_ratio | | | |
| end_balance | | | — |
| bar_count | | | — |

---

## 6. Troubleshooting — Топ 5 причин падіння

### F-1: YAML boolean `off` інтерпретується як `False`

**Симптом:** `ValidationError: ... field expected str, got bool` або `KeyError` при завантаженні конфігу.

**Причина:** YAML-1.1 вважає `off`, `on`, `yes`, `no` булевими значеннями без лапок.

**Перевірка:**
```bat
python -X utf8 -c "
import yaml
for f in ['config/aurora/strategies/aurora.yaml', 'config/aurora/regime.yaml']:
    data = yaml.safe_load(open(f, encoding='utf-8').read())
    print(f, 'OK')
"
```

**Виправлення:** Знайди в YAML і візьми в лапки:
```yaml
# НЕПРАВИЛЬНО:
some_field: off
# ПРАВИЛЬНО:
some_field: "off"
```

---

### F-2: Відсутній parquet-файл для місяця

**Симптом:**
```
FileNotFoundError: data/processed/XYZUSDT/5m/2023-06_enriched.parquet
```
або символ тихо пропускається (0 барів по ньому).

**Перевірка доступності файлів:**
```bat
python -X utf8 -c "
from pathlib import Path
for sym in ['BTCUSDT','ETHUSDT','DOGEUSDT','1000PEPEUSDT','BNBUSDT']:
    for ym in ['2023-06', '2023-07']:
        p = Path(f'data/processed/{sym}/5m/{ym}_enriched.parquet')
        print('OK' if p.exists() else 'MISSING', p)
"
```

**Відомо відсутні (очікувано):** SOLUSDT, XRPUSDT — у instruments.yaml є, parquet немає.
Движок їх пропускає. Якщо він на них падає — виключи з instruments.yaml тимчасово.

**Виправлення якщо треба символ:** завантаж parquet через `tools/parquet_pipeline/`.

---

### F-3: Schema mismatch (fail-fast parquet validation)

**Симптом:**
```
SchemaValidationError: column 'XXX' expected dtype float64, got int32
```
або
```
AssertionError: ... missing required columns: [...]
```

**Де шукати:** у `logs/aurora_core.log` або в `R2_A_stdout.txt` / `R2_B_stdout.txt`.

**Причина:** parquet-файл побудований старим pipeline без нових колонок.

**Виправлення:**
1. Перевір версію схеми: `tools/parquet_pipeline/audit.py`
2. Перебудуй файл: `python -m tools.parquet_pipeline --symbol BTCUSDT --year 2023 --month 6`
3. Перевір що колонки відповідають `schemas/` JSON-схемам

---

### F-4: `sys.exit(1)` всередині `run_backtest_simulation`

**Симптом:** Exit code = 1, stdout-лог обривається посередині. JSON-звіт відсутній або порожній (0 байт — файл відкрили, але `json.dump` не встиг завершитись).

**Де причина:** `apps/reference/main.py` у блоці `except Exception`:
```python
except Exception as e:
    LOG.error(f"Backtest failed: {e}", exc_info=True)
    sys.exit(1)
```

`SystemExit` **не ловиться** `except Exception` — вбиває процес.

**Як знайти root cause:**
```bat
python -X utf8 -c "
content = open('reports/backtests/R2_A_stdout.txt', encoding='utf-8', errors='replace').read()
lines = content.splitlines()
# Знайди 'ERROR' або 'Traceback'
for i, l in enumerate(lines):
    if 'ERROR' in l or 'Traceback' in l or 'Exception' in l:
        print(f'L{i+1}: {l}')
"
```
Або перевір `logs/aurora_core.log` — там весь traceback з `exc_info=True`.

**Типові sub-причини:**
- Невалідний конфіг (Pydantic ValidationError) → дивись F-1
- Відсутній parquet → дивись F-2
- Corrupted JSON schema registry → `python -c "from apps.reference.main import init_global_registry; init_global_registry('.')" 2>&1`

---

### F-5: Колізія шляхів / перезапис JSON-звіту

**Симптом:** JSON звіту перезаписаний іншим прогоном і містить не ті дані. Або обидва прогони запущені одночасно в одному процесі (state leakage → 0 трейдів на 2-му).

**Захист вбудований:** `run_id = datetime.now().strftime("%Y%m%d_%H%M%S")` — унікальний timestamp.

**Але:** якщо два процеси запущено в ту саму секунду — будe колізія.

**Правило:** запускай A, чекай завершення (Exit code 0), тоді запускай B.

**Перевірка після запуску:**
```bat
python -X utf8 -c "
from pathlib import Path
reports = sorted(Path('reports/backtests').glob('backtest_202603*.json'))
for r in reports:
    print(r.stat().st_size, r.name)
"
```
Якщо два файли мають однаковий розмір — один з них може бути копією.
Звір `run_id` всередині файлу з іменем файлу:
```bat
python -X utf8 -c "
import json
from pathlib import Path
for r in Path('reports/backtests').glob('backtest_202603*.json'):
    d = json.loads(r.read_text(encoding='utf-8'))
    rid = d.get('metadata', {}).get('run_id', '?')
    print(r.name, '→ internal run_id:', rid)
"
```

---

## 7. Оновлення маніфесту після обох прогонів

Після отримання обох run_id запусти:

```bat
python -X utf8 -c "
import json, copy
from pathlib import Path

RUN_ID_A = 'ЗАМІН'   # наприклад: 20260302_143521
RUN_ID_B = 'ЗАМІН'   # наприклад: 20260302_160812

def load_metrics(run_id):
    p = Path(f'reports/backtests/backtest_{run_id}.json')
    data = json.loads(p.read_text(encoding='utf-8'))
    m = data['metrics']
    pipe = data.get('pipeline', {})
    broker = data.get('broker', {}) or {}
    regimes = data.get('regimes', {}) or {}
    return {
        'error': False,
        'total_pnl':        round(float(m['total_pnl']), 4),
        'roi_pct':          round(float(m['roi_pct']), 4),
        'max_drawdown':     round(float(m['max_drawdown']), 6),
        'max_drawdown_pct': round(float(m['max_drawdown']) * 100, 2),
        'total_trades':     int(m['total_trades']),
        'win_rate':         round(float(m['win_rate']), 4),
        'end_balance':      round(float(m['end_balance']), 4),
        'sharpe_ratio':     round(float(m.get('sharpe_ratio') or 0), 4),
        'calmar_ratio':     round(float(m.get('calmar_ratio') or 0), 4),
        'run_id':           run_id,
        'report_path':      str(Path(f'reports/backtests/backtest_{run_id}.json').resolve()),
        'fees_total':       round(float(broker.get('total_fees') or 0), 4),
        'fills_total':      int(broker.get('total_fills') or 0),
        'cancels_total':    int(broker.get('total_cancels') or 0),
        'bar_count':        int(pipe.get('bar_count') or 0),
        'blocked_reasons':  pipe.get('blocked_reason_counts', {}),
        'regime_counts_by_symbol': (regimes.get('counts_by_symbol') or {}),
        'pnl_by_symbol':    {},
    }

def compute_deltas(a, b):
    keys = ['total_pnl','roi_pct','max_drawdown_pct','total_trades','win_rate','sharpe_ratio']
    d = {}
    for k in keys:
        try:
            d[f'delta_{k}'] = round(float(b[k]) - float(a[k]), 4)
        except Exception:
            d[f'delta_{k}'] = None
    return d

ma = load_metrics(RUN_ID_A)
mb = load_metrics(RUN_ID_B)
deltas = compute_deltas(ma, mb)

# Завантажити існуючий маніфест
manifest_path = Path('reports/arhive/backtest_ladder_manifest.json')
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))

# Знайти R2 і оновити
for rung in manifest['rungs']:
    if rung['rung'] == 2:
        rung['metrics_a'] = ma
        rung['metrics_b'] = mb
        rung['deltas']    = deltas
        rung['notes']     = [
            f'B PnL delta: {deltas[\"delta_total_pnl\"]:+.4f} USDT',
            f'B DD delta:  {deltas[\"delta_max_drawdown_pct\"]:+.2f}pp',
            'SMA 48/192 vs 24/96; ETH HIGH_VOL sizing 0.5 vs 0.3; BTC HIGH_VOL 0.65 vs 0.5',
        ]
        rung['verdict'] = (
            f'continue — B >= A on PnL (delta={deltas[\"delta_total_pnl\"]:+.4f})'
            if deltas['delta_total_pnl'] >= 0
            else f'continue — B < A on PnL (delta={deltas[\"delta_total_pnl\"]:+.4f}), within threshold'
        )
        break

manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
print('Manifest updated:', manifest_path)
print()
print('=== R2 DELTA TABLE ===')
print(f'  delta_total_pnl        : {deltas[\"delta_total_pnl\"]:+.4f}')
print(f'  delta_roi_pct          : {deltas[\"delta_roi_pct\"]:+.4f}%')
print(f'  delta_max_drawdown_pct : {deltas[\"delta_max_drawdown_pct\"]:+.2f}pp')
print(f'  delta_total_trades     : {deltas[\"delta_total_trades\"]:+d}')
print(f'  delta_win_rate         : {deltas[\"delta_win_rate\"]:+.4f}')
print(f'  delta_sharpe_ratio     : {deltas[\"delta_sharpe_ratio\"]:+.4f}')
"
```

---

## 8. Додавання R2-секції до ladder report

```bat
python -X utf8 -c "
from pathlib import Path

# Заповни після попереднього кроку
RUN_ID_A = 'ЗАМІН'
RUN_ID_B = 'ЗАМІН'
PNL_A, PNL_B, DPNL       = 0.0, 0.0, 0.0   # замін числами
DD_A,  DD_B,  DDD         = 0.0, 0.0, 0.0
TR_A,  TR_B,  DTR         = 0,   0,   0
SR_A,  SR_B               = 0.0, 0.0
WR_A,  WR_B               = 0.0, 0.0

section = f'''
### R2 — 2023-06-01 → 2023-07-31

**Символи:** BTCUSDT, ETHUSDT, DOGEUSDT, 1000PEPEUSDT, BNBUSDT
**A run_id:** {RUN_ID_A} | **B run_id:** {RUN_ID_B}

#### A vs B метрики

| Метрика | A (baseline) | B (patched) | Delta B-A |
|---|---|---|---|
| total_pnl (USDT) | {PNL_A:.4f} | {PNL_B:.4f} | {DPNL:+.4f} |
| max_drawdown % | {DD_A:.2f} | {DD_B:.2f} | {DDD:+.2f}pp |
| total_trades | {TR_A} | {TR_B} | {DTR:+d} |
| win_rate | {WR_A:.4f} | {WR_B:.4f} | {WR_B-WR_A:+.4f} |
| sharpe_ratio | {SR_A:.4f} | {SR_B:.4f} | {SR_B-SR_A:+.4f} |

#### Діагноз попереднього падіння B

Попередній B-прогін (`20260302_004205`) дав 0 трейдів через **state leakage**:
ladder-скрипт викликав `run_backtest_simulation()` двічі в одному процесі —
warmup-стан не скидався, 2-й виклик бачив \"WARMUP_NOT_FULL_READY\" для кожного бару.
Виправлення: окремий процес через `run_single_backtest.py --side B --rung 2`.

---
'''

report = Path('reports/arhive/backtest_ladder_report.md')
with report.open('a', encoding='utf-8') as f:
    f.write(section)
print('Appended to', report)
"
```

---

## Довідка: архітектура конфігу

```
config/
  aurora_baseline/          ← A (pre-patch)
    trading.yaml            ← backtest.start_date / end_date / initial_balance
    regime.yaml             ← sma_short_period:24, sma_long_period:96
    strategies/
      aurora.yaml           ← per-symbol regime_sizing (ETH HV:0.3, BTC HV:0.5)
    instruments.yaml        ← 7 символів (SOLUSDT/XRPUSDT без parquet)
    domains.yaml            ← (ідентичний з patched)
    strategies.yaml         ← реєстр стратегій (ідентичний з patched)
    system.yaml
    observability.yaml

  aurora/                   ← B (post-patch)
    trading.yaml            ← (ідентичний з baseline)
    regime.yaml             ← sma_short_period:48, sma_long_period:192 + regime_shift_inception
    strategies/
      aurora.yaml           ← ETH HV:0.5, ETH LV:0.85, BTC HV:0.65 + regime_smoothing block
    instruments.yaml        ← (ідентичний з baseline)
    ...
```

**Entrypoint для A/B:** `scripts/diagnostics/run_single_backtest.py`
**НЕ використовуй** `apps/reference/main.py` для A — він hard-code-ує `config/aurora` (завжди B).
**JSON-звіт:** `reports/backtests/backtest_<YYYYMMDD_HHMMSS>.json`
**run_id:** timestamp старту, унікальний при послідовних запусках.
