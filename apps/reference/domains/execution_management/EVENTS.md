# Execution Management Events

## Огляд подій (Events Overview)

Домен `execution_management` обробляє події торгових намірів та координує їх виконання через систему FSM.

## Вхідні події (Input Events)

### EVT:TRADE_INTENT_PROPOSED

**Тип**: EVT (Event)
**Джерело**: decision_making domain
**Призначення**: execution_management

**Структура payload**:
```json
{
  "instrument": "BTCUSDT",
  "side": "buy|sell",
  "order": {
    "qty": "0.001",
    "price": "50000.0"
  }
}
```

**Обробка**:
1. Логування отримання події
2. Вилучення даних торгового наміру
3. Пересилання до execution_position FSM
4. Логування завершення обробки

## Вихідні події (Output Events)

### Пересилання до Execution Position

Події пересилаються до `execution_position` FSM з тими самими даними для фактичного виконання торгівлі.

## Логування подій (Event Logging)

### Chain Logging Структура

Кожна подія логується з наступною структурою:

```json
{
  "rid": "uuid-string",
  "event_type": "EVT:TRADE_INTENT_PROPOSED",
  "domain": "execution_management",
  "symbol": "BTCUSDT",
  "stage": "event_receipt|event_processing|event_forwarded",
  "handler": "on_trade_intent",
  "action": "trade_intent_received|forwarded_to_execution_position",
  "side": "buy|sell",
  "quantity": "0.001",
  "price": "50000.0"
}
```

### Стадії обробки (Processing Stages)

1. **event_receipt**: Подія отримана
2. **event_processing**: Подія обробляється, дані вилучаються
3. **event_forwarded**: Подія пересилана до execution_position

## Обробка помилок (Error Handling)

### Неправильні дані (Invalid Data)

- Відсутність обов'язкових полів обробляється з дефолтними значеннями
- Невідомий символ логується як "unknown"
- Неправильні типи даних не призводять до збоїв

### Логування помилок (Error Logging)

Помилки логується на рівні додатку:
```python
self.logger.error(f"Error processing trade intent: {str(e)}")
```

## Метрики та моніторинг (Metrics & Monitoring)

### RID Tracing

Кожна подія має унікальний RID для відстеження через всю систему.

### Таймінги (Timings)

- Обробка події: < 50ms (ціль)
- Логування: мінімальний вплив на продуктивність

## Тестування подій (Event Testing)

### Тестові сценарії (Test Scenarios)

- Повні дані торгового наміру
- Неповні дані (відсутність side/order)
- Невідомий символ
- Множинні події (RID унікальність)
- Структура логування

### Mock Events

```python
event = Message(
    op="EVT",
    verb="TRADE_INTENT_PROPOSED",
    src="decision_making",
    dst="execution_management",
    pld=trade_intent
)
```

## Інтеграція з FSM (FSM Integration)

### Підписка на події (Event Subscription)

```python
fsm.listen("EVT:TRADE_INTENT_PROPOSED", self.on_trade_intent)
```

### Пересилання подій (Event Forwarding)

Події пересилаються до execution_position FSM для виконання:
```python
# TODO: Implement actual forwarding
# execution_position_fsm.handle_trade_intent(event)
```

## Майбутні події (Future Events)

### EVT:TRADE_EXECUTION_STATUS

Зворотний зв'язок про статус виконання від execution_position.

### EVT:TRADE_CANCELLATION_REQUEST

Запити на скасування торгівельних операцій.
