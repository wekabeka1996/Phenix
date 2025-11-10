# Execution Management API Dependencies

## Огляд залежностей (Dependencies Overview)

Домен `execution_management` інтегрується з vFoundation framework та використовує його компоненти для обробки подій та логування.

## Core vFoundation Dependencies

### 1. FSM (Finite State Machine)

**Модуль**: `vfoundation.core.fsm`
**Використання**: Обробка подій та управління станом

```python
# Підписка на події
fsm.listen("EVT:TRADE_INTENT_PROPOSED", self.on_trade_intent)

# Типізація
from vfoundation.core.fsm import FSM
```

**Методи FSM**:
- `listen(event_type, handler)`: Підписка на події
- `emit(event)`: Відправка подій (майбутнє використання)

### 2. Message Protocol

**Модуль**: `vfoundation.core.protocol`
**Використання**: Стандартизований формат повідомлень

```python
from vfoundation.core.protocol import Message

# Створення події
event = Message(
    op="EVT",
    verb="TRADE_INTENT_PROPOSED",
    src="decision_making",
    dst="execution_management",
    pld=trade_intent_data
)
```

**Message Fields**:
- `op`: Operation type (ASK/DEC/CMD/EVT/UPD/ERR)
- `verb`: Action verb
- `src`: Source component
- `dst`: Destination component
- `rid`: Request ID (auto-generated UUID)
- `pld`: Payload data
- `ts`: Timestamp
- `ttl_ms`: Time-to-live

### 3. Chain Logger

**Модуль**: `vfoundation.core.logging`
**Використання**: Структуроване логування з контекстом

```python
from vfoundation.core.logging import chain_logger

# Логування з контекстом
chain_logger.info(
    "Trade intent received",
    extra={
        'rid': rid,
        'event_type': 'EVT:TRADE_INTENT_PROPOSED',
        'domain': 'execution_management',
        'symbol': symbol,
        'stage': 'event_receipt'
    }
)
```

**Chain Logger Features**:
- Структуроване JSON логування
- RID tracing через компоненти
- Контекстна інформація (domain, stage, action)
- Інтеграція з розподіленим tracing

## Python Standard Library

### 1. Logging

**Використання**: Application-level логування

```python
import logging

class ExecutionManagement:
    def __init__(self, fsm, config):
        self.logger = logging.getLogger(self.__class__.__qualname__)
```

**Логування levels**:
- `DEBUG`: Детальна діагностика
- `INFO`: Інформація про обробку
- `WARNING`: Попередження
- `ERROR`: Помилки обробки

### 2. Typing

**Використання**: Type hints для кращої maintainability

```python
from typing import Dict, Any, Optional

def on_trade_intent(self, event: Message) -> None:
    # Type-safe event processing
```

## Конфігурація (Configuration)

### Hierarchical Config Access

```python
# Конфігурація з apps/reference/configs/
config = {
    "execution": {
        "management": {
            "enabled": True,
            "forward_to_execution_position": True
        }
    }
}

# Доступ до конфігурації
enabled = config["execution"]["management"]["enabled"]
```

## Тестові залежності (Test Dependencies)

### pytest Framework

```python
import pytest
from unittest.mock import MagicMock, patch

# Fixtures для тестування
@pytest.fixture
def mock_fsm():
    fsm = MagicMock()
    fsm.listen = MagicMock()
    return fsm
```

### Mock Objects

- `MagicMock`: Для FSM mocking
- `patch`: Для chain_logger mocking
- `caplog`: Для логування assertions

## Архітектурні залежності (Architectural Dependencies)

### Domain Integration

1. **decision_making**: Джерело EVT:TRADE_INTENT_PROPOSED
2. **execution_position**: Призначення для пересилання подій

### Event Flow

```
decision_making → EVT:TRADE_INTENT_PROPOSED → execution_management → execution_position
```

## Версійні залежності (Version Dependencies)

### vFoundation Compatibility

- **Message Protocol**: v1 (JSON Schema 2020-12)
- **FSM Interface**: Stable API
- **Chain Logger**: Structured logging v2

### Python Version

- **Minimum**: Python 3.9+
- **Recommended**: Python 3.11+
- **Type Hints**: Full typing support

## Майбутні залежності (Future Dependencies)

### Execution Position Integration

```python
# Майбутня інтеграція
from apps.reference.domains.execution_position import ExecutionPositionFSM

class ExecutionManagement:
    def __init__(self, fsm, config, execution_position: ExecutionPositionFSM):
        self.execution_position = execution_position
```

### Metrics & Monitoring

```python
# Майбутні метрики
from vfoundation.core.metrics import MetricsCollector

class ExecutionManagement:
    def __init__(self, fsm, config, metrics: MetricsCollector):
        self.metrics = metrics
```

### Configuration Management

```python
# Покращена конфігурація
from vfoundation.core.config import ConfigManager

class ExecutionManagement:
    def __init__(self, fsm, config_manager: ConfigManager):
        self.config = config_manager.get_domain_config('execution_management')
```

## Troubleshooting Dependencies

### Common Issues

1. **Import Errors**: Перевірка PYTHONPATH та virtual environment
2. **FSM Connection**: Верифікація FSM ініціалізації
3. **Message Validation**: Перевірка required fields (op, verb, src, dst)
4. **Logger Configuration**: Правильна настройка logging levels

### Debug Commands

```bash
# Перевірка імпортів
python -c "from vfoundation.core.protocol import Message; print('OK')"

# Перевірка FSM
python -c "from vfoundation.core.fsm import FSM; print('OK')"

# Тестування логування
python -c "from vfoundation.core.logging import chain_logger; print('OK')"
```
