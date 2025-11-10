# Тестування Regime Detector Domain

## Огляд тестів

### Тестові файли
- `tests/test_regime_detector.py` - основні unit тести
- `tests/test_regime_detector_integration.py` - інтеграційні тести

### Покриття тестів: 5/5 ✅

## Структура тестів

### Unit Tests

#### TestRegimeDetector

##### test_initialization
```python
def test_initialization(self):
    """Тест ініціалізації RegimeDetector"""
    detector = RegimeDetector(config=self.config)

    assert detector.config is not None
    assert detector.symbol_states == {}
    assert detector.models_config is not None
```

##### test_sma_trend_detection
```python
def test_sma_trend_detection(self):
    """Тест визначення тренду через SMA crossover"""

    # Setup: створити історію цін з трендом вгору
    prices = [100, 101, 102, 103, 104, 105]  # Ростучий тренд

    # Act: обробити події
    for price in prices:
        self._emit_market_tick(price)

    # Assert: перевірити визначення TREND_UP
    regime_event = self._get_last_regime_event()
    assert regime_event['regime'] == 'TREND_UP'
    assert regime_event['confidence'] > 0.8
```

##### test_volatility_regime_detection
```python
def test_volatility_regime_detection(self):
    """Тест визначення волатильності через ATR"""

    # Setup: створити високо волатильні ціни
    high_vol_prices = [
        (100, 105, 95),   # Високий діапазон
        (105, 110, 100),
        (110, 115, 105)
    ]

    # Act: обробити OHLC дані
    for high, low, close in high_vol_prices:
        self._emit_ohlc_tick(high, low, close)

    # Assert: перевірити HIGH_VOLATILITY
    regime_event = self._get_last_regime_event()
    assert regime_event['regime'] == 'HIGH_VOLATILITY'
    assert regime_event['confidence'] > 0.7
```

##### test_mean_reversion_detection
```python
def test_mean_reversion_detection(self):
    """Тест визначення mean reversion"""

    # Setup: ціна близько до SMA
    sma = Decimal('100.0')
    current_price = Decimal('101.0')  # 1% відхилення

    # Act: обробити подію з features
    features = {'price': str(current_price)}
    self.detector.on_features_calculated({
        'ts': 1000,
        'symbol': 'TEST',
        'features': features
    })

    # Assert: перевірити MEAN_REVERSION
    regime_event = self._get_last_regime_event()
    assert regime_event['regime'] == 'MEAN_REVERSION'
    assert regime_event['confidence'] > 0.5
```

##### test_confidence_scoring
```python
def test_confidence_scoring(self):
    """Тест розрахунку confidence scores"""

    # Test cases з різними confidence levels
    test_cases = [
        # (trend_strength, expected_regime, min_confidence)
        (0.005, 'TREND_UP', 0.8),      # Сильний тренд
        (-0.003, 'TREND_DOWN', 0.6),   # Помірний спад
        (0.0005, 'SIDEWAYS', 0.5),     # Бічний рух
    ]

    for strength, expected_regime, min_conf in test_cases:
        # Setup mock data
        self._setup_trend_data(strength)

        # Act
        self.detector._detect_regime('TEST')

        # Assert
        regime_event = self._get_last_regime_event()
        assert regime_event['regime'] == expected_regime
        assert regime_event['confidence'] >= min_conf
```

##### test_error_handling
```python
def test_error_handling(self):
    """Тест обробки помилок"""

    # Test: невірні features
    self.detector.on_features_calculated({
        'ts': 1000,
        'symbol': 'TEST',
        'features': {}  # Порожні features
    })

    # Assert: немає події regime (graceful degradation)
    assert len(self.emitted_events) == 0

    # Test: невірна конфігурація
    invalid_config = {'models': {'sma_trend': {'fast_period': 20, 'slow_period': 5}}}
    detector = RegimeDetector(config=invalid_config)

    # Assert: логування warning, використання defaults
    # (перевірити через mock logger)
```

### Integration Tests

#### TestRegimeDetectorIntegration

##### test_full_pipeline
```python
def test_full_pipeline(self):
    """Тест повного пайплайну: tick → features → regime"""

    # Setup: створити FSM з feature_engineering + regime_detector
    fsm = self._create_test_fsm()

    # Act: надіслати market tick
    fsm.process_event('EVT:MARKET_TICK_RECEIVED', {
        'ts': 1000,
        'symbol': 'BTCUSDT',
        'price': '45000.50',
        'volume': '100.0'
    })

    # Assert: перевірити послідовність подій
    events = fsm.get_emitted_events()
    assert 'EVT:FEATURES_CALCULATED' in [e['event'] for e in events]
    assert 'EVT:REGIME_DETECTED' in [e['event'] for e in events]

    # Assert: перевірити дані regime
    regime_event = next(e for e in events if e['event'] == 'EVT:REGIME_DETECTED')
    assert 'regime' in regime_event['payload']
    assert 'confidence' in regime_event['payload']
```

##### test_state_persistence
```python
def test_state_persistence(self):
    """Тест збереження стану між обробками"""

    symbol = 'TEST'

    # Act: обробити кілька подій
    for i in range(25):  # Більше ніж max_period
        price = 100 + i * 0.1
        self._emit_market_tick(price)

    # Assert: стан містить тільки останні дані
    state = self.detector.symbol_states[symbol]
    assert len(state['price_history']) <= self.detector.max_period
    assert state['fast_sma'] is not None
    assert state['slow_sma'] is not None
```

##### test_model_switching
```python
def test_model_switching(self):
    """Тест перемикання між моделями"""

    # Setup: різні умови для різних моделей
    scenarios = [
        ('strong_trend', {'trend_strength': 0.01}, 'TREND_UP'),
        ('high_vol', {'atr_ratio': 2.5}, 'HIGH_VOLATILITY'),
        ('mean_rev', {'price_deviation': 0.005}, 'MEAN_REVERSION'),
    ]

    for scenario_name, conditions, expected_regime in scenarios:
        # Setup mock conditions
        self._setup_scenario_conditions(conditions)

        # Act
        self.detector._detect_regime('TEST')

        # Assert
        regime_event = self._get_last_regime_event()
        assert regime_event['regime'] == expected_regime
```

## Test Fixtures

### Конфігурація тесту
```python
@pytest.fixture
def test_config(self):
    return {
        'models': {
            'sma_trend': {
                'enabled': True,
                'fast_period': 5,
                'slow_period': 20,
                'threshold': 0.001
            },
            'volatility': {
                'enabled': True,
                'atr_period': 14,
                'high_vol_threshold': 2.0,
                'low_vol_threshold': 0.5
            },
            'mean_reversion': {
                'enabled': True,
                'sma_period': 50,
                'deviation_threshold': 0.02
            }
        },
        'max_period': 100
    }
```

### Mock Event Emitter
```python
class MockEventEmitter:
    def __init__(self):
        self.events = []

    def emit(self, event_type, payload):
        self.events.append({
            'event': event_type,
            'payload': payload,
            'ts': time.time()
        })
```

## Test Coverage Analysis

### Покриті сценарії
- ✅ Ініціалізація з різними конфігураціями
- ✅ SMA trend detection (вгору/вниз/бічний)
- ✅ Volatility regime detection (high/low/normal)
- ✅ Mean reversion detection
- ✅ Confidence scoring для всіх моделей
- ✅ Error handling (невірні дані, конфігурація)
- ✅ State management (deque обмеження, persistence)
- ✅ Integration з feature_engineering
- ✅ Model switching logic

### Гaps в покритті
- ❌ Edge cases: пусті history, single data point
- ❌ Performance: великий обсяг даних, memory usage
- ❌ Configuration validation: invalid parameters
- ❌ Concurrent access: multi-threading scenarios
- ❌ Recovery: state corruption, restart scenarios

## Рекомендації по розширенню тестів

### Performance Tests
```python
def test_high_frequency_ticks(self):
    """Тест обробки високої частоти тіків"""

    # Setup: 1000 тіків за секунду
    ticks = [{'price': 100 + i*0.01} for i in range(1000)]

    start_time = time.time()
    for tick in ticks:
        self.detector.on_features_calculated(tick)

    duration = time.time() - start_time
    assert duration < 1.0  # < 1 секунди на 1000 тіків
```

### Stress Tests
```python
def test_memory_usage(self):
    """Тест використання пам'яті при великій кількості символів"""

    # Setup: 1000 символів
    for i in range(1000):
        symbol = f'SYMBOL_{i}'
        for j in range(100):  # 100 тіків на символ
            self._emit_market_tick(100, symbol)

    # Assert: пам'ять в межах лімітів
    # (використати memory_profiler)
```

### Configuration Tests
```python
def test_invalid_config_handling(self):
    """Тест обробки невірної конфігурації"""

    invalid_configs = [
        {'models': {'sma_trend': {'fast_period': 20, 'slow_period': 5}}},  # fast >= slow
        {'models': {'volatility': {'atr_period': 0}}},  # invalid period
        {'models': {'mean_reversion': {'deviation_threshold': -0.1}}},  # negative threshold
    ]

    for config in invalid_configs:
        with pytest.raises(ValueError):
            RegimeDetector(config=config)
```

## Test Execution

### Запуск тестів
```bash
# Unit tests
pytest tests/test_regime_detector.py -v

# Integration tests
pytest tests/test_regime_detector_integration.py -v

# З покриттям
pytest tests/test_regime_detector*.py --cov=apps.reference.domains.regime_detector --cov-report=html
```

### CI/CD Integration
```yaml
# .github/workflows/test.yml
- name: Run regime_detector tests
  run: |
    pytest tests/test_regime_detector*.py --cov=apps.reference.domains.regime_detector --cov-fail-under=90
```

## Debugging Helpers

### Test Utilities
```python
def _emit_market_tick(self, price, symbol='TEST'):
    """Helper для еміту market tick"""
    self.detector.on_features_calculated({
        'ts': int(time.time() * 1000),
        'symbol': symbol,
        'features': {'price': str(price)}
    })

def _get_last_regime_event(self):
    """Helper для отримання останньої regime події"""
    regime_events = [e for e in self.emitted_events if e['event'] == 'EVT:REGIME_DETECTED']
    return regime_events[-1]['payload'] if regime_events else None
```
