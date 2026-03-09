# Backtest Ladder — Інструкція ручного запуску

## Поточний стан

| Щабель | Сторона | Період | PnL | Угоди | Статус |
|--------|---------|--------|-----|-------|--------|
| R1 | A (baseline) | 2023-06 | +167.93 USDT | 200 | ✅ DONE |
| R1 | B (patched)  | 2023-06 | −72.83 USDT  | 208 | ✅ DONE |
| R2 | A (baseline) | 2023-06..07 | −78.63 USDT | 318 | ✅ DONE |
| R2 | B (patched)  | 2023-06..07 | — | — | ⏳ **NEXT** |
| R3–R10 | A + B | ... | — | — | ❌ потрібно перезапустити |

---

## Чому окремий скрипт (run_single_backtest.py)?

Виклик `run_backtest_simulation()` двічі в одному процесі спричиняє витік стану —
другий запуск видає 0 угод (warmup ніколи не очищається).

**Рішення:** кожен запуск — окремий Python-процес (один виклик на процес).

---

## Підготовка (одноразово)

```bash
# Відкрий термінал у корені проекту
cd C:\Users\wekab\Music\Phenix

# Активуй venv (якщо є)
# Windows:
.venv\Scripts\activate
# або:
venv\Scripts\activate
```

---

## Команди для кожного щабля

### Формат команди

```bash
# A-сторона (aurora_baseline — поточний прод, SMA 24/96)
python scripts/diagnostics/run_single_backtest.py --side A --rung <N>

# B-сторона (aurora — патч, SMA 48/192 + нові розміри)
python scripts/diagnostics/run_single_backtest.py --side B --rung <N>
```

> **ВАЖЛИВО:** кожна команда — в окремому терміналі АБО дочекайся завершення першої
> перед запуском другої. Ніколи не запускай A і B разом в одному сеансі interpreter.

---

## R2 — 2023-06 .. 2023-07

**A вже виконано** (`run_id=20260302_003943`, PnL=−78.63, trades=318).

```bash
# Запусти тільки B
python scripts/diagnostics/run_single_backtest.py --side B --rung 2
```

Після завершення — скопіюй рядок `RESULT SUMMARY` і надай мені.

---

## R3 — 2023-06 .. 2023-08

```bash
# Спочатку A (дочекайся завершення — ~5-15 хв)
python scripts/diagnostics/run_single_backtest.py --side A --rung 3

# Потім B (в новому терміналі або після завершення A)
python scripts/diagnostics/run_single_backtest.py --side B --rung 3
```

---

## R4 — 2023-06 .. 2023-09

```bash
python scripts/diagnostics/run_single_backtest.py --side A --rung 4
python scripts/diagnostics/run_single_backtest.py --side B --rung 4
```

---

## R5 — 2023-06 .. 2023-10

```bash
python scripts/diagnostics/run_single_backtest.py --side A --rung 5
python scripts/diagnostics/run_single_backtest.py --side B --rung 5
```

---

## R6 — 2023-06 .. 2023-11

```bash
python scripts/diagnostics/run_single_backtest.py --side A --rung 6
python scripts/diagnostics/run_single_backtest.py --side B --rung 6
```

---

## R7 — 2023-06 .. 2023-12

```bash
python scripts/diagnostics/run_single_backtest.py --side A --rung 7
python scripts/diagnostics/run_single_backtest.py --side B --rung 7
```

---

## R8 — 2023-06 .. 2024-01

```bash
python scripts/diagnostics/run_single_backtest.py --side A --rung 8
python scripts/diagnostics/run_single_backtest.py --side B --rung 8
```

---

## R9 — 2023-06 .. 2024-02

```bash
python scripts/diagnostics/run_single_backtest.py --side A --rung 9
python scripts/diagnostics/run_single_backtest.py --side B --rung 9
```

---

## R10 — 2023-06 .. 2024-03

```bash
python scripts/diagnostics/run_single_backtest.py --side A --rung 10
python scripts/diagnostics/run_single_backtest.py --side B --rung 10
```

---

## Що надавати після кожного запуску

Скрипт виведе блок `RESULT SUMMARY`. Скопіюй його цілком і надай мені, наприклад:

```
============================================================
  RESULT SUMMARY — side=B | rung=2
============================================================
  run_id        : 20260302_123456
  period        : 2023-06-01 → 2023-07-31
  total_pnl     : -45.2100 USDT
  roi_pct       : -4.5210%
  max_drawdown  : 8.34%
  total_trades  : 295
  win_rate      : 0.4800
  end_balance   : 954.7900 USDT
  sharpe_ratio  : 0.0520
  bar_count     : 17280
  total_fees    : 12.3400 USDT
============================================================
```

Або просто цифри — я сам розберу.

---

## Правило раннього зупинення (early-stop)

Зупиняємось якщо **2 щаблі поспіль** виконуються:
- B гірше ніж A на **>10% PnL** (ΔPnL < −10%)
- **ТА** B гірше ніж A на **>15% drawdown** (ΔDD > +15pp)

Я перевіряю це після кожного B-результату автоматично.

---

## Конфіг-відмінності A vs B

| Параметр | A (baseline) | B (patched) |
|----------|-------------|-------------|
| SMA short/long | 24/96 | 48/192 |
| BTC HIGH_VOL sizing | 0.50 | 0.65 |
| ETH HIGH_VOL sizing | 0.30 | 0.50 |
| ETH LOW_VOL sizing  | 1.00 | 0.85 |

Config dirs:
- A: `config/aurora_baseline/`
- B: `config/aurora/`

---

## Якщо виникає помилка

Якщо скрипт падає з помилкою — надай останні 20 рядків виводу. Найчастіша причина:
`sys.exit(1)` з `run_backtest_simulation()` → є виключення у логах.

Перевір:
```bash
# Знайди останній лог
ls -t logs/*.log | head -3
cat logs/aurora_core.log | tail -50
```

---

## Швидка перевірка поточного manifest

```bash
cat reports/backtest_ladder_manifest.json
```
