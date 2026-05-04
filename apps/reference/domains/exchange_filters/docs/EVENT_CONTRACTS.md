# Контракти домену Exchange Filters

## Функціональні інтерфейси
Домен не використовує асинхронну шину подій (FSM), натомість надає прямий інтерфейс для валідації.

### `validate_instruments_on_startup`
**Вхідні параметри:**
- `adapter`: Об'єкт для зв'язку з API.
- `instruments_config`: Сирий словник конфігурації.
- `mode`: Режим роботи (`live`, `testnet` тощо).

**Результат:**
- Повертає `None` при успіху.
- Викидає `FilterMismatchError` при критичних розбіжностях.

## Структура помилки `FilterMismatch`
Кожна розбіжність містить:
- `symbol`: Назва тикера.
- `field`: Поле (`step_size`, `min_qty`, `min_notional`, `tick_size`).
- `ssot_value`: Значення в проекті.
- `exchange_value`: Значення на біржі.
- `severity`: Рівень критичності (`CRITICAL`, `WARNING`).
