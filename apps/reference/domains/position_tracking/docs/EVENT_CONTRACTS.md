# Контракти подій домену Position Tracking

## Вихідні події (Outbound)

### 1. EVT:PORTFOLIO_STATE_UPDATED
Центральний контракт стану активів.

**Payload Схема:**

## Вхідні події (Consumed)

**Примітка:** `markPrice`, `unRealizedProfit` та похідний `unrealizedPnlPct` зберігаються, якщо authoritative position update / positionRisk payload їх надає; якщо source їх не містить, ці поля можуть бути `null`.
### 1. EVT:TRADE_EXECUTED
- `symbol`, `side` (buy/sell), `price`, `quantity`, `fees`.
- Використовується для інкрементального оновлення стану.

### 2. EVT:ACCOUNT_UPDATE_RECEIVED
- Повний зріз акаунту Binance Futures.
- Використовується для "жорсткої" синхронізації.
