# Position Tracking Domain - Events

## Overview

The position_tracking domain processes financial events and emits portfolio state updates. It serves as the central source of truth for position and P&L information in the QuantumTraderX system.

## Event Flow Architecture

```
Trade Execution → Position Tracking → Portfolio State Update
Account Updates → State Synchronization → Portfolio State Update
Balance Changes → Equity Calculation → Portfolio State Update
```

## Input Events

### EVT:TRADE_EXECUTED

**Purpose**: Process executed trades and update position state with P&L calculations.

**Source**: Execution adapters (BinanceAdapter, etc.)

**Frequency**: Per trade execution

**Processing Priority**: High (real-time)

**Payload Structure**:
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

**Field Descriptions**:
- `symbol`: Trading pair symbol (string)
- `side`: Trade direction - "buy" or "sell" (string)
- `price`: Execution price (decimal string)
- `quantity`: Executed quantity (decimal string)
- `fees`: Trading fees (decimal string)
- `venue`: Execution venue identifier (string)
- `ts`: Execution timestamp in milliseconds (integer)
- `rid`: Request ID for correlation (string)
- `venue_order_id`: Venue-specific order identifier (string)

**Processing Logic**:
1. **WAL Write**: Event logged to write-ahead log for durability
2. **Position Update**: Internal position state updated with new trade
3. **P&L Calculation**: Realized P&L calculated for position changes
4. **Portfolio Emission**: EVT:PORTFOLIO_STATE_UPDATED emitted

**Error Handling**:
- WAL write failure → Processing halted (critical safety measure)
- Invalid payload → Logged and skipped
- State inconsistency → WAL rollback attempted

### EVT:ACCOUNT_UPDATE_RECEIVED

**Purpose**: Synchronize portfolio state with official account data from exchange.

**Source**: Binance WebSocket API

**Frequency**: Real-time account changes

**Processing Priority**: High (state synchronization)

**Payload Structure**:
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
  ],
  "assets": [
    {
      "asset": "USDT",
      "walletBalance": "10000.0",
      "crossWalletBalance": "9500.0",
      "crossUnPnl": "500.0"
    }
  ]
}
```

**Field Descriptions**:
- `updateTime`: Account update timestamp (milliseconds)
- `totalWalletBalance`: Total account balance including unrealized P&L
- `totalUnrealizedProfit`: Total unrealized P&L across all positions
- `totalCrossWalletBalance`: Balance excluding unrealized P&L
- `maxWithdrawAmount`: Available balance for withdrawal
- `positions`: Array of position objects with detailed position data
- `assets`: Array of asset balances

**Processing Logic**:
1. **WAL Write**: Account state change logged for durability
2. **Equity Update**: Internal equity state updated from wallet balance
3. **Realized P&L Recalculation**: Computed from cross wallet balance changes
4. **Position Synchronization**: Internal positions updated to match exchange state
5. **Portfolio Emission**: EVT:PORTFOLIO_STATE_UPDATED emitted with full state

**State Synchronization Rules**:
- Positions with `abs(positionAmt) > 1e-9` are tracked
- Zero positions are removed from internal state
- Manually closed positions (in internal state but not in exchange) are cleaned up
- Position average prices updated from `entryPrice`

### EVT:BALANCE_UPDATE_RECEIVED

**Purpose**: Handle balance changes and compute equity metrics for decision making.

**Source**: Binance WebSocket API

**Frequency**: Balance changes (deposits, withdrawals, fees)

**Processing Priority**: Medium (equity updates)

**Payload Structure**:
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

**Field Descriptions**:
- `updateTime`: Balance update timestamp (milliseconds)
- `assets`: Array of asset balance updates

**Processing Logic**:
1. **Equity Computation**: Calculate free and cross equity from USDT balance
2. **Portfolio Emission**: EVT:PORTFOLIO_STATE_UPDATED emitted with equity fields
3. **No WAL Write**: Balance updates don't change position state (only equity)

**Equity Calculation**:
```python
# Free equity (available for new positions)
equity_free = usdt_balance

# Cross equity (total wallet value)
equity_cross = usdt_cross_wallet_balance + usdt_cross_unrealized_pnl
```

## Output Events

### EVT:PORTFOLIO_STATE_UPDATED

**Purpose**: Broadcast comprehensive portfolio state to all subscribers for decision making and risk management.

**Destinations**: Decision Making, Risk Management, Exposure Guard, Monitoring

**Frequency**: After every state-changing event

**Processing Priority**: High (portfolio state distribution)

**Payload Structure**:
```json
{
  "ts": 1703123456789,
  "equity": "10000.0",
  "equity_free_usdt": "9500.0",
  "equity_cross_usdt": "10000.0",
  "equity_ts": 1703123456789,
  "realized_pnl": "500.0",
  "unrealized_pnl": "0.0",
  "available_balance": "9400.0",
  "positions": [
    {
      "symbol": "BTCUSDT",
      "net_position": "0.001",
      "avg_entry_price": "50000.0",
      "venues": ["binance"]
    }
  ],
  "open_positions_usd": "50.0",
  "open_positions_margin_usd": "2.5",
  "positions_by_side": {
    "long_margin": "2.5",
    "short_margin": "0.0"
  },
  "positions_last_ts_ms": 1703123456789
}
```

**Field Descriptions**:

**Core Equity Fields**:
- `ts`: Portfolio state timestamp (milliseconds)
- `equity`: Legacy equity field for backward compatibility
- `equity_free_usdt`: USDT available for new positions
- `equity_cross_usdt`: Total account value including unrealized P&L
- `equity_ts`: Equity calculation timestamp

**P&L Fields**:
- `realized_pnl`: Cumulative realized profit/loss (decimal string)
- `unrealized_pnl`: Current unrealized profit/loss (decimal string)
- `available_balance`: Balance available for withdrawal/trading

**Position Fields**:
- `positions`: Array of active positions
- `open_positions_usd`: Total notional value of open positions
- `open_positions_margin_usd`: Total margin used by positions
- `positions_by_side`: Margin breakdown by long/short
- `positions_last_ts_ms`: Last position update timestamp

**Position Object Structure**:
```json
{
  "symbol": "BTCUSDT",
  "net_position": "0.001",
  "avg_entry_price": "50000.0",
  "venues": ["binance"]
}
```

## Event Processing Flows

### Trade Execution Flow

```
1. EVT:TRADE_EXECUTED received
2. WAL write (durability guarantee)
3. Position state update
4. P&L calculation (realized only)
5. Portfolio metrics calculation
6. EVT:PORTFOLIO_STATE_UPDATED emitted
```

### Account Synchronization Flow

```
1. EVT:ACCOUNT_UPDATE_RECEIVED received
2. WAL write (state change logging)
3. Equity state update
4. Realized P&L recalculation
5. Position synchronization with exchange
6. Portfolio metrics calculation
7. EVT:PORTFOLIO_STATE_UPDATED emitted
```

### Balance Update Flow

```
1. EVT:BALANCE_UPDATE_RECEIVED received
2. Equity calculation from balance data
3. Portfolio state preparation
4. EVT:PORTFOLIO_STATE_UPDATED emitted
```

## Error Handling and Recovery

### WAL Write Failures
**Condition**: WAL.append() returns None (lock timeout)

**Response**:
- Processing halted immediately
- Critical error logged with RID
- Event not processed to prevent state inconsistency
- Manual intervention required

**Recovery**:
- Check WAL disk space and permissions
- Restart service after WAL issue resolved
- Events replayed from external source if needed

### Invalid Event Payloads
**Condition**: Missing required fields or invalid data types

**Response**:
- Event logged as warning
- Processing skipped for invalid event
- State remains unchanged
- Downstream systems unaffected

### State Inconsistencies
**Condition**: Internal state diverges from exchange state

**Response**:
- Account update events trigger reconciliation
- Internal positions overwritten with exchange data
- Discrepancies logged for analysis
- Manual position audit recommended

## Performance Characteristics

### Latency Requirements
- **EVT:TRADE_EXECUTED**: < 10ms end-to-end
- **EVT:ACCOUNT_UPDATE_RECEIVED**: < 50ms end-to-end
- **EVT:BALANCE_UPDATE_RECEIVED**: < 20ms end-to-end

### Throughput
- **Peak Load**: 100 events/second
- **Normal Load**: 10 events/second
- **Minimum Load**: 1 event/minute

### Resource Usage
- **Memory**: ~50KB per active position
- **CPU**: < 5ms per event processing
- **Storage**: ~1KB per WAL entry

## Testing Event Scenarios

### Position Opening
```json
// Input: EVT:TRADE_EXECUTED
{
  "symbol": "BTCUSDT",
  "side": "buy",
  "price": "50000.0",
  "quantity": "0.001"
}

// Output: EVT:PORTFOLIO_STATE_UPDATED
{
  "positions": [
    {
      "symbol": "BTCUSDT",
      "net_position": "0.001",
      "avg_entry_price": "50000.0"
    }
  ],
  "open_positions_usd": "50.0"
}
```

### Position Closing with P&L
```json
// Input: EVT:TRADE_EXECUTED (closing trade)
{
  "symbol": "BTCUSDT",
  "side": "sell",
  "price": "51000.0",
  "quantity": "0.001"
}

// Output: EVT:PORTFOLIO_STATE_UPDATED
{
  "realized_pnl": "10.0",
  "positions": [],
  "open_positions_usd": "0.0"
}
```

### Account Synchronization
```json
// Input: EVT:ACCOUNT_UPDATE_RECEIVED
{
  "totalWalletBalance": "10000.0",
  "positions": [
    {
      "symbol": "BTCUSDT",
      "positionAmt": "0.001",
      "entryPrice": "50000.0"
    }
  ]
}

// Output: EVT:PORTFOLIO_STATE_UPDATED
{
  "equity": "10000.0",
  "positions": [
    {
      "symbol": "BTCUSDT",
      "net_position": "0.001",
      "avg_entry_price": "50000.0"
    }
  ]
}
```

## Monitoring and Observability

### Key Metrics
- **Event Processing Rate**: Events processed per second
- **WAL Write Success Rate**: Percentage of successful WAL writes
- **Portfolio Update Latency**: Time to emit portfolio state updates
- **Position Count**: Number of active positions tracked
- **State Synchronization Delay**: Time between exchange and internal state

### Alert Conditions
- WAL write failure rate > 1%
- Event processing latency > 100ms
- Position state inconsistencies detected
- Memory usage > 500MB

### Log Patterns
```
INFO: Handling EVT:TRADE_EXECUTED...
INFO: WAL: Appended TRADE_EXECUTED to WAL with hash=abc123...
INFO: Emitting EVT:PORTFOLIO_STATE_UPDATED...
WARNING: Detected manually closed positions: {'BTCUSDT'}
CRITICAL: Failed to write EVT:TRADE_EXECUTED to WAL (lock timeout)
```

## Future Event Enhancements

### Planned Events
- **EVT:POSITION_RISK_UPDATED**: Position-level risk metrics
- **EVT:PnL_REALIZED**: Detailed P&L breakdown events
- **EVT:PORTFOLIO_SNAPSHOT**: Periodic full portfolio snapshots

### Enhanced Payloads
- **Real-time P&L**: Include mark prices for unrealized P&L
- **Position Greeks**: Delta, gamma, theta for options positions
- **Performance Metrics**: Sharpe ratio, max drawdown tracking

### Event Streaming
- **WebSocket Streams**: Real-time portfolio updates
- **Event Filtering**: Subscriber-specific event filtering
- **Event Replay**: Historical event replay for backtesting</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\position_tracking\EVENTS.md
