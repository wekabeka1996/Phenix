# Контракти подій домену Account Balance

## Вихідні події (Outbound)

### 1. EVT:BALANCE_UPDATE_RECEIVED
Емітується при успішному отриманні залишків активів.

**Схема (Payload):**
```json
{
  "assets": [
    {
      "asset": "string (напр. USDT)",
      "balance": "string (Decimal)",
      "crossUnPnl": "string (Decimal)",
      "crossWalletBalance": "string (Decimal)",
      "updateTime": "integer (ms)"
    }
  ],
  "updateTime": "integer (ms)"
}
```
**Правила фільтрації:** До списку `assets` потрапляють лише активи, чий `balance > 0`.

---

### 2. EVT:ACCOUNT_UPDATE_RECEIVED
Емітується при успішному отриманні списку позицій. Об'єднує дані про позиції з даними про загальний баланс гаманця.

**Схема (Payload):**
```json
{
  "totalWalletBalance": "string (Decimal)",
  "totalUnrealizedProfit": "string (Decimal)",
  "totalCrossWalletBalance": "string (Decimal)",
  "positions": [
    {
      "symbol": "string (напр. BTCUSDT)",
      "positionAmt": "string (Decimal)",
      "entryPrice": "string (Decimal)",
      "unRealizedProfit": "string (Decimal)",
      "leverage": "integer",
      "marginType": "string (cross/isolated)",
      "markPrice": "string (Decimal)",
      "liquidationPrice": "string (Decimal)"
    }
  ],
  "updateTime": "integer (ms)"
}
```
**Правила фільтрації:** У список `positions` потрапляють лише позиції з `abs(positionAmt) > 0`.
**Примітка:** `totalWalletBalance` та інші сумарні показники беруться з останнього успішного запиту балансу активу `USDT`.

## Вхідні події (Inbound)
*Немає.*
