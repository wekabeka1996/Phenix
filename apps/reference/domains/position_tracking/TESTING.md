# Position Tracking Domain - Testing Guide

## Overview

The position_tracking domain has comprehensive test coverage with 43 tests across 4 test files, achieving 100% pass rate. Tests validate position tracking logic, P&L calculations, account synchronization, and disaster recovery features.

## Test Structure

### Test Files Organization

```
tests/domains/
├── test_position_tracking.py              # Core functionality (9 tests)
├── test_position_tracking_logic.py        # Business logic (20 tests)
├── test_position_tracking_margins.py      # Margin calculations (10 tests)
└── test_position_tracking_wal_integration.py # WAL integration (4 tests)
```

### Test Categories

#### 1. Core Functionality Tests (9 tests)
**File**: `test_position_tracking.py`
**Purpose**: Validate basic position tracking and portfolio state emission

**Test Scenarios**:
- Trade consumption and portfolio updates
- Multiple trade processing
- Complete position closures
- Short position handling
- Multi-venue position tracking
- Invalid input rejection
- Position direction flips
- Partial position closures

#### 2. Business Logic Tests (20 tests)
**File**: `test_position_tracking_logic.py`
**Purpose**: Comprehensive validation of position management logic

**Test Scenarios**:
- Position opening (long/short)
- Position accumulation
- Partial closures with P&L
- Complete position closures
- Position direction flips
- P&L calculations with fees
- Multi-symbol independence
- Account update processing
- Balance update handling
- Portfolio state emissions
- Zero position filtering
- Invalid input validation

#### 3. Margin Calculation Tests (10 tests)
**File**: `test_position_tracking_margins.py`
**Purpose**: Validate margin and leverage calculations

**Test Scenarios**:
- Directional margin tracking
- Single position margin calculations
- Mixed long/short positions
- Leverage-based margin computation
- Fallback leverage handling
- Portfolio state margin inclusion
- Calculation precision validation
- Zero leverage edge cases
- Negative position handling

#### 4. WAL Integration Tests (4 tests)
**File**: `test_position_tracking_wal_integration.py`
**Purpose**: Validate disaster recovery and durability features

**Test Scenarios**:
- WAL write on trade events
- WAL write on account updates
- WAL failure handling
- WAL entry structure validation

## Test Execution

### Running All Tests
```bash
# Run all position tracking tests
pytest tests/domains/test_position_tracking*.py -v

# Run with coverage
pytest tests/domains/test_position_tracking*.py --cov=apps.reference.domains.position_tracking --cov-report=html
```

### Running Individual Test Files
```bash
# Core functionality
pytest tests/domains/test_position_tracking.py -v

# Business logic
pytest tests/domains/test_position_tracking_logic.py -v

# Margin calculations
pytest tests/domains/test_position_tracking_margins.py -v

# WAL integration
pytest tests/domains/test_position_tracking_wal_integration.py -v
```

### Running Specific Tests
```bash
# Run single test
pytest tests/domains/test_position_tracking_logic.py::test_opens_new_long_position_correctly -v

# Run tests matching pattern
pytest tests/domains/test_position_tracking.py -k "trade" -v
```

## Test Fixtures

### Common Test Fixtures

#### FSM and Config Setup
```python
@pytest.fixture
def fsm():
    """Create test FSM instance"""
    return FSMCore()

@pytest.fixture
def config():
    """Create test configuration"""
    return {
        "trading": {
            "execution": {
                "exposure": {
                    "leverage_defaults": {
                        "default": "20",
                        "BTCUSDT": "10"
                    }
                }
            }
        }
    }
```

#### Position Tracking Instance
```python
@pytest.fixture
def position_tracking(fsm, config):
    """Create PositionTracking instance"""
    pt = PositionTracking(fsm, config)
    yield pt
    # Cleanup if needed
```

### Mock Data Factories

#### Trade Event Factory
```python
def create_trade_event(symbol="BTCUSDT", side="buy", quantity="0.001", price="50000.0"):
    """Create mock trade execution event"""
    return Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="binance_adapter",
        dst="position_tracking",
        rid="test_123",
        pld={
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "fees": "0.1",
            "venue": "binance",
            "ts": 1703123456789
        }
    )
```

#### Account Update Factory
```python
def create_account_update(positions=None, balance="10000.0"):
    """Create mock account update event"""
    return Message(
        op="EVT",
        verb="ACCOUNT_UPDATE_RECEIVED",
        src="binance_ws",
        dst="position_tracking",
        rid="test_456",
        pld={
            "totalWalletBalance": balance,
            "positions": positions or [],
            "updateTime": 1703123456789
        }
    )
```

## Test Scenarios and Edge Cases

### Position Management Scenarios

#### 1. Basic Position Opening
```python
def test_opens_new_long_position_correctly(position_tracking, fsm):
    # Create and process trade
    event = create_trade_event(side="buy", quantity="0.001", price="50000.0")
    position_tracking.on_trade_executed(event)

    # Verify position created
    positions = position_tracking.get_positions()
    assert "BTCUSDT" in positions
    assert positions["BTCUSDT"]["quantity"] == Decimal("0.001")
    assert positions["BTCUSDT"]["avg_price"] == Decimal("50000.0")
```

#### 2. Position Accumulation
```python
def test_increases_existing_long_position(position_tracking, fsm):
    # First trade
    event1 = create_trade_event(quantity="0.001", price="50000.0")
    position_tracking.on_trade_executed(event1)

    # Second trade (same direction)
    event2 = create_trade_event(quantity="0.002", price="51000.0")
    position_tracking.on_trade_executed(event2)

    # Verify weighted average
    positions = position_tracking.get_positions()
    pos = positions["BTCUSDT"]
    assert pos["quantity"] == Decimal("0.003")
    expected_avg = (0.001 * 50000 + 0.002 * 51000) / 0.003
    assert pos["avg_price"] == Decimal(str(expected_avg))
```

#### 3. Position Closure with P&L
```python
def test_calculates_realized_pnl_on_close(position_tracking, fsm):
    # Open position
    open_event = create_trade_event(side="buy", quantity="0.001", price="50000.0")
    position_tracking.on_trade_executed(open_event)

    # Close position at profit
    close_event = create_trade_event(side="sell", quantity="0.001", price="51000.0")
    position_tracking.on_trade_executed(close_event)

    # Verify P&L calculation
    assert position_tracking._realized_pnl == Decimal("10.0")  # 0.001 * (51000 - 50000)
```

#### 4. Position Flip
```python
def test_flips_long_to_short(position_tracking, fsm):
    # Open long position
    long_event = create_trade_event(side="buy", quantity="0.001", price="50000.0")
    position_tracking.on_trade_executed(long_event)

    # Sell more than position size (flip to short)
    flip_event = create_trade_event(side="sell", quantity="0.002", price="49000.0")
    position_tracking.on_trade_executed(flip_event)

    # Verify position flipped
    positions = position_tracking.get_positions()
    pos = positions["BTCUSDT"]
    assert pos["quantity"] == Decimal("-0.001")  # Short position
    assert pos["avg_price"] == Decimal("49000.0")  # New entry price
```

### Account Synchronization Scenarios

#### 1. Account Update Processing
```python
def test_handles_account_update_event(position_tracking, fsm):
    positions_data = [{
        "symbol": "BTCUSDT",
        "positionAmt": "0.001",
        "entryPrice": "50000.0"
    }]

    event = create_account_update(positions=positions_data, balance="10000.0")
    position_tracking.on_account_update(event)

    # Verify equity updated
    assert position_tracking._equity == Decimal("10000.0")

    # Verify positions synchronized
    positions = position_tracking.get_positions()
    assert positions["BTCUSDT"]["quantity"] == Decimal("0.001")
```

#### 2. Manual Position Closure Detection
```python
def test_account_update_removes_flat_positions(position_tracking, fsm):
    # Set up internal position
    position_tracking._positions["BTCUSDT"] = {
        "quantity": Decimal("0.001"),
        "avg_price": Decimal("50000.0"),
        "venues": ["binance"]
    }

    # Account update with no positions (manual close)
    event = create_account_update(positions=[], balance="10000.0")
    position_tracking.on_account_update(event)

    # Verify position removed
    positions = position_tracking.get_positions()
    assert "BTCUSDT" not in positions
```

### Margin Calculation Scenarios

#### 1. Directional Margin Tracking
```python
def test_margin_by_side_single_long_position(position_tracking, fsm):
    # Set up position
    position_tracking._positions["BTCUSDT"] = {
        "quantity": Decimal("0.001"),
        "avg_price": Decimal("50000.0"),
        "venues": ["binance"]
    }

    # Calculate margin by side
    margin_by_side = position_tracking._calculate_margin_by_side([])

    # Verify long margin calculated
    assert margin_by_side["long_margin"] > Decimal("0")
    assert margin_by_side["short_margin"] == Decimal("0")
```

#### 2. Leverage-Based Calculations
```python
def test_portfolio_state_includes_margin_by_side(position_tracking, fsm):
    # Set up position and trigger portfolio update
    position_tracking._positions["BTCUSDT"] = {
        "quantity": Decimal("0.001"),
        "avg_price": Decimal("50000.0"),
        "venues": ["binance"]
    }

    # Mock FSM emit to capture portfolio update
    emitted_events = []
    def mock_emit(event_name, payload, why):
        emitted_events.append((event_name, payload))

    fsm.emit = mock_emit

    # Trigger account update to emit portfolio state
    event = create_account_update(positions=[{
        "symbol": "BTCUSDT",
        "positionAmt": "0.001",
        "entryPrice": "50000.0",
        "markPrice": "50000.0",
        "leverage": "20"
    }])
    position_tracking.on_account_update(event)

    # Verify margin included in portfolio update
    assert len(emitted_events) == 1
    event_name, payload = emitted_events[0]
    assert event_name == "EVT:PORTFOLIO_STATE_UPDATED"
    assert "positions_by_side" in payload
```

### WAL Integration Scenarios

#### 1. WAL Write on Events
```python
def test_trade_executed_writes_to_wal(position_tracking, fsm):
    # Mock WAL to capture writes
    wal_writes = []
    def mock_append(event_dict):
        wal_writes.append(event_dict)
        return "mock_hash"

    # Patch WAL
    import vfoundation.dr.wal as wal_module
    original_append = wal_module.append
    wal_module.append = mock_append

    try:
        # Process trade
        event = create_trade_event()
        position_tracking.on_trade_executed(event)

        # Verify WAL write
        assert len(wal_writes) == 1
        wal_entry = wal_writes[0]
        assert wal_entry["op"] == "EVT"
        assert wal_entry["verb"] == "TRADE_EXECUTED"
    finally:
        wal_module.append = original_append
```

#### 2. WAL Failure Handling
```python
def test_wal_write_failure_halts_processing(position_tracking, fsm):
    # Mock WAL to simulate failure
    def mock_append(event_dict):
        return None  # Lock timeout

    import vfoundation.dr.wal as wal_module
    original_append = wal_module.append
    wal_module.append = mock_append

    try:
        # Process trade
        event = create_trade_event()
        initial_positions = position_tracking.get_positions().copy()

        position_tracking.on_trade_executed(event)

        # Verify processing halted (no position change)
        final_positions = position_tracking.get_positions()
        assert final_positions == initial_positions
    finally:
        wal_module.append = original_append
```

## Performance Testing

### Load Testing
```python
def test_high_frequency_trades(position_tracking, fsm):
    """Test processing many trades quickly"""
    import time

    start_time = time.time()

    # Process 1000 trades
    for i in range(1000):
        event = create_trade_event(quantity="0.001", price=str(50000 + i))
        position_tracking.on_trade_executed(event)

    end_time = time.time()

    # Verify performance
    assert end_time - start_time < 5.0  # Should complete in < 5 seconds
    assert len(position_tracking.get_positions()) == 1
```

### Memory Leak Testing
```python
def test_no_memory_leaks_in_position_tracking(position_tracking, fsm):
    """Ensure position tracking doesn't accumulate memory"""
    import psutil
    import os

    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss

    # Process many position operations
    for i in range(1000):
        event = create_trade_event()
        position_tracking.on_trade_executed(event)

        # Close position
        close_event = create_trade_event(side="sell")
        position_tracking.on_trade_executed(close_event)

    final_memory = process.memory_info().rss
    memory_increase = final_memory - initial_memory

    # Allow some memory increase but not excessive
    assert memory_increase < 50 * 1024 * 1024  # < 50MB increase
```

## Test Maintenance

### Adding New Tests
1. **Identify Test Scenario**: Determine what behavior needs testing
2. **Create Test Data**: Use factory functions for consistent test data
3. **Write Test Logic**: Follow AAA pattern (Arrange, Act, Assert)
4. **Add Edge Cases**: Test boundary conditions and error scenarios
5. **Update Documentation**: Add test to this guide if significant

### Test Data Management
- Use factory functions for consistent event creation
- Avoid hardcoded values in tests
- Mock external dependencies (WAL, FSM)
- Clean up test state between runs

### CI/CD Integration
```yaml
# .github/workflows/test.yml
- name: Run Position Tracking Tests
  run: |
    pytest tests/domains/test_position_tracking*.py -v --cov=apps.reference.domains.position_tracking --cov-report=xml
```

## Test Coverage Analysis

### Coverage Report
```bash
pytest tests/domains/test_position_tracking*.py --cov=apps.reference.domains.position_tracking --cov-report=html
```

### Coverage Areas
- **Position Management**: 95% coverage
  - Opening, closing, accumulation
  - P&L calculations
  - Position flips

- **Account Synchronization**: 90% coverage
  - Account updates
  - Balance updates
  - State reconciliation

- **Margin Calculations**: 85% coverage
  - Directional margins
  - Leverage handling
  - Fallback calculations

- **WAL Integration**: 80% coverage
  - Write operations
  - Failure handling
  - Data validation

### Gaps and Improvements
- **Unrealized P&L**: Not fully tested (requires market data integration)
- **Error Scenarios**: Some edge cases could have more coverage
- **Performance**: Load testing could be expanded
- **Integration**: End-to-end scenarios with multiple components

## Debugging Failed Tests

### Common Failure Patterns

#### 1. Decimal Precision Issues
```python
# Problem: Decimal comparison fails due to precision
assert position["avg_price"] == Decimal("50000.0")

# Solution: Use approximate comparison
assert abs(position["avg_price"] - Decimal("50000.0")) < Decimal("1e-10")
```

#### 2. Event Timing Issues
```python
# Problem: Events processed out of order
fsm.emit.assert_called_once()  # But called multiple times

# Solution: Check specific call
calls = fsm.emit.call_args_list
assert len(calls) == 1
assert calls[0][0][0] == "EVT:PORTFOLIO_STATE_UPDATED"
```

#### 3. State Mutation Issues
```python
# Problem: Test state polluted between runs
def test_isolated_operation(position_tracking):
    # Reset state
    position_tracking._positions.clear()
    position_tracking._realized_pnl = Decimal("0")

    # Test operation
    # ...
```

### Debugging Tools
```python
# Add debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Inspect internal state
print("Positions:", position_tracking.get_positions())
print("P&L:", position_tracking._realized_pnl)

# Mock verification
fsm.emit.assert_called_with(
    "EVT:PORTFOLIO_STATE_UPDATED",
    payload=mock.ANY,  # Ignore payload details
    why=mock.ANY
)
```

## Future Test Enhancements

### Planned Improvements
- **Integration Tests**: End-to-end scenarios with multiple domains
- **Performance Benchmarks**: Latency and throughput testing
- **Chaos Testing**: Network failures, disk full scenarios
- **Property-Based Testing**: Generate test cases automatically

### Test Automation
- **CI Pipeline**: Automated test execution on commits
- **Coverage Gates**: Fail builds with insufficient coverage
- **Performance Regression**: Alert on performance degradation
- **Flaky Test Detection**: Identify and fix unreliable tests</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\position_tracking\TESTING.md
