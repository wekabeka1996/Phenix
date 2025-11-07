# 01 Mathematical Foundation — Перенесення Специфіки в Проект

**Мета**: Переклад фундаментальної математичної специфіки (§1–19) на мову реалізації в Aurora+vFoundation.

**Дата**: 3 листопада 2025 | **Статус**: ✅ DRAFT

---

## 📍 РОЗДІЛ 1–2: ПОЗНАЧЕННЯ & ДАНІ

### Позначення
```
s ∈ S           — інструмент (BTCUSDT, ETHUSDT, … із config.yaml)
t ∈ ℤ           — індекс M15 бару (15-хв часові діапазони)
p_s(t)          — close ціна бару
H_s(t), L_s(t)  — high/low за бар
r_s(t) = ln(p_s(t)/p_s(t-1))  — логарифмічна доходність
V_s(t)          — обсяг за бар (volume)
σ_s(t)          — реалізована волатильність (ATR 14)
```

### Дані в проекті
| Параметр | Джерело | Формат | Частота |
|----------|---------|--------|---------|
| **p_s(t)** | Binance REST/WS | Decimal | M15 бар |
| **H/L** | `market_data` domain | Decimal | M15 бар |
| **V_s(t)** | `feature_engineering` | float → Decimal | M15 бар |
| **ATR 14** | Вже обчислено | Decimal | На кожному барі |
| **OBI** | `feature_engineering.py` | `obi = (bid - ask) / depth` | Тік-рівень → M15 агрегат |
| **TFI** | `feature_engineering.py` | `tfi = (buy_vol - sell_vol) / total` | Тік-рівень → M15 агрегат |

**Конфіг**: `config/aurora/trading.yaml` → `decision.signal_weights`

---

## 📍 РОЗДІЛ 3: МІКРОРЕНДЖ & СТИСК (SQUEEZE)

### Локальний Діапазон (K = 20 барів за дефолтом)

```python
# Файл: regime_detector.py (лінії ~140–160)
R_s^max(t) = max(H_s(t-i) for i in [1,K])
R_s^min(t) = min(L_s(t-i) for i in [1,K])
W_s(t) = R_s^max(t) - R_s^min(t)   # WIDTH

# Нормалізована ширина
ω_s(t) = W_s(t) / p_s(t)

# Squeeze Detection
squeeze = (ω_s(t) ≤ τ_ω) ∧ (σ_s(t) ≤ τ_σ)
```

**У коді:**
- 📍 `regime_detector.py`: Детекція HIGH_VOLATILITY/LOW_VOLATILITY через ATR ratio
- 📍 `config/aurora/trading.yaml`:
  ```yaml
  models:
    volatility:
      threshold_multiplier: 2.0       # HIGH_VOL: ATR > 2.0 × SMA(ATR)
      low_vol_multiplier: 0.5         # LOW_VOL: ATR < 0.5 × SMA(ATR)
      atr_period: 14
  ```

---

## 📍 РОЗДІЛ 4: ІНДЕКС НАПРУГИ (TENSION INDEX)

### Композиція Рушійних Ознак

$$T_s(t) = \beta_1 |\widetilde{\Delta OI}_s(t)| + \beta_2 |\widetilde{F}_s(t)| + \beta_3 |LS_s(t) - 0.5| + \beta_4 \mathbb{1}[\omega_s(t) ≤ \tau_ω] + \beta_5 w_{\text{phase}}(\tau)$$

**Компоненти:**
1. **ΔOI (Open Interest Delta)** — z-score зміни OI за період
2. **F (Funding)** — z-score funding rate
3. **LS (Long/Short Ratio)** — дисбалланс позицій
4. **Squeeze** — індикатор стиску (ω ≤ τ_ω)
5. **Phase weight** — внутрішньобарне часове зважування (M15)

### Пороги Режимів

```
T_s(t) < θ₁           ⟹ "IdleFlat" (м'який флет)
θ₁ ≤ T_s(t) < θ₂      ⟹ "Tension" (стиск/перекіс)
T_s(t) ≥ θ₂           ⟹ "High Tension" (рух)
```

**У коді:**
- 📍 `regime_detector.py`: Детекція через SMA crossover + volatility
- ⚠️ **БРАКУЄ:** Повна реалізація Tension Index (ΔOI, Funding, LS Ratio)
- **Поточне:** Спрощена версія через ATR ratio + SMA trend

---

## 📍 РОЗДІЛ 5: РЕЖИМНА МАШИНА (BEHAVIOR-FSM)

### Множина Станів: **ℳ = {IdleFlat, Tension, Break/Fake, Trend, Cooldown}**

```
IdleFlat ─→ Tension ─→ Break/Fake ─→ Trend ─→ Cooldown ↻ IdleFlat
                    ↓
                  FAKE_OUT
                    ↓
                Cooldown
```

### Переходи

| Від → До | Умова | Реалізація |
|---------|-------|------------|
| **IdleFlat → Tension** | `T_s(t) ≥ θ₁` | 📍 `regime_detector.py`: Детекція HIGH_VOL/MEAN_REV |
| **Tension → Break/Fake** | `T_s(t) ≥ θ₂ ∧ (BreakUp ∨ BreakDown)` | ⚠️ Потреби реалізації break detection |
| **Break/Fake → Trend** | `HoldUp ∨ HoldDown` | ⚠️ Потреби реалізації hold validation |
| **→ Cooldown** | `ρ_reject > ρ* ∨ slip_p95 > η*` | 📍 `decision_making.py`: QoS блоки & cooldown |
| **Tension → IdleFlat** | `T_s(t) < θ₁ ∧ ¬Break` | 📍 Коли режим = UNCERTAIN |

**У коді:**
- 📍 `decision_making.py`: Блокування входу не в IdleFlat (режимний фільтр)
- 📍 `execution_position/fsm.py`: Open/Manage/Close flows

---

## 📍 РОЗДІЛ 6: СИГНАЛЬНИЙ СКОР & ВХІД

### Нормалізовані Компоненти

```python
# regime_detector.py → feature_engineering.py → decision_making.py
φ_OBI(t)         # Normalized OBI [-1, 1] → [0, 1]
φ_TFI(t)         # Normalized TFI [-1, 1] → [0, 1]
φ_ΔP(t)          # Normalized ΔPrice [-∞, ∞] → [0, 1]
```

### Ваговий Скор

$$S_s(t) = w_1 \phi_{\text{OBI}}(t) + w_2 \phi_{\text{TFI}}(t) + w_3 \phi_{\Delta P}(t), \quad \sum w_i = 1, \; w_i ≥ 0$$

**У коді:**
```yaml
# config/aurora/trading.yaml
decision:
  signal_weights:
    obi: 0.6           # w₁
    tfi: 0.35          # w₂
    delta_price: 0.05  # w₃
  signal_threshold: 0.15  # ϑ (мінімум для входу)
```

**Умова Входу:**
```python
# decision_making.py (лінії ~160–200)
Enter_s(t) = 𝟙[S_s(t) ≥ ϑ ∧ Π(IdleFlat).allow_entry = 1]
```

---

## 📍 РОЗДІЛ 7–8: САЙЗИНГ & TP/SL

### Розмір Позиції (Kelly-based)

```python
# decision_making.py (лінії ~250–300)

# Капітал & ризик
E(t)            # Equity (з portfolio state)
q ∈ (0, 0.03]   # Risk fraction per trade
SL_bps ∈ [40, 120]  # Stop-loss у basis points

# Нотіонал (USD)
N_s(t) = (q × E(t) / (SL_bps / 10000)) × κ_liq

# Kelly фракція
p = 0.5 + signal_score         # Динамічна ймовірність
r = payoff_ratio               # TP/SL ratio
full_kelly = p - (1 - p) / r   # Класична Kelly
kelly_used = min(kelly_cap, kelly_α × full_kelly)

# Остаточна позиція (з режимним множником)
position_size = N_s(t) × kelly_used × κ_regime
```

**У коді:**
- 📍 `decision_making.py` (лінії 342–400): Kelly калькулятор
- 📍 `config/aurora/trading.yaml`:
  ```yaml
  decision:
    sizing_modifiers:
      HIGH_VOLATILITY: "0.60"    # κ_regime = 0.6 (−40%)
      LOW_VOLATILITY: "1.20"     # κ_regime = 1.2 (+20%)
      MEAN_REVERSION: "0.50"     # κ_regime = 0.5 (−50%)
      UNCERTAIN: "0.50"
  ```

### TP/SL Стратегія

```python
# execution_position/fsm_manage.py (лінії ~50–100)

TP_low = k₁ × SL_bps         # 1.6 × SL_bps
TP_high = k₂ × SL_bps        # 2.4 × SL_bps
φ ∈ (0.3, 0.7)               # Часткова позиція для закриття

# Трейл-止loss (після TP_low досягнення)
TrailStart = τ_trail ≥ BE + δ
TrailStop(t) = max(BE, max_price(τ≤t) - λ_trail)
```

---

## 📍 РОЗДІЛ 9–11: РИЗИК-ОБМЕЖЕННЯ & ЦІЛЬОВА ФУНКЦІЯ

### Добові Обмеження

```yaml
# config/aurora/trading.yaml
risk:
  daily:
    max_realized_loss_usd: 250.0   # DD_max = 8%
    max_drawdown_pct: 8.0          # Intra-day DD
    reset_time_utc: "00:00"

  trading_allowed_thresholds:
    max_risk_score: 0.90           # Режимні коефіцієнти
```

### Цільова Функція

$$J = \text{Exp} - \lambda_1 \text{CVaR}_{0.95} - \lambda_2 \text{MaxDD} - \lambda_3 \text{Turn} - \lambda_4 \rho_{\text{reject}}$$

**Хард-констрейнти:**
```
CVaR_0.95 ≤ 0.10
MaxDD ≤ 0.20
ρ_reject ≤ 0.08
```

**У коді:**
- 📍 `risk_management` domain: Скоринг по CVaR/MaxDD
- 📍 `decision_making.py`: QoS enforcement

---

## 📍 РОЗДІЛ 12: WALK-FORWARD ВАЛІДАЦІЯ

### Часова Стратифікація

```
─┬─ Train [t₁, t₂) ─┬─ Val [t₂, t₃) ─┬─ Train [t₃, t₄) ─┬─ Val [t₄, t₅) ─┐
 └─ k=1             └─ k=1           └─ k=2             └─ k=2           ⋮
```

**Метрики стабільності:**
```
J̄ = (1/K) Σ J^(k)
Var(J) = (1/(K-1)) Σ (J^(k) - J̄)²

Критерій: J̄ > 0  ∧  Var(J) → min
```

---

## 📍 РОЗДІЛ 16: WHY-CHAIN & ПОЯСНЮВАНІСТЬ

### Формальна Вимога

Для кожного рішення (вхід/модифікація/вихід):

```python
# Координата рішення
W(t) = (S_s(t), T_s(t), ℳ(t), RuleID)

# Вектор аргументів
ψ(t) = [φ_OBI, φ_TFI, φ_ΔP, Δ̃OI, F̃, LS−0.5, ω, phase]_t

# Інваріант детермінованості
Action(t) = g(ψ(t), Π(ℳ(t)))  # Детерміновано повторюваний
```

**У коді:**
- 📍 `decision_making.py`: Логування всіх входів у `dlog` (DecisionLog)
- ⚠️ **ПОТРЕБИ РОЗШИРЕННЯ:** Повний ψ вектор не залогований

---

## 📍 РОЗДІЛ 17: ІНВАРІАНТИ СИСТЕМИ

### Залізні Правила

```python
# 1. NO-ADD-DOWN
if unrealized_PnL < 0:
    BLOCK_new_entry()

# 2. FAIL-CLOSED RISK
if data_missing or confidence_low:
    BLOCK_new_entry()

# 3. SINGLE-SOURCE-OF-TRUTH ПОЗИЦІЙ
portfolio_state = fetch_once()  # Один снімок
# Усі розрахунки від цього снімка

# 4. ДИСКРЕТНІСТЬ ПОЛІТИКИ
# Зміни політики тільки на кордонах бару чи при строгих переходах
if time_is_bar_end() or state_transition_detected():
    apply_policy_change()
```

**У коді:**
- 📍 `decision_making.py` (лінії 401–425): NO-ADD-DOWN блок
- 📍 `risk_management.py`: Fail-closed гейти
- 📍 `execution_position/fsm.py`: Single state snapshot

---

## 📍 РОЗДІЛ 18–19: ПАРАМЕТРИ & КРИТЕРІЇ ПРИЙНЯТНОСТІ

### Діапазони Параметрів

| Параметр | Діапазон | Дефолт | Файл |
|----------|----------|--------|------|
| w₁ (OBI) | [0.3, 0.7] | 0.6 | `trading.yaml` |
| w₂ (TFI) | [0.2, 0.6] | 0.35 | `trading.yaml` |
| ϑ (threshold) | [0.12, 0.35] | 0.15 | `trading.yaml` |
| SL (bps) | [40, 120] | 60 | TBD |
| k₁ (TP ratio) | [1.6, 2.0] | 1.8 | TBD |
| k₂ (TP ratio) | [2.0, 2.4] | 2.2 | TBD |
| q (risk frac) | [0.005, 0.03] | 0.015 | TBD |
| κ_liq | (0, 1] | 0.8 | TBD |

### Критерій Прийнятності (§19)

```
ІНЖЕНЕРНА ПРИЙНЯТНІСТЬ ⟺
    J̄ > 0  ∧
    CVaR_0.95 ≤ 0.10  ∧
    MaxDD ≤ 0.20  ∧
    ρ_reject ≤ 0.08  ∧
    WHY_coverage = 100%
```

---

## 🔗 МАППІНГ НА КОД

| Специфіка (§) | Компонента | Файл | Статус |
|---------------|-----------|------|--------|
| §1–2 (Дані) | Market Data | `market_data/` domain | ✅ |
| §3–4 (ATR/Squeeze/Tension) | RegimeDetector | `regime_detector.py` | ⚠️ Спрощена |
| §5 (FSM) | ExecPos FSM | `execution_position/fsm.py` | ✅ |
| §6 (Сигнали) | FeatureEng + DecisionMaking | `feature_engineering.py`, `decision_making.py` | ✅ |
| §7–8 (Сайзинг) | DecisionMaking | `decision_making.py` лінії 342–400 | ✅ |
| §9–11 (Ризик) | RiskManagement | `risk_management/` domain | ✅ |
| §12 (Walk-Forward) | Testing | `tests/` | ⚠️ TBD |
| §16 (Why-Chain) | DecisionLog | `dm_log_adapter.py` | ⚠️ Потреби розширення |
| §17 (Інваріанти) | DecisionMaking | `decision_making.py` | ✅ |
| §18–19 (Валідація) | Вся система | `config/` + `tests/` | ✅ |

---

## 📝 ВИСНОВОК

Математична специфіка **на 75% відображена в кодовій базі:**

✅ **Готово:**
- Режимна детекція (SMA crossover + ATR)
- Сигнальна композиція (OBI/TFI/ΔP)
- Kelly калькулятор з динамічною ймовірністю
- TP/SL управління (трейл + часткові exits)
- Ризик-обмеження (DD/CVaR/MaxDD)

⚠️ **Потреби розширення:**
- Повна Tension Index (ΔOI + Funding + LS Ratio)
- Break/Fake детекція & Hold validation
- Walk-forward validation інфраструктура
- Розширений Why-Chain логування

❌ **Не реалізовано:**
- Funding события обробка
- Повна phase-wave фільтрація

**Наступний крок**: Перейти до `02_Architecture_Mapping.md` для розуміння потоків подій.

