# Aurora/WiseScalp — Аудит впровадження нових метрик (ema_bias, volume_spike, volatility_state, depth_imbalance, macro_sync)

Дата: 2025-11-05
Автор: Codex (Aurora assistant)


**Охоплення аудиту**
- Перевірено кодові домени: `market_data`, `feature_engineering`, `decision_making`.
- Перевірено конфіги: `config/aurora/system.yaml`, `config/aurora/trading.yaml` (джерело істини), `config/aurora/trading_v0.2.yaml` (застарілий/не використовується лоадером).
- Перевірено тести: наявність і зміст Phase3…Phase10.
- Зіставлено із планом: `Хазяйство/METRICS_INTEGRATION_PLAN.md:1` і звітом агента `METRICS_INTEGRATION_COMPLETE.md:1`.


**Підсумок (1–2 рядки)**
- 5 метрик реалізовано у `FeatureEngineering` та враховано в `DecisionMaking` з нормалізацією і вагами з конфігу. Тести для фаз 3–10 присутні.
- Виявлено 3 ключові розбіжності: (A) volume_spike рахується за кількістю тікiв, а не за торгами; (B) macro_sync не отримує цін якорів у live-циклі; (C) документи в Хазяйстві посилаються на `trading_v0.2.yaml` замість актуального `trading.yaml`.


**Знахідки по доменах**
- MarketData
  - `apps/reference/domains/market_data/websocket_aggregator.py:1` — додано підтримку `anchors` і колбек `set_anchor_update_callback`.
  - `apps/reference/domains/market_data/market_data_connector.py:120` — читає `anchors` з `trading.market_data.macro_sync.anchors`, передає колбек у FE (`set_feature_engineering` → `_on_anchor_update` → `FeatureEngineering.update_anchor_price`).
  - Прогалина: у `_fetch_and_emit_data` немає завантаження даних по `self.anchors` (bookTicker/trades/klines) — агрегатор не отримує оновлень для якорів, тож `macro_sync` у live не оновлюватиметься (тільки у тестах).

- FeatureEngineering
  - `apps/reference/domains/feature_engineering/feature_engineering.py:1` — Phase 1 версія з реалізацією всіх 5 метрик, буфери вікон, `update_anchor_price` присутній.
  - Емісія `EVT:FEATURES_CALCULATED` містить нові ключі (як str), узгоджено з планом.
  - Прогалина: `volume_spike` зараз рахується як лічильник тікiв у вікні (див. `_update_volume_spike`) замість (buy_trades+sell_trades) з тiка.

- DecisionMaking
  - `apps/reference/domains/decision_making/decision_making.py:880` — `signals.normalize` враховано; `phi_map` розширено до 8 компонентів; `psi_vector` логгує нові phi.

- Конфіги
  - Джерело істини: `config/aurora/trading.yaml:1` — містить нові ваги, `signals.normalize: true`, блоки для `feature_engineering` та `market_data.macro_sync` (+ anchors).
  - `ConfigLoader` використовує саме `trading.yaml` (`apps/reference/config_loader.py:112`). `trading_v0.2.yaml` — не використовується.
  - Документи у `Хазяйство/` посилаються на `trading_v0.2.yaml` — слід оновити посилання на `trading.yaml`.

- Тести
  - Наявні: `tests/test_phase3_psi_vector.py:1`, `tests/test_phase4_metrics.py:1`, `tests/test_phase6_integration.py`, `tests/test_phase7_performance.py`, `tests/test_phase8_backtest.py`, `tests/test_phase9_tuning.py`, `tests/test_phase10_documentation.py`.
  - Перевіряють наявність 8 ваг, phi-компоненти, сценарії кореляції, перфоманс та бектест (генератор синтетики всередині тестів).


**Статус по метриках (детально)**
- ema_bias — Впроваджено (FE обчислює phi у [0,1]); використовує ціну з тiка; у DM враховується; є тести.
- volume_spike — Частково: логіка FE рахує кількість тiків за вікно (замість об’єму/кількості трейдів). Рекомендація: використовувати `buy_volume+sell_volume` з payload MarketData як поточний обсяг вікна і зіставляти з SMA(5) історичних обсягів.
- volatility_state — Впроваджено: min/max у 60s, SMA(10) історичних діапазонів, cap → phi.
- depth_imbalance — Впроваджено: `(asks+depth_half)/(bids+depth_half)` → (ratio−1)/(ratio+1) → phi.
- macro_sync — Частково: FE реалізує буфери і кореляцію, але MarketData не постачає ціни якорів у live-циклі (див. прогалину вище).


**Невідповідності між планом/звітом і кодом**
- План/доки (Хазяйство) → `trading_v0.2.yaml`: неактуально. Фактичний файл — `config/aurora/trading.yaml`.
- Volume spike: у плані — “volume/avg_volume(5) із трейдів”, у коді — “count ticks per window”.
- Macro sync: у звіті — “anchor subscription non-blocking” (вірно), але фактично немає завантаження даних для `anchors` у MarketDataConnector.
- Rollback flag у звіті: приклад `metrics.enable_new_metrics: false` — такої гілки в конфігу немає; реальні прапори: `trading.decision.signals.enable_new_metrics` і `trading.feature_engineering.enable_new_metrics`.


**Рекомендовані правки (мінімальні та безпечні)**
- MarketDataConnector (якорі):
  - У `_fetch_and_emit_data` додати цикл по `self.anchors` з оновленням ціни: достатньо викликати `get_book_ticker(anchor)` і передати в `self.aggregator.on_trade(anchor, price=..., quantity="0", is_buyer_maker=False, ts=...)` або викликати `on_book_ticker` для оновлення latest_price. Це розблокує live-оновлення `macro_sync`.
- FeatureEngineering (volume_spike):
  - Замінити інкремент `vol_window_trades += 1` на додавання фактичного обсягу за тiк, напр.: `vol_window_trades += int(buy_volume + sell_volume)` (payload з MarketData). Так значення відповідатиме плану й тестам “volume-based spike”.
- Документи у `Хазяйство/`: 
  - Замінити посилання на `config/aurora/trading_v0.2.yaml` → `config/aurora/trading.yaml`.
  - Уточнити rollback: вказати два прапори (`decision.signals.enable_new_metrics`, `feature_engineering.enable_new_metrics`) або нульові ваги як швидкий шлях.


**Перевірка за чеклістом (VALIDATION_CHECKLIST.md)**
- 60s оновлення вікон: Частково — логіка є, але volume_spike та macro_sync потребують корекцій джерел/лічильників.
- Передача сигналів у DecisionMaking: Так — 8-компонентний `psi_vector`, нормалізація, ваги з конфігу.
- Ручний vs автоматичний ≤ 1%: Тести на контрольних серіях присутні; повну верифікацію не запускали у цій сесії.
- >5% покращення у backtest: Тести наявні; запуск поза межами цього аудиту.


**Висновок**
- Реалізація майже повна й узгоджена з планом. Для відповідності DoD і мінімізації ризиків у live режимі необхідно:
  1) Додати постачання цін якорів у MarketDataConnector.
  2) Перевести `volume_spike` на базу реальних трейдів із payload.
  3) Оновити посилання в документації Хазяйства на `trading.yaml`.

Після цих трьох правок система відповідатиме плану та заявленим критеріям.
