# SCORING SYSTEM PASSPORT
## Phenix Aurora Trading System — Повний паспорт системи скорингу
**Версія документа:** 2.0.0
**Дата:** 2026-03-12
**Статус:** Production (Phase 9)

> **AUDIT SUMMARY**
> - **Document path:** `config/docs/scoring_passport.md`
> - **Audit mode:** Code-driven deep sync
> - **Major drifts found:** 
>   1. L3 Signal Scoring now splits into Linear (`v2`) and Phase 9 Quadratic (`quadratic`) modes.
>   2. `QuadraticScoringKernel` introduced as the new scoring foundation, utilizing `pillar_sum` and non-linear `Exposure = sign(Σ) × Σ²` transforms.
>   3. Shield Cascade (MemoryShield, DangerZone, etc.) introduced to act as attenuators before exposure calculation.
>   4. L2 Risk Score absorption penalty math updated (split into `proxy` toxicity and `feature` terms).
>   5. `macro_sync` officially deprecated from active directional features.
> - **Overall confidence:** HIGH.

---

## ЗМІСТ

1. [Загальна архітектура](#1-загальна-архітектура)
2. [Ланцюжок скорингу](#2-ланцюжок-скорингу)
3. [Стратегія Aurora — Повний скоринг (Phase 9)](#3-стратегія-aurora--повний-скоринг-phase-9)
4. [Стратегія Mean Reversion — Скоринг](#4-стратегія-mean-reversion--скоринг)
5. [Risk Scoring — Портфельний рівень](#5-risk-scoring--портфельний-рівень)
6. [Повні конфігураційні значення](#6-повні-конфігураційні-значення)
7. [Гейти та фільтри](#7-гейти-та-фільтри)
8. [Архітектурна оцінка](#8-архітектурна-оцінка)

---

## 1. ЗАГАЛЬНА АРХІТЕКТУРА

### 1.1 Структура скорингу — три рівні

```
┌─────────────────────────────────────────────────────────────┐
│                    SCORING SYSTEM                           │
│                                                             │
│  РІВЕНЬ 1: Portfolio RISK GATE                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ DailyRiskState.can_open()                           │   │
│  │ Inputs: daily_drawdown, daily_loss                  │   │
│  │ Output: ALLOW / BLOCK (вся торгівля)                │   │
│  └─────────────────────────────────────────────────────┘   │
│                           ↓                                 │
│  РІВЕНЬ 2: INSTRUMENT RISK SCORE                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ risk_score = f(dp_pct, obi, tfi, abs_proxy, abs_ft) │   │
│  │ Gate: risk_score <= max_risk_score (0.96)           │   │
│  └─────────────────────────────────────────────────────┘   │
│                           ↓                                 │
│  РІВЕНЬ 3: SIGNAL SCORING (per strategy)                   │
│  ┌──────────────────────┐  ┌────────────────────────────┐  │
│  │  AURORA STRATEGY     │  │  MEAN REVERSION STRATEGY   │  │
│  │  Phase 9 Quadratic   │  │  MeanReversionStrategy     │  │
│  │  or Linear (v2)      │  │  confidence ∈ [0,1]        │  │
│  └──────────────────────┘  └────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Розподіл символів по стратегіях

Стратегії розподіляються по символах через конфігурації у `strategies.yaml` та `aurora.yaml` (`assets`).
> **Контракт:** Якщо символ не вказаний як активний (enabled: true) для конкретної стратегії, система повністю ігнорує розрахунок сигналів цієї стратегії для даного символу.

---

## 2. ЛАНЦЮЖОК СКОРИНГУ

### 2.1 Повний pipeline (Aurora)

```
FE: FeatureEngineering (Pillars & Features)
  └─ emit EVT:BAR_CLOSED + CMD:PROCESS_STRATEGY
       │
       ▼
RiskManagement
  ├─ [L1] DailyGate.can_open() → drawdown/loss check
  ├─ [L2] risk_score computation (Instrument Risk)
  └─ emit EVT:RISK_ASSESSMENT_COMPLETED {is_trading_allowed, risk_score}
       │
       ▼
DecisionMaking._make_decision_for_symbol()
  ├─ [A1] Resolve requested rollout (v2_live, quadratic_live, quadratic_shadow)
  ├─ [A2] Evaluate Shields Cascade (MemoryShield, DangerZone)
  ├─ [A3] Scoring Kernel (QuadraticScoringKernel або AuroraScoringKernel)
  │       ├─ pillar_sum injection (для Quadratic)
  │       ├─ Exposure = sign(Σ) × Σ² × shield_multiplier
  │       ├─ Hysteresis & Side bias penalty
  │       └─ Side determination (buy/sell/neutral)
  │
  └─ Objective Engine (Score Modulation)
       ├─ [O1] Evaluate Cost, Risk, Edge, Execution, Info
       ├─ [O2] Map to Multiplier via Sigmoid Function
       └─ [O3] final_score = kernel_score × multiplier
```

---

## 3. СТРАТЕГІЯ AURORA — ПОВНИЙ СКОРИНГ (PHASE 9)

**Type:** `v2` (Linear fallback) / `quadratic` (Phase 9)
**Logic Owner:** `QuadraticScoringKernel` / `AuroraScoringKernel`
**Code Reference:** `apps/reference/domains/decision_making/quadratic_scoring_kernel.py`

### 3.1 Phase 9: The Quadratic Brain (QuadraticScoringKernel)

Новий SSOT-скоринг конвертує спрямовану впевненість (`pillar_sum` або `linear_score`) у нелінійну експозицію.

**Формула експозиції:**
```
Exposure = sign(Σ) × Σ² × shield_multiplier
```

**Де:**
- `Σ` (Sigma) = зважена сума піларів або лінійний скор ∈ [-1, +1]
- `shield_multiplier` ∈ [0, 1] (згасання від щитів: MemoryShield, DangerZone)

**Математичний ефект:**
- Слабка впевненість (|Σ| < 0.3) → близьконульова експозиція (hesitation penalty).
- Сильна впевненість (|Σ| > 0.7) → агресивне масштабування (conviction reward).
- Знак зберігається для визначення long vs short.
- Гладка, диференційовна функція без стрибків.

### 3.2 Linear Score Fallback (AuroraScoringKernel / v2)

Якщо `scoring_version: "v2"`, використовується лінійний DirectionStrength скоринг.

```
dir_score      = SignalScoreV2(directional_features)    ∈ [-1, +1]
strength_score = SignalScoreV2(strength_features)        ∈ [0, cap=1.0]
final_score    = dir_score × (1 + α × strength_score)
```
- **Net-Zero**: кожна фіча центрується навколо свого neutralного значення (наприклад `ema_bias: 0.5`).
- Відсутня essential фіча → `DEFER` (не 0, а відмова).
- **signed_v2**: `[0,1]` фічі розтягуються до `[-1, +1]` через `2×x-0.5`.

### 3.3 Ваги сигналів та Фічі (config: aurora.yaml)

**Status:** `ACTIVE` (впливає на `v2_live` або як fallback для `pillar_sum`)

| Фіча              | Вага w  | Нейтраль | Група        | Status     |
|-------------------|---------|----------|--------------|------------|
| `obi`             | +0.42   | 0.0      | directional  | ACTIVE     |
| `tfi`             | +0.15   | 0.0      | directional  | ACTIVE     |
| `delta_price`     | +0.15   | 0.0      | directional  | ACTIVE     |
| `ema_bias`        | +0.15   | 0.5      | directional  | ACTIVE     |
| `depth_imbalance` | -0.15   | 0.5      | directional  | ACTIVE     |
| `macro_resid`     | +0.10   | 0.0      | directional  | ACTIVE     |
| `macro_sync`      | -       | 0.5      | telemetry    | **LEGACY** |
| `absorption`      | 0.0     | 0.0      | directional  | ACTIVE (signed) |
| `volume_spike`    | +0.10   | 0.0      | strength     | ACTIVE     |
| `volatility_state`| +0.10   | 0.0      | strength     | ACTIVE     |

> ⚠️ `depth_imbalance` має від'ємну вагу: high depth_imbalance (ASK dominance) = sell pressure.
> ⚠️ `macro_sync` офіційно deprecated для скорингу, залишено лише для телеметрії.

### 3.4 Порогові значення, Режими та Hysteresis

```yaml
signal_threshold: 0.162
neutral_threshold: 0.05
```

**Режимний множник (`regime_threshold_multipliers`):**
Базовий поріг множиться на фактор режиму:
- `HIGH_VOLATILITY`: 0.20
- `LOW_VOLATILITY`: 0.12 (в `regime_thresholds` може стояти 99.0 = повний блок)
- `MEAN_REVERSION`: 0.16
- `TREND_UP`: 0.14
- `TREND_DOWN`: 0.14
- `UNCERTAIN`: 0.18 (зазвичай блокується через 99.0)

**Hysteresis (3-зонна логіка):**
```
NEUTRAL → BUY:   score >= thr_buy
BUY → HOLD:      score >= neutral_thr
BUY → EXIT:      score < neutral_thr
```

### 3.5 Side Bias Penalty

Захист від однобічності. Якщо частка позицій одного напрямку (напр., SELL) перевищує `target_ratio` (0.72) у вікні (420 сек), поріг для цього напрямку підвищується на величину `penalty_factor`.

---

## 4. СТРАТЕГІЯ MEAN REVERSION — СКОРИНГ

**Type:** Bollinger Band Technical Analysis
**Logic Owner:** `MeanReversionStrategy`

Стратегія базується на пробоях Bollinger Bands:
```
SHORT:  price > BB_upper  AND  pct_b > entry_threshold
LONG:   price < BB_lower  AND  pct_b < (1 - entry_threshold)
```

**Актуальні параметри (mean_reversion.yaml):**
| Символ   | bb_window | bb_std | entry_threshold | Allowed Regimes |
|----------|-----------|--------|-----------------|-----------------|
| DOGEUSDT | 40        | 2.5    | 0.05            | FLAT_LOW, FLAT_NORMAL, FLAT_HIGH, MR |
| XRPUSDT  | 40        | 2.5    | 0.05            | FLAT_LOW, FLAT_NORMAL, FLAT_HIGH, MR |
| BTCUSDT  | 40        | 1.6    | 0.24            | FLAT_LOW, FLAT_NORMAL, FLAT_HIGH, MR |
| SOLUSDT  | 24        | 1.8    | 0.12            | FLAT_LOW, FLAT_NORMAL, FLAT_HIGH, MR |

---

## 5. RISK SCORING — ПОРТФЕЛЬНИЙ РІВЕНЬ

### 5.1 L1: Daily Gate (Portfolio Circuit Breaker)
**Code Reference:** `apps/reference/domains/risk_management/daily_gate.py`

Заблокує ВСЮ торгівлю якщо:
- `daily_drawdown_pct >= max_drawdown_pct`
- АБО `daily_realized_loss >= max_realized_loss_usd`

### 5.2 L2: Instrument Risk Score
**Code Reference:** `apps/reference/domains/risk_management/risk_management.py`

Формула зазнала змін для безпечної інтеграції absorption toxicity proxy:
```python
delta_price_pct = |delta_price| / price

# Source = proxy
applied_toxicity = |tfi| * clip(delta_price_pct / absorption_dp_cap_pct, 0, 1) * w_abs_inv
# Source = feature
applied_feature = clip(|absorption|, min, max) * w_abs_feature

risk_score = delta_price_pct * w_dp
           + |obi| * w_obi
           + |tfi| * w_tfi
           + applied_toxicity
           + applied_feature

risk_score = clamp(risk_score, 0, 1)
```

**Ваги (`risk_score_weights`):**
- `delta_price_pct`: 0.10
- `obi`: 0.30
- `tfi`: 0.30
- `absorption_inverse`: 0.30 (proxy weight)
- `absorption_feature`: 0.0 (direct feature weight)

Гейт: `is_trading_allowed = risk_score <= max_risk_score (0.96)`.

---

## 6. ПОВНІ КОНФІГУРАЦІЙНІ ЗНАЧЕННЯ

Звертатись до SSOT-файлів:
- `config/aurora/strategies/aurora.yaml` — для ваг та threshold-ів `Aurora`.
- `config/aurora/strategies/mean_reversion.yaml` — для параметрів `Mean Reversion`.
- `config/aurora/domains.yaml` — для `RiskManagement` налаштувань.

---

## 7. ГЕЙТИ ТА ФІЛЬТРИ

1. **WARMUP GATE**: Всі essential_features (або пілари) мають бути ready.
2. **DAILY RISK GATE (L1)**: Загальносистемний блок за просадками.
3. **INSTRUMENT RISK GATE (L2)**: Блок конкретного символу, якщо risk_score > 0.96.
4. **SHIELD CASCADE (Phase 9)**: 
   - `MemoryShield`: Приглушує сигнал на основі історичних результатів у поточних станах.
   - `DangerZone`: Жорсткі блоки або штрафи у небезпечних макро-станах.
5. **LIQUIDITY GATE**: `liquidity_kappa >= kappa_min`.
6. **REGIME GATE**: Перевірка `regime_thresholds` (99.0 = блок) або `allowed_regimes`.
7. **HOLDING PERIOD GATE (Anti-Churn)**: Запобігає надто швидким виходам (напр., `min_duration_sec: 30`).
8. **RE-ENTRY COOLDOWN**: Охолодження після закриття (напр., `300` сек для BTCUSDT).

---

## 8. АРХІТЕКТУРНА ОЦІНКА

### 8.1 Сильні сторони ✅
1. **Phase 9 Quadratic Brain**: Нелінійний скілинг експозиції (Σ²) створює природну зону вагань та винагороду за високу впевненість.
2. **Fail-Closed Everywhere**: Відсутність піларів або фіч викликає DEFER, а не 0.
3. **Net-Zero Scoring**: Математично коректний підхід у v2 (центрування навколо neutrals).
4. **Separation of Concerns**: `QuadraticScoringKernel` є чистою математичною функцією, незалежною від стейту (стейт передається ззовні).

### 8.2 Дріфт та Застереження ⚠️
1. **scoring_version Fallbacks**: В `aurora.yaml` наразі вказано `scoring_version: "v2"`, однак логіка маршрутизації (`resolve_requested_quadratic_rollout`) може підміняти його на `quadratic_shadow` або `quadratic_live`. 
2. **Absorption Risk Proxy**: Оригінальна фіча `absorption` не використовувалась безпосередньо у L2 ризику до появи `absorption_penalty_source`, замість неї рахувалась directionless toxicity через `tfi`.
3. **Macro Sync Deprecation**: `macro_sync` офіційно вилучено зі скорингу (замінено на `macro_resid`), але його нейтралі все ще наявні у конфігах для телеметрії.
