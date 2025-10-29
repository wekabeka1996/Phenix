# Функції домену Account Observer

## Основний клас: AccountObserver

Клас `AccountObserver` реалізує моніторинг торгової активності через Binance API з автоматичною дедуплікацією та емісією подій FSM.

### Конструктор: `__init__(self, fsm: Any, config: dict[str, Any]) -> None`

Ініціалізує екземпляр AccountObserver з FSM та конфігурацією.

**Параметри:**
- `fsm: Any` - Екземпляр FSM core для емісії подій
- `config: dict[str, Any]` - Конфігурація домену з наступною структурою:
  - `trading_mode: str` - Режим роботи ('live', 'testnet', 'hybrid_*')
  - `binance_api: dict` - Конфігурація API з ключами для live/testnet
    - `live: dict` - API ключі для mainnet
      - `api_key: str` - Binance API ключ
      - `api_secret: str` - Binance API секрет
    - `testnet: dict` - API ключі для testnet
      - `api_key: str` - Testnet API ключ
      - `api_secret: str` - Testnet API секрет
  - `account_observer: dict` - Специфічна конфігурація домену
    - `poll_interval: int` - Інтервал опитування в секундах (за замовчуванням 5)
    - `symbols: list[str]` - Список символів для моніторингу (за замовчуванням ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'])
    - `trade_limit: int` - Кількість трейдів для отримання за раз (за замовчуванням 50)

**Повертає:** `None`

**Викидає:**
- `ImportError` - якщо не встановлена бібліотека python-binance
- `ValueError` - при невалідній конфігурації API ключів

**Приклад використання:**
```python
config = {
    'trading_mode': 'testnet',
    'binance_api': {
        'testnet': {
            'api_key': 'your_testnet_api_key',
            'api_secret': 'your_testnet_api_secret'
        }
    },
    'account_observer': {
        'poll_interval': 5,
        'symbols': ['BTCUSDT', 'ETHUSDT'],
        'trade_limit': 50
    }
}

observer = AccountObserver(fsm, config)
```

---

### Метод: `start(self) -> None`

Запускає фонове опитування торгової активності.

**Параметри:** Немає

**Повертає:** `None`

**Побічні ефекти:**
- Запускає daemon thread для `_poll_loop()`
- Встановлює прапор `running = True`
- Логує початок роботи

**Приклад використання:**
```python
observer.start()
# Тепер працює у фоні
```

---

### Метод: `stop(self) -> None`

Зупиняє моніторинг та graceful shutdown.

**Параметри:** Немає

**Повертає:** `None`

**Побічні ефекти:**
- Встановлює `running = False`
- Очікує завершення потоку (timeout 10 секунд)
- Логує завершення роботи
- Очищає ресурси

**Приклад використання:**
```python
observer.stop()
# Моніторинг зупинено
```

---

### Метод: `is_running(self) -> bool`

Перевіряє чи працює моніторинг.

**Параметри:** Немає

**Повертає:** `bool` - `True` якщо моніторинг активний

**Приклад використання:**
```python
if observer.is_running():
    print("Моніторинг активний")
```

---

### Приватний метод: `_poll_loop(self) -> None`

Основний цикл опитування API. Виконується у окремому потоці.

**Алгоритм:**
1. Перевіряє прапор `running`
2. Якщо активний - викликає `_poll_trades()`
3. Очікує `poll_interval` секунд
4. Повторює цикл

**Обробка помилок:**
- Логує помилки але продовжує роботу
- Не перериває цикл при одиночних помилках

---

### Приватний метод: `_poll_trades(self) -> None`

Опитує трейди для всіх символів у конфігурації.

**Алгоритм:**
1. Для кожного символу в `symbols`:
   - Викликає `_poll_symbol_trades(symbol)`
2. Агрегує статистику викликів

**Обробка помилок:**
- Продовжує з іншими символами при помилці одного
- Логує помилки для кожного символу окремо

---

### Приватний метод: `_poll_symbol_trades(self, symbol: str) -> None`

Опитує трейди для конкретного символу.

**Параметри:**
- `symbol: str` - Торгова пара (наприклад, 'BTCUSDT')

**Алгоритм:**
1. Викликає `binance_client.get_my_trades(symbol, limit=trade_limit)`
2. Фільтрує відповідь через `_process_trades()`
3. Оновлює метрики

**Обробка помилок:**
- `BinanceAPIException` - логує та повертає
- `Exception` - логує як неочікувану помилку

---

### Приватний метод: `_process_trades(self, trades: list, symbol: str) -> None`

Обробляє список трейдів для символу з дедуплікацією.

**Параметри:**
- `trades: list` - Список трейдів від Binance API
- `symbol: str` - Торгова пара

**Алгоритм:**
1. Для кожного трейду в списку:
   - Перевіряє чи `trade['id']` вже оброблений
   - Якщо ні - додає в `processed_trade_ids`
   - Конвертує через `_trade_to_payload()`
   - Емітує подію `EVT:TRADE_EXECUTED`
2. Оновлює метрики обробки

**Дедуплікація:**
- Використовує `processed_trade_ids: Set[int]`
- Перевіряє наявність перед обробкою
- Додає після успішної обробки

---

### Приватний метод: `_trade_to_payload(self, trade: dict) -> dict`

Конвертує трейд з формату Binance в payload події FSM.

**Параметри:**
- `trade: dict` - Трейд у форматі Binance API

**Повертає:** `dict` - Payload для події EVT:TRADE_EXECUTED

**Структура payload:**
```python
{
    'symbol': str,      # Торгова пара
    'side': str,        # 'buy' або 'sell'
    'price': str,       # Ціна як рядок для точності
    'quantity': str,    # Кількість (від'ємна для продажу)
    'ts': int,          # Timestamp в мілісекундах
    'fees': str,        # Комісія як рядок
    'venue': str        # 'binance'
}
```

**Конвертація:**
- `isBuyer: true` → `side: 'buy'`
- `isBuyer: false` → `side: 'sell'`
- `qty` → `quantity` (від'ємне для продажу)
- `price`, `commission` → зберігаються як рядки</content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_observer\functions.md