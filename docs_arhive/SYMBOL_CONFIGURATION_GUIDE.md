# Symbol Configuration Guide

## Overview

**Важливо:** Система НЕ повинна мати жорстко закодованих символів! Всі модулі беруть символи з конфігу.

## Configuration Source

Символи визначаються в **`config/aurora/trading.yaml`**:

```yaml
trading:
  instruments:
    SOLUSDT:
      step_size: "0.01"
      min_notional: "10"
    ETHUSDT:
      step_size: "0.001"
      min_notional: "10"
```

## Використання у коді

### 1. Отримати всі символи

```python
from vfoundation.config_symbols import get_trading_symbols

symbols = get_trading_symbols()
# Result: ['SOLUSDT', 'ETHUSDT']

for symbol in symbols:
    print(f"Trading: {symbol}")
```

### 2. Отримати перший символ

```python
from vfoundation.config_symbols import get_first_symbol

symbol = get_first_symbol()
# Result: 'SOLUSDT'
```

### 3. Отримати конфіг для символу

```python
from vfoundation.config_symbols import get_symbol_config

config = get_symbol_config('SOLUSDT')
# Result: {'step_size': '0.01', 'min_notional': '10'}

step_size = config.get('step_size') if config else '0.01'
```

### 4. Валідація символу

```python
from vfoundation.config_symbols import validate_symbol

if validate_symbol('SOLUSDT'):
    print("Symbol is configured")
else:
    print("Symbol is NOT configured")
```

## Приклади

### Bridge: Live Feature Collector

**Правильно ✅**
```python
from vfoundation.config_symbols import get_trading_symbols

def main():
    symbols = get_trading_symbols()  # Читає з конфігу
    for symbol in symbols:
        collect_features(symbol)
```

**Неправильно ❌**
```python
def main():
    symbols = ["BTCUSDT", "ETHUSDT"]  # ЖОРСТКО ЗАКОДОВАНО - НЕ РОБИТИ!
    for symbol in symbols:
        collect_features(symbol)
```

### Tools: Metrics Summary

**Правильно ✅**
```python
from vfoundation.config_symbols import get_trading_symbols

def collect_metrics():
    symbols = get_trading_symbols()
    breakdown = {}
    for symbol in symbols:
        breakdown[symbol] = collect_symbol_metrics(symbol)
    return breakdown
```

### Tests: Unit Tests

**Правильно ✅**
```python
from vfoundation.config_symbols import get_first_symbol

def test_order_placement():
    symbol = get_first_symbol()
    order = place_order(symbol, "BUY", 1.0)
    assert order.symbol == symbol
```

## Як змінити символи

1. **Редагуй `config/aurora/trading.yaml`**:
   ```yaml
   instruments:
     BTCUSDT:       # Змінено с SOLUSDT
       step_size: "0.00001"
       min_notional: "10"
     ETHUSDT:
       step_size: "0.001"
       min_notional: "10"
   ```

2. **Перезавантаж процес** - всі модулі автоматично прочитають нові символи

3. **Не потрібно змінювати код** - система гнучка!

## Fallback Behavior

Якщо конфіг недоступний, система використовує fallback:
```python
["SOLUSDT", "ETHUSDT"]  # Fallback, якщо конфіг не знайдений
```

## Testing

Для тестів використовуй конфіг-символи:

```python
import pytest
from vfoundation.config_symbols import get_trading_symbols, get_first_symbol

@pytest.fixture
def test_symbol():
    """Використовує перший сконфігований символ"""
    return get_first_symbol()

def test_something(test_symbol):
    # test_symbol буде SOLUSDT з конфігу
    result = my_function(test_symbol)
    assert result is not None
```

## Перевірка: нема жорстко закодованих символів

```bash
# Пошук жорстко закодованих символів у коді
grep -r 'BTCUSDT' --include="*.py" src/
grep -r '"ETH' --include="*.py" src/
grep -r '"SOL' --include="*.py" src/

# Правильно закодовані посилання будуть ТІЛЬКИ у:
# - config_symbols.py (fallback)
# - config/aurora/trading.yaml (конфіг)
# - Documentation
```

## Миграція старого коду

**Раніше:**
```python
SYMBOL = "BTCUSDT"  # Глобальна константа

def trade():
    place_order(SYMBOL, "BUY", 1.0)
```

**Тепер:**
```python
from vfoundation.config_symbols import get_trading_symbols

def trade():
    for symbol in get_trading_symbols():
        place_order(symbol, "BUY", 1.0)
```

## Принципи

1. ✅ **Символи в конфігу** - `config/aurora/trading.yaml`
2. ✅ **Отримуй з утиліти** - `from vfoundation.config_symbols import get_trading_symbols`
3. ✅ **Без жорсткого кодування** - nikad ne hardcod!
4. ✅ **Динамічна система** - змінюємо конфіг → система адаптується
