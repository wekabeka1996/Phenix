# Документація до config/aurora/regime.yaml
# Паспортізація кожного блоку конфігурації (українською)

# -------- config_version: --------
#   - Версія формату конфігурації.
#   - Дозволяє системі перевіряти сумісність при завантаженні.
#   - Використовується у всіх модулях, що працюють із regime.yaml.
#   - Pydantic: str, формат x.y.z

# -------- hmm: --------
#   enabled: true
#     - Вмикає/вимикає Hidden Markov Model (HMM) для режимної класифікації ринку.
#     - Якщо false — HMM не використовується для визначення режиму.
#     - Використовується у regime_detector.py, regime_manager.py.
#     - Pydantic: bool.
#   K: 3
#     - Кількість прихованих станів HMM (>=2).
#     - Визначає складність режимної моделі.
#     - Використовується у regime_detector.py.
#     - Pydantic: int, >=2.
#   emission.cov_kind: diag
#     - Тип коваріації для емісійної моделі: diag (діагональна) або full (повна).
#     - Впливає на точність і швидкість EM-алгоритму.
#     - Використовується у regime_detector.py.
#     - Pydantic: str, enum.
#   sticky_kappa: 0.15
#     - Коефіцієнт "прилипання" (self-transition bias) — ймовірність залишитись у поточному стані.
#     - 0 = без пріоритету, >0 = більше інерції.
#     - Використовується у regime_detector.py.
#     - Pydantic: float, [0,1].
#   update_interval: 250
#     - Каденція оновлення EM-алгоритму (кількість спостережень).
#     - Визначає, як часто HMM перенавчається онлайн.
#     - Використовується у regime_detector.py.
#     - Pydantic: int, >0.
#   history_hours: 48
#     - Глибина історії для офлайн-навчання (години).
#     - Використовується у regime_detector.py.
#     - Pydantic: int, >0.
#   confidence_threshold: 0.75
#     - Поріг впевненості для прийняття режиму.
#     - Якщо ймовірність < threshold — режим вважається невизначеним.
#     - Використовується у regime_detector.py.
#     - Pydantic: float, [0,1].
#
# -------- features: --------
#   rv_window: 120
#     - Кількість вибірок для розрахунку реалізованої волатильності (realized volatility).
#     - Використовується у regime_detector.py, regime_features.py.
#     - Pydantic: int, >0.
#   trend_window: 180
#     - Кількість вибірок для регресії тренду (trend slope).
#     - Використовується у regime_detector.py, regime_features.py.
#     - Pydantic: int, >0.
#   obi_window: 60
#     - Кількість вибірок для згладжування order book imbalance.
#     - Використовується у regime_detector.py, regime_features.py.
#     - Pydantic: int, >0.
#   spread_min_ticks: 1
#     - Мінімальний спред у тиках для нормалізації (safeguard).
#     - Використовується у regime_detector.py, regime_features.py.
#     - Pydantic: int, >0.
#   micro_return_window: 1
#     - Вікно для розрахунку мікро-доходності (micro return).
#     - Використовується у regime_detector.py, regime_features.py.
#     - Pydantic: int, >0.
#
# -------- hotreload_whitelist: --------
#   - Список параметрів, які можна змінювати "на льоту" без перезапуску системи.
#   - Дозволяє оперативно підлаштовувати чутливість HMM та інші ключові параметри.
#   - Використовується у regime_manager.py, config hotreload logic.
#   - Pydantic: list[str].
#
# -------- models: --------
#   sma_trend:
#     sma_short_period: 10
#       - Період короткої SMA для трендового режиму.
#       - Використовується у regime_models.py, regime_detector.py.
#       - Pydantic: int, >0.
#     sma_long_period: 50
#       - Період довгої SMA для трендового режиму.
#       - Використовується у regime_models.py, regime_detector.py.
#       - Pydantic: int, > sma_short_period.
#     confidence_multiplier: 20.0
#       - Множник для підсилення впевненості у трендовому режимі.
#       - Використовується у regime_models.py.
#       - Pydantic: float, >0.
#     confidence_min: 0.5
#       - Мінімальна впевненість для сигналу тренду.
#       - Використовується у regime_models.py.
#       - Pydantic: float, [0,1].
#     confidence_max: 0.95
#       - Максимальна впевненість для сигналу тренду.
#       - Використовується у regime_models.py.
#       - Pydantic: float, [0,1].
#   volatility:
#     enabled: true
#       - Вмикає/вимикає режим волатильності.
#       - Використовується у regime_models.py, regime_detector.py.
#       - Pydantic: bool.
#     atr_period: 14
#       - Період ATR для розрахунку волатильності.
#       - Використовується у regime_models.py.
#       - Pydantic: int, >0.
#     atr_sma_length: 100
#       - Довжина SMA для ATR.
#       - Використовується у regime_models.py.
#       - Pydantic: int, >0.
#     threshold_multiplier: 2.0
#       - Множник для порогу волатильності.
#       - Використовується у regime_models.py.
#       - Pydantic: float, >0.
#     low_vol_multiplier: 0.5
#       - Множник для режиму низької волатильності.
#       - Використовується у regime_models.py.
#       - Pydantic: float, >0.
#     high_vol_confidence_multiplier: 2.0
#       - Множник впевненості для високої волатильності.
#       - Використовується у regime_models.py.
#       - Pydantic: float, >0.
#     low_vol_confidence_multiplier: 3.0
#       - Множник впевненості для низької волатильності.
#       - Використовується у regime_models.py.
#       - Pydantic: float, >0.
#   mean_reversion:
#     threshold: 0.005
#       - Поріг для визначення mean reversion режиму.
#       - Використовується у regime_models.py.
#       - Pydantic: float, >0.
#     confidence_multiplier: 100.0
#       - Множник впевненості для mean reversion.
#       - Використовується у regime_models.py.
#       - Pydantic: float, >0.
#
# ...existing code...
