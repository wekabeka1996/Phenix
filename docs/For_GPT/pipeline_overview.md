# Pipeline Overview

## Flowchart (событийная дорожка)

```
MarketDataConnector
  (apps/reference/domains/market_data/market_data_connector.py)
  -- EVT:MARKET_TICK_RECEIVED --> FeatureEngineering
      ↓
FeatureEngineering
  (apps/reference/domains/feature_engineering/feature_engineering.py)
  -- EVT:FEATURES_CALCULATED --> {RiskManagement, DecisionMaking}
      ↓                           ↖ EVT:REGIME_DETECTED / EVT:PORTFOLIO_STATE_UPDATED / EVT:EXPOSURE_SUMMARY_UPDATED feed back into DecisionMaking
RiskManagement
  (apps/reference/domains/risk_management/risk_management.py)
  -- EVT:RISK_ASSESSMENT_COMPLETED --> DecisionMaking
      ↓
DecisionMaking
  (apps/reference/domains/decision_making/decision_making.py)
  -- EVT:TRADE_INTENT_PROPOSED --> ExecutionManagement / AuroraBridge
      ↓
AuroraBridge (apps/reference/main.py) / ExecutionManagement stub
  • QoS + portfolio freshness gates (INTENT_DEFERRED, INTENT_DROPPED events)
  -- CMD:OPEN --> ExecPos FSM
      ↓
ExecPos FSM
  (apps/reference/domains/execution_position/fsm.py)
  • OpenFlow → DEC:OPEN
  • ManageFlow (fills/tracking/brackets)
  • CloseFlow on CMD:CLOSE
  • Emits EVT:EXPOSURE_SUMMARY_UPDATED after portfolio/fill/cancel
      ↓
BinanceAdapter
  (apps/reference/adapters/binance_adapter.py)
  Executes DEC:OPEN/CLOSE/PLACE_ORDER/CANCEL_ORDER via REST
```

Каждый блок слушает указанные события и передаёт дальше только те сообщения, которые реально публикуются (см. код). Комментарии на каждом переходе отражают фактически испускаемый `op:verb`.

## Слои и события

- **MarketDataConnector** получает `bookTicker`, `trades`, `klines` через `BinanceAdapter` и выпускает `EVT:MARKET_TICK_RECEIVED` с реальными фичами по каждому символу. Конфигурационные ключи: `binance_api`, `trading.market_data` (poll_interval, websocket_streams, macro_sync anchors), `domain_configuration.market_data`.
- **FeatureEngineering** (`feature_engineering.py`) слушает `EVT:MARKET_TICK_RECEIVED`, рассчитывает Phase‑1 метрики (OBI/TFI/delta_price + новые фичи), управляет буферами макросинхронизации и эмитит `EVT:FEATURES_CALCULATED`. Настройки берутся из `trading.feature_engineering.*` (`ema`, `volume`, `volatility`, `liquidity`, `enable_new_metrics`) и из `trading.market_data.macro_sync`.
- **RiskManagement** реагирует на `EVT:FEATURES_CALCULATED`, использует `trading.risk` (`max_daily_drawdown_pct`, `trading_allowed_thresholds.max_risk_score`, `soft_limits`), а если их нет — обращается к `system.risk`. Он рассчитывает `risk_score` и `is_trading_allowed`, затем отправляет `EVT:RISK_ASSESSMENT_COMPLETED` с этими параметрами.
- **DecisionMaking** агрегирует `EVT:FEATURES_CALCULATED`, `EVT:RISK_ASSESSMENT_COMPLETED`, `EVT:PORTFOLIO_STATE_UPDATED`, `EVT:REGIME_DETECTED`, `EVT:EXPOSURE_SUMMARY_UPDATED` (см. `listen` в `decision_making.py`). Проверяет `trading.decision` (signals, signal_threshold, risk_budgets, position_sizing, kelly, qos), `trading.mode` и `trading.instruments`, применяет QoS (symbol cooldowns, rate limits) и блокирует через `NormalizedRejectReasons`. Если решает, что можно торговать, эмитит `EVT:TRADE_INTENT_PROPOSED`.
- **ExecutionManagement / AuroraBridge**: домен `execution_management` слушает `EVT:TRADE_INTENT_PROPOSED`, но реальный мост лежит в `apps/reference/main.py`. `AuroraBridge` применяется к `EVT:TRADE_INTENT_PROPOSED`, делает QoS‑проверку, отслеживает свежесть портфеля (`position_tracking.positions_stale_ttl_sec`), публикует `EVT:INTENT_DEFERRED` / `EVT:INTENT_DROPPED` при блокировках и переводит утверждённый intent в `CMD:OPEN` (включает `order_type`, `qty`, `price`, `idempotent_key`, `price_ref`). Результат `CMD:OPEN` сразу пробрасывается в `execution_position` FSM через `AuroraBridge`.
- **ExecPos FSM** получает `CMD:OPEN`, обрабатывает `OpenFlowFSM`, `ManageFlowFSM` и `CloseFlowFSM` (см. поведение в `behavior_execpos.md`). После `DEC` команд отправляет результаты адаптеру и публикует `EVT:EXPOSURE_SUMMARY_UPDATED` после изменения портфеля (портфельный update, филл, отмена). `EVT/UPD` события маршрутизируются исключительно в `ManageFlowFSM` (смотри фильтр `else: result = manage_flow.handle(msg)` в `fsm.py`), а `CloseFlowFSM` активируется только на `CMD:CLOSE`.
- **BinanceAdapter** получает `DEC:OPEN/CLOSE/PLACE_ORDER/CANCEL_ORDER` и выполняет REST вызовы (с конфигурацией из `binance_api`, действующим `domain_configuration.execution_position.trading_mode` и `trading.execution.orders/watchdog` параметрами).

## Ключевые события между слоями

| Событие | Откуда | Куда | Что несёт |
| --- | --- | --- | --- |
| `EVT:MARKET_TICK_RECEIVED` | MarketDataConnector | FeatureEngineering | реальные bid/ask/volume/anchor / `data_source` |
| `EVT:FEATURES_CALCULATED` | FeatureEngineering | RiskManagement, DecisionMaking | словарь метрик, `symbol`, `ts` |
| `EVT:RISK_ASSESSMENT_COMPLETED` | RiskManagement | DecisionMaking | `risk_score`, `is_trading_allowed` |
| `EVT:TRADE_INTENT_PROPOSED` | DecisionMaking | ExecutionManagement / AuroraBridge | `order` + `instrument`, `side`, `idempotent_key`, вопросы позиционного sizing |
| `EVT:INTENT_DEFERRED` / `EVT:INTENT_DROPPED` | AuroraBridge | (широкий `dst="*"`) | причина QoS/портфера |
| `CMD:OPEN` | AuroraBridge | ExecPos FSM | `symbol`, `qty`, `price`, `order_type`, `price_ref`, `idempotent_key` |
| `EVT:EXPOSURE_SUMMARY_UPDATED` | ExecPos FSM | DecisionMaking | `exposure_summary`, `portfolio_state`, `timestamp` |
| `CMD:CLOSE` / `DEC:CLOSE` / `DEC:PLACE_ORDER` / `DEC:CANCEL_ORDER` | ExecPos FSM | BinanceAdapter | reduce_only close, OCO-управление, trailing |

## Конфигурации YAML по слоям (config/aurora/trading.yaml)

| Слой | Влияющие секции |
| --- | --- |
| MarketData | `binance_api`, `trading.market_data` (poll_interval_sec, websocket_streams, macro_sync anchors), `domain_configuration.market_data` |
| FeatureEngineering | `trading.feature_engineering` (`ema`, `volume`, `volatility`, `liquidity`, `enable_new_metrics`, `compute_all`), `trading.market_data.macro_sync`, `domain_configuration.feature_engineering` |
| RiskManagement | `trading.risk` (`max_daily_drawdown_pct`, `trading_allowed_thresholds`, `soft_limits`), резервные пути через `system.risk`, режим `domain_configuration.risk_management` |
| DecisionMaking | `trading.decision` (signals, signal_threshold, sizing, kelly, risk_budgets), `trading.decision.qos`, `trading.mode`, `trading.instruments`, `domain_configuration.decision_making` |
| ExecutionManagement / AuroraBridge | `trading.execution` (`manage`, `exposure`, `orders`, `watchdog`), `position_tracking.positions_stale_ttl_sec`, `domain_configuration.execution_position` |
| ExecPos FSM | те же `trading.execution.*` + `trading.exposure` (caps, per_symbol_cap_pct, max_directional_ratio), `trading.risk.soft_limits` (soft clipping), `trading.execution.manage.quick_profit`, `trading.execution.brackets`, `trading.execution.orphan_monitor`, `trading.execution.exposure` (reserve TTL) |
| BinanceAdapter | `binance_api` и `domain_configuration.execution_position.trading_mode` (чтобы знать, в каком API работают DEC). |

## Точки блокировки и risk gates

1. **RiskManagement gate**: `risk_score` сравнивается с `trading.risk.trading_allowed_thresholds.max_risk_score` (fallback 0.8) и прямо ставит `is_trading_allowed = risk_score <= threshold`. При превышении — логируется `WhyCode.RISK_SCORE_HIGH` (см. `risk_management.py`, строки 244–295).
2. **DecisionMaking QoS**: `_qos_allow` считает symbol cooldown, intent rate и exposure_block_cooldown (`trading.decision.qos`). Если блокирует, генерирует `NormalizedRejectReasons.RATE_LIMIT_EXCEEDED`/`...EXPOSURE_LIMIT_EXCEEDED`, увеличивает счётчики и вызывает `AlertManager` каждую ≥10 секунд, если доля заблокированных >20% (`testnet`) или >50% (`production`).
3. **AuroraBridge QoS / fresh portfolio**: `_is_qos_allowed` и `_is_portfolio_fresh` используют `QoS` state и `position_tracking.positions_stale_ttl_sec`; намерения откладываются (INTENT_DEFERRED) или сбрасываются (INTENT_DROPPED), пока не выполнены условия.
4. **ExposureGuard в ExecPos FSM**: `ExecPosFSM._check_exposure_fail_closed` вычисляет USD-нарионал с `price_ref` и резервирует через `ExposureGuard`. Если `exposure_guard.can_open` отказывает, `CMD:OPEN` блокируется с `ERR:OPEN` и `why="exposure_fail_closed_*"`. При закрытии/филлах `ExposureGuard` перемещает резервы, после чего ExecPos эмитит `EVT:EXPOSURE_SUMMARY_UPDATED`.
5. **Soft limits / clipping**: `ExposureGuard` читает `trading.risk.soft_limits` и может подрезать ордер (или полностью отклонить) через `SoftClipEngine`, а `trading.execution.exposure.*` задаёт TTL ожидания/reservations, левери и per_symbol_cap.

## ExecPos FSM и фильтр маршрутизации

- `ExecPosFSM.handle` смотрит `msg.verb`: только `CMD:OPEN` идёт в `OpenFlowFSM`, `CMD:CLOSE` переводит `CloseFlowFSM`, `ORDER_STATE_CHANGED` / `ORDER_CANCELLED` вызывают `_handle_cancel_event`, а **все остальные `EVT`/`UPD` идут только в `ManageFlowFSM`** (см. `else: result = manage_flow.handle(msg)` в `apps/reference/domains/execution_position/fsm.py`, строка ~1500). Это устраняет legacy-маршруты из Open/Close.
- `ManageFlowFSM` обрабатывает `EVT:PARTIAL_FILL`, `EVT:FILL`, `EVT:TRADE_EXECUTED`, `UPD:MARKET_DATA`, `EVT:ORDER_UPDATED` (SL/TP) и выдаёт `DEC:ADJUST`, `DEC:PLACE_ORDER`, `DEC:CANCEL_ORDER`, `DEC:CLOSE`. `CloseFlowFSM` активируется исключительно вручную (`CMD:CLOSE`), то есть никакие EVT/UPD не дёргают `CloseFlowFSM`.
- После каждого изменения портфеля ExecPos публикует `EVT:EXPOSURE_SUMMARY_UPDATED`, который раз в DecisionMaking обновляет `_exposure_cache` до очередной проверки интента. Это замыкает картинку: `DecisionMaking` смотрит на `ExecPos` summary, `AuroraBridge` проверяет `position_tracking`, затем `OpenFlow` → Manage → адаптер.

