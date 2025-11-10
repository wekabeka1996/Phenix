# Тестування Feature Engineering Domain

## Загальна статистика
- **Загальна кількість тестів**: 5
- **Пройдено**: 5 ✅
- **Провалено**: 0 ❌
- **Покриття**: Основні сценарії розрахунку характеристик

## Структура тестів

### Тестові файли
- `test_feature_engineering.py` - основні тести розрахунку характеристик

### Категорії тестів

#### Basic Feature Calculation (3 пройдених)
- ✅ `test_calculate_and_emit_features_basic` - базовий розрахунок OBI, TFI, delta_price
- ✅ `test_no_symbol_no_emit` - відсутність символу не генерує події
- ✅ `test_first_tick_only_stored` - перший tick тільки зберігається

#### Edge Cases (2 пройдених)
- ✅ `test_delta_price_suppressed_when_time_diff_large` - фільтрація великих часових інтервалів
- ✅ `test_feature_engineering_consumes_tick_and_emits_features` - повний потік від tick до features

## Ключові тестові сценарії

### Базовий розрахунок характеристик
```python
# Вхідний tick
tick = {
    "symbol": "BTCUSDT",
    "ts": 1000,
    "price": "50000",
    "bid_size": "10",
    "ask_size": "5",
    "buy_volume": "3",
    "sell_volume": "1"
}

# Очікувані характеристики
expected_features = {
    "obi": "0.3333",  # (10-5)/(10+5) = 5/15 = 0.333
    "tfi": "0.5",     # (3-1)/(3+1) = 2/4 = 0.5
    "delta_price": "0",
    "liquidity_kappa": "0.8333"  # depth/(depth+depth_half)
}
```

### Фільтрація delta_price
```python
# Великий часовий інтервал
last_tick = {"ts": 1000, "price": "50000"}
current_tick = {"ts": 7000, "price": "50025"}  # 5 сек інтервал

# Результат: delta_price = 0 (фільтрується)
assert features["delta_price"] == "0"
```

### Перший tick
```python
# Перший tick для символу
tick = {"symbol": "BTCUSDT", "ts": 1000, "price": "50000"}

# Результат: тільки зберігається, події не генерується
assert no_event_emitted()
assert last_tick_data["BTCUSDT"] == tick
```

## Конфігурація тестування

### pytest налаштування
```ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
```

### Mock об'єкти
```python
# FSM mock
fsm = Mock()
fsm.emit = Mock()

# Config mock
config = {
    "trading": {
        "feature_engineering": {
            "enable_new_metrics": False,  # Для базових тестів
            "liquidity": {"depth_half": 1000}
        }
    }
}

# FeatureEngineering instance
fe = FeatureEngineering(fsm, config)
```

## Рекомендації по розширенню

### Додаткові тести
1. **Phase 1 метрики** - EMA bias, volume spike, volatility state
2. **Macro sync** - кореляції з anchor символами
3. **Edge cases** - нульові значення, extreme ranges
4. **Performance** - навантаження з множиною символів
5. **Configuration** - різні конфігурації параметрів

### Інтеграційні тести
1. **End-to-end** - від market tick до risk assessment
2. **Multi-symbol** - паралельна обробка різних символів
3. **State persistence** - відновлення стану після restart

### Property-based testing
```python
@given(
    bid_size=st.floats(min_value=0, max_value=1000),
    ask_size=st.floats(min_value=0, max_value=1000)
)
def test_obi_range(bid_size, ask_size):
    """OBI завжди в діапазоні [-1, 1]"""
    obi = calculate_obi(bid_size, ask_size)
    assert -1 <= obi <= 1
```

## Метрики якості

### Coverage цілі
- **Unit tests**: > 80% покриття функцій
- **Integration**: Ключові сценарії покриті
- **Edge cases**: Extreme values, error conditions

### Performance benchmarks
- **Latency**: < 10ms на розрахунок характеристик
- **Throughput**: > 1000 ticks/сек на символ
- **Memory**: Лінійний ріст з кількістю символів

## Дебагінг

### Поширені проблеми
1. **Нульові значення** - перевірка ділення на нуль
2. **Часові інтервали** - фільтрація великих gaps
3. **State corruption** - правильна ініціалізація per-symbol state

### Debug logging
```python
# Детальний лог розрахунків
self.logger.debug(f"OBI calc: bid={bid_size}, ask={ask_size}, depth={depth}, obi={obi}")
self.logger.debug(f"Features calculated for {symbol}: {features}")
```
