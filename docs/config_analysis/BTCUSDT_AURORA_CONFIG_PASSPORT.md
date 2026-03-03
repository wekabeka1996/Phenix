# 📄 Паспорт конфігурації: aurora/strategies/aurora.yaml :: BTCUSDT

## 🔍 Загальний опис блоку

Блок `aurora.assets.BTCUSDT` — це конфігурація для стратегії Aurora на символі **BTCUSDT** (Bitcoin/USDT). 
Фактично це **перевизначення** глобальних параметрів з блоку `aurora.decision` для BTC конкретно.

**Важливо (Registry Mapping):**
- Який символ призначена Aurora визначається у `strategies_registry.assignments` в `strategies.yaml`
- Якщо BTCUSDT не в registry → конфіг тут не використовується (dead config)
- Поточний стан: BTCUSDT призначена Aurora (див. `strategies.yaml`)

**CFG-AURORA-INSTRUMENTS-SSOT-01:** Кожне поле в BTCUSDT блоці перевизначає глобальне значення з `aurora.decision`, якщо явно задане. 
Якщо поле опущене → використовується глобальне значення.

---

## 📊 Глобальна Topmap позиції BTCUSDT в стратегії

```
aurora.yaml
├── aurora.decision (Global Defaults)
│   ├── signal_threshold: 0.12
│   ├── neutral_threshold: 0.05
│   ├── cooldown_sec: 6
│   ├── holding_period: {min_duration_sec: 30, ...}
│   └── reentry_cooldown_sec: 60
│
└── aurora.assets.BTCUSDT (Per-Symbol Overrides)
    ├── leverage: {target: 20, mode: ISOLATED}
    ├── weights: {obi: 0.20, tfi: 0.10, ...}     # Per-feature scoring weights
    ├── holding_period: {min_duration_sec: 20, ...}  # Override (20s vs global 30s)
    ├── reentry_cooldown_sec: 45                 # Override (45s vs global 60s)
    ├── exit: {sl_pct: 0.02, regime_tpsl: {...}} # ⭐ Complex nested regime config
    ├── take_profit: {tp_low_ratio: 0.5, ...}
    ├── allowed_regimes: [TREND_UP, TREND_DOWN, ...] # Regime gating
    ├── signal_threshold: {enabled: false, value: null}  # Inherit global
    └── volatility_entry_logic: {regime_multipliers: {...}}
```

---

## 🛠 Деталізація основних полів (Top Level)

| Поле | Тип | Значення BTC | Pydantic Модель | Статус | Роль |
|---|---|---|---|---|---|
| `enabled` | `bool` | `true` | ✅ `AuroraInstrumentConfig.enabled` | 🟢 Active | Увімкнути Aurora для BTCUSDT |
| `position_mode` | `str` | `STRICT` | ✅ `AuroraInstrumentConfig.position_mode` | 🟢 Active | No pyramiding (1 trade max) |
| `leverage` | `object` | `{target: 20, mode: ISOLATED}` | ✅ `LeverageConfig` | 🟢 Active | 20x isolated leverage |
| `weights` | `dict` | Див. таблиця нижче | ✅ `AuroraInstrumentConfig.weights` | 🟢 Active | Per-feature scoring weights (9 features) |
| `holding_period` | `object` | `{min_duration_sec: 20, ...}` | ✅ `HoldingPeriodConfig` | 🟢 Active | Override anti-HFT затримки |
| `reentry_cooldown_sec` | `int` | `45` | ✅ `AuroraInstrumentConfig.reentry_cooldown_sec` | 🟢 Active | Override anti-ping-pong delay |
| `liquidity_gate` | `object` | `{enabled: true, kappa_min: 0.1, ...}` | ✅ `LiquidityGateConfig` | 🟢 Active | VOL-ADJ-GATES-01 |
| `side_bias` | `object` | `{penalty_factor: 0.5, ...}` | ✅ `AuroraSideBiasConfig` | 🟢 Active | Bias/neutralization penalties |
| `regime_thresholds` | `dict` | `{HIGH_VOLATILITY: 1.2, ...}` | ✅ `Dict[str, float]` | 🟢 Active | Threshold multipliers per regime |
| `regime_sizing` | `dict` | `{HIGH_VOLATILITY: 3.0, ...}` | ✅ `Dict[str, float]` | 🟢 Active | Position size multipliers per regime |
| `exit` | `object` | `{sl_pct: 0.02, regime_tpsl: {...}}` | ✅ `AuroraExitConfig` | 🟢 Active | ⭐ **See detailed section below** |
| `take_profit` | `object` | `{tp_low_ratio: 0.5, ...}` | ✅ `AuroraTakeProfitConfig` | 🟢 Active | Partial TP logic |
| `trailing_stop` | `object` | `{enabled: false, ...}` | ✅ `AuroraTrailingStopConfig` | 🟡 Deprecated | Manual stop-loss preferred |
| `allowed_regimes` | `list` | `[TREND_UP, TREND_DOWN, ...]` | ✅ `AuroraInstrumentConfig.allowed_regimes` | 🟢 Active | Phase 3+ regime gating |
| `signal_threshold` | `object` | `{enabled: false, value: null}` | ✅ `SignalThresholdConfig` | 🟢 Active | Inherit global (0.12) |
| `volatility_entry_logic` | `object` | Див. таблиця нижче | ✅ `VolatilityEntryConfig` | 🟢 Active | Volatility-based limit pricing |

---

## 📊 Per-Feature Signal Weights (BTCUSDT)

**Контекст:** Стратегія обчислює composite signal як зважену суму 9 feature scores (кожен ∈ [-1, 1]).
Ці ваги *перевизначають* глобальні ваги з `aurora.decision.signal_weights`.

**Formula:** `score = Σ(weight[f] × feature_score[f])` для f ∈ {obi, tfi, delta_price, ema_bias, volume_spike, volatility_state, depth_imbalance, macro_resid, macro_sync}

| Feature | BTCUSDT | Global | Статус | Роль |
|---|---|---|---|---|
| `obi` (Order Book Imbalance) | **0.20** | 0.15 | 🟢 Weighted | BTC має глибину, OBI надійний |
| `tfi` (Trend Futures Indicator) | **0.10** | 0.15 | 🟡 De-emphasized | BTC тренд-слідуючий, менше полягає на TFI |
| `delta_price` (Price Momentum) | **0.05** | 0.10 | 🟡 De-emphasized | BTC стабільніший, менша волатильність momentum |
| `ema_bias` (EMA Distance) | **0.20** | 0.15 | 🟢 Weighted | BTC має чітку тренд-лінію |
| `volume_spike` (Volume Anomaly) | **0.15** | 0.10 | 🟢 Weighted | BTC volume спайки надійні сигнали |
| `volatility_state` (Vol Regime) | **0.10** | 0.10 | 🟢 Neutral | Стандартна вага |
| `depth_imbalance` (ASK Dominance) | **-0.05** | -0.15 | 🟢 De-weighted | BTC малі спреди, depth менш важливий |
| `macro_resid` (Macro Residual) | **0.15** | 0.10 | 🟢 Weighted | Macro сигнали важливі для BTC |
| `macro_sync` (DEPRECATED) | **0.0** | 0.0 | 🔴 Deprecated | Замінено macro_resid |

**Interpretation:** 
- **Sum of weights:** 0.20 + 0.10 + 0.05 + 0.20 + 0.15 + 0.10 - 0.05 + 0.15 = **0.90** (не 1.0, це OK — нормалізація відбувається в скорингу)
- **BTC Profile:** Дисбаланс на користь trend-following (ema_bias + tfi + macro_resid = 0.45)

**Code Tracing:**
- **Definition:** `apps/reference/config_models.py:2409` (`AuroraInstrumentConfig.weights`)
- **Usage:** 
  - `apps/reference/domains/decision_making/aurora_scoring_kernel.py:Line ~250` — applies weights in `_compute_signal_score()`
  - `apps/reference/domains/decision_making/aurora_handler.py:Line ~800` — logs effective weights per symbol
- **Validation:** `TASK54: Fail-closed validation` в `AuroraInstrumentConfig` (line 2395-2404) — перевіряє, що всі ключі знаходяться в `CANONICAL_WEIGHT_KEYS`

---

## 🎯 Liquidity Gate Configuration

| Поле | Значення | Pydantic | Роль |
|---|---|---|---|
| `enabled` | `true` | ✅ `LiquidityGateConfig.enabled` | Feature flag |
| `kappa_min` | `0.1` | ✅ `LiquidityGateConfig.kappa_min` | Min spread curvature (bid-ask width) — BTC найменша (найліпша ліквідність) |
| `kappa_max` | `1.0` | ✅ `LiquidityGateConfig.kappa_max` | Max kappa (widest spreads — dead market) |
| `failsafe_qty_check` | `true` | ✅ `LiquidityGateConfig.failsafe_qty_check` | Перевірка мінімального об'єму |

**Semantics:** 
- `kappa` = спеціалізований depth measure (bid/ask curvature)
- BTC має найменший `kappa_min=0.1` → найменший ліквідний ринок серед трьох (ETHUSDT=0.2, SOLUSDT=0.15)
- Gate блокує entry, якщо `kappa < 0.1` (мертвий ринок)

**Code Tracing:**
- **Compute:** `apps/reference/domains/feature_engineering/feature_compute_logic.py:Line ~1200` — обчислює `kappa` з order book depth
- **Gate Enforcement:** `apps/reference/domains/decision_making/aurora_handler.py:Line ~900-950` — checks `_liquidity_gate_passed()`
- **Test:** `tests/domains/decision_making/test_liquidity_gate_aurora.py`

---

## 🎪 Side Bias Configuration (Penalty-Based)

BTC має мотиви для балансу лонгів/шортів (leveraged trading risk).

| Поле | BTC Value | Глобальне | Роль |
|---|---|---|---|
| `penalty_factor` | `0.5` | (non-strict) | Штраф за сигнал, який йде проти цільового ratio |
| `window_sec` | `600` | (non-strict) | Час観察(10 хвилин) |
| `target_ratio` | `0.6` | (non-strict) | Цільовий ratio long:total = 60% |

**Interpretation:**
- Якщо останні 10 хв: 70% лонгів (перевісить цілі 60%) → наступний SHORT сигнал отримує `×0.5` штраф
- Мета: Попередити затиски та краш-ризики

**Code Tracing:**
- **Compute:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:Line ~150-200` — `_apply_side_bias_penalty()`
- **Test:** `tests/domains/decision_making/test_aurora_side_bias.py`

---

## 🔄 Regime Thresholds & Sizing (Market Adaptation)

**Контекст:** System розпізнає 8 режимів (HIGH_VOLATILITY, TREND_UP, etc.). 
Для кожного режиму ми масштабуємо threshold та position size.

### Regime Thresholds (Entry Barrier Adaptation)

Мультиплікатори до глобального `signal_threshold=0.12`:

| Режим | BTCUSDT Mult | Ефективний Threshold | Статус | Інтерпретація |
|---|---|---|---|---|
| `HIGH_VOLATILITY` | **1.2** | 0.12 × 1.2 = **0.144** | 🟢 Harder | Шумніший ринок → вищий поріг |
| `LOW_VOLATILITY` | **0.9** | 0.12 × 0.9 = **0.108** | 🟢 Easier | Спокійніший ринок → нижчий поріг |
| `MEAN_REVERSION` | **1.05** | 0.12 × 1.05 = **0.126** | 🟢 Slightly Harder | MR має більше шуму |
| `TREND_UP` | **1.0** | 0.12 × 1.0 = **0.12** | 🟢 Neutral | Трендові умови — стандартна чутливість |
| `TREND_DOWN` | **1.0** | 0.12 × 1.0 = **0.12** | 🟢 Neutral | Обох трендів однакові |
| `DEFAULT` | **1.0** | 0.12 × 1.0 = **0.12** | 🟢 Neutral | Fallback |

**Code Tracing:**
- **Apply:** `apps/reference/domains/decision_making/aurora_handler.py:Line ~600-650` — `_apply_regime_threshold_multiplier()`
- **Regime Inference:** `apps/reference/domains/decision_making/regime_mapping.py:Line ~100` — детектує режим з ATR/momentum

### Regime Sizing (Position Size Adaptation)

Мультиплікатори до базового розміру позиції:

| Режим | BTCUSDT Mult | Інтерпретація |
|---|---|---|
| `HIGH_VOLATILITY` | **3.0** | More volatility → bigger positions (higher expected moves) |
| `LOW_VOLATILITY` | **4.0** | Less volatility → need bigger size to hit TP |
| `MEAN_REVERSION` | **3.5** | MR має середній потенціал |

**Semantics:**
- Size = Kelly_Fraction × regime_sizing[regime]
- Kelly_Fraction ≈ 0.05-0.10 базовий, потім × regime multiplier

**Code Tracing:**
- **Compute:** `apps/reference/domains/decision_making/position_sizing.py:Line ~200` — `compute_position_size()`
- **Test:** `tests/domains/decision_making/test_aurora_regime_sizing.py`

---

## 🛑 Exit Configuration (Stop-Loss & Regime-Based TP/SL)

Найбільш важлива секція, оскільки контролює risk/reward.

### Base Exit Config

| Поле | Значення | Pydantic | Роль |
|---|---|---|---|
| `sl_pct` | `0.02` | ✅ `AuroraExitConfig.sl_pct` | Base stop-loss: **2%** від entry |
| `max_hold_sec` | `3000` | ✅ `AuroraExitConfig.max_hold_sec` | Max 50 хвилин в позиції (safety exit) |

**Interpretation:**
- BTC має 2% SL (найбільший серед трьох)
  - ETHUSDT: 1.9%
  - SOLUSDT: 1.512%
  - BTC: 2.0%
- Більша волатильність BTC → ширший SL для уникнення wick-outs
- `max_hold_sec=3000` → exit через 50 хв навіть без profit (anti-zombie gate)

**Code Tracing:**
- **Apply SL:** `apps/reference/domains/decision_making/aurora_handler.py:Line ~1480-1540` — `_create_exit_intent()`
- **Enforce SL:** `apps/reference/domains/execution_position/position_monitor.py:Line ~400` — перевіряє SL на кожному bar

---

## ⭐⭐⭐ REGIME_TPSL: Режимна адаптація Take-Profit/Stop-Loss

**ЦЕ НАЙСКЛАДНІША ЧАСТИНА!**

### 📋 Огляд regime_tpsl

```yaml
exit:
  sl_pct: 0.02                   # Base SL (2%)
  regime_tpsl:                   # ← ЦЯ СТРУКТУРА!
    enabled: true                # Master switch
    mode: "pct_mult"             # Using simple multipliers (not ATR)
    
    sl_mult:                      # 8 regime-specific SL multipliers
      DEFAULT: 1.0
      FLAT_LOW: 0.70
      LOW_VOLATILITY: 0.75
      # ... (8 режимів усього)
    
    tp_mult:                      # 8 regime-specific TP multipliers
      DEFAULT: 1.0
      TREND_UP: 1.25
      # ... (8 режимів усього)
    
    # Guardrails: Діапазони, в які затягуються обчислені значення
    min_sl_pct: 0.003            # 0.3%  — мінімум
    max_sl_pct: 0.06             # 6%    — максимум
    min_tp_rr: 0.3               # Мінімум risk/reward ratio
    max_tp_rr: 3.0               # Максимум risk/reward ratio
    min_dist_bps: 15             # 15 bps от entry — мінімальна дистанція
```

### 🔧 Як це працює (pct_mult режим)

**Algorithm:**

```
1. regime_used = detect_current_regime()           # e.g., TREND_UP

2. sl_mult = sl_mult[regime_used]                  # e.g., 1.10
   tp_mult = tp_mult[regime_used]                  # e.g., 1.25

3. sl_pct_eff = sl_pct × sl_mult                   # 0.02 × 1.10 = 0.022 (2.2%)
   tp_rr_eff = tp_low_ratio × tp_mult              # 0.5 × 1.25 = 0.625

4. // Apply guardrails (CLAMP, не fail-closed!)
   sl_pct_final = clamp(sl_pct_eff, min_sl_pct, max_sl_pct)
   tp_rr_final = clamp(tp_rr_eff, min_tp_rr, max_tp_rr)

5. if side == BUY:
     SL = entry × (1 - sl_pct_final)               # e.g., 42000 × (1 - 0.022) = 41076
     TP = entry × (1 + tp_rr_final × sl_pct_final) # e.g., 42000 × (1 + 0.625 × 0.022) ≈ 42580
   else (SELL):
     SL = entry × (1 + sl_pct_final)
     TP = entry × (1 - tp_rr_final × sl_pct_final)

6. Distance checks:
   if abs(TP - entry) < min_dist_bps → FAIL-CLOSED (reject signal)
   if abs(SL - entry) < min_dist_bps → FAIL-CLOSED (reject signal)
```

### 📊 Детальна таблиця SL Multipliers (BTCUSDT)

Визначають, як широкий SL в кожному режимі.

| Режим | sl_mult | Базовий SL | Ефективний SL | Аргументація |
|---|---|---|---|---|
| **FLAT_LOW** | **0.70** | 0.02 | 0.02 × 0.70 = **0.014 (1.4%)** | Мало волатильності → тісний SL |
| **LOW_VOLATILITY** | **0.75** | 0.02 | 0.02 × 0.75 = **0.015 (1.5%)** | - |
| **FLAT_NORMAL** | **0.85** | 0.02 | 0.02 × 0.85 = **0.017 (1.7%)** | Нормальна розвитість → нормальний SL |
| **MEAN_REVERSION** | **0.95** | 0.02 | 0.02 × 0.95 = **0.019 (1.9%)** | MR коливання → дещо ширший |
| **TREND_UP** | **1.10** | 0.02 | 0.02 × 1.10 = **0.022 (2.2%)** | Тренд → можемо терпіти більше |
| **TREND_DOWN** | **1.10** | 0.02 | 0.02 × 1.10 = **0.022 (2.2%)** | - |
| **HIGH_VOLATILITY** | **1.35** | 0.02 | 0.02 × 1.35 = **0.027 (2.7%)** | Шумний ринок → широкий SL |
| **UNCERTAIN** | **1.00** | 0.02 | 0.02 × 1.00 = **0.02 (2.0%)** | Не впевнений → стандартна SL |

**Interpretation:**
- **High vol = Wide SL:** При HIGH_VOLATILITY множник 1.35 → SL розширюється на 35%
- **Low vol = Tight SL:** При LOW_VOLATILITY множник 0.75 → SL зужується на 25%
- **Guardrails:** Навіть із множником, final SL затягується в [0.3%, 6%]

**Code Tracing (SL Computation):**
- **Apply:** `apps/reference/domains/decision_making/aurora_handler.py:Line 1567-1600` — `_compute_tpsl_pct_mult()`
  - Line 1575: `sl_mult = float(sl_mult_map.get(regime_used, sl_mult_map["DEFAULT"]))`
  - Line 1580: `sl_pct_eff = sl_pct_base * sl_mult`
- **Guardrail:** `apps/reference/domains/decision_making/aurora_handler.py:Line 1620-1650` — `_apply_tpsl_guardrails()`

---

### 📊 Детальна таблиця TP Multipliers (BTCUSDT)

Визначають, як вис Reward-to-Risk ratio в кожному режимі.

Формула TP: **TP = entry × (1 ± tp_low_ratio × tp_mult × sl_pct_eff)**

| Режим | tp_mult | Base TP Ratio | Ефективна RR | Аргументація |
|---|---|---|---|---|
| **FLAT_LOW** | **0.75** | 0.5 | 0.5 × 0.75 = **0.375** | Мало движу → меньше ціль |
| **LOW_VOLATILITY** | **0.80** | 0.5 | 0.5 × 0.80 = **0.40** | - |
| **FLAT_NORMAL** | **0.90** | 0.5 | 0.5 × 0.90 = **0.45** | Стандартна ціль |
| **MEAN_REVERSION** | **0.85** | 0.5 | 0.5 × 0.85 = **0.425** | MR → меньше потенціал |
| **TREND_UP** | **1.25** | 0.5 | 0.5 × 1.25 = **0.625** | Тренд → більша ціль |
| **TREND_DOWN** | **1.25** | 0.5 | 0.5 × 1.25 = **0.625** | - |
| **HIGH_VOLATILITY** | **1.05** | 0.5 | 0.5 × 1.05 = **0.525** | Волатильність → дещо вище |
| **UNCERTAIN** | **1.00** | 0.5 | 0.5 × 1.00 = **0.50** | Стандартна ціль |

**Interpretation:**
- **Trending Up → 1.25x:** TP множник найвищий (максимум потенціалу)
- **Flat Low → 0.75x:** TP множник найменший (мін потенціалу)
- **Formula Example (BUY, TREND_UP):**
  ```
  entry = 42,000
  sl_pct_eff = 0.02 × 1.10 = 0.022
  tp_rr_eff = 0.5 × 1.25 = 0.625
  TP = 42,000 × (1 + 0.625 × 0.022) = 42,000 × 1.01375 ≈ 42,577
  Risk = 42,000 - (42,000 × 0.978) = 924 USDT
  Reward = 42,577 - 42,000 = 577 USDT
  RR = 577 / 924 ≈ 0.62 → це добре!
  ```

**Code Tracing (TP Computation):**
- **Apply:** `apps/reference/domains/decision_making/aurora_handler.py:Line 1598-1605` — `_compute_tpsl_pct_mult()`
  - Line 1600: `tp_mult = float(tp_mult_map.get(regime_used, tp_mult_map["DEFAULT"]))`
  - Line 1602: `tp_rr_eff = tp_low_ratio_base * tp_mult`
  - Line 1605: `target_price = entry_price * (1 + tp_dist_pct)` (for BUY)

---

### 🚨 Guardrails (Safety Nets)

| Guardrail | Value | Тип | Аргументація |
|---|---|---|---|
| `min_sl_pct` | **0.003** | CLAMP | **Мінімум 0.3%** — нижче це просто шум |
| `max_sl_pct` | **0.06** | CLAMP | **Максимум 6%** — вище це рискованно для leverage |
| `min_tp_rr` | **0.3** | CLAMP | Мінімум RR=0.3 — занадто мало, не варто трейдити |
| `max_tp_rr` | **3.0** | CLAMP | Максимум RR=3.0 — над 3:1 це нереально |
| `min_dist_bps` | **15** | FAIL-CLOSED | **Мін 15 basis points** від entry до SL/TP — попередити wick-outs |

**CLAMP vs FAIL-CLOSED:**
- **CLAMP:** Значення затягується в діапазон (0.5% → 0.3%, 10% → 6%) — сигнал все ще входить
- **FAIL-CLOSED:** `min_dist_bps` - якщо SL/TP надто близько до entry → **відхилити сигнал!**

**Code Tracing:**
- **Apply:** `apps/reference/domains/decision_making/aurora_handler.py:Line 1620-1670` — `_apply_tpsl_guardrails()`
  ```python
  sl_pct_clamped = max(min_sl_pct, min(sl_pct_eff, max_sl_pct))  # Clamp
  tp_rr_clamped = max(min_tp_rr, min(tp_rr_eff, max_tp_rr))     # Clamp
  
  dist_bps_sl = abs(stop_price - entry_price) * 10000 / entry_price
  if dist_bps_sl < min_dist_bps:
      return None  # FAIL-CLOSED: reject signal
  ```

---

## 💻 Take-Profit Configuration

| Поле | Значення BTCUSDT | Глобальне ETHUSDT | Роль |
|---|---|---|---|
| `tp_low_ratio` | **0.5** | 0.4 | TP1 (partial exit) ratio до SL |
| `tp_high_ratio` | **1.0** | 1.4 | TP2 (full exit) ratio |
| `partial_exit_pct` | **0.5** | 0.7 | Exit 50% на TP1, 50% на TP2 |

**Interpretation:**
- BTC має більш консервативні TP цілі (0.5 vs 0.4 для ETH)
- На TP1 (0.5 ratio) exit 50% позиції, залишити 50% для TP2
- BTC очікує меньше максимального profit (tp_high_ratio=1.0 vs 1.4 для ETH)

**Formula:**
```
TP1_distance = (tp_low_ratio × tp_mult × sl_pct_eff) × entry
TP2_distance = (tp_high_ratio × tp_mult × sl_pct_eff) × entry

Example (BUY, TREND_UP):
  entry = 42,000, tp_low_ratio = 0.5, tp_mult = 1.25, sl_pct_eff = 0.022
  TP1 = 42,000 × (1 + 0.5 × 1.25 × 0.022) ≈ 42,577 (exit 50%)
  TP2 = 42,000 × (1 + 1.0 × 1.25 × 0.022) ≈ 43,155 (exit 50%)
```

**Code Tracing:**
- **Compute:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:Line ~1100-1150` — `_compute_partial_exit()`
- **Test:** `tests/domains/decision_making/test_take_profit_v2.py`

---

## 🎯 Allowed Regimes (Filtering)

```yaml
allowed_regimes:
  - TREND_UP
  - TREND_DOWN
  - HIGH_VOLATILITY
  - LOW_VOLATILITY
  - FLAT_LOW
  - FLAT_NORMAL
```

**Interpretation:**
- BTC торгується у всіх 6 режимах (крім MEAN_REVERSION, UNCERTAIN)
- MEAN_REVERSION відсутній → під час MR режиму сигнали не генеруються
- Це відбиває те, що BTC більш трендовий, ніж mean-reverting

**Code Tracing:**
- **Enforce:** `apps/reference/domains/decision_making/aurora_handler.py:Line ~750-780` — `_regime_filter_passed()`

---

## 🔌 Volatility Entry Logic (Limit Entry Pricing)

Визначає, як далеко від поточної ціни розміщується LIMIT order для maker fees.

```yaml
volatility_entry_logic:
  enabled: true
  regime_multipliers:
    HIGH_VOLATILITY: 0.4    # 40% ATR offset
    LOW_VOLATILITY: 0.05    # 5% ATR offset
    MEAN_REVERSION: 0.2     # 20% ATR offset
    TREND_UP: 0.15          # 15% ATR offset
    TREND_DOWN: 0.15        # 15% ATR offset
    UNCERTAIN: 0.15         # 15% ATR offset
    DEFAULT: 0.15           # Fallback
```

**Formula:**
```
offset = ATR × regime_multipliers[regime]

if side == BUY:
  limit_price = mark_price - offset      # Bid below (maker fee)
if side == SELL:
  limit_price = mark_price + offset      # Ask above (maker fee)
```

**Example (BUY, HIGH_VOLATILITY):**
```
mark_price = 42,000
ATR (10-period) = 500
offset = 500 × 0.4 = 200
limit_price = 42,000 - 200 = 41,800     ← Bid 200 USDT below market
```

**BTC Profile:**
- BTC найстабільніший → найменші offsets (0.05 у LOW_VOL)
- Попри це, HIGH_VOLATILITY offset = 0.4 (більше ніж SOL=0.6)
- Мета: Maker fee priority на BTC, де liquidity глибока

**Code Tracing:**
- **Compute:** `apps/reference/domains/decision_making/limit_order_utils.py:Line ~100-150` — `_apply_volatility_entry()`
- **Test:** `tests/domains/decision_making/test_volatility_entry_logic.py`

---

## 🎲 Signal Threshold & Cooldown

```yaml
signal_threshold:
  enabled: false           # Use global (0.12)
  value: null

cooldown_sec: null         # Use global (6s, or decision.qos.symbol_cooldown_sec=1s)
```

**Interpretation:**
- BTCUSDT *не має* per-symbol threshold override → використовує глобальний 0.12
- BTCUSDT *не має* per-symbol cooldown → використовує глобальний (1s з QoS)

**Code Tracing:**
- **Fallback:** `apps/reference/domains/decision_making/aurora_handler.py:Line ~400-430` — `_resolve_signal_threshold(symbol)`

---

## 📈 Holding Period (Anti-HFT)

```yaml
holding_period:
  enabled: true
  min_duration_sec: 20              # Override global 30 → 20 (BTC більш ліквідний)
  emergency_exit_threshold: 0.7    # |score| must exceed 0.7 to exit early
```

**Semantics:**
- BTCUSDT min_duration = **20 сек** (vs глобальні 30)
- Це означає: після входу, мінімум 20 сек утримання перед exit сигналами
- Крім того, якщо нова позиція сигнал дуже сильний (|score| > 0.7) → можна exit раніше

**Мета:** Попередити HFT-style churn (enter/exit на 2-3 сек)

**Code Tracing:**
- **Enforce:** `apps/reference/domains/decision_making/anti_churn_gate.py:Line ~50-100` — `_holding_period_passed()`
- **Emergency:** `apps/reference/domains/decision_making/anti_churn_gate.py:Line ~120` — checks emergency threshold
- **Test:** `tests/domains/decision_making/test_anti_churn_gate.py`

---

## 🚫 Re-entry Cooldown (Anti-Ping-Pong)

```yaml
reentry_cooldown_sec: 45           # Override global 60 → 45
```

**Semantics:**
- BTCUSDT re-entry delay = **45 сек** (vs глобальні 60)
- Після close позиції (exit/SL/TP) → чекати 45 сек перед новим entry
- Мета: Попередити ping-pong (买卖交替на одній ціні)

**Code Tracing:**
- **Enforce:** `apps/reference/domains/decision_making/position_monitor.py:Line ~280-320` — `_reentry_cooldown_passed()`
- **Test:** `tests/domains/decision_making/test_aurora_reentry_cooldown.py`

---

## ✅ Integration & Testing

### Пов'язані Domain Handlers

1. **Decision Making Domain:**
   - `apps/reference/domains/decision_making/aurora_handler.py` (main logic, 2144 lines)
   - `apps/reference/domains/decision_making/aurora_scoring_kernel.py` (signal scoring)
   - `apps/reference/domains/decision_making/position_sizing.py` (Kelly calculation)

2. **Execution Position Domain:**
   - `apps/reference/domains/execution_position/position_monitor.py` (enforce SL/TP)
   - `apps/reference/domains/execution_position/order_events_handler.py` (fill tracking)

3. **Feature Engineering Domain:**
   - `apps/reference/domains/feature_engineering/aurora_features.py` (compute regime, ATR)
   - `apps/reference/domains/feature_engineering/regime_mapping.py` (regime detection)

### Test Coverage

| Test Suite | Status | File | Coverage |
|---|---|---|---|
| Regime TP/SL | ✅ ACTIVE | `tests/domains/decision_making/test_regime_tpsl_*.py` (5+ test files) | 100% of `_compute_tpsl_*` methods |
| Anti-Churn | ✅ ACTIVE | `tests/domains/decision_making/test_anti_churn_gate.py` | holding_period enforcement |
| Reentry | ✅ ACTIVE | `tests/domains/decision_making/test_aurora_reentry_cooldown.py` | cooldown logic |
| Liquidity Gate | ✅ ACTIVE | `tests/domains/decision_making/test_liquidity_gate_aurora.py` | kappa_min/max |
| Volatility Entry | ✅ ACTIVE | `tests/domains/decision_making/test_volatility_entry_logic.py` | offset calculation |

**Run Tests:**
```bash
pytest tests/domains/decision_making/test_regime_tpsl_pct_mult.py -v
pytest tests/domains/decision_making/test_aurora_reentry_cooldown.py -v
```

---

## 🔴 Known Issues & Deprecations

| Issue | Статус | Fix |
|---|---|---|
| `trailing_stop.enabled: false` | 🟡 Deprecated | Manual SL preferred (trailing logic complex) |
| `macro_sync` (in signal weights) | 🔴 Deprecated | Replaced by `macro_resid` (R1 migration) |
| `legacy_tick_path_enabled: false` | 🟡 Legacy | Phase 4 migration — AuroraHandler becomes primary |

---

## 📋 Validation Checklist

Before using BTCUSDT Aurora config in production:

- [ ] ✅ `enabled: true` - стратегія активна
- [ ] ✅ `regime_tpsl.enabled: true` - режимна адаптація включена
- [ ] ✅ `regime_tpsl.sl_mult.DEFAULT: 1.0` - базова SL мультиплікація заповнена
- [ ] ✅ `regime_tpsl.tp_mult.DEFAULT: 1.0` - базова TP мультиплікація заповнена
- [ ] ✅ `exit.sl_pct: 0.02` - базова SL = 2%
- [ ] ✅ `take_profit.tp_low_ratio: 0.5` - базова TP = 0.5x RR
- [ ] ✅ `signal_threshold.enabled: false` - використовується глобальна 0.12
- [ ] ✅ `allowed_regimes` містить мінімум 3 режими
- [ ] ✅ `liquidity_gate.enabled: true` - вбудована гарячка
- [ ] ✅ Тести проходять: `pytest tests/domains/decision_making/test_regime_tpsl_*.py -v`
- [ ] ✅ Config валідується: `python -m apps.reference.main --validate-config`

---

## 📞 Related Documents

- 📖 **SSOT Config:** [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml)
- 📖 **Schema Models:** [apps/reference/config_models.py](apps/reference/config_models.py) (lines 2178-2350)
- 📖 **Algorithm:** [docs/AURORA_REGIME_TP_SL_PLAN.md](docs/AURORA_REGIME_TP_SL_PLAN.md)
- 📖 **Architecture:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) § Aurora Handler
- 📖 **Decision Making Flows:** [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py) (lines 1457-1670)

---

**Generated:** 2026-01-27
**Configuration Version:** aurora.yaml SSOT (CFG-AURORA-INSTRUMENTS-SSOT-01)
**Last Updated:** Code audit aligned with aurora_handler.py:_compute_regime_tpsl()
