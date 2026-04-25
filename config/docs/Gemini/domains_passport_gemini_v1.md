# 📄 Semantic Configuration Passport: `config/aurora/domains.yaml` (Part 1)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/domains_passport_gemini_v1.md
> - Scope: Lines 1-150 of `config/aurora/domains.yaml`
> - Purpose: Baseline passport extraction for domain-specific logic configurations.

Цей паспорт описує логіку та налаштування на рівні окремих доменів системи: `decision_making` (прийняття рішень, ризик-гейти) та частково `feature_engineering` (генерація фічів).

---

## 1. Global Debug Overrides (`debug`)

### `debug.disable_positions_stale_gate` / `disable_daily_loss_limit`
- **Type:** `bool` (`false`)
- **Role:** Прапорці для локального дебагу або специфічного тестування. Дозволяють тимчасово вимкнути захист від "старих" позицій або жорсткий денний ліміт збитків. У production мають бути `false`.

---

## 2. Decision Making Domain (`decision_making`)

Цей домен відповідає за перетворення сирих сигналів у `TradeIntent`, фільтрацію ризиків (Risk Gates) та сайзинг.

### `decision_making.position_sizing`
- **Role:** Ліміти розміру позиції для нових намірів на трейд.
- **`min_position_size_usd`:** `float` (10.0). Мінімально допустимий розмір позиції в доларах.
- **`liquidity_based_cap_usd`:** `float` (10000.0). Максимальний кеп, базований на доступній ліквідності (запобігає занадто великому маркет-імпакту).

### `decision_making.entry_plan`
- **Role:** Формування параметрів входу (Entry) та брекетів (TP/SL) на основі метрик волатильності (ATR).
- **`enabled`:** `bool` (`true`). Увімкнення розрахунку.
- **`atr_period`:** `int` (14). Період для розрахунку Average True Range.
- **`entry_k_atr` / `sl_k_atr` / `tp_k_atr`:** Множники ATR для розрахунку відступу ціни входу (0.3), Stop Loss (1.5) та Take Profit (2.0).
- **`obi_weight` / `obi_mod_clamp_min` / `obi_mod_clamp_max`:** Модуляція відступів на основі Order Book Imbalance.
- **`structural_stop_enabled`:** `bool` (`false`). Чи використовувати структурні рівні для стопів.
- **`confidence_scale`:** `float` (0.5). Базовий множник впевненості.
- **`min_stop_bps`:** `int` (15). Жорсткий мінімум для відстані Stop Loss у базисних пунктах.

### `decision_making.qos` (Quality of Service)
- **Role:** Захист системи від перевантаження (Rate Limiting / Throttling) на рівні генерації інтентів.
- **`exposure_block_cooldown_sec`:** `int` (60). Кулдаун після блокування по експозиції.
- **`symbol_cooldown_sec`:** `int` (3). Мінімальний час між двома інтентами по одному символу.
- **`max_intents_per_minute_per_symbol`:** `int` (20). Жорсткий ліміт на спам.
- **`mode` / `enforce`:** Режим роботи QoS (`enforce: true` означає жорстке відхилення нових інтентів при перевищенні лімітів).

### `decision_making.features.ttl_sec`
- **Type:** `int` (30)
- **Role:** Час життя фічів (Time-To-Live). Якщо фічі старіші за 30 секунд, рішення не приймається (Fail-Closed).

### Санітарні гейти (Sanity Gates)
- **`directional_sanity`:** Перевіряє узгодженість напрямку тренду. `min_regime_confidence: 0.42` — мінімальна впевненість у режимі для дозволу на вхід.
- **`price_motion_sanity`:** Захист від "флеш-крешів" та "повільного стікання" ціни. `flash_threshold_norm: 1.0`, `bleed_threshold_norm: 0.5`.

### `decision_making.regime_loss_embargo`
- **Role:** Ембарго (блокування) на торгівлю після збитків у певному режимі. `enabled: true`, `min_loss_threshold_net: 0.0`.

### Контекстні гейти (Degraded Context)
- **`fail_closed_on_degraded_context`:** `bool` (`false`). 
- **`degraded_context_contracts_by_strategy`:** Визначає, які саме фічі є "критичними" (`critical_keys`) для кожної стратегії (наприклад, для `mean_reversion` критичними є `tfi`, `obi`, `price_motion`, `liquidity_kappa`). Якщо критична фіча `NaN`, стратегія блокується.

---

## 3. Feature Engineering Domain (`feature_engineering`) - Початок

Домен розрахунку ринкових метрик, стаканів, дисбалансів та мікроструктури.

### Базові налаштування
- **`enabled_timeframes_sec`:** Список таймфреймів (180, 300, 900) для яких інженерія розраховує агреговані бари/фічі.
- **`trace_features`:** `bool` (`false`). Детальне логування (Trace).

### Мікроструктурні компоненти
Параметри "ковзних вікон" та множників для розрахунку базових індикаторів:
- **`ema`:** Короткі та довгі періоди (`period_short: 1`, `period_long: 2`).
- **`volatility`:** Довжина SMA для волатильності (`sma_length: 10`, вікно `60s`).
- **`liquidity`:** Калібрування функції ліквідності (`depth_half: 1000.0`, межі `kappa_min: 0.3`, `kappa_max: 1.0`).
- **`volume_spike` / `volume_zscore`:** Детекція аномальних сплесків об'єму (Z-score кліпінг `clip_sigma: 5.0`).
- **`large_trade_imbalance`:** Дисбаланс великих трейдів (`window_ms: 1000`, `min_trades: 1`).
- **`depth_imbalance`:** Order Book Imbalance (OBI). `use_laplace_smoothing: true` (математичне згладжування для уникнення ділення на нуль при пустих стаканах).
- **`delta_price`:** `spike_filter_ms: 600000` (Фільтр аномальних цінових спайків на 10-хвилинному вікні).