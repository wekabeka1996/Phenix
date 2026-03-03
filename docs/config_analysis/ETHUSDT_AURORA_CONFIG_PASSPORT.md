# 📄 Паспорт конфігурації: aurora/strategies/aurora.yaml :: ETHUSDT

## 🔍 Загальний опис блоку

Блок `aurora.assets.ETHUSDT` — це конфігурація для стратегії Aurora на символі **ETHUSDT** (Ethereum/USDT).
Це **перевизначення** глобальних параметрів з блоку `aurora.decision` для ETH конкретно.

**Характеристики ETHUSDT:**
- 🟢 **Менш волатильна** ніж SOLUSDT (σ < SOL)
- 🟢 **Більш ліквідна** (вищий vol, глибший order book)
- 🔄 **Trend-following** (довше утримання: 45 сек vs BTC 20 сек)
- ↗️ **Потенційно вищі TP цілі** (tp_high_ratio=1.4 vs BTC 1.0)

**Registry Mapping:** ETHUSDT призначена Aurora якщо в `strategies_registry.assignments` є відповідний запис.

---

## 📊 Глобальна Topmap позиції ETHUSDT в стратегії

```
aurora.assets.ETHUSDT (Per-Symbol Overrides)
├── enabled: true
├── position_mode: STRICT (no pyramiding)
├── leverage: {target: 20, mode: ISOLATED}
├── weights: {9 features}  ← Trend-biased (ema_bias: 0.20, macro_resid: 0.25)
├── holding_period: {min_duration_sec: 45, ...}  ← Довше ніж BTC (45 vs 20)
├── reentry_cooldown_sec: 120  ← Консервативна (vs BTC 45)
├── liquidity_gate: {kappa_min: 0.2, ...}  ← Більш середня ліквідність
├── side_bias: {penalty_factor: 0.9, ...}
├── regime_thresholds: {HIGH_VOLATILITY: 1.3, ...}  ← 6 режимів
├── regime_sizing: {HIGH_VOLATILITY: 0.3, ...}
├── exit: {sl_pct: 0.019, regime_tpsl: {...}}  ← ⭐ NOW ADDED!
├── take_profit: {tp_low_ratio: 0.4, tp_high_ratio: 1.4, ...}
├── allowed_regimes: [TREND_UP, TREND_DOWN, FLAT_LOW, FLAT_NORMAL, LOW_VOLATILITY, MEAN_REVERSION]
├── signal_threshold: {enabled: true, value: 0.09}  ← Override
└── volatility_entry_logic: {regime_multipliers: {...}}
```

---

## 🛠 Деталізація основних полів (Top Level)

| Поле | Значення ETH | BTCUSDT | SOLUSDT | Статус | Роль |
|---|---|---|---|---|---|
| `enabled` | `true` | `true` | `true` | 🟢 Active | Увімкнути Aurora для ETHUSDT |
| `position_mode` | `STRICT` | `STRICT` | `STRICT` | 🟢 Active | No pyramiding (1 trade) |
| `leverage.target` | `20` | `20` | `20` | 🟢 Active | 20x изоляциона leverage |
| `holding_period.min_duration_sec` | **45** | 20 | 35 | 🟢 Active | **Найдовше** — ETH trend-following |
| `reentry_cooldown_sec` | **120** | 45 | 120 | 🟢 Active | **Консервативна** для trend-following |
| `liquidity_gate.kappa_min` | **0.2** | 0.1 | 0.15 | 🟢 Active | Середня ліквідність |
| `side_bias.penalty_factor` | **0.9** | 0.5 | 0.0 | 🟡 High | Сильні penalties за контр-тренд |
| `regime_thresholds` | ✅ 6 режимів | ✅ 6 режимів | ✅ 4 режими | 🟢 Active | Threshold adaptation |
| `regime_sizing` | 3 множники | 3 множники | 3 множники | 🟢 Active | Position size adaptation |
| `exit.sl_pct` | **0.019** | 0.02 | 0.01512 | 🟢 Active | **Найменша SL** (найменш волат) |
| `exit.regime_tpsl` | ✅ **ADDED!** | ✅ YES | ✅ **ADDED!** | 🟢 Active | ⭐ Режимна адаптація TP/SL |
| `signal_threshold.enabled` | `true` | `false` | `true` | 🟢 Active | **Override глобальну** (0.09 vs 0.12) |
| `allowed_regimes` | 6 режимів | 6 режимів | 4 режими | 🟢 Active | Режимна гатинг |

---

## 📊 Per-Feature Signal Weights (ETHUSDT)

**Важливе примітання:** ETHUSDT ваги дуже відрізняються від BTCUSDT — більше на trend-signals.

| Feature | ETHUSDT | BTCUSDT | SOLUSDT | Статус | Роль |
|---|---|---|---|---|---|
| `obi` | **0.25** | 0.20 | 0.25 | 🟢 Weighted | Depth imbalance — high |
| `tfi` | **0.093** | 0.10 | 0.09 | 🟡 De-emp | Trend futures — low |
| `delta_price` | **0.10** | 0.05 | 0.10 | 🟢 Weighted | Price momentum — medium |
| `ema_bias` | **0.20** | 0.20 | 0.20 | 🟢 Weighted | **Trend distance — high** |
| `volume_spike` | **0.20** | 0.15 | 0.20 | 🟢 Weighted | **Volume anomaly — high** |
| `volatility_state` | **0.036** | 0.10 | 0.05 | 🔴 Very Low | Vol regime — almost ignored |
| `depth_imbalance` | **-0.256** | -0.05 | -0.20 | 🔴 Negative | ASK dominance — penalized |
| `macro_resid` | **0.25** | 0.15 | 0.25 | 🟢 Weighted | **Macro signals — very high** |

**Interpretation:**
- **Sum:** 0.25 + 0.093 + 0.10 + 0.20 + 0.20 + 0.036 - 0.256 + 0.25 = **0.873** (normalized in scoring)
- **ETHUSDT Profile:** Strongly trend-biased
  - **High:** obi (0.25), ema_bias (0.20), volume_spike (0.20), macro_resid (0.25)
  - **Low:** volatility_state (0.036), tfi (0.093), depth_imbalance (-0.256)
  - **Why?** ETH більше трендова, ніж BTC; volume spikes важливі для altcoin

---

## 🛑 Exit Configuration & ⭐ REGIME_TPSL (NEW!)

### Base Exit Config

| Поле | ETH | BTC | SOL | Роль |
|---|---|---|---|---|
| `sl_pct` | **0.019** | 0.02 | 0.01512 | **Найменша SL** — ETH найстабільніша |
| `max_hold_sec` | 3000 | 3000 | 3000 | 50 хв anti-zombie gate |

**Semantics:**
- ETH має 1.9% SL (найменше серед трьох)
- Це рефлектує нижчу волатильність ETH vs BTC/SOL
- 3000 сек = 50 хвилин максимум в позиції

---

### ⭐ REGIME_TPSL Configuration (NEWLY ADDED!)

**NOTE:** regime_tpsl **тільки що додана** для ETHUSDT (був missing!). Це зменшить режимну адаптацію.

```yaml
exit:
  sl_pct: 0.019
  regime_tpsl:              # ← НОВЫЙ БЛОК!
    enabled: true
    mode: "pct_mult"
    sl_mult: {...}          # 8 режимів
    tp_mult: {...}          # 8 режимів
    guardrails...
```

---

### 📊 Детальна таблиця SL Multipliers (ETHUSDT)

ETH консервативніша за BTC → мультиплікатори **меньші**.

| Режим | sl_mult | Base SL | Ефективна SL | Порівняння BTC | Аргументація |
|---|---|---|---|---|---|
| **FLAT_LOW** | **0.65** | 0.019 | 0.0124 (**1.24%**) | 0.70→1.4% | Тісніший SL для flat |
| **LOW_VOLATILITY** | **0.70** | 0.019 | 0.0133 (**1.33%**) | 0.75→1.5% | - |
| **FLAT_NORMAL** | **0.80** | 0.019 | 0.0152 (**1.52%**) | 0.85→1.7% | Нормальна |
| **MEAN_REVERSION** | **0.90** | 0.019 | 0.0171 (**1.71%**) | 0.95→1.9% | MR коливання |
| **TREND_UP** | **1.05** | 0.019 | 0.0200 (**2.0%**) | 1.10→2.2% | Дещо ширше |
| **TREND_DOWN** | **1.05** | 0.019 | 0.0200 (**2.0%**) | 1.10→2.2% | Одне з TREND_UP |
| **HIGH_VOLATILITY** | **1.25** | 0.019 | 0.0238 (**2.38%**) | 1.35→2.7% | Ширше для high vol |
| **UNCERTAIN** | **1.00** | 0.019 | 0.0190 (**1.9%**) | 1.00→2.0% | Стандартна |

**Interpretation:**
- **Найменший множник (FLAT_LOW):** 0.65 — ETH найстабільніша, може витримати тісну SL
- **Найбільший множник (HIGH_VOL):** 1.25 — навіть в high vol, ETH потребує менше простору ніж BTC (1.35)
- **vs BTC:** Усі множники ETH нижче, ніж для BTC

**Code Tracing:**
- **Apply:** `apps/reference/domains/decision_making/aurora_handler.py:Line ~1575` — `_compute_tpsl_pct_mult()`

---

### 📊 Детальна таблиця TP Multipliers (ETHUSDT)

ETH має більш агресивні TP цілі (trend-following).

| Режим | tp_mult | Base TP Ratio | Ефективна RR | Порівняння BTC | Аргументація |
|---|---|---|---|---|---|
| **FLAT_LOW** | **0.70** | 0.4 | 0.28 (**0.28**) | 0.75→0.375 | Низька мета |
| **LOW_VOLATILITY** | **0.75** | 0.4 | 0.30 (**0.30**) | 0.80→0.40 | - |
| **FLAT_NORMAL** | **0.85** | 0.4 | 0.34 (**0.34**) | 0.90→0.45 | Стандартна |
| **MEAN_REVERSION** | **0.80** | 0.4 | 0.32 (**0.32**) | 0.85→0.425 | MR менше потенціалу |
| **TREND_UP** | **1.20** | 0.4 | 0.48 (**0.48**) | 1.25→0.625 | **Більш агресивна** ніж BTC! |
| **TREND_DOWN** | **1.20** | 0.4 | 0.48 (**0.48**) | 1.25→0.625 | - |
| **HIGH_VOLATILITY** | **1.00** | 0.4 | 0.40 (**0.40**) | 1.05→0.525 | Conservative |
| **UNCERTAIN** | **1.00** | 0.4 | 0.40 (**0.40**) | 1.00→0.50 | Стандартна |

**Interpretation:**
- **TREND modes:** ETH = 1.20, BTC = 1.25 — мало різниці, обидва агресивні
- **HIGH_VOL:** ETH = 1.0 (conservative), BTC = 1.05 (дещо більше)
- **Overall:** ETH і BTC подібні для TP, обидві trend-friendly

**Formula Example (BUY, TREND_UP):**
```
entry = 2,000 USDT
sl_pct_eff = 0.019 × 1.05 = 0.02 (2%)
tp_rr_eff = 0.4 × 1.20 = 0.48
TP = 2,000 × (1 + 0.48 × 0.02) = 2,000 × 1.0096 ≈ 2,019.2
Risk = 2,000 - (2,000 × 0.98) = 40 USDT
Reward = 2,019.2 - 2,000 = 19.2 USDT
RR = 19.2 / 40 = 0.48 ✓
```

**Code Tracing:**
- **Apply:** `apps/reference/domains/decision_making/aurora_handler.py:Line ~1600` — `_compute_tpsl_pct_mult()`

---

### 🚨 Guardrails (Safety Nets)

| Guardrail | ETH | BTC | SOL | Тип | Аргументація |
|---|---|---|---|---|---|
| `min_sl_pct` | **0.002** | 0.003 | 0.0025 | CLAMP | ETH дозволяє найтіснішу SL (0.2%) |
| `max_sl_pct` | **0.055** | 0.06 | 0.065 | CLAMP | ETH менше макс (5.5% vs 6% BTC) |
| `min_tp_rr` | **0.3** | 0.3 | 0.25 | CLAMP | Мінімум RR = 0.3 |
| `max_tp_rr` | **3.0** | 3.0 | 3.5 | CLAMP | Максимум RR = 3.0 |
| `min_dist_bps` | **12** | 15 | 18 | FAIL-CLOSED | **Найменша дистанція** (ETH ліквідніша) |

**Interpretation:**
- **min_dist_bps = 12:** ETH дозволяє LIMIT orders 12 bps від entry (vs BTC 15, SOL 18)
- **min_sl_pct = 0.002:** ETH найтіснішої мін-SL (0.2% vs BTC 0.3%, SOL 0.25%)
- **Mensaje:** ETH найстабільніша → може витримати найтісніші guardrails

---

## 💻 Take-Profit Configuration

| Поле | ETH | BTC | SOL | Роль |
|---|---|---|---|---|
| `tp_low_ratio` | **0.4** | 0.5 | 0.36 | TP1 ratio до SL |
| `tp_high_ratio` | **1.4** | 1.0 | 0.60 | TP2 ratio |
| `partial_exit_pct` | **0.7** | 0.5 | 0.31 | Exit 70% на TP1 |

**Interpretation:**
- **ETH найбільш агресивна:** tp_high_ratio=1.4 (найвище!) → очікує великих moves
- **Partial Exit:** 70% на TP1 → оптимістично щодо потенціалу ETH
- **TP1 距离:** Менша ніж BTC (0.4 vs 0.5) — повільніший тренд, частіший exit

---

## 🎯 Режимні параметри (Threshold & Sizing)

### Regime Thresholds (Entry Barrier)

Мультиплікатори до глобального `signal_threshold=0.12`:

| Режим | Mult | ETH Threshold | BTC Threshold | SOL Threshold | Інтерпретація |
|---|---|---|---|---|---|
| `HIGH_VOLATILITY` | **1.3** | 0.156 | 0.144 | 0.162 | **Найвищий** — шумний ринок |
| `LOW_VOLATILITY` | **0.85** | 0.102 | 0.108 | 0.096 | Легше входити |
| `MEAN_REVERSION` | **1.05** | 0.126 | 0.126 | 0.132 | MR coiling |
| `DEFAULT` | **1.0** | 0.12 | 0.12 | 0.12 | Стандартна |

**Interpretation:**
- **ETH HIGH_VOL = 1.3:** Найвищий серед трьох → найконсервативніша в шумі
- **ETH LOW_VOL = 0.85:** Довший з BTCUSDT (BTC = 0.9) → більш чутлива до спокійних ринків

---

### Regime Sizing (Position Size)

| Режим | ETH | BTC | SOL | Мотивація |
|---|---|---|---|---|
| `HIGH_VOLATILITY` | **0.3** | 3.0 | 5.0 | Найменша позиція (мало руху) |
| `LOW_VOLATILITY` | **1.9** | 4.0 | 6.0 | Велика позиція (тісне SL) |
| `MEAN_REVERSION` | **0.8** | 3.5 | 5.0 | Середня |

**Interpretation:**
- **ETH = 0.3 в HIGH_VOL:** Найменша серед трьох (консервативна)
- **ETH = 1.9 в LOW_VOL:** Найбільша серед трьох! (агресивна в спокійних ринках)
- **Profile:** ETH — максимізує profit в низькій-vol, мінімізує loss у high-vol

---

## 🔌 Liquidity Gate & Volatility Entry

### Liquidity Gate

| Параметр | ETH | BTC | SOL | Роль |
|---|---|---|---|---|
| `enabled` | `true` | `true` | `true` | Feature flag |
| `kappa_min` | **0.2** | 0.1 | 0.15 | **Найвищий поріг** |
| `kappa_max` | 1.0 | 1.0 | 1.0 | Standard |

**Interpretation:**
- **kappa_min = 0.2:** ETH потребує кращої ліквідності ніж BTC (0.1) і SOL (0.15)
- **Why?** ETH потребує глибшого order book для големши positions

### Volatility Entry Logic

LIMIT entry pricing via ATR offset:

| Режим | ETH Mult | BTC Mult | SOL Mult | Інтерпретація |
|---|---|---|---|---|
| HIGH_VOLATILITY | **0.5** | 0.4 | 0.6 | Середній offset |
| LOW_VOLATILITY | **0.1** | 0.05 | 0.1 | **Найменший** для ETH |
| MEAN_REVERSION | **0.25** | 0.2 | 0.3 | Середній |
| DEFAULT | **0.2** | 0.15 | 0.2 | Стандартна |

**Interpretation:**
- **LOW_VOL = 0.1:** ETH дозволяє максимально близьку LIMIT до mark (maker fee priority)
- **HIGH_VOL = 0.5:** Більш агресивна ніж BTC (0.4), менш ніж SOL (0.6)

---

## 🎲 Holding Period & Reentry Cooldown

### Holding Period (Anti-HFT)

| Параметр | ETH | BTC | SOL | Роль |
|---|---|---|---|---|
| `min_duration_sec` | **45** | 20 | 35 | **Найдовше** |
| `emergency_exit_threshold` | 0.65 | 0.7 | 0.65 | Early exit trigger |

**Interpretation:**
- **45 сек:** ETH максимум утримання перед exit сигналами (trend-following!)
- **BTC = 20, SOL = 35:** ETH найконсервативніша до quick reversals
- **Why?** ETH трендова → не хочемо швидких flips

### Re-entry Cooldown (Anti-Ping-Pong)

| Параметр | ETH | BTC | SOL | Роль |
|---|---|---|---|---|
| `reentry_cooldown_sec` | **120** | 45 | 120 | **Найдовше** |

**Interpretation:**
- **120 сек:** ETH чекає 2 хвилини перед re-entry (як SOL)
- **BTC = 45:** Більш ліквідна → швидше re-entry
- **Why?** ETH trend-following → уникаємо ping-pong у choppy periods

---

## ✅ Signal Threshold Override

```yaml
signal_threshold:
  enabled: true
  value: 0.09              # Override глобальну 0.12
```

**Interpretation:**
- **ETHUSDT = 0.09:** Нижче глобального 0.12
- **BTCUSDT = null (inherit 0.12):** Глобальна
- **SOLUSDT = 0.09:** Такі ж як ETH
- **Why?** ETH более чутлива → нижча барієра для входу

---

## 📈 Allowed Regimes (Filtering)

```yaml
allowed_regimes:
  - TREND_UP
  - TREND_DOWN
  - FLAT_LOW
  - FLAT_NORMAL
  - LOW_VOLATILITY
  - MEAN_REVERSION
```

**Interpretation:**
- **6 режимів (максимум):** ETH торгується у всіх режимах
- **BTCUSDT = 6:** Те ж саме
- **SOLUSDT = 4:** SOLUSDT крім TREND_UP, HIGH_VOL, UNCERTAIN
- **Why?** ETH універсальна, SOL більш специфічна

---

## 📊 Comparison Table: ETHUSDT vs BTCUSDT vs SOLUSDT

| Параметр | ETHUSDT | BTCUSDT | SOLUSDT | Winner |
|---|---|---|---|---|
| **Min Duration (Anti-HFT)** | 45s | 20s | 35s | ETH (longest) |
| **Reentry Cooldown** | 120s | 45s | 120s | ETH/SOL (longest) |
| **Base SL%** | 1.9% | 2.0% | 1.512% | SOL (tightest) |
| **TP High Ratio** | 1.4 | 1.0 | 0.60 | ETH (most aggressive) |
| **Signal Threshold** | 0.09 | 0.12 | 0.09 | ETH/SOL (easiest entry) |
| **Liquidity Gate kappa_min** | 0.2 | 0.1 | 0.15 | BTC (most liquid) |
| **Allowed Regimes** | 6 | 6 | 4 | ETH/BTC (most regimes) |
| **regime_tpsl.enabled** | ✅ YES | ✅ YES | ✅ YES | All equal (NEW!) |

---

## 🔴 Дисбаланси, виправлені в цьому Passport

### Проблеми (Before)
1. ❌ **regime_tpsl був відсутній** для ETHUSDT
2. ❌ Режимна адаптація TP/SL була **неактивна** для ETHUSDT

### Розв'язання (After)
1. ✅ **regime_tpsl добавлена** з параметрами, адаптованими до ETH
2. ✅ **8 режимів × 2 типи = 16 мультиплікацій** тепер активні
3. ✅ **Guardrails установлені** для ETH специфіки (min_dist_bps=12)

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
```

---

## 📋 Validation Checklist

- [ ] ✅ `regime_tpsl.enabled: true`
- [ ] ✅ `regime_tpsl.sl_mult` містить DEFAULT key
- [ ] ✅ `regime_tpsl.tp_mult` містить DEFAULT key
- [ ] ✅ `min_dist_bps: 12` (правильно для ETH)
- [ ] ✅ `holding_period.min_duration_sec: 45` (longest)
- [ ] ✅ `signal_threshold.value: 0.09` (override)
- [ ] ✅ `allowed_regimes` містить 6 режимів
- [ ] ✅ Тести проходять

---

**Generated:** 2026-01-27
**Configuration Version:** aurora.yaml SSOT (CFG-AURORA-INSTRUMENTS-SSOT-01)
**Status:** regime_tpsl NEWLY ADDED - Ready for production
