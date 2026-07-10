# Run Configuration

```json
{
  "session_id": "session-p42n-17ef11d9",
  "model": "deepseek-v4-pro",
  "base_url": "https://api.deepseek.com",
  "symbols": [
    "ETHUSDT",
    "SOLUSDT"
  ],
  "duration_target_seconds": 14400,
  "prestart_checks": {
    "deepseek_health": "PASS",
    "binance_time": "PASS",
    "exchange_info": "PASS",
    "no_unresolved_positions": "PASS",
    "no_unresolved_orders": "PASS",
    "margin_leverage": "PASS"
  }
}
```