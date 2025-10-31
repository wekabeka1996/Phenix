# Features Pipeline Audit Report

## Ветка: Test_MyPC (комміт: 52c5bfb)

## Карта потока

```mermaid
graph LR
    LiveBridge --> MarketDataConnector --> FeatureEngineering --> RiskManagement --> DecisionMaking
    FeatureEngineering -- EVT:FEATURES_CALCULATED --> DecisionMaking
    MarketDataConnector -- EVT:MARKET_TICK_RECEIVED --> FeatureEngineering
    RiskManagement -- EVT:RISK_ASSESSMENT_COMPLETED --> DecisionMaking
    DecisionMaking -- EVT:TRADE_INTENT_PROPOSED --> ExecutionPosition
```

## Таблиця вузлів

| Узел        | Файл  | Кла� � /Функции | Слушает | Эмитит | Ключ. поля |
| ----------- | ----- | ------------- | ------- | ------ | ---------- |
| Live Bridge | `apps/reference/domains/market_data/market_data_connector.py` | MarketDataConnector._poll_loop(), _fetch_and_emit_data() | binance REST API | EVT:MARKET_TICK_RECEIVED | `symbol, bid/ask, bid_size/ask_size, buy_volume/sell_volume, ts` |
| MarketData | `apps/reference/domains/market_data/market_data_connector.py` | MarketDataConnector._emit_market_tick() | live feed from BinanceAdapter | `EVT:MARKET_TICK_RECEIVED` | `symbol, price, bid/ask, bid_size/ask_size, buy_volume/sell_volume, ts` |
| Features | `apps/reference/domains/feature_engineering/feature_engineering.py` | FeatureEngineering.on_market_tick(), _calculate_and_emit_features() | `EVT:MARKET_TICK_RECEIVED` | `EVT:FEATURES_CALCULATED` | `obi, tfi, delta_price, absorption, price, ts` |
| Risk | `apps/reference/domains/risk_management/risk_management.py` | RiskManagement.on_features_calculated(), _calculate_risk_parameters() | `EVT:FEATURES_CALCULATED`, `EVT:PORTFOLIO_STATE_UPDATED` | `EVT:RISK_ASSESSMENT_COMPLETED` | `is_trading_allowed, risk_score` |
| Decision | `apps/reference/domains/decision_making/decision_making.py` | DecisionMaking.on_features(), on_risk(), _make_decision_for_symbol() | `features+risk+portfolio` | `EVT:TRADE_INTENT_PROPOSED` | `symbol, side, qty, price_ref, order` |

## Причини `features=False` у проекті

З аналізу коду DecisionMaking, `features=False` виникає коли:

1. **Немає EVT:FEATURES_CALCULATED** для � имвола - DecisionMaking чекає на `on_features()` виклик
2. **Немає EVT:RISK_ASSESSMENT_COMPLETED** для � имвола - чекає на `on_risk()` виклик
3. **Немає PORTFOLIO_STATE_UPDATED** - чекає на `on_portfolio()` виклик
4. **TTL/у� таревание** - немає явної логіки TTL, але дані можуть бути за� тарілими
5. **Неправильні підпи� ки** - домени реє� трують� я в main.py, але якщо FSM не ініціалізований правильно, події не доходять
6. **Конфігурація � имволів** - MarketDataConnector має `symbols_to_track: ["BTCUSDT", "ETHUSDT"]`, DecisionMaking працює з тими � амими � имволами

## Спи� ок точних функцій/� трок кода

### Live Bridge (MarketDataConnector)
- `apps/reference/domains/market_data/market_data_connector.py:125` - `_poll_loop()`
- `apps/reference/domains/market_data/market_data_connector.py:130` - `_fetch_and_emit_data()`
- `apps/reference/domains/market_data/market_data_connector.py:200` - `_emit_market_tick()`

### MarketDataConnector
- `apps/reference/domains/market_data/market_data_connector.py:200` - `_emit_market_tick()`
- `apps/reference/domains/market_data/market_data_connector.py:35` - `__init__()` - ініціалізація

### FeatureEngineering
- `apps/reference/domains/feature_engineering/feature_engineering.py:15` - `on_market_tick()`
- `apps/reference/domains/feature_engineering/feature_engineering.py:25` - `_calculate_and_emit_features()`
- `apps/reference/domains/feature_engineering/feature_engineering.py:10` - `__init__()` - підпи� ка на події

### RiskManagement
- `apps/reference/domains/risk_management/risk_management.py:45` - `on_features_calculated()`
- `apps/reference/domains/risk_management/risk_management.py:75` - `_calculate_risk_parameters()`
- `apps/reference/domains/risk_management/risk_management.py:25` - `__init__()` - підпи� ка на події

### DecisionMaking
- `apps/reference/domains/decision_making/decision_making.py:150` - `on_features()`
- `apps/reference/domains/decision_making/decision_making.py:160` - `on_risk()`
- `apps/reference/domains/decision_making/decision_making.py:170` - `on_portfolio()`
- `apps/reference/domains/decision_making/decision_making.py:185` - `_check_and_trigger_decision_for_symbol()`
- `apps/reference/domains/decision_making/decision_making.py:200` - `_make_decision_for_symbol()`
- `apps/reference/domains/decision_making/decision_making.py:90` - `__init__()` - підпи� ка на події

## Міні-прогон тра� � ировки

Для перевірки потоку потрібно:

1. Запу� тити � и� тему з live режимом
2. Перевірити логи `logs/domain_decision_making.log` на появу `on_features()`
3. Перевірити `aurora_events.jsonl` на `EVT:FEATURES_CALCULATED`
4. Якщо події доходять, але `features=False` - перевірити � тан `symbol_states` в DecisionMaking

## Ви� новки

- **Карта потока точна** - в� і вузли знайдені та проаналізовані
- **Причини `features=False`** - переважно від� утні� ть подій від upstream доменів
- **Вузькі мі� ця** - конфігурація � имволів узгоджена, але потрібна перевірка ініціалізації FSM та реє� трації � лухачів
- **Рекомендації** - додати більше логування в MarketDataConnector та перевірити WebSocket aggregator</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\reports\features_pipeline_audit.md
