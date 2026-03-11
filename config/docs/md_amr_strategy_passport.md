# Semantic Configuration Passport: `config/aurora/strategies/md_amr.yaml`

Цей документ описує конфігурацію стратегії **Multi-Dimensional Asymmetric Mean Reversion (MD-AMR) V1.2**.
**Статус:** Production / SSOT
**Owner:** `decision_making` / `md_amr_handler`

---

## 1. Базові параметри
- `md_amr.enabled` (bool): Master toggle для стратегії MD-AMR.
- `md_amr.type` (str): Ідентифікатор типу стратегії (`md_amr_v1_2`).
- `md_amr.description` (str): Опис.
- `md_amr.timeframe_sec` (int): Таймфрейм виконання (наприклад, 900 для 15 хвилин).
- `md_amr.defer_ttl_sec` (int): Час життя відкладених ордерів (defer TTL).

## 2. Параметри індикаторів та математики скорингу
- `md_amr.channel_window_bars` (int): Розмір вікна для каналу.
- `md_amr.channel_robust_pct` (float): Відсоток робастності для каналу.
- `md_amr.atr_window` (int): Розмір вікна для розрахунку ATR.
- `md_amr.atr_stats_window` (int): Розмір вікна для статистичного ATR.
- `md_amr.hysteresis_mult` (float): Множник гістерезису для запобігання флапінгу.
- `md_amr.threshold_z` (float): Поріг Z-Score для входів.
- `md_amr.volatility_dampening_factor` (float): Коефіцієнт демпфування волатильності.
- `md_amr.thr_base` (float): Базовий поріг входження.
- `md_amr.thr_floor` (float): Мінімальний поріг.
- `md_amr.alpha` (float): Альфа коефіцієнт.
- `md_amr.conf_min` (float): Мінімальна впевненість (confidence) для сигналів.
- `md_amr.max_hold_bars` (int): Максимальна кількість барів для утримання позиції.
- `md_amr.atr_zscore_clamp` (float): Обмеження Z-Score для забезпечення робастності (Fix 3).
- `md_amr.atr_std_floor_pct` (float): Мінімальне стандартне відхилення ATR у відсотках.

## 3. Витрати та виконання (`execution` & costs)
- `md_amr.fee_bps` (float): Комісія в базисних пунктах.
- `md_amr.slippage_buffer_bps` (float): Буфер на проковзування.
- `md_amr.scaleout_fraction` (float): Доля для часткового виходу (scale-out).
- `md_amr.scaleout_cost_model` (str): Модель розрахунку витрат при виході (`round_trip`, `one_way`).
- `md_amr.weights` (dict): Ваги впливу різних таймфреймів на прийняття рішення (`d1`, `h1`, `m30`, `m15`).
- `md_amr.execution`: Налаштування виконання 
  - `entry_order_type`: `LIMIT` (стандарт для AMR)
  - `entry_tif`: `GTX` (post-only)
  - `exit_order_type`: `MARKET`
  - `gtx_retry_max`, `gtx_retry_offset_bps`, `gtx_fallback_to_market`: Параметри управління лімітними ордерами.

## 4. Objective Engine
Стратегія інтегрована з глобальним рушієм об'єктивної оцінки сигналів (`Objective Engine`).
- `md_amr.objective.enabled` (bool): Увімкнення Objective Engine виключно для цієї стратегії.
- `md_amr.objective.regimes`: Налаштування впливу (`weights`), множників (`multiplier`) та блокувань (`gate`) в залежності від поточного ринкового режиму.
  - Наявні режими: `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `TREND_UP`, `TREND_DOWN`, `MEAN_REVERSION`, `UNCERTAIN`, `FLAT_LOW`, `FLAT_NORMAL`, `FLAT_HIGH`.
  - У кожному режимі визначається, наскільки важливі `cost`, `risk`, `edge`, `execution`, `information`, `behavior`.

## 5. Гейти та захист
- `md_amr.safety_gates.enabled` (bool): Увімкнення базових гейтів.
- `md_amr.llm_gate`: Гейт на базі сентименту від LLM.
- `md_amr.reconciliation`: Звірка позицій з допусками на дрифт (drift_tolerance).
- `md_amr.concentration_guard`: Захист від надмірної концентрації ордерів (max_simultaneous_entries_per_bar).

## 6. Активи (Assets / Instruments)
Налаштування для окремих символів (напр., `BTCUSDT`, `ETHUSDT`, `SOLUSDT`).
- `enabled`: Увімкнення стратегії для символу.
- `cooldown_sec`: Кулдаун між угодами на активі.
- `allowed_regimes`: Режими, в яких дозволено торгувати цим символом (зазвичай `MEAN_REVERSION`, `LOW_VOLATILITY`, `HIGH_VOLATILITY` і FLAT-режими).
- `exit.sl_pct`: Базовий відсоток Stop Loss.
- `exit.tp_rr`: Базовий рівень Take Profit (Risk/Reward ratio).
- `exit.regime_tpsl`: Адаптивний TP/SL на базі поточного режиму (використовує множники до базових SL/TP значень).