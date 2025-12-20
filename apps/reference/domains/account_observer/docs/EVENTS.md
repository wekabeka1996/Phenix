# Архітектура Подій - Account Observer Domain

## Огляд Подій

Домен account_observer працює як **event producer** - він споживає дані з Binance API та перетворює їх на події для решти системи. Це дозволяє асинхронно інтегрувати trade execution monitoring з іншими доменами.

## Вихідні Події (Emitted Events)

### EVT:FILL

**Частота:** При виявленні нових угод (кожні 5+ секунд опитування)

**Тригери:**
- Успішне отримання нових угод з `get_my_trades()` API
- Фільтрація дублікатів через trade ID tracking
- Обробка кореляції з внутрішніми ордерами

**Payload Структура:**
```json
{
  "symbol": "BTCUSDT",
  "side": "buy",
  "price": "45000.50",
  "quantity": "0.001",
  "ts": 1703123456789,
  "fees": "0.000001",
  "venue": "binance",
  "corr_id": "uuid-correlation-id",
  "link_fill_id": "12345678",
  "oco_group_id": "group-uuid",
  "parent_client_order_id": "parent-order-123"
}
```

**Поля Payload:**
- `symbol`: Trading pair (BTCUSDT, ETHUSDT, etc.)
- `side`: "buy" або "sell"
- `price`: Execution price як string (preserves precision)
- `quantity`: Executed quantity (positive for buy, negative for sell)
- `ts`: Timestamp в milliseconds
- `fees`: Commission amount як string
- `venue`: "binance" (future expansion to other exchanges)
- `corr_id`: Correlation ID для зв'язування з внутрішніми ордерами
- `link_fill_id`: Binance order ID
- `oco_group_id`: OCO group identifier (якщо застосовується)
- `parent_client_order_id`: Parent order identifier

**Споживачі:**
- **execution_position**: Оновлення позицій після fill
- **risk_management**: Перерахунок risk metrics
- **data_monitoring**: Логування та audit trail
- **analyzer**: Performance analysis та статистика
- **snapshot_scheduler**: Trigger для position snapshots

## Вхідні Події (Consumed Events)

Домен account_observer **не споживає події** від інших доменів. Він є джерелом даних для системи, працюючи як bridge між external exchange API та internal event system.

## FSM Стани

### Стани AccountObserver

```
┌─────────────┐
│   CREATED   │
└──────┬──────┘
       │ start()
       ▼
┌─────────────┐     _poll_loop()
│  RUNNING    │ ──────────────────┐
│             │                   │
│  ┌────────┐ │                   │
│  │ Thread │ │                   │
│  │ Active │ │                   │
│  └────────┘ │                   │
└──────┬──────┘                   │
       │ stop()                   │
       ▼                          │
┌─────────────┐                   │
│  STOPPING   │ ◄─────────────────┘
└──────┬──────┘
       │ Thread.join()
       ▼
┌─────────────┐
│   STOPPED   │
└─────────────┘
```

### Переходи Станів

| From State | Event | To State | Action |
|------------|-------|----------|--------|
| CREATED | start() | RUNNING | Створення та запуск polling thread |
| RUNNING | _poll_loop iteration | RUNNING | API polling, trade processing |
| RUNNING | stop() | STOPPING | Signal thread to stop |
| STOPPING | Thread finished | STOPPED | Cleanup resources, clear state |

## Data Flow

```
Binance API
    │
    ▼
_poll_loop() [every 5s]
    │
    ├─► get_my_trades(symbol) ──► _process_trades()
    │   │
    │   ├─► Trade ID check (duplicate prevention)
    │   │
    │   ├─► _trade_to_payload() (format conversion)
    │   │
    │   ├─► CorrelationStore lookup
    │   │
    │   └─► EVT:FILL emission
    │
    └─► FSM Event Bus ──► Other Domains
```

## Обробка Помилок

### API Помилки
- **Invalid API Key:** Immediate failure з clear error message
- **Rate Limit:** Exponential backoff, logging warnings
- **Network Timeout:** Retry з configurable timeout
- **Symbol Not Found:** Graceful skip з debug logging

### Threading Помилки
- **Thread Crash:** Automatic restart з error logging
- **Memory Issues:** Monitored через system metrics
- **Deadlock:** Timeout на thread.join() для graceful shutdown

## Корреляція

### CorrelationStore Інтеграція

**Метод:** `correlation_store.get_by_order_id(order_id)`

**Повертає:**
```json
{
  "corr_id": "uuid-correlation-id",
  "oco_group_id": "group-uuid",
  "parent_client_order_id": "parent-order-123"
}
```

**Використання в Payload:**
```python
if corr_data:
    payload["corr_id"] = corr_data["corr_id"]
    payload["link_fill_id"] = order_id
    payload["oco_group_id"] = corr_data.get("oco_group_id")
    payload["parent_client_order_id"] = corr_data.get("parent_client_order_id")
```

### Переваги Корреляції
- **End-to-End Tracing:** Від order placement до execution
- **Complex Orders:** Підтримка OCO, bracket orders
- **Audit Trail:** Complete execution history
- **Debugging:** Easy correlation між logs різних доменів

## Моніторинг

### Логування

**Structured Logging Format:**
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "domain": "account_observer",
  "event": "ORDER_STATE_CHANGED",
  "order_id": "12345678",
  "corr_id": "uuid-correlation-id",
  "symbol": "BTCUSDT",
  "side": "buy",
  "quantity": "0.001",
  "price": "45000.50",
  "trade_id": 98765432
}
```

**Log Levels:**
- **DEBUG:** API responses, detailed processing
- **INFO:** Event emissions, state changes
- **WARNING:** API errors, rate limits
- **ERROR:** Critical failures, thread crashes

### Метрики

**Prometheus Metrics:**
```python
# Counters
trades_found = Counter('account_observer_trades_found_total', 'Total trades found')
events_emitted = Counter('account_observer_events_emitted_total', 'Total events emitted')
api_errors = Counter('account_observer_api_errors_total', 'Total API errors')

# Gauges
active_symbols = Gauge('account_observer_active_symbols', 'Number of active symbols')
processed_trades = Gauge('account_observer_processed_trades', 'Number of processed trade IDs')

# Histograms
poll_duration = Histogram('account_observer_poll_duration_seconds', 'Poll duration')
api_latency = Histogram('account_observer_api_latency_seconds', 'API call latency')
```

## Контракти Даних

### Trade Payload Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://quantumtraderx.com/schemas/account_observer/fill_event.json",
  "type": "object",
  "properties": {
    "symbol": {
      "type": "string",
      "pattern": "^[A-Z]{3,}/[A-Z]{3,}$",
      "description": "Trading pair symbol"
    },
    "side": {
      "enum": ["buy", "sell"],
      "description": "Trade side"
    },
    "price": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+$",
      "description": "Execution price with precision"
    },
    "quantity": {
      "type": "string",
      "pattern": "^-?\\d+\\.\\d+$",
      "description": "Executed quantity (negative for sells)"
    },
    "ts": {
      "type": "integer",
      "minimum": 0,
      "description": "Execution timestamp in milliseconds"
    },
    "fees": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+$",
      "description": "Commission fees"
    },
    "venue": {
      "type": "string",
      "enum": ["binance"],
      "description": "Execution venue"
    },
    "corr_id": {
      "type": "string",
      "format": "uuid",
      "description": "Correlation ID for internal tracking"
    },
    "link_fill_id": {
      "type": "string",
      "description": "Exchange-specific fill identifier"
    }
  },
  "required": ["symbol", "side", "price", "quantity", "ts", "fees", "venue"]
}
```

## Тестування Подій

### Unit Тести
```python
def test_fill_event_emission():
    observer = AccountObserver(fsm=mock_fsm, config=mock_config)
    observer.start()

    # Simulate trade detection
    mock_trade = {
        "id": 12345,
        "orderId": 67890,
        "symbol": "BTCUSDT",
        "price": "45000.50",
        "qty": "0.001",
        "isBuyer": True,
        "time": 1703123456789,
        "commission": "0.000001"
    }

    observer._process_trades([mock_trade], "binance")

    # Verify event emission
    mock_fsm.emit.assert_called_with(
        "EVT:FILL",
        payload=mock_payload,
        why="Detected new user fill from Binance account."
    )
```

### Integration Тести
```python
def test_end_to_end_trade_detection():
    with mock_binance_api():
        observer = AccountObserver(fsm=mock_fsm, config=mock_config)
        observer.start()
        time.sleep(0.1)  # Allow polling

        # Verify trades were fetched and processed
        assert len(captured_events) > 0
        assert any(e['name'] == 'EVT:FILL' for e in captured_events)
```

## Безпека Подій

### Data Sanitization
- Всі числові значення конвертуються через string для precision
- Trade IDs hash для internal tracking
- Sensitive credentials не включаються в payload

### Audit Trail
- Кожна подія логується з full context
- Correlation IDs для traceability
- Timestamp verification для temporal integrity

### Rate Limiting
- API-level rate limiting через Binance limits
- Event emission throttling для запобігання overload
- Configurable poll intervals

## Продуктивність

### Оптимізації
- **Trade ID Caching:** Set-based duplicate prevention (O(1) lookup)
- **Symbol Parallelization:** Concurrent polling множини символів
- **Payload Minimization:** Only necessary fields in events
- **Memory Management:** Bounded cache для processed trades

### Performance Characteristics
- **Memory:** O(n) де n = кількість processed trade IDs
- **CPU:** Minimal processing per trade
- **Network:** 1 API call per symbol per poll interval
- **Latency:** Poll interval + API latency + processing time

---

**Версія:** 1.0
**Дата:** 9 листопада 2025 г.</content>
<filePath">c:\Users\user\Music\Phenix\apps\reference\domains\account_observer\Readme\EVENTS.md
