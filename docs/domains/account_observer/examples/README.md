# Приклади викори� тання домену Account Observer

Ця папка мі� тить практичні приклади викори� тання домену `account_observer` для моніторингу торгової активно� ті.

## Файли прикладів

### [usage_examples.py](usage_examples.py)
Комплек� ні приклади коду Python для різних � ценаріїв викори� тання:

- **Базове викори� тання**: Ініціалізація, запу� к та зупинка моніторингу
- **Про� луховування подій**: Обробка подій `EVT:TRADE_EXECUTED`
- **Розширені можливо� ті**: Фільтрація трейдів, � тати� тика в реальному ча� і
- **Інтеграція**: Співпраця з іншими доменами (position tracking)
- **Обробка помилок**: Graceful degradation та відновлення
- **Те� тування**: Моки та інтеграційні те� ти

### [config_examples.yaml](config_examples.yaml)
Приклади конфігураційних файлів для різних � ередовищ:

- **production.yaml**: Продуктивна конфігурація з повним набором � имволів
- **testnet.yaml**: Те� това конфігурація для розробки
- **minimal.yaml**: Мінімальна конфігурація для швидкого � тарту
- **filtered.yaml**: Конфігурація з фільтрами трейдів
- **high_frequency.yaml**: Оптимізована конфігурація для ви� окої ча� тоти
- **debug.yaml**: Конфігурація для діагно� тики та налагодження

### [sample_trade_event.json](sample_trade_event.json)
Приклад події `EVT:TRADE_EXECUTED` у форматі JSON з у� іма обов'язковими полями.

### [event_sequences.md](event_sequences.md)
По� лідовно� ті подій для те� тування різних � ценаріїв:

- Нормальна по� лідовні� ть трейдів
- Ви� ока ча� тота торгівлі
- Помилки та відновлення
- Те� тування дедуплікації

## Швидкий � тарт

### 1. Базова конфігурація
```yaml
account_observer:
  trading_mode: live
  symbols: [BTCUSDT, ETHUSDT]
```

### 2. Про� тий код
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

В� і події `EVT:TRADE_EXECUTED` мі� тять � тандартизований payload:

```json
{
  "symbol": "BTCUSDT",        // Торгова пара
  "side": "buy",             // "buy" або "sell"
  "price": "50000.00",       // Ціна як рядок
  "quantity": "0.00100000",  // Кількі� ть (від'ємна для продажу)
  "ts": 1640995200000,       // Unix timestamp в мілі� екундах
  "fees": "0.00025000",      // Комі� ія як рядок
  "venue": "binance",        // Майданчик
  "trade_id": 12345,         // Унікальний ID трейду
  "order_id": 67890          // ID ордера
}
```

## Найкращі практики

### Конфігурація
- Вибирайте `poll_interval` залежно від потреб (1-10 � екунд для live, 30+ для те� тування)
- Обмежуйте кількі� ть � имволів для кращої продуктивно� ті
- Викори� товуйте `max_processed_trades` для контролю пам'яті

### Обробка помилок
- Завжди обробляйте помилки API (rate limits, network issues)
- Реалізуйте ек� поненціальну затримку при помилках
- Логуйте критичні помилки для діагно� тики

### Те� тування
- Викори� товуйте моки для ізоляції те� тів
- Те� туйте дедуплікацію з повторюваними даними
- Перевіряйте правильні� ть конвертації payload

### Продуктивні� ть
- Моніторте викори� тання пам'яті (кеш ID трейдів)
- Стежте за ча� тотою API викликів
- Оптимізуйте `trade_limit` для вашого об� ягу торгівлі

## Сумі� ні� ть

- **Python**: 3.11+
- **Binance API**: Futures API
- **vFoundation**: 1.0+
- **FSM**: Поддержка подій та observer pattern

## Дивіть� я також

- [README.md](../README.md) - Загальна інформація про домен
- [architecture.md](../architecture.md) - Архітектурні деталі
- [functions.md](../functions.md) - API функцій
- [schema.json](../schema.json) - JSON Schema
- [dictionaries.yaml](../dictionaries.yaml) - Конфігураційні � ловники</content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_observer\examples\README.md