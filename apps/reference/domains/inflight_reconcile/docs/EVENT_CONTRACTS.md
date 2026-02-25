# Контракти домену In-Flight Reconcile

## Протоколи взаємодії
Домен використовує Python Protocols (Structural Typing) для гнучкої інтеграції з адаптерами.

### `ExchangeOrderChecker` (Protocol)
Адаптер повинен реалізувати:
- `get_order_status(symbol, client_order_id, ...)`: Повертає статус ордера з біржі.
- `get_open_orders(symbol)`: Повертає список активних ордерів.

### `CancelOrderAdapter` (Protocol)
Адаптер повинен реалізувати:
- `cancel_order(symbol, order_id)`: Для примусового скасування після Max TTL.

## Структура запису `InFlightEntry`
- `rid`: Request ID (UUID).
- `client_order_id`: Внутрішній ID ордера.
- `exchange_order_id`: ID ордера, присвоєний біржею.
- `status`: Поточний стан звірки.
- `reconcile_attempts`: Кількість спроб звернення до API.
