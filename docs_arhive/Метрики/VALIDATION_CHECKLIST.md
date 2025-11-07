```markdown
# Validation Checklist — Нові метрики Aurora/WiseScalp

Версія: 2025-11-05 (post-fix verification)

- Передумови
  - Переконатися, що `mode: "testnet"` у `config/aurora/trading.yaml:1` (джерело істини).
  - Domain modes: market_data/feature_engineering/decision_making = live, risk_management/execution = testnet (перевірити `domain_configuration`).
  - Додано anchors у `market_data.macro_sync.anchors` (BTCUSDT, ETHUSDT).

- Конфіг/ваги
  - Ввімкнено `decision.signals.normalize: true` (рекомендовано) або підтверджено масштаби ваг при `false`.
  - Оновлено `decision.signal_weights` з 5 новими метриками (див. `Хазяйство/CONFIG_SNIPPETS.yaml:1`).
  - Перенесено `feature_engineering.liquidity.depth_half` під `trading.feature_engineering.liquidity`.

- Дані/івенти
  - Перевірити, що `EVT:MARKET_TICK_RECEIVED` приходить кожні 1–2s (лог `apps/reference/domains/market_data/market_data_connector.py:1`).
  - Переконатися, що `EVT:FEATURES_CALCULATED` містить: `ema_bias`, `volume_spike`, `volatility_state`, `depth_imbalance`, `macro_sync`.

- Обчислення/коректність
  - ema_bias: з детермінованим стрімом тренду bias > 0; на флеті ~0.
  - volume_spike: при інжекції burst-трейдів значення → ~[2..3] і phi → 1.0 (cap).
  - volatility_state: при розширенні діапазону цін ratio > 1.
  - depth_imbalance: при asks ≫ bids → позитивне значення; при bids ≫ asks → негативне.
  - macro_sync: на SOLUSDT під час руху BTC — corr значимо відмінний від 0.

- DecisionMaking
  - Логи містять `psi_vector` з новими phi-компонентами.
  - Поріг `signal_threshold` коректно модифікується режимом (`regime_threshold_multipliers`).
  - Формується TRADE_INTENT при перевищенні порогу, QoS не блокує валідні наміри.

- Перфоманс/стабільність
  - p95 latency: FE < 5ms/тик/символ, DM < 2ms/тик/символ (оціночні логи).
  - Немає orphan-івентів/витоків пам’яті за 2 години.

- Backtest/DoD
  - Синтетичний датасет: усі контрольні кейси пройдені (≤ 1% розбіжності з ручним).
  - A/B бектест: покращення > 5% (precision/hit-rate).

- Rollback (за потреби)
  - Вимкнути `decision.signals.enable_new_metrics` або повернути `signal_weights` до базових.
  - Вимкнути anchors у `market_data`.
