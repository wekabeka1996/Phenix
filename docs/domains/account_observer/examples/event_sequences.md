#  ü   ∏ ∫ ª   ¥  Ç µ   Ç æ ≤ æ ≥ æ    Ü µ Ω     ñ é  ∑    æ   ª ñ ¥ æ ≤ Ω ñ   Ç é    æ ¥ ñ π

##  ° Ü µ Ω     ñ π:  ü æ   ª ñ ¥ æ ≤ Ω ñ   Ç å  Ç   µ π ¥ ñ ≤ BTCUSDT

###  ü æ ¥ ñ è 1:  ö É   ñ ≤ ª è BTC
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

###  ü æ ¥ ñ è 2:  ü   æ ¥   ∂  á     Ç ∏ Ω ∏ BTC ( á     Ç ∫ æ ≤ ∏ π  ≤ ∏ Ö ñ ¥)
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

###  ü æ ¥ ñ è 3:  ö É   ñ ≤ ª è ETH
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

##  ° Ü µ Ω     ñ π:  í ∏   æ ∫    á     Ç æ Ç    Ç æ   ≥ ñ ≤ ª ñ

###  ® ≤ ∏ ¥ ∫      æ   ª ñ ¥ æ ≤ Ω ñ   Ç å  Ç   µ π ¥ ñ ≤
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

##  ° Ü µ Ω     ñ π:  ü æ º ∏ ª ∫ ∏  Ç    ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è

###  ü æ ¥ ñ è    ñ   ª è  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è  ∑' î ¥ Ω   Ω Ω è
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

##  ¢ µ   Ç æ ≤ ñ  ¥   Ω ñ  ¥ ª è  ¥ µ ¥ É   ª ñ ∫   Ü ñ ó

###  ü æ ≤ Ç æ   é ≤   Ω ñ  Ç   µ π ¥ ∏ ( ¥ ª è  Ç µ   Ç É ≤   Ω Ω è  ¥ µ ¥ É   ª ñ ∫   Ü ñ ó)
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

###  û á ñ ∫ É ≤   Ω ∏ π    µ ∑ É ª å Ç   Ç:
-  ü µ   à ∏ π  Ç   µ π ¥:  æ ±   æ ± ª µ Ω æ,    æ ¥ ñ è  µ º ñ Ç æ ≤   Ω  
-  î   É ≥ ∏ π  Ç   µ π ¥:      æ   É â µ Ω æ ( ¥ É ± ª ñ ∫   Ç),    æ ¥ ñ ó  Ω µ º   î
-  ¢   µ Ç ñ π  Ç   µ π ¥:  æ ±   æ ± ª µ Ω æ,    æ ¥ ñ è  µ º ñ Ç æ ≤   Ω  </content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_observer\examples\event_sequences.md
