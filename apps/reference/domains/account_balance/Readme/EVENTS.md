# Архітектура Подій - Account Balance Domain

## Огляд Подій

Домен account_balance працює виключно через event-driven комунікацію, не маючи синхронних API викликів. Всі операції відбуваються через емісію та обробку подій FSM системи.

## Вихідні Події (Emitted Events)

### EVT:BALANCE_UPDATE_RECEIVED

**Частота:** Кожні 30 секунд (або примусово)

**Тригери:**
- Успішне отримання даних з `/fapi/v2/balance` ендпоінту
- Періодичне оновлення в `_monitor_loop()`

**Payload Структура:**
```json
{
  "assets": [
    {
      "asset": "USDT",
      "balance": "1000.50",
      "crossUnPnl": "25.30",
      "crossWalletBalance": "975.20",
      "updateTime": 1703123456789
    }
  ],
  "updateTime": 1703123456789
}
```

**Споживачі:**
- risk_strategy domain (для розрахунку margin)
- analyzer domain (для ринкового аналізу)
- data_monitoring domain (для логування)

### EVT:ACCOUNT_UPDATE_RECEIVED

**Частота:** Кожні 30 секунд (або примусово)

**Тригери:**
- Успішне отримання даних з `/fapi/v2/positionRisk` ендпоінту
- Періодичне оновлення в `_monitor_loop()`

**Payload Структура:**
```json
{
  "totalWalletBalance": "1000.50",
  "totalUnrealizedProfit": "25.30",
  "totalCrossWalletBalance": "975.20",
  "positions": [
    {
      "symbol": "BTCUSDT",
      "positionAmt": "0.001",
      "entryPrice": "45000.00",
      "unRealizedProfit": "5.50",
      "leverage": 10,
      "marginType": "cross",
      "markPrice": "45125.30",
      "liquidationPrice": "42750.00"
    }
  ],
  "updateTime": 1703123456789
}
```

**Споживачі:**
- execution_position domain (для позиційного менеджменту)
- risk_strategy domain (для risk assessment)
- analyzer domain (для P&L аналізу)

## Вхідні Події (Consumed Events)

Домен account_balance **не споживає** події від інших доменів - він є джерелом даних для всієї системи.

## FSM Стани

### Стани AccountConnector

```
┌─────────────┐
│   STOPPED   │
└──────┬──────┘
       │ start()
       ▼
┌─────────────┐     monitor_loop()
│  RUNNING    │ ──────────────────┐
│             │                   │
│  ┌────────┐ │                   │
│  │ Thread │ │                   │
│  │ Active │ │                   │
│  └────────┘ │                   │
└──────┬──────┘                   │
       │ stop()                   │
       ▼                          │
┌─────────────┐                   │
│  STOPPING   │ ◄─────────────────┘
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   STOPPED   │
└─────────────┘
```

### Переходи Станів

| From State | Event | To State | Action |
|------------|-------|----------|--------|
| STOPPED | start() | RUNNING | Запуск thread, ініціалізація API клієнта |
| RUNNING | _monitor_loop timeout | RUNNING | API polling, event emission |
| RUNNING | stop() | STOPPING | Signal thread to stop |
| STOPPING | Thread finished | STOPPED | Cleanup resources |

## Обробка Помилок

### API Помилки
- **Timeout:** Retry з exponential backoff
- **Rate Limit:** Затримка відповідно до API limits
- **Authentication:** Логування помилки, продовження з fallback даними
- **Network:** Retry з прогресивною затримкою

### Threading Помилки
- **Thread Crash:** Автоматичний restart thread
- **Memory Issues:** Graceful degradation до cached даних
- **Deadlock:** Monitoring та force restart

## Моніторинг

### Метрики
- `account_balance.api_calls_total` - загальна кількість API викликів
- `account_balance.api_errors_total` - кількість помилок API
- `account_balance.last_update_timestamp` - timestamp останнього успішного оновлення
- `account_balance.thread_health` - статус фонового thread

### Логи
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "domain": "account_balance",
  "event": "BALANCE_UPDATE_RECEIVED",
  "why": "Balance data updated from Binance API",
  "data": {
    "assets_count": 3,
    "total_balance": "1500.75"
  }
}
```

## Data Flow

```
Binance API
    │
    ▼
_monitor_loop() [every 30s]
    │
    ├─► _fetch_and_emit_account_data()
    │   │
    │   ├─► /fapi/v2/balance ──► _emit_balance_update()
    │   │                        │
    │   │                        ▼
    │   │                   EVT:BALANCE_UPDATE_RECEIVED
    │   │
    │   └─► /fapi/v2/positionRisk ─► _emit_positions_update()
    │                                 │
    │                                 ▼
    │                            EVT:ACCOUNT_UPDATE_RECEIVED
    │
    └─► FSM.emit() ──► Event Bus ──► Other Domains
```

## Контракти Даних

### Balance Asset Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "account_balance.asset",
  "type": "object",
  "properties": {
    "asset": {"type": "string", "minLength": 1},
    "balance": {"type": "string", "pattern": "^-?\\d+\\.\\d+$"},
    "crossUnPnl": {"type": "string", "pattern": "^-?\\d+\\.\\d+$"},
    "crossWalletBalance": {"type": "string", "pattern": "^-?\\d+\\.\\d+$"},
    "updateTime": {"type": "integer", "minimum": 0}
  },
  "required": ["asset", "balance", "crossUnPnl", "crossWalletBalance", "updateTime"]
}
```

### Position Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "account_balance.position",
  "type": "object",
  "properties": {
    "symbol": {"type": "string", "minLength": 1},
    "positionAmt": {"type": "string", "pattern": "^-?\\d+\\.\\d+$"},
    "entryPrice": {"type": "string", "pattern": "^\\d+\\.\\d+$"},
    "unRealizedProfit": {"type": "string", "pattern": "^-?\\d+\\.\\d+$"},
    "leverage": {"type": "integer", "minimum": 1, "maximum": 125},
    "marginType": {"enum": ["cross", "isolated"]},
    "markPrice": {"type": "string", "pattern": "^\\d+\\.\\d+$"},
    "liquidationPrice": {"type": "string", "pattern": "^\\d+\\.\\d+$"}
  },
  "required": ["symbol", "positionAmt", "entryPrice", "unRealizedProfit", "leverage", "marginType", "markPrice", "liquidationPrice"]
}
```

## Тестування Подій

### Unit Тести
```python
def test_balance_update_event_emission():
    connector = AccountConnector(fsm=mock_fsm)
    connector._emit_balance_update(mock_balance_data)

    mock_fsm.emit.assert_called_once_with(
        event_name="EVT:BALANCE_UPDATE_RECEIVED",
        payload=mock_payload,
        why="Balance data updated from Binance API."
    )
```

### Integration Тести
```python
def test_full_event_cycle():
    with mock_binance_api():
        connector.start()
        time.sleep(1)  # Allow monitoring loop to run

        # Verify events were emitted
        assert len(captured_events) >= 2  # balance + positions
        assert any(e['name'] == 'EVT:BALANCE_UPDATE_RECEIVED' for e in captured_events)
        assert any(e['name'] == 'EVT:ACCOUNT_UPDATE_RECEIVED' for e in captured_events)
```

## Безпека Подій

### Data Sanitization
- Всі числові значення конвертуються через `decimal.Decimal`
- Строки ескейпляться для JSON
- Видаляються null/undefined значення

### Audit Trail
- Кожна подія логуються з WHY поясненням
- Payload дані зберігаються для forensic analysis
- Timestamp для кожного оновлення

---

**Версія:** 1.0
**Дата:** $(date +%Y-%m-%d)</content>
<filePath">c:\Users\user\Music\Phenix\apps\reference\domains\account_balance\Readme\EVENTS.md
