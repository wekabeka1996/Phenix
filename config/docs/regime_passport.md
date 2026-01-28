# 📄 Паспорт конфігурації: aurora/regime.yaml (Section: basis_tf_sec, uncertain_cutoff, liveness_factor, hmm, features, models)

## 🔍 Загальний опис блоку
Файл `regime.yaml` контролює **детектування ринкових режимів (Market Regime Detection)** — систему яка визначає в якому стані перебуває ринок: тренд вверх, тренд вниз, фласс (плоский), високе/низьке волатильність, mean reversion.

Режими впливають на:
- **Вибір параметрів TP/SL** (різні режими = різні ціни виходу)
- **Гейти входу** (наприклад, MEAN_REVERSION блокується для BTC в趋势 режимі)
- **Розмір позиції** (більше позицій у трендових режимах)

Це **SSOT (Single Source of Truth)** для режимної логіки; всі параметри мають точну аналогію в Pydantic моделях.

---

## 🛠 Деталізація полів

| Поле | Тип | Pydantic | Статус | Роль у проекті |
|---|---|---|---|---|
| `basis_tf_sec` | `int` | ✅ | 🟢 Active | Таймфрейм обробки (5 хвилин = 300сек). Повинні обробляватися тільки бари цього розміру |
| `uncertain_cutoff` | `float` | ✅ | 🟢 Active | Min confidence для випуску режиму (< цього → UNCERTAIN) |
| `liveness_factor` | `int` | ✅ | 🟢 Active | Множник для "heartbeat guard" (запобігає торгівлі якщо режим застарів) |
| ~~`hmm.enabled`~~ | ~~`bool`~~ | ❌ REMOVED | ✅ Deleted 2026-01-27 | ~~Прапорець для HMM-режиму~~ (REMOVED — не реалізовано) |
| ~~`hmm.K`~~ | ~~`int`~~ | ❌ REMOVED | ✅ Deleted 2026-01-27 | ~~Кількість прихованих станів~~ (REMOVED) |
| ~~`hmm.update_interval`~~ | ~~`int`~~ | ❌ REMOVED | ✅ Deleted 2026-01-27 | ~~Інтервал оновлення~~ (REMOVED) |
| ~~`features.rv_window`~~ | ~~`int`~~ | ❌ REMOVED | ✅ Deleted 2026-01-27 | ~~Вікно realized volatility~~ (REMOVED — в feature_engineering) |
| ~~`features.trend_window`~~ | ~~`int`~~ | ❌ REMOVED | ✅ Deleted 2026-01-27 | ~~Вікно тренда~~ (REMOVED) |
| `models.sma_trend.*` | `Object` | ✅ | 🟢 Active | SMA-тренд модель (детектує TREND_UP/DOWN/MR) |
| `models.volatility.*` | `Object` | ✅ | 🟢 Active | ATR-волатильність модель (HIGH_VOL / LOW_VOL) |
| `models.mean_reversion.*` | `Object` | ✅ | 🟢 Active | Mean reversion модель (MEAN_REVERSION режим) |

---

### 1. `basis_tf_sec` (Базовий таймфрейм)
* **Суть:** **КРИТИЧНИЙ** параметр. Визначає яким таймфреймом "тактує" вся система детектування режимів. Система обробляє тільки события EVT:FEATURES_CALCULATED з `tf_sec == basis_tf_sec`; вся інша інформація ігнорується.
  * При `basis_tf_sec = 300` → система обробляє 5-хвилинні бари
  * Tick-level сигнали (`tf_sec=0`) автоматично ігнорируються (no double-clocking)
* **Домен:** `Regime Detector` (Core).
* **Режими роботи:** Усі режими (Live, Backtest, Testnet).
* **Code Trace (Де використовується):**
    * [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L69) — `self._basis_tf_sec: int = config.basis_tf_sec` (ініціалізація в конструкторі).
    * [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L216-219) — перевірка в `handle_event()`:
      ```python
      if tf_sec != self._basis_tf_sec:
          self.logger.debug(f"[{symbol}] RegimeDetector: ignoring tf_sec={tf_sec} (basis={self._basis_tf_sec})")
          return
      ```
    * [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py#L422) — використання для `liveness_guard` обчислення.
* **Математичний вплив:**
  * Визначає розмір вікна даних для розрахунку SMA: `sma_short_period` та `sma_long_period` мірять в барах (не в сек), тому їхня реальна тривалість = `basis_tf_sec * period_in_bars`.
  * Приклад: `sma_short_period=2, basis_tf_sec=300` → фактична тривалість SMA = 2 бари * 300сек = 10 хвилин.
* **Валідація:**
    * Модель: `AuroraConfig.basis_tf_sec: int` (REQUIRED, no default)
    * Обмеження: Немає експліцитних, але мають бути > 0
    * **Fail-closed:** Відсутність → `ConfigContractError` при запуску
* **Тести:** 
    * ✅ [tests/domains/regime_detector/test_regime_bar_only.py](tests/domains/regime_detector/test_regime_bar_only.py) — перевіряє що non-basis timeframes ігнорируються
    * ✅ [tests/config/test_regime_yaml_strict_validation.py](tests/config/test_regime_yaml_strict_validation.py) — валідація конфіг-ладання

**Рекомендація:** В LIVE мають бути `basis_tf_sec=300` (5m бари — стандарт). В BACKTEST можна зменшувати для прискорення.

---

### 2. `uncertain_cutoff` (Границя впевненості)
* **Суть:** Мінімальний поріг впевненості (`confidence`) для випуску режиму як "валідного". Якщо режим визначений але `confidence < uncertain_cutoff`, система понижає його до режиму "UNCERTAIN" (консервативна позиція, блокує сигнали).
* **Домен:** `Regime Detector` (Quality Gate).
* **Режими роботи:** Усі режими.
* **Code Trace:**
    * [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L70) — зчитується при ініціалізації
    * [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L436-446) — застосування у гейті:
      ```python
      if regime != "UNCERTAIN" and float(confidence) < self._uncertain_cutoff:
          ...
          regime = "UNCERTAIN"
          source_model = "uncertain_cutoff_gate"
      ```
* **Математичний вплив:**
  * **Коефіцієнт:** `if confidence < uncertain_cutoff: mode = UNCERTAIN` (fail-closed)
  * Запобігає слабким сигналам (слабкий тренд = фласс, не тренд)
* **Валідація:**
    * Модель: `AuroraConfig.uncertain_cutoff: float` (REQUIRED)
    * Обмеження: `ge=0.0, le=1.0` (от 0 до 1)
    * **Fail-closed:** Невідповідь → `ValidationError` при завантаженні конфіг
* **Тести:** ✅ Побіжно перевіряється в режимних тестах (реаль-значення 0.35 = помірна границя).

**Рекомендація:** Типові значення — 0.3-0.5. Вище = більш консервативна система (більше UNCERTAIN).

---

### 3. `liveness_factor` (Множник heartbeat)
* **Суть:** Захисний механізм від "мертвої" детекції режиму. Якщо система не отримує режимні оновлення більше ніж `basis_tf_sec * liveness_factor` секунд, вона **блокує торгівлю** (fail-closed).
  * При `basis_tf_sec=300, liveness_factor=3` → якщо немає новинок > 15 хвилин, торгівля заблокована
* **Домен:** `Decision Making` (Safety Gate, Aurora Handler).
* **Режими роботи:** Live, Hybrid, Backtest (в backtest менш критична).
* **Code Trace:**
    * [apps/reference/config_models.py](apps/reference/config_models.py#L2920-2923) — визначення з дефолтом `default=3`
    * [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py#L406-432) — використання в `_check_regime_gate()`:
      ```python
      basis_tf_sec = int(self.config.basis_tf_sec)
      liveness_factor = int(getattr(self.config, "liveness_factor", 3))
      ...
      max_delay_ms = basis_tf_sec * 1000 * liveness_factor
      if (now_ms - last_regime_ts) > max_delay_ms:
          return {"allowed": False, "reason": "REGIME_GATE_BLOCKED:heartbeat_stale"}
      ```
* **Математичний вплив:**
  * `max_allowed_delay_sec = basis_tf_sec * liveness_factor`
  * Коли `(now - last_regime_update) > max_delay_sec` → DROP intent (fail-closed)
* **Валідація:**
    * Модель: `AuroraConfig.liveness_factor: int` (default=3)
    * Обмеження: `ge=1` (мін 1, щоб не було негативних)
* **Тести:** ✅ Перевіряється у тестах Aurora Handler (heartbeat stale scenarios).

**Рекомендація:** Залиште дефолт (3) в LIVE. В BACKTEST можна знизити для прискорення тестування.

---

### 4. ~~`hmm` (HMM режим — Legacy)~~ — **REMOVED**

🟢 **STATUS:** ✅ REMOVED (Scorched-Earth 2026-01-27)

Field completely deleted from config_models.py (line 2954 comment: "hmm and features fields DELETED — zero runtime references").

This section was previously documented as "NOT IMPLEMENTED" and has been eliminated entirely.

---

### 5. ~~`features` (Feature engineering params — Legacy)~~ — **REMOVED**

🟢 **STATUS:** ✅ REMOVED (Scorched-Earth 2026-01-27)

Field completely deleted from config_models.py (line 2954 comment: "hmm and features fields DELETED — zero runtime references").

This section was previously documented as "LEGACY" and has been eliminated entirely. All feature engineering is now centralized in the `feature_engineering` domain with its own configuration.

---

### 6. `models.sma_trend` (SMA Trend Detection)
* **Суть:** SMA-based trend regime detector. Порівнює короткий SMA (trend) з довгим SMA (baseline) для детектування TREND_UP, TREND_DOWN або MEAN_REVERSION.
* **Домен:** `Regime Detector` (Model).
* **Режими роботи:** Усі режими.
* **Code Trace:**
    * [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L87-91) — завантаження:
      ```python
      self.sma_short_period = int(self.model_config.sma_short_period)
      self.sma_long_period = int(self.model_config.sma_long_period)
      ```
    * [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L310-314) — обчислення SMA:
      ```python
      sma_short = sum(list(self._price_buf[symbol])[-self.sma_short_period:]) / Decimal(str(self.sma_short_period))
      sma_long = sum(list(self._price_buf[symbol])[-self.sma_long_period:]) / Decimal(str(self.sma_long_period))
      ```
    * [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L143-180) — функція `_calculate_confidence()` обчислює впевненість як:
      ```
      confidence = |spread_ratio| * confidence_multiplier
      spread_ratio = (sma_short - sma_long) / sma_long
      ```
* **Математичний вплив:**
  * **Тренд вверх:** `sma_short > sma_long` → TREND_UP
  * **Тренд вниз:** `sma_short < sma_long` → TREND_DOWN
  * **Flat:** `|sma_short - sma_long| < порог` → MEAN_REVERSION (або FLAT)
  * **Confidence:** `|(sma_short - sma_long) / sma_long| * confidence_multiplier` (clamped to [confidence_min, confidence_max])
* **Під-поля:**

| Поле | Тип | Обмеження | Роль |
|---|---|---|---|
| `sma_short_period` | `int` | `ge=2` | Короткий SMA період (в барах). Мен. значення для warmup |
| `sma_long_period` | `int` | `ge=5` | Довгий SMA період (в барах). Мен. базового тренду |
| `confidence_multiplier` | `float` | `ge=1.0` | Масштабування spread-ratio в confidence (вище = більше contrast) |
| `confidence_min` | `float` | `ge=0, le=1` | Floor для confidence (мін. значення) |
| `confidence_max` | `float` | `ge=0, le=1` | Ceiling для confidence (макс. значення) |

* **Валідація:**
    * Модель: `SMARegimeModelConfig` (extra='forbid')
* **Тести:** 
    * ✅ [tests/domains/regime_detector/test_regime_bar_only.py](tests/domains/regime_detector/test_regime_bar_only.py) — перевірка SMA logic
    * ✅ [tests/runtime/test_task24_regime_detector_correctness.py](tests/runtime/test_task24_regime_detector_correctness.py) — детальні SMA тести

**Рекомендація:** LIVE значення `sma_short=10, sma_long=50`. BACKTEST/TESTNET мінімізуємо для warmup (сейчас `sma_short=2, sma_long=5`).

---

### 7. `models.volatility` (ATR Volatility Detection)
* **Суть:** ATR (Average True Range)-based volatility regime detector. Визначає HIGH_VOLATILITY або LOW_VOLATILITY за порівнянням поточного ATR з історичним середнім.
* **Домен:** `Regime Detector` (Model).
* **Режими роботи:** Усі режими.
* **Code Trace:**
    * [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L112) — завантаження `atr_period`
    * [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L353-359) — розрахунок ATR:
      ```python
      if len(self._tr_buf[symbol]) >= self.atr_period:
          init_atr = sum(list(self._tr_buf[symbol])[-self.atr_period:]) / Decimal(str(self.atr_period))
      ```
    * [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L390) — порівняння з порогом:
      ```python
      threshold_multiplier = Decimal(str(vol_cfg.threshold_multiplier))
      if atr_sma > threshold_multiplier * baseline_atr:
          regime = "HIGH_VOLATILITY"
      ```
* **Математичний вплив:**
  * **HIGH_VOLATILITY:** `current_ATR > threshold_multiplier * avg_ATR`
  * **LOW_VOLATILITY:** `current_ATR < low_vol_multiplier * avg_ATR`
  * Confidence масштабується як: `base_confidence * high_vol_confidence_multiplier` (або low_vol版本)
* **Під-поля:**

| Поле | Тип | Обмеження | Роль |
|---|---|---|---|
| `enabled` | `bool` | - | Вмикає/вимикає волатильність детекцію |
| `atr_period` | `int` | `ge=1` | Період для розрахунку ATR (в барах). Хорошої: 14 (LIVE), 1 (TESTNET) |
| `atr_sma_length` | `int` | `ge=10` | SMA довжина для базового ATR (для детектування baseline). Хорошої: 100 (LIVE), 10 (TESTNET) |
| `allow_close_to_close_atr` | `bool` | - | Дозволити розраховувати ATR з Close-to-Close коли OHLC невідомий (explicit opt-in) |
| `threshold_multiplier` | `float` | `ge=1.0` | Поріг для HIGH_VOL: `ATR > mult * avg` (вище = більш вибірко) |
| `low_vol_multiplier` | `float` | `ge=0, le=1` | Поріг для LOW_VOL: `ATR < mult * avg` |
| `high_vol_confidence_multiplier` | `float` | `ge=1.0` | Масштаб confidence для HIGH_VOL (вище = більш впевнено) |
| `low_vol_confidence_multiplier` | `float` | `ge=1.0` | Масштаб confidence для LOW_VOL |

* **Валідація:**
    * Модель: `VolatilityRegimeModelConfig` (extra='forbid')
* **Тести:** ✅ Перевіряється у режимних тестах (ATR warmup, threshold logic).

**Рекомендація:** LIVE: `atr_period=14, atr_sma_length=100, threshold_multiplier=2.0`. TESTNET: мініми для прискорення (сейчас `atr_period=1, atr_sma_length=10`).

---

### 8. `models.mean_reversion` (Mean Reversion Detection)
* **Суть:** Простий детектор mean reversion режиму. Визначає MEAN_REVERSION коли ціна близька до обох SMA (тісна cougar).
* **Домен:** `Regime Detector` (Model).
* **Режими роботи:** Усі режими.
* **Code Trace:**
    * [apps/reference/config_models.py](apps/reference/config_models.py#L804-808) — модель `MeanReversionRegimeModelConfig`
    * [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py) — **НЕ ЗНАЙДЕНО прямого використання** конфіг параметрів (threshold, confidence_multiplier)
      * Замість того логіка mean reversion детектується як "if (sma_short ~= sma_long)" у SMA-тренд логіці
* **Математичний вплив:**
  * Коли `|sma_short - sma_long| / sma_long < threshold` → MEAN_REVERSION режим
* **Під-поля:**

| Поле | Тип | Обмеження | Роль |
|---|---|---|---|
| `threshold` | `float` | `ge=0` | Макс relative deviation від SMA для MR режиму (0.005 = 0.5%) |
| `confidence_multiplier` | `float` | `ge=1.0` | Масштаб confidence для MR |

* **Валідація:**
    * Модель: `MeanReversionRegimeModelConfig` (extra='forbid')
* **Тести:** ❌ Немає прямих тестів для MR detection параметрів (можливо мертві поля).

**Вердикт:** Параметри `models.mean_reversion` може бути **ZOMBIE** — визначення MR режиму залежить від SMA logic, а не від цих параметрів. Перевірити у коді.

---

## 📊 Audit Summary (Вердикт)

| Поле | Статус | Примітка |
|---|---|---|
| `basis_tf_sec` | 🟢 **ACTIVE** | КРИТИЧНЕ. Фільтрує non-basis-tf eventos. Full code-trace. |
| `uncertain_cutoff` | 🟢 **ACTIVE** | Fail-closed гейт для слабких сигналів. Full code-trace. |
| `liveness_factor` | 🟢 **ACTIVE** | Heartbeat guard для мертвої детекції. Full code-trace у aurora_handler. |
| `hmm.*` | 🔴 **ZOMBIE** | NOT IMPLEMENTED. Конфіг зберігається але ніколи не читається. DELETE. |
| `features.*` | 🔵 **LEGACY** | Параметри присутні але вся логіка у feature_engineering домені. MOVE або DELETE. |
| `models.sma_trend` | 🟢 **ACTIVE** | Повна реалізація. SMA-crossover тренд детекція. Full code-trace. |
| `models.volatility` | 🟢 **ACTIVE** | Повна реалізація. ATR-based HIGH/LOW vol детекція. Full code-trace. |
| `models.mean_reversion` | 🟡 **QUESTIONABLE** | Параметри визначені але логіка може бути у SMA-тренд. Перевірити. |

---

## 🔐 Data Cleanliness & Recommendations

### ✅ Що добре:
1. **Fail-closed валідація:** `basis_tf_sec` та `uncertain_cutoff` REQUIRED (no silent defaults).
2. **Pydantic strict validation:** `extra='forbid'` для всіх моделей (SSOT).
3. **Windowed logic:** `basis_tf_sec` + `liveness_factor` запобігають deadlocks.

### ⚠️ Що чекити/видалити:
1. **`hmm` блок** — NOT IMPLEMENTED. Видаліть або позначте як TODO.
2. **`features` блок** — можливо дублюється з `feature_engineering`. Консолідуйте.
3. **`models.mean_reversion`** — перевірте чи параметри реально використовуються (можливо мертві поля).

### 🚀 Рекомендації для Backtest:
```yaml
basis_tf_sec: 300           # Залиште 5m (не змінюйте)
uncertain_cutoff: 0.35      # Залиште як є
liveness_factor: 3          # Можна знизити до 1 для прискорення
models:
  sma_trend:
    sma_short_period: 2     # MIN: 2 (було 10 в LIVE)
    sma_long_period: 5      # MIN: 5 (було 50 в LIVE)
    confidence_multiplier: 20.0
    confidence_min: 0.5
    confidence_max: 0.95
  volatility:
    atr_period: 1           # MIN: 1 (було 14 в LIVE)
    atr_sma_length: 10      # MIN: 10 (було 100 в LIVE)
```

---

## 🧪 Test Coverage

| Тест-файл | Охоплення |
|---|---|
| [test_regime_bar_only.py](tests/domains/regime_detector/test_regime_bar_only.py) | ✅ basis_tf_sec filtering, SMA logic |
| [test_regime_mapping.py](tests/domains/test_regime_mapping.py) | ✅ Режимні переходи та логіка |
| [test_regime_yaml_strict_validation.py](tests/config/test_regime_yaml_strict_validation.py) | ✅ Конфіг-валідація, fail-closed |
| [test_task24_regime_detector_correctness.py](tests/runtime/test_task24_regime_detector_correctness.py) | ✅ Детальні SMA/ATR тести |

---

**Документ завершено:** 2026-01-27  
**SSOT:** `config/aurora/regime.yaml` + `config_models.py` (регіме-моделі) + `apps/reference/domains/regime_detector/`
