# Контракти подій домену Position Tracking

## Вихідні події (Outbound)

### 1. EVT:PORTFOLIO_STATE_UPDATED
Центральний контракт стану активів.

**Payload Схема:**
- `equity`: string (Decimal) — повний капітал акаунту.
- `equity_free_usdt`: string (Decimal) — вільний капітал для нових позицій.
- `realized_pnl`: string (Decimal) — накопичений прибуток/збиток.
- `unrealized_pnl`: string (Decimal) — плаваючий прибуток/збиток.
- `positions`: list[dict] — список активних позицій (`symbol`, `net_position`, `avg_entry_price`).
- `open_positions_usd`: string (Decimal) — сумарний номінал усіх позицій.
- `open_positions_margin_usd`: string (Decimal) — сумарна задіяна маржа.

## Вхідні події (Consumed)

### 1. EVT:TRADE_EXECUTED
- `symbol`, `side` (buy/sell), `price`, `quantity`, `fees`.
- Використовується для інкрементального оновлення стану.

### 2. EVT:ACCOUNT_UPDATE_RECEIVED
- Повний зріз акаунту Binance Futures.
- Використовується для "жорсткої" синхронізації.
