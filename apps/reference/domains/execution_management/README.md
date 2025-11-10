# Execution Management Domain

## Огляд (Overview)

Домен `execution_management` є центральним компонентом системи QuantumTraderX, який обробляє події `EVT:TRADE_INTENT_PROPOSED` та координує виконання торгівельних операцій між доменами `decision_making` та `execution_position`.

## Архітектура (Architecture)

### Основні компоненти (Core Components)

- **ExecutionManagement**: Головний клас, що обробляє торгові наміри
- **Event Processing**: Обробка подій EVT:TRADE_INTENT_PROPOSED
- **Chain Logging**: Структуроване логування з RID для відстеження життєвого циклу подій
- **FSM Integration**: Інтеграція з vFoundation FSM для обробки подій

### Життєвий цикл події (Event Lifecycle)

1. **Event Receipt**: Отримання події EVT:TRADE_INTENT_PROPOSED
2. **Event Processing**: Обробка торгового наміру та вилучення даних
3. **Event Forwarding**: Пересилання до execution_position FSM

## API

### ExecutionManagement

```python
class ExecutionManagement:
    def __init__(self, fsm: FSM, config: dict)
    def start(self) -> None
    def on_trade_intent(self, event: Message) -> None
```

#### Методи (Methods)

- `__init__(fsm, config)`: Ініціалізація з FSM та конфігурацією
- `start()`: Запуск компонента та підписка на події
- `on_trade_intent(event)`: Обробка торгового наміру

### Конфігурація (Configuration)

```yaml
execution:
  management:
    enabled: true
    forward_to_execution_position: true
```

## Залежності (Dependencies)

- **vFoundation**: FSM, Message протокол, chain_logger
- **Python**: logging, typing

## Події (Events)

### Вхідні події (Input Events)

- `EVT:TRADE_INTENT_PROPOSED`: Торгові наміри від decision_making домена

### Вихідні події (Output Events)

- Події пересилаються до `execution_position` FSM для виконання

## Логування (Logging)

### Chain Logging

Кожна подія логується з наступними полями:
- `rid`: Унікальний ідентифікатор запиту
- `event_type`: Тип події
- `domain`: Домен обробки
- `symbol`: Торговий інструмент
- `stage`: Стадія обробки (receipt/processing/forwarded)
- `handler`: Обробник події

### Application Logging

Додаткове логування для діагностики:
- Отримання події
- Пересилання до execution_position
- Завершення обробки

## Тестування (Testing)

Тестовий набір включає:
- Ініціалізація компонента
- Обробка подій з різними даними
- Логування та RID генерація
- Конфігурація та життєвий цикл

Запуск тестів:
```bash
pytest tests/test_execution_management.py -v
```

## Майбутні покращення (Future Enhancements)

- Реалізація фактичного пересилання до execution_position FSM
- Додавання валідації торгових намірів
- Підтримка batch обробки
- Метрики продуктивності
