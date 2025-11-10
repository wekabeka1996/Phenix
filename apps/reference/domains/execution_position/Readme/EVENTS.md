# Архітектура Подій - Execution Position Domain

## Огляд Подій

Домен execution_position працює як **command processor** та **decision emitter** в event-driven архітектурі. Він споживає високорівневі команди (CMD:OPEN/CLOSE/ADJUST) та емітує детальні рішення (DEC:OPEN/CLOSE/ADJUST) після validation та risk checks.

## Вхідні Команди (Consumed Events)

### CMD:OPEN

**Тригери:**
- User-initiated position opening
- Rebalancing signals
- Strategy execution commands

**Payload Структура:**
```json
{
  "symbol": "BTCUSDT",
  "side": "BUY",
  "qty": "0.001",
  "order_type": "LIMIT",
  "price": "45000.50",
  "tif": "GTC",
  "tp_bps": 50,
  "sl_bps": 25,
  "client_order_id": "strategy_123"
}
```

**Обробка:**
1. **OpenFlowFSM** validation (guards: min_notional, qty/price steps)
2. **ExposureGuard** checks (position limits, portfolio exposure)
3. **Cooldown** verification (minimum time between orders)
4. **DEC:OPEN** emission if all guards pass

### CMD:CLOSE

**Тригери:**
- Manual position closure
- Risk management signals
- Take-profit/stop-loss triggers
- Time-based exits

**Payload Структура:**
```json
{
  "symbol": "BTCUSDT",
  "close_type": "MARKET",
  "reduce_only": true
}
```

**Обробка:**
1. **CloseFlowFSM** state verification (position exists)
2. **OrderGuardian** cleanup (cancel TP/SL orders)
3. **DEC:CLOSE** emission

### CMD:ADJUST

**Тригери:**
- Dynamic TP/SL adjustment
- Risk management updates
- Strategy parameter changes

**Payload Структура:**
```json
{
  "symbol": "BTCUSDT",
  "tp_price": "46000.00",
  "sl_price": "44000.00",
  "adjust_type": "TRAILING"
}
```

**Обробка:**
1. **ManageFlowFSM** validation
2. **Anti-2021** checks (TP/SL positioning)
3. **DEC:ADJUST** emission

## Вихідні Рішення (Emitted Events)

### DEC:OPEN

**Тригери:**
- CMD:OPEN passed all guards in OpenFlowFSM
- Position opening approved for execution

**Payload Структура:**
```json
{
  "symbol": "BTCUSDT",
  "side": "BUY",
  "qty": "0.001",
  "price": "45000.50",
  "tif": "GTC",
  "client_order_id": "exec_pos_1703123456789",
  "tp_price": "45225.25",
  "sl_price": "44625.13",
  "corr_id": "uuid-correlation-id",
  "working_type": "MARK_PRICE"
}
```

**Споживачі:**
- **execution_adapter:** Actual order placement on exchange
- **order_logger:** Audit trail recording
- **correlation_store:** Link internal/external order IDs

### DEC:CLOSE

**Тригери:**
- CMD:CLOSE processed by CloseFlowFSM
- Time-based or event-driven position closure

**Payload Структура:**
```json
{
  "symbol": "BTCUSDT",
  "close_type": "MARKET",
  "reduce_only": true,
  "client_order_id": "exec_close_1703123456789",
  "corr_id": "uuid-correlation-id"
}
```

**Споживачі:**
- **execution_adapter:** Position closure execution
- **order_guardian:** TP/SL order cleanup
- **metrics_collector:** P&L calculation triggers

### DEC:ADJUST

**Тригери:**
- CMD:ADJUST validation passed
- TP/SL level modifications approved

**Payload Структура:**
```json
{
  "symbol": "BTCUSDT",
  "tp_price": "45500.00",
  "sl_price": "44200.00",
  "adjust_type": "MODIFY",
  "client_order_id": "exec_adjust_1703123456789",
  "corr_id": "uuid-correlation-id"
}
```

**Споживачі:**
- **execution_adapter:** TP/SL order modifications
- **exposure_guard:** Risk limit updates
- **metrics_collector:** Adjustment tracking

## FSM Data Flow

```
CMD:OPEN
    │
    ▼
OpenFlowFSM
├── Guards: min_notional, qty/price validation, cooldown
├── State: IDLE → CANDIDATE → READY → EMIT_DEC_OPEN → DONE
└── Output: DEC:OPEN

CMD:CLOSE
    │
    ▼
CloseFlowFSM
├── Conditions: position exists, close triggers met
├── State: OPENED → CLOSE_COND → EMIT_DEC_CLOSE → DONE
└── Output: DEC:CLOSE

CMD:ADJUST
    │
    ▼
ManageFlowFSM
├── Validation: TP/SL positioning, anti-2021 checks
├── State: Monitor → Adjust → Emit
└── Output: DEC:ADJUST
```

## Event Processing Pipeline

### 1. Command Reception
```python
def process_command(self, cmd: Message):
    """Route command to appropriate FSM based on symbol."""
    symbol = cmd.payload["symbol"]

    if cmd.op == "CMD:OPEN":
        self._route_to_open_flow(symbol, cmd)
    elif cmd.op == "CMD:CLOSE":
        self._route_to_close_flow(symbol, cmd)
    elif cmd.op == "CMD:ADJUST":
        self._route_to_manage_flow(symbol, cmd)
```

### 2. FSM Processing
```python
def _route_to_open_flow(self, symbol: str, cmd: Message):
    """Process CMD:OPEN through OpenFlowFSM."""
    flow = self.open_flows.get(symbol)
    if not flow:
        flow = OpenFlowFSM()
        self.open_flows[symbol] = flow

    # Process through FSM states
    if flow.state == OpenState.IDLE:
        flow.candidate(cmd.payload)
        flow.state = OpenState.CANDIDATE

    if flow.state == OpenState.CANDIDATE:
        if flow.validate_guards():
            flow.state = OpenState.READY

    if flow.state == OpenState.READY:
        dec_payload = flow.prepare_decision()
        self.emit_decision("DEC:OPEN", dec_payload)
        flow.state = OpenState.DONE
```

### 3. Decision Emission
```python
def emit_decision(self, dec_type: str, payload: dict):
    """Emit validated decision to execution layer."""
    message = Message(
        op=dec_type,
        payload=payload,
        why=f"Validated {dec_type.lower()} decision from execution_position FSM"
    )

    emit_compat(
        event_name=dec_type,
        payload=payload,
        why=message.why
    )
```

## Error Handling Events

### EVT:ORDER_FAILED

**Тригери:**
- DEC:OPEN/DEC:CLOSE execution failures
- API errors, rate limits, validation failures

**Payload:**
```json
{
  "symbol": "BTCUSDT",
  "error_code": "RATE_LIMIT_EXCEEDED",
  "error_message": "Too many requests",
  "original_command": "DEC:OPEN",
  "corr_id": "uuid-correlation-id"
}
```

### EVT:GUARD_VIOLATION

**Тригери:**
- Command failed guard validation
- Risk limits exceeded, invalid parameters

**Payload:**
```json
{
  "symbol": "BTCUSDT",
  "guard_type": "MIN_NOTIONAL",
  "violated_value": 5.0,
  "required_value": 10.0,
  "original_command": "CMD:OPEN"
}
```

## Correlation & Tracking

### Correlation Integration

**Store Lookup:**
```python
# Before emitting DEC:OPEN
corr_data = self.correlation_store.get_by_command_id(cmd.id)
if corr_data:
    payload["corr_id"] = corr_data["corr_id"]
    payload["parent_client_order_id"] = corr_data.get("client_order_id")
```

**ID Generation:**
```python
# Generate execution-specific IDs
client_order_id = generate_client_order_id("exec_pos")
payload["client_order_id"] = client_order_id
```

### Audit Trail

**Event Logging:**
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "domain": "execution_position",
  "event": "DEC:OPEN",
  "symbol": "BTCUSDT",
  "corr_id": "uuid-123",
  "client_order_id": "exec_pos_1703123456789",
  "payload": {...}
}
```

## State Management

### Per-Symbol State

**FSM Registry:**
```python
self.open_flows: Dict[str, OpenFlowFSM] = {}
self.close_flows: Dict[str, CloseFlowFSM] = {}
self.manage_flows: Dict[str, ManageFlowFSM] = {}
```

**State Persistence:**
```python
def save_state(self):
    """Persist FSM states for recovery."""
    state = {
        "open_flows": {sym: flow.state for sym, flow in self.open_flows.items()},
        "close_flows": {sym: flow.state for sym, flow in self.close_flows.items()},
        "manage_flows": {sym: flow.state for sym, flow in self.manage_flows.items()}
    }
    # Save to WAL for crash recovery
```

## Performance Considerations

### Event Throughput
- **Validation Latency:** < 50ms per command
- **Decision Emission:** < 10ms per decision
- **State Transitions:** < 5ms per FSM step

### Scalability Limits
- **Concurrent Symbols:** Limited by memory (1KB per symbol)
- **Event Queue:** Bounded queue prevents memory exhaustion
- **API Rate Limits:** 10 orders/sec, 100K/day

## Testing Event Flows

### Unit Tests
```python
def test_open_command_to_decision_flow():
    """Test CMD:OPEN → DEC:OPEN full flow."""
    fsm = ExecPosFSM()

    # Send command
    cmd = Message(op="CMD:OPEN", payload=valid_open_payload)
    fsm.process_command(cmd)

    # Verify decision emitted
    assert len(captured_events) == 1
    assert captured_events[0]["op"] == "DEC:OPEN"
    assert "client_order_id" in captured_events[0]["payload"]
```

### Integration Tests
```python
def test_full_order_lifecycle():
    """Test complete order lifecycle with mocks."""
    with mock_binance_api():
        fsm = ExecPosFSM()

        # Open position
        open_cmd = Message(op="CMD:OPEN", payload=open_payload)
        fsm.process_command(open_cmd)

        # Verify DEC:OPEN emitted
        assert_decision_emitted("DEC:OPEN")

        # Simulate fill event
        fill_event = Message(op="EVT:FILL", payload=fill_payload)
        fsm.process_event(fill_event)

        # Close position
        close_cmd = Message(op="CMD:CLOSE", payload=close_payload)
        fsm.process_command(close_cmd)

        # Verify DEC:CLOSE emitted
        assert_decision_emitted("DEC:CLOSE")
```

## Monitoring & Observability

### Event Metrics

**Prometheus Counters:**
```python
commands_received = Counter('execution_position_commands_total', 'Commands received')
decisions_emitted = Counter('execution_position_decisions_total', 'Decisions emitted')
guards_violated = Counter('execution_position_guards_violated_total', 'Guard violations')
processing_errors = Counter('execution_position_errors_total', 'Processing errors')
```

**Latency Histograms:**
```python
command_processing_duration = Histogram('execution_position_command_duration_seconds', 'Command processing time')
fsm_transition_duration = Histogram('execution_position_fsm_transition_duration_seconds', 'FSM transition time')
```

### Health Checks

**Event Processing Health:**
```python
def check_event_processing_health(self) -> bool:
    """Verify event processing pipeline is functioning."""
    # Check recent command processing
    last_command_age = time.time() - self._last_command_ts
    if last_command_age > 300:  # 5 minutes
        return False

    # Check FSM states are valid
    for flows in [self.open_flows, self.close_flows, self.manage_flows]:
        for flow in flows.values():
            if flow.state not in flow.valid_states:
                return False

    return True
```

---

**Версія:** 1.0
**Дата:** 9 листопада 2025 г.</content>
<filePath">c:\Users\user\Music\Phenix\apps\reference\domains\execution_position\Readme\EVENTS.md
