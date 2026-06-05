# 📄 Semantic Configuration Passport: `config/aurora/system.yaml` (Gemini Extraction)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/system_passport_gemini.md
> - Scope: First ~150 lines of `config/aurora/system.yaml`
> - Purpose: Baseline passport extraction for top-level system configuration.

Цей паспорт описує базові налаштування системи `Aurora/Phenix`: глобальні режими, ринкові дані (market data), екзекуцію (execution), ризикові моделі (risk_core, kelly, hawkes) та механізми hardening.

---

## 1. Global System Metadata

### `config_version`
- **Type:** `string` (`1.0.1`)
- **Role:** Версіонування конфігураційного файлу для зворотної сумісності (back-compat) та валідації міграцій.

### `trading_mode`
- **Type:** `string` (`hybrid_live_data_testnet_exec`)
- **Role:** Глобальний майстер-перемикач середовища. Pydantic синхронізує це значення з `trading.mode` (див. `trading_passport_gemini.md`). Визначає, чи йдуть ордери на реальну біржу чи на testnet.

---

## 2. System Level Settings (`system`)

### `system.market_data`
Налаштування внутрішніх черг (Queues) та брокерів для обробки WebSocket/REST ринкових даних.

- **`queue_maxsize` / `local_queue_maxsize`:** `int` (10000). Розмір асинхронних черг (захист від OOM при бекпресурі).
- **`emit_workers`:** `int` (4). Кількість паралельних воркерів для публікації подій ринку на Event Bus.
- **`tick_ttl_ms` / `bar_ttl_ms`:** `int` (2000 / 10000). Максимально допустимий "вік" (старість) тика або бара в мілісекундах перед тим, як він буде відхилений системою як "stale".
- **`bar_event_age_mode`:** `string` (`received`). Вказує, що вік події рахується від локального часу отримання сервером, а не від біржового `event_time`.
- **`ws_heartbeat_sec`:** `float` (20.0). WebSocket keep-alive інтервал.
- **`ws_receive_timeout_sec` / `trade_silence_reconnect_sec`:** `float` (60.0 / 120.0). Детектори тихого зависання (Silent Hang). Якщо немає даних за цей час, система форсує реконнект WebSocket.
- **`proxy_batch_size` / `proxy_queue_get_timeout_sec` / `proxy_idle_sleep_sec`:** Налаштування для IPC (`multiprocessing`), коли `MarketDataProxy` читає з черг між процесами.

### `system.validate_instruments_on_startup`
- **Type:** `bool` (`true`)
- **Role:** Якщо `true`, система при старті перевіряє валідність усіх тикерів через Binance API (чи не делістнуті, чи правильна точність ціни/розміру).

### `system.warn_only_filters` / `debug_event_listener_enabled`
- **Type:** `bool` (`false`)
- **Role:** Прапорці для локального дебагу. Вимкнені у production/hybrid.

---

## 3. Operational Config (`ops`)

### `ops.panic_killswitch`
- **Type:** `bool` (`false`)
- **Role:** Глобальне аварійне гальмо виконання. Якщо `true`, `FSMOpen` негайно блокує всі нові заявки (`CMD:OPEN`).

### `ops.metrics_url` / `reports_dir`
- **Type:** `string`
- **Role:** Точки призначення для телеметрії та генерації офлайн-репортів (напр. з `tools/metrics_summary.py`).

---

## 4. Execution Base (`execution`)

Блок `execution` у `system.yaml` виступає майстер-конфігом для `execution_position` домену, доповнюючи специфічні налаштування з `trading.yaml`.

### `execution.manage.brackets` (SL / TP)
- **`sl.fixed_bps` / `tp.fixed_bps`:** `int` (40 / 80). Дефолтні відстані для Stop Loss і Take Profit, якщо стратегія не надала власних.
- **`oco_emulation`:** `bool` (`true`). Системна емуляція One-Cancels-The-Other для зниження залишків (Orphan brackets).
- **`offset_bps`:** `int` (5). Safety margin — відступ при виставленні ордерів, щоб уникнути помилок `order would immediately trigger`.

### `execution.manage.emergency`
- **Role:** Аварійний вихід з позиції. (`enabled: false`, `emergency_sl_bps: 100`, `wait_mode_bars: 2`). Якщо ціна різко йде проти позиції на `100 bps` (і це увімкнено), система кидає Market Close і блокує нові входи на `2` бара.

### `execution.manage.orphan_monitor`
- **Role:** Збирач сміття (GC) для забутих біржових ордерів. (`periodic_interval_sec: 300`). Скасовує ордери батчами (`batch_cancel_limit: 50`) в обхід основного FSM.

### `execution.exposure`
- **Role:** Суворі ліміти капіталу (`max_equity_utilization_pct: 150.0`, `max_portfolio_fraction: 150.0`, `max_directional_ratio: 50.0`) та дефолтне плече (`leverage_defaults`) для кожного активу (`BTCUSDT: 20`).
- **Pending Logic:** Враховувати нереалізовані ордери у ризик (`count_pending_orders: true`), але не враховувати ордери на закриття (`exclude_reduce_only: true`).

### `execution.watchdog`
- **Role:** Захист від втрати пакетів / зависання ордерів на біржі. Ордер має отримати підтвердження (ACK) за 8 секунд (`ack_ttl_ms: 8000`) або вважається втраченим.

### `execution.order_params`
- **Role:** Біржові дефолти для ордерів (наприклад, `LIMIT: {timeInForce: GTC}`, `STOP_MARKET: {workingType: MARK_PRICE}`). 

### `execution.order_guardian`
- **Role:** Зберігання стану в БД (`ledger_db_path: data/order_ledger.db`) з режимом відновлення після збоїв (`unified: true`).

---

## 5. Quantitative / Math Models (`trailing`, `sequential_tests`, `risk_core`, `kelly`, `hawkes`)

Ці параметри визначають поведінку складних математичних оверлеїв поверх FSM.

- **`trailing`:** Динамічний Trailing Stop. Активується при прибутку `activation_pct: 0.003` (0.3%) і тягне стоп на відстані `trail_pct: 0.006` (0.6%).
- **`sequential_tests` (wald / glr):** Параметри статистичних тестів Вальда (SPRT) та GLR для визначення режимів/відхилень (`alpha: 0.05`, `beta: 0.2`).
- **`risk_core`:** Ядро ризику портфелю (`cvar_threshold_bps: 120`). Ліміти інвентарю (`max_abs_position: 500`).
- **`kelly`:** Консервативний келі-сайзинг (`fraction_cap: 0.85`, період напіврозпаду для метрик `decay_half_life_days: 5`).
- **`hawkes`:** Процеси Хоукса для детекції мікроструктурного "зараження" / черг (`kernel.decay_beta_ms: 250.0`, `update_interval_ms: 100`).

---

## 6. Hardening (`hardening`)

Налаштування системної резильєнтності до відмов (Resilience).

### `hardening.ttl_config`
- **Role:** Time-To-Live (TTL) для різних фаз постановки ордера (`entry_place_ttl_ms: 5000`, `cancel_ttl_ms: 2000`).

### `hardening.retry_config`
- **Role:** Механізм повторних спроб (Backoff/Retry) при мережевих або біржових помилках (`max_tries: 3`, `backoff_ms: 1000` з джитером `jitter: true`).

### `hardening.circuit_breaker`
- **Role:** Запобіжник (Circuit Breaker). Якщо відбувається `fail_max: 5` помилок підряд, торгова активність призупиняється на `reset_timeout_sec: 30`. Винятки (`exclude`): специфічні помилки Binance, які система має обробляти штатно (наприклад `-2010` - недостатньо балансу).
