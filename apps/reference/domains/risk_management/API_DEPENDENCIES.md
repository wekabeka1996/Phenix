# API Dependencies - Risk Management Domain

## Core Dependencies

### vFoundation Framework
```python
from vfoundation import FSM, EVT, CMD, DEC
from vfoundation.why import WhyCode
from vfoundation.ttl import TTLManager
```

**Використання:**
- `FSM`: Базовий клас для управління станом
- `EVT/CMD/DEC`: Типи операцій для event-driven архітектури
- `WhyCode`: Інструментація для пояснення рішень
- `TTLManager`: Управління часом життя повідомлень

### Decimal Precision
```python
from decimal import Decimal as D, InvalidOperation
```

**Використання:**
- Точні розрахунки фінансових показників
- Запобігання помилкам округлення
- Safe conversion з fallback до 0.0

### DateTime Handling
```python
from datetime import datetime, date, timezone
```

**Використання:**
- UTC часові зони для консистентності
- Щоденні ресети за розкладом
- Timestamp для event кореляції

## Configuration Dependencies

### Hybrid Config Support
```python
from typing import Dict, Any, Optional
```

**Використання:**
- Підтримка як dict, так і Pydantic конфігурацій
- Backward compatibility з legacy кодом
- Type-safe доступ до nested структур

### Safe Access Patterns
```python
# Dict access
risk_cfg = cfg.get("risk", {})
daily_cfg = risk_cfg.get("daily", {})

# Pydantic access
risk_cfg = getattr(cfg, "risk", {})
daily_cfg = getattr(risk_cfg, "daily", {})
```

## Schema Validation

### JSON Schema Contracts
- **Файл**: `schemas/risk_assessment_v1.json`
- **Версія**: JSON Schema 2020-12
- **$id**: Вимога для ідентифікації контрактів

**Payload структура:**
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "risk_assessment_v1",
  "type": "object",
  "properties": {
    "symbol": {"type": "string"},
    "ts": {"type": "string", "format": "date-time"},
    "risk_parameters": {
      "type": "object",
      "properties": {
        "is_trading_allowed": {"type": "boolean"},
        "risk_score": {"type": "number", "minimum": 0, "maximum": 1},
        "max_position_size_usd": {"type": "number"}
      }
    }
  }
}
```

## Event Flow Dependencies

### Input Events
- `EVT:FEATURES_CALCULATED`: Ініціює оцінку ризику
- `EVT:PORTFOLIO_STATE_UPDATED`: Оновлює стан портфеля

### Output Events
- `EVT:RISK_ASSESSMENT_COMPLETED`: Результат оцінки
- `EVT:DAILY_RISK_LIMIT`: Блокування через ліміти

## Testing Dependencies

### pytest Framework
```python
import pytest
from unittest.mock import Mock, patch
```

**Використання:**
- Unit testing для окремих компонентів
- Integration testing для event потоків
- Mocking для зовнішніх залежностей

### Test Data Generation
- Реалістичні фінансові сценарії
- Крайні випадки (нульові значення, максимальні ліміти)
- Property-based testing для автоматичної генерації

## Performance Considerations

### SLO Requirements
- **p95 latency**: < 50ms для оцінки ризику
- **Throughput**: Підтримка високої частоти event'ів
- **Memory**: Ефективне управління станом портфеля

### Optimization Patterns
- Lazy evaluation для складних розрахунків
- Caching для повторюваних перевірок
- Async processing для I/O операцій
