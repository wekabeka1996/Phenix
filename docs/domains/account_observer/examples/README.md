# Приклади використання домену Account Observer

Ця папка містить практичні приклади використання домену `account_observer` для моніторингу торгової активності.

## Файли прикладів

### [usage_examples.py](usage_examples.py)
Комплексні приклади коду Python для різних сценаріїв використання:

- **Базове використання**: Ініціалізація, запуск та зупинка моніторингу
- **Прослуховування подій**: Обробка подій `EVT:TRADE_EXECUTED`
- **Розширені можливості**: Фільтрація трейдів, статистика в реальному часі
- **Інтеграція**: Співпраця з іншими доменами (position tracking)
- **Обробка помилок**: Graceful degradation та відновлення
- **Тестування**: Моки та інтеграційні тести

### [config_examples.yaml](config_examples.yaml)
Приклади конфігураційних файлів для різних середовищ:

- **production.yaml**: Продуктивна конфігурація з повним набором символів
- **testnet.yaml**: Тестова конфігурація для розробки
- **minimal.yaml**: Мінімальна конфігурація для швидкого старту
- **filtered.yaml**: Конфігурація з фільтрами трейдів
- **high_frequency.yaml**: Оптимізована конфігурація для високої частоти
- **debug.yaml**: Конфігурація для діагностики та налагодження

### [sample_trade_event.json](sample_trade_event.json)
Приклад події `EVT:TRADE_EXECUTED` у форматі JSON з усіма обов'язковими полями.

### [event_sequences.md](event_sequences.md)
Послідовності подій для тестування різних сценаріїв:

- Нормальна послідовність трейдів
- Висока частота торгівлі
- Помилки та відновлення
- Тестування дедуплікації

## Швидкий старт

### 1. Базова конфігурація
```yaml
account_observer:
  trading_mode: live
  symbols: [BTCUSDT, ETHUSDT]
```

### 2. Простий код
```python
from binance.client import Client
from aurora.domains.account_observer import AccountObserver

config = {'trading_mode': 'live', 'symbols': ['BTCUSDT']}
client = Client('api_key', 'api_secret')

observer = AccountObserver(config, client)
observer.start()

# Observer працює в фоні та емітує події EVT:TRADE_EXECUTED
```

### 3. Обробка подій
```python
@fsm.on_event('EVT:TRADE_EXECUTED')
def handle_trade(event):
    payload = event.payload
    print(f"Трейд: {payload['symbol']} {payload['side']} {payload['quantity']} @ {payload['price']}")
```

## Структура payload події

Всі події `EVT:TRADE_EXECUTED` містять стандартизований payload:

```json
{
  "symbol": "BTCUSDT",        // Торгова пара
  "side": "buy",             // "buy" або "sell"
  "price": "50000.00",       // Ціна як рядок
  "quantity": "0.00100000",  // Кількість (від'ємна для продажу)
  "ts": 1640995200000,       // Unix timestamp в мілісекундах
  "fees": "0.00025000",      // Комісія як рядок
  "venue": "binance",        // Майданчик
  "trade_id": 12345,         // Унікальний ID трейду
  "order_id": 67890          // ID ордера
}
```

## Найкращі практики

### Конфігурація
- Вибирайте `poll_interval` залежно від потреб (1-10 секунд для live, 30+ для тестування)
- Обмежуйте кількість символів для кращої продуктивності
- Використовуйте `max_processed_trades` для контролю пам'яті

### Обробка помилок
- Завжди обробляйте помилки API (rate limits, network issues)
- Реалізуйте експоненціальну затримку при помилках
- Логуйте критичні помилки для діагностики

### Тестування
- Використовуйте моки для ізоляції тестів
- Тестуйте дедуплікацію з повторюваними даними
- Перевіряйте правильність конвертації payload

### Продуктивність
- Моніторте використання пам'яті (кеш ID трейдів)
- Стежте за частотою API викликів
- Оптимізуйте `trade_limit` для вашого обсягу торгівлі

## Сумісність

- **Python**: 3.11+
- **Binance API**: Futures API
- **vFoundation**: 1.0+
- **FSM**: Поддержка подій та observer pattern

## Дивіться також

- [README.md](../README.md) - Загальна інформація про домен
- [architecture.md](../architecture.md) - Архітектурні деталі
- [functions.md](../functions.md) - API функцій
- [schema.json](../schema.json) - JSON Schema
- [dictionaries.yaml](../dictionaries.yaml) - Конфігураційні словники</content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_observer\examples\README.md