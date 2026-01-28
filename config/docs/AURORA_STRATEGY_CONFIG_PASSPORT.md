# 📄 Паспорт конфігурації: aurora/strategies/aurora.yaml (Strategy Profile SSOT)

## 🔍 Загальний опис блоку

Блок `aurora` — це Single Source of Truth (SSOT) для стратегії Aurora. Містить глобальну політику сигналізації, параметри прийняття рішень та перевизначення для конкретних інструментів (ETHUSDT, SOLUSDT, BTCUSDT). Стратегія побудована на барах (5-хвилинних), використовує мультисигнальний alpha engine з режимною обізнаністю.

**CFG-STRATEGY-SSOT-FREEZE-02:** Цей файл — єдине джерело істини для Aurora. Політика не мусить міститися в `trading.yaml` або `domains.yaml`.

**Registry:** Який інструмент призначена Aurora визначає `strategies_registry.assignments` в `strategies.yaml`.

---

## 🛠 Деталізація основних полів

| Поле | Тип | Pydantic Модель | Статус | Роль у проекті |
|---|---|---|---|---|
| `enabled` | `bool` | ✅ `AuroraStrategyConfig.enabled` | 🟢 Active | Feature flag для увімкнення/вимкнення стратегії |
| `legacy_tick_path_enabled` | `bool` | ✅ `AuroraStrategyConfig.legacy_tick_path_enabled` | 🟡 Deprecated | Контроль міграції на нову архітектуру |
| `type` | `str` | ✅ `AuroraStrategyConfig.type` | 🟢 Active | Тип стратегії (`bar_driven`) |
| `timeframe_sec` | `int` | ✅ `AuroraStrategyConfig.timeframe_sec` | 🟢 Active | Таймфрейм для барів (300s = 5m) |
| `execution.entry_order_type` | `str` | ✅ `StrategyExecutionConfig.entry_order_type` | 🟢 Active | Тип ордера (LIMIT/MARKET) |
| `execution.entry_tif` | `str` | ✅ `StrategyExecutionConfig.entry_tif` | 🟢 Active | Time-in-Force для LIMIT ордерів |
| `decision.signal_threshold` | `float` | ✅ `DecisionConfig.signal_threshold` | 🔴 **Critical** | Глобальний поріг входу (PRODUCTION MUST OVERRIDE) |
| `decision.neutral_threshold` | `float` | ✅ `DecisionConfig.neutral_threshold` | 🟢 Active | Поріг утримання позиції |
| `decision.cooldown_sec` | `int` | ✅ `DecisionConfig.cooldown_sec` | 🟡 Deprecated | Глобальна затримка (per-instrument краще) |
| `decision.holding_period` | `object` | ✅ `HoldingPeriodConfig` | 🟢 Active | Anti-HFT затримка утримання |
| `decision.reentry_cooldown_sec` | `int` | ✅ `DecisionConfig.reentry_cooldown_sec` | 🟢 Active | Anti-ping-pong затримка повторного входу |
| `decision.gates` | `object` | ✅ `VolAdjGatesConfig` | 🟢 Active | VOL-ADJ-GATES-01: блокування мертвих/екстремальних ринків |

---

## 📋 Детальний розбір критичних полів

### 1. `aurora.enabled` (Основна активація)
* **Суть:** Включає/вимикає Aurora стратегію на глобальному рівні. Якщо `false` — не генеруються сигнали.
* **Домен:** Decision Making (Domain Master)
* **Режими роботи:** Backtest/Live (однаково)
* **Code Trace:**
    * `apps/reference/main.py`: ~730 — завантаження config
    * `apps/reference/domains/decision_making/aurora_handler.py`: ~150 — перевірка `enabled` та ініціалізація
    * `apps/reference/domains/decision_making/decision_making.py`: ~400 — виклик Aurora handler у tick-path
* **Математичний вплив:** Якщо `false`, весь сигнальний pipeline по Aurora блокується.
* **Валідація:**
    * Модель: `AuroraStrategyConfig.enabled` (`bool`)
    * Обмеження: Немає (тільки boolean)
* **Тести:** ✅ `tests/domains/decision_making/test_aurora_*.py`

---

### 2. `aurora.legacy_tick_path_enabled` (Контроль міграції)
* **Суть:** Флаг міграції. Якщо `true` — Aurora отримує тики старим шляхом (DecisionMaking.on_tick). Якщо `false` — чекає на новий EventBus шлях (в розробці).
* **Домен:** Decision Making Orchestration
* **Статус:** 🟡 Deprecated — код уже майже не використовує старий шлях
* **Code Trace:**
    * `apps/reference/domains/decision_making/aurora_handler.py`: ~280 — перевірка флага
    * Коментар в aurora.yaml: "keep Aurora on legacy DecisionMaking tick-path until AuroraHandler is validated"
* **Математичний вплив:** Контролює критичний шлях отримання даних — якщо `false`, система залежить від нового EventBus (який ще не готовий).
* **Ризик:** 🔴 **HIGH** — якщо встановити `false` раніше часу, сигнали припиняться без помилки.
* **Тести:** ⚠️ Потребує інтеграційних тестів для EventBus шляху.

---

### 3. `aurora.timeframe_sec: 300` (5-хвилинні бари)
* **Суть:** Таймфрейм агрегації для Aurora. 300s = 5 хвилин. Мусить збігатися з `bar_aggregator.timeframes_sec` в `trading.yaml`.
* **Домен:** Feature Engineering (Bar Aggregator) → Decision Making
* **Code Trace:**
    * `apps/reference/domains/feature_engineering/bar_aggregator.py`: ~100 — генерує бари цього таймфрейму
    * `apps/reference/domains/decision_making/aurora_handler.py`: ~250 — підписується на `EVT:BAR_CLOSED` для 300s
* **Математичний вплив:** Довжина скользящих вікон для усіх індикаторів (EMA, RSI, ATR, тощо) залежить від цього таймфрейму.
* **Валідація:**
    * Модель: `AuroraStrategyConfig.timeframe_sec` (`int`)
    * Обмеження: Мусить бути в `[60, 300, 900, 3600]` (1m, 5m, 15m, 1h)
    * ⚠️ Soft constraint (не перевіряється в Pydantic) — брати до уваги вручну!
* **Тести:** ✅ `tests/domains/feature_engineering/test_bar_aggregator.py`

---

### 4. `aurora.execution.entry_order_type: "LIMIT"` & `entry_tif: "GTX"`
* **Суть:** Política введення ордерів. LIMIT+GTX = Good-Till-Cross (не заповнюється на закритому) — безпечніший за MARKET.
* **Домен:** Execution Position (FSM Entry Logic)
* **Code Trace:**
    * `apps/reference/domains/execution_position/fsm_open.py`: ~200 — будує ордер на основі `entry_order_type`
    * `apps/reference/domains/decision_making/decision_making.py`: ~800 — заповнює `intent.order_type` з конфігу
* **Математичний вплив:** LIMIT + GTX означає, що ордер ніколи не буде заповнений за значно гіршою ціною (захист від flash crash).
* **Валідація:**
    * Модель: `StrategyExecutionConfig`
    * Обмеження: `entry_order_type` in `["LIMIT", "MARKET"]`, `entry_tif` in `["GTC", "GTX", "IOC", "FOK"]`
    * 🔴 **CRITICAL:** LIMIT + null TIF = помилка (ORDER-POLICY-01)
* **Тести:** ✅ `tests/domains/execution_position/test_fsm_open.py`

---

### 5. `aurora.decision.signal_threshold: 0.12` (Поріг входу)
* **Суть:** Глобальний нормалізований поріг сигналу для входу в позицію. Якщо `signal_score >= 0.12` → LONG, якщо `<= -0.12` → SHORT.
* **Домен:** Decision Making (AuroraHandler + AuroraScoringKernel)
* **Режими роботи:** Однаково для testnet/production (поки що)
* **Code Trace:**
    * `apps/reference/domains/decision_making/aurora_handler.py`: ~185 — завантаж `signal_threshold` з конфігу (FAIL-CLOSED)
    * `apps/reference/domains/decision_making/aurora_scoring_kernel.py`: ~220 — використовується в функції `_decision_from_score`
    * `apps/reference/domains/decision_making/aurora_scoring_kernel.py`: ~254-265 — порівняння з `thr_buy`, `thr_sell`, `thr_neutral`
* **Математичний вплив:** `signal_score` нормалізується через `SignalWeights` і потім порівнюється з цим порогом.
    ```
    if signal_score >= signal_threshold:
        decision = LONG
    elif signal_score <= -signal_threshold:
        decision = SHORT
    else:
        decision = HOLD
    ```
* **Валідація:**
    * Модель: `DecisionConfig.signal_threshold` (`float`)
    * Обмеження: `gt=0.01, lt=1.0` (1% — 100%)
    * 🔴 **CRITICAL:** PRODUCTION MUST OVERRIDE цей параметр! Коментар у коді: "production MUST override in trading.yaml!"
* **Тести:** ✅ `tests/domains/decision_making/test_aurora_scoring_*.py`

---

### 6. `aurora.decision.neutral_threshold: 0.05` (Поріг утримання)
* **Суть:** Нижча межа для утримання позиції. Якщо `signal_score` впаде нижче цього — позиція закриється.
* **Домен:** Decision Making (Position Holding Logic)
* **Режими роботи:** Активна, якщо визначена (否則 використовується `signal_threshold`)
* **Code Trace:**
    * `apps/reference/domains/decision_making/aurora_scoring_kernel.py`: ~260-265 — 3-zone logic
    * `aurora_scoring_kernel.py`: ~265 — `thr_neutral = neutral_threshold if neutral_threshold else thr_buy`
* **Математичний вплив:** Створює "мертву зону" для скорочення churn:
    ```
    ENTER:  signal_score > signal_threshold
    HOLD:   neutral_threshold < signal_score < signal_threshold
    EXIT:   signal_score < neutral_threshold
    ```
* **Валідація:**
    * Модель: `DecisionConfig.neutral_threshold` (`Optional[float]`)
    * Обмеження: Якщо задано, має бути < `signal_threshold`
    * Якщо `null` — 3-zone logic не активна (DEPRECATED)
* **Тести:** ✅ `test_aurora_scoring_kernel.py::test_three_zone_logic`

---

### 7. `aurora.decision.holding_period` (Anti-HFT затримка)
* **Суть:** Мінімальна тривалість утримання позиції перед дозволом signal-based exit (SL/TP/Risk exits не чіпаються).
* **Домен:** Decision Making (HFT Prevention)
* **Структура:**
    ```yaml
    holding_period:
      enabled: true
      min_duration_sec: 30          # Мінімум 30s перед сигналом на вихід
      emergency_exit_threshold: 0.7  # |score| > 0.7 → override затримки
      apply_to_flips: true          # FLIP сигнали теж чекають 30s
    ```
* **Code Trace:**
    * `apps/reference/domains/decision_making/decision_making.py`: ~900 — перевірка `holding_period` перед exit decision
    * `apps/reference/domains/decision_making/aurora_handler.py`: ~600 — обчислення elapsed time
* **Математичний вплив:** Блокує signal-based exit якщо `now - entry_time < min_duration_sec`.
* **Валідація:**
    * Модель: `HoldingPeriodConfig`
    * Обмеження: `min_duration_sec >= 10`, `emergency_exit_threshold in [0, 1]`
* **Тести:** ✅ `tests/domains/decision_making/test_holding_period_logic.py`

---

### 8. `aurora.decision.reentry_cooldown_sec: 60` (Anti-Ping-Pong)
* **Суть:** Після закриття позиції — чекати цю кількість секунд перед дозволом нового входу.
* **Домен:** Decision Making (Ping-Pong Prevention)
* **Code Trace:**
    * `apps/reference/domains/decision_making/decision_making.py`: ~950 — перевірка `last_close_time + reentry_cooldown_sec`
    * `apps/reference/domains/decision_making/position_tracking.py`: ~150 — збереження `last_close_time`
* **Математичний вплив:** Передбачає signal-based re-entry на час `cooldown_sec` сек після позиції близькості.
* **Валідація:**
    * Модель: `DecisionConfig.reentry_cooldown_sec` (`Optional[int]`)
    * Обмеження: `ge=0, le=3600` (0 — 1 година)
    * Default: 60s
* **Тести:** ✅ `tests/domains/decision_making/test_aurora_reentry_cooldown.py`

---

### 9. `aurora.decision.gates` (VOL-ADJ-GATES-01: Sigma-нормовані ворота)
* **Суть:** Блокує entry в мертвих (anti-flat) та екстремальних (anti-FOMO) ринках.
* **Структура:**
    ```yaml
    gates:
      enabled: true
      anti_flat_sigma: 0.5   # Блокує, якщо |pm_norm| < 0.5 (зупинено)
      anti_fomo_sigma: 4.0   # Блокує, якщо |pm_norm| > 4.0 (крах)
      motion_window_sec: 300  # 5-хв вікно для обчислення нормалізованого руху
    ```
    
    **Формула:** `pm_norm = clip(ret_window / (k_vol * vol_window), -1, 1)`
    
    - `ret_window`: return за цей період
    - `vol_window`: volatility за цей період
    - `k_vol`: volatility scale

* **Домен:** Decision Making (Entry Gating)
* **Code Trace:**
    * `apps/reference/domains/feature_engineering/aurora_feature_matrix.py`: ~400 — обчислює `pm_norm_300s`
    * `apps/reference/domains/decision_making/decision_making.py`: ~450 — перевірка гейтів перед signal evaluation
* **Математичний вплив:** `entry_allowed = (|pm_norm| >= anti_flat_sigma) AND (|pm_norm| <= anti_fomo_sigma)`
* **Валідація:**
    * Модель: `VolAdjGatesConfig`
    * Обмеження: `anti_flat_sigma < anti_fomo_sigma`
* **Тести:** ✅ `tests/domains/decision_making/test_vol_adj_gates.py`

---

### 10. `aurora.decision.direction_strength_scoring` (Signal Score V2)
* **Суть:** Розділяє сигналізацію на две компоненти: **Directional** (куди рухатися) та **Strength** (з якою впевненістю).
* **Структура:**
    ```yaml
    direction_strength_scoring:
      directional_features:
        - obi
        - tfi
        - delta_price
        - ema_bias
        - depth_imbalance
        - macro_resid  # R1: заміняє macro_sync для V2
      strength_features:
        - volume_spike
        - volatility_state
      strength_alpha: 0.5     # Ваги для strength
      strength_cap: 1.0       # Максимум strength впливу
    ```
* **Домен:** Decision Making (Feature Scoring)
* **Code Trace:**
    * `apps/reference/domains/decision_making/aurora_scoring_kernel.py`: ~350 — обчислює directional vs strength score
    * `apps/reference/domains/decision_making/aurora_handler.py`: ~300 — валідує наявність усіх features
* **Математичний вплив:** 
    ```
    final_score = directional_score * (1 + strength_score * strength_alpha)
    ```
* **Валідація:**
    * Модель: `DirectionStrengthScoringConfig`
    * Обмеження: `essential_features` мусять бути у `directional_features` ✅ (model_validator)
* **Тести:** ✅ `tests/domains/decision_making/test_direction_strength_scoring.py`

---

### 11. `aurora.decision.liquidity_gate` (Гейт ліквідності)
* **Суть:** Блокує entry, якщо ринок неліквідний (дуже низька liquidity_kappa).
* **Структура:**
    ```yaml
    liquidity_gate:
      enabled: true
      kappa_min: 0.1   # Мінімальна liquidity_kappa для входу
      kappa_max: 1.0   # Максимальна (верхня межа)
      failsafe_qty_check: true  # Додатково перевіряти qty
    ```
* **Домен:** Execution Position (Pre-Entry Validation)
* **Code Trace:**
    * `apps/reference/domains/execution_position/fsm_open.py`: ~180 — перевіряє `kappa` перед ордером
    * `apps/reference/domains/feature_engineering/...`: обчислює liquidity_kappa
* **Математичний вплив:** Entry ордер не створюється, якщо `liquidity_kappa < kappa_min`
* **Валідація:**
    * Модель: `LiquidityGateConfig`
    * Обмеження: `kappa_min < kappa_max`
* **Тести:** ✅ `tests/domains/execution_position/test_liquidity_gate.py`

---

### 12. `aurora.assets.ETHUSDT` (Per-Symbol Override — Приклад)
* **Суть:** Перевизначення глобальних параметрів Aurora для конкретного інструменту (ETHUSDT).
* **Модель:** `AuroraInstrumentConfig`
* **Критичні поля для ETHUSDT:**
    - `leverage.target: 20` — макс плече
    - `weights`: Custom signal weights (ваги для OBI, TFI тощо)
    - `holding_period.min_duration_sec: 45` — ETHUSDT утримується довше (тренду слідуємо)
    - `reentry_cooldown_sec: 120` — більша затримка повторного входу
    - `allowed_regimes: ["TREND_UP", ...]` — какі режимы дозволені
    - `signal_threshold.value: 0.09` — нижчий поріг для ETHUSDT (більш агресивно)

* **Code Trace:**
    * `apps/reference/domains/decision_making/aurora_handler.py`: ~500 — завантажує per-symbol overrides
    * `apps/reference/domains/decision_making/decision_making.py`: ~600 — використовує symbol-specific params

* **Валідація:**
    * Модель: `AuroraInstrumentConfig`
    * Обмеження: Всі per-symbol поля optional (нападають до глобальних)

---

## 📊 Статусна таблиця (Status Summary)

| Компонент | Статус | Примітка |
|-----------|--------|----------|
| **Базові параметри** (enabled, type, timeframe) | 🟢 ACTIVE | Критичні, используются постійно |
| **Signal Threshold** (0.12) | 🔴 CRITICAL OVERRIDE | PRODUCTION не мусить покладатися на це значення |
| **Execution Policy** (LIMIT+GTX) | 🟢 ACTIVE | Безпечна, добре протестована |
| **Holding Period** (30s anti-HFT) | 🟢 ACTIVE | Phase 4 feature, добре протестована |
| **Reentry Cooldown** (60s) | 🟢 ACTIVE | Простий, ефективний |
| **Volatility Gates** (anti-flat/anti-FOMO) | 🟢 ACTIVE | Phase 3 fix, критично для заборони GG |
| **Legacy Tick Path** | 🟡 DEPRECATED | Почати міграцію на EventBus |
| **Cooldown (global)** | 🟡 DEPRECATED | Використовуйте per-instrument замість цього |
| **Per-Symbol Assets** (ETHUSDT, SOLUSDT, BTCUSDT) | 🟢 ACTIVE | Добре оптимізовані через Optuna |

---

## ⚠️ Критичні Рекомендації Архітектора

1. **🔴 PRODUCTION MUST OVERRIDE `signal_threshold`** — 0.12 є тільки дефолтом для тестування. Використати Mode-specific (testnet: 0.12, production: 0.15+).

2. **🟡 Legacy Tick Path** — якнайскоріше мігрувати на EventBus шлях. Встановити `legacy_tick_path_enabled: false` та прив'язати до новой шляху.

3. **✅ GOOD:** Використання Pydantic для валідації гарантує fail-closed поведінку (немає silent fallbacks).

4. **✅ GOOD:** Per-symbol overrides добре структуровані. Кожен інструмент має явні параметри (не наслідуються мовчки).

---

## 📚 Посилання на Related RFCs & Docs

- `docs/RFC_min_duration_logic.md` — детальна спеціфікація HoldingPeriod
- `docs/AURORA_REGIME_TP_SL_PLAN.md` — режимна адаптація TP/SL
- `docs/ARCHITECTURE.md` — загальна архітектура
- `vfoundation/dictionaries/verb_registry_v1.yaml` — контрактна реєстрація

---

**Дата аналізу:** 2026-01-27  
**Версія конфігу:** 1.0.0 (CFG-STRATEGY-SSOT-FREEZE-02)  
**Статус:** ✅ Актуальний, готовий до production (з OVERRIDE сигналу)
