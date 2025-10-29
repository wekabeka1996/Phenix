# Приклад тестового сценарію з послідовністю подій

## Сценарій: Послідовність трейдів BTCUSDT

### Подія 1: Купівля BTC
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440001",
  "timestamp": 1640995200000,
  "source": "account_observer",
  "version": "1.0.0",
  "event_type": "EVT:TRADE_EXECUTED",
  "payload": {
    "symbol": "BTCUSDT",
    "side": "buy",
    "price": "50000.00",
    "quantity": "0.00100000",
    "ts": 1640995200000,
    "fees": "0.00025000",
    "venue": "binance"
  }
}
```

### Подія 2: Продаж частини BTC (частковий вихід)
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440002",
  "timestamp": 1640995260000,
  "source": "account_observer",
  "version": "1.0.0",
  "event_type": "EVT:TRADE_EXECUTED",
  "payload": {
    "symbol": "BTCUSDT",
    "side": "sell",
    "price": "50100.00",
    "quantity": "-0.00050000",
    "ts": 1640995260000,
    "fees": "0.00012500",
    "venue": "binance"
  }
}
```

### Подія 3: Купівля ETH
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440003",
  "timestamp": 1640995320000,
  "source": "account_observer",
  "version": "1.0.0",
  "event_type": "EVT:TRADE_EXECUTED",
  "payload": {
    "symbol": "ETHUSDT",
    "side": "buy",
    "price": "3000.00",
    "quantity": "0.01000000",
    "ts": 1640995320000,
    "fees": "0.00750000",
    "venue": "binance"
  }
}
```

## Сценарій: Висока частота торгівлі

### Швидка послідовність трейдів
```json
[
  {
    "event_id": "550e8400-e29b-41d4-a716-446655440010",
    "timestamp": 1640995200000,
    "source": "account_observer",
    "payload": {
      "symbol": "BTCUSDT", "side": "buy", "price": "50000.00",
      "quantity": "0.001", "fees": "0.00025", "trade_id": 12350
    }
  },
  {
    "event_id": "550e8400-e29b-41d4-a716-446655440011",
    "timestamp": 1640995201000,
    "source": "account_observer",
    "payload": {
      "symbol": "BTCUSDT", "side": "sell", "price": "50010.00",
      "quantity": "-0.001", "fees": "0.00025", "trade_id": 12351
    }
  },
  {
    "event_id": "550e8400-e29b-41d4-a716-446655440012",
    "timestamp": 1640995202000,
    "source": "account_observer",
    "payload": {
      "symbol": "ETHUSDT", "side": "buy", "price": "3000.00",
      "quantity": "0.01", "fees": "0.0075", "trade_id": 12352
    }
  }
]
```

## Сценарій: Помилки та відновлення

### Подія після відновлення з'єднання
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440020",
  "timestamp": 1640995500000,
  "source": "account_observer",
  "version": "1.0.0",
  "event_type": "EVT:TRADE_EXECUTED",
  "metadata": {
    "recovery_mode": true,
    "missed_trades": 5,
    "downtime_seconds": 300
  },
  "payload": {
    "symbol": "BTCUSDT",
    "side": "buy",
    "price": "49900.00",
    "quantity": "0.00200000",
    "ts": 1640995500000,
    "fees": "0.00050000",
    "venue": "binance",
    "trade_id": 12360,
    "order_id": 67900
  }
}
```

## Тестові дані для дедуплікації

### Повторювані трейди (для тестування дедуплікації)
```json
[
  {
    "symbol": "BTCUSDT", "id": 12345, "price": "50000.00", "qty": "0.001",
    "time": 1640995200000, "isBuyer": true
  },
  {
    "symbol": "BTCUSDT", "id": 12345, "price": "50000.00", "qty": "0.001",
    "time": 1640995200000, "isBuyer": true
  },
  {
    "symbol": "BTCUSDT", "id": 12346, "price": "50005.00", "qty": "0.001",
    "time": 1640995210000, "isBuyer": false
  }
]
```

### Очікуваний результат:
- Перший трейд: оброблено, подія емітована
- Другий трейд: пропущено (дублікат), події немає
- Третій трейд: оброблено, подія емітована</content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_observer\examples\event_sequences.md
