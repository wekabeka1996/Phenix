# Приклади використання домену Account Observer

## Базове використання

### Ініціалізація та запуск моніторингу

```python
from aurora.domains.account_observer import AccountObserver

# Конфігурація домену
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
        'symbols': ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'],
        'trade_limit': 50
    }
}

# Створення та запуск observer (fsm передається автоматично в домені)
observer = AccountObserver(fsm_instance, config)
observer.start()

print("Account Observer запущено. Моніторинг активний...")

# Робота в фоні...
# observer.stop()  # Для зупинки
```

### Прослуховування подій трейдів

```python
from aurora.core.fsm import FSM

# Налаштування FSM для отримання подій
fsm = FSM()

@fsm.on_event('EVT:TRADE_EXECUTED')
def handle_trade_executed(event):
    payload = event.payload

    print(f"Новий трейд: {payload['symbol']} {payload['side'].upper()}")
    print(f"Ціна: {payload['price']}, Кількість: {payload['quantity']}")
    print(f"Час: {payload['ts']}, Комісія: {payload['fees']}")

    # Додаткова логіка обробки трейду
    # Наприклад, оновлення P&L, перевірка умов тощо

# Запуск FSM
fsm.start()

# Account Observer буде автоматично емітувати події сюди
```

## Розширені приклади

### Моніторинг з фільтрацією

```python
class FilteredAccountObserver(AccountObserver):
    def __init__(self, config, client, min_trade_size=0.001):
        super().__init__(config, client)
        self.min_trade_size = min_trade_size

    def _process_trades(self, trades, symbol):
        filtered_trades = [
            trade for trade in trades
            if abs(float(trade['qty'])) >= self.min_trade_size
        ]

        if filtered_trades:
            print(f"Знайдено {len(filtered_trades)} значущих трейдів для {symbol}")

        super()._process_trades(filtered_trades, symbol)

# Використання з фільтром мінімального розміру
config = {
    'trading_mode': 'live',
    'symbols': ['BTCUSDT'],
    'poll_interval': 10
}

observer = FilteredAccountObserver(config, client, min_trade_size=0.01)
observer.start()
```

### Статистика трейдів в реальному часі

```python
from collections import defaultdict
import time

class TradeStatistics:
    def __init__(self):
        self.stats = defaultdict(lambda: {
            'total_trades': 0,
            'buy_trades': 0,
            'sell_trades': 0,
            'total_volume': 0.0,
            'total_fees': 0.0,
            'last_update': time.time()
        })

    def update_trade(self, payload):
        symbol = payload['symbol']
        side = payload['side']
        quantity = abs(float(payload['quantity']))
        fees = float(payload['fees'])

        stat = self.stats[symbol]
        stat['total_trades'] += 1
        stat['buy_trades' if side == 'buy' else 'sell_trades'] += 1
        stat['total_volume'] += quantity
        stat['total_fees'] += fees
        stat['last_update'] = time.time()

    def get_summary(self, symbol=None):
        if symbol:
            return self.stats[symbol]

        # Загальна статистика
        total = {
            'total_trades': sum(s['total_trades'] for s in self.stats.values()),
            'total_volume': sum(s['total_volume'] for s in self.stats.values()),
            'total_fees': sum(s['total_fees'] for s in self.stats.values()),
            'symbols_count': len(self.stats)
        }
        return total

# Використання
stats = TradeStatistics()

@fsm.on_event('EVT:TRADE_EXECUTED')
def track_statistics(event):
    stats.update_trade(event.payload)

    # Вивід статистики кожні 100 трейдів
    if stats.get_summary()['total_trades'] % 100 == 0:
        summary = stats.get_summary()
        print(f"Загальна статистика: {summary['total_trades']} трейдів, "
              f"об'єм: {summary['total_volume']:.4f}, "
              f"комісії: {summary['total_fees']:.4f}")

fsm.start()
```

### Інтеграція з position tracking

```python
class PositionAwareObserver(AccountObserver):
    def __init__(self, config, client, position_manager):
        super().__init__(config, client)
        self.position_manager = position_manager

    def _emit_trade_event(self, payload):
        # Спочатку оновлюємо позицію
        self.position_manager.update_from_trade(payload)

        # Потім емітуємо подію
        super()._emit_trade_event(payload)

# Приклад використання
position_manager = PositionManager()  # Ваш менеджер позицій

observer = PositionAwareObserver(config, client, position_manager)
observer.start()
```

## Конфігураційні приклади

### Продуктивна конфігурація

```yaml
account_observer:
  trading_mode: live
  poll_interval: 3
  symbols:
    - BTCUSDT
    - ETHUSDT
    - BNBUSDT
    - ADAUSDT
    - SOLUSDT
  trade_limit: 100
  max_processed_trades: 50000
  enable_metrics: true
  log_level: INFO
```

### Тестова конфігурація

```yaml
account_observer:
  trading_mode: testnet
  poll_interval: 10
  symbols:
    - BTCUSDT
    - ETHUSDT
  trade_limit: 20
  max_processed_trades: 1000
  enable_metrics: false
  log_level: DEBUG
```

### Мінімальна конфігурація

```yaml
account_observer:
  trading_mode: live
  symbols: [BTCUSDT]
```

## Обробка помилок

### Graceful degradation при проблемах з API

```python
class ResilientAccountObserver(AccountObserver):
    def __init__(self, config, client):
        super().__init__(config, client)
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        self.backoff_time = 60  # секунди

    def _poll_symbol_trades(self, symbol):
        try:
            super()._poll_symbol_trades(symbol)
            self.consecutive_errors = 0  # Скидання лічильника
        except Exception as e:
            self.consecutive_errors += 1
            print(f"Помилка для {symbol}: {e}")

            if self.consecutive_errors >= self.max_consecutive_errors:
                print(f"Забагато помилок для {symbol}, пауза {self.backoff_time}с")
                time.sleep(self.backoff_time)
                self.consecutive_errors = 0

# Використання
observer = ResilientAccountObserver(config, client)
observer.start()
```

### Моніторинг здоров'я

```python
def check_observer_health(observer):
    """Перевірка здоров'я Account Observer"""

    health_status = {
        'is_running': observer.is_running(),
        'cached_trades': len(observer.processed_trade_ids),
        'config_valid': True,  # Тут можна додати валідацію
        'last_api_call': getattr(observer, 'last_api_call', None)
    }

    # Перевірка граничних значень
    if health_status['cached_trades'] > observer.config.get('max_processed_trades', 10000) * 0.9:
        print("WARNING: Кеш трейдів майже повний")

    if not health_status['is_running']:
        print("ERROR: Observer не працює")

    return health_status

# Періодична перевірка
import schedule

def health_check_job():
    health = check_observer_health(observer)
    print(f"Статус здоров'я: {health}")

schedule.every(5).minutes.do(health_check_job)
```

## Тестування

### Мок для тестування

```python
from unittest.mock import Mock, MagicMock

def create_mock_observer():
    """Створює мок AccountObserver для тестування"""

    # Мок конфігурації
    config = {
        'trading_mode': 'testnet',
        'symbols': ['BTCUSDT'],
        'poll_interval': 1
    }

    # Мок клієнта Binance
    mock_client = Mock()
    mock_client.get_my_trades.return_value = [
        {
            'symbol': 'BTCUSDT',
            'id': 12345,
            'orderId': 67890,
            'price': '50000.00',
            'qty': '0.001',
            'quoteQty': '50.00',
            'commission': '0.00025',
            'commissionAsset': 'BNB',
            'time': 1640995200000,
            'isBuyer': True,
            'isMaker': True,
            'isBestMatch': True
        }
    ]

    # Створення observer з моками
    observer = AccountObserver(config, mock_client)

    # Мок FSM для тестування подій
    observer.fsm = Mock()
    observer.fsm.emit = Mock()

    return observer

# Використання в тестах
def test_trade_processing():
    observer = create_mock_observer()

    # Симуляція отримання трейдів
    observer._poll_symbol_trades('BTCUSDT')

    # Перевірка що подія була емітована
    observer.fsm.emit.assert_called_once()
    args = observer.fsm.emit.call_args

    assert args[0][0] == 'EVT:TRADE_EXECUTED'
    payload = args[0][1]

    assert payload['symbol'] == 'BTCUSDT'
    assert payload['side'] == 'buy'
    assert payload['price'] == '50000.00'
```

### Інтеграційні тести

```python
import pytest
from aurora.domains.account_observer import AccountObserver

class TestAccountObserverIntegration:
    def test_full_trade_flow(self, mock_binance_client):
        """Тест повного потоку обробки трейдів"""

        config = {
            'trading_mode': 'live',
            'symbols': ['BTCUSDT'],
            'poll_interval': 1
        }

        observer = AccountObserver(config, mock_binance_client)

        # Запуск
        observer.start()
        time.sleep(2)  # Час на обробку

        # Перевірка що трейди оброблені
        assert len(observer.processed_trade_ids) > 0

        # Зупинка
        observer.stop()

    def test_deduplication(self, mock_binance_client):
        """Тест дедуплікації"""

        observer = create_mock_observer()

        # Перший виклик
        observer._process_trades(mock_binance_client.get_my_trades(), 'BTCUSDT')
        initial_count = len(observer.processed_trade_ids)

        # Повторний виклик з тими ж трейдами
        observer._process_trades(mock_binance_client.get_my_trades(), 'BTCUSDT')

        # Кількість оброблених не повинна змінитися
        assert len(observer.processed_trade_ids) == initial_count
```</content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_observer\examples\usage_examples.py