# SCORING SYSTEM PASSPORT
## Phenix Aurora Trading System — Повний паспорт системи скорингу
**Версія документа:** 1.0.0
**Дата:** 2026-03-02
**Статус:** Production

---

## ЗМІСТ

1. [Загальна архітектура](#1-загальна-архітектура)
2. [Ланцюжок скорингу](#2-ланцюжок-скорингу)
3. [Стратегія Aurora — повний скоринг](#3-стратегія-aurora--повний-скоринг)
4. [Стратегія Mean Reversion — скоринг](#4-стратегія-mean-reversion--скоринг)
5. [Risk Scoring — портфельний рівень](#5-risk-scoring--портфельний-рівень)
6. [Повні конфігураційні значення](#6-повні-конфігураційні-значення)
7. [Гейти та фільтри](#7-гейти-та-фільтри)
8. [Архітектурна оцінка](#8-архітектурна-оцінка)
9. [Математична оцінка](#9-математична-оцінка)

---

## 1. ЗАГАЛЬНА АРХІТЕКТУРА

### 1.1 Структура скорингу — два рівні

```
┌─────────────────────────────────────────────────────────────┐
│                    SCORING SYSTEM                           │
│                                                             │
│  РІВЕНЬ 1: Portfolio RISK GATE                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ RiskManagement → is_trading_allowed (bool)          │   │
│  │ Inputs: daily_drawdown, daily_loss, portfolio_state │   │
│  │ Output: ALLOW / BLOCK (вся торгівля)                │   │
│  └─────────────────────────────────────────────────────┘   │
│                           ↓                                 │
│  РІВЕНЬ 2: INSTRUMENT RISK SCORE                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ risk_score = f(obi, tfi, delta_price, absorption)   │   │
│  │ Gate: risk_score <= max_risk_score (0.96)           │   │
│  └─────────────────────────────────────────────────────┘   │
│                           ↓                                 │
│  РІВЕНЬ 3: SIGNAL SCORING (per strategy)                   │
│  ┌──────────────────────┐  ┌────────────────────────────┐  │
│  │  AURORA STRATEGY     │  │  MEAN REVERSION STRATEGY   │  │
│  │  AuroraScoringKernel │  │  MeanReversion1mStrategy   │  │
│  │  signal_score ∈ R    │  │  confidence ∈ [0,1]        │  │
│  │  thresh: 0.162       │  │  thresh: 0.05-0.24         │  │
│  └──────────────────────┘  └────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Розподіл символів по стратегіях (SSOT: strategies.yaml)

| Символ    | Aurora | Mean Reversion |
|-----------|--------|----------------|
| BTCUSDT   | ❌ off | ❌ off         |
| ETHUSDT   | ❌ off | ❌ off         |
| SOLUSDT   | ✅ on  | ❌ off         |
| DOGEUSDT  | ❌ off | ✅ on          |
| XRPUSDT   | ❌ off | ❌ off         |

> ⚠️ **Критично:** BTCUSDT та ETHUSDT та XRPUSDT мають порожні assignments `[]` — вони взагалі не торгують. Лише SOLUSDT (Aurora) та DOGEUSDT (MR) активні.

---

## 2. ЛАНЦЮЖОК СКОРИНГУ

### 2.1 Повний pipeline (Aurora)

```
FE: FeatureEngineering
  └─ emit EVT:BAR_CLOSED + CMD:PROCESS_STRATEGY
       │
       ▼
RiskManagement
  ├─ [L1] DailyGate.can_open() → drawdown/loss check
  │       Gate: daily_drawdown_pct <= 10.0 (зараз ВИМКНЕНО)
  ├─ [L2] risk_score computation ──────────────────────────────────┐
  │       Formula (детально в розділі 5)                           │
  │       Gate: risk_score <= 0.96                                 │
  └─ emit EVT:RISK_ASSESSMENT_COMPLETED {is_trading_allowed, risk_score}
                                                                    │
       ▼                                                            │
DecisionMaking.on_risk()                              ◄────────────┘
  └─ Зберігає risk params для символу
       │
       ▼
DecisionMaking._make_decision_for_symbol()
  └─ AuroraScoringKernel.compute()
       ├─ [S1] Нормалізація delta_price
       ├─ [S2] signed_v2 transforms
       ├─ [S3] compute_direction_strength_score()
       │       ├─ dir_score = SignalScoreV2 (directional features)
       │       ├─ strength_score = SignalScoreV2 (strength features)
       │       └─ final = dir × (1 + α × strength)
       ├─ [S4] Regime threshold factor
       ├─ [S5] Side bias penalty
       └─ [S6] Side determination (buy/sell/neutral)
```

---

## 3. СТРАТЕГІЯ AURORA — ПОВНИЙ СКОРИНГ

### 3.1 SignalScoreV2 — базова формула

**Файл:** `apps/reference/domains/decision_making/signal_score_v2.py`

```
score_raw = Σ w_i × (x_i − neutral_i)     [тільки ready+present features]
wabs      = Σ |w_i|                         [тільки ready+present features]
score_norm = score_raw / wabs
score      = clamp(score_norm, -1, +1)
```

**Принципи:**
- **Net-Zero**: кожна фіча центрується навколо свого neutralного значення
- **Fail-Closed**: відсутня або not-ready essential фіча → DEFER (не 0, а відмова)
- **Normalization**: ділення на Σ|w| → score завжди в [-1, +1]
- **Missing features** не входять ні в score_raw ні в wabs (пропускаються повністю)

### 3.2 DirectionStrength split — розширена формула

**Файл:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py`

```
dir_score      = SignalScoreV2(directional_features)    ∈ [-1, +1]
strength_score = SignalScoreV2(strength_features)        ∈ [0, cap=1.0] (≥0 завжди)
final_score    = dir_score × (1 + α × strength_score)
```

де `α` = **strength_alpha = 0.5**

**Інтерпретація:**
- `dir_score` показує **напрямок** (позитивний = BUY, негативний = SELL)
- `strength_score` показує **силу** руху (більший → сильніше підсилення dir)
- При `strength_score = 1.0` і `α = 0.5`: `final = dir × 1.5` (+50% підсилення)
- При `strength_score = 0.0`: `final = dir × 1.0` (без підсилення)

### 3.3 signed_v2 трансформації (pre-processing)

**Файл:** `scoring_direction_strength_v1.py:_apply_signed_v2_transforms()`

```
Для [0,1] features (neutral=0.5):
    x' = 2×clamp(x, 0, 1) − 0.5
    Результат: (x' - 0.5) = 2×(x - 0.5) ∈ [-1, +1]   (повне розтягування)

Для signed features (neutral=0.0):
    x' = clamp(x, -1, +1)   (вінзоризація)
```

> **Навіщо:** [0,1]-фічі з нейтраллю 0.5 дають компонент w×(x-0.5) max = w×0.5.
> Трансформація double-stretches їх до повного діапазону w×[-1,+1].

### 3.4 Ваги сигналів — глобальні (config: aurora.yaml)

| Фіча              | Вага w  | Нейтраль | Тип          | Група        |
|-------------------|---------|----------|--------------|--------------|
| `obi`             | +0.42   | 0.0      | signed       | directional  |
| `tfi`             | +0.15   | 0.0      | signed       | directional  |
| `delta_price`     | +0.15   | 0.0      | signed       | directional  |
| `ema_bias`        | +0.15   | 0.5      | [0,1]        | directional  |
| `depth_imbalance` | **-0.15** | 0.5    | [0,1]        | directional  |
| `macro_resid`     | +0.10   | 0.0      | signed[-3,3] | directional  |
| `macro_sync`      | **0.0** (deprecated) | 0.5 | [0,1] | directional (telemetry) |
| `volume_spike`    | +0.10   | 0.0      | [0,∞)        | strength     |
| `volatility_state`| +0.10   | 0.0      | [0,1]        | strength     |

**Сума directional |w|:** 0.42+0.15+0.15+0.15+0.15+0.10 = **1.12**
**Сума strength |w|:**    0.10+0.10 = **0.20**

> `depth_imbalance` має від'ємну вагу: high depth_imbalance (ASK dominance) = sell pressure → знижує BUY score

### 3.5 Порогові значення та визначення сторони

#### Базовий поріг:
```
signal_threshold = 0.162   (глобальний, з aurora.yaml)
```

#### Режимний множник (regime_threshold_multipliers):
```
final_threshold = base_threshold × regime_factor × side_bias_mult
```

| Режим           | Множник | Ефективний поріг |
|----------------|---------|-----------------|
| HIGH_VOLATILITY | 0.20    | 0.0324          |
| MEAN_REVERSION  | 0.16    | 0.0259          |
| TREND_UP        | 0.14    | 0.0227          |
| TREND_DOWN      | 0.14    | 0.0227          |
| UNCERTAIN       | 0.18    | 0.0292          |
| LOW_VOLATILITY  | 0.12    | 0.0194          |
| DEFAULT         | 0.16    | 0.0259          |

> ⚠️ **Також є другий набір** `regime_thresholds` в aurora.yaml (не множники, а абсолютні поріги):
> `LOW_VOLATILITY: 99.0`, `UNCERTAIN: 99.0` — фактично блокують ці режими для певних символів.

#### Hysteresis (3-зонна логіка):

```
neutral_threshold = 0.05   (нижній поріг утримання)

NEUTRAL → BUY:   score >= thr_buy         (вхід)
NEUTRAL → SELL:  score <= -thr_sell       (вхід)

BUY → HOLD:      score >= neutral_thr     (утримання)
BUY → EXIT:      score < neutral_thr      (вихід за слабким сигналом)
BUY → SELL FLIP: score <= -thr_sell       (розворот на сильному сигналі)
```

### 3.6 Side Bias Penalty (анти-однобічність)

**Мета:** Prevent SELL bias або BUY bias у вікні часу

```
Параметри:
  window_sec     = 420 сек (7 хвилин)
  target_ratio   = 0.72  (72% від одного напрямку — max допустимо)
  penalty_factor = 0.25  (max штраф на поріг)
  min_intents    = 18    (мінімум угод для активації)

Якщо sell_share > 0.72:
    excess   = sell_share - 0.72
    max_exc  = 1.0 - 0.72 = 0.28
    scaling  = excess / max_exc        ∈ [0, 1]
    penalty  = 0.25 × scaling          ∈ [0, 0.25]
    sell_bias_mult = 1.0 + penalty     ∈ [1.0, 1.25]
    → thr_sell = signal_threshold × regime_factor × sell_bias_mult
```

### 3.7 Delta Price нормалізація (pre-scoring)

```
delta_price_cap_pct = 0.02   (2% cap)

dp_pct  = delta_price / price          (відсоткова зміна)
dp_pct  = clamp(dp_pct, -0.02, +0.02) (hard cap)
dp_norm = dp_pct / 0.02               ∈ [-1, +1]
```

---

## 4. СТРАТЕГІЯ MEAN REVERSION — СКОРИНГ

### 4.1 Тип скорингу

MR не використовує SignalScoreV2. Вона базується на технічному аналізі:

**Сигнал генерується коли:**
```
SHORT:  price > BB_upper  AND  pct_b > entry_threshold  AND  RSI > rsi_overbought
LONG:   price < BB_lower  AND  pct_b < (1 - entry_threshold)  AND  RSI < rsi_oversold
```

### 4.2 Bollinger Bands

```
BB_mid   = SMA(close, bb_window)
BB_std   = STD(close, bb_window)
BB_upper = BB_mid + bb_num_std × BB_std
BB_lower = BB_mid - bb_num_std × BB_std
BB_width = (BB_upper - BB_lower) / BB_mid

pct_b    = (close - BB_lower) / (BB_upper - BB_lower)   ∈ [0, 1]
```

### 4.3 Confidence Score (MR)

```
confidence ∈ [0, 1]  (передається як score в EVT:STRATEGY_SIGNAL_PRODUCED)

Логіка форування:
  При BB breach: confidence = пропорційно до pct_b відхилення
  confidence > 0.5 → сигнал actionable
```

### 4.4 Параметри по символах

| Символ    | bb_window | bb_std | entry_threshold | RSI_ob/os | SL ATR | TP  |
|-----------|-----------|--------|-----------------|-----------|--------|-----|
| DOGEUSDT  | 20        | 2.1    | 0.05            | 70/30     | 1.5×   | outer band |
| XRPUSDT   | 40        | 2.5    | 0.05            | 70/30     | 2.0×   | mid band |
| BTCUSDT   | 40        | 1.6    | 0.24            | 70/30     | 2.0×   | mid band |
| SOLUSDT   | 24        | 1.8    | 0.12            | 70/30     | 2.0×   | mid band |

### 4.5 Режимний фільтр для MR

```
allowed_regimes (DOGE): ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH", "MEAN_REVERSION"]

FLAT класифікація:
  ATR/price > 0.003 → FLAT_HIGH
  ATR/price < 0.001 → FLAT_LOW
  інше             → FLAT_NORMAL

Поточний режим DOGE: LOW_VOLATILITY
→ LOW_VOLATILITY не у allowed_regimes → сигнали заблоковані!
```

---

## 5. RISK SCORING — ПОРТФЕЛЬНИЙ РІВЕНЬ

### 5.1 L1: Daily Gate (портфельний circuit breaker)

**Файл:** `apps/reference/domains/risk_management/daily_gate.py`

```
Заблокує ALL торгівлю якщо:
  daily_drawdown_pct >= max_drawdown_pct (10.0%)
  OR daily_realized_loss >= max_realized_loss_usd ($250)

Reset: щодня о 00:00 UTC
```

**Поточний стан:** `disable_daily_loss_limit=true` (вимкнено)

### 5.2 L2: Instrument Risk Score

**Файл:** `apps/reference/domains/risk_management/risk_management.py`

#### Формула:

```
delta_price_pct = |delta_price| / price              (нормалізована зміна ціни)

risk_score = delta_price_pct × w_dp
           + |obi|            × w_obi
           + |tfi|            × w_tfi
           + (1 - absorption) × w_abs    [тільки якщо use_absorption_penalty=True]

risk_score = clamp(risk_score, 0, 1)
```

#### Ваги:

| Компонент           | Вага  | Конфіг                              |
|---------------------|-------|-------------------------------------|
| `delta_price_pct`   | 0.10  | `risk_score_weights.delta_price_pct`|
| `|obi|`             | 0.30  | `risk_score_weights.obi`            |
| `|tfi|`             | 0.30  | `risk_score_weights.tfi`            |
| `(1-absorption)`    | 0.30  | `risk_score_weights.absorption_inverse` |
| **Разом**           | **1.00** (без absorption: 0.70) |

> ⚠️ `use_absorption_penalty = false` → absorption_inverse_weight = 0
> При цьому решта ваг НЕ перерахована: wabs = 0.70 (не 1.0)

#### Поріг:
```
is_trading_allowed = risk_score <= max_risk_score (0.96)
```

#### Інтерпретація:
При відключеному absorption максимальний score = 0.70 (якщо OBI=TFI=1.0, delta_price=100%).
Тобто поріг 0.96 фактично **ніколи не досягається** при поточній конфігурації.

---

## 6. ПОВНІ КОНФІГУРАЦІЙНІ ЗНАЧЕННЯ

### 6.1 Aurora Signal Weights (глобальні)

```yaml
signal_weights:
  obi: 0.42            # ГОЛОВНИЙ сигнал (42% ваги)
  tfi: 0.15
  delta_price: 0.15
  ema_bias: 0.15
  depth_imbalance: -0.15   # НЕГАТИВНА вага
  macro_resid: 0.10
  volume_spike: 0.10
  volatility_state: 0.10

feature_neutrals:
  obi: 0.0
  tfi: 0.0
  delta_price: 0.0
  ema_bias: 0.5
  volume_spike: 0.0
  volatility_state: 0.0
  depth_imbalance: 0.5
  macro_sync: 0.5
  macro_resid: 0.0
```

### 6.2 Aurora per-symbol weights (BTCUSDT)

```yaml
BTCUSDT weights:          SOLUSDT weights:         ETHUSDT weights:
  ema_bias: 0.20            ema_bias: 0.20            ema_bias: 0.20
  volume_spike: 0.15        volume_spike: 0.20        volume_spike: 0.20
  macro_resid: 0.15         macro_resid: 0.25         macro_resid: 0.25
  obi: 0.20                 obi: 0.15                 obi: 0.15
  tfi: 0.10                 tfi: 0.09                 tfi: 0.093
  volatility_state: 0.10    volatility_state: 0.05    volatility_state: 0.036
  depth_imbalance: -0.05    depth_imbalance: -0.20    depth_imbalance: -0.256
  delta_price: 0.05         delta_price: 0.10         delta_price: 0.10
```

### 6.3 Порогові значення

```yaml
signal_threshold: 0.162          # Глобальний Aurora вхід
neutral_threshold: 0.05          # Hysteresis нижній поріг
delta_price_cap_pct: 0.02        # 2% cap на delta_price

regime_threshold_multipliers:    # Множники до 0.162
  HIGH_VOLATILITY: 0.20   → eff=0.0324
  LOW_VOLATILITY:  0.12   → eff=0.0194
  MEAN_REVERSION:  0.16   → eff=0.0259
  TREND_UP:        0.14   → eff=0.0227
  TREND_DOWN:      0.14   → eff=0.0227
  UNCERTAIN:       0.18   → eff=0.0292
  DEFAULT:         0.16   → eff=0.0259

regime_thresholds (абсолютні блокувальники):
  LOW_VOLATILITY: 99.0     # Блок для Aurora (LOW_VOL = MR-only)
  UNCERTAIN:      99.0     # Блок для Aurora
```

### 6.4 Risk Score Weights

```yaml
risk_score_weights:
  delta_price_pct: 0.10
  obi: 0.30
  tfi: 0.30
  absorption_inverse: 0.30   # ВИМКНЕНО (use_absorption_penalty=false)

max_risk_score: 0.96         # Поріг дозволу торгівлі
```

### 6.5 Regime Detection

```yaml
# SMA Trend model:
sma_short_period: 8
sma_long_period: 24
confidence_multiplier: 28.0
confidence_min: 0.42
uncertain_cutoff: 0.52

# Volatility model:
atr_period: 14
atr_sma_length: 32
threshold_multiplier: 1.3
high_vol_confidence_multiplier: 2.0
low_vol_confidence_multiplier: 3.0

# Hysteresis:
hysteresis_bars: 4          # 4 бари підтвердження перед зміною режиму
vol_slope_gate_eps: -0.0035  # Slope gate
```

---

## 7. ГЕЙТИ ТА ФІЛЬТРИ

### 7.1 Повна карта гейтів Aurora

```
1. WARMUP GATE
   Умова: всі essential_features ready
   Блокує: будь-яке рішення до завершення warmup (~46 барів)

2. DAILY RISK GATE (L1)
   Умова: drawdown_pct < 10% та realized_loss < $250
   Блокує: ВСЕ торгування (всі символи)
   Стан: ВИМКНЕНО (disable_daily_loss_limit=true)

3. INSTRUMENT RISK GATE (L2)
   Умова: risk_score <= 0.96
   Блокує: конкретний символ
   Поточна ефективність: майже завжди проходить (max=0.70 < 0.96)

4. LIQUIDITY GATE
   Умова: liquidity_kappa >= kappa_min (0.1-0.2 per symbol)
   Блокує: вхід при низькій ліквідності

5. REGIME GATE
   Умова: поточний режим in allowed_regimes
   Aurora дозволяє: TREND_UP, TREND_DOWN, HIGH_VOL, MR, LOW_VOL (per-symbol)
   Aurora блокує: UNCERTAIN (threshold=99.0 → неможливо досягти)
   MR дозволяє: FLAT_LOW, FLAT_NORMAL, FLAT_HIGH, MR

6. ANCHOR SHOCK VETO
   Умова: macro_resid(BTCUSDT) >= -2.0
   Блокує: BUY сигнали при BTC краші

7. ANTI-FLAT GATE (vol-based)
   Умова: normalized_motion >= anti_flat_sigma (0.48)
   Блокує: входи при дуже тихому ринку

8. ANTI-FOMO GATE
   Умова: normalized_motion <= anti_fomo_sigma (10.5)
   Блокує: входи при надзвичайно сильному русі (snapback risk)

9. HOLDING PERIOD GATE (Anti-Churn)
   Умова: time_in_position >= min_duration_sec
   Глобально: 30 сек
   SOLUSDT: 900 сек (15 хвилин!)
   BTCUSDT: 20 сек

10. RE-ENTRY COOLDOWN
    Умова: time_since_close >= reentry_cooldown_sec
    Глобально: 840 сек (14 хвилин!)
    BTCUSDT: 300 сек

11. SIDE BIAS GATE
    Умова: не перевищено target_ratio (0.72) в window (420 сек)
    Блокує через підняття threshold за допомогою penalty_factor

12. RISK_SCORE_MISSING GATE
    Умова: risk_score повинен бути отриманий до обробки сигналу
    Блокує якщо RISK_RX ще не прийшов або is_trading_allowed=False
```

---

## 8. АРХІТЕКТУРНА ОЦІНКА

### 8.1 Сильні сторони ✅

1. **Чіткий SSOT**: Конфіги є SSOT через typed Pydantic моделі. Відсутня дублікація конфігурацій.

2. **Fail-Closed everywhere**: Відсутня essential фіча → DEFER (не дефолт). Risk ламається → BLOCK. Це правильний підхід для торгової системи.

3. **Net-Zero Scoring**: Центрування навколо neutrals усуває систематичний bias. Це математично коректний підхід.

4. **Explainability chain**: `why_chain` відстежує кожен крок рішення. `psi_vector` зберігає внески фіч.

5. **DirectionStrength Split**: Розділення напрямку та сили — більш просунутий підхід ніж простий weighted sum.

6. **Pure kernel**: `AuroraScoringKernel` — pure function (no side effects). Добре для тестування та shadow mode.

7. **Decimal precision**: Весь скоринг на `decimal.Decimal` — важливо для фінансових розрахунків.

8. **Hysteresis**: 3-зонна логіка (enter/hold/exit) з neutral_threshold усуває flapping.

### 8.2 Проблеми та ризики ⚠️

**КРИТИЧНІ:**

1. **Неузгоджені ваги в risk_score**: `use_absorption_penalty=false` виключає absorption але НЕ перераховує wabs. Реальна сума ваг = 0.70, а не 1.0. Risk score систематично занижений.

2. **regime_thresholds vs regime_threshold_multipliers**: В aurora.yaml є ДВА різних набори:
   - `decision.regime_threshold_multipliers` (множники до base 0.162)
   - `decision.regime_thresholds` (абсолютні порогові значення 99.0 = блок)
   Це може призводити до неочевидної поведінки та плутанини.

3. **Стратегічні прогалини**: BTCUSDT, ETHUSDT, XRPUSDT мають `assignments: []` — вони взагалі не мають активних стратегій. Це, скоріш за все, кроковий стан конфігурації.

4. **DOGEUSDT MR блок**: Поточний режим DOGEUSDT = LOW_VOLATILITY, але MR allowed_regimes = ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH", "MEAN_REVERSION"]. LOW_VOLATILITY ≠ FLAT → сигнали блоковані на рівні режиму навіть після відключення drawdown ліміту.

**СЕРЕДНІ:**

5. **macro_sync deprecated але listed**: Фіча в directional_features з вагою 0 (deprecated) і прокоментована. Краще видалити з конфігу щоб не плутати.

6. **debug print у production**: У `risk_management.py` є `print(f"DEBUG: ...")` в production коді (рядки 132-133). Це не має бути у production бранчі.

7. **Side bias target_ratio = 0.72**: Асиметричний target (72% для однієї сторони mean 28% для другої). Нелогічно в симетричному ринку без directional bias.

**НЕЗНАЧНІ:**

8. `_on_bar_closed_data_only` — порожній метод (pass). Або прибрати або документувати чому.

9. Сигнали для неактивних символів (score > threshold але не emit) кидають попередження "ARBITRATION: symbol not in registry". Краще early-exit.

---

## 9. МАТЕМАТИЧНА ОЦІНКА

### 9.1 Net-Zero Scoring — математична коректність

Формула `score = Σ w_i(x_i − n_i) / Σ|w_i|` **математично коректна** при:
- Всі x_i центровані навколо n_i
- Всі x_i в однаковому масштабі після центрування

**Проблема масштабу:**
Без `signed_v2` трансформацій компоненти різного масштабу:
- `obi ∈ [-1,1]`: компонент w×(x-0) ∈ [-0.42, +0.42]
- `ema_bias ∈ [0,1]`: компонент w×(x-0.5) ∈ [-0.075, +0.075]

`signed_v2` виправляє це:
- `ema_bias` після transform: `2×x-0.5`, компонент w×(x'-0.5) ∈ [-0.15, +0.15] ✅

**Масштаб після трансформації:**
| Фіча | До transform | Після transform | Δ |
|------|-------------|-----------------|---|
| `obi` (signed, n=0) | [-0.42, +0.42] | [-0.42, +0.42] | = |
| `ema_bias` ([0,1], n=0.5) | [-0.075, +0.075] | [-0.15, +0.15] | ×2 ✅ |
| `depth_imbalance` ([0,1], n=0.5) | [-0.075, +0.075] | [-0.15, +0.15] | ×2 ✅ |

### 9.2 DirectionStrength — аналіз

```
final = dir × (1 + 0.5 × strength)

При dir = +0.5, strength = 1.0:
  final = 0.5 × 1.5 = 0.75   (≤ threshold 0.0324)

При dir = +0.2, strength = 0.0:
  final = 0.2 × 1.0 = 0.2    (> threshold 0.0324)
```

**Результат:** `final` потенційно > 1.0 при `dir` близько до 1.0:
`final_max = 1.0 × (1 + 0.5 × 1.0) = 1.5`

SignalScoreV2 клампує score до [-1, +1] після нормалізації, але `final_score` у DirectionStrength **не клампується**. Це означає, що `final_score ∈ [-1.5, +1.5]` теоретично.

Для порогу 0.0324 це не критично, але формально порушує [-1,+1] контракт.

### 9.3 Kelly Fraction (sizing)

**Конфіг:**
```yaml
kelly:
  base_probability: 0.5
  kelly_cap: 0.25       (max 25% від капіталу)
  kelly_alpha: 0.8      (fractional kelly)
  payoff_ratio_r: 1.5   (reward:risk ratio)
  p_min: 0.45
  p_max: 0.65
  uplift_factor: 0.20   (сигнал підвищує p на max 20%)
```

**Формула Kelly:**
```
p = base_prob + score × uplift_factor   (де score ∈ [0,1])
p = clamp(p, p_min, p_max)

f* = p - (1-p)/r    (Full Kelly)
f  = f* × kelly_alpha × kelly_cap   (Fractional)
```

При `p=0.5, r=1.5`:
```
f* = 0.5 - 0.5/1.5 = 0.5 - 0.333 = 0.167   (16.7% Full Kelly)
f  = 0.167 × 0.8 = 0.133   (13.3% Fractional Kelly)
```

Це стандартне консервативне fractional Kelly. Математично коректно.

### 9.4 Risk Score — оцінка адекватності

**При поточних налаштуваннях** (`use_absorption_penalty=false`):

```
risk_score_max = 1.0 × 0.10 + 1.0 × 0.30 + 1.0 × 0.30 = 0.70

Граница блоку: risk_score > 0.96

→ risk_score ніколи не досягне 0.96 при поточних вагах!
→ Risk gate L2 фактично ЗАВЖДИ ПРОПУСКАЄ.
```

**Висновок:** Risk gate є неефективним при `use_absorption_penalty=false`. Поріг 0.96 потрібно знизити до ≤ 0.60 або увімкнути absorption.

---

## 10. КОРОТКИЙ ПІДСУМОК

### Що зараз скоринг робить добре:
- Математично обґрунтований Net-Zero підхід
- Fail-closed поведінка скрізь
- Зрозуміла explainability chain
- Гарна модульність (pure kernel)

### Що не працює або субоптимально:
1. **BTCUSDT/ETHUSDT/XRPUSDT не торгують** (порожні assignments)
2. **DOGEUSDT MR заблоковано режимом** (LOW_VOLATILITY не в allowed_regimes)
3. **Risk score gate фактично вимкнений** (max реальний score 0.70 < поріг 0.96)
4. **Асиметричні ваги** absorption викидається без перерахунку

### Рекомендовані пріоритети:
1. Додати LOW_VOLATILITY до MR allowed_regimes для DOGEUSDT (або очікувати зміни режиму)
2. Перевірити assignments у strategies.yaml — додати потрібні символи
3. Знизити `max_risk_score` до 0.55-0.65 або увімкнути absorption penalty
4. Видалити debug print з production коду

---

*Документ згенеровано на основі аналізу кодової бази та конфігурацій*
*Файли: aurora_scoring_kernel.py, signal_score_v2.py, scoring_direction_strength_v1.py, risk_management.py, aurora.yaml, mean_reversion.yaml, strategies.yaml, domains.yaml*
