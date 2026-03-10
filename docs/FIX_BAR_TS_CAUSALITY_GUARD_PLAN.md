# FIX: BAR-TS-CAUSALITY-GUARD — Bar Timestamp vs Anchor Causality Guard

**Статус:** PLAN
**Пріоритет:** P0 CRITICAL
**Дата:** 2026-02-09
**Автор:** Copilot Agent
**Scope:** `apps/reference/domains/feature_engineering/feature_engineering.py`
**Registry verb:** `CMD:PROCESS_STRATEGY` (owner: `strategies`, status: `active`)

---

## 0. Суть проблеми (Executive Summary)

**CMD:PROCESS_STRATEGY повністю заблоковано для ВСІХ символів.**
За 12+ годин live-сесії: **83 rejections, 0 successful emissions.**
Стратегія Aurora не отримує жодного сигналу. Система alive but **inert** — жоден ордер не може бути відкритий.

Кореневий дефект: causality guard порівнює `bar_close_ts` з `anchor_last_ts_ms`, що **за визначенням** завжди спрацьовує для bar events, бо tick-рівневі anchor обновлення випереджають bar timestamp.

---

## 1. Діагностика: чому anchor_from_future завжди True для bar events

### 1.1. Data flow (поточний, дефектний)

```
EVT:BAR_CLOSED
  └─ on_bar_closed()
       ├─ bar_ts = bar_data["end_ts_ms"]       # наприклад 10:30:00.000
       ├─ bar_tick = {"ts": bar_ts, ...}        # synthetic tick з ts = bar_close
       └─ _calculate_and_emit_features_for_tf(symbol, tf_sec=300, current_tick=bar_tick, ...)
            ├─ current_ts_ms = current_tick["ts"]   # = bar_close = 10:30:00.000
            ├─ _compute_macro_sync(current_ts_ms=10:30:00.000)
            │    └─ anchor_ts = _anchor_last_ts_ms["BTCUSDT"]  # = 10:30:00.150 (live tick)
            │    └─ anchor_ts > current_ts_ms → TRUE → macro_sync_ready = False ❌
            ├─ macro_resid causality guard
            │    └─ btc_anchor_ts > current_ts_ms → TRUE → macro_resid_ready = False ❌
            ├─ warmup: ready_map["macro_sync"] = False, ready_map["macro_resid"] = False
            ├─ compute_warmup_full_ready → False
            └─ CMD:PROCESS_STRATEGY Gate 3 (enforcement_mode=fail_fast) → REJECTED ❌
```

### 1.2. Чому це завжди спрацьовує

1. **Bar закривається** о 10:30:00.000 → `bar_tick["ts"] = end_ts_ms = 10:30:00.000`
2. **Live ticks** продовжують прибувати паралельно (WebSocket): BTC tick о 10:30:00.050, ETH tick о 10:30:00.080
3. Anchor ticks **оновлюють** `_anchor_last_ts_ms["BTCUSDT"] = 10:30:00.050`
4. Коли `on_bar_closed` обробляє бар:
   - `current_ts_ms = 10:30:00.000` (Historic: момент закриття бару)
   - `anchor_ts = 10:30:00.050` (Live: останній anchor tick)
   - **`anchor_ts > current_ts_ms` → True** → causality violation → block

Це **не каузальне порушення** — це архітектурна невідповідність між Historic-часом (bar_close) і Live-часом (anchor ticks).

### 1.3. Додаткові причини блокування

Крім `anchor_from_future`, в reasons зʼявляється `invalid_value_type` — це наслідковий ефект feature sanity firewall, який спрацьовує коли macro features повертають neutral через rejected causality guard.

---

## 2. Обгрунтування: чому це архітектурна помилка

### 2.1. Семантика часу: bar events vs tick events

| Аспект | Tick event | Bar event |
|--------|-----------|-----------|
| `current_ts_ms` | Exchange tick timestamp (мікросекундна точність) | Bar close timestamp (кратний timeframe) |
| Семантика | "Стан ринку в момент тіка" | "Агрегований стан за період" |
| Часовий контекст | Real-time, монотонно зростає | Historic: завжди ≤ now(), може бути на bars×tf_sec назад |
| Anchor порівняння | Коректне: tick → anchor каузальність | **Некоректне**: bar_close < live_anchor_tick завжди |

### 2.2. Призначення causality guard (FIX 2, P0)

Оригінальний guard (line 362–371, line 827–837) розроблявся для **tick-level** features:

> "Never mix anchor updates from the future (relative to this tick) into macro features."

Це правильна логіка для тіків: якщо BTCUSDT tick з 10:30:00.100 прибув раніше ніж DOGEUSDT tick з 10:30:00.050, ми не повинні використовувати "майбутній" BTC anchor для DOGE-features.

Але для **bar events** ця логіка не застосовна:
- Bar вже закрився. Всі дані, що існують на момент обробки, є **легітимними** для аналізу
- `end_ts_ms` — це конвенційний час кінця бару, а не "поточний момент обробки"
- Anchor data, що прибула після `bar_close` але до обробки — це **додаткова ліквідна інформація**, а не каузальне порушення

### 2.3. Proof: BTC блокує САМ СЕБЕ

BTC є anchor (`anchors: ["BTCUSDT", "ETHUSDT"]` в `domains.yaml`). При обробці bar event для BTCUSDT:
- `current_ts_ms = bar_close_ts` (наприклад, 10:30:00.000)
- `_anchor_last_ts_ms["BTCUSDT"]` = останній BTC tick (10:30:00.150)
- BTC's OWN anchor ts > BTC's bar_close_ts → block

**BTC блокує себе через власний tick, що прибув після закриття його ж бару** — це абсурдна каузальність.

### 2.4. Мінімальний вплив vs максимальна шкода

- **Вплив усунення guard для bars:** Zero — bar features обчислюються з OHLCV бару, macro_sync/macro_resid використовують лише *historical* anchor price buffers, які вже коректні
- **Шкода від guard:** Повна зупинка `CMD:PROCESS_STRATEGY` = повна зупинка стратегії = нуль торгівлі

---

## 3. План імплементації

### 3.1. Підхід: Wall-clock injection для bar events

**Принцип:** При виклику `_calculate_and_emit_features_for_tf` для bar events передавати `wall_ts_ms = int(time.time() * 1000)` як поточний момент обробки, а не `bar_close_ts`.

Bar features — це "стан на момент обробки бару", а не "стан на момент закриття бару".

### 3.2. Зміна 1: `on_bar_closed()` — inject wall_ts_ms в bar_tick

**Файл:** `apps/reference/domains/feature_engineering/feature_engineering.py`
**Метод:** `on_bar_closed()` (line ~625)

**Що:** Додати в `bar_tick` поле `wall_ts_ms` = поточний wallclock. Це зберігає `bar_tick["ts"] = bar_close_ts` для features (delta_price, time_diff), але дозволяє causality guard використовувати правильний час.

```python
# BEFORE (дефектний):
bar_tick = {
    "symbol": symbol,
    "ts": bar_ts,
    "price": str(close_price),
    ...
}

# AFTER (фікс):
bar_tick = {
    "symbol": symbol,
    "ts": bar_ts,
    "price": str(close_price),
    # BAR-TS-CAUSALITY-FIX: wall-clock для causality guards (bar_close_ts < live anchor)
    "wall_ts_ms": int(time.time() * 1000),
    ...
}
```

### 3.3. Зміна 2: `_calculate_and_emit_features_for_tf()` — використовувати wall_ts_ms для causality

**Файл:** `apps/reference/domains/feature_engineering/feature_engineering.py`
**Метод:** `_calculate_and_emit_features_for_tf()` (line ~670)

**Що:** Винести окремий `causality_ts_ms` — для tick events = `current_ts_ms`, для bar events = `wall_ts_ms`.

```python
# Line ~690-692 (ПІСЛЯ парсингу current_tick):
current_ts_ms = int((current_tick["ts"] if "ts" in current_tick else 0) or 0)

# BAR-TS-CAUSALITY-FIX: For bar events, use wall-clock for anchor causality checks.
# Bar's end_ts_ms is ALWAYS behind live anchor ticks → false "anchor_from_future".
# Wall-clock represents actual processing moment → correct causality reference.
causality_ts_ms = int(current_tick.get("wall_ts_ms") or current_ts_ms)
```

### 3.4. Зміна 3: `_compute_macro_sync()` — параметризувати causality timestamp

**Файл:** `apps/reference/domains/feature_engineering/feature_engineering.py`
**Метод:** `_compute_macro_sync()` (line ~348)

**Що:** Додати optional параметр `causality_ts_ms` для causality guard, зберігаючи `current_ts_ms` для обчислень.

```python
# BEFORE:
def _compute_macro_sync(self, symbol: str, *, current_ts_ms: int) -> decimal.Decimal:
    ...
    for anchor in self.cfg.macro_sync_anchors:
        anchor_ts = int((self._anchor_last_ts_ms.get(anchor, 0) or 0))
        if anchor_ts > 0 and anchor_ts > int(current_ts_ms):    # ← дефект

# AFTER:
def _compute_macro_sync(self, symbol: str, *, current_ts_ms: int, causality_ts_ms: int | None = None) -> decimal.Decimal:
    ...
    check_ts = causality_ts_ms if causality_ts_ms is not None else current_ts_ms
    for anchor in self.cfg.macro_sync_anchors:
        anchor_ts = int((self._anchor_last_ts_ms.get(anchor, 0) or 0))
        if anchor_ts > 0 and anchor_ts > int(check_ts):         # ← фікс
```

### 3.5. Зміна 4: macro_resid causality guard — аналогічний фікс

**Файл:** `apps/reference/domains/feature_engineering/feature_engineering.py`
**Рядки:** ~827–837

**Що:** Використовувати `causality_ts_ms` замість `current_ts_ms` в macro_resid guard.

```python
# BEFORE:
btc_anchor_ts = int((self._anchor_last_ts_ms.get("BTCUSDT", 0) or 0))
if btc_anchor_ts > 0 and btc_anchor_ts > int(current_ts_ms):    # ← дефект

# AFTER:
btc_anchor_ts = int((self._anchor_last_ts_ms.get("BTCUSDT", 0) or 0))
if btc_anchor_ts > 0 and btc_anchor_ts > int(causality_ts_ms):  # ← фікс
```

### 3.6. Зміна 5: Прокинути causality_ts_ms через виклики

В `_calculate_and_emit_features_for_tf()`:

```python
# Line ~820 (macro_sync виклик):
# BEFORE:
features["macro_sync"] = str(self._compute_macro_sync(
    symbol, current_ts_ms=int(current_ts_ms)))

# AFTER:
features["macro_sync"] = str(self._compute_macro_sync(
    symbol, current_ts_ms=int(current_ts_ms), causality_ts_ms=int(causality_ts_ms)))

# Line ~831 (macro_resid guard):
# Вже використовує causality_ts_ms (Зміна 4)
```

### 3.7. Повний список змін (diff outline)

| # | Файл | Метод | Рядки | Тип зміни |
|---|------|-------|-------|-----------|
| 1 | feature_engineering.py | `on_bar_closed()` | ~588 | Додати `wall_ts_ms` в `bar_tick` |
| 2 | feature_engineering.py | `_calculate_and_emit_features_for_tf()` | ~690 | Витягти `causality_ts_ms` |
| 3 | feature_engineering.py | `_compute_macro_sync()` | ~348 | Додати параметр `causality_ts_ms` |
| 4 | feature_engineering.py | `_compute_macro_sync()` | ~366 | Використати `check_ts` для guard |
| 5 | feature_engineering.py | `_calculate_and_emit_features_for_tf()` | ~820 | Прокинути `causality_ts_ms` в macro_sync |
| 6 | feature_engineering.py | `_calculate_and_emit_features_for_tf()` | ~831 | Використати `causality_ts_ms` в macro_resid guard |

---

## 4. Інваріанти, що зберігаються

| Інваріант | Статус після фіксу |
|-----------|-------------------|
| Tick-level causality guard | ✅ Не змінюється (wall_ts_ms = None → fallback на current_ts_ms) |
| bar_close_ts для delta_price | ✅ Не змінюється (current_ts_ms = bar_close_ts) |
| bar_close_ts для time_diff | ✅ Не змінюється |
| warmup.full_ready обчислення | ✅ Коректне (macro_sync/macro_resid не будуть постійно blocked) |
| bar_ttl_ms / staleness check | ✅ Продовжує працювати з bar_close_ts |
| Features payload ts field | ✅ Залишається bar_close_ts |
| Macro_sync resampler timing | ✅ current_ts_ms=bar_close_ts — правильний hour-based lookup |
| CMD:PROCESS_STRATEGY payload | ✅ bar_close_ts без змін |
| Regime injection в CMD | ✅ Без змін |

---

## 5. План тестування

### 5.1. Unit тести (нові)

#### Test 1: `test_bar_event_anchor_causality_uses_wall_clock`

**Сценарій:** Bar closes at T=10:30:00.000, anchor tick has T=10:30:00.150.
**Перевіряємо:** `macro_sync_ready=True`, `macro_resid_ready=True`, causality guard НЕ спрацьовує.
**Як:** Mock `time.time()` → 10:30:01.000, створити bar_tick з `wall_ts_ms`.

```python
def test_bar_event_anchor_causality_uses_wall_clock():
    """BAR-TS-CAUSALITY-FIX: Bar events use wall-clock for causality, not bar_close_ts."""
    fe = create_fe_instance(...)

    bar_close_ts = 1000000000  # bar closed here
    anchor_tick_ts = 1000000150  # anchor tick 150ms after bar close
    wall_ts = 1000001000  # 1s after bar close (processing moment)

    fe._anchor_last_ts_ms["BTCUSDT"] = anchor_tick_ts

    bar_tick = {"ts": bar_close_ts, "wall_ts_ms": wall_ts, "price": "100", ...}

    # Should NOT trigger anchor_from_future
    result = fe._compute_macro_sync("DOGEUSDT", current_ts_ms=bar_close_ts, causality_ts_ms=wall_ts)
    assert hot.macro_sync_ready is True  # was False before fix
```

#### Test 2: `test_tick_event_anchor_causality_preserved`

**Сценарій:** Tick for DOGEUSDT at T=100, anchor BTC at T=200.
**Перевіряємо:** causality guard **спрацьовує** для tick events (backward compat).

```python
def test_tick_event_anchor_causality_preserved():
    """Tick-level causality guard MUST still block future anchors."""
    fe = create_fe_instance(...)
    fe._anchor_last_ts_ms["BTCUSDT"] = 200

    # No wall_ts_ms → causality_ts_ms falls back to current_ts_ms
    tick = {"ts": 100, "price": "100", ...}
    result = fe._compute_macro_sync("DOGEUSDT", current_ts_ms=100)
    assert hot.macro_sync_ready is False  # Causality preserved
```

#### Test 3: `test_cmd_process_strategy_emitted_after_fix`

**Сценарій:** Full bar event pipeline з realistic timing.
**Перевіряємо:** `CMD:PROCESS_STRATEGY` емітується (не rejected).

#### Test 4: `test_wall_ts_ms_not_injected_for_tick_features`

**Сценарій:** Tick event → `_calculate_and_emit_features()` → `_calculate_and_emit_features_for_tf(tf_sec=0)`.
**Перевіряємо:** `current_tick` не має `wall_ts_ms`, `causality_ts_ms = current_ts_ms`.

### 5.2. Регресійні тести (існуючі, повинні пройти)

| Тест | Файл | Що перевіряє |
|------|------|-------------|
| `test_macro_sync_stale_anchor_returns_neutral` | tests/runtime/test_task24_feature_engineering_correctness.py | Stale anchor → neutral (TTL check не змінюється) |
| E2E macro_sync async | tests/e2e/test_s2_macro_sync_async.py | Stale anchor TTL fallback |
| CMD:PROCESS_STRATEGY gates | tests/integration/test_fe_emits_cmd_process_strategy.py | Gate 1-5 логіка |
| EP-01.1 volatility | tests/integration/test_ep01_volatility_obi.py | Bar volatility features |
| Tick FE no-bar gate | tests/integration/test_tick_fe_no_bar_gate.py | tf_sec=0 контракт |

### 5.3. Integration тест (новий)

#### Test 5: `test_bar_event_e2e_cmd_process_strategy_full_pipeline`

**Сценарій:** Повний pipeline: warmup ticks → anchor ticks → bar_closed → CMD:PROCESS_STRATEGY.
**Перевіряємо:** CMD емітується з повним payload + warmup.full_ready=True.

### 5.4. Smoke test (live)

```bash
# 1. Застосувати фікс
# 2. Запустити систему
# 3. Дочекатися першого bar close (5 хвилин)
# 4. Перевірити в логах:
grep "Emitted CMD:PROCESS_STRATEGY" logs/domain_feature_engineering.log
# Очікуємо: повідомлення для ВСІХ символів (BTCUSDT, ETHUSDT, SOLUSDT, DOGEUSDT, XRPUSDT)

# 5. Перевірити відсутність anchor_from_future для bar events:
grep "anchor_from_future" logs/domain_feature_engineering.log
# Очікуємо: ТІЛЬКИ tick-level events (якщо є), НЕ bar-level
```

---

## 6. Proof: чому фікс знімає блок

### 6.1. Логічний proof

Блокуючий ланцюг (поточний):
```
bar_close_ts < live_anchor_ts (завжди True)
  → macro_sync_ready = False
  → macro_resid_ready = False
  → ready_map["macro_sync"] = False, ready_map["macro_resid"] = False
  → compute_warmup_full_ready = False (macro_sync/macro_resid в declared_keys)
  → CMD:PROCESS_STRATEGY Gate 3: warmup not full_ready → REJECTED
```

Після фіксу:
```
causality_ts_ms = wall_ts_ms (= time.time() * 1000)
  → wall_ts_ms > live_anchor_ts (завжди True — wall-clock = now)
  → causality check: anchor_ts < wall_ts_ms → guard NOT triggered
  → macro_sync_ready = True (якщо data sufficient)
  → macro_resid_ready = True (якщо data sufficient)
  → ready_map["macro_sync"] = True, ready_map["macro_resid"] = True
  → compute_warmup_full_ready = True (всі declared_keys ready)
  → CMD:PROCESS_STRATEGY Gate 3: warmup full_ready → PASS ✅
```

### 6.2. Чому wall-clock завжди > anchor_ts

- `wall_ts_ms = int(time.time() * 1000)` — це поточний момент обробки
- `anchor_ts` — це timestamp останнього прийнятого anchor тіка
- Тік не може бути з майбутнього відносно wall-clock (WebSocket latency > 0)
- Ergo: `wall_ts_ms ≥ anchor_ts` завжди (з точністю до NTP drift, який ≪ bar_tf_sec)

### 6.3. Edge case: clock skew

Якщо NTP desync > 0 і exchange clock впереді на Δ:
- `anchor_ts` може бути на Δ мс "далі" ніж `wall_ts_ms`
- Для bar events: Δ << 300000ms (5m bar) → нерелевантно
- Для tick events: causality guard залишається БЕЗ ЗМІН (wall_ts_ms не використовується)

---

## 7. Ризики та мітигація

| Ризик | Імовірність | Мітигація |
|-------|------------|-----------|
| Wall-clock рассинхрон з exchange | Низька (NTP) | Tick causality guard не змінено; bar tolerance >>  clock skew |
| Macro features некоректні з "майбутніми" anchors | Нуль | Anchor price buffers заповнюються monotonically — "майбутній" тік лише додає свіжішу ціну |
| Backward compatibility break | Нуль | Tick pipeline не змінено. `causality_ts_ms=None` → fallback |
| Інші компоненти читають wall_ts_ms | Нуль | Нове поле, не конфліктує з існуючими |
| Test flake через time.time() | Середня | Використати `@patch('time.time')` в тестах |

---

## 8. Зв'язок із другим питанням (Regime Detector)

**Після фіксу CMD:PROCESS_STRATEGY:**
- Стратегія Aurora отримуватиме bar events → приймає рішення → відкриває/закриває позиції
- Regime detector **вже працює коректно** (див. лог: BTC отримав LOW_VOLATILITY, інші в UNCERTAIN)
- Режим inject-иться в CMD:PROCESS_STRATEGY payload через `self.last_regime`
- Після фіксу стратегія зможе інтерпретувати режим для кожного символу

SOL/ETH/DOGE/XRP залишаються в UNCERTAIN бо ринкові умови не задовольняють threshold-и — це **не баг**, це відображення реальності (див. аналіз в попередній відповіді).

---

## 9. Порядок виконання

1. **Імплементація змін 1-6** (один файл, ~15 рядків netto)
2. **Написати тести 1-5**
3. **Запустити існуючі тести:**
   ```bash
   pytest -q tests/vfoundation
   pytest -q tests/integration/test_fe_emits_cmd_process_strategy.py
   pytest -q tests/runtime/test_task24_feature_engineering_correctness.py
   pytest -q tests/integration/test_ep01_volatility_obi.py
   pytest -q tests/integration/test_tick_fe_no_bar_gate.py
   ```
4. **Deploy на live testnet** і перевірити smoke test (розділ 5.4)
5. **Моніторинг:** перші 30 хвилин (6 bar closes) — переконатися що CMD:PROCESS_STRATEGY емітується
