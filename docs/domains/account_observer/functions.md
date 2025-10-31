# Функції домену Account Observer

## О� новний кла� : AccountObserver

Кла�  `AccountObserver` реалізує моніторинг торгової активно� ті через Binance API з автоматичною дедуплікацією та емі� ією подій FSM.

### Кон� труктор: `__init__(self, fsm: Any, config: dict[str, Any]) -> None`

Ініціалізує екземпляр AccountObserver з FSM та конфігурацією.

**Параметри:**
- `fsm: Any` - Екземпляр FSM core для емі� ії подій
- `config: dict[str, Any]` - Конфігурація домену з на� тупною � труктурою:
  - `trading_mode: str` - Режим роботи ('live', 'testnet', 'hybrid_*')
  - `binance_api: dict` - Конфігурація API з ключами для live/testnet
    - `live: dict` - API ключі для mainnet
      - `api_key: str` - Binance API ключ
      - `api_secret: str` - Binance API � екрет
    - `testnet: dict` - API ключі для testnet
      - `api_key: str` - Testnet API ключ
      - `api_secret: str` - Testnet API � екрет
  - `account_observer: dict` - Специфічна конфігурація домену
    - `poll_interval: int` - Інтервал опитування в � екундах (за замовчуванням 5)
    - `symbols: list[str]` - Спи� ок � имволів для моніторингу (за замовчуванням ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'])
    - `trade_limit: int` - Кількі� ть трейдів для отримання за раз (за замовчуванням 50)

**Повертає:** `None`

**Викидає:**
- `ImportError` - якщо не в� тановлена бібліотека python-binance
- `ValueError` - при невалідній конфігурації API ключів

**Приклад викори� тання:**
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

Запу� кає фонове опитування торгової активно� ті.

**Параметри:** Немає

**Повертає:** `None`

**Побічні ефекти:**
- Запу� кає daemon thread для `_poll_loop()`
- В� тановлює прапор `running = True`
- Логує початок роботи

**Приклад викори� тання:**
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
- В� тановлює `running = False`
- Очікує завершення потоку (timeout 10 � екунд)
- Логує завершення роботи
- Очищає ре� ур� и

**Приклад викори� тання:**
```python
observer.stop()
# Моніторинг зупинено
```

---

### Метод: `is_running(self) -> bool`

Перевіряє чи працює моніторинг.

**Параметри:** Немає

**Повертає:** `bool` - `True` якщо моніторинг активний

**Приклад викори� тання:**
```python
if observer.is_running():
    print("Моніторинг активний")
```

---

### Приватний метод: `_poll_loop(self) -> None`

О� новний цикл опитування API. Виконуєть� я у окремому потоці.

**Алгоритм:**
1. Перевіряє прапор `running`
2. Якщо активний - викликає `_poll_trades()`
3. Очікує `poll_interval` � екунд
4. Повторює цикл

**Обробка помилок:**
- Логує помилки але продовжує роботу
- Не перериває цикл при одиночних помилках

---

### Приватний метод: `_poll_trades(self) -> None`

Опитує трейди для в� іх � имволів у конфігурації.

**Алгоритм:**
1. Для кожного � имволу в `symbols`:
   - Викликає `_poll_symbol_trades(symbol)`
2. Агрегує � тати� тику викликів

**Обробка помилок:**
- Продовжує з іншими � имволами при помилці одного
- Логує помилки для кожного � имволу окремо

---

### Приватний метод: `_poll_symbol_trades(self, symbol: str) -> None`

Опитує трейди для конкретного � имволу.

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

Обробляє � пи� ок трейдів для � имволу з дедуплікацією.

**Параметри:**
- `trades: list` - Спи� ок трейдів від Binance API
- `symbol: str` - Торгова пара

**Алгоритм:**
1. Для кожного трейду в � пи� ку:
   - Перевіряє чи `trade['id']` вже оброблений
   - Якщо ні - додає в `processed_trade_ids`
   - Конвертує через `_trade_to_payload()`
   - Емітує подію `EVT:TRADE_EXECUTED`
2. Оновлює метрики обробки

**Дедуплікація:**
- Викори� товує `processed_trade_ids: Set[int]`
- Перевіряє наявні� ть перед обробкою
- Додає пі� ля у� пішної обробки

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
    'price': str,       # Ціна як рядок для точно� ті
    'quantity': str,    # Кількі� ть (від'ємна для продажу)
    'ts': int,          # Timestamp в мілі� екундах
    'fees': str,        # Комі� ія як рядок
    'venue': str        # 'binance'
}
```

**Конвертація:**
- `isBuyer: true` → `side: 'buy'`
- `isBuyer: false` → `side: 'sell'`
- `qty` → `quantity` (від'ємне для продажу)
- `price`, `commission` → зберігають� я як рядки</content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_observer\functions.md