# Neocortex — API Dependencies (events map)

Цей документ описує, від яких доменів і подій залежить Neocortex, та які події він продукує.

## 1) Вхідні події (IN)

| Event | Джерело | Частота | Мінімально потрібні поля payload | Використання |
|---|---|---:|---|---|
| `EVT:FEATURES_CALCULATED` | `feature_engineering` | 1–5Hz (або бар) | `symbol`, `ts`, `features`, `price_ref` | state/latent, training, intent build |
| `EVT:RISK_ASSESSMENT_COMPLETED` | `risk_management` | ~1Hz | `symbol`, `ts`, `risk_score`, `allowed` | gates, risk proxy |
| `EVT:PORTFOLIO_STATE_UPDATED` | `position_tracking` | ~1Hz | `ts`, `equity`, `positions[]` | exposure, drawdown, viability context |
| `EVT:REGIME_DETECTED` | `regime_detector` | ~bar | `symbol`, `ts`, `regime`, `confidence` | conditioning, gates |
| `EVT:TRADE_INTENT_PROPOSED` | `decision_making` | подієво | `instrument`, `side`, `order`, `why[]`, `dto_version` | divergence (R2) |
| `EVT:ORDER_ACK` | `execution_position` | подієво | `symbol`, `order_id`, `client_order_id` | episode tracking |
| `EVT:ORDER_FILL` | `execution_position` | подієво | `symbol`, `qty`, `price`, `reduce_only` | episode outcome |
| `EVT:POSITION_OPENED` | `execution_position` | подієво | `symbol`, `side`, `qty`, `avg_price` | episode open |
| `EVT:POSITION_CLOSED` | `execution_position` | подієво | `symbol`, `trade_id`, `close_ts_ms`, `realized_pnl_net`, `fees` | episode close + structured reward (no proxy fallback) |

Примітка: у Standalone режимі ці події відновлюються із WAL через `verb/op/pld`.

---

## 2) Вихідні події (OUT)

> На R0–R2 ці події існують лише як логи/моніторинг. Їх emission у FSM‑шину дозволяється лише при in‑proc запуску.

| Event | Призначення | Кому |
|---|---|---|
| `EVT:NEOCORTEX_STATE_UPDATED` | latency‑safe стан/метрики/латент | monitoring/logs |
| `EVT:NEOCORTEX_ALERT` | інваріанти/аномалії/OOD/churn | monitoring/operator |
| `EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED` | рекомендація без впливу (R2) | logs/reports |
| `EVT:NEOCORTEX_TRADE_INTENT_PROPOSED` | окремий intent‑канал (R3, gated) | bridge/DM (optional) |
| `EVT:NEOCORTEX_MODULATION_PROPOSED` | overlay‑пропозиція (R3, gated) | DM modulation store |

---

## 3) Заборонені інтеграції (must not)

- Neocortex **не** має писати в `config/aurora/*.yaml`.
- Neocortex **не** має емити `CMD:*` напряму.
- Neocortex **не** має “патчити” обʼєкти `AuroraConfig` в рантаймі.

