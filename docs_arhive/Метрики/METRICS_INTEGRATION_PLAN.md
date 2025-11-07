# Aurora/WiseScalp — Інтеграція нових метрик аналізу ринку

Дата: 2025-11-04
Автор: Codex (Aurora assistant)


**I. Technical Overview**
- Архітектура даних (чинна):
  - MarketData (live/testnet) → EVT:MARKET_TICK_RECEIVED → FeatureEngineering → EVT:FEATURES_CALCULATED → DecisionMaking → RiskManagement → Execution.
  - Домени у конфігу (`config/aurora/trading.yaml` — джерело істини):
    - market_data, feature_engineering, decision_making: live; risk_management: testnet; execution_position: testnet.
  - Базові фічі: `obi`, `tfi`, `delta_price` вже обчиснюються в:
    - `apps/reference/domains/market_data/websocket_aggregator.py:1` (агрегація),
    - `apps/reference/domains/feature_engineering/feature_engineering.py:1` (кінцева нормалізація і емісія подій),
    - використовуються в `apps/reference/domains/decision_making/decision_making.py:860` (ваги і поріг).

- Нові метрики та джерела даних:
  1) ema_bias = (EMA3 − EMA7)/EMA7
     - Дані: поточна ціна (mid/last). Є в EVT:MARKET_TICK_RECEIVED як `price`/`mid`.
     - Розрахунок: підтримувати стан на символ у FeatureEngineering (EMA3, EMA7 з α=2/(n+1)).
     - Вихід: скаляр у [-∞,+∞], на практиці |bias| < ~0.02 для М15/тiк. Нормалізація: clamp 2% і масштабування до [-1,1].

  2) volume_spike = vol_window / SMA(vol, 5)
     - Дані: проксі об’єму = кількість угод в останнi 60s з `WebSocketAggregator` (`buy_trades` + `sell_trades`).
     - Розрахунок: у FeatureEngineering тримати deque з 5 останніх 60s значень; spike = cur/avg.
     - Нормалізація: cap 3.0; phi = min(spike/3.0, 1.0) ∈ [0,1].

  3) volatility_state = range_window / SMA(range, 10)
     - Дані: ціни за останню хвилину; якщо немає OHLC, використовуємо min/max за вікно (60s) з агрегатора (він вже має `prices`).
     - Розрахунок: range = max(price) − min(price) за 60s; далі SMA(10) по вікнах.
     - Нормалізація: cap 3.0; phi = min(ratio/3.0, 1.0).

  4) depth_imbalance (asks/bids ratio, depth_half=1000)
     - Дані: `bid_size`, `ask_size` (bookTicker) є в події.
     - Розрахунок: ratio = (asks + depth_half)/(bids + depth_half). Мапінг до [-1,1]: imb = (ratio − 1)/(ratio + 1) ≡ tanh(ln(ratio)/2).
     - Налаштування: `trading.feature_engineering.liquidity.depth_half` (перенести з `binance_api.feature_engineering` до `trading.feature_engineering`).

  5) macro_sync (кореляція з BTCUSDT, ETHUSDT)
     - Дані: стріми цін для якорів (BTCUSDT, ETHUSDT). Потрібно додати підписку у MarketData лише на читання (без торгівлі).
     - Розрахунок: Pearson corr між r_t(symbol) та r_t(anchor) на N=30–60 тiків; агрегат: середнє або max(|corr|) зі знаком.
     - Конфіг: `market_data.macro_sync.anchors: [BTCUSDT, ETHUSDT]`, `window: 60`, `emit_abs: false`.

- Формат подій/полів (розширення EVT:FEATURES_CALCULATED):
  - features: { obi, tfi, delta_price, price, liquidity_kappa, ema_bias, volume_spike, volatility_state, depth_imbalance, macro_sync }
  - Всі нові метрики додаються як рядки (str) або float згідно з усталеною практикою у коді; рекомендовано str для сумісності з існуючим доменом.

- Нормалізація vs сирі значення (DecisionMaking):
  - Якщо `trading.decision.signals.normalize: true`, кожну нову метрику потрібно привести до [0,1] або [-1,1] та описати мапінг.
  - Рекомендація: ввімкнути нормалізацію (нові метрики різнимасштабні) та задати явні мапінги:
    - ema_bias_phi = clip((ema_bias/cap)+0.5, 0, 1) з cap=0.02 (±2%).
    - volume_spike_phi = min(spike/3.0, 1.0).
    - volatility_state_phi = min(ratio/3.0, 1.0).
    - depth_imbalance_phi = (imb+1)/2.
    - macro_sync_phi = (corr+1)/2.


**II. Implementation Roadmap (Phases + Tasks)**
- Phase 0 — Design & Config alignment
  - Узгодити місця зберігання параметрів: перенести `feature_engineering.liquidity.depth_half` під `trading.feature_engineering.liquidity`.
  - Додати до `trading.decision.signal_weights` нові ключі (див. CONFIG_SNIPPETS.yaml:1).
  - Додати `market_data.macro_sync.anchors` і `window` в системний конфіг.

- Phase 1 — FeatureEngineering: обчислення метрик
  - Файл: `apps/reference/domains/feature_engineering/feature_engineering.py:1`.
  - Зміни:
    - Стан на символ: ema3, ema7, vol_window_prices (deque), vol_window_trades (int), vol_hist (deque len=5), range_hist (deque len=10), depth_half cache, macro buffers для якорів.
    - ema_bias: оновити EMA на кожному тiку, обчислити bias і phi.
    - volume_spike: раз/60s закривати вікно (за ts) → vol_hist, spike, phi.
    - volatility_state: по вікну ціни → range, SMA(10), ratio, phi.
    - depth_imbalance: з bid/ask sizes + depth_half → ratio → imb → phi.
    - macro_sync: підтримувати returns deque по symbol та anchors, Pearson corr.
  - Емісія розширених features у EVT:FEATURES_CALCULATED.

- Phase 2 — MarketData: підписка на anchors (тільки читання)
  - Файли: `apps/reference/domains/market_data/websocket_aggregator.py:1`, `.../market_data_connector.py:1`.
  - Зміни:
    - Конфіг: `market_data.macro_sync.anchors`.
    - Додати підписку на anchors у WebSocketAggregator (не включати їх до `trading.instruments`).
    - В агрегаторі зберігати останні ціни anchors (prices deque) і прокидати їх у tick payload (напр., `tick['anchors'] = { 'BTCUSDT': last, ... }`).

- Phase 3 — DecisionMaking: оновлення сигналу
  - Файл: `apps/reference/domains/decision_making/decision_making.py:860`.
  - Зміни:
    - Розширити `phi_map`/raw map новими ключами.
    - Оновити логування `psi_vector` для нових компонентів.
    - В конфігу додати ваги (див. CONFIG_SNIPPETS.yaml:1). Рекомендація для testnet: normalize=true.

- Phase 4 — Tests
  - Unit (обчислення):
    - `tests/domains/test_feature_engineering.py:1` — нові тести на кожну метрику (контрольні серії → очікувані значення ±tol).
  - Regression (складені фічі):
    - `tests/test_features_signals_core.py:1` — скоринг DecisionMaking з новими вагами, нормалізацією і порогами.
  - Integration (live bridge):
    - `tests/integration/test_live_bridge_to_marketdata.py:1` — anchors присутні, коректно передаються, не впливають на виконання ордерів.

- Phase 5 — Synthetic dataset & backtest
  - Згенерувати JSONL/CSV потоки з контрольними шаблонами (тренд/флет/виброси, волатильність) для 2 інструментів та anchors.
  - Додати сценарії у `order_simulator/` (без інтеграції в прод, тільки для бектестів).

- Phase 6 — Stabilization
  - Тюнінг ваг, порогів, лімітів нормалізації.
  - Телеметрія: gauge для latency метрик (95p, 99p) у FeatureEngineering і DecisionMaking.


**III. Testing & Validation Plan**
- Контрольні значення (expected vs actual)
  - ema_bias: побудувати ціну з відомим приростом, перевірити EMA3/EMA7 і bias з точністю ≤ 1e-4.
  - volume_spike: послідовність вікон {10,10,10,10,30} → spike=30/10=3 → phi=1.0 (cap).
  - volatility_state: range={1,1,1,1,2,1,1,1,1,1} → SMA10=1.1 → ratio=~0.91/1.82 залежно від порядку.
  - depth_imbalance: bids=1000, asks=2000, depth_half=1000 → ratio=(3000/2000)=1.5 → imb=(1.5-1)/(1.5+1)=0.2.
  - macro_sync: синхронні ряди → corr≈1; інверсні → corr≈−1; ортогональні → ≈0.

- Стрес-тести (висока волатильність/спайки/гепи)
  - Серії з великими gap’ами ts → delta_price suppression, EMA стабільність, коректні закриття вікон vol/range.
  - Burst trades: 10× spike у 60s → latency < 10ms/тик, без backpressure.

- Latency-перевірки
  - Ціль: FE обчислення < 5ms/символ/тик (p95), Decision score < 2ms/символ/тик (p95) на 2–4 символи + 2 anchors.
  - Логи: виміряти `on_market_tick` і `_calculate_and_emit_features` часові мітки.

- Автотести (скелет):
  - Unit: `tests/domains/test_feature_engineering.py:1` — `test_ema_bias()`, `test_volume_spike()`, `test_volatility_state()`, `test_depth_imbalance()`, `test_macro_sync()`.
  - Regression: `tests/test_features_signals_core.py:1` — `test_signal_score_with_new_metrics_normalized()`.
  - Integration: `tests/integration/test_live_bridge_to_marketdata.py:1` — `test_anchor_subscription_and_payload()`.


**IV. Success Metrics & Acceptance Criteria (DoD)**
- Оновлення без пропусків кожні 60 сек
  - Для volume_spike/volatility_state зберігається 100% заповнення вікон (0 пропусків протягом 2 годин тесту).
- Коректна передача сигналів у DecisionMaking
  - У події `EVT:FEATURES_CALCULATED` присутні всі 5 нових метрик; у DecisionMaking вони враховуються в score (лог `psi_vector`).
- Точність: |manual − auto| ≤ 1%
  - Для контрольних сценаріїв (детерміновані ряди) розбіжність ≤ 1% для всіх метрик.
- Покращення якості прогнозу > 5% у backtest
  - Порівняння A/B (до/після) на синтетичних і реальних відрізках: precision/recall або hit-rate TP>SL покращується ≥ 5%.
- Перфоманс
  - p95 latency FE < 5ms/тик/символ, DM < 2ms/тик/символ; відсутність падінь/витоків пам’яті протягом 2 годин.


**V. Risk & Rollback Notes**
- Основні ризики
  - Часова розсинхронізація між anchors і цільовим символом (corr bias) — вирішується уніфікацією часових вікон (60s) та вирівнюванням по останньому доступному ts.
  - Невідповідність масштабів метрик → спотворення score — вирішується `signals.normalize: true` та cap/clip стратегій.
  - Надмірна чутливість volume_spike/volatility_state у тихих режимах — вводити підлогові/стелі (floor/cap) та згладжування EMA на рівні вікон.
  - Навантаження на подієвий цикл при burst’ах — тестувати p95/99 latency, backoff у QoS.

- Флаги та відкат
  - Конфіг-прапор `decision.signals.enable_new_metrics: true|false` (опц.) — швидке вимкнення нових ваг (залишити старі 3 метрики).
  - Швидкий відкат: повернути `signal_weights` до {obi,tfi,delta_price} та вимкнути `normalize`.
  - Підписка на anchors — окремий конфіг; легко відключити без впливу на торгівлю.


Додатково див. `Хазяйство/CONFIG_SNIPPETS.yaml:1` та `Хазяйство/SYNTHETIC_DATASET_SPEC.md:1` для прикладів конфігу і даних.
