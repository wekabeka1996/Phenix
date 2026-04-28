# 📄 Semantic Configuration Passport: `config/aurora/domains.yaml` (Gemini Extraction Final)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/domains_passport_gemini.md
> - Scope: Lines 1-615 (Full File) of `config/aurora/domains.yaml`
> - Purpose: Baseline passport extraction for domain-specific logic configurations.

Цей паспорт описує логіку та налаштування на рівні окремих доменів системи.

---

## 1. Global Debug Overrides (`debug`)

### `debug.disable_positions_stale_gate` / `disable_daily_loss_limit`
- **Type:** `bool` (`false`)
- **Role:** Прапорці для локального дебагу або тестування. Дозволяють тимчасово вимкнути захист. У production мають бути `false`.

---

## 2. Decision Making Domain (`decision_making`)

Цей домен відповідає за перетворення сирих сигналів у `TradeIntent`, фільтрацію ризиків (Risk Gates) та сайзинг.

### `decision_making.position_sizing`
- **Role:** Ліміти розміру позиції для нових намірів на трейд.
- **`min_position_size_usd`:** `float` (10.0). Мінімально допустимий розмір позиції в доларах.
- **`liquidity_based_cap_usd`:** `float` (10000.0). Максимальний кеп, базований на доступній ліквідності.

### `decision_making.entry_plan`
- **Role:** Формування параметрів входу (Entry) та брекетів (TP/SL).
- **`enabled`:** `bool` (`true`).
- **`atr_period`:** `int` (14).
- **`entry_k_atr` / `sl_k_atr` / `tp_k_atr`:** Множники ATR для розрахунку відступів ціни входу (0.3), Stop Loss (1.5) та Take Profit (2.0).
- **`obi_weight` / `obi_mod_clamp_min` / `obi_mod_clamp_max`:** Модуляція відступів на основі Order Book Imbalance.
- **`structural_stop_enabled`:** `bool` (`false`).
- **`confidence_scale`:** `float` (0.5).
- **`min_stop_bps`:** `int` (15). Жорсткий мінімум для відстані Stop Loss.

### `decision_making.qos` (Quality of Service)
- **Role:** Захист системи від перевантаження інтентами.
- **`exposure_block_cooldown_sec`:** `int` (60). Кулдаун після блокування по експозиції.
- **`symbol_cooldown_sec`:** `int` (3). Мінімальний час між двома інтентами по одному символу.
- **`max_intents_per_minute_per_symbol`:** `int` (20). Жорсткий ліміт на спам.
- **`mode` / `enforce`:** Режим роботи QoS (`enforce: true`).

### `decision_making.features.ttl_sec`
- **Type:** `int` (30)
- **Role:** Час життя фічів (Time-To-Live). Якщо фічі старіші за 30 секунд, рішення не приймається.

### Санітарні гейти (Sanity Gates)
- **`directional_sanity`:** `min_regime_confidence: 0.42` — мінімальна впевненість у режимі для дозволу на вхід.
- **`price_motion_sanity`:** Захист від "флеш-крешів". `flash_threshold_norm: 1.0`, `bleed_threshold_norm: 0.5`.
- **`regime_loss_embargo`:** Ембарго на торгівлю після збитків у певному режимі (`enabled: true`, `min_loss_threshold_net: 0.0`).

### Контекстні гейти (Degraded Context)
- **`fail_closed_on_degraded_context`:** `bool` (`false`).
- **`degraded_context_contracts_by_strategy`:** Визначає, які фічі є "критичними" (`critical_keys`). Якщо критична фіча `NaN`, стратегія блокується.

---

## 3. Feature Engineering Domain (`feature_engineering`)

Домен розрахунку ринкових метрик, стаканів, дисбалансів та мікроструктури.

### Базові налаштування
- **`enabled_timeframes_sec`:** Список таймфреймів (180, 300, 900).
- **`trace_features`:** `bool` (`false`). Детальне логування.

### Мікроструктурні компоненти
- **`ema`:** `period_short: 1`, `period_long: 2`.
- **`volatility`:** `sma_length: 10`, вікно `60s`.
- **`liquidity`:** `depth_half: 1000.0`, `kappa_min: 0.3`, `kappa_max: 1.0`.
- **`volume_spike` / `volume_zscore`:** Детекція аномальних сплесків об'єму (Z-score кліпінг `clip_sigma: 5.0`).
- **`large_trade_imbalance`:** Дисбаланс великих трейдів (`window_ms: 1000`, `min_trades: 1`).
- **`depth_imbalance`:** Order Book Imbalance (OBI). `use_laplace_smoothing: true`.
- **`delta_price`:** `spike_filter_ms: 600000`.

### `macro_sync`
- **Role:** Синхронізація "еталонних" активів (`anchors`: `BTCUSDT`, `ETHUSDT`) з поточним активом. `time_diff_threshold_ms: 60000`. `align_mode: tail_min_len`.

### `readiness_registry` та `warmup`
- **`declared_keys`:** Повний перелік з 14 фічів, які домен зобов'язаний розрахувати.
- **`warmup.enforcement_mode`:** `fail_fast`. Якщо хоча б одна фіча не готова (`check_full_ready_invariant: true`), домен сигналізує про неготовність.

### `feature_sanity`
- **Role:** Жорсткі математичні межі для кожної фічі (Hard Bounds).
- **`nan_inf_behavior`:** `neutral_and_not_ready`.
- Межі: `obi` [-1, 1], `tfi` [-1, 1], `macro_resid` [-3, 3], `volume_spike` [0, 10].

### `macro_resid` та `absorption`
- Розрахунок макро-резидуалів (`beta_window: 60`, `winsor_percentile: 0.05`).
- Абсорбція розраховується з вікном `30`, дедуплікацією та кліпінгом `1.0`.

### `pillars` (Когнітивні опори сигналів)
- Трирівнева архітектура часових горизонтів:
  1. **`tactician`:** (15 хв). Вага: 0.65.
  2. **`operator`:** (4 год). Вага: 0.3.
  3. **`strategist`:** (1 день). Вага: 0.05.
- **`backfill`:** Автоматичне завантаження історичних свічок при старті.

---

## 4. TA Features Domain (`ta_features`)

- **`timeframes_sec`:** `[180, 300, 900]`.
- **`warm_up_bars`:** `int` (30). Кількість свічок для прогріву індикаторів.
- **`buffer_max_bars`:** `int` (300).

---

## 5. Risk Management Domain (`risk_management`)

Агрегований ризик-скоринг системи.

- **`risk_score_weights`:** Ваги компонентів (`delta_price_pct: 0.1`, `obi: 0.3`, `tfi: 0.3`, `absorption_inverse: 0.3`, `absorption_feature: 0.2`).
- **`validation`:** Загальна сума ваг повинна знаходитися в межах від 0.5 до 2.0.
- **`trading_allowed_thresholds`:** `max_risk_score: 0.96`. Абсолютний ліміт ризику.

---

## 6. Position Tracking Domain (`position_tracking`)

- **`precision`:** Математична точність портфелю (`decimal_places: 2`, `quantity_min_threshold: 1.0e-09`, `flat_position_threshold: 1.0e-12`).
- **`positions_stale_ttl_sec`:** 15 сек.

---

## 7. Execution Position Domain (`execution_position`)

Керує станом ордерів, взаємодіє з біржею та захищає виконання.

### Базові налаштування та Ліміти
- **`fallback.policy`:** `fail_closed`.
- **`exposure_guard`:** Ліміти капіталу (`max_equity_utilization_pct: 150.0`, `max_directional_ratio: 20.0`, `max_concentration_pct: 500.0`).
- **`pending_ttl_sec`:** `int` (90). Час життя наміру на відкриття.

### Дедуплікація та Реконсиліація
- **`inflight_reconcile`:** Монітор "завислих" ордерів (`reconcile_interval_sec: 10`).
- **`event_dedup`:** Дедуплікація біржових подій. Розмір кешу `100000`, зберігає стан на диску (`execution_terminal_identity_cache_v1.json`).

### Pending Limit Orders
- **`cancel_on_regime_change`:** `true`.
- **`supersede_reprice_guard`:** `true`. Дозволяє перевиставити ордер за кращою ціною (мінімум на `5 bps` та `0.1 ATR`).
- **`advanced_stale_cancel`:** Скасовує старі ордери (понад 300 сек), якщо ціна відхилилася більше ніж на `0.5 ATR`.

### Guardian та Стан
- **`guardian`:** `unified: true`, `emit_tidy_event: true` (deprecated compatibility alias), `emit_tidy_monitoring_event: true` (monitoring-only tidy telemetry; does not control `EVT:SYMBOL_TIDY`).
- **`restore_artifact`:** Стан зберігається у `execution_position_restore_envelope_v1.json` кожні 30 секунд (Crash Recovery).

### 7.1. `position_policy_sidecar` (AI-Augmented Position Management)
Сайдкар, який рекомендує дострокове закриття позицій.
- **`freshness` / `startup_grace`:** Вимагає свіжих даних і має прогрів `30000 ms`.
- **`profitability_guard`:** `min_unrealized_pnl_pct: 0.25`. Забороняє закривати прибуткові позиції завчасно.
- **`scoring`:** Оцінює `microstructure_adverse_pressure`, `regime_exhaustion_hint`, `conviction_decay`.
- **`thresholds`:** Рекомендує закриття при `recommend_soft_close_at: 0.3`.
- **`allowed_actions`:** Сайдкару дозволено лише `soft_close_symbol_current_net_only`. ЗАБОРОНЕНО мутувати брекети (`bracket_mutation: false`).

---

## 8. Shadow Telemetry Domain (`shadow_telemetry`)

Інфраструктура для комунікації з ШІ.
- **`ingest` (Читання):** IPC Tap (`tcp://127.0.0.1:7101`) слухає суворий перелік подій. Черга `50000` з `fail_closed`.
- **`api` (Запис від ШІ):** REST API (`port: 8443`). Має **Allowlist** (`1000PEPEUSDT`), Rate-limit `30`/хв, Idempotency TTL `300` сек.
- **`egress_to_main`:** Канал зворотного зв'язку (`tcp://127.0.0.1:7102`).
- **`snapshot`:** Генерує зліпки стану при `EVT:FEATURES_CALCULATED` (Observation Space $O_t$ для агента).

---

## 9. Objective Engine Domain (`objective_engine`)

Двигун багатокомпонентної винагороди (Dense Multi-Objective Reward Function).
1. **`cost`:** Штрафи за комісії (`alpha_fee`) та проковзування (`alpha_slippage`).
2. **`risk`:** Оцінка ризику (`phi_inventory`) та волатильності (`phi_volatility`).
3. **`edge`:** Співвідношення Risk/Reward (`omega_rr`) та відстань до стопа.
4. **`execution`:** Вплив ліквідності (`omega_liquidity`) та спреду (`phi_spread_drag`).
5. **`information`:** Штрафи за старі дані (`phi_staleness`) та впевненість у режимі (`omega_regime_confidence`).
6. **`behavior`:** Штрафи за стрес: блокування інтентів (`phi_blocked_intents: 0.08`), часті скасування (`phi_cancel_replace`), повторні входи (`phi_reentry`).
