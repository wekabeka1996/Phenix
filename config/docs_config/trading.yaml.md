# Документація до config/aurora/trading.yaml
# Паспортізація кожного блоку конфігурації (українською)

# -------- binance_api: --------
#   live:
#     api_key, api_secret, rest_url, ws_url
#       - Креденшали та URL для підключення до Binance Futures LIVE.
#       - Значення підтягуються з .env через шаблони ${VAR_NAME}.
#       - Використовується у binance_adapter.py, core/binance_api.py.
#       - Pydantic: str.
#   testnet:
#     api_key, api_secret, rest_url, ws_url
#       - Креденшали та URL для підключення до Binance Futures TESTNET.
#       - Використовується для тестування без ризику.
#       - Pydantic: str.
#   feature_engineering:
#     liquidity.depth_half
#       - Параметр для розрахунку ліквідності (kappa) на рівні venue.
#       - Використовується у feature_engineering.py.
#       - Pydantic: int/float, >0.
#
# -------- trading: --------
#   mode: "testnet"
#     - Операційний режим: "live", "testnet", "hybrid".
#     - Визначає, які ключі API та потоки даних використовуються.
#     - Використовується у core/main.py, binance_adapter.py.
#     - Pydantic: str, enum.
#
# -------- trading.decision: --------
#   signal_threshold: 0.10
#     - Поріг для генерації торгового сигналу (мінімальна сила).
#     - Використовується у decision_making.py.
#     - Pydantic: float, [0,1].
#   neutral_threshold: 0.18
#     - Поріг для нейтрального сигналу (нижче — не торгуємо).
#     - Використовується у decision_making.py.
#     - Pydantic: float, [0,1].
#   symbols_to_track:
#     - Список символів для прийняття рішень.
#     - Використовується у decision_making.py.
#     - Pydantic: list[str].
#   behavior_fsm:
#     enable: false
#       - Вмикає FSM для поведінкових режимів.
#       - Використовується у decision_making.py.
#       - Pydantic: bool.
#     high_vol_multiplier: 2.0
#       - Множник для high volatility режиму.
#       - Використовується у decision_making.py.
#       - Pydantic: float, >0.
#     low_vol_multiplier: 0.5
#       - Множник для low volatility режиму.
#       - Використовується у decision_making.py.
#       - Pydantic: float, >0.
#   regime_threshold_multipliers:
#     - Множники для порогів сигналу залежно від режиму ринку.
#     - Використовується у decision_making.py.
#     - Pydantic: dict[str, float].
#   side_bias_window_sec: 60
#     - Вікно для підрахунку співвідношення BUY/SELL.
#     - Використовується у decision_making.py.
#     - Pydantic: int, >0.
#   side_bias_target_ratio: 0.60
#     - Цільове співвідношення SELL (максимум 60%).
#     - Використовується у decision_making.py.
#     - Pydantic: float, [0,1].
#   side_bias_penalty_factor: 0.50
#     - Множник штрафу при перевищенні цільового співвідношення.
#     - Використовується у decision_making.py.
#     - Pydantic: float, [0,1].
#   cooldown_sec: 10
#     - Затримка між рішеннями (секунди).
#     - Використовується у decision_making.py.
#     - Pydantic: int, >0.
#   position_sizing:
#     min_position_size_usd: 10
#       - Мінімальний розмір позиції (USD).
#       - Використовується у decision_making.py.
#       - Pydantic: float, >0.
#     liquidity_based_cap_usd: 10000
#       - Максимальний розмір позиції (USD).
#       - Використовується у decision_making.py.
#       - Pydantic: float, >0.
#     risk_fraction_q: 0.05
#       - Частка ризику на одну угоду.
#       - Використовується у decision_making.py.
#       - Pydantic: float, (0,1].
#     liquidity_kappa: 1.0
#       - Коефіцієнт ліквідності для sizing.
#       - Використовується у decision_making.py.
#       - Pydantic: float, (0,1].
#     liquidity_kappa_mode: dynamic
#       - Режим розрахунку kappa: "static" або "dynamic".
#       - Використовується у decision_making.py.
#       - Pydantic: str, enum.
#     risk_contract_v1:
#       enabled: false
#         - Вмикає контрактну модель ризику (етап 1).
#         - Використовується у decision_making.py.
#         - Pydantic: bool.
#       effective_leverage: 10.0
#         - Ефективне плече для розрахунку notional.
#         - Використовується у decision_making.py.
#         - Pydantic: float, >0.
#       per_symbol_margin_fraction:
#         - Частка маржі для кожного інструменту.
#         - Використовується у decision_making.py.
#         - Pydantic: dict[str, float].
#       fixed_notional_usd:
#         - Фіксований розмір позиції для кожного інструменту.
#         - Використовується у decision_making.py.
#         - Pydantic: dict[str, float].
#       sol_regime_multipliers:
#         - Множники для SOL залежно від режиму.
#         - Використовується у decision_making.py.
#         - Pydantic: dict[str, float].
#   sizing_modifiers:
#     - Множники для розміру позиції залежно від режиму.
#     - Використовується у decision_making.py.
#     - Pydantic: dict[str, float].
#   kelly:
#     base_probability: 0.50
#       - Базова ймовірність для формули Келлі.
#       - Використовується у decision_making.py.
#       - Pydantic: float, [0,1].
#     kelly_cap: 0.25
#       - Максимальна частка Келлі.
#       - Використовується у decision_making.py.
#       - Pydantic: float, (0,1].
#     kelly_alpha: 0.8
#       - Фракція Келлі (0-1).
#       - Використовується у decision_making.py.
#       - Pydantic: float, (0,1].
#     payoff_ratio_r: 1.5
#       - Відношення TP/SL для Келлі.
#       - Використовується у decision_making.py.
#       - Pydantic: float, >0.
#   qos:
#     mode: "defer"
#       - Режим QoS: defer/block/allow.
#       - Використовується у decision_making.py.
#       - Pydantic: str, enum.
#     enforce: false
#       - Чи застосовувати обмеження QoS.
#       - Використовується у decision_making.py.
#       - Pydantic: bool.
#     exposure_block_cooldown_sec: 30
#       - Затримка між блокуванням експозиції (секунди).
#       - Використовується у decision_making.py.
#       - Pydantic: int, >0.
#     symbol_cooldown_sec: 1
#       - Затримка між сигналами по одному символу (секунди).
#       - Використовується у decision_making.py.
#       - Pydantic: int, >0.
#     max_intents_per_minute_per_symbol: 60
#       - Максимальна кількість намірів на хвилину по символу.
#       - Використовується у decision_making.py.
#       - Pydantic: int, >0.
#   signal_weights:
#     - Ваги для композиції сигналу (8 метрик).
#     - Використовується у decision_making.py.
#     - Pydantic: dict[str, float].
