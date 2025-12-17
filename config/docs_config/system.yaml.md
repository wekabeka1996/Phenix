# Документація до config/aurora/system.yaml
# Паспортізація кожного блоку конфігурації (українською)

# -------- config_version: --------
#   - Версія формату конфігурації.
#   - Дозволяє перевірку сумісності при завантаженні.
#   - Використовується у всіх модулях, що працюють із system.yaml.
#   - Pydantic: str, формат x.y.z

# -------- trading_mode: --------
#   - Операційний режим торгового бота.
#   - Варіанти: "live", "testnet", "hybrid_live_data_testnet_exec".
#   - Визначає, які ключі API та потоки даних використовуються.
#   - Використовується у core/main.py, binance_adapter.py.
#   - Pydantic: str, enum.

# -------- sequential_tests: --------
#   wald:
#     alpha: 0.05
#       - Рівень значущості для тесту Вальда.
#       - Використовується у модулі статистичних тестів.
#       - Pydantic: float, (0,1).
#     beta: 0.2
#       - Ймовірність помилки другого роду.
#       - Використовується у Wald test.
#       - Pydantic: float, (0,1).
#     mu0: 0.0
#       - Гіпотеза H0 (середнє).
#       - Використовується у Wald test.
#       - Pydantic: float.
#     mu1: 0.5
#       - Гіпотеза H1 (альтернативне середнє).
#       - Використовується у Wald test.
#       - Pydantic: float.
#     sigma: 1.0
#       - Стандартне відхилення.
#       - Використовується у Wald test.
#       - Pydantic: float, >0.
#   glr:
#     alpha: 0.05
#       - Рівень значущості для GLR тесту.
#       - Використовується у GLR test.
#       - Pydantic: float, (0,1).
#     beta: 0.2
#       - Ймовірність помилки другого роду.
#       - Використовується у GLR test.
#       - Pydantic: float, (0,1).
#     min_samples: 5
#       - Мінімальна кількість вибірок для запуску GLR тесту.
#       - Використовується у GLR test.
#       - Pydantic: int, >0.
#
# -------- risk_core: --------
#   cvar_threshold_bps: 120
#     - Поріг CVaR (Conditional Value at Risk) у базисних пунктах.
#     - Використовується для обмеження ризику портфеля.
#     - Використовується у risk_core.py, risk_manager.py.
#     - Pydantic: int, >0.
#   stress_scenarios:
#     - Список сценаріїв стрес-тестування (наприклад, flash_crash, volatility_spike).
#     - Використовується у risk_core.py, risk_manager.py.
#     - Pydantic: list[str].
#   inventory_limits:
#     max_abs_position: 500
#       - Максимальна абсолютна позиція (наприклад, 500 BTC).
#       - Використовується у risk_core.py, risk_manager.py.
#       - Pydantic: int, >0.
#     max_daily_notional: 10000000
#       - Максимальний денний обіг (USD).
#       - Використовується у risk_core.py, risk_manager.py.
#       - Pydantic: int, >0.
#
# -------- kelly: --------
#   fraction_cap: 0.85
#     - Максимальна частка Kelly для розрахунку розміру ставки.
#     - Використовується у kelly.py, risk_manager.py.
#     - Pydantic: float, (0,1].
#   decay_half_life_days: 5
#     - Період напіврозпаду для згладжування Kelly fraction (днів).
#     - Використовується у kelly.py.
#     - Pydantic: int, >0.
#
# -------- calibrator: --------
#   state_store:
#     backend: sqlite
#       - Тип бекенду для зберігання стану калібратора.
#       - Використовується у calibrator.py.
#       - Pydantic: str, enum.
#     path: data/calibrator/state.db
#       - Шлях до файлу стану.
#       - Використовується у calibrator.py.
#       - Pydantic: str.
#     versioning: true
#       - Чи вмикати версіонування стану.
#       - Використовується у calibrator.py.
#       - Pydantic: bool.
#     retention_days: 30
#       - Кількість днів зберігання стану.
#       - Використовується у calibrator.py.
#       - Pydantic: int, >0.
#
# -------- hawkes: --------
#   enabled: true
#     - Вмикає/вимикає Hawkes процес для моделювання подій.
#     - Використовується у hawkes.py.
#     - Pydantic: bool.
#   kernel.decay_beta_ms: 250.0
#     - Параметр згасання ядра (мс).
#     - Використовується у hawkes.py.
#     - Pydantic: float, >0.
#   eta_max: 1.0
#     - Максимальна інтенсивність процесу.
#     - Використовується у hawkes.py.
#     - Pydantic: float, >0.
#   update_interval_ms: 100
#     - Інтервал оновлення параметрів (мс).
#     - Використовується у hawkes.py.
#     - Pydantic: int, >0.
#   window_ms: 1000
#     - Вікно для розрахунку Hawkes процесу (мс).
#     - Використовується у hawkes.py.
#     - Pydantic: int, >0.
#   bivariate: false
#     - Чи використовувати біваріантний Hawkes процес.
#     - Використовується у hawkes.py.
#     - Pydantic: bool.
# -------- hotreload_whitelist: --------
#   - Список параметрів, які можна змінювати "на льоту" без перезапуску системи.
#   - Дозволяє оперативно підлаштовувати ключові параметри ризику, тестів, Hawkes-процесу тощо.
#   - Використовується у core/config_hotreload.py, config_manager.py.
#   - Pydantic: list[str].
#
# -------- logging: --------
#   level: "DEBUG"
#     - Рівень логування: DEBUG, INFO, WARNING, ERROR.
#     - Визначає деталізацію логів.
#     - Використовується у core/logging.py.
#     - Pydantic: str, enum.
#   file: "logs/aurora_core.log"
#     - Шлях до файлу логів.
#     - Використовується у core/logging.py.
#     - Pydantic: str.
#   format: "json"
#     - Формат логів: 'json' або 'text'.
#     - Використовується у core/logging.py.
#     - Pydantic: str, enum.
#   rotation:
#     max_bytes: 10485760
#       - Максимальний розмір файлу логів (байти).
#       - Використовується у core/logging.py.
#       - Pydantic: int, >0.
#     backup_count: 5
#       - Кількість резервних копій логів.
#       - Використовується у core/logging.py.
#       - Pydantic: int, >0.
#
# -------- hardening: --------
#   ttl_config:
#     entry_place_ttl_ms: 5000
#       - TTL для заявок на відкриття (мс).
#       - Використовується у core/hardening.py, order_manager.py.
#       - Pydantic: int, >0.
#     bracket_place_ttl_ms: 3000
#       - TTL для bracket-ордерів (мс).
#       - Використовується у core/hardening.py, order_manager.py.
#       - Pydantic: int, >0.
#     cancel_ttl_ms: 2000
#       - TTL для скасування ордерів (мс).
#       - Використовується у core/hardening.py, order_manager.py.
#       - Pydantic: int, >0.
#   retry_config:
#     max_tries: 3
#       - Максимальна кількість спроб повтору.
#       - Використовується у core/hardening.py, order_manager.py.
#       - Pydantic: int, >0.
#     backoff_ms: 1000
#       - Базовий час backoff (мс).
#       - Використовується у core/hardening.py, order_manager.py.
#       - Pydantic: int, >0.
#     jitter: true
#       - Чи додавати випадковий jitter до backoff.
#       - Використовується у core/hardening.py, order_manager.py.
#       - Pydantic: bool.
#   circuit_breaker:
#     fail_max: 5
#       - Кількість помилок для відкриття circuit breaker.
#       - Використовується у core/hardening.py, circuit_breaker.py.
#       - Pydantic: int, >0.
#     reset_timeout_sec: 30
#       - Час у стані OPEN перед переходом у HALF_OPEN (секунди).
#       - Використовується у core/hardening.py, circuit_breaker.py.
#       - Pydantic: int, >0.
#     exclude:
#       - Список виключень (exception patterns), які не рахуються як помилки.
#       - Використовується у core/hardening.py, circuit_breaker.py.
#       - Pydantic: list[str].
#     open_threshold_pct: 20
#       - Відсоток помилок для відкриття circuit breaker.
#       - Використовується у core/hardening.py, circuit_breaker.py.
#       - Pydantic: int, 0-100.
#     error_rate_window_sec: 60
#       - Вікно для підрахунку error rate (секунди).
#       - Використовується у core/hardening.py, circuit_breaker.py.
#       - Pydantic: int, >0.
#     half_open_attempts: 3
#       - Кількість тестових викликів у HALF_OPEN.
#       - Використовується у core/hardening.py, circuit_breaker.py.
#       - Pydantic: int, >0.
#   market_data:
#     max_allowed_lag_ms: 1000
#       - Максимальний лаг ринкових даних (мс).
#       - Використовується у core/hardening.py, market_data.py.
#       - Pydantic: int, >0.
#     sequence_check_enabled: true
#       - Чи вмикати перевірку послідовності ринкових даних.
#       - Використовується у core/hardening.py, market_data.py.
#       - Pydantic: bool.
#   wal:
#     integrity_check_enabled: true
#       - Чи вмикати перевірку цілісності WAL.
#       - Використовується у core/hardening.py, wal.py.
#       - Pydantic: bool.
#     hash_algorithm: "sha256"
#       - Алгоритм хешування для перевірки WAL.
#       - Використовується у core/hardening.py, wal.py.
#       - Pydantic: str.
# -------- account_observer: --------
#   poll_interval: 5
#     - Інтервал опитування акаунта (секунди).
#     - Визначає, як часто оновлюється інформація про угоди.
#     - Використовується у account_observer.py.
#     - Pydantic: int, >0.
#   symbols: [SOLUSDT, ETHUSDT, DOGEUSDT, XRPUSDT, BTCUSDT]
#     - Список символів для моніторингу.
#     - Використовується у account_observer.py.
#     - Pydantic: list[str].
#   trade_limit: 50
#     - Максимальна кількість угод для отримання по кожному символу.
#     - Використовується у account_observer.py.
#     - Pydantic: int, >0.
#
# -------- position_tracking: --------
#   positions_stale_ttl_sec: 8
#     - TTL для перевірки актуальності портфеля (секунди).
#     - Використовується у bridge/position_tracking.py.
#     - Pydantic: int, >0.
#
# -------- trading: --------
#   symbols_to_track:
#     - Список символів для торгівлі та моніторингу.
#     - Використовується у core/trading.py, market_data.py.
#     - Pydantic: list[str].
#   market_data:
#     websocket_streams:
#       - Список потоків ринкових даних для feature engineering.
#       - "bookTicker" — для OBI (Order Book Imbalance)
#       - "trade" — для TFI (Trade Flow Imbalance) та delta_price
#       - Використовується у core/market_data.py, feature_engineering.py.
#       - Pydantic: list[str].
