# 🔴 MD-AMR V1.1 — Архітектурний та Кількісний Аудит (Red Team)

**Дата:** 2026-03-04  
**Аудитор:** Principal Quant Researcher / Chief Auditor  
**Об'єкт:** MD-AMR V1.1 (Multi-Dimensional Asymmetric Mean Reversion)  
**Скоуп:** 8 файлів, ~1 740 LOC

---

## Domain 1: Quantitative Math & Crypto Edge

### 🔴 RED-1.1 — Згладжений OHLC канал: SMA вразливий до flash crashes

**Файли:** [indicators.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/indicators.py#L63-L96), [md_amr_strategy.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/md_amr_strategy.py#L188-L196)

Канал будується через [compute_sma()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/indicators.py#45-61) — простий арифметичний середній. SMA **однаково зважує** свічку з flash crash і нормальну свічку. Один flash crash (Binance wicks -15..20% за 1 свічку) гарантовано **деформує `avg_low_12` на 12 барів** = 3 години.

**Наслідок:** Стратегія бачить аномально низький `avg_low_12` → score `long_score` стає >= `thr_buy` → **хибний ENTRY LONG прямо під час дампу**.

```python
# md_amr_strategy.py L232:
long_score = max(0.0, (avg_low - close_now) / band) * self.hysteresis_mult
# При flash crash: avg_low різко падає, але close_now вже відновився → 
# (avg_low - close_now) < 0 → long_score = 0 ← насправді ОК для цього напрямку
# АЛЕ: наступний бар, close повертається до нормалі, avg_low ще занижений:
# (avg_low - close_now) > 0 → ХИБНИЙ LONG ENTRY
```

> [!WARNING]
> Після flash crash вікно SMA "пам'ятає" екстрему 12 барів, генеруючи хибні сигнали.

---

### 🔴 RED-1.2 — Z-Score ATR не обробляє price gaps

**Файл:** [md_amr_strategy.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/md_amr_strategy.py#L115-L121)

```python
def compute_atr_zscore(self, atr_current, atr_ma_n, atr_std_n):
    if atr_std_n <= eps:
        return 0.0  # ← Z-Score = 0 при gap!
    return (atr_current - atr_ma_n) / max(atr_std_n, eps)
```

**Проблема:** Після тривалого руху вбік (atr_std ≈ 0), раптовий gap (наприклад, делістинг, регуляторна новина) створює `atr_std_n ≈ 0`, і [compute_atr_zscore](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/md_amr_strategy.py#115-122) повертає [0.0](file:///c:/Users/user/Music/Phenix/=0.110.0) замість екстремально високого значення. Dampening **НЕ спрацьовує** → ваги d1/h1 не зменшуються → стратегія трактує хаос як нормальний ринок.

Зверніть також увагу: коли `atr_std_n` тільки-но почне зростати після стисканої фази, перший такий бар дасть z-score = [(atr_current - atr_ma_n) / tiny_std](file:///c:/Users/user/Music/Phenix/tools/md_amr_optuna.py#109-136) → **нескінченно великий z-score**, що різко домпить `d1` і `h1` — протилежна крайність.

---

### 🟡 YELLOW-1.3 — Fee-aware scale-out: математика комісій не врахо вує round-trip

**Файл:** [md_amr_strategy.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/md_amr_strategy.py#L158-L166)

```python
fees = float(cost_ctx.get("fee_bps", self.fee_bps)) / 10_000.0
slippage_buffer = float(cost_ctx.get("slippage_buffer_bps", self.slippage_buffer_bps)) / 10_000.0
# ...
if reached_target and expected_edge_after_costs > (fees + slippage_buffer):
    return "PARTIAL_CLOSE", "FEE_AWARE_SCALEOUT"
```

**4 bps fee_bps + 2 bps slippage = 6 bps одностороннього кошту.** Але на Binance Futures:
- **Entry side:** вже заплачено ~4 bps (або менше для Maker)
- **Exit side:** ще ~4 bps

Round-trip = ~8 bps + 2 bps slippage = **10 bps**, а не 6 bps. Формула недооцінює costs на ~40%. Для scale-out partial close це ще гірше, тому що partial close = окремий ордер зі своїм fee.

**Backtest** також використовує [(fee_bps + slippage_buffer_bps) / 10_000.0](file:///c:/Users/user/Music/Phenix/tools/md_amr_optuna.py#109-136) (vector_backtest L182), але **PnL обчислюється БЕЗ вирахування комісій** (L194, L203) — тільки raw price delta. Це означає Optuna оптимізує метрики **без fee deduction**.

---

### 🟡 YELLOW-1.4 — Байєсівська деформація порогів: безумовна при dir_score→0

**Файл:** [md_amr_strategy.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/md_amr_strategy.py#L134-L145)

При `dir_score ≈ 0` (ринок у хопу), `bias ≈ 0`, `thr_buy ≈ thr_sell ≈ thr_base`. Це нормально. **Але:** при `dir_score → ±1.0` та `alpha = 0.25`:
- `bias = 0.25 * 1.0 = 0.25`
- `thr_buy = 0.55 - 0.25 = 0.30` (дуже низький поріг)

Поріг 0.30 для входу — дуже агресивний. У парі з `hysteresis_mult = 1.20` це може призвести до надмірної кількості трейдів в трендових ринках.

---

## Domain 2: State Management & Event-Driven Architecture

### 🔴 RED-2.1 — Race condition: Kill-Switch vs Zombie-Timeout

**Файл:** [md_amr_strategy.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/md_amr_strategy.py#L147-L167)

```python
def resolve_exit_action(self, *, position_ctx, score_ctx, cost_ctx):
    if conf_ratio < self.conf_min:
        return "FULL_CLOSE", "EDGE_GONE_KILLSWITCH"      # ← пріоритет 1
    if bars_held > self.max_hold_bars:
        return "FULL_CLOSE", "ZOMBIE_POSITION_TIMEOUT"    # ← пріоритет 2
    if reached_target and expected_edge_after_costs > (...):
        return "PARTIAL_CLOSE", "FEE_AWARE_SCALEOUT"      # ← пріоритет 3
    return None, None
```

Порядок `if-elif` визначає жорсткий пріоритет. **Конфлікту в одному тику немає**, оскільки перемагає перший if. 

Однак, є прихований **state leak**: коли Kill-Switch спрацьовує та емітить `FULL_CLOSE` через handler → FSM, **handler НЕ скидає `self._bars_held[symbol]`** (тільки [_on_trade_executed](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#169-196) робить це за рахунок qty → 0). Якщо execution layer затримає підтвердження (partial fill або network latency), на **наступному барі** `bars_held` інкрементується ще раз (L289), і Kill-Switch емітить **другий** `FULL_CLOSE` з тим самим rid (md5 від того ж бару). Дублікат ордера.

---

### 🟡 YELLOW-2.2 — Warmup: відсутній механізм дедуплікації

**Файл:** [md_amr_handler.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L268-L271)

```python
if warmup.get("full_ready") is not True:
    rid = self._rid(symbol=symbol, side="BUY", ts_ms=bar_close_ts, intent_kind="DEFER")
    self._register_defer(symbol, rid, ["warmup.full_ready"], now_ms)
    return
```

Handler довіряє зовнішньому `warmup.full_ready` полю, але **не верифікує** чи достатньо барів в `strategy.closes` deque. Якщо warmup layer помилково виставив `full_ready=True` раніше ніж зібрано 96 барів + 64 atr_stats_window, стратегія поверне `DEFER` на кожному барі, поки деки не заповняться, але **не логує це як warmup failure**.

Явної дедуплікації `timestamp <= last_hydrated_timestamp` для REST vs WebSocket **нема у handler'і** — це або делегується іншому шару, або просто відсутнє. Якщо REST-кеш містить бар, який потім приходить через WS — **бар додається двічі** в deque стратегії → спотворення SMA/ATR.

---

### 🔴 RED-2.3 — Position tracking drift: handler vs exchange

**Файл:** [md_amr_handler.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L169-L195)

```python
def _on_trade_executed(self, event):
    # ...
    if qty > 0 and side == "sell":
        qty = -qty
    if qty < 0 and side == "buy":
        qty = -qty
    prev = self._position_qty.get(symbol, Decimal("0"))
    now = prev + qty
```

Handler **локально акумулює** позицію зі сліпих `EVT:TRADE_EXECUTED` подій. Якщо будь-який execution event:
1. Загублений (WebSocket reconnect)
2. Прийшов з неправильним `side` (опечатка у downstream)
3. Прийшов двічі (retry logic)

…`self._position_qty` **дрейфує** від реального стану на біржі. Немає ніякого `reconciliation` або periodic sync з exchange position. Це може призвести до:
- Стратегія думає: `qty_signed = 0` (flat), тоді як на біржі є відкрита позиція → **orphaned position**, ніхто не ставить SL/TP
- Стратегія думає: `qty_signed > 0`, на біржі flat → хибний FULL_CLOSE → reject від біржі

---

### ✅ GREEN-2.4 — Fail-Closed Integrity: NaN → DEFER

Strategy core коректно перевіряє кожен вхідний параметр:
- L180-181: `if not all([bar_open, bar_high, bar_low, bar_close])` → DEFER
- L195-196: `if channel is None` → DEFER
- L204-205: `if atr_dec is None` → DEFER
- L209-210: `if len(self.atr_history) < self.atr_stats_window` → DEFER
- L219-220: `if dir_components is None` → DEFER

Backtest vector engine (L125): `if np.any(~np.isfinite(fields))` → skip row.

Це **правильна** fail-closed поведінка. Жодного crash-шляху через NaN.

---

## Domain 3: Backtest Integrity

### 🔴 RED-3.1 — Lookahead Bias: вхід та вихід на тому ж close[i]

**Файл:** [md_amr_vector_backtest.py](file:///c:/Users/user/Music/Phenix/tools/md_amr_vector_backtest.py#L111-L212)

```python
for i in range(len(s)):
    # ...
    if pos == 0:
        if score >= thr_buy:
            pos = 1
            entry = close[i]         # ← відкрив по close[i]
            # ...
    else:
        bars_held += 1
        # exit logic uses close[i]
```

**Entry відбувається по `close[i]` поточної свічки.** Це означає: бектестер "бачить" close поточної свічки, обраховує score з нього і тут же входить по ній. У реальності:
- Сигнал може бути сформований тільки **після закриття** 15-хв свічки
- Реальний вхід буде по ціні **наступної** свічки (open[i+1]) або гірше

Це **класичний Lookahead Bias** який завищує результати на ~2-5 bps per trade.

Стратегія live ([md_amr_strategy.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/md_amr_strategy.py)) також використовує `bar_close` як `price_ref` — але в live це подія "бар закрився", і виконання буде ПІСЛЯ неї на ринковій ціні. Бектест не моделює цю затримку.

---

### 🔴 RED-3.2 — PnL обчислюється БЕЗ комісій

**Файл:** [md_amr_vector_backtest.py](file:///c:/Users/user/Music/Phenix/tools/md_amr_vector_backtest.py#L192-L207)

```python
# PARTIAL close:
pnl = pos * ((close[i] - entry) / max(entry, 1e-9)) * pos_size * close_frac
net_profit += pnl  # ← raw PnL, NO fee deduction

# FULL close:
pnl = pos * ((close[i] - entry) / max(entry, 1e-9)) * pos_size
net_profit += pnl  # ← raw PnL, NO fee deduction
```

Costs [(fee_bps + slippage_buffer_bps) / 10_000.0](file:///c:/Users/user/Music/Phenix/tools/md_amr_optuna.py#109-136) обчислюються (L182), але використовуються **тільки** для порівняння `expected_edge_after_costs > costs` при вирішенні partial close. Фактичний PnL **не зменшується на fee**.

При `fee_bps=4.0` на Binance, кожний round-trip trade = ~8 bps. Якщо стратегія робить 100 трейдів, це **0.8% нерахованих втрат**. Calmar ratio завищений.

> [!CAUTION]
> **Optuna оптимізує цільову функцію (Calmar × log(trades)) на PnL БЕЗ комісій.  
> Знайдені "оптимальні" параметри будуть over-trade (більше trades = вищий score, а fee не каже).**

---

### 🟡 YELLOW-3.3 — In-Sample Warmup: неявний, без явного відкидання

**Файли:** [md_amr_optuna.py](file:///c:/Users/user/Music/Phenix/tools/md_amr_optuna.py#L65-L83), [md_amr_vector_backtest.py](file:///c:/Users/user/Music/Phenix/tools/md_amr_vector_backtest.py#L125-L127)

Warmup "відкидання перших 96 барів" **НЕ реалізований явно**. Замість цього backtest покладається на `np.isfinite()` check (L125-127) — перші рядки, де `atr_ma_n` або `dir_d1` = NaN (через rolling window), автоматично пропускаються як `skipped_rows`.

Це **працює**, але:
1. Кількість skipped збережена в `result.skipped_rows`, але Optuna **не використовує** це для пенальті
2. Якщо дані починаються "ідеально" (з pre-computed features), warmup bypass → стратегія починає торгувати на першому барі → bias від початкових умов

---

### 🟡 YELLOW-3.4 — Нема Out-of-Sample (OOS) split в Optuna

**Файл:** [md_amr_optuna.py](file:///c:/Users/user/Music/Phenix/tools/md_amr_optuna.py#L98-L106)

```python
df = load_recorder_900(recorder_dir, symbols=symbols, start=start, end=end)
df_features = compute_md_amr_features(df)
study.optimize(make_objective(df_features), n_trials=n_trials)
```

Весь датасет йде **одним блоком** через [make_objective](file:///c:/Users/user/Music/Phenix/tools/md_amr_optuna.py#65-84). Нема Walk-Forward, нема IS/OOS split. 100% in-sample optimization → **гарантований overfitting**.

---

## Domain 4: Execution Risk

### 🔴 RED-4.1 — Latency NOT modeled, entry_order_type = LIMIT + GTX

**Файл:** [md_amr.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/strategies/md_amr.yaml#L30-L35)

```yaml
execution:
  entry_order_type: "LIMIT"
  entry_tif: "GTX"       # ← Post-Only guarantee
  exit_order_type: "MARKET"
```

`GTX` = "Good Till Crossing" = Post-Only. Ордер буде **відхилений**, якщо він одразу матчнеться (тобто якщо limit price ≥ best ask для BUY). У 15-хв стратегії:
- Сигнал генерується на close бару
- Ціна `price_ref` = close бару
- Якщо за час latency (~50-500ms) ціна не змінилась, LIMIT BUY @ close = best ask → **GTX REJECT**

Handler не обробляє GTX reject scenario — немає retry logic, fallback до MARKET, або price offset.

---

### 🟡 YELLOW-4.2 — Partial Fills: handler не враховує

**Файл:** [md_amr_handler.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L169-L195)

[_on_trade_executed](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#169-196) акумулює кожен fill event (`prev + qty`). Scale-out intent каже "продай 50%", але:
1. Якщо ордер частково виконується (наприклад, 70% з 50%)
2. Залишок скасовується або не виконується
3. Handler коректно акумулює часткові fills...

**...АЛЕ:** `self._bars_held` **не скидається** при partial fill, тільки коли `abs(now) < 1e-9`. Якщо partial close зменшив позицію, але не закрив повністю, `bars_held` продовжує рости → хибний ZOMBIE_TIMEOUT на наступному барі.

---

### 🟡 YELLOW-4.3 — MD5-based rid: collision probability

**Файл:** [md_amr_handler.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L197-L199)

```python
def _rid(self, *, symbol, side, ts_ms, intent_kind):
    raw = f"{symbol}:{side}:{ts_ms}:{intent_kind}:md_amr"
    return f"mdamr-{hashlib.md5(raw.encode()).hexdigest()[:16]}"
```

MD5 обрізаний до 16 hex (64 bit). При ~100 трейдах/день × 5 символів × 365 днів = ~182k rids/рік. Birthday paradox collision probability = `n² / 2^65` ≈ negligible. **Прийнятно**, але MD5 = deprecated for any security context.

---

## 📊 Оцінка (Scoring)

| Критерій | Бал | Обґрунтування |
|---|:---:|---|
| **Robustness** (стійкість до крипто-шуму) | **5/10** | SMA канал вразливий до wicks; Z-Score ламається при gap-after-squeeze; dampening має edge cases |
| **Architecture** (ізоляція та State Management) | **6/10** | Чиста ізоляція handler/strategy; але position tracking = blind accumulation без reconciliation |
| **Backtest Validity** (відсутність Lookahead Bias) | **3/10** | Lookahead bias (entry @ close[i]); PnL без fee; нема OOS split; Optuna overfits |
| **Risk Management** (fail-closed adherence) | **7/10** | NaN → DEFER правильно; exit priority table чітка; але GTX reject не handled, bars_held drift |
| **OVERALL SCORE** | **5.25/10** | Backtest results **не можуть бути підставою для live deployment** без виправлення RED-3.1 та RED-3.2 |

---

## 🔧 Actionable Fixes (Перед запуском Optuna)

### Fix 1: Fee Deduction в Backtest (RED-3.2) — CRITICAL

```python
# md_amr_vector_backtest.py, після L194 та L203:
# Замінити:
pnl = pos * ((close[i] - entry) / max(entry, 1e-9)) * pos_size * close_frac

# На:
raw_return = pos * ((close[i] - entry) / max(entry, 1e-9))
fee_cost = 2.0 * costs  # round-trip: entry + exit
pnl = (raw_return - fee_cost) * pos_size * close_frac
```

Аналогічно для FULL close (L203):
```python
raw_return = pos * ((close[i] - entry) / max(entry, 1e-9))
fee_cost = 2.0 * costs
pnl = (raw_return - fee_cost) * pos_size
```

І для end-of-data close (L215):
```python
raw_return = pos * ((close[-1] - entry) / max(entry, 1e-9))
pnl = (raw_return - 2.0 * costs) * pos_size
```

---

### Fix 2: Entry on Next Bar Open (RED-3.1) — CRITICAL

```python
# md_amr_vector_backtest.py, заміна entry logic:
if pos == 0:
    if score >= thr_buy:
        # Defer entry to next bar
        pending_entry = ("LONG", i)
    elif score <= -thr_sell:
        pending_entry = ("SHORT", i)

# На початку наступної ітерації (i+1):
if pending_entry is not None:
    direction, signal_bar = pending_entry
    pos = 1 if direction == "LONG" else -1
    entry = close[i]  # або open[i] якщо доступний
    bars_held = 0
    total_trades += 1
    pending_entry = None
```

> [!TIP]
> Ідеально замість `close[i]` використовувати `open[i+1]` (якщо стовбець open доступний) або `close[i] * (1 + slippage_multiplier)`.

---

### Fix 3: Z-Score clamp для gap-after-squeeze (RED-1.2)

```python
# md_amr_strategy.py, L121:
# Замінити:
return (atr_current - atr_ma_n) / max(atr_std_n, eps)

# На:
raw_z = (atr_current - atr_ma_n) / max(atr_std_n, eps)
return max(-10.0, min(10.0, raw_z))  # clamp extreme Z-Scores
```

---

### Fix 4: Position Reconciliation Guard (RED-2.3)

Додати periodic reconciliation:

```python
# md_amr_handler.py — новий метод:
def _reconcile_position(self, symbol: str, exchange_qty: Decimal) -> None:
    """Called externally (e.g., every 5 min) with actual exchange position."""
    local_qty = self._position_qty.get(symbol, Decimal("0"))
    if abs(local_qty - exchange_qty) > Decimal("1e-6"):
        self.mlog.warning(
            "MD_AMR_POSITION_DRIFT symbol=%s local=%s exchange=%s",
            symbol, local_qty, exchange_qty,
        )
        self._position_qty[symbol] = exchange_qty
        if abs(exchange_qty) < Decimal("1e-9"):
            self._bars_held[symbol] = 0
```

---

### Fix 5: OOS Split в Optuna (YELLOW-3.4)

```python
# md_amr_optuna.py — додати IS/OOS split:
def run_study(...):
    df = load_recorder_900(...)
    df_features = compute_md_amr_features(df)
    
    # 70/30 temporal split
    timestamps = df_features["timestamp"].unique()
    cutoff_idx = int(len(timestamps) * 0.7)
    cutoff_ts = timestamps[cutoff_idx]
    
    df_is = df_features[df_features["timestamp"] < cutoff_ts]
    df_oos = df_features[df_features["timestamp"] >= cutoff_ts]
    
    study.optimize(make_objective(df_is), n_trials=n_trials)
    
    # Validate best params on OOS
    best_params = study.best_trial.params
    oos_result = run_vector_backtest(df_oos, params=best_params)
    print(f"OOS Calmar: {oos_result.calmar_ratio}")
```
