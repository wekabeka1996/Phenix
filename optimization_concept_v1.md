# 📜 Aurora Optimization Concept & Roadmap v1.0

**Status:** APPROVED (Consensus of Grok, GPT, Gemini)  
**Date:** 2026-02-09  
**Architecture:** Hierarchical (Regime First → Alpha Second → Robustness Third)

---

## 1. Концепція: Ієрархічний Пошук (The Hierarchy)

Ми відмовляємось від "пласкої" оптимізації (кидати всі параметри в один котел), оскільки Aurora має чітку залежність: **Стратегія залежить від Режиму**.

Якщо детектор режимів працює нестабільно ("миготить"), будь-яка стратегія отримуватиме сміттєві сигнали. Тому ми прийняли **Триєдиний Протокол**:

1. **Foundation (Stage 0):** Стабілізація "зору" системи (Regime Detector).
2. **Alpha (Stage 1):** Пошук прибутку на стабільному фундаменті (Strategy).
3. **Survival (Stage 2):** Перевірка на реалістичність виконання (Robustness).

---

## 2. Технічний Протокол (The Protocol)

### Етап 0: Стабілізація Режиму (Regime Calibration)

- **Ціль:** Максимізувати час перебування у чітких режимах (`HIGH_VOL`, `LOW_VOL`) та мінімізувати "шум" перемикань. **PnL ігнорується.**
- **Метод:** `Random Search` або `Latin Hypercube` (100–150 ітерацій).
- **Простір пошуку:** `regime.yaml` (`uncertain_cutoff`, `hysteresis_bars`, `basis_tf_sec`).
- **Виконання:** **Full Pipeline Simulation**. Ми проганяємо дані через реальний `bar_aggregator` та `regime_detector` (з урахуванням TTL та liveness), щоб уникнути оптимізації "сферичного коня".
- **Objective Function (Maximize):**

```text
hours           = total_bars * basis_tf_sec / 3600
definite_ratio  = 1 − (uncertain_bars / total_bars)
flicker_per_h   = flips / max(hours, ε)
uncertain_share = uncertain_bars / total_bars

stability_score = definite_ratio − 2.0 * flicker_per_h − 1.0 * uncertain_share
```

> Примітка: `flicker_per_h` MUST бути “per hour”, інакше порівняння tf=60s vs tf=900s буде некоректним.

---

### Етап 1: Пошук Альфи (Strategy Optimization)

- **Ціль:** Знайти параметри стратегії, що дають Risk-Adjusted Return.
- **Метод:** `Bayesian Optimization` (TPE via `skopt`, 50–80 ітерацій) з практичним протоколом:
  - Random/LHS pre-scan → звуження bounds → local TPE/GP.
- **Вхід:** Фіксований найкращий режим з Етапу 0 + `strategies.yaml` (patch overrides).
- **Risk Logic (Crucial):**
  - **Hard Constraints:** Порушення лімітів з `domains.yaml` (ExposureGuard, DailyRisk)  **Cost = 1e9 (Reject Run)**.
  - **Soft Penalties:** Впливають на score (optimizer має “вчитись” уникати країв, а не просто відкидати 90% кандидатів пост-фільтром).

- **Objective Function (Minimize Cost):**

```text
score = median_sharpe
        − P_mdd
        − P_churn
        − P_reject
        − P_starvation
        − P_util_proximity

cost  = −score    (бо оптимізатор мінімізує)
```

- **Penalties (мінімальний набір):**
  - **P_mdd:** експоненційний/квадратичний штраф за `MDD > 20%`.
  - **P_util_proximity:** штраф за наближення до utilization soft-zone (напр. `>80%`).
  - **P_reject:** штраф за `reject_rate > 30%` (ознака “мертвого” конфігу, fail-closed dominating).
  - **P_starvation:** штраф за `<50` угод (статистична незначущість).
  - **P_churn:** штраф за flips/entries per 100 bars (anti-churn).

---

### Етап 2: Валідація (Robustness Check)

- **Ціль:** Відсіяти перепідігнані (overfitted) рішення.
- **Метод:**
  1. **Walk-Forward Analysis:** Rolling window (**Train 60% / Gap 10% / Test 30%**).
  2. **Execution Stress:** Додавання випадкових `latency`, `slippage`, `fees` (але **без шуму в OHLCV**, щоб зберегти патерни).
  3. **Block Bootstrap:** Ресемплінг returns блоками (10–50 барів) для перевірки хвостів розподілу (tail-risk).

- **Критерій прийняття:** `Median Sharpe > 1.5`, `MDD (p90) < 20%` на тестових вибірках + stress-run’ах.

---

## 3. Архітектура та Інструменти

Ми створюємо окремий модуль `optimization/`, який не змішується з основним кодом `trading/`.

| Файл | Призначення | Статус |
| --- | --- | --- |
| **`config/optimization/search_space.json`** | Декларативний опис параметрів та меж (Structure by GPT). Включає `derived_fields`. | ✅ Ready |
| **`optimization/optimizer.py`** | Головний клас-оркестратор (`AuroraOptimizer`). Реалізує Stage 0 та Stage 1, Penalties, Hard Constraints. | ✅ Ready |
| **`optimization/robustness.py`** | Stage 2: Walk-Forward, Bootstrap, Stress Test logic. | ✅ Ready |
| **`optimization/backtest_interface.py`** | Адаптер, що з'єднує Optimizer з існуючим `CustomBacktester`. | ⏳ To Do |

---

## 4. Дорожня Карта (Execution Roadmap)

### Фаза 1: Підготовка (Setup)

1. [ ] Створити папку `optimization/` та зберегти `config/optimization/search_space.json`.
2. [ ] Створити `optimization/robustness.py` (код Stage 2: walk-forward + bootstrap + stress).
3. [ ] Створити `optimization/optimizer.py` (Stage 0 + Stage 1 orchestration).

### Фаза 2: Інтеграція (Bridge)

1. [ ] Написати адаптер `optimization/backtest_interface.py`.
   - Він має приймати `overrides` (словник параметрів).
   - Запускати бектест у потрібному режимі (Stage0 scan / Stage1 backtest / Stage2 walk-forward).
   - Повертати об'єкт `BacktestResult` (Sharpe, MDD, regime_log, hard_limit_violation, trades_count, rejected_signals, total_signals, churn/flips).

2. [ ] Переконатись, що бектестер вміє приймати `stress` параметри (latency/slippage/fees/funding) для Stage 2.

### Фаза 3: Калібрування (The Run)

1. [ ] **Run Stage 0:** Знайти стабільний `regime.yaml` на даних за 2024–2025 рік.
2. [ ] **Run Stage 1:** Знайти `strategies.yaml` на отриманому режимі.
3. [ ] **Run Stage 2:** Валідувати результат (walk-forward + bootstrap + stress).

### Фаза 4: Production

1. [ ] Застосувати отримані YAML-конфіги у `config/aurora/`.
2. [ ] Запустити Paper Trading.
3. [ ] Після стабілізації — поступовий перехід у live (з гейтами/лімітами як SSOT).

---

**Підпис:**  
*Архітектурна Рада ШІ (Grok, GPT, Gemini)*  
*Погоджено та затверджено.*

---

## Додаток A (Reference): Розширене пояснення консенсусу

Цей додаток не є “обов’язковим контрактом”, але корисний як довідник логіки рішень (чому саме так).

- Система не-гладка (ступінчасті гейти, fail-closed), тому **Random/LHS → Local Bayesian** є стандартом.
- Grid — тільки для дискретних “логічних” параметрів (on/off gates), Genetic — відкинуто через ризик exploit’ів симуляції/FSM.
- Robustness — без OHLC noise: тільки **block bootstrap + execution stress**.
- Hard risk limits — це **constraints**, soft ризики — **penalties**, інакше оптимізатор генерує купу сміття або живе на грані.
