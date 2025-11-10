# Execution Position Domain - API Dependencies

## Overview

The execution_position domain integrates with multiple external systems and internal components. This document outlines all API dependencies, contracts, and integration points.

## Core Dependencies

### 1. BinanceAdapter
**Purpose**: Live order execution and market data feed

**Interface**: `apps/reference/domains/execution_position/binance_execution_adapter.py`

**Key Methods**:
```python
async def place_order(dec_msg: Message) -> Dict[str, object]
async def cancel_order(dec_msg: Message) -> Dict[str, object]
def get_status() -> str
```

**Events Emitted**:
- `EVT:TRADE_EXECUTED` - Order fills
- `EVT:ORDER_STATE_CHANGED` - Order status updates
- `EVT:ACCOUNT_UPDATE_RECEIVED` - Portfolio updates

**Configuration**:
```yaml
trading:
  mode: "testnet"  # or "live"
  api_key: "your_key"
  api_secret: "your_secret"
```

### 2. ExposureGuard
**Purpose**: Risk management and position limits

**Interface**: `apps/reference/domains/execution_position/exposure_guard.py`

**Key Methods**:
```python
def can_open(symbol: str, side: str, qty: str, price: str) -> Dict[str, Any]
def reserve(symbol: str, exposure: Decimal) -> bool
def release(symbol: str, exposure: Decimal) -> None
```

**Response Format**:
```json
{
  "allowed": true,
  "reason": "ok",
  "reserved": 50000.0
}
```

### 3. OrderTimeoutWatchdog
**Purpose**: Monitor order ACK/FILL timeouts

**Interface**: `apps/reference/domains/execution_position/watchdog.py`

**Key Methods**:
```python
def register_order(order_id: str, timeout_ms: int) -> None
def check_timeouts() -> List[str]  # Returns expired order IDs
def cancel_expired(order_id: str) -> None
```

### 4. OrderGuardian
**Purpose**: Orphan order detection and cleanup

**Interface**: `apps/reference/domains/execution_position/order_guardian.py`

**Key Methods**:
```python
async def cleanup_orphans() -> Dict[str, int]
async def reconcile_positions() -> Dict[str, Any]
def get_orphan_count() -> int
```

## Internal Dependencies

### 5. FSM Core
**Purpose**: Event routing and message passing

**Interface**: `vfoundation.core.protocol.Message`

**Key Classes**:
```python
class Message:
    op: str      # CMD, DEC, EVT, UPD
    verb: str    # OPEN, CLOSE, FILL, etc.
    src: str     # Source component
    dst: str     # Destination component
    rid: str     # Request ID
    pld: Dict    # Payload
    data_ref: List  # WHY chain
```

### 6. Metrics Aggregator
**Purpose**: Performance monitoring and alerting

**Interface**: `apps/reference/domains/execution_position/metrics_aggregator.py`

**Key Methods**:
```python
def record_event(event_type: str, data: Dict) -> None
def get_metrics() -> Dict[str, int]
def reset_counters() -> None
```

## External Integrations

### 7. Portfolio Service
**Purpose**: Position state synchronization

**Events Consumed**:
- `UPD:PORTFOLIO_STATE` - Current positions and balances

**Events Produced**:
- `EVT:POSITION_UPDATED` - Position changes

### 8. Decision Making Domain
**Purpose**: Trading signal processing

**Events Consumed**:
- `CMD:OPEN` - Position opening commands
- `CMD:CLOSE` - Position closure commands
- `CMD:ADJUST` - Position adjustment commands

### 9. Risk Strategy Domain
**Purpose**: Risk parameter coordination

**Configuration Shared**:
- Exposure limits
- Position size constraints
- Risk multipliers

## Configuration Schema

### Main Configuration Structure
```yaml
trading:
  mode: "testnet"
  execution:
    cooldown_ms: 1000
    guard_enabled: true
    watchdog:
      ack_ttl_ms: 8000
      fill_ttl_ms: 30000
    manage:
      auto_manage: true
      brackets:
        enable: true
        sl:
          fixed_bps: 50
        tp:
          fixed_bps: 100
        offset_bps: 5
        oco_emulation: true
      trailing:
        enable: false
        activation_profit_atr_k: 1.0
        step_bps: 10
        cooldown_sec: 60
      emergency:
        enable: true
        emergency_sl_bps: 100
    orphan_monitor:
      enabled: true
      run_on_startup: true
      periodic_interval_sec: 300
      min_order_age_sec: 0
      batch_cancel_limit: 50
      rate_limit_per_min: 120
  orders:
    default_ttl_seconds: 30
  instruments:
    BTCUSDT:
      tick_size: "0.01"
      min_qty: "0.000001"
```

## Data Contracts

### Order Execution Feedback
```json
{
  "instrument": "BTCUSDT",
  "order_id": "12345",
  "clientOrderId": "client_123",
  "lifecycle": "filled",
  "fills": [],
  "tca_realized": {
    "fees_bps": 0,
    "slip_in_bps": 0,
    "slip_out_bps": 0,
    "adverse_bps": 0,
    "latency_ms": 25,
    "rebates_bps": 0
  },
  "breaches": [],
  "why": ["EXEC_GUARD_PASS"],
  "dto_version": "1.0.0",
  "schema_ref": "https://aurora.scalp/shared/dto/exec_feedback.schema.json"
}
```

### Position State
```json
{
  "symbol": "BTCUSDT",
  "qty": "0.001",
  "entry_price": "50000.0",
  "side": "BUY",
  "open_ts": 1703123456.789,
  "sl_order_id": "sl_123",
  "tp_order_id": "tp_456",
  "unrealized_pnl": "50.0"
}
```

## Error Handling Contracts

### Error Response Format
```json
{
  "allowed": false,
  "reason": "EXPOSURE_LIMIT_EXCEEDED",
  "details": {
    "requested": 100000,
    "available": 50000,
    "symbol": "BTCUSDT"
  }
}
```

### Exception Types
- `ValueError`: Invalid input parameters
- `RuntimeError`: Execution failures
- `ConnectionError`: Network/adapter issues
- `TimeoutError`: Order timeouts

## Performance Contracts

### Latency SLAs
- **Hot Path** (CMD:OPEN → DEC:OPEN): p95 < 50ms
- **Full Cycle** (CMD:OPEN → EVT:FILL): p95 < 100ms
- **Timeout Rate**: < 1%
- **Error Rate**: < 0.1%

### Throughput
- **Orders/second**: 10+ (limited by exchange)
- **Concurrent Symbols**: 50+ (FSM per symbol)
- **Memory/FSM**: < 1MB

## Monitoring Contracts

### Health Checks
- **Adapter Status**: `connected`, `disconnected`, `shadow`
- **FSM Health**: State validation, error counters
- **Queue Depth**: Pending operations monitoring

### Alert Conditions
- Error rate > 1%
- Timeout rate > 0.5%
- Exposure limit breaches
- Orphan order accumulation

## Version Compatibility

### API Versions
- **Message Protocol**: v1.0 (stable)
- **Configuration Schema**: v1.0 (additive-only)
- **Metrics Schema**: v1.0 (backward compatible)

### Breaking Changes
- None planned for v1.x
- New features use additive configuration
- Legacy support maintained for 6 months

## Testing Dependencies

### Mock Requirements
```python
# BinanceAdapter mock
mock_adapter = AsyncMock()
mock_adapter.place_order.return_value = success_feedback

# ExposureGuard mock
mock_guard = MagicMock()
mock_guard.can_open.return_value = {"allowed": True}
```

### Test Data Contracts
- Use consistent symbol: `BTCUSDT`
- Standard quantities: `0.001`
- Standard prices: `50000.0`
- Event verbs: Match adapter emissions</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\execution_position\API_DEPENDENCIES.md
