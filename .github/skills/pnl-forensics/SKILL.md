---
name: pnl-forensics
description: >
  Use for financial investigation of wallet/balance loss, ORDER_INTENT lifecycle forensics,
  position profitability/loss analysis, and capital drain investigation. Anchors to
  logs/order_log_v1.jsonl, logs/trade_lifecycle.jsonl, logs/features/<SYMBOL>.log,
  ops/wal/*.jsonl, and tools/forensics/, tools/backtest/backtest_summarize.py,
  tools/monitoring/extract_equity_free_usdt.py.
---

# PnL Forensics Skill

## Purpose
Проводити повне фінансове розслідування втрати коштів на гаманці системи.
Визначати причини збитків через аналіз повного ланцюга ORDER_INTENT → позиція → закриття,
із перехресним звіренням мікроструктури ринку з logs/features/<SYMBOL>.log.
Звіт виводиться **виключно українською мовою**.

## When to use
- Розслідування втрати коштів / зменшення балансу гаманця
- Аналіз подій ORDER_INTENT і чи вони активували позицію
- Дослідження прибутковості/збитковості торгових рішень
- Аналіз причин закриття позицій (TP/SL/TTL/NRR/policy/sidecar)
- Перевірка відповідності ринкових умов (features) та рішень системи
- Будь-який запит із ключовими словами: "гроші", "баланс", "збиток", "прибуток",
  "ORDER_INTENT", "втрата", "PnL", "фінансове розслідування", "позиція не відкрилась"

## When NOT to use
- Відлагодження коду без аналізу фінансового результату
- Зміни конфігурації без інциденту із втратою коштів
- Аналіз продуктивності алгоритму без прив'язки до реальних торгів

## Required inputs
- Часовий діапазон розслідування (або "всі доступні дані")
- Символ(и) торгової пари (або "всі символи")
- Опис аномалії (зменшення балансу, збиткові угоди, ордери без позиції тощо)

Якщо вхідні дані відсутні — вивести:
BLOCKED: missing <часовий діапазон>, <символ>, <опис аномалії>

## Evidence sources
| Джерело | Зміст |
|---------|-------|
| `logs/order_log_v1.jsonl` | ORDER_INTENT події (ExposureGuard, DecisionMaking, ExecPosFSM), DECISION_INTENT_REJECTED, NRR-коди |
| `logs/trade_lifecycle.jsonl` | Відкриття/закриття позицій, fill_price, fill_fees, close_reason |
| `logs/features/<SYMBOL>.log` | Мікроструктура ринку: obi, tfi, delta_price, spread_bps, pillar_sum, pillar_contribs |
| `ops/wal/*.jsonl` | WAL: TRADE_INTENT_PROPOSED / REJECTED по DecisionMaking |
| `logs/aurora_events.jsonl` | Aurora рішення та ваги сигналів |
| `logs/shadow_critical_event_journal_v1.jsonl` | Критичні події системи |
| `logs/regime_confidence_audit_v1.jsonl` | Аудит впевненості режиму |
| `apps/logs/order_guardian.log` | Order Guardian — захист від дублікатів |

## Tools (виконувати скриптами, не читати логи вручну)
| Скрипт | Призначення |
|--------|-------------|
| `tools/forensics/wal_intent_summary.py` | Підрахунок PROPOSED/REJECTED + virtual PnL по WAL |
| `tools/forensics/deep_wal_forensics.py` | Глибокий WAL: cross-ref із features і recorder |
| `tools/forensics/gate_effect_report.py` | Аналіз блокувань LOW_VOL_COST_SUPPRESS gate |
| `tools/forensics/entry_execution_report.py` | Аналіз виконання входів |
| `tools/forensics/entry_fill_audit.py` | Аудит цін fill |
| `tools/forensics/log_forensics_cancel_audit.py` | Аудит скасувань ордерів |
| `tools/forensics/extract_last_trades.py` | Остання торгова активність |
| `tools/forensics/position_policy_sidecar_validation.py` | Валідація рішень Sidecar |
| `tools/backtest/backtest_summarize.py` | PnL по режимах, close_reason розподіл |
| `tools/monitoring/extract_equity_free_usdt.py` | Трекінг балансу equity/free USDT |
| `tools/monitoring/analyze_wal.py` | WAL: деталі ордерів і трейдів |
| `tools/diagnostics/check_positions.py` | Поточні позиції + unrealized PnL |
| `tools/diagnostics/check_orders.py` | Відкриті ордери на біржі |
| `tools/diagnostics/log_audit.py` | Аудит логів |

## Deterministic procedure

### Фаза 0 — Попередній підрахунок (завжди першою)
```
python tools/forensics/wal_intent_summary.py --start <START> --end <END>
python tools/monitoring/extract_equity_free_usdt.py
```
Зафіксувати:
- Загальну кількість ORDER_INTENT подій по фазах (ExposureGuard / DecisionMaking / ExecPosFSM)
- Кількість DECISION_INTENT_REJECTED по NRR-кодах
- Поточний баланс equity та free USDT

### Фаза 1 — Кількісний аудит ORDER_INTENT
Виконати автоматизований підрахунок через jq або Python:
```bash
# Підрахунок по source_fsm
jq -r '.source_fsm // "unknown"' logs/order_log_v1.jsonl | sort | uniq -c | sort -rn

# Підрахунок REJECTED по NRR кодах
jq -r 'select(.event_type=="DECISION_INTENT_REJECTED") | .nrr_code // .metadata.deny_reason // "unknown"' \
  logs/order_log_v1.jsonl | sort | uniq -c | sort -rn
```
**Вивести**: таблицю підрахунку (не читати рядки вручну).

### Фаза 2 — Аналіз позицій: відкриття → закриття
Для кожного rid у trade_lifecycle.jsonl (по символах та часовому діапазону):
```bash
python tools/forensics/entry_execution_report.py
python tools/forensics/entry_fill_audit.py
```
Класифікувати кожну позицію:
- **Активована** (є fill_price, fill_ts_ms)
- **Відхилена** (status=REJECTED, reject_reason_code)
- **Orphaned** (fill без закриття, status=ORPHANED_TTL)

### Фаза 3 — Класифікація причин закриття позицій
Для кожної АКТИВОВАНОЇ позиції визначити `close_reason`:
| close_reason | Категорія | Вплив на PnL |
|---|---|---|
| `TP` | Take Profit спрацював | Потенційно прибуток |
| `SL` | Stop Loss спрацював | Зафіксований збиток |
| `TTL_EXPIRED_3600s` | Таймаут (1год) | Невизначено — потребує аналізу price delta |
| `CMD_OPEN_VALIDATION_FAIL` | Валідація провалилась | Збиток від комісії |
| `NRR-EXECUTION-REJECTED` | NRR на рівні виконання | Без позиції, тільки комісія резервування |
| `POSITION_DISAPPEARANCE_ATTRIBUTED` | Exchange-підтверджене закриття | Перевірити proof_source |

### Фаза 4 — Кросс-référence із feature_engineering
Для кожної позиції (відкриття + закриття):
1. Знайти відповідний запис у `logs/features/<SYMBOL>.log` за часовою міткою ±1 бар
2. Зафіксувати мікроструктуру ПЕРЕД відкриттям:
   - `obi` (order book imbalance), `tfi` (trade flow imbalance)
   - `delta_price`, `spread_bps`, `volatility_state`
   - `pillar_sum`, `pillar_strategist` (основний драйвер рішення)
3. Зафіксувати мікроструктуру В МОМЕНТ закриття (якщо доступна)
4. Оцінити: чи відповідали features логіці рішення системи?
   - pillar_sum > 0 при SHORT вході = суперечність
   - spread_bps > threshold при LIMIT = ризик unfilled
   - volatility_state = 0 при LOW_VOLATILITY = підтвердження режиму

```bash
python tools/forensics/deep_wal_forensics.py
```

### Фаза 5 — Розрахунок реалізованого PnL
Для кожної CLOSED позиції:
```
PnL_gross = (entry_price - close_price) * fill_qty  (SHORT)
            (close_price - entry_price) * fill_qty  (LONG)
PnL_net = PnL_gross - fill_fees
```
Агрегувати по:
- Символ
- close_reason категорія
- Режим (regime при відкритті)

```bash
python tools/backtest/backtest_summarize.py --report-path reports/backtests/
```

### Фаза 6 — Аналіз Sidecar та Policy
```bash
python tools/forensics/position_policy_sidecar_validation.py
```
Перевірити:
- POSITION_POLICY_SIDECAR_SUPPRESSED події — скільки сигналів пригнічено
- evaluation_mode: `phase1_recommendation_only` = рекомендація, не примусово
- startup_grace_active — чи діяв grace period

### Фаза 7 — Gate аналіз
```bash
python tools/forensics/gate_effect_report.py
```
Перевірити: чи LOW_VOL_COST_SUPPRESS заблокував прибуткові торги (rv_bps > cost_bps)?

### Фаза 8 — Хронологічна реконструкція
Побудувати послідовність подій у UTC для кожного дослідженого rid:
```
[ts] ORDER_INTENT (ExposureGuard) → reservation
[ts] ORDER_INTENT (DecisionMaking) → intent_proposed / REJECTED (NRR-xxx)
[ts] ORDER_INTENT (ExecPosFSM) → LIMIT_SUBMIT_TRACE
[ts] FILL → fill_price, fill_qty, fill_fees
[ts] CLOSE → close_reason, PnL
[ts] features snapshot → mікроструктура ринку
```

## Output
Використати output_template.md. **Звіт складати ВИКЛЮЧНО українською мовою.**

## Safety constraints
- Не змінювати логи чи звіти
- Не виконувати команди, що впливають на live-торгівлю
- Не спекулювати — лише факти з логів
- Помітити INFERRED / UNPROVEN коли докази відсутні

## Failure handling
Якщо необхідні артефакти відсутні:
BLOCKED: missing <точні шляхи>
