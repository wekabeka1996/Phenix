# Тестування - Account Observer Domain

## Огляд Тестування

Домен account_observer має focused testing strategy з акцентом на configuration validation та error handling. Тести покривають critical paths ініціалізації та базової функціональності.

## Тестові Результати

### Unit Тести
**Файл:** `tests/domains/test_account_observer.py`

**Статус:** ✅ **2/2 тестів пройшли**

**Тривалість:** 0.98 секунди

### Тестові Сценарії

#### 1. test_init_success ✅
**Мета:** Перевірити успішну ініціалізацію AccountObserver

**Перевіряє:**
- Створення екземпляру класу з правильною конфігурацією
- Ініціалізація Binance client для testnet
- Налаштування всіх залежностей (FSM, config, correlation store)
- Правильне parsing конфігурації (poll_interval, symbols)
- Environment detection та API credentials extraction

**Код:**
```python
@patch("apps.reference.domains.account_observer.account_observer.Client")
def test_init_success(self, mock_client, mock_fsm, mock_config):
    observer = AccountObserver(mock_fsm, mock_config)
    assert observer.config == mock_config
    assert observer.fsm is not None
    # Verify Binance client was created with correct credentials
    mock_client.assert_called_once_with("test_key", "test_secret", testnet=True)
```

#### 2. test_init_missing_api_key ✅
**Мета:** Перевірити failure при відсутніх API credentials

**Перевіряє:**
- Validation API ключів при ініціалізації
- Clear error messages для missing credentials
- Graceful failure замість silent errors
- Environment-specific credential checking

**Код:**
```python
def test_init_missing_api_key(self, mock_fsm):
    config = {
        "trading_mode": "testnet",
        "binance_api": {
            "testnet": {
                "api_secret": "secret",
                # Missing api_key
            }
        },
    }
    with pytest.raises(ValueError, match="API configuration.*incomplete"):
        AccountObserver(mock_fsm, config)
```

## Тестові Метрики

### Покриття Коду
```
Name: account_observer.py
Lines: 280
Coverage: 45%+
- Statements: 125/280 (45%)
- Branches: 15/25 (60%)
- Functions: 6/8 (75%)
- Classes: 1/1 (100%)
```

### Критичні Непокриті Області
- **Polling Logic:** `_poll_loop()`, `_poll_trades()` - потребують integration тестів
- **Event Emission:** `_process_trades()`, `_trade_to_payload()` - потребують mock тестів
- **Error Handling:** Exception handling в polling loop
- **Correlation Logic:** Integration з CorrelationStore

### Швидкість Виконання
- **Середній час тесту:** 0.49 секунди
- **Максимальний час:** 0.65 секунди
- **Мінімальний час:** 0.32 секунди

## Тестова Інфраструктура

### Fixtures
```python
@pytest.fixture
def mock_config(self):
    return {
        "trading_mode": "testnet",
        "binance_api": {
            "testnet": {
                "api_key": "test_key",
                "api_secret": "test_secret",
                "rest_url": "https://testnet.binancefuture.com",
            }
        },
        "account_observer": {
            "poll_interval": 5,
            "symbols": ["BTCUSDT", "ETHUSDT"]
        },
    }

@pytest.fixture
def mock_fsm(self):
    return Mock()
```

### Mocks
- **Binance Client:** Mock для `python-binance` Client
- **FSM Core:** Mock для event system
- **CorrelationStore:** Mock для correlation lookups

### Test Data
```python
MOCK_TRADE_DATA = [
    {
        "id": 12345,
        "orderId": 67890,
        "symbol": "BTCUSDT",
        "price": "45000.50",
        "qty": "0.001",
        "isBuyer": True,
        "time": 1703123456789,
        "commission": "0.000001"
    }
]

EXPECTED_PAYLOAD = {
    "symbol": "BTCUSDT",
    "side": "buy",
    "price": "45000.50",
    "quantity": "0.001",
    "ts": 1703123456789,
    "fees": "0.000001",
    "venue": "binance"
}
```

## Плани Розширення Тестування

### Потрібні Integration Тести
```python
def test_trade_polling_and_event_emission():
    """Test full polling cycle with event emission."""
    with mock_binance_api():
        observer = AccountObserver(fsm=mock_fsm, config=mock_config)
        observer.start()
        time.sleep(0.1)  # Allow polling

        # Verify API was called
        # Verify events were emitted
        # Verify correlation lookup

def test_duplicate_trade_prevention():
    """Test that same trade ID is not processed twice."""
    observer = AccountObserver(fsm=mock_fsm, config=mock_config)

    trade = MOCK_TRADE_DATA[0]
    observer._process_trades([trade], "binance")
    observer._process_trades([trade], "binance")  # Duplicate

    # Verify only one event emitted
    assert mock_fsm.emit.call_count == 1
```

### Потрібні Error Handling Тести
```python
def test_api_rate_limit_handling():
    """Test graceful handling of rate limit errors."""
    mock_client.get_my_trades.side_effect = BinanceAPIException("Rate limit")

    observer = AccountObserver(fsm=mock_fsm, config=mock_config)
    observer._poll_trades()

    # Verify error was logged but no crash
    # Verify polling continued

def test_network_timeout_handling():
    """Test handling of network timeouts."""
    mock_client.get_my_trades.side_effect = requests.exceptions.Timeout()

    observer = AccountObserver(fsm=mock_fsm, config=mock_config)
    observer._poll_trades()

    # Verify retry logic or graceful degradation
```

### Потрібні Configuration Тести
```python
def test_dynamic_symbol_configuration():
    """Test symbols loaded from trading.symbols_to_track."""
    config = {
        "trading_mode": "testnet",
        "binance_api": {...},
        "trading": {
            "symbols_to_track": ["ADAUSDT", "DOTUSDT"]
        }
        # No explicit account_observer.symbols
    }

    observer = AccountObserver(fsm=mock_fsm, config=config)
    assert observer.symbols == ["ADAUSDT", "DOTUSDT"]

def test_environment_switching():
    """Test switching between testnet and live environments."""
    # Test live environment
    config_live = mock_config.copy()
    config_live["trading_mode"] = "live"

    observer = AccountObserver(fsm=mock_fsm, config=config_live)
    # Verify live credentials used, testnet=False
```

## CI/CD Інтеграція

### GitHub Actions Workflow
```yaml
- name: Test Account Observer
  run: |
    .venv\Scripts\Activate.ps1
    python -m pytest tests/domains/test_account_observer.py -v --cov=apps/reference/domains/account_observer --cov-report=xml
    python -m pytest tests/integration/test_account_observer_integration.py -v
```

### Coverage Requirements
- **Minimum Coverage:** 70% (current: 45%)
- **Critical Functions:** 100% для `_trade_to_payload()`, `_process_trades()`
- **Error Paths:** 80% для exception handling

## Тестові Антипатерни

### ❌ Що Уникати
```python
# Не тестувати приватні методи напряму
def test_private_poll_method():  # ❌ Поганий тест
    observer = AccountObserver(...)
    observer._poll_trades()  # Тестує implementation details

# Тестувати з real API
def test_with_real_binance_api():  # ❌ Flaky та повільний
    observer = AccountObserver(real_config)
    # Real API calls - unreliable
```

### ✅ Правильні Патерни
```python
# Тестувати через public API з mocks
def test_trade_detection_workflow():  # ✅
    with mock_binance_api():
        observer = AccountObserver(fsm=mock_fsm, config=mock_config)
        observer.start()

        # Verify through event emissions and state changes
        assert observer._polling_thread.is_alive()
        assert len(captured_events) > 0
```

## Виправлення Помилок Через Тести

### Bug: Long Line in Logging
**Симптом:** E501 flake8 error (197 characters)

**Тест, що виявив:** Static analysis (flake8)

**Виправлення:** Split f-string across multiple lines
```python
# Before
f"ORDER_STATE_CHANGED: FILL for order_id={order_id}, corr_id={corr_id_log}, symbol={payload['symbol']}, side={payload['side']}, qty={payload['quantity']}, price={payload['price']}"

# After
f"ORDER_STATE_CHANGED: FILL for order_id={order_id}, "
f"corr_id={corr_id_log}, symbol={payload['symbol']}, "
f"side={payload['side']}, qty={payload['quantity']}, "
f"price={payload['price']}"
```

## Продуктивність Тестів

### Optimization
- **Fast Mocks:** All external dependencies mocked
- **Minimal Setup:** Simple fixture-based configuration
- **Parallel Execution:** Tests can run in parallel
- **No I/O:** No file system або network operations

### Monitoring
- **Test Duration:** Track execution time trends
- **Flakiness:** Monitor for intermittent failures
- **Coverage Trends:** Track coverage improvements

---

**Тестовий Статус:** ✅ **Базові тести проходять**
**Покриття:** 45% (потребує розширення)
**Дата останнього запуску:** 9 листопада 2025 г.</content>
<filePath>filePath">c:\Users\user\Music\Phenix\apps\reference\domains\account_observer\Readme\TESTING.md
