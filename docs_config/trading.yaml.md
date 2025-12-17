---

## Блок `trading.instruments`

### Опис
Блок `instruments` містить специфікації для кожного інструменту (символу) Binance Futures, які використовуються для коректної роботи торгової системи Aurora. Кожен підблок відповідає окремому активу (наприклад, SOLUSDT, ETHUSDT) та визначає його торгові параметри.

### Параметри
- `symbol`: Символ інструменту (рядок, обов'язковий). Використовується для ідентифікації активу у всіх модулях системи. Валідується через Pydantic як required.
- `step_size`: Мінімальний крок зміни кількості (лоту) для ордерів. Визначає, з якою дискретністю можна виставляти об'єм позиції. Важливо для коректного округлення об'ємів при розрахунках.
- `tick_size`: Мінімальний крок ціни (price tick) для ордерів. Всі ціни (TP/SL, вхід, вихід) мають бути кратні цьому значенню. Використовується для квантизації цін у FSM та при розрахунках у execution_position.
- `min_notional`: Мінімальний номінал ордеру в USD. Ордери з меншою вартістю будуть відхилені біржею. Використовується для валідації перед відправкою заявки.

### Вплив на систему
- Всі розрахунки цін (TP, SL, entry) та об'ємів позицій проходять через ці параметри для уникнення помилок API Binance.
- Некоректно задані значення можуть призвести до відхилення ордерів або помилок при виконанні FSM.

### Формули та використання в коді
- Округлення ціни: `price = round(price / tick_size) * tick_size`
- Округлення кількості: `qty = round(qty / step_size) * step_size`
- Мінімальний notional: `qty * price >= min_notional`
- Основний код: `apps/reference/domains/execution_position/`, функції розрахунку bracket-ордерів, FSM ManageFlow.

### Fallback/Override
- Значення мають бути визначені для кожного символу окремо. Відсутність параметра призведе до помилки валідації.

### Валідація
- Pydantic-схеми: `config_models.py` (AuroraInstrumentSpec)
- Тести: `tests/domains/test_per_instrument_overrides.py`, `test_fsm_manage_brackets.py`

---

## Блок `trading.aurora_instruments`

### Опис
Блок `aurora_instruments` містить пер-інструментні (пер-активні) налаштування для стратегії Aurora, отримані з Optuna-оптимізації. Дозволяє задавати унікальні параметри для кожного активу, які мають пріоритет над глобальними налаштуваннями (`trading.decision`).

### Параметри (на прикладі ETHUSDT, SOLUSDT, DOGEUSDT, XRPUSDT)
- `weights`: Ваги для кожного сигналу/метрики (ema, volume, macro, liquidity, obi, tfi, volatility, depth_imbalance, delta_price). Визначають вплив кожної метрики на фінальний сигнал. Використовуються у модулі `decision_making`.
- `side_bias`: Параметри штрафу за односторонню торгівлю (penalty_factor, window_sec, target_ratio). Дозволяють уникати накопичення позицій лише в один бік. Використовується у FSM та при розрахунку сигналу.
- `regime_thresholds`: Множники порогів для різних ринкових режимів (HIGH_VOLATILITY, LOW_VOLATILITY, MEAN_REVERSION, DEFAULT). Дозволяють адаптувати чутливість до сигналу залежно від режиму ринку.
- `regime_sizing`: Множники розміру позиції для різних режимів. Дозволяють зменшувати/збільшувати ризик у залежності від волатильності.
- `exit`: Параметри виходу (sl_pct — стоп-лосс у %, max_hold_sec — максимальний час утримання позиції). Використовується у FSM для розрахунку SL та watchdog.
- `take_profit`: Параметри часткового виходу (tp_low_ratio, tp_high_ratio, partial_exit_pct). Дозволяють реалізувати TP1/TP2 з частковим закриттям позиції.
- `trailing_stop`: Параметри трейлінг-стопу (enabled, activation_pct, trail_pct, min_update_interval_sec). Використовується для динамічного захисту прибутку.
- `allowed_regimes`: Список дозволених режимів для торгівлі цим активом. Дозволяє уникати торгівлі у несприятливих умовах.

### Вплив на систему
- Пер-інструментні налаштування мають найвищий пріоритет (див. fallback chain).
- Дозволяють гнучко оптимізувати поведінку стратегії під кожен актив.
- Відсутність блоку для активу → використовується глобальний блок `trading.decision`.

### Формули та використання в коді
- Lookup: `self._get_aurora_instrument_cfg(symbol)`
- Fallback: якщо параметр не заданий для активу, використовується глобальний (`trading.decision`).
- Основний код: `apps/reference/domains/decision_making/`, `execution_position/`, `feature_engineering/`

### Fallback/Override
- Fallback chain: `aurora_instruments.<SYMBOL>.<param>` → `decision.<param>` (глобальний)
- При відсутності параметра — використовується дефолт із глобального блоку.

### Валідація
- Pydantic-схеми: `config_models.py` (AuroraInstrumentConfig)
- Тести: `tests/domains/test_per_instrument_overrides.py`, `test_aurora_instrument_config.py`

---

## Блок `trading.mean_reversion_1m`

### Опис
Блок `mean_reversion_1m` містить налаштування для стратегії середньоринкової (mean reversion) на 1-хвилинних барах. Дозволяє окремо вмикати/вимикати стратегію для кожного активу та задавати специфічні параметри для кожного з них.

### Параметри
- `enabled`: Глобальний перемикач для активації стратегії (true/false).
- `assets`: Словник з параметрами для кожного активу (DOGEUSDT, BTCUSDT, XRPUSDT):
  - `enabled`: Чи активна стратегія для цього активу.
  - `strategy`: Параметри Bollinger Bands:
    - `bb_window`: Вікно для розрахунку BB (кількість барів).
    - `bb_num_std`: Кількість стандартних відхилень для побудови BB.
    - `min_bb_width`: Мінімальна ширина BB (захист від низької волатильності).
    - `entry_threshold`: Поріг для входу (відхилення від середньої).
    - `sl_atr_mult`: Множник ATR для SL (динамічний стоп-лосс).
    - `tp_to_mid`: Чи використовувати середню BB як ціль для TP.
    - `cooldown_sec`: Кулдаун між угодами.
  - `allowed_regimes`: Список режимів ринку, в яких дозволена торгівля для цього активу.
  - `risk`: Розмір позиції у USD.

### Вплив на систему
- Дозволяє гнучко налаштовувати mean reversion-стратегію для кожного активу.
- Всі параметри впливають на генерацію сигналів, розрахунок SL/TP та управління ризиком.

### Формули та використання в коді
- Розрахунок BB: `BB = SMA ± bb_num_std * stddev`
- SL: `SL = entry_price - sl_atr_mult * ATR` (динамічний)
- TP: залежить від `tp_to_mid` (або до середньої, або до зовнішньої BB)
- Основний код: `apps/reference/domains/decision_making/mean_reversion_1m.py`, `feature_engineering/`

### Fallback/Override
- Відсутність параметра для активу → стратегія не активна для нього.
- SL/TP можуть бути динамічно переозначені через overrides.

### Валідація
- Pydantic-схеми: `config_models.py` (MeanReversion1mConfig)
- Тести: `tests/domains/test_per_instrument_overrides.py`, `test_aurora_instrument_config.py`

---

## Блок `trading.tca_prefs`

### Опис
Блок `tca_prefs` містить налаштування для Transaction Cost Analysis (TCA) — аналізу та контролю витрат на виконання ордерів.

### Параметри
- `max_slippage_pct`: Максимально допустимий відсоток прослизання (slippage) при виконанні ордерів.
- `preferred_venue`: Бажана біржа для виконання (наприклад, "binance").
- `execution_priority`: Пріоритет виконання (наприклад, "speed" для максимально швидкого виконання).

### Вплив на систему
- Визначає обмеження на прослизання та вибір біржі для виконання ордерів.
- Впливає на логіку вибору venue та типу ордеру у execution_position.

### Формули та використання в коді
- Перевірка slippage: `actual_slippage <= max_slippage_pct`
- Основний код: `apps/reference/domains/execution_position/`, TCA-модуль.

### Fallback/Override
- Відсутність блоку — використовуються дефолтні значення у коді.

### Валідація
- Pydantic-схеми: `config_models.py` (TCAPrefsConfig)
- Тести: `tests/domains/test_per_instrument_overrides.py`

---

## Блок `trading.risk_budgets`

### Опис
Блок `risk_budgets` визначає основні ліміти ризику для портфеля та окремих позицій. Використовується для контролю максимальної експозиції та втрат у системі.

### Параметри
- `max_portfolio_risk_pct`: Максимальний відсоток ризику для всього портфеля (наприклад, 5%).
- `max_single_position_risk_pct`: Максимальний ризик на одну позицію (наприклад, 1%).
- `max_daily_loss_pct`: Максимально допустимий відсоток втрат за день (наприклад, 2%).

### Вплив на систему
- Всі ці ліміти використовуються для перевірки допустимості нових угод та контролю денної втрати.
- Перевищення будь-якого з лімітів призводить до блокування нових угод або зупинки торгівлі.

### Формули та використання в коді
- Перевірка портфельного ризику: `portfolio_risk <= max_portfolio_risk_pct`
- Перевірка ризику на позицію: `position_risk <= max_single_position_risk_pct`
- Перевірка денної втрати: `daily_loss <= max_daily_loss_pct`
- Основний код: `apps/reference/domains/risk_management/`, risk gate у FSM.

### Fallback/Override
- Відсутність блоку — використовуються дефолтні значення у коді.

### Валідація
- Pydantic-схеми: `config_models.py` (RiskBudgetsConfig)
- Тести: `tests/domains/test_per_instrument_overrides.py`, `test_aurora_instrument_config.py`

---

## Блок `trading.risk`

### Опис
Блок `risk` містить розширені налаштування управління ризиками, включаючи ліміти денної просадки, ваги для скорингових метрик, профілі, soft-ліміти, адаптацію до режиму ринку та додаткові фічі.

### Параметри
- `max_daily_drawdown_limit`: Максимальна денна просадка (наприклад, 0.05 = 5%).
- `score_weights`: Ваги для скорингових метрик (delta_price, obi, tfi, absorption_inverse).
- `testnet`/`production`: Максимальний risk_score для різних режимів (0.90/0.80).
- `trading_allowed_thresholds`: Активний поріг risk_score (залежить від режиму).
- `daily`: Ліміти на денний збиток, просадку та час скидання лічильника.
- `profile`: Активний профіль ризику (balanced/conservative/accelerated).
- `soft_limits`: Параметри soft-лімітів (режим, мінімальний notional, directional ratio, exposure).
- `regime_adaptation`: Множники для directional_ratio_max залежно від ринкового режиму.
- `feature_flags`: Вмикання/вимикання динамічних фіч (dynamic_ratio, clipping_enabled).

### Вплив на систему
- Всі ці параметри впливають на допуск до торгівлі, розмір позицій, soft-кліпінг та адаптацію до ринку.
- Перевищення лімітів призводить до блокування нових угод.

### Формули та використання в коді
- Розрахунок risk_score: `risk_score = Σ(metric * weight)`
- Soft-кліпінг: якщо позиція перевищує ліміт — зменшується до допустимого значення.
- Адаптація directional_ratio: залежить від режиму (trend_up_delta, flat_delta тощо).
- Основний код: `apps/reference/domains/risk_management/`, FSM risk gate.

### Fallback/Override
- Відсутність блоку — використовуються дефолтні значення у коді.
- Профіль може бути змінений через перемикач profile.

### Валідація
- Pydantic-схеми: `config_models.py` (RiskConfig)
- Тести: `tests/domains/test_per_instrument_overrides.py`, `test_aurora_instrument_config.py`, `test_fsm_manage_brackets.py`

---

## Блок `trading.feature_engineering`

### Опис
Блок `feature_engineering` містить налаштування для обчислення технічних індикаторів та метрик, які використовуються у стратегіях Aurora та Mean Reversion. Дозволяє задавати параметри вікон, періодів та контроль активації нових метрик.

### Параметри
- `ema`: Параметри експоненціального ковзаючого середнього (EMA)
  - `period_short`: Короткий період EMA (наприклад, 3).
  - `period_long`: Довгий період EMA (наприклад, 7).
- `volume`: Параметри для обчислення об'ємів
  - `window_sec`: Вікно у секундах для підрахунку об'ємів.
  - `sma_length`: Довжина SMA для визначення сплесків об'ємів.
- `volatility`: Параметри для обчислення волатильності
  - `window_sec`: Вікно у секундах для розрахунку діапазону.
  - `sma_length`: Довжина SMA для стану волатильності.
- `liquidity`: Параметри ліквідності
  - `depth_half`: Глибина для розрахунку дисбалансу (USD або кількість).
- `enable_new_metrics`: Вмикання нових метрик (true/false).
- `compute_all`: Обчислювати всі нові метрики (true/false).

### Вплив на систему
- Всі ці параметри впливають на якість та швидкість генерації сигналів.
- Некоректні значення можуть призвести до некоректної роботи індикаторів та стратегії.

### Формули та використання в коді
- EMA: `EMA_t = α * Price_t + (1-α) * EMA_{t-1}`
- SMA: `SMA = Σ(Price) / N`
- Основний код: `apps/reference/domains/feature_engineering/`, `decision_making/`

### Fallback/Override
- Відсутність блоку — використовуються дефолтні значення у коді.
- Можливі пер-інструментні overrides через aurora_instruments.

### Валідація
- Pydantic-схеми: `config_models.py` (FeatureEngineeringConfig)
- Тести: `tests/domains/test_per_instrument_overrides.py`, `test_aurora_instrument_config.py`

---

## Блок `trading.market_data`

### Опис
Блок `market_data` містить налаштування для збору та обробки ринкових даних з Binance. Дозволяє контролювати частоту опитування, типи стрімів, ліміти API та параметри кореляції з "якорями" (anchor symbols).

### Параметри
- `poll_interval_sec`: Інтервал опитування ринку (секунди).
- `websocket_streams`: Список стрімів WebSocket (наприклад, "bookTicker", "trade").
- `use_multiprocessing`: Чи запускати збір ринкових даних у окремому процесі (true/false).
- `api_call_limits`: Ліміти на API-запити (наприклад, get_recent_trades, get_klines).
- `macro_sync`: Параметри для кореляції з anchor-символами:
  - `enabled`: Вмикання кореляції.
  - `anchors`: Список anchor-символів.
  - `window`: Вікно для розрахунку кореляції.
  - `emit_abs`: Чи використовувати абсолютне значення кореляції.

### Вплив на систему
- Визначає частоту та якість ринкових даних для всіх стратегій.
- Від коректності налаштувань залежить стабільність роботи FSM та генерація сигналів.

### Формули та використання в коді
- Кореляція: `corr = cov(X, Y) / (σ_X * σ_Y)`
- Основний код: `apps/reference/domains/feature_engineering/`, `market_data/`

### Fallback/Override
- Відсутність блоку — використовуються дефолтні значення у коді.

### Валідація
- Pydantic-схеми: `config_models.py` (MarketDataConfig)
- Тести: `tests/domains/test_per_instrument_overrides.py`, `test_aurora_instrument_config.py`

---

## Блок `trading.ops`

### Опис
Блок `ops` містить налаштування для операційної безпеки та режиму роботи системи. Відповідає за аварійне вимкнення, "тихі години" та allowlist для символів.

### Параметри
- `panic_killswitch`: Вмикає аварійний вимикач для екстреної зупинки всіх торгівельних операцій (true/false).
- `quiet_hours_utc`: Список часових інтервалів (UTC), коли торгівля обмежена або вимкнена.
- `allowlist_symbols`: Список дозволених символів для торгівлі (порожній — без обмежень).

### Вплив на систему
- Аварійний вимикач дозволяє миттєво зупинити всі торгові операції у разі критичних збоїв.
- "Тихі години" дозволяють уникати торгівлі у малоліквідні або ризиковані періоди.
- Allowlist обмежує торгівлю лише певними активами.

### Формули та використання в коді
- Перевірка часу: `now_utc in quiet_hours_utc`
- Основний код: `apps/reference/domains/execution_position/`, `ops/`

### Fallback/Override
- Відсутність блоку — всі функції вимкнені (торгівля дозволена завжди).

### Валідація
- Pydantic-схеми: `config_models.py` (OpsConfig)
- Тести: `tests/domains/test_per_instrument_overrides.py`, `test_aurora_instrument_config.py`

---

## Блок `trading.execution`

### Опис
Блок `execution` містить налаштування для управління виконанням ордерів, моніторингу, контролю експозиції, типів ордерів, параметрів watchdog та інших аспектів order management.

### Параметри
- `manage`: Параметри автоматичного управління позиціями (TP/SL, orphan monitor, brackets).
- `exposure`: Ліміти експозиції портфеля, сторони, символу, параметри резервування, левередж.
- `open_order_type`: Тип ордеру для відкриття позиції (LIMIT, MARKET тощо).
- `order_params`: Параметри для кожного типу ордеру (наприклад, timeInForce, workingType).
- `watchdog`: Параметри таймаутів для ACK/FILL, інтервал перевірки, rps-ліміт.
- `orders`: TTL для ордерів, ліміти сліпіджу, параметри скасування.

### Вплив на систему
- Всі ці параметри визначають поведінку FSM ManageFlow, моніторинг ордерів, автоматичне закриття, atomic bracket cleanup, orphan monitor.
- Некоректні значення можуть призвести до втрати контролю над позиціями або помилок при виконанні.

### Формули та використання в коді
- TTL: `order_expiry = now + default_ttl_seconds`
- Сліпідж: `actual_slippage <= slippage_cap_bps`
- Основний код: `apps/reference/domains/execution_position/`, FSM ManageFlow, order_guardian.

### Fallback/Override
- Відсутність блоку — використовуються дефолтні значення у коді.
- Можливі пер-інструментні overrides через aurora_instruments.

### Валідація
- Pydantic-схеми: `config_models.py` (ExecutionConfig)
- Тести: `tests/domains/test_per_instrument_overrides.py`, `test_aurora_instrument_config.py`, `test_fsm_manage_brackets.py`

---

## Блок `trading.domain_configuration`

### Опис
Блок `domain_configuration` дозволяє окремо задавати режим роботи (trading_mode) для кожного домену системи: market_data, feature_engineering, decision_making, risk_management, execution_position, audit_trail. Це дає змогу комбінувати live/testnet режими для різних частин пайплайну.

### Параметри
- `market_data.trading_mode`: Режим для збору ринкових даних ("live"/"testnet").
- `feature_engineering.trading_mode`: Режим для обробки фіч ("live"/"testnet").
- `decision_making.trading_mode`: Режим для генерації сигналів ("live"/"testnet").
- `risk_management.trading_mode`: Режим для скорингу ризику ("live"/"testnet").
- `execution_position.trading_mode`: Режим для виконання ордерів ("live"/"testnet").
- `audit_trail.trading_mode`: Режим для логування ("live"/"testnet").

### Вплив на систему
- Дозволяє гнучко комбінувати джерела даних та режими виконання для тестування, продакшену чи гібридних сценаріїв.
- Важливо для безпечного тестування нових стратегій без ризику для реальних коштів.

### Формули та використання в коді
- Вибір режиму: `self.config['domain_configuration'][domain]['trading_mode']`
- Основний код: всі домени у `apps/reference/domains/`, ConfigLoader.

### Fallback/Override
- Відсутність блоку — використовується глобальний режим з trading.mode.

### Валідація
- Pydantic-схеми: `config_models.py` (DomainConfiguration)
- Тести: `tests/domains/test_per_instrument_overrides.py`, `test_aurora_instrument_config.py`

---

## Блок `trading.models`

### Опис
Блок `models` містить налаштування для детектора ринкових режимів (RegimeDetector Domain), зокрема для визначення волатильності та mean reversion.

### Параметри
- `volatility`:
  - `enabled`: Вмикання детектора волатильності.
  - `atr_period`: Період ATR для розрахунку волатильності.
  - `threshold_multiplier`: Множник для визначення HIGH_VOLATILITY (ATR > multiplier × SMA(ATR)).
  - `low_vol_multiplier`: Множник для LOW_VOLАТILITY (ATR < multiplier × SMA(ATR)).
- `mean_reversion`:
  - `threshold`: Поріг для визначення mean reversion (відхилення ціни від SMA).

### Вплив на систему
- Визначає режими ринку, які впливають на всі стратегії, sizing, фільтри сигналів.
- Некоректні значення можуть призвести до хибної класифікації режиму ринку.

### Формули та використання в коді
- ATR: `ATR = SMA(TrueRange, atr_period)`
- HIGH_VOL: `ATR > threshold_multiplier × SMA(ATR)`
- LOW_VOL: `ATR < low_vol_multiplier × SMA(ATR)`
- Mean reversion: `abs(price - SMA) < threshold × SMA`
- Основний код: `apps/reference/domains/feature_engineering/`, `decision_making/`, `regime_detector/`

### Fallback/Override
- Відсутність блоку — використовуються дефолтні значення у коді.

### Валідація
- Pydantic-схеми: `config_models.py` (RegimeModelsConfig)
- Тести: `tests/domains/test_per_instrument_overrides.py`, `test_aurora_instrument_config.py`

---

## Блок `trading.risk_management`

### Опис
Блок `risk_management` містить налаштування джерел даних для risk scoring (portfolio_state, market_data). Дозволяє явно вказати, які джерела використовувати для оцінки ризику.

### Параметри
- `data_sources.portfolio_state`: Джерело даних для стану портфеля ("live"/"testnet").
- `data_sources.market_data`: Джерело ринкових даних ("live"/"testnet").

### Вплив на систему
- Дозволяє тестувати risk scoring на тестнеті, навіть якщо решта системи працює з live-даними.

### Формули та використання в коді
- Вибір джерела: `self.config['risk_management']['data_sources']`
- Основний код: `apps/reference/domains/risk_management/`, ConfigLoader.

### Fallback/Override
- Відсутність блоку — використовується режим з domain_configuration/risk_management.

### Валідація
- Pydantic-схеми: `config_models.py` (RiskManagementConfig)
- Тести: `tests/domains/test_per_instrument_overrides.py`, `test_aurora_instrument_config.py`

---

## Блок `binance_api`

### Опис
Блок `binance_api` містить налаштування для підключення до API Binance Futures у режимах live та testnet. Всі ключі та секрети підтягуються з .env-файлу через шаблони змінних оточення.

### Параметри
- `live`:
  - `api_key`: Ключ API для live-режиму (змінна оточення).
  - `api_secret`: Секретний ключ для live-режиму (змінна оточення).
  - `rest_url`: REST endpoint для live-режиму.
  - `ws_url`: WebSocket endpoint для live-режиму.
- `testnet`:
  - `api_key`: Ключ API для testnet-режиму (змінна оточення).
  - `api_secret`: Секретний ключ для testnet-режиму (змінна оточення).
  - `rest_url`: REST endpoint для testnet-режиму.
  - `ws_url`: WebSocket endpoint для testnet-режиму.
- `feature_engineering.liquidity.depth_half`: Параметр для розрахунку ліквідності (може бути специфічним для venue).

### Вплив на систему
- Визначає, які ключі та ендпоінти використовуються для підключення до Binance.
- Некоректні значення призведуть до неможливості підключення або помилок при виконанні ордерів.

### Формули та використання в коді
- Підстановка змінних: `ConfigLoader._resolve_env_vars()`
- Основний код: `bridge/`, `apps/reference/domains/execution_position/`, `feature_engineering/`

### Fallback/Override
- Відсутність блоку — підключення до Binance неможливе.
- Значення мають бути визначені для кожного режиму окремо.

### Валідація
- Pydantic-схеми: `config_models.py` (BinanceAPIConfig)
- Тести: `tests/domains/test_per_instrument_overrides.py`, `test_aurora_instrument_config.py`

---

## Блок `execution`

### Опис
Блок `execution` містить додаткові налаштування для контролю виконання ордерів, watchdog, order_guardian та інших аспектів, які не входять до основного блоку trading.execution.

### Параметри
- `allow_trade_with_guardian_tidy_only`: Дозволяє торгівлю лише після "tidy"-синхронізації Guardian (захист від торгівлі на "холодному" старті).
- `fsm_periodic_cleanup_enabled`: Вмикає періодичне очищення FSM.
- `preflight_backoff_ms`: Список затримок (мс) для preflight backoff.
- `anti_race_close_ms`: Затримка для захисту від race condition при закритті позиції.
- `min_post_interval_per_symbol_ms`: Мінімальний інтервал між постами по одному символу.
- `order_guardian.poll_interval_ms`: Інтервал опитування Guardian.

### Вплив на систему
- Всі ці параметри впливають на стабільність та безпечність виконання FSM, Guardian, order management.

### Формули та використання в коді
- Основний код: `apps/reference/domains/execution_position/`, order_guardian, FSM ManageFlow.

### Fallback/Override
- Відсутність блоку — використовуються дефолтні значення у коді.

### Валідація
- Pydantic-схеми: `config_models.py` (ExecutionAuxConfig)
- Тести: `tests/domains/test_per_instrument_overrides.py`, `test_aurora_instrument_config.py`

---

## Блок `guardian`

### Опис
Блок `guardian` містить налаштування для модуля Order Guardian — моніторингу, очищення, ведення журналу та TTL для cleanup.

### Параметри
- `unified`: Вмикає уніфікований режим Guardian.
- `emit_tidy_event`: Вмикає генерацію tidy-подій.
- `cleanup_ttl_ms`: TTL для очищення (мс).
- `symbol_cooldown_ms`: Кулдаун для символу (мс).
- `poll_interval_ms`: Інтервал опитування (мс).
- `ledger_db_path`: Шлях до бази даних журналу ордерів.

### Вплив на систему
- Всі ці параметри впливають на частоту очищення, моніторинг та журналювання ордерів.

### Формули та використання в коді
- Основний код: `apps/reference/domains/execution_position/`, order_guardian.

### Fallback/Override
- Відсутність блоку — використовуються дефолтні значення у коді.

### Валідація
- Pydantic-схеми: `config_models.py` (GuardianConfig)
- Тести: `tests/domains/test_per_instrument_overrides.py`, `test_aurora_instrument_config.py`

---
