# Документація до config/aurora/domains.yaml
# Паспортізація кожного блоку конфігурації (українською)

# -------- decision_making: --------
# 
# Модуль: apps/reference/domains/decision_making/
# Контракти: TradingConfig, DecisionMakingConfig (див. config_models.py)
# 
# 1. position_sizing:
#   min_position_size_usd: 10
#     - Мінімальний розмір позиції у доларах США.
#     - Впливає на фільтрацію сигналів та відкриття позицій: якщо розрахований розмір < цього значення — позиція не відкривається.
#     - Використовується у модулях decision_making, execution_position (через FSM ManageFlowFSM).
#     - Формула: position_size = max(розрахований_розмір, min_position_size_usd)
#     - Фолбек: якщо не задано — використовується дефолт із TradingConfig.
#     - Pydantic: валідується як float/int, перевіряється на позитивність.
#     - Покриття тестами: test_per_instrument_overrides.py, test_aurora_instrument_config.py
#   liquidity_based_cap_usd: 10000
#     - Ліміт максимальної позиції на основі ліквідності (у доларах США).
#     - Обмежує розмір позиції, щоб уникнути надмірного впливу на ринок.
#     - Використовується у decision_making.position_sizing та execution_position для перевірки допустимості заявки.
#     - Формула: position_size = min(розрахований_розмір, liquidity_based_cap_usd)
#     - Фолбек: дефолт із TradingConfig, якщо не задано.
#     - Pydantic: float/int, >0.
#     - Покриття тестами: test_per_instrument_overrides.py
#
# Виклики у коді:
#   - apps/reference/domains/decision_making/decision_making.py: клас DecisionMaker, методи _calculate_position_size, _get_param
#   - apps/reference/domains/execution_position/manage_flow_fsm.py: клас ManageFlowFSM, методи _check_position_size
# Участь у доменах: decision_making, execution_position
#
# Валідація: Pydantic, схеми config_models.py
# Фолбеки: через _get_param() та _safe_config_get()
# Тестування: pytest tests/domains/test_per_instrument_overrides.py

# -------- qos: --------
# 
# Модуль: apps/reference/domains/decision_making/
# Контракти: TradingConfig, DecisionMakingConfig (див. config_models.py)
# 
# 2. qos:
#   exposure_block_cooldown_sec: 10
#     - Час (у секундах) блокування відкриття нової позиції після попередньої спроби (rate-limit для експозиції).
#     - Захищає від надмірної частоти відкриття позицій по одному інструменту.
#     - Використовується у decision_making, execution_position (через FSM).
#     - Фолбек: дефолт із TradingConfig, якщо не задано.
#     - Pydantic: int, >0.
#     - Покриття тестами: test_per_instrument_overrides.py
#   symbol_cooldown_sec: 3
#     - Мінімальний інтервал (секунди) між сигналами/заявками по одному символу.
#     - Запобігає спаму заявок по одному активу.
#     - Використовується у decision_making, FSM ManageFlowFSM.
#     - Фолбек: TradingConfig.
#     - Pydantic: int, >0.
#   max_intents_per_minute_per_symbol: 6
#     - Максимальна кількість торгових намірів (intent) на хвилину по одному символу.
#     - Захист від флуду та помилкових стратегій.
#     - Використовується у decision_making, FSM.
#     - Фолбек: TradingConfig.
#     - Pydantic: int, >0.
#   mode: shadow
#     - Режим роботи QoS: 'shadow' — лише логування, 'allow trading' — дозволяє торгівлю, 'defer broken' — відкладення (немає event loop).
#     - Впливає на поведінку системи при перевищенні лімітів.
#     - Використовується у decision_making, FSM.
#     - Фолбек: TradingConfig.
#     - Pydantic: str, enum.
#   enforce: false
#     - Чи застосовувати обмеження QoS жорстко (true) чи лише логувати (false).
#     - Використовується у decision_making, FSM.
#     - Фолбек: TradingConfig.
#     - Pydantic: bool.
#
# Виклики у коді:
#   - apps/reference/domains/decision_making/decision_making.py: клас DecisionMaker, методи _check_qos, _get_param
#   - apps/reference/domains/execution_position/manage_flow_fsm.py: FSM ManageFlowFSM, перевірка QoS
#
# Участь у доменах: decision_making, execution_position
#
# Валідація: Pydantic, схеми config_models.py
# Фолбеки: через _get_param() та _safe_config_get()
# Тестування: pytest tests/domains/test_per_instrument_overrides.py

# -------- features: --------
# 
# Модуль: apps/reference/domains/feature_engineering/
# Контракти: TradingConfig, FeatureEngineeringConfig (див. config_models.py)
# 
# 3. features:
#   ttl_sec: 30
#     - Time-To-Live (TTL) для фічей у секундах: максимальний вік даних, які вважаються актуальними для прийняття рішень.
#     - Якщо фічі старші за ttl_sec — сигнал не генерується, торгівля блокується.
#     - Використовується у feature_engineering, decision_making (через перевірку свіжості даних).
#     - Фолбек: TradingConfig, якщо не задано.
#     - Pydantic: int, >0.
#     - Покриття тестами: test_per_instrument_overrides.py
#
# Виклики у коді:
#   - apps/reference/domains/feature_engineering/feature_engineering.py: перевірка свіжості фічей
#   - apps/reference/domains/decision_making/decision_making.py: _check_features_freshness
#
# Участь у доменах: feature_engineering, decision_making
#
# Валідація: Pydantic, схеми config_models.py
# Фолбеки: через _get_param() та _safe_config_get()
# Тестування: pytest tests/domains/test_per_instrument_overrides.py

# -------- bar_gating: --------
# 
# Модуль: apps/reference/domains/decision_making/
# Контракти: TradingConfig, DecisionMakingConfig (див. config_models.py)
# 
# 4. bar_gating:
#   enable: false
#     - Вмикає/вимикає режим барового гейтингу (бар'єр по часу для генерації сигналів).
#     - Якщо true — сигнали генеруються лише на початку нового бару (наприклад, кожні 15 хвилин).
#     - Використовується для синхронізації з таймфреймами та зменшення шуму.
#     - Використовується у decision_making, feature_engineering.
#     - Фолбек: TradingConfig.
#     - Pydantic: bool.
#   bar_ms: 900000
#     - Довжина бару у мілісекундах (900000 мс = 15 хвилин).
#     - Визначає частоту генерації сигналів при bar_gating.enable=true.
#     - Використовується у decision_making, feature_engineering.
#     - Фолбек: TradingConfig.
#     - Pydantic: int, >0.
#
# Виклики у коді:
#   - apps/reference/domains/decision_making/decision_making.py: _should_gate_on_bar, _get_param
#   - apps/reference/domains/feature_engineering/feature_engineering.py: bar_gating logic
#
# Участь у доменах: decision_making, feature_engineering
#
# Валідація: Pydantic, схеми config_models.py
# Фолбеки: через _get_param() та _safe_config_get()
# Тестування: pytest tests/domains/test_per_instrument_overrides.py

# -------- behavior_fsm: --------
# 
# Модуль: apps/reference/domains/decision_making/
# Контракти: TradingConfig, DecisionMakingConfig (див. config_models.py)
# 
# 5. behavior_fsm:
#   enable: false
#     - Вмикає/вимикає FSM (автомат кінцевих станів) для поведінкових режимів.
#     - Якщо true — активується додаткова логіка зміни режимів залежно від волатильності.
#     - Використовується для адаптації стратегії до ринку.
#     - Використовується у decision_making, FSM.
#     - Фолбек: TradingConfig.
#     - Pydantic: bool.
#   high_vol_multiplier: 2.0
#     - Множник для розрахунків у режимі високої волатильності.
#     - Збільшує/зменшує розмір позиції, ризик чи інші параметри при high volatility.
#     - Використовується у decision_making, FSM.
#     - Фолбек: TradingConfig.
#     - Pydantic: float, >0.
#   low_vol_multiplier: 0.5
#     - Множник для режиму низької волатильності.
#     - Зменшує ризик/позицію при low volatility.
#     - Використовується у decision_making, FSM.
#     - Фолбек: TradingConfig.
#     - Pydantic: float, >0.
#
# Виклики у коді:
#   - apps/reference/domains/decision_making/decision_making.py: _apply_behavior_fsm, _get_param
#   - FSM ManageFlowFSM: адаптація режиму
#
# Участь у доменах: decision_making
#
# Валідація: Pydantic, схеми config_models.py
# Фолбеки: через _get_param() та _safe_config_get()
# Тестування: pytest tests/domains/test_per_instrument_overrides.py

# -------- signals: --------
# 
# Модуль: apps/reference/domains/decision_making/
# Контракти: TradingConfig, DecisionMakingConfig (див. config_models.py)
# 
# 6. signals:
#   normalize: false
#     - Чи нормалізувати значення сигналів перед прийняттям рішення.
#     - Якщо true — всі сигнали приводяться до єдиного масштабу (наприклад, [0,1] або [-1,1]).
#     - Використовується для уніфікації впливу різних індикаторів.
#     - Використовується у decision_making, feature_engineering.
#     - Фолбек: TradingConfig.
#     - Pydantic: bool.
#
# Виклики у коді:
#   - apps/reference/domains/decision_making/decision_making.py: _normalize_signals, _get_param
#   - apps/reference/domains/feature_engineering/feature_engineering.py: нормалізація фічей
#
# Участь у доменах: decision_making, feature_engineering
#
# Валідація: Pydantic, схеми config_models.py
# Фолбеки: через _get_param() та _safe_config_get()
# Тестування: pytest tests/domains/test_per_instrument_overrides.py

# -------- risk_skew: --------
# 
# Модуль: apps/reference/domains/decision_making/
# Контракти: TradingConfig, DecisionMakingConfig (див. config_models.py)
# 
# 7. risk_skew:
#   max_skew_sec: 5
#     - Максимально допустима різниця (секунди) між часовими мітками features.ts та risk.ts.
#     - Якщо різниця перевищує — сигнал не генерується, торгівля блокується.
#     - Використовується для захисту від розсинхронізації даних.
#     - Використовується у decision_making, FSM.
#     - Фолбек: TradingConfig.
#     - Pydantic: int, >0.
#   max_defer_count: 3
#     - Максимальна кількість відкладень (DEFER) по символу до переходу у NO_TRADE_UNTIL_REFRESH.
#     - Захищає від нескінченних спроб при розсинхронізації.
#     - Використовується у decision_making, FSM.
#     - Фолбек: TradingConfig.
#     - Pydantic: int, >0.
#   defer_cooldown_sec: 2
#     - Час (секунди) між повторними спробами після DEFER.
#     - Використовується у decision_making, FSM.
#     - Фолбек: TradingConfig.
#     - Pydantic: int, >0.
#
# Виклики у коді:
#   - apps/reference/domains/decision_making/decision_making.py: _check_risk_skew, _get_param
#   - FSM ManageFlowFSM: логіка DEFER/NO_TRADE
#
# Участь у доменах: decision_making
#
# Валідація: Pydantic, схеми config_models.py
# Фолбеки: через _get_param() та _safe_config_get()
# Тестування: pytest tests/domains/test_per_instrument_overrides.py

# -------- Наступний блок додається нижче за аналогією --------
# -------- feature_engineering: --------
# 
# Модуль: apps/reference/domains/feature_engineering/
# Контракти: TradingConfig, FeatureEngineeringConfig (див. config_models.py)
# 
# 8. feature_engineering:
#   enable_new_metrics: true
#     - Вмикає нові метрики для розрахунку фічей (EMA, volume spike, тощо).
#     - Якщо true — використовуються розширені фічі для генерації сигналів.
#     - Використовується у feature_engineering.
#     - Фолбек: TradingConfig.
#     - Pydantic: bool.
#
#   ema:
#     period_short: 3
#       - Період короткої експоненційної ковзної середньої (EMA).
#       - Використовується для розрахунку короткострокового тренду.
#       - Використовується у feature_engineering, індикатор EMA.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#     period_long: 7
#       - Період довгої EMA для розрахунку довгострокового тренду.
#       - Використовується у feature_engineering, індикатор EMA.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#
#   volume:
#     sma_length: 5
#       - Довжина SMA для обсягу (volume).
#       - Використовується для згладжування обсягу торгів.
#       - Використовується у feature_engineering.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#     window_sec: 60
#       - Вікно (секунди) для розрахунку обсягу.
#       - Використовується у feature_engineering.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#     min_window_volume_usd: 1000.0
#       - Мінімальний обсяг у доларах для активації volume_spike (якщо менше — spike=0.5).
#       - Захист від шуму на низьколіквідних активах.
#       - Використовується у feature_engineering.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, >0.
#
#   volatility:
#     sma_length: 10
#       - Довжина SMA для волатильності.
#       - Використовується у feature_engineering.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#     window_sec: 60
#       - Вікно (секунди) для розрахунку волатильності.
#       - Використовується у feature_engineering.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#
#   liquidity:
#     depth_half: 1000
#       - Глибина стакану для розрахунку ліквідності (USD).
#       - Використовується у feature_engineering.
#       - Фолбек: TradingConfig.
#       - Pydantic: int/float, >0.
#     kappa_min: 0.3
#       - Мінімальний коефіцієнт ліквідності.
#       - Використовується у feature_engineering.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, >0.
#     kappa_max: 1.0
#       - Максимальний коефіцієнт ліквідності.
#       - Використовується у feature_engineering.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, >0.
#
#   ema_bias:
#     clamp_min: -0.02
#       - Мінімальне значення для bias EMA (обмеження).
#       - Використовується у feature_engineering.
#       - Фолбек: TradingConfig.
#       - Pydantic: float.
#     clamp_max: 0.02
#       - Максимальне значення для bias EMA (обмеження).
#       - Використовується у feature_engineering.
#       - Фолбек: TradingConfig.
#       - Pydantic: float.
#
#   volume_spike:
#     cap_max: 3.0
#       - Максимальне значення для volume_spike (захист від аномалій).
#       - Використовується у feature_engineering.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, >0.
#
#   delta_price:
#     spike_filter_ms: 60000
#       - Фільтр для аномальних змін ціни (мс).
#       - Використовується у feature_engineering.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#
#   macro_sync:
#     time_diff_threshold_ms: 60000
#       - Максимальна різниця часу між синхронізованими активами (мс).
#       - Використовується у feature_engineering.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#     min_buffer_size: 3
#       - Мінімальний розмір буфера для синхронізації.
#       - Використовується у feature_engineering.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#     window: 60
#       - Вікно (секунди) для синхронізації.
#       - Використовується у feature_engineering.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#     anchors: ["BTCUSDT", "ETHUSDT"]
#       - Якірні символи для синхронізації макро-фічей.
#       - Використовується у feature_engineering.
#       - Фолбек: TradingConfig.
#       - Pydantic: list[str].
#
# Виклики у коді:
#   - apps/reference/domains/feature_engineering/feature_engineering.py: всі методи розрахунку фічей
#
# Участь у доменах: feature_engineering, decision_making
#
# Валідація: Pydantic, схеми config_models.py
# Фолбеки: через _get_param() та _safe_config_get()
# Тестування: pytest tests/domains/test_per_instrument_overrides.py, test_aurora_instrument_config.py

# -------- risk_management: --------
# 
# Модуль: apps/reference/domains/decision_making/, apps/reference/domains/execution_position/
# Контракти: TradingConfig, RiskManagementConfig (див. config_models.py)
# 
# 9. risk_management:
#   use_absorption_penalty: false
#     - Чи застосовувати штраф за поглинання ліквідності (absorption penalty) при розрахунку ризику.
#     - Якщо true — ризикова оцінка враховує додатковий штраф за агресивний вплив на стакан.
#     - Використовується у risk_management, decision_making.
#     - Фолбек: TradingConfig.
#     - Pydantic: bool.
#
#   risk_score_weights:
#     delta_price_pct: 0.1
#       - Вага зміни ціни у загальній ризиковій оцінці.
#       - Використовується у risk_management, decision_making.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, [0,1].
#     obi: 0.3
#       - Вага Order Book Imbalance (OBI) у ризиковій оцінці.
#       - Використовується у risk_management, decision_making.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, [0,1].
#     tfi: 0.3
#       - Вага Trade Flow Imbalance (TFI) у ризиковій оцінці.
#       - Використовується у risk_management, decision_making.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, [0,1].
#     absorption_inverse: 0.3
#       - Вага інверсного absorption у ризиковій оцінці.
#       - Використовується у risk_management, decision_making.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, [0,1].
#
#   trading_allowed_thresholds:
#     max_risk_score: 0.96
#       - Максимально допустимий ризиковий скор для дозволу торгівлі.
#       - Якщо risk_score > max_risk_score — торгівля блокується.
#       - Використовується у risk_management, decision_making.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, [0,1].
#
#   validation:
#     total_weight_min: 0.5
#       - Мінімальна сума ваг для ризикової моделі (перевірка коректності).
#       - Використовується у risk_management, decision_making.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, >0.
#     total_weight_max: 2.0
#       - Максимальна сума ваг для ризикової моделі.
#       - Використовується у risk_management, decision_making.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, >0.
#
# Виклики у коді:
#   - apps/reference/domains/decision_making/decision_making.py: _calculate_risk_score, _get_param
#   - apps/reference/domains/decision_making/risk_management.py: розрахунок ризику
#
# Участь у доменах: risk_management, decision_making
#
# Валідація: Pydantic, схеми config_models.py
# Фолбеки: через _get_param() та _safe_config_get()
# Тестування: pytest tests/domains/test_per_instrument_overrides.py, test_aurora_instrument_config.py

# -------- position_tracking: --------
# 
# Модуль: apps/reference/domains/execution_position/
# Контракти: TradingConfig, PositionTrackingConfig (див. config_models.py)
# 
# 10. position_tracking:
#   precision:
#     quantity_min_threshold: 1e-9
#       - Мінімальний поріг для кількості позиції (менше — вважається нульовою).
#       - Використовується для уникнення помилок округлення.
#       - Використовується у execution_position, position_tracking.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, >0.
#     flat_position_threshold: 1e-12
#       - Поріг для визначення "плоскої" (flat) позиції.
#       - Використовується у execution_position, position_tracking.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, >0.
#     decimal_places: 2
#       - Кількість знаків після коми для позицій.
#       - Використовується у execution_position, position_tracking.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#   positions_stale_ttl_sec: 15
#     - TTL для актуальності портфеля (секунди).
#     - Якщо дані старші — портфель вважається неактуальним.
#     - Використовується у execution_position, position_tracking.
#     - Фолбек: TradingConfig.
#     - Pydantic: int, >0.
#   thread_timeouts:
#     join_timeout_sec: 10
#       - Таймаут для завершення потоків (секунди).
#       - Використовується у execution_position, position_tracking.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#
# Виклики у коді:
#   - apps/reference/domains/execution_position/position_tracking.py: всі методи роботи з позиціями
#
# Участь у доменах: execution_position, position_tracking
#
# Валідація: Pydantic, схеми config_models.py
# Фолбеки: через _get_param() та _safe_config_get()
# Тестування: pytest tests/domains/test_per_instrument_overrides.py, test_aurora_instrument_config.py

# -------- account_observer: --------
# 
# Модуль: apps/reference/domains/execution_position/
# Контракти: TradingConfig, AccountObserverConfig (див. config_models.py)
# 
# 11. account_observer:
#   poll_interval_sec: 5
#     - Інтервал опитування акаунта (секунди).
#     - Визначає, як часто оновлюється інформація про баланс, позиції, ордери.
#     - Використовується у execution_position, account_observer.
#     - Фолбек: TradingConfig.
#     - Pydantic: int, >0.
#   trade_limit: 10
#     - Максимальна кількість одночасних угод (trade) для акаунта.
#     - Використовується для обмеження ризику.
#     - Використовується у execution_position, account_observer.
#     - Фолбек: TradingConfig.
#     - Pydantic: int, >0.
#   symbols: []
#     - Список символів для моніторингу (порожній — використовуються trading.symbols_to_track).
#     - Використовується у execution_position, account_observer.
#     - Фолбек: TradingConfig.
#     - Pydantic: list[str].
#   thread_timeouts:
#     join_timeout_sec: 10
#       - Таймаут для завершення потоків (секунди).
#       - Використовується у execution_position, account_observer.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#
# Виклики у коді:
#   - apps/reference/domains/execution_position/account_observer.py: всі методи моніторингу акаунта
#
# Участь у доменах: execution_position, account_observer
#
# Валідація: Pydantic, схеми config_models.py
# Фолбеки: через _get_param() та _safe_config_get()
# Тестування: pytest tests/domains/test_per_instrument_overrides.py, test_aurora_instrument_config.py

# -------- execution_position: --------
# 
# Модуль: apps/reference/domains/execution_position/
# Контракти: TradingConfig, ExecutionPositionConfig (див. config_models.py)
# 
# 12. execution_position:
#   watchdog:
#     ack_ttl_ms: 8000
#       - TTL для підтвердження заявки (мс).
#       - Якщо не підтверджено за ack_ttl_ms — заявка вважається втраченою.
#       - Використовується у execution_position, watchdog.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#     fill_ttl_ms: 30000
#       - TTL для очікування виконання заявки (мс).
#       - Якщо не виконано за fill_ttl_ms — заявка вважається втраченою.
#       - Використовується у execution_position, watchdog.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#     check_interval_ms: 1000
#       - Інтервал перевірки статусу заявки (мс).
#       - Використовується у execution_position, watchdog.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#     rps_limit: 10
#       - Ліміт RPS (requests per second) для заявок.
#       - Використовується у execution_position, watchdog.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#
#   exposure_guard:
#     pending_ttl_sec: 90
#       - TTL для очікування виконання заявки (секунди).
#       - Використовується у execution_position, exposure_guard.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#     post_fill_ttl_sec: 5
#       - TTL після виконання заявки (секунди).
#       - Використовується у execution_position, exposure_guard.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#     stale_ttl_sec: 60
#       - TTL для визнання заявки застарілою (секунди).
#       - Використовується у execution_position, exposure_guard.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#     pending_timeout_sec: 5
#       - Таймаут очікування заявки (секунди).
#       - Використовується у execution_position, exposure_guard.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#     max_equity_utilization_pct: 0.95
#       - Максимальна частка використання equity для однієї позиції.
#       - Використовується у execution_position, exposure_guard.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, [0,1].
#     max_portfolio_fraction: 0.95
#       - Максимальна частка портфеля для однієї позиції.
#       - Використовується у execution_position, exposure_guard.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, [0,1].
#     max_long_utilization_pct: 0.95
#       - Максимальна частка лонг-позицій.
#       - Використовується у execution_position, exposure_guard.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, [0,1].
#     max_short_utilization_pct: 0.95
#       - Максимальна частка шорт-позицій.
#       - Використовується у execution_position, exposure_guard.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, [0,1].
#     max_directional_ratio: 20.0
#       - Максимальне співвідношення long/short.
#       - Використовується у execution_position, exposure_guard.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, >0.
#     max_concentration_pct: 0.10
#       - Максимальна концентрація на одному активі.
#       - Використовується у execution_position, exposure_guard.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, [0,1].
#
#   fsm_open:
#     idempotency_window_sec: 60
#       - Вікно ідемпотентності для відкриття FSM (секунди).
#       - Використовується у execution_position, FSM.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#
#   order_index:
#     ttl_sec: 3600
#       - TTL для order index (секунди).
#       - Використовується у execution_position, order_index.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#
#   metrics_collector:
#     window_size_minutes: 60
#       - Вікно для збору метрик (хвилини).
#       - Використовується у execution_position, metrics_collector.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#     recent_rejections_minutes: 5
#       - Вікно для підрахунку відхилених заявок (хвилини).
#       - Використовується у execution_position, metrics_collector.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#
#   idempotent_cancel:
#     max_retries: 2
#       - Максимальна кількість повторних спроб для ідемпотентного скасування.
#       - Використовується у execution_position, idempotent_cancel.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#
#   utils:
#     client_order_id_max_length: 32
#       - Максимальна довжина client_order_id.
#       - Використовується у execution_position, utils.
#       - Фолбек: TradingConfig.
#       - Pydantic: int, >0.
#     basis_points_base: 10000.0
#       - Базове значення для розрахунку basis points (bps).
#       - Використовується у execution_position, utils.
#       - Фолбек: TradingConfig.
#       - Pydantic: float, >0.
#
# Виклики у коді:
#   - apps/reference/domains/execution_position/manage_flow_fsm.py: всі методи FSM, order, exposure, utils
#
# Участь у доменах: execution_position
#
# Валідація: Pydantic, схеми config_models.py
# Фолбеки: через _get_param() та _safe_config_get()
# Тестування: pytest tests/domains/test_per_instrument_overrides.py, test_aurora_instrument_config.py
