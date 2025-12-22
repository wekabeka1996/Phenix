# Таймаути, TTL, інтервали та вікна у config/aurora/domains.yaml

| Параметр | Опис | Навіщо використовується |
|----------|------|------------------------|
| decision_making.qos.exposure_block_cooldown_sec | Час (сек), протягом якого після блокування exposure не можна відкривати нові позиції по символу | Захист від надмірної частоти відкриття позицій після блокування |
| decision_making.qos.symbol_cooldown_sec | Мінімальний інтервал (сек) між двома інтенціями по одному символу | Анти-спам, захист від order storm |
| decision_making.features.ttl_sec | Максимальний вік (сек) даних features, після якого вони вважаються застарілими | Гарантія актуальності сигналів для прийняття рішень |
| decision_making.risk_skew.max_skew_sec | Максимально допустима різниця (сек) між timestamp features та risk | Захист від розсинхронізації risk/feature даних |
| decision_making.risk_skew.defer_cooldown_sec | Інтервал (сек) між повторними спробами після DEFER через risk skew | Контроль частоти повторних спроб |
| feature_engineering.ema.period_short | Короткий період EMA (барів) | Для розрахунку короткої EMA |
| feature_engineering.ema.period_long | Довгий період EMA (барів) | Для розрахунку довгої EMA |
| feature_engineering.volume.window_sec | Вікно (сек) для агрегації об'єму | Для розрахунку об'ємних індикаторів |
| feature_engineering.volatility.window_sec | Вікно (сек) для агрегації волатильності | Для розрахунку волатильності |
| feature_engineering.large_trade_imbalance.window_ms | Вікно (мс) для пошуку великих трейдів | Для детекції аномальних об'ємів |
| feature_engineering.macro_sync.time_diff_threshold_ms | Максимальна різниця (мс) між часовими мітками anchor-символів | Для синхронізації потоків даних |
| feature_engineering.macro_sync.ttl_ms | TTL (мс) для збереження синхронізованих даних | Гарантія актуальності macro_sync |
| feature_engineering.macro_sync.window | Кількість бінів у macro_sync | Для агрегації даних по вікнах |
| position_tracking.precision.quantity_min_threshold | Мінімальний розмір позиції (float) для визнання її не-нульовою | Для уникнення false-positive flat |
| position_tracking.precision.flat_position_threshold | Поріг (float) для визнання позиції flat | Для коректної інтерпретації flat |
| position_tracking.positions_stale_ttl_sec | TTL (сек) для актуальності портфеля | Якщо портфель не оновлювався — gate блокує торгівлю |
| position_tracking.thread_timeouts.join_timeout_sec | Таймаут (сек) для join потоків | Для уникнення зависань при завершенні потоків |
| account_observer.poll_interval_sec | Інтервал (сек) між опитуванням балансу/позицій | Частота оновлення account state |
| account_observer.thread_timeouts.join_timeout_sec | Таймаут (сек) для join потоків account observer | Для коректного завершення потоків |
| execution_position.watchdog.ack_ttl_ms | Максимальний час (мс) очікування ACK від біржі | Для виявлення завислих ордерів |
| execution_position.watchdog.fill_ttl_ms | Максимальний час (мс) очікування fill | Для виявлення завислих ордерів |
| execution_position.watchdog.check_interval_ms | Інтервал (мс) перевірки статусу ордерів | Частота перевірки watchdog |
| execution_position.exposure_guard.pending_ttl_sec | TTL (сек) для pending ордерів | Якщо ордер завис — буде скасовано |
| execution_position.exposure_guard.post_fill_ttl_sec | Час (сек) після fill, протягом якого позиція вважається "свіжою" | Для захисту від double-fill |
| execution_position.exposure_guard.stale_ttl_sec | TTL (сек) для актуальності portfolio після fill | Для уникнення торгівлі по застарілим даним |
| execution_position.exposure_guard.pending_timeout_sec | Таймаут (сек) очікування відповіді на pending | Для fail-fast cancel |
| execution_position.fsm_open.idempotency_window_sec | Вікно (сек) для ідемпотентності відкриття | Захист від дублювання intent |
| execution_position.order_index.ttl_sec | TTL (сек) для order index (in-flight refs) | Для очищення старих refs |
| execution_position.metrics_collector.window_size_minutes | Вікно (хв) для агрегації метрик | Для статистики по rejections |
| execution_position.metrics_collector.recent_rejections_minutes | Вікно (хв) для підрахунку недавніх відмов | Для rate limiting rejection |
| execution_position.idempotent_cancel.max_retries | Максимальна кількість повторів для ідемпотентного cancel | Для контролю retriable cancel |

---

*Якщо потрібен аналогічний опис для інших конфігів — повідомте!*
