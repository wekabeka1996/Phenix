# Події Risk Management Domain

## EVT:FEATURES_CALCULATED → EVT:RISK_ASSESSMENT_COMPLETED

### Опис
Основний потік оцінки ризику: від розрахунку характеристик до прийняття рішення про дозвіл торгівлі.

### Payload вхідний (FEATURES_CALCULATED)
```json
{
  "symbol": "BTCUSDT",
  "ts": "2024-01-15T10:30:00Z",
  "features": {
    "volatility_24h": 0.0234,
    "liquidity_score": 0.85,
    "trend_strength": 0.72,
    "market_regime": "bull"
  }
}
```

### Payload вихідний (RISK_ASSESSMENT_COMPLETED)
```json
{
  "symbol": "BTCUSDT",
  "ts": "2024-01-15T10:30:01Z",
  "risk_parameters": {
    "is_trading_allowed": true,
    "risk_score": 0.34,
    "max_position_size_usd": 1000,
    "circuit_breaker_active": false,
    "daily_gate_status": "OPEN"
  },
  "why": "risk_assessment_completed"
}
```

## EVT:PORTFOLIO_STATE_UPDATED

### Опис
Оновлення стану портфеля для моніторингу щоденних лімітів.

### Payload
```json
{
  "equity_free_usdt": 98500.50,
  "total_equity_usdt": 100000.00,
  "realized_pnl_usdt": -1500.00,
  "unrealized_pnl_usdt": 200.00
}
```

## EVT:DAILY_RISK_LIMIT

### Опис
Блокування торгівлі через порушення щоденних лімітів ризику.

### Payload приклади

#### Максимальне просідання
```json
{
  "reason": "DAILY_RISK_LIMIT",
  "detail": "MAX_DRAWDOWN",
  "drawdown_pct": "8.5",
  "limit_pct": "8.0",
  "equity_open_usd": "100000",
  "equity_now_usd": "91500",
  "why": "daily_drawdown_limit_exceeded"
}
```

#### Максимальні втрати
```json
{
  "reason": "DAILY_RISK_LIMIT",
  "detail": "MAX_REALIZED_LOSS",
  "realized_pnl_usd": "-300",
  "limit_usd": "250",
  "why": "daily_loss_limit_exceeded"
}
```

## Логіка оцінки ризику

### Двошарова перевірка
1. **Portfolio Level**: DailyGate перевіряє загальні ліміти
2. **Instrument Level**: RiskManagement оцінює конкретний інструмент

### Критерії дозволу
- `is_trading_allowed`: true/false
- `risk_score`: 0.0 (низький) - 1.0 (високий)
- `max_position_size_usd`: рекомендований розмір позиції
