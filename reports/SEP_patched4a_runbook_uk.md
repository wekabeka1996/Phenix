# Runbook: SEP patched4a — Чистий прогін September-only
**Baseline:** B3 (patched3) + patched4a guard | **Дата підготовки:** 2026-03-07
**Ціль:** Isolated September 2023 без 1000PEPEUSDT, BTC HIGH_VOL 0.20, BTC LOW_VOL 0.25

---

## 1. Передумови (Preconditions)

```powershell
# 1. Перейти в корінь репозиторію
cd C:\Users\wekab\Music\Phenix

# 2. Перевірити Python
python -V
# Очікується: Python 3.10+ (або 3.11+)

# 3. Активувати venv (якщо ще не активовано)
.venv\Scripts\Activate.ps1
```

**Важливо:**
- Запускати лише **один прогін за раз** (два виклики в одному процесі → state leakage, 0 trades на другому)
- **Не використовувати `| head`** (обривання stdout ламає pipe на Windows)
- Переконатися, що `reports/backtests/` існує:

```powershell
New-Item -ItemType Directory -Force -Path reports/backtests
```

---

## 2. Валідація конфігу перед запуском

Виконати щоб переконатися, що patched4a застосований коректно:

```powershell
python -X utf8 -c "import yaml; s=yaml.safe_load(open('config/aurora/strategies/aurora.yaml',encoding='utf-8').read()); r=yaml.safe_load(open('config/aurora/regime.yaml',encoding='utf-8').read()); a=s['aurora']['assets']; print('PEPE enabled:', a['1000PEPEUSDT']['enabled']); print('BTC allowed_regimes:', a['BTCUSDT']['allowed_regimes']); print('BTC HIGH_VOL sizing:', a['BTCUSDT']['regime_sizing']['HIGH_VOLATILITY']); print('BTC LOW_VOL sizing:', a['BTCUSDT']['regime_sizing']['LOW_VOLATILITY']); print('SMA short/long:', r['models']['sma_trend']['sma_short_period'], '/', r['models']['sma_trend']['sma_long_period'])"
```

**Очікуваний вивід:**
```
PEPE enabled: False
BTC allowed_regimes: ['TREND_UP', 'TREND_DOWN', 'HIGH_VOLATILITY', 'MEAN_REVERSION', 'LOW_VOLATILITY']
BTC HIGH_VOL sizing: 0.2
BTC LOW_VOL sizing: 0.25
SMA short/long: 48 / 192
```

Якщо будь-яке значення відрізняється — **не запускати бектест**, перевірити `config/aurora/strategies/aurora.yaml`.

---

## 3. Команда запуску — September-only patched4a

```powershell
python scripts/diagnostics/run_single_backtest.py --side B --start 2023-09-01 --end 2023-09-30 2>&1 | Tee-Object reports/backtests/SEP_patched4a_stdout.txt
```

Після завершення перевірити exit code:
```powershell
echo "Exit code: $LASTEXITCODE"
```
Очікується: `Exit code: 0`

---

## 4. Де шукати результати

| Артефакт | Шлях |
|---|---|
| JSON-звіт з метриками | `reports/backtests/backtest_<run_id>.json` |
| Stdout/stderr лог | `reports/backtests/SEP_patched4a_stdout.txt` |
| Детальний лог Aurora | `logs/backtest/aurora_core.log` або `logs/` |
| JSONL-лог угод | `logs/backtest/*.jsonl` (якщо налаштовано) |

`<run_id>` — timestamp-based ID, видний в stdout в кінці прогону в рядку `run_id : ...`

Знайти останній JSON-звіт:
```powershell
Get-ChildItem reports/backtests/backtest_*.json | Sort-Object LastWriteTime | Select-Object -Last 1
```

---

## 5. Що перевірити після завершення

Відкрити `reports/backtests/backtest_<run_id>.json` і знайти наступні поля:

| Метрика | Шлях у JSON | Коментар |
|---|---|---|
| `total_pnl` | `metrics.total_pnl` | Тільки якщо немає open positions! |
| `roi_pct` | `metrics.roi_pct` | % від initial balance |
| `max_drawdown_pct` | `metrics.max_drawdown * 100` | У долях → *100 = % |
| `total_trades` | `metrics.total_trades` | Очікується ~60–100 (без PEPE) |
| `win_rate` | `metrics.win_rate` | 0.0–1.0 (не % — це частка) |
| `sharpe_ratio` | `metrics.sharpe_ratio` | Може бути null |
| `end_balance` | `metrics.end_balance` | USDT, initial=1000.0 |

**Перевірка на артефакти:**
```powershell
python -X utf8 -c "
import json, pathlib, glob
files = sorted(glob.glob('reports/backtests/backtest_*.json'), key=lambda f: pathlib.Path(f).stat().st_mtime)
data = json.loads(pathlib.Path(files[-1]).read_text(encoding='utf-8'))
trades = data.get('trades', [])
open_pos = [t for t in trades if t.get('exit') is None or t.get('close_reason') is None]
print('file:', pathlib.Path(files[-1]).name)
print('total_pnl:', data.get('metrics', {}).get('total_pnl'))
print('total_trades:', data.get('metrics', {}).get('total_trades'))
print('win_rate:', data.get('metrics', {}).get('win_rate'))
print('end_balance:', data.get('metrics', {}).get('end_balance'))
print('open_at_end:', len(open_pos))
syms = {}
for t in trades:
    if t.get('close_reason'):
        s = t.get('symbol','?')
        syms[s] = syms.get(s, 0) + t.get('pnl_usdt_net', 0)
print('pnl_by_symbol:', syms)
"
```

**PEPE-перевірка (критична):** у `pnl_by_symbol` рядок `1000PEPEUSDT` **не повинен з'являтися взагалі**. Якщо з'явився — патч не застосований, зупинити аналіз і перевірити `enabled: false`.

---

## 6. Шаблон звіту — що скинути назад після прогону

```
=== SEP patched4a РЕЗУЛЬТАТ ===
run_id        :
period        : 2023-09-01 → 2023-09-30
side          : B (patched4a)
total_pnl     :          USDT
roi_pct       :          %
max_drawdown  :          %
total_trades  :
win_rate      :
sharpe_ratio  :
end_balance   :          USDT
open_at_end   :          (має бути 0 або 1 незначна позиція)

pnl_by_symbol:
  BTCUSDT  :          USDT
  ETHUSDT  :          USDT
  BNBUSDT  :          USDT
  1000PEPEUSDT: (має бути відсутній або 0)

exit code: 0
```

---

## 7. Патч-дельта (patched4a vs patched3)

| Параметр | B3 (patched3) | patched4a | Обґрунтування |
|---|---|---|---|
| `1000PEPEUSDT.enabled` | true | **false** | Sep closed: −662 USDT, ev/t=−4.27, sim artifact |
| `BTCUSDT.regime_sizing.HIGH_VOLATILITY` | 0.50 | **0.20** | R4_CUM: 86% SL rate, n=42, −103 USDT |
| `BTCUSDT.regime_sizing.LOW_VOLATILITY` | 0.75 | **0.25** | R4_CUM: 65% SL rate, n=54, −159 USDT |
| ETH/BNB/SMA/TP/SL | без змін | без змін | не чіпаємо до наступного патчу |

---

## 8. Файли overlay (документація змін)

| Файл | Призначення |
|---|---|
| `config/overlays/patched4a_sep_only.yaml` | Window документація (Sep 2023-09-01..09-30) |
| `config/overlays/patched4a_strategy_guard.yaml` | BEFORE/AFTER diff, валідація, revert інструкції |
| `config/aurora/strategies/aurora.yaml` | **Реальний конфіг** (зміни застосовані inline) |

---

*Runbook підготовлено: 2026-03-07 | Aurora/Phenix patched4a Sep-only experiment*
