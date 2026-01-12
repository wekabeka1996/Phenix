# TIMER-AUDIT-002 — Aurora timers forensic (v1)

Дата: 2026-01-12

## 1) Таблиця: таймери / timebase / state / блокуючі reason_code

| Таймер / gate | Джерело часу | Де зберігається стан | Блокує через `reason_code` |
|---|---|---|---|
| Reentry cooldown (anti-ping-pong) | `monotonic_fn()` (seconds) | `SymbolState.last_exit_timestamp` | `REENTRY_COOLDOWN` (EVT:STRATEGY_DECISION_BLOCKED) |
| Flip/exit min duration (holding period / anti-churn) | `monotonic_fn()` (seconds) | `SymbolState.entry_timestamp`, `SymbolState.position_side` | `HOLDING_PERIOD_ACTIVE` (EVT:STRATEGY_DECISION_BLOCKED) |
| Regime inertia confirm window (anti-churn) | `monotonic_fn()` (seconds) | `SymbolState.regime_raw_change_ts`, `SymbolState.regime_effective` | (не блокує напряму; впливає на multiplier для таймерів) |
| Side-bias window (penalty window) | `wall_time_fn()` (seconds) | `SymbolState.buy_timestamps` / `sell_timestamps` | (не блокує напряму) |
| Signal timestamp (event payload) | `wall_time_fn()` → `ts_ms` | `SymbolState.last_signal_ts_ms` | — |

## 2) Чому `monotonic()` для таймерів і `wall time` для логів/ts

- **Timer-для-обмежень** (cooldown/min-duration/confirm-window) має бути на **монотонному часі**, щоб:
  - стрибки системного годинника (NTP/VM suspend/resume/manual change) не скорочували/не подовжували вікна;
  - порівняння `$\Delta t$` було детермінованим.
- **`ts_ms` в подіях/логах** має бути на **wall time (epoch)**, щоб:
  - корелювати з іншими сервісами/логами/біржовими timestamps;
  - не змішувати "відносний" таймерний час із абсолютним.

## 3) Доказова база (prod-risk oriented)

### Додані/оновлені тести

- Guardrail: no mutation of scoring result при suppressed flip
  - [tests/domains/decision_making/test_timers_flip_min_duration_v1.py](../tests/domains/decision_making/test_timers_flip_min_duration_v1.py)
- Мінімальний інтеграційний контракт таймерів (реальний config stub, DI `monotonic_fn`)
  - [tests/domains/decision_making/test_aurora_timer_integration_contract_v1.py](../tests/domains/decision_making/test_aurora_timer_integration_contract_v1.py)

### Команди запуску

Точкові:

- `pytest -q tests/domains/decision_making/test_timers_reentry_cooldown_v1.py`
- `pytest -q tests/domains/decision_making/test_timers_flip_min_duration_v1.py`
- `pytest -q tests/domains/decision_making/test_anti_churn_time_multipliers_v1.py`
- `pytest -q tests/domains/decision_making/test_aurora_timer_integration_contract_v1.py`

Мінімальний регрес:

- `pytest -q -m "not legacy" --maxfail=0`

### Очікувані reason_code / why_chain (факти)

- Reentry cooldown блокує entry: `reason_code=REENTRY_COOLDOWN`.
- Holding period блокує soft flip/exit: `reason_code=HOLDING_PERIOD_ACTIVE`, why_chain містить `HOLDING_PERIOD`.

## 4) Mutation-free scoring result (forensic висновок)

- `AuroraHandler` більше **не мутує** об’єкт `ScoringResult` (включно з `side/score/thr_*`).
- Для forced-hold використовується локальне `effective_side`, яке прокидується в emission/gates без зміни input object.
