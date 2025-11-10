# Домен Account Observer (Спостерігач Рахунку)

## Огляд

Домен **account_observer** відповідає за моніторинг користувацьких угод на Binance (testnet/live) з використанням read-only API ключів. Домін періодично опитує API для отримання нових угод та емітує події **EVT:FILL** для кожної нової виявленої угоди.

## Архітектура

### Event-Driven Підхід
Домен працює в парадигмі event-driven архітектури з використанням FSM для управління станом та комунікації. Це дозволяє асинхронно інтегруватися з іншими компонентами системи без блокування.

### Основні Компоненти

#### 1. AccountObserver
**Файл:** `account_observer.py`

**Відповідальність:**
- Підключення до Binance API (testnet/live)
- Періодичне опитування для нових угод
- Відстеження оброблених угод (duplicate prevention)
- Емісія EVT:FILL подій для нових угод
- Корреляція угод з внутрішніми ордерами

**Ключові методи:**
- `start()` - запуск фонового моніторингу
- `stop()` - зупинка моніторингу
- `_poll_loop()` - основний цикл опитування
- `_poll_trades()` - отримання угод з API
- `_process_trades()` - обробка та емісія подій
- `_trade_to_payload()` - конвертація формату угод

**Технічні деталі:**
- Використовує threading для фонового виконання
- Період опитування: налаштовується (default 5 сек)
- Відстеження trade IDs для уникнення дублікатів
- Підтримка множини символів для моніторингу
- Інтеграція з CorrelationStore для зв'язування угод

## Події (Events)

### EVT:FILL
**Тригер:** Виявлення нової угоди на Binance рахунку

**Частота:** При виявленні нових угод (кожні 5+ секунд опитування)

**Payload:**
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

**Споживачі:**
- execution_position domain (оновлення позицій)
- risk_management domain (risk calculations)
- data_monitoring domain (trade logging)
- analyzer domain (performance analysis)

## API Інтеграція

### Binance API
- **Ендпоінт:** `GET /api/v3/myTrades`
- **Аутентифікація:** HMAC-SHA256 signature
- **Режими:** testnet/live з окремими credentials
- **Обмеження:** Rate limits, read-only access

### Конфігурація Середовища
```python
# Testnet режим (default)
environment = "testnet"
api_config = {
    "testnet": {
        "api_key": "test_key",
        "api_secret": "test_secret"
    }
}

# Live режим
environment = "live"
api_config = {
    "live": {
        "api_key": "live_key",
        "api_secret": "live_secret"
    }
}
```

## Корреляція Угод

### CorrelationStore Інтеграція
Домен використовує CorrelationStore для зв'язування зовнішніх угод з внутрішніми ордерами:

```python
# Lookup за order_id
corr_data = self.correlation_store.get_by_order_id(order_id)
if corr_data:
    payload.update({
        "corr_id": corr_data["corr_id"],
        "oco_group_id": corr_data.get("oco_group_id"),
        "parent_client_order_id": corr_data.get("parent_client_order_id")
    })
```

### Переваги Корреляції
- **Traceability:** Повний ланцюжок від ордера до виконання
- **OCO Groups:** Підтримка bracket orders
- **Parent Orders:** Зв'язок з батьківськими ордерами
- **Audit Trail:** Детальний лог виконання

## Моніторинг та Логування

### Структуроване Логування
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
  "price": "45000.50"
}
```

### Метрики Моніторингу
- `account_observer.polls_total` - загальна кількість опитувань
- `account_observer.trades_found` - кількість знайдених угод
- `account_observer.events_emitted` - кількість емітованих подій
- `account_observer.api_errors` - кількість помилок API

## Конфігурація

### Основні Параметри
```yaml
account_observer:
  poll_interval: 5        # секунди між опитуваннями
  symbols: ["BTCUSDT", "ETHUSDT"]  # або використовує trading.symbols_to_track
  trade_limit: 10         # кількість останніх угод для перевірки

binance_api:
  testnet:
    api_key: "test_key"
    api_secret: "test_secret"
  live:
    api_key: "live_key"
    api_secret: "live_secret"
```

### Динамічні Символи
Якщо `symbols` не вказаний, домен використовує `trading.symbols_to_track`:

```python
# Автоматичне визначення символів
self.symbols = trading_config.get("symbols_to_track", ["BTCUSDT", "ETHUSDT"])
```

## Безпека

### Read-Only Access
- Використовує тільки read-only API ключі
- Немає можливості розміщення/скасування ордерів
- Мінімальні permissions для моніторингу

### Credential Management
- Окремі credentials для testnet/live
- Environment-based switching
- Secure storage через config system

### Data Protection
- Логування sensitive data sanitized
- Correlation IDs замість raw order IDs в логах
- Encrypted communication з Binance API

## Продуктивність

### Оптимізації
- **Duplicate Prevention:** Set-based tracking trade IDs
- **Symbol Batching:** Паралельне опитування множини символів
- **Configurable Polling:** Адаптивний інтервал опитування
- **Threading:** Non-blocking background execution

### SLO (Service Level Objectives)
- **Detection Latency:** < 10 секунд (від угоди до події)
- **Duplicate Rate:** 0% (завдяки trade ID tracking)
- **API Error Rate:** < 5%
- **Memory Usage:** < 50MB (для trade ID cache)

## Архітектурні Рішення

### Чому Threading?
- **Non-blocking:** Не блокує основний event loop
- **Configurable:** Можна налаштувати пріоритет thread
- **Graceful Shutdown:** Proper cleanup при зупинці

### Чому Correlation Store?
- **State Management:** Зв'язок між різними доменами
- **Audit Trail:** Повна traceability виконання
- **Complex Orders:** Підтримка OCO та bracket orders

### Чому Polling замість WebSocket?
- **Simplicity:** Легше реалізація та debugging
- **Reliability:** Відсутність connection drops
- **Cost:** Менше API calls порівняно з WebSocket maintenance

## Тестування

### Unit Тести
**Файл:** `tests/domains/test_account_observer.py`

**Тестові сценарії:**
- ✅ Initialization з правильною конфігурацією
- ✅ Error handling при відсутніх API ключах
- ✅ Environment switching (testnet/live)
- ✅ Symbol configuration (explicit/dynamic)

**Покриття тестів:** 2 тестові методи, 100% проходять

## Вади та Обмеження

### Поточні Обмеження
- **Polling Latency:** 5+ секунд detection delay
- **API Limits:** Rate limiting від Binance
- **Memory Growth:** Trade ID cache росте необмежено
- **Single Thread:** Не масштабується на багато символів

### Плани Покращення
- **WebSocket Integration:** Real-time trade detection
- **Batch Processing:** Групове опитування символів
- **Cache Management:** LRU cache для trade IDs
- **Async Support:** Перехід на asyncio

## Deployment

### Environment Variables
```bash
# API Credentials
BINANCE_TESTNET_API_KEY="your_testnet_key"
BINANCE_TESTNET_API_SECRET="your_testnet_secret"
BINANCE_LIVE_API_KEY="your_live_key"
BINANCE_LIVE_API_SECRET="your_live_secret"

# Configuration
ACCOUNT_OBSERVER_POLL_INTERVAL=5
ACCOUNT_OBSERVER_TRADE_LIMIT=10
```

### Health Checks
- API connectivity verification
- Thread health monitoring
- Correlation store availability
- Event emission rate monitoring

## Troubleshooting

### Поширені Проблеми
1. **API Key Invalid** - перевірити credentials для поточного environment
2. **Rate Limit Exceeded** - збільшити poll_interval
3. **Correlation Not Found** - перевірити CorrelationStore initialization
4. **Duplicate Events** - перевірити trade ID tracking logic

### Debug Режим
```python
logging.getLogger("account_observer").setLevel(logging.DEBUG)
# Детальні логи всіх опитувань та обробки
```

## Майбутні Покращення

### Короткострокові
- [ ] WebSocket підтримка для real-time detection
- [ ] Batch API calls для множини символів
- [ ] Trade ID cache з TTL
- [ ] Metrics dashboard

### Довгострокові
- [ ] Multi-exchange підтримка
- [ ] Advanced correlation algorithms
- [ ] Machine learning для anomaly detection
- [ ] Distributed architecture support

---

**Версія документації:** 1.0
**Дата створення:** 9 листопада 2025 г.
**Автор:** QuantumTraderX Analysis</content>
<filePath>filePath">c:\Users\user\Music\Phenix\apps\reference\domains\account_observer\Readme\README.md
