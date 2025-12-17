# Документація до config/aurora/features.yaml
# Паспортізація кожного блоку конфігурації (українською)

# -------- feature_engineering: --------
# 
# Модуль: apps/reference/domains/feature_engineering/
# Контракти: FeatureEngineeringConfig, TradingConfig (див. config_models.py)
#
# 1. enable_new_metrics: true
#   - Головний перемикач для метрик фази 1 (EMA bias, volume_spike, volatility_state, depth_imbalance, macro_sync).
#   - Якщо false — обчислюються лише базові фічі (OBI, TFI, delta_price).
#   - Впливає на обсяг розрахунків та складність сигналів.
#   - Використовується у feature_engineering.py, decision_making.py.
#   - Фолбек: TradingConfig.
#   - Pydantic: bool.
#   - Тестування: test_per_instrument_overrides.py, test_aurora_instrument_config.py
#
# -------- ema: --------
#   period_short: 3
#     - Період короткої EMA для розрахунку ema_bias.
#     - Формула: ema_bias = (EMA_short - EMA_long) / EMA_long
#     - Використовується у feature_engineering.py (EMA розрахунок).
#     - Pydantic: int, >0, < period_long.
#   period_long: 7
#     - Період довгої EMA для розрахунку ema_bias.
#     - Використовується у feature_engineering.py.
#     - Pydantic: int, > period_short.
#
# -------- ema_bias: --------
#   clamp_min: -0.02
#     - Мінімальне значення для сирого bias EMA (обмеження).
#     - Значення < clamp_min приводиться до clamp_min.
#     - Після clamp — лінійно нормалізується у [0,1]: 0.0 = повний bearish, 1.0 = повний bullish.
#     - Використовується у feature_engineering.py (нормалізація ema_bias).
#     - Pydantic: float.
#   clamp_max: 0.02
#     - Максимальне значення для bias EMA (обмеження).
#     - Значення > clamp_max приводиться до clamp_max.
#     - Використовується у feature_engineering.py.
#     - Pydantic: float.
#
# -------- volume: --------
#   window_sec: 60
#     - Вікно агрегації обсягу (секунди).
#     - Використовується для розрахунку поточного обсягу у volume_spike.
#     - Використовується у feature_engineering.py.
#     - Pydantic: int, 1-3600.
#   sma_length: 5
#     - Кількість періодів SMA для baseline обсягу.
#     - Використовується у feature_engineering.py.
#     - Pydantic: int, 2-100.
#
# -------- volume_spike: --------
#   cap_max: 3.0
#     - Максимальне значення для spike ratio (обмеження аномалій).
#     - Значення > cap_max приводиться до cap_max.
#     - Після cap — нормалізується у [0,1].
#     - Використовується у feature_engineering.py (volume_spike).
#     - Pydantic: float, >0.
#
# -------- volatility: --------
#   window_sec: 60
#     - Вікно для розрахунку діапазону цін (секунди).
#     - Використовується у feature_engineering.py (volatility_state).
#     - Pydantic: int, 1-3600.
#   sma_length: 10
#     - Кількість періодів SMA для baseline волатильності.
#     - Використовується у feature_engineering.py.
#     - Pydantic: int, 2-100.
#
# -------- volatility_state: --------
#   cap_max: 3.0
#     - Максимальне значення для volatility ratio (обмеження аномалій).
#     - Значення > cap_max приводиться до cap_max.
#     - Після cap — нормалізується у [0,1].
#     - Використовується у feature_engineering.py (volatility_state).
#     - Pydantic: float, >0.
#
# -------- liquidity: --------
#   depth_half: 1000.0
#     - Параметр згладжування для розрахунку ліквідності (USD або контракти).
#     - Використовується у формулі: kappa = depth / (depth + depth_half)
#     - Чим більше depth_half — тим менш чутлива метрика до змін глибини.
#     - Використовується у feature_engineering.py (liquidity_kappa, depth_imbalance).
#     - Pydantic: float, >0.
#   kappa_min: 0.3
#     - Мінімальне значення kappa (навіть для низької ліквідності).
#     - Використовується у feature_engineering.py.
#     - Pydantic: float, >0.
#   kappa_max: 1.0
#     - Максимальне значення kappa.
#     - Використовується у feature_engineering.py.
#     - Pydantic: float, >0.
#
# -------- depth_imbalance: --------
#   use_laplace_smoothing: true
#     - Чи використовувати depth_half для згладжування співвідношення глибини (Laplace smoothing).
#     - Формула: ratio = (asks + depth_half) / (bids + depth_half)
#     - Використовується у feature_engineering.py (depth_imbalance).
#     - Pydantic: bool.
#
# -------- delta_price: --------
#   spike_filter_ms: 5000
#     - Фільтр для аномальних змін ціни (мс).
#     - Якщо time gap > spike_filter_ms — delta_price = 0 (захист від артефактів reconnection).
#     - Використовується у feature_engineering.py (delta_price).
#     - Pydantic: int, >0.
#
# -------- macro_sync: --------
#   enabled: true
#     - Вмикає розрахунок кореляції з anchor-активами (BTCUSDT, ETHUSDT).
#     - Якщо false — macro_sync не розраховується.
#     - Використовується у feature_engineering.py (macro_sync).
#     - Pydantic: bool.
#   anchors: ["BTCUSDT", "ETHUSDT"]
#     - Список anchor-активів для кореляції.
#     - Використовується у feature_engineering.py.
#     - Pydantic: list[str].
#   window: 60
#     - Розмір rolling window для returns (секунди).
#     - Використовується у feature_engineering.py.
#     - Pydantic: int, >0.
#   min_buffer_size: 3
#     - Мінімальна кількість зразків для розрахунку кореляції.
#     - Використовується у feature_engineering.py.
#     - Pydantic: int, >0.
#   time_diff_threshold_ms: 5000
#     - Максимальний розрив часу для returns (мс).
#     - Використовується у feature_engineering.py.
#     - Pydantic: int, >0.
#
# -------- defaults: --------
#   neutral_value: 0.5
#     - Значення "нейтраль" для всіх фічей (центр діапазону [0,1]).
#     - Використовується у feature_engineering.py (edge cases, insufficient data).
#     - Pydantic: float, [0,1].
#   zero_value: 0.0
#     - Значення для відсутніх фічей (наприклад, absorption placeholder).
#     - Використовується у feature_engineering.py.
#     - Pydantic: float, [0,1].
#   correlation_default: 0.0
#     - Значення за замовчуванням для кореляції, якщо немає даних.
#     - Використовується у feature_engineering.py.
#     - Pydantic: float, [-1,1] (але нормалізується до [0,1]).
#   ms_per_sec: 1000
#     - Константа для конвертації секунд у мілісекунди.
#     - Використовується у feature_engineering.py.
#     - Pydantic: int, >0.
#
# -------- futures: --------
#   enabled: true
#     - Вмикає розрахунок фічей для ф'ючерсів (funding rate, open interest).
#     - Потрібні події EVT:FUNDING_UPDATE та EVT:OI_UPDATE від провайдера даних.
#     - Використовується у feature_engineering.py (futures features).
#     - Pydantic: bool.
#
#   funding:
#     extreme_threshold: 0.001
#       - Поріг для "екстремальних" значень funding rate (0.1%).
#       - Використовується для нормалізації funding до [-1,1] (приклади у коментарях).
#       - funding > threshold → normalized = 1.0 (clamped), < -threshold → -1.0.
#       - Використовується у feature_engineering.py (futures features).
#       - Pydantic: float, >0.
#
# Виклики у коді:
#   - apps/reference/domains/feature_engineering/feature_engineering.py: методи для futures features
#
# Участь у доменах: feature_engineering
#
# Валідація: Pydantic, схеми config_models.py
# Фолбеки: через _get_param() та _safe_config_get()
# Тестування: pytest tests/domains/test_per_instrument_overrides.py, test_aurora_instrument_config.py
