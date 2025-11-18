# Execution Position Domain - Event Reference

## Command Events (Input)

### CMD:OPEN
Initiates position opening.

**Payload:**
```json
{
  "symbol": "BTCUSDT",
  "side": "BUY",
  "qty": "0.001",
  "price": "50000.0",
  "price_ref": "50000.0"
}
```

**Response:** DEC:OPEN

### CMD:CLOSE
Initiates position closure.

**Payload:**
```json
{
  "symbol": "BTCUSDT"
}
```

**Response:** DEC:CLOSE

### CMD:ADJUST
Adjusts position management (brackets, trailing stops).

**Payload:**
```json
{
  "symbol": "BTCUSDT",
  "action": "adjust_brackets",
  "sl_price": "45000.0",
  "tp_price": "55000.0"
}
```

## Decision Events (Output)

### DEC:OPEN
Order placement decision for position opening.

**Payload:**
```json
{
  "symbol": "BTCUSDT",
  "side": "BUY",
  "qty": "0.001",
  "order_type": "MARKET",
  "price": null,
  "newClientOrderId": "open_1234567890"
}
```

## OpenFlowFSM Lifecycle

The open-flow state machine now reflects the minimal runtime behaviour:

- **IDLE** – waiting for the next `CMD:OPEN`.
- **PROCESSING** – guards and idempotency checks are running for the current command.
- **DONE** – a `DEC:OPEN` was emitted successfully.
- **ERROR** – guard or validation failure (emits `ERR:OPEN`).

There are no intermediate `CANDIDATE/READY` stages and no `EVT:READY` / `EVT:EXECUTE` triggers. The external contract stays unchanged: `CMD:OPEN` produces either `DEC:OPEN` or `ERR:OPEN`.

### DEC:CLOSE
Order placement decision for position closure.

**Payload:**
```json
{
  "symbol": "BTCUSDT",
  "reduce_only": true
}
```

### DEC:PLACE_ORDER
Bracket order placement (SL/TP).

**Payload:**
```json
{
  "symbol": "BTCUSDT",
  "side": "SELL",
  "qty": "0.001",
  "order_type": "STOP_MARKET",
  "stopPrice": "45000.0",
  "reduceOnly": true,
  "newClientOrderId": "bracket_sl_1234567890"
}
```

### DEC:CANCEL_ORDER
Order cancellation decision.

**Payload:**
```json
{
  "orderId": "12345",
  "symbol": "BTCUSDT"
}
```

### DEC:ADJUST
Position adjustment decisions (breakeven, trailing stop).

**Payload:**
```json
{
  "rule": "breakeven",
  "elapsed_sec": 3600
}
```

## Event Events (External)

### EVT:FILL / EVT:TRADE_EXECUTED
Order fill confirmation from adapter.

**Payload:**
```json
{
  "symbol": "BTCUSDT",
  "orderId": "12345",
  "side": "BUY",
  "qty": "0.001",
  "price": "50000.0",
  "status": "FILLED"
}
```

### EVT:ORDER_STATE_CHANGED
Order status updates from adapter.

**Payload:**
```json
{
  "symbol": "BTCUSDT",
  "orderId": "12345",
  "status": "PARTIALLY_FILLED",
  "filled_qty": "0.0005"
}
```

### EVT:ACCOUNT_UPDATE_RECEIVED
Portfolio state updates.

**Payload:**
```json
{
  "balances": [...],
  "positions": [...]
}
```

## Update Events (Periodic)

### UPD:MARKET_DATA
Market price updates for trailing stops.

**Payload:**
```json
{
  "symbol": "BTCUSDT",
  "price": "51000.0",
  "ts": 1703123456789
}
```

### UPD:TICK
Timer events for time-based rules.

**Payload:**
```json
{
  "ts": 1703123456789
}
```

## Event Flow Diagrams

### Position Opening Flow
```
CMD:OPEN → ExposureGuard → DEC:OPEN → EVT:FILL → Position Tracking → Bracket Placement
```

### Position Management Flow
```
EVT:FILL → _place_brackets() → DEC:PLACE_ORDER × 2 → EVT:ORDER_UPDATED → State: BRACKETS_PLACED
```

### ManageFlowFSM Lifecycle
- **FLAT** – no active position tracked.
- **BRACKETS_PENDING** – initial fill observed, awaiting confirmation of emitted brackets.
- **BRACKETS_PLACED** – both SL/TP acknowledgements received; begin steady-state monitoring.
- **TRACKING** – steady state for trailing, breakeven, and quick-profit rules; also used after bracket placement when deduped.
- **EMIT_DEC_ADJUST** – transient state while emitting `DEC:ADJUST` / `DEC:CLOSE`, immediately returns to `TRACKING`.
- **WAIT_MODE** – temporary pause after emergency SL trigger; resumes `TRACKING` once bar-based cooldown elapses.
- **ERROR** – hydration or state restore failure; guarded by tests.

### CloseFlowFSM Lifecycle
- **IDLE** – default resting state; awaits explicit `CMD:CLOSE`.
- **CLOSING** – processing manual close command, emits `DEC:CLOSE` when guards pass.
- **DONE** – terminal acknowledgement after manual close; legacy auto-close timers no longer feed this FSM.

CloseFlowFSM більше не підписується на `EVT`/`UPD`. Автоматичні правила (`quick_profit`, trailing, emergency, hold) тепер живуть виключно в `ManageFlowFSM`, який під час роботи в `TRACKING`/`WAIT_MODE` генерує відповідні `DEC:CLOSE`.

### Position Closing Flow
```
CMD:CLOSE → DEC:CLOSE → EVT:FILL → Position Reset
Time Rules → DEC:CLOSE
```

### Risk Management Flow
```
Any Command → ExposureGuard.can_open() → BLOCK/ALLOW
Order Timeout → DEC:CANCEL_ORDER
```

## Error Handling Events

### EVT:MANAGE_SKIPPED
Emitted when position management is disabled or in cooldown.

**Payload:**
```json
{
  "symbol": "BTCUSDT",
  "reason": "auto_manage_disabled"
}
```

## Metrics Events

All metrics are collected internally and available via `get_metrics()` calls. Key metrics include:

- `fsm_open_decisions_total`
- `fsm_close_decisions_total`
- `fsm_bracket_orders_placed`
- `fsm_errors_total`
- `exposure_guard_blocks`
- `order_timeouts`</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\execution_position\EVENTS.md
