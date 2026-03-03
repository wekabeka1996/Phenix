# 📄 Паспорт конфігурації: aurora/strategies/aurora.yaml :: SOLUSDT

## 🔍 Загальний опис блоку

Блок `aurora.assets.SOLUSDT` — це конфігурація для стратегії Aurora на символі **SOLUSDT** (Solana/USDT).
Це **перевизначення** глобальних параметрів з блоку `aurora.decision` для SOL конкретно.

**Характеристики SOLUSDT:**
- 🔴 **Найбільш волатильна** з трьох (σ > ETH > BTC)
- 🟡 **Менш ліквідна** (нижче vol, мілше order book)
- 🎲 **Більш хаотична** (режимна фільтрація встроєна — тільки 4 режими)
- 💰 **Потребує більш агресивних SL** (1.5% vs 1.9% ETH, 2.0% BTC)

**Registry Mapping:** SOLUSDT призначена Aurora якщо в `strategies_registry.assignments` є відповідний запис.

---

## 📊 Глобальна Topmap позиції SOLUSDT в стратегії

```
aurora.assets.SOLUSDT (Per-Symbol Overrides)
├── enabled: true
├── position_mode: STRICT (no pyramiding)
├── leverage: {target: 20, mode: ISOLATED}
├── weights: {9 features}  ← Ось-centered (ema_bias: 0.20, macro_resid: 0.25, obi: 0.25)
├── holding_period: {min_duration_sec: 35, ...}  ← Нова! (was null)
├── reentry_cooldown_sec: 120  ← Консервативна (vs BTC 45)
├── liquidity_gate: {kappa_min: 0.15, ...}  ← Нижча ніж ETHUSDT
├── side_bias: {penalty_factor: 0.0, ...}  ← Жодних penalties!
├── regime_thresholds: {HIGH_VOLATILITY: 1.35, ...}  ← НОВА! (was null)
├── regime_sizing: {HIGH_VOLATILITY: 5.0, ...}
├── exit: {sl_pct: 0.01512, regime_tpsl: {...}}  ← ⭐ НОВА!
├── take_profit: {tp_low_ratio: 0.36, tp_high_ratio: 0.60, ...}
├── allowed_regimes: [TREND_DOWN, LOW_VOLATILITY, FLAT_NORMAL, MEAN_REVERSION]  ← Тільки 4!
├── signal_threshold: {enabled: true, value: 0.09}  ← Override
├── trailing_stop: {enabled: true, ...}  ← Один із двох, що використовує
└── volatility_entry_logic: {regime_multipliers: {...}}
```

---

## 🛠 Деталізація основних полів (Top Level)

| Поле | Значення SOL | ETHUSDT | BTCUSDT | Статус | Роль |
|---|---|---|---|---|---|
| `enabled` | `true` | `true` | `true` | 🟢 Active | Увімкнути Aurora для SOLUSDT |
| `position_mode` | `STRICT` | `STRICT` | `STRICT` | 🟢 Active | No pyramiding |
| `leverage.target` | `20` | `20` | `20` | 🟢 Active | 20x isolated |
| `holding_period.min_duration_sec` | **35** | 45 | 20 | 🟢 Active | **Нова!** (was null) |
| `reentry_cooldown_sec` | **120** | 120 | 45 | 🟢 Active | **Найвища** (с ETH) |
| `liquidity_gate.kappa_min` | **0.15** | 0.2 | 0.1 | 🟡 Low | **Менш ліквідна** |
| `side_bias.penalty_factor` | **0.0** | 0.9 | 0.5 | 🟡 Zero | **Жодних penalties!** |
| `regime_thresholds` | ✅ 4 множники | ✅ 6 | ✅ 6 | 🔴 Limited | **Тільки 4 режими** |
| `regime_sizing` | 3 множники | 3 | 3 | 🟢 Active | Більші множники (5.0, 6.0) |
| `exit.sl_pct` | **0.01512** | 0.019 | 0.02 | 🟢 Active | **Найменша SL** (найвол) |
| `exit.regime_tpsl` | ✅ **ADDED!** | ✅ YES | ✅ YES | 🟢 Active | ⭐ **Найширші мультиплікатори** |
| `signal_threshold.enabled` | `true` | `true` | `false` | 🟢 Active | Override 0.12 → 0.09 |
| `allowed_regimes` | **4 режими** | 6 | 6 | 🔴 Limited | Крім TREND_UP, HIGH_VOL, UNCERTAIN |
| `trailing_stop.enabled` | **true** | false | false | 🟡 Deprecated | Один із двох! |

---

## 📊 Per-Feature Signal Weights (SOLUSDT)

**Важливе примітання:** SOLUSDT ваги ідентичні ETHUSDT (за винятком tfi).

| Feature | SOLUSDT | ETHUSDT | BTCUSDT | Статус | Роль |
|---|---|---|---|---|---|
| `obi` | **0.25** | 0.25 | 0.20 | 🟢 Weighted | Depth imbalance — high |
| `tfi` | **0.09** | 0.093 | 0.10 | 🟡 De-emp | Trend futures — very low |
| `delta_price` | **0.10** | 0.10 | 0.05 | 🟢 Weighted | Price momentum — medium |
| `ema_bias` | **0.20** | 0.20 | 0.20 | 🟢 Weighted | Trend distance — high |
| `volume_spike` | **0.20** | 0.20 | 0.15 | 🟢 Weighted | **Volume anomaly — high** |
| `volatility_state` | **0.05** | 0.036 | 0.10 | 🟡 Low | Vol regime — low |
| `depth_imbalance` | **-0.20** | -0.256 | -0.05 | 🔴 Negative | ASK dominance — penalized |
| `macro_resid` | **0.25** | 0.25 | 0.15 | 🟢 Weighted | **Macro signals — very high** |

**Interpretation:**
- **Sum:** 0.25 + 0.09 + 0.10 + 0.20 + 0.20 + 0.05 - 0.20 + 0.25 = **0.95** (normalized)
- **SOLUSDT Profile:** Trend + Volume biased (як ETH)
  - **High:** obi (0.25), ema_bias (0.20), volume_spike (0.20), macro_resid (0.25)
  - **Low:** tfi (0.09), volatility_state (0.05), depth_imbalance (-0.20)
  - **Vs BTC:** SOL має більш тенденцію до volume signal

---

## 🛑 Exit Configuration & ⭐ REGIME_TPSL (NEW!)

### Base Exit Config

| Поле | SOL | ETH | BTC | Роль |
|---|---|---|---|---|
| `sl_pct` | **0.01512** | 0.019 | 0.02 | **Найменша SL** — волатильна |
| `max_hold_sec` | 3000 | 3000 | 3000 | 50 хв anti-zombie |

**Semantics:**
- SOL має **1.512% SL** (найменше!)
- Це відбиває найвищу волатильність SOL
- Потребує більш жорсткої SL для manage risk з high leverage

---

### ⭐ REGIME_TPSL Configuration (NEWLY ADDED!)

**NOTE:** regime_tpsl **тільки що додана** для SOLUSDT (був missing!). 
Це найбільш **агресивна конфіграція** з трьох (найширші мультиплікатори).

```yaml
exit:
  sl_pct: 0.01512
  regime_tpsl:              # ← НОВИЙ БЛОК!
    enabled: true
    mode: "pct_mult"
    sl_mult: {...}          # 8 режимів, найширші мультиплікатори
    tp_mult: {...}          # 8 режимів, середні мультиплікатори
    guardrails...           # Найнижчі min_tp_rr для SOL
```

---

### 📊 Детальна таблиця SL Multipliers (SOLUSDT)

SOL волатильна → мультиплікатори **НАЙШИРШІ** з трьох.

| Режим | sl_mult | Base SL | Ефективна SL | ETH mult | BTC mult | Аргументація |
|---|---|---|---|---|---|---|
| **FLAT_LOW** | **0.60** | 0.01512 | 0.00907 (**0.91%**) | 0.65→1.24% | 0.70→1.4% | Тісниний SL для flat |
| **LOW_VOLATILITY** | **0.65** | 0.01512 | 0.00983 (**0.98%**) | 0.70→1.33% | 0.75→1.5% | - |
| **FLAT_NORMAL** | **0.75** | 0.01512 | 0.01134 (**1.13%**) | 0.80→1.52% | 0.85→1.7% | Нормальна |
| **MEAN_REVERSION** | **0.85** | 0.01512 | 0.01284 (**1.28%**) | 0.90→1.71% | 0.95→1.9% | MR коливання |
| **TREND_UP** | **1.15** | 0.01512 | 0.01739 (**1.74%**) | 1.05→2.0% | 1.10→2.2% | Шире для тренду |
| **TREND_DOWN** | **1.15** | 0.01512 | 0.01739 (**1.74%**) | 1.05→2.0% | 1.10→2.2% | - |
| **HIGH_VOLATILITY** | **1.50** | 0.01512 | 0.02268 (**2.27%**) | 1.25→2.38% | 1.35→2.7% | **Найширший** — волатильна |
| **UNCERTAIN** | **1.00** | 0.01512 | 0.01512 (**1.51%**) | 1.00→1.9% | 1.00→2.0% | Стандартна |

**Interpretation:**
- **HIGH_VOLATILITY = 1.50:** SOL найширший множник (vs ETH 1.25, BTC 1.35)
- **Why?** SOL найбільш волатильна → потребує більш простору для SL
- **Range:** 0.91% - 2.27% (найширший діапазон з трьох)

**Code Tracing:**
- **Apply:** `apps/reference/domains/decision_making/aurora_handler.py:Line ~1575` — `_compute_tpsl_pct_mult()`

---

### 📊 Детальна таблиця TP Multipliers (SOLUSDT)

SOL консервативніша для TP (менш потенціалу, більш непередбачувана).

| Режим | tp_mult | Base TP Ratio | Ефективна RR | ETH mult | BTC mult | Аргументація |
|---|---|---|---|---|---|---|
| **FLAT_LOW** | **0.65** | 0.36 | 0.234 (**0.234**) | 0.70→0.28 | 0.75→0.375 | Низька мета |
| **LOW_VOLATILITY** | **0.70** | 0.36 | 0.252 (**0.252**) | 0.75→0.30 | 0.80→0.40 | - |
| **FLAT_NORMAL** | **0.80** | 0.36 | 0.288 (**0.288**) | 0.85→0.34 | 0.90→0.45 | Стандартна |
| **MEAN_REVERSION** | **0.75** | 0.36 | 0.270 (**0.270**) | 0.80→0.32 | 0.85→0.425 | MR менше потенціалу |
| **TREND_UP** | **1.30** | 0.36 | 0.468 (**0.468**) | 1.20→0.48 | 1.25→0.625 | **Найвище** для SOL! |
| **TREND_DOWN** | **1.30** | 0.36 | 0.468 (**0.468**) | 1.20→0.48 | 1.25→0.625 | - |
| **HIGH_VOLATILITY** | **1.10** | 0.36 | 0.396 (**0.396**) | 1.00→0.40 | 1.05→0.525 | Moderate |
| **UNCERTAIN** | **1.00** | 0.36 | 0.360 (**0.360**) | 1.00→0.40 | 1.00→0.50 | Стандартна |

**Interpretation:**
- **TREND modes (1.30):** SOL найвищий (vs ETH 1.20, BTC 1.25) — агресивна для трендів
- **LOW_VOL (0.70):** SOL дещо нижче ETH (0.75) — більш консервативна
- **Overall:** SOL має найвищі мультиплікатори для TREND, найменші для FLAT

**Formula Example (BUY, TREND_UP):**
```
entry = 100 USDT
sl_pct_eff = 0.01512 × 1.15 = 0.01739 (1.74%)
tp_rr_eff = 0.36 × 1.30 = 0.468
TP = 100 × (1 + 0.468 × 0.01739) = 100 × 1.00814 ≈ 100.81
Risk = 100 - (100 × 0.9826) = 1.74 USDT
Reward = 100.81 - 100 = 0.81 USDT
RR = 0.81 / 1.74 = 0.47 ✓
```

**Code Tracing:**
- **Apply:** `apps/reference/domains/decision_making/aurora_handler.py:Line ~1600` — `_compute_tpsl_pct_mult()`

---

### 🚨 Guardrails (Safety Nets)

| Guardrail | SOL | ETH | BTC | Тип | Аргументація |
|---|---|---|---|---|---|
| `min_sl_pct` | **0.0025** | 0.002 | 0.003 | CLAMP | **Найменша** (0.25%) |
| `max_sl_pct` | **0.065** | 0.055 | 0.06 | CLAMP | **Найбільша** (6.5%) |
| `min_tp_rr` | **0.25** | 0.3 | 0.3 | CLAMP | **Найменша** RR ratio |
| `max_tp_rr` | **3.5** | 3.0 | 3.0 | CLAMP | **Найбільша** RR ratio |
| `min_dist_bps` | **18** | 12 | 15 | FAIL-CLOSED | **Найбільша** дистанція |

**Interpretation:**
- **min_dist_bps = 18:** SOL потребує найбільше простору від entry до SL/TP (менш ліквідна)
- **max_sl_pct = 0.065:** SOL дозволяє найбільший SL (волатильна)
- **min_tp_rr = 0.25:** SOL дозволяє найнижчу RR (непередбачувана)
- **Message:** SOL найменш стабільна → найбільш защитні guardrails

---

## 💻 Take-Profit Configuration

| Поле | SOL | ETH | BTC | Роль |
|---|---|---|---|---|
| `tp_low_ratio` | **0.36** | 0.4 | 0.5 | **Найменша** TP1 |
| `tp_high_ratio` | **0.60** | 1.4 | 1.0 | **Найменша** TP2 |
| `partial_exit_pct` | **0.31** | 0.7 | 0.5 | **Найменша** partial exit |

**Interpretation:**
- **SOL найбільш консервативна:** tp_high_ratio=0.60 (найнижче!)
- **Why?** SOL непередбачувана → не можемо очікувати великих moves
- **Partial Exit:** 31% на TP1 → залишити 69% на TP2 (очікуємо першого exitu, потім хочемо видержати)

---

## 🎯 Режимні параметри (Threshold & Sizing)

### Regime Thresholds (Entry Barrier) — NEWLY ADDED!

**NOTE:** regime_thresholds **був null** для SOL, тепер **добавлений**!

Мультиплікатори до глобального `signal_threshold=0.12`:

| Режим | Mult | SOL Threshold | ETH Threshold | BTC Threshold | Інтерпретація |
|---|---|---|---|---|---|
| `HIGH_VOLATILITY` | **1.35** | 0.162 | 0.156 | 0.144 | **Найвищий** — шумний ринок |
| `LOW_VOLATILITY` | **0.80** | 0.096 | 0.102 | 0.108 | **Найніший** — легше входити |
| `MEAN_REVERSION` | **1.10** | 0.132 | 0.126 | 0.126 | MR coiling |
| `DEFAULT` | **1.0** | 0.12 | 0.12 | 0.12 | Стандартна |

**Interpretation:**
- **SOL HIGH_VOL = 1.35:** Найвищий серед трьох → найбільш консервативна в шумі
- **SOL LOW_VOL = 0.80:** Найнижчий серед трьох → найменше легко входити (SOL непередбачувана!)
- **Why?** SOL волатильна → при high vol потребує вищого поріга

---

### Regime Sizing (Position Size)

| Режим | SOL | ETH | BTC | Мотивація |
|---|---|---|---|---|
| `HIGH_VOLATILITY` | **5.0** | 0.3 | 3.0 | **Найбільша** позиція |
| `LOW_VOLATILITY` | **6.0** | 1.9 | 4.0 | **Найбільша** позиція |
| `MEAN_REVERSION` | **5.0** | 0.8 | 3.5 | **Найбільша** позиція |

**Interpretation:**
- **SOL дозволяє найбільші позиції:** 5.0-6.0 (vs ETH 0.3-1.9, BTC 3.0-4.0)
- **Why?** SOL має найменший базовий SL (1.512%) → може витримати більші position size для Kelly calculation
- **Trade-off:** Більш агресивна sizing, але більш тісна SL = більш ризикована

---

## 🎲 Holding Period & Reentry Cooldown

### Holding Period (Anti-HFT) — NEWLY ADDED!

**NOTE:** holding_period **був null** для SOL, тепер **добавлена**!

| Параметр | SOL | ETH | BTC | Роль |
|---|---|---|---|---|
| `min_duration_sec` | **35** | 45 | 20 | **Нова!** Середня утримання |
| `emergency_exit_threshold` | 0.65 | 0.65 | 0.7 | Early exit trigger |

**Interpretation:**
- **35 сек:** SOL утримання 35 сек перед exit сигналами (між BTC і ETH)
- **Why?** SOL волатильна але не тренд-following → помірна утримання
- **Emergency:** 0.65 threshold (як ETH) — доволі жорстока для ранніх exits

### Re-entry Cooldown (Anti-Ping-Pong)

| Параметр | SOL | ETH | BTC | Роль |
|---|---|---|---|---|
| `reentry_cooldown_sec` | **120** | 120 | 45 | **Найдовша** (з ETH) |

**Interpretation:**
- **120 сек:** SOL чекає 2 хвилини перед re-entry (як ETH)
- **BTC = 45:** Більш ліквідна → швидше re-entry
- **Why?** SOL непередбачувана → вища затримка для уникнення ping-pong

---

## 🔌 Liquidity Gate & Volatility Entry

### Liquidity Gate

| Параметр | SOL | ETH | BTC | Роль |
|---|---|---|---|---|
| `enabled` | `true` | `true` | `true` | Feature flag |
| `kappa_min` | **0.15** | 0.2 | 0.1 | **Найменша** |
| `kappa_max` | 1.0 | 1.0 | 1.0 | Standard |

**Interpretation:**
- **kappa_min = 0.15:** SOL дозволяє меньшу ліквідність ніж ETHUSDT (0.2)
- **Why?** SOL менш ліквідна в порівнянні з BTC/ETH → більш жорстка гата потребує низіської

### Volatility Entry Logic

LIMIT entry pricing via ATR offset:

| Режим | SOL Mult | ETH Mult | BTC Mult | Інтерпретація |
|---|---|---|---|---|
| HIGH_VOLATILITY | **0.6** | 0.5 | 0.4 | **Найбільший** offset |
| LOW_VOLATILITY | **0.1** | 0.1 | 0.05 | Однаковий (з ETH) |
| MEAN_REVERSION | **0.3** | 0.25 | 0.2 | Середній |
| DEFAULT | **0.2** | 0.2 | 0.15 | Стандартна |

**Interpretation:**
- **HIGH_VOL = 0.6:** SOL найбільше шкода LIMIT від mark (менш ліквідна)
- **DEFAULT = 0.2:** Більш ніж BTC (0.15) через менш ліквідність
- **Why?** SOL менш ліквідна → потребує більш агресивної LIMIT pricing

---

## 🎲 Trailing Stop Configuration

```yaml
trailing_stop:
  enabled: true              # ← ОДИН ІЗ ДВОХ!
  activation_pct: 0.046     # Activate after 4.6% profit
  trail_pct: 0.018          # Trail at 1.8% distance
  min_update_interval_sec: 5
```

**Interpretation:**
- **SOL один із двох, що використовує trailing stop** (ETHUSDT і BTC = disabled)
- **Why?** SOL волатильна → manual SL більш вірна, але trailing stop може допомогти у трендах
- **Params:** Аґрессивна активація (4.6% profit) і дальна відстань (1.8%)

---

## 📈 Allowed Regimes (Filtering)

```yaml
allowed_regimes:
  - TREND_DOWN
  - LOW_VOLATILITY
  - FLAT_NORMAL
  - MEAN_REVERSION
```

**Interpretation:**
- **4 режими (не 6!):** SOL пропускає TREND_UP, HIGH_VOL, UNCERTAIN
- **Why?** SOL непередбачувана в трендах → фільтрація TREND_UP
- **Vs ETHUSDT:** ETHUSDT робить усім 6 режимів (більш універсальна)

---

## 📊 Comparison Table: SOLUSDT vs ETHUSDT vs BTCUSDT

| Параметр | SOLUSDT | ETHUSDT | BTCUSDT | Winner |
|---|---|---|---|---|
| **Min Duration (Anti-HFT)** | 35s | 45s | 20s | ETH (longest) |
| **Reentry Cooldown** | 120s | 120s | 45s | SOL/ETH (longest) |
| **Base SL%** | 1.512% | 1.9% | 2.0% | SOL (tightest) |
| **TP High Ratio** | 0.60 | 1.4 | 1.0 | ETH (most aggressive) |
| **Signal Threshold** | 0.09 | 0.09 | 0.12 | SOL/ETH (easier entry) |
| **Liquidity Gate kappa_min** | 0.15 | 0.2 | 0.1 | BTC (most liquid) |
| **Allowed Regimes** | 4 | 6 | 6 | ETH/BTC (most regimes) |
| **regime_tpsl.enabled** | ✅ YES | ✅ YES | ✅ YES | All equal (NEW!) |
| **regime_thresholds** | ✅ YES (NEW) | ✅ YES | ✅ YES | All equal (NEW!) |
| **holding_period** | ✅ YES (NEW) | ✅ YES | ✅ YES | All equal (NEW!) |
| **SL mult HIGH_VOL** | **1.50** | 1.25 | 1.35 | SOL (widest) |
| **TP mult TREND** | **1.30** | 1.20 | 1.25 | SOL (most aggressive) |
| **regime_sizing max** | **6.0** | 1.9 | 4.0 | SOL (biggest position) |

---

## 🔴 Дисбаланси, виправлені в цьому Passport

### Проблеми (Before)
1. ❌ **regime_tpsl був відсутній** для SOLUSDT
2. ❌ **regime_thresholds був null** (інгерував глобальні)
3. ❌ **holding_period був null** (інгерував глобальні)
4. ❌ Режимна адаптація **неактивна** для SOLUSDT

### Розв'язання (After)
1. ✅ **regime_tpsl добавлена** з **найширшими мультиплікаторами** для волатильної монети
2. ✅ **regime_thresholds добавлена** з 4 режимами (HIGH_VOL: 1.35, LOW_VOL: 0.80)
3. ✅ **holding_period добавлена** з 35 сек (оптимізовано для SOL)
4. ✅ **8 режимів × 2 типи = 16 мультиплікацій** тепер активні
5. ✅ **Guardrails установлені** для SOL специфіки (min_dist_bps=18, max_sl_pct=6.5%)

---

## ✅ Integration & Testing

### Related Domains
1. **Decision Making:** `aurora_handler.py`, `aurora_scoring_kernel.py`
2. **Execution Position:** `position_monitor.py` (enforce SL/TP)
3. **Feature Engineering:** `regime_mapping.py` (detect regime)

### Test Coverage
```bash
pytest tests/domains/decision_making/test_regime_tpsl_*.py -v
pytest tests/domains/decision_making/test_anti_churn_gate.py -v
pytest tests/domains/decision_making/test_aurora_reentry_cooldown.py -v
pytest tests/domains/decision_making/test_liquidity_gate_aurora.py -v
```

### Validation Command
```bash
python -m apps.reference.main --validate-config
# Should pass all regime_tpsl, holding_period, regime_thresholds validations
```

---

## 📋 Validation Checklist

- [ ] ✅ `regime_tpsl.enabled: true`
- [ ] ✅ `regime_tpsl.sl_mult` містить DEFAULT key + 7 інших
- [ ] ✅ `regime_tpsl.tp_mult` містить DEFAULT key + 7 інших
- [ ] ✅ `regime_thresholds.HIGH_VOLATILITY: 1.35` ✓
- [ ] ✅ `holding_period.min_duration_sec: 35` ✓
- [ ] ✅ `min_dist_bps: 18` (правильно для SOL)
- [ ] ✅ `max_sl_pct: 0.065` (найбільш для SOL)
- [ ] ✅ `allowed_regimes` містить 4 режими (TREND_DOWN, LOW_VOL, FLAT_NORMAL, MR)
- [ ] ✅ `signal_threshold.value: 0.09` (override)
- [ ] ✅ `trailing_stop.enabled: true` (один із двох!)
- [ ] ✅ Тести проходять

---

## 📞 Related Documents

- 📖 **SSOT Config:** [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml)
- 📖 **Schema Models:** [apps/reference/config_models.py](apps/reference/config_models.py)
- 📖 **Algorithm:** [docs/AURORA_REGIME_TP_SL_PLAN.md](docs/AURORA_REGIME_TP_SL_PLAN.md)
- 📖 **Anti-Churn Gate:** [docs/RFC_min_duration_logic.md](docs/RFC_min_duration_logic.md)
- 📖 **Decision Making:** [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py)

---

**Generated:** 2026-01-27
**Configuration Version:** aurora.yaml SSOT (CFG-AURORA-INSTRUMENTS-SSOT-01)
**Status:** regime_tpsl, regime_thresholds, holding_period NEWLY ADDED - Ready for production
**Volatility Profile:** HIGHEST (vs ETHUSDT, BTCUSDT) - Most aggressive guardrails
