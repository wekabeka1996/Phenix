# MeanReversionHandler Hardening — План виправлення та тестування

Дата: 2025-12-23

Ціль: прибрати **неоднозначності активації**, **помилкові лічильники барів**, **silent-pass**, і підсилити контракт/логування для `EVT:STRATEGY_SIGNAL_PRODUCED`.

Файл у фокусі: [apps/reference/domains/decision_making/mean_reversion_handler.py](apps/reference/domains/decision_making/mean_reversion_handler.py)

---

## 0) Evidence (що підтверджено кодом)

1) **Коментар vs реальність активації**
- `_get_mr_assigned_symbols()` коментує: “assigned OR enabled=True”, але `_parse_config()` робить **assignment ∩ enabled assets** і ще й **fail-closed** якщо assigned та `enabled=false`.

2) **Лічильники “bars_completed/neutral_bars” рахуються по тиках**
- `bars_completed += 1` інкрементиться на кожному тіку при `st.bars` не пустому.
- `neutral_bars += 1` інкрементиться на кожному тіку з `signal.is_signal == False`.

3) **Докстрінг каже “emit EVT:TRADE_INTENT_PROPOSED”, а реально емісія `EVT:STRATEGY_SIGNAL_PRODUCED`.**

4) **Silent-pass присутній**
- `except Exception: pass` в логуванні бару.
- outer exceptions логуються через `debug` без `exc_info=True`.

5) **Тік з `price<=0` не дропається**
- `price` парситься через `or 0` і передається в стратегію.

6) **Regime встановлюється двома шляхами**
- На `EVT:REGIME_DETECTED` і на кожному тіку через параметр `regime`.

7) **Timestamp normalization — евристика, не винесена в pure-функцію і не тестована**

---

## 1) Цілі та інваріанти

### I-A: SSOT для активації
- **SSOT = `strategies_registry.assignments`**.
- `mean_reversion.enabled` — лише global kill-switch (може заборонити, але **не активує без assignment**).

### I-B: Tick validity
- Тік з `timestamp_ms <= 0` → drop + counter.
- Тік з `price <= 0` → drop + counter.
- Out-of-order `timestamp_ms < last_ts_ms` → drop + counter.

### I-C: Bar counters мають бути “per closed bar”, не “per tick”
- `bars_completed` інкрементиться **рівно 1 раз** на кожен новий бар.
- `neutral_bars` інкрементиться **рівно 1 раз** на кожен новий бар, якщо за цей бар сигнал “не actionable” (мінімальне визначення нижче).

### I-D: No silent-pass
- Жоден `except Exception` не має бути `pass`.
- Мінімум: `logger.warning(..., exc_info=True)` + counter.

### I-E: Event contract
- `EVT:STRATEGY_SIGNAL_PRODUCED` payload має включати `schema_version: 1`.

---

## 2) Рішення по неоднозначностях (фіксуємо наперед)

### 2.1 Обираємо варіант SSOT активації
Рекомендований варіант (A): **assignment-only SSOT**.
- Якщо MR не assigned — handler не активний (навіть якщо `enabled=true`).
- Якщо MR assigned, але `mean_reversion.enabled=false` — **fail-closed** (як зараз), але дока/коментарі мають це відображати.

### 2.2 Визначення “neutral_bars”
Найпростіша й детермінована інтерпретація (без переробки стратегії):
- При переході на новий бар (новий `bar.end_ts_ms`) інкрементити `neutral_bars`, якщо **останній сигнал, який повернувся на цьому тіку, не actionable** (`signal.is_signal == False`).
- Це не ідеально математично, але принаймні стає “per bar”, а не “per tick”, і детерміновано тестується.

Якщо захочеш точніше (по факту закриття бару) — тоді потрібен явний callback/стан зі стратегії про “bar_closed” або повернення інформації з resampler.

---

## 3) План змін в коді (Implementation)

### P0 — обов’язково

#### P0-1: Вирівняти доки/коментарі під реальний SSOT
- Оновити docstring класу та `_get_mr_assigned_symbols()`:
  - прибрати “OR enabled=True” і описати: **SSOT assignments**, `enabled` — kill-switch.
- Оновити фразу про подію: вказати `EVT:STRATEGY_SIGNAL_PRODUCED`.

#### P0-2: Виправити лічильники барів
- Додати поле стану: `self._last_counted_bar_end_ts_ms: Dict[str, int] = {}`.
- У `_on_market_tick()` після `st = strat.get_state(symbol)`:
  - якщо `st.bars` порожній → нічого.
  - `bar_end = st.bars[-1].end_ts_ms`
  - якщо `bar_end` != `self._last_counted_bar_end_ts_ms.get(symbol)`:
    - `self._stats["bars_completed"] += 1`
    - (опційно) `if not signal.is_signal: self._stats["neutral_bars"] += 1`
    - `self._last_counted_bar_end_ts_ms[symbol] = bar_end`

#### P0-3: Tick validation (price)
- Після парсингу `price` додати:
  - якщо `price <= 0`: `ticks_dropped_invalid_price += 1`, лог `MR_TICK_DROP` з reason `invalid_price`, return.

#### P0-4: Заборонити silent-pass
- Замість `except Exception: pass`:
  - `self._stats["bar_logging_errors"] += 1` (додати лічильник)
  - `self.logger.warning("...", exc_info=True)` або `self.mlog.warning(..., exc_info=True)`

#### P0-5: Outer exception logging
- У `_on_market_tick()` і `_on_regime_detected()` перейти з `debug` на `warning` + `exc_info=True`.

### P1 — бажано, але після P0

#### P1-1: Regime wiring — один шлях
- Вибір (простий): **тільки через `_per_symbol_regime`**.
  - У `on_tick()` прибрати `if regime: strategy.set_regime(...)`.
  - Regime встановлюється в `_on_regime_detected()` через `on_regime()`.

#### P1-2: Нормалізація timestamp винести в pure-функцію
- Додати приватну функцію (module-level): `def normalize_ts_ms(raw: Any) -> int`.
- Покрити unit-тестами секунди→мс, строки, None, 0.

#### P1-3: Додати `schema_version` в payload
- В `_emit_signal()` додати: `"schema_version": 1`.

---

## 4) План тестування

### 4.1 Unit tests (обов’язково)

Файл: `tests/domains/decision_making/test_mean_reversion_handler_hardening_v1.py` (новий)

1) **SSOT activation: assignments-only**
- `test_mr_activation_assigned_enabled_true_ok`:
  - MR assigned + `mean_reversion.enabled=true` + asset enabled → handler.enabled True.
- `test_mr_activation_assigned_enabled_false_raises`:
  - MR assigned + `mean_reversion.enabled=false` → ValueError.
- `test_mr_no_assignments_enabled_true_stays_disabled`:
  - no assignments + `enabled=true` → handler.enabled False (визначена поведінка).

2) **Tick parsing: drop invalid price**
- `test_tick_drops_invalid_price_le_zero`:
  - Подати tick з `price=0` або `price=None` → counter `ticks_dropped_invalid_price` + не викликається `strategy.on_tick`.

3) **Tick parsing: timestamp normalization**
- `test_normalize_ts_ms_seconds_to_ms` (якщо винесемо функцію):
  - `1700000000` → `1700000000000`.
- `test_normalize_ts_ms_ms_unchanged`:
  - `1700000000000` → unchanged.

4) **Out-of-order drop**
- `test_out_of_order_tick_dropped_and_counter_incremented`:
  - два тики, другий з меншим ts → drop + counter.

5) **Bars completed counted once per bar**
- `test_bars_completed_counts_once_per_bar_end_ts`:
  - підмінити `strategy.get_state(symbol)` так, щоб `st.bars[-1].end_ts_ms` не змінювався на кількох тиках → `bars_completed` збільшується 1 раз.
  - потім змінити `end_ts_ms` → `bars_completed` +1.

6) **No silent-pass**
- `test_bar_logging_exception_increments_counter_and_logs_warning`:
  - змусити `strategy.get_state()` кинути exception → не має бути `pass`, має бути counter `bar_logging_errors` + warning.

### 4.2 Integration tests (мінімум)

Файл: `tests/integration/test_mean_reversion_handler_event_contract_v1.py` (новий)

1) **Emits EVT:STRATEGY_SIGNAL_PRODUCED with schema_version**
- Побудувати handler з mock FSMCore (`emit`/`listen`), підкласти strategy, яка повертає `MRSignal(is_signal=True, ...)`.
- Прогнати `_on_market_tick()`.
- Assert: `fsm.emit` викликано з `EVT:STRATEGY_SIGNAL_PRODUCED` і `payload.schema_version == 1`.

2) **Tick invalid price does not emit signal**
- Tick з `price=0` → `fsm.emit` НЕ викликано.

---

## 5) Definition of Done (DoD)

- DoD-1: Документація/коментарі відповідають реальним подіям і SSOT-правилу.
- DoD-2: `bars_completed` і `neutral_bars` рахуються **per bar** (unit).
- DoD-3: `price<=0` дропається (unit) + лічильник.
- DoD-4: Жодного `except: pass` — замінено на warning+counter (unit).
- DoD-5: Payload сигналу містить `schema_version: 1` (integration).
- DoD-6: `pytest -q tests/domains/decision_making/... tests/integration/...` зелений.

---

## 6) Rollout / Перевірка в логах (швидкий smoke)

- Після деплою/рестарту:
  - `domain_mean_reversion`: бачимо `MR_INIT`, `MR_REGISTER`.
  - На валідних тиках: `MR_TICK`.
  - На невалідних: `MR_TICK_DROP` з `invalid_price` / `missing_ts` / `out_of_order`.
  - На сигналі: `EVT:STRATEGY_SIGNAL_PRODUCED` з `schema_version=1`.

---

## 7) Ризики

- Зміна поведінки `neutral_bars`: буде “per bar”, а не “per tick” — це зламає старі метрики, але виправляє семантику.
- Якщо DecisionMaking або інші компоненти покладались на `price=0` як “missing” — тепер буде drop; це бажано, але треба врахувати в аналітиці.
