# Position Tracking Domain - API Dependencies

## Overview

The position_tracking domain integrates with multiple internal components and external systems to maintain accurate portfolio state. This document outlines all API dependencies, integration contracts, and external interfaces.

## Core Dependencies

### 1. vFoundation Core
**Purpose**: Event-driven architecture and message processing

**Interface**: `vfoundation.core.FSMCore`, `vfoundation.core.protocol.Message`

**Key Methods**:
```python
# FSM event listening
fsm.listen("EVT:TRADE_EXECUTED", self.on_trade_executed)

# Event emission
fsm.emit("EVT:PORTFOLIO_STATE_UPDATED", payload=portfolio_data, why="Portfolio updated")
```

**Integration Points**:
- Event subscription for trade and account events
- Message protocol for structured event handling
- Request ID (RID) correlation across events

### 2. Write-Ahead Log (WAL)
**Purpose**: Durability and disaster recovery

**Interface**: `vfoundation.dr.wal`

**Key Methods**:
```python
# Write event to WAL
wal_hash = wal.append({
    "op": event.op,
    "verb": event.verb,
    "pld": event.pld,
    "timestamp": time.time()
})

# WAL failure handling
if wal_hash is None:
    # Critical: halt processing
    return
```

**Configuration**:
- WAL writes required before state changes
- Lock timeout handling (5-second default)
- Automatic retry logic for transient failures

### 3. Decimal Arithmetic
**Purpose**: High-precision financial calculations

**Interface**: Python `decimal.Decimal`

**Usage Patterns**:
```python
# Safe decimal parsing
def _d(value: Any, default: decimal.Decimal = decimal.Decimal("0")) -> decimal.Decimal:
    return decimal.Decimal(str(value)) if value is not None else default

# Precision preservation
price = _d(payload["price"])  # Maintains exact decimal representation
pnl = quantity * (sell_price - buy_price)  # Exact financial calculations
```

**Configuration**:
- Default precision: 28 decimal places
- Rounding: ROUND_HALF_UP for financial calculations
- String serialization to preserve precision

## External System Integrations

### 4. Binance API Integration
**Purpose**: Account state synchronization and balance updates

**Event Sources**:
- `EVT:ACCOUNT_UPDATE_RECEIVED` - Full account state updates
- `EVT:BALANCE_UPDATE_RECEIVED` - Balance changes only

**Data Contracts**:

#### Account Update Payload
```json
{
  "updateTime": 1703123456789,
  "totalWalletBalance": "10000.0",
  "totalUnrealizedProfit": "500.0",
  "totalCrossWalletBalance": "9500.0",
  "maxWithdrawAmount": "9400.0",
  "positions": [
    {
      "symbol": "BTCUSDT",
      "positionAmt": "0.001",
      "entryPrice": "50000.0",
      "markPrice": "50100.0",
      "unrealizedProfit": "1.0",
      "leverage": "20",
      "notional": "50.1"
    }
  ]
}
```

#### Balance Update Payload
```json
{
  "updateTime": 1703123456789,
  "assets": [
    {
      "asset": "USDT",
      "balance": "9500.0",
      "crossWalletBalance": "9500.0",
      "crossUnPnl": "0.0",
      "updateTime": 1703123456789
    }
  ]
}
```

**Synchronization Logic**:
1. **Equity Calculation**: `totalWalletBalance` → internal equity
2. **Realized P&L**: `totalCrossWalletBalance - initial_balance`
3. **Position Sync**: Overwrite internal positions with exchange data
4. **Cleanup**: Remove manually closed positions

### 5. Execution Adapters
**Purpose**: Trade execution event processing

**Event Sources**:
- `EVT:TRADE_EXECUTED` - Individual trade fills

**Trade Event Payload**:
```json
{
  "symbol": "BTCUSDT",
  "side": "buy",
  "price": "50000.0",
  "quantity": "0.001",
  "fees": "0.1",
  "venue": "binance",
  "ts": 1703123456789,
  "rid": "req_12345",
  "venue_order_id": "binance_123"
}
```

**Processing Requirements**:
- Real-time processing (< 10ms latency)
- Idempotent handling (duplicate events ignored)
- Correlation with request IDs

## Internal Component Integrations

### 6. Decision Making Domain
**Purpose**: Portfolio state consumption for trading decisions

**Data Flow**: Position Tracking → Decision Making

**Consumed Events**:
- `EVT:PORTFOLIO_STATE_UPDATED`

**Required Fields**:
```json
{
  "equity_free_usdt": "9500.0",
  "positions": [...],
  "open_positions_usd": "50.0",
  "positions_by_side": {
    "long_margin": "2.5",
    "short_margin": "0.0"
  }
}
```

### 7. Risk Management Domain
**Purpose**: Position exposure monitoring and limits

**Data Flow**: Position Tracking → Risk Management

**Consumed Events**:
- `EVT:PORTFOLIO_STATE_UPDATED`

**Required Fields**:
```json
{
  "open_positions_usd": "50.0",
  "open_positions_margin_usd": "2.5",
  "positions_by_side": {
    "long_margin": "2.5",
    "short_margin": "0.0"
  }
}
```

### 8. Exposure Guard
**Purpose**: Pre-trade risk validation

**Data Flow**: Position Tracking → Exposure Guard

**Consumed Events**:
- `EVT:PORTFOLIO_STATE_UPDATED`

**Required Fields**:
```json
{
  "open_positions_usd": "50.0",
  "available_balance": "9400.0",
  "positions_last_ts_ms": 1703123456789
}
```

## Configuration Dependencies

### 9. Leverage Configuration
**Purpose**: Margin calculations for different symbols

**Configuration Path**:
```yaml
trading:
  execution:
    exposure:
      leverage_defaults:
        default: "20"
        BTCUSDT: "10"
        ETHUSDT: "15"
```

**Usage**:
```python
# Safe configuration access
leverage_config = config.get("trading", {}).get("execution", {}).get("exposure", {}).get("leverage_defaults", {})

# Symbol-specific leverage with fallback
symbol_leverage = leverage_config.get(symbol, leverage_config.get("default", "20"))
```

### 10. System Configuration
**Purpose**: Worker identification for DR snapshots

**Configuration Path**:
```yaml
system:
  worker_id: "worker-01"
```

## Data Contracts and Schemas

### 11. Portfolio State Schema
**Purpose**: Standardized portfolio state representation

**Schema Reference**: `schemas/portfolio_state_v1.json`

**Required Fields**:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "ts": {"type": "number"},
    "equity": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
    "realized_pnl": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
    "positions": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "symbol": {"type": "string"},
          "net_position": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
          "avg_entry_price": {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"},
          "venues": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["symbol", "net_position", "avg_entry_price", "venues"]
      }
    }
  },
  "required": ["ts", "equity", "realized_pnl", "positions"]
}
```

### 12. DR Snapshot Schema
**Purpose**: Disaster recovery state persistence

**Schema Reference**: `schemas/snapshot_v1.schema.json`

**Snapshot Structure**:
```json
{
  "domain": "position_tracking",
  "version": "1.0.0",
  "timestamp_utc": "2024-01-15T10:30:00Z",
  "state_hash": "sha256:...",
  "state": {
    "positions": {
      "BTCUSDT": {
        "qty": "0.001",
        "avg_price": "50000.0",
        "side": "long"
      }
    },
    "portfolio": {
      "equity": "10000.0",
      "balance": "9500.0"
    }
  },
  "metadata": {
    "worker_id": "worker-01",
    "positions_count": 1
  }
}
```

## Error Handling Contracts

### 13. WAL Failure Handling
**Contract**: WAL write failures are critical and halt processing

**Error Response**:
```python
if wal_hash is None:
    self.logger.critical(f"CRITICAL: Failed to write {event.verb} to WAL (lock timeout)")
    return  # Halt processing
```

**Recovery Procedures**:
1. Check disk space and permissions
2. Verify WAL directory accessibility
3. Restart service after issue resolution
4. Replay missed events from external logs

### 14. Invalid Data Handling
**Contract**: Invalid event data is logged and skipped

**Error Response**:
```python
try:
    quantity = _d(payload["quantity"])
except (KeyError, ValueError) as e:
    self.logger.error(f"Invalid quantity in trade event: {e}")
    return
```

**Data Validation Rules**:
- Required fields must be present
- Numeric fields must be valid decimals
- Symbol must be non-empty string
- Side must be "buy" or "sell"

## Performance Contracts

### 15. Latency Requirements
- **Trade Processing**: < 10ms from event receipt to portfolio update
- **Account Sync**: < 50ms for full account state processing
- **Balance Updates**: < 20ms for equity calculations

### 16. Throughput Requirements
- **Peak Load**: 100 events/second
- **Normal Load**: 10 events/second
- **Memory Usage**: < 50KB per active position

### 17. Durability Guarantees
- **WAL Writes**: Synchronous before state changes
- **Crash Recovery**: Automatic state restoration
- **Data Consistency**: ACID properties via WAL

## Monitoring Contracts

### 18. Health Checks
**Portfolio State Freshness**:
```python
current_time = time.time() * 1000
staleness = current_time - portfolio_state.get("positions_last_ts_ms", 0)
is_healthy = staleness < 30000  # 30 seconds
```

**WAL Health**:
```python
# Check WAL write capability
test_hash = wal.append({"test": "health_check"})
wal_healthy = test_hash is not None
```

### 19. Key Metrics
- **Event Processing Rate**: Events/second by type
- **WAL Write Success Rate**: Percentage of successful writes
- **Portfolio Update Latency**: End-to-end processing time
- **Position Count**: Number of active positions
- **Memory Usage**: RAM consumption tracking

### 20. Alert Conditions
- WAL write failure rate > 1%
- Event processing latency > 100ms
- Position state staleness > 60 seconds
- Memory usage > 500MB

## Version Compatibility

### 21. API Versions
- **Message Protocol**: v1.0 (stable)
- **Portfolio Schema**: v1.0 (backward compatible)
- **DR Snapshot**: v1.0 (additive fields allowed)

### 22. Breaking Changes
- **Event Payload Changes**: Require coordinated deployment
- **Schema Updates**: Use new versions for incompatible changes
- **Configuration Changes**: Document migration procedures

## Testing Dependencies

### 23. Mock Requirements
```python
# FSM mock for event testing
fsm_mock = MagicMock()
fsm_mock.listen = MagicMock()
fsm_mock.emit = MagicMock()

# WAL mock for durability testing
wal_mock = MagicMock()
wal_mock.append.return_value = "mock_hash_123"

# Configuration mock
config_mock = {
    "trading": {
        "execution": {
            "exposure": {
                "leverage_defaults": {"default": "20"}
            }
        }
    }
}
```

### 24. Test Data Contracts
- **Symbols**: Use consistent test symbols (BTCUSDT, ETHUSDT)
- **Quantities**: Standard test quantities (0.001, 0.01)
- **Prices**: Realistic price ranges (50000.0 for BTC, 3000.0 for ETH)
- **Timestamps**: Use fixed timestamps for reproducible tests
- **RIDs**: Use predictable request IDs for correlation testing

## Future API Enhancements

### Planned Integrations
- **Market Data Integration**: Real-time P&L calculations
- **Options Support**: Greeks calculations for derivatives
- **Multi-Asset Support**: Extended asset class coverage
- **Performance Analytics**: Advanced P&L metrics

### API Evolution
- **Event Streaming**: Real-time WebSocket portfolio updates
- **Bulk Operations**: Batch position updates for efficiency
- **Custom Calculations**: Configurable P&L methodologies
- **Historical Data**: Time-series portfolio state storage</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\position_tracking\API_DEPENDENCIES.md
