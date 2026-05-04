# 📄 Паспорт конфігурації: `config/aurora/regime.yaml`

> **AUDIT SUMMARY**
> - **Document path:** `config/docs/regime_passport.md`
> - **Audit date:** 2026-03-18
> - **Audit mode:** Code-driven deep sync
> - **Total claims checked:** 37
> - **Confirmed:** 28
> - **Corrected:** 4
> - **Removed as stale:** 1 (hmm and features blocks officially removed)
> - **Added as missing:** `basis_import_buffer`, detailed `models.volatility.*` parameters, `mean_reversion.confidence_multiplier`, and A4 preset circuit breaker fields in `system_stress.state_mapping`.
> - **Major drifts found:** SMA and ATR periods updated to R2-winner defaults (`sma_short_period=48`, `sma_long_period=192`, `atr_sma_length=288`); explicit `SystemStressConfig` layer validated.
> - **Overall confidence:** HIGH

Нотатка про контекст: у `apps/reference/domains/regime_detector/` **немає** `types.py`; типи конфігів визначені в `apps/reference/config_models.py`.

---

## 1. БАЗОВІ ПАРАМЕТРИ ДЕТЕКТОРА

### `basis_tf_sec`
- **Type:** `int`
- **Logic Owner:** `regime_detector` (bar-only SSOT) + `decision_making` (liveness guard)
- **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py`
- **Runtime Role:** Базовий таймфрейм для роботи RegimeDetector.
- **Mathematical / Behavioral Role:** Bar-only тактування. Обробляються лише `EVT:FEATURES_CALCULATED` з `tf_sec == basis_tf_sec`. Тік-події (`tf_sec=0`) ігноруються.
- **Actual Runtime Semantics:** Впливає на розрахунок liveness-вікна.
- **Tuning Sensitivity:** Більше значення → рідше оновлення режиму, толерантніший liveness.
- **Constraints / Invariants:** `REQUIRED` (fail-closed на старті без нього).
- **Status:** `ACTIVE`

### `uncertain_cutoff`
- **Type:** `float`
- **Logic Owner:** `regime_detector`
- **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py`
- **Runtime Role:** Гейт впевненості для вихідних режимів.
- **Mathematical / Behavioral Role:** Якщо `regime != "UNCERTAIN"` і розрахований `confidence < uncertain_cutoff`, режим примусово переводиться в `UNCERTAIN` із впевненістю `conf_min`.
- **Actual Runtime Semantics:** Fallback слабких сигналів до безпечного "UNCERTAIN".
- **Tuning Sensitivity:** Вище значення = більше переходів в UNCERTAIN, менше агресивних торгових рішень.
- **Constraints / Invariants:** `0.0 <= value <= 1.0`
- **Status:** `ACTIVE`

### `liveness_factor`
- **Type:** `int`
- **Logic Owner:** `decision_making`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py`
- **Runtime Role:** Safety guard від зупинки генерації режимів.
- **Mathematical / Behavioral Role:** `max_delay_ms = basis_tf_sec * 1000 * liveness_factor`. Якщо `delta_ms > max_delay_ms`, торгівля блокується з `NRR-REGIME-DETECTOR-DEAD`.
- **Actual Runtime Semantics:** Fail-closed захист.
- **Tuning Sensitivity:** Нижче значення = швидше блокування при затримках.
- **Constraints / Invariants:** `value >= 1` (default 3).
- **Status:** `ACTIVE`

### `hysteresis_bars`
- **Type:** `int`
- **Logic Owner:** `regime_detector`
- **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py`
- **Runtime Role:** Стабілізація режимів (Anti-churn).
- **Mathematical / Behavioral Role:** Новий режим фіксується як `stable_regime` тільки якщо він повторюється `>= hysteresis_bars` послідовних барів.
- **Actual Runtime Semantics:** Затримує вихід `EVT:REGIME_DETECTED` з прапорцем `changed=True` до підтвердження.
- **Tuning Sensitivity:** Вище значення (напр. 3) = менше whipsaw перемикань, але більша затримка у визнанні нового тренду.
- **Constraints / Invariants:** `1 <= value <= 10`
- **Status:** `ACTIVE`

### `basis_import_buffer`
- **Type:** `int`
- **Logic Owner:** `market_data_cache` / `regime_detector`
- **Runtime Role:** Буфер додаткових барів для згладжування затримок завантаження історії.
- **Mathematical / Behavioral Role:** Додається до `regime_detector_required_bars()`.
- **Actual Runtime Semantics:** `Total import = required_bars + basis_import_buffer`.
- **Tuning Sensitivity:** Вище значення дає більшу стабільність при мікро-гепах від API бінансу під час ініціалізації.
- **Constraints / Invariants:** `>= 0`
- **Status:** `ACTIVE`

---

## 2. VOLATILITY SLOPE GATE

### `vol_slope_gate_enabled`
- **Type:** `bool`
- **Logic Owner:** `regime_detector`
- **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py`
- **Runtime Role:** Захист від "вмираючої бурі".
- **Mathematical / Behavioral Role:** Якщо поточний розрахунковий режим `HIGH_VOLATILITY`, перевіряє нахил `vol_ratio`. Якщо нахил стабільно падає, форсує `UNCERTAIN`.
- **Actual Runtime Semantics:** Знижує фальшиві входи на затухаючих імпульсах.
- **Tuning Sensitivity:** `true` = менше ризикових входів після піку волатильності.
- **Constraints / Invariants:** boolean, default `true`.
- **Status:** `ACTIVE`

### `vol_slope_gate_eps`
- **Type:** `float`
- **Logic Owner:** `regime_detector`
- **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py`
- **Runtime Role:** Поріг спаду волатильності.
- **Mathematical / Behavioral Role:** Тригер активується, якщо `vol_ratio_slope <= vol_slope_gate_eps`.
- **Actual Runtime Semantics:** `vol_ratio_slope` розраховується як `EMA3 - EMA6` від `vol_ratio`.
- **Tuning Sensitivity:** Нижче значення (напр. `-0.005`) вимагає більш крутого падіння волатильності для блокування.
- **Constraints / Invariants:** `-0.1 <= value <= 0.1`
- **Status:** `ACTIVE`

### `vol_slope_gate_confirm_bars`
- **Type:** `int`
- **Logic Owner:** `regime_detector`
- **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py`
- **Runtime Role:** Тривалість підтвердження спаду.
- **Mathematical / Behavioral Role:** Кількість послідовних барів, коли нахил `<= eps`.
- **Actual Runtime Semantics:** Якщо `_slope_reject_count >= confirm_bars`, встановлюється `storm_rejected=True` та `UNCERTAIN`.
- **Tuning Sensitivity:** Більше значення = захист від випадкових короткочасних просадок волатильності.
- **Constraints / Invariants:** `1 <= value <= 5`
- **Status:** `ACTIVE`

---

## 3. MODELS

### `models.sma_trend.sma_short_period` & `sma_long_period`
- **Type:** `int`
- **Logic Owner:** `regime_detector`
- **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py`
- **Runtime Role:** Визначення напрямку тренду та бази для Mean Reversion.
- **Mathematical / Behavioral Role:** Тренд ВГОРУ якщо `sma_short > sma_long` та `price > sma_short`.
- **Actual Runtime Semantics:** Задає довжину вікна. (R2-Winner: `sma_short=48`, `sma_long=192`).
- **Tuning Sensitivity:** Довгі періоди зменшують шум, але збільшують warmup.
- **Constraints / Invariants:** `short >= 2`, `long >= 5`
- **Status:** `ACTIVE`

### `models.sma_trend.confidence_*`
- **Type:** `float`
- **Logic Owner:** `regime_detector`
- **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py`
- **Runtime Role:** Розрахунок сили тренду та глобальні межі (min/max).
- **Mathematical / Behavioral Role:** `conf = abs(short-long)/long * multiplier`. Результат затискається між `confidence_min` та `confidence_max`.
- **Actual Runtime Semantics:** Базові `conf_min` та `conf_max` впливають на ВСІ інші моделі (MR, Volatility).
- **Constraints / Invariants:** `min >= 0.0`, `max <= 1.0`, `multiplier >= 1.0`.
- **Status:** `ACTIVE`

### `models.volatility.enabled`
- **Type:** `bool`
- **Logic Owner:** `regime_detector`
- **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py`
- **Runtime Role:** Управління визначенням волатильних режимів.
- **Mathematical / Behavioral Role:** Volatility (якщо увімкнено) має ПРІОРИТЕТ 1. Якщо `vol_ratio > high_vol_mult` або `< low_vol_mult`, воно перезаписує Trend та MR.
- **Actual Runtime Semantics:** Впливає на розрахунок `warmup.full_ready` (вимагає/ігнорує ATR).
- **Constraints / Invariants:** boolean
- **Status:** `ACTIVE`

### `models.volatility.atr_period` & `atr_sma_length`
- **Type:** `int`
- **Logic Owner:** `regime_detector`
- **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py`
- **Runtime Role:** Розрахунок `vol_ratio`.
- **Mathematical / Behavioral Role:** `vol_ratio = atr / atr_baseline`, де `atr_baseline` це SMA від ATR за період `atr_sma_length`.
- **Actual Runtime Semantics:** Встановлює рівень волатильності відносно історії (напр. 288 барів = 24 години на 5m).
- **Constraints / Invariants:** `atr_period >= 1`, `atr_sma_length >= 10`.
- **Status:** `ACTIVE`

### `models.volatility.allow_close_to_close_atr`
- **Type:** `bool`
- **Logic Owner:** `regime_detector`
- **Runtime Role:** Дозволяє розрахунок ATR за цінами закриття при відсутності повної OHLCV свічки.
- **Constraints / Invariants:** boolean, default `true`.
- **Status:** `ACTIVE`

### `models.volatility.multipliers` (`threshold_multiplier`, `low_vol_multiplier`, v-confidence)
- **Type:** `float`
- **Logic Owner:** `regime_detector`
- **Runtime Role:** Пороги спрацювання волатильних станів.
- **Mathematical / Behavioral Role:** 
  - Якщо `vol_ratio >= threshold_multiplier` → `HIGH_VOLATILITY`.
  - Якщо `vol_ratio <= low_vol_multiplier` → `LOW_VOLATILITY`.
  - Впевненість скалюється через `high_vol_confidence_multiplier` та `low_vol_confidence_multiplier`.
- **Constraints / Invariants:** Пороги `> 0`.
- **Status:** `ACTIVE`

### `models.mean_reversion.threshold` & `confidence_multiplier`
- **Type:** `float`
- **Logic Owner:** `regime_detector`
- **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py`
- **Runtime Role:** Поріг переходу в `MEAN_REVERSION` та сила впевненості.
- **Mathematical / Behavioral Role:** ПРІОРИТЕТ 2 (працює тільки якщо волатильність не спрацювала). Якщо розбіжності SMAs та Price < `threshold`, режим стає "MEAN_REVERSION". Далі впевненість скалюється через `confidence_multiplier`.
- **Actual Runtime Semantics:** Використовується для знаходження періодів консолідації (Flat).
- **Constraints / Invariants:** `value >= 0.0`.
- **Status:** `ACTIVE`

---

## 4. SYSTEM STRESS GUARD (Phase 0.0)

### `system_stress.enabled`
- **Type:** `bool`
- **Logic Owner:** `system_stress_overlay`
- **Code Reference:** `apps/reference/domains/system_stress/system_stress_overlay.py`
- **Runtime Role:** Додатковий рівень захисту від ринкових аномалій.
- **Mathematical / Behavioral Role:** Якщо увімкнено, працює незалежно від TREND/MR. Емітує стан `NORMAL / STRESS / EXTREME` через `EVT:SYSTEM_STRESS_STATE_UPDATED`.
- **Actual Runtime Semantics:** Впливає на `DecisionMaking`, який може блокувати або зменшувати позиції при `STRESS`/`EXTREME`.
- **Constraints / Invariants:** boolean.
- **Status:** `ACTIVE`

### `system_stress.thresholds` & `aggregation`
- **Type:** `Object`
- **Logic Owner:** `system_stress_overlay`
- **Code Reference:** `apps/reference/domains/system_stress/system_stress_overlay.py`
- **Runtime Role:** Формування композитного stress_level.
- **Mathematical / Behavioral Role:** Розраховує z-scores (напр. `atr_sigma`, `gap_sigma`). Агрегує їх через `weighted_vote`, `k_of_n` або `max` для отримання `stress_level` від 0 до 1.
- **Constraints / Invariants:** `extra='forbid'` в Pydantic.
- **Status:** `ACTIVE`

### `system_stress.state_mapping` (Actuator FSM & CB)
- **Type:** `Object`
- **Logic Owner:** `system_stress_overlay`
- **Code Reference:** `apps/reference/domains/system_stress/system_stress_overlay.py`
- **Runtime Role:** Перетворення `stress_level` у стани з гістерезисом і Circuit Breaker захистом.
- **Mathematical / Behavioral Role:** 
  - `enter_stress` / `exit_stress`: пороги входу/виходу для STRESS.
  - `enter_extreme` / `exit_extreme`: пороги для EXTREME.
  - `consecutive_bars_enter` / `min_duration_bars`: anti-churn стабілізація.
  - `switch_window_bars` / `max_switches_per_window`: Circuit Breaker для виявлення "флапінгу" між станами.
  - `circuit_breaker_mode`: `halt` (зупиняє торгівлю при флапінгу).
- **Actual Runtime Semantics:** Забезпечує, що стресові стани не блимають. Перехід підтверджується N барів і тримається мінімум M барів. Аномальні перемикання захищені Circuit Breaker.
- **Constraints / Invariants:** Сувора перевірка на порядок (`exit_stress < enter_stress < enter_extreme`).
- **Status:** `ACTIVE`

---

## 5. REGIME SHIFT INCEPTION

### `regime_shift_inception.enabled`
- **Type:** `bool`
- **Logic Owner:** `decision_making` (Inception Guard)
- **Code Reference:** `apps/reference/domains/decision_making/aurora_decision.py`
- **Runtime Role:** Дозволяє мікро-входи в перший бар переходу.
- **Mathematical / Behavioral Role:** Реагує на raw-режим під час "stable_regime ∉ allowed_regimes". Застосовує `action` (напр. `micro_size_fraction`).
- **Constraints / Invariants:** boolean
- **Status:** `ACTIVE`

---

## 6. АРХІТЕКТУРНА ОЦІНКА ТА ВИРІШЕННЯ КОНФЛІКТІВ

Порядок застосування правил під час `handle_event` для одного бару:
1. **Volatility (Priority 1):** Якщо `atr` та `baseline` готові, і `vol_ratio` пробиває пороги → результат `HIGH_VOLATILITY` або `LOW_VOLATILITY`.
2. **Slope Gate:** Якщо вийшов `HIGH_VOLATILITY`, перевіряється спад імпульсу. Якщо він згасає (`storm_rejected=True`) → примусово `UNCERTAIN`.
3. **Mean Reversion (Priority 2):** ТІЛЬКИ якщо режим після 1 і 2 залишається `UNCERTAIN`. Якщо ціна між SMA близько → `MEAN_REVERSION`.
4. **SMA Trend (Priority 3):** ТІЛЬКИ якщо режим досі `UNCERTAIN`. Оцінка `TREND_UP` / `TREND_DOWN`.
5. **Confidence Gate:** Якщо `regime != UNCERTAIN` але впевненість `< uncertain_cutoff` → примусовий `UNCERTAIN`.
6. **Hysteresis:** Отриманий `raw_regime` пропускається через лічильник. `stable_regime` змінюється лише після `hysteresis_bars` повторень.

*Система гарантує Fail-Closed поведінку (падіння до UNCERTAIN або блокування торгівлі) на всіх рівнях: від відсутності барів (Liveness), до неповних даних (OHLC ATR), слабких сигналів та втрати імпульсу (Slope gate).*
