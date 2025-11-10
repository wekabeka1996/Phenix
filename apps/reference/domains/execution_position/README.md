# Execution Position Domain - README

## Overview

The **execution_position** domain implements a sophisticated 3-FSM architecture for managing trade execution, position tracking, and risk management in the QuantumTraderX system. This domain handles the complete lifecycle of trading positions from opening through management to closing.

## Architecture

### 3-FSM Design

The domain consists of three specialized Finite State Machines:

1. **OpenFlowFSM** - Handles position opening and entry orders
2. **ManageFlowFSM** - Manages active positions with bracket orders (SL/TP)
3. **CloseFlowFSM** - Monitors exit conditions and handles position closure

### Key Components

- **ExecPosFSM** - Main orchestrator managing per-symbol FSM instances
- **ExposureGuard** - Risk management with fail-closed logic
- **OrderTimeoutWatchdog** - Monitors order ACK/FILL timeouts
- **OrderGuardian** - Handles orphan cleanup and position reconciliation
- **BinanceAdapter** - Live/testnet execution interface

## Event Flow

```
CMD:OPEN → DEC:OPEN → EVT:FILL → Position Tracking → Bracket Placement
                                      ↓
CMD:CLOSE ← DEC:CLOSE ← Time/Event Rules
```

## Configuration

The domain supports both Pydantic and dict-based configuration:

```yaml
trading:
  execution:
    manage:
      brackets:
        enable: true
        sl:
          fixed_bps: 50
        tp:
          fixed_bps: 100
        offset_bps: 5
        oco_emulation: true
```

## Risk Management

- **Exposure Limits**: Position size and notional value controls
- **Fail-Closed Logic**: Conservative behavior on errors
- **Order Timeouts**: Automatic cancellation of stuck orders
- **Orphan Detection**: Cleanup of unmatched orders

## Testing

Comprehensive test suite with 29 tests covering:
- FSM state transitions
- Event handling
- Risk guard integration
- Position lifecycle management
- Error recovery scenarios

Run tests: `pytest tests/test_execution_position.py`

## Metrics

The domain provides extensive observability metrics:
- Order placement/cancellation counts
- Position tracking metrics
- Error rates and timeouts
- Risk guard activations

## Integration

The domain integrates with:
- **decision_making**: Receives CMD:OPEN/CLOSE commands
- **BinanceAdapter**: Executes orders via REST/WebSocket
- **Portfolio**: Position state synchronization
- **Metrics**: Performance and health monitoring

## Development Status

✅ **Complete** - All FSMs implemented, tested, and documented
- 100% test pass rate (29/29 tests)
- Full event flow validation
- Risk management integration
- Production-ready code quality</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\execution_position\README.md
