# Контракти подій домену Market Data

## Вихідні події (Outbound)

### 1. EVT:MARKET_TICK_RECEIVED
**Payload Схема:**
- `symbol` (str): BTCUSDT
- `ts` (int): Біржовий таймстамп (ms).
- `bid` / `ask` (Decimal): Кращі ціни стакану.
- `bid_size` / `ask_size` (Decimal): Об'єми на вершині стакану.
- `buy_volume` / `sell_volume` (Decimal): Сумарний об'єм угод за останню ітерацію агрегатора.

### 2. EVT:BAR_CLOSED
**Payload Схема:**
- `symbol` (str): BTCUSDT
- `timeframe_sec` (int): Тривалість бару (напр. 60).
- `open`, `high`, `low`, `close` (Decimal): OHLC дані.
- `volume` (Decimal): Сумарний об'єм.
- `gap_bars_skipped` (int): Кількість порожніх барів перед цим.

### 3. EVT:ANCHOR_UPDATED
Емітується, коли ціна інструменту, позначеного як "anchor" (якор), оновлюється. Використовується для синхронізації макро-рухів.
