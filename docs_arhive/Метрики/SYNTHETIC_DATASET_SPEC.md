# Synthetic Dataset Spec — Нові метрики

Мета: reproducible набір сценаріїв для валідації та бектесту інтеграції п’яти нових метрик.

- Формат даних
  - JSONL або CSV з полями, що імітують `EVT:MARKET_TICK_RECEIVED`: { ts, symbol, price, bid, ask, mid, bid_size, ask_size, buy_volume, sell_volume }.
  - Додатково: anchors (BTCUSDT, ETHUSDT) з тим самим форматом.

- Сценарії
  1) Trend-Up (EMA-bias позитивний):
     - Для SOLUSDT/ETHUSDT — лінійне зростання ціни з малим шумом; bid/ask balanced; trades — стабільні.
     - Очікування: ema_bias > 0, volume_spike ≈ 1, volatility_state ≈ 1.
  2) Mean-Reversion (низька волатильність):
     - Невеликі коливання навколо середнього; range низький → volatility_state < 1.
  3) High-Vol Spike:
     - Різке розширення діапазону протягом 60s + burst trades (×3) → volume_spike → ~3 (cap), volatility_state > 1.5.
  4) Depth Skew:
     - ask_size стійко вищий за bid_size (або навпаки) при сталих цінах → depth_imbalance ≠ 0.
  5) Macro Sync:
     - BTCUSDT веде (trend up/down); SOLUSDT слідує з невеликим лагом → corr(SOL,BTC) ~ 0.8–0.95.
     - Інверсний приклад: ETHUSDT рухається протилежно до BTC → corr ~ −0.8.

- Об’єм та гранулярність
  - 2 торгові символи (SOLUSDT, ETHUSDT), 2 anchors (BTCUSDT, ETHUSDT) — 30 хвилин даних, крок 1–2s.
  - Віконні метрики: агрегувати у 60s інтервали для volume/range; зберігати розмітку в окремому полі (window_id).

- Очікувані еталони (для порівняння expected vs actual)
  - Надавати окремий JSON з очікуваними серіями: { metric_name: { symbol: [values...] } }.
  - Допустима похибка: ≤ 1% (або абсолютний tol 1e-4 для малих величин).

- Генерація
  - Рекомендовано: скрипт-генератор у `tools/` (не прод-код), який формує ticks і anchors.
  - Зберігати у `data/synthetic/`:
    - `ticks.jsonl`, `anchors.jsonl`, `expected_metrics.json`.

- Підключення до тестів
  - Unit: тест/фікстури читають expected і порівнюють із обчисленими FeatureEngineering.
  - Regression: тест загального скору з вагами (DecisionMaking) на тих самих даних.
