# Decision Making Testing

## Test Coverage Overview

The Decision Making domain maintains comprehensive test coverage across QoS controls, rejection handling, and core decision logic.

### Test Files

- `tests/test_decision_making_qos.py`: QoS control testing (8 tests)
- `tests/test_normalized_reject_reasons.py`: Rejection reason testing (7 tests)

### Coverage Metrics

- **Total Tests**: 15
- **QoS Tests**: 8 (symbol cooldown, rate limiting, exposure blocking)
- **Rejection Tests**: 7 (various rejection scenarios)
- **Coverage Target**: 90% FSM coverage requirement

## QoS Testing Strategy

### Symbol Cooldown Testing

```python
def test_symbol_cooldown_qos(self, decision_making):
    """Test symbol-specific cooldown prevents rapid trading."""
    # First intent allowed
    result = decision_making.evaluate_opportunity(...)
    assert result is None  # Intent processed

    # Immediate second intent blocked
    result = decision_making.evaluate_opportunity(...)
    assert result is not None  # Intent rejected
    assert "SYMBOL_COOLDOWN" in result
```

**Test Cases:**
- Initial state allows trading
- Cooldown period blocks subsequent trades
- Cooldown expiration allows new trades
- Multiple symbols operate independently

### Rate Limiting Testing

```python
def test_rate_limit_qos(self, decision_making):
    """Test global rate limiting across symbols."""
    # Fill rate limit window
    for i in range(10):
        decision_making.evaluate_opportunity(f"SYMBOL{i}", ...)

    # Next intent blocked by rate limit
    result = decision_making.evaluate_opportunity("NEWSYMBOL", ...)
    assert "RATE_LIMIT_EXCEEDED" in result
```

**Test Cases:**
- Rate limit enforcement
- Window reset behavior
- Multi-symbol rate limiting
- Rate limit bypass scenarios

### Exposure Blocking Testing

```python
def test_exposure_block_cooldown(self, decision_making):
    """Test exposure limits prevent over-concentration."""
    # Configure high exposure limit
    decision_making.qos_max_exposure_pct = 0.1

    # Large position triggers exposure block
    result = decision_making.evaluate_opportunity("BTCUSDT", large_qty, ...)
    assert "EXPOSURE_LIMIT_EXCEEDED" in result
```

**Test Cases:**
- Exposure threshold enforcement
- Exposure calculation accuracy
- Exposure block cooldown
- Exposure limit bypass conditions

## Rejection Reason Testing

### Normalized Reject Reasons

```python
def test_normalize_insufficient_balance(self):
    """Test balance-related rejection normalization."""
    reason = "Account balance insufficient for order"
    nrr = NormalizedRejectReasons.normalize(reason)
    assert nrr == "INSUFFICIENT_BALANCE"

    description = NormalizedRejectReasons.get_description(nrr)
    assert "balance" in description.lower()
```

**Test Cases:**
- Insufficient balance scenarios
- Invalid order parameters
- Market closed conditions
- Exposure limit violations
- Rate limit violations
- Unknown error handling

### Comprehensive Rejection Testing

```python
def test_comprehensive_rejection_scenarios(self):
    """Test all major rejection paths."""
    scenarios = [
        ("neutral_signal", "NEUTRAL_SIGNAL"),
        ("behavior_gate_block", "BEHAVIOR_GATE"),
        ("regime_filter", "REGIME_FILTER"),
        ("no_price_reference", "NO_PRICE_REFERENCE"),
        ("zero_quantity", "ZERO_QUANTITY"),
    ]

    for scenario, expected_nrr in scenarios:
        with self.subTest(scenario=scenario):
            result = self.evaluate_with_scenario(scenario)
            assert expected_nrr in result
```

## Test Architecture

### Fixtures

```python
@pytest.fixture
def decision_making(self, mock_fsm, qos_config):
    """DecisionMaking instance with QoS configuration."""
    dm = DecisionMaking(config=qos_config, fsm=mock_fsm)
    dm.start()
    yield dm
    dm.stop()
```

### Mock Strategy

- **FSM Mocking**: Event emission verification
- **Config Mocking**: Controlled configuration testing
- **Portfolio Mocking**: Balance and position state control
- **Alpha Mocking**: Signal score and regime injection

### Test Data Management

```python
def generate_test_portfolio(self, equity="100000.0"):
    """Generate consistent portfolio test data."""
    return {
        "equity": equity,
        "positions": {},
        "margin_used": "0.0"
    }
```

## Performance Testing

### Latency Targets

- **p95 Latency**: < 50ms (hot path requirement)
- **Overall Latency**: < 100ms
- **Test Timeout**: 30 seconds

```python
def test_decision_making_latency_target(self):
    """Verify decision latency meets performance requirements."""
    latencies = []

    for _ in range(100):
        start = time.time()
        self.evaluate_opportunity(...)
        latency = (time.time() - start) * 1000
        latencies.append(latency)

    p95 = sorted(latencies)[95]
    assert p95 < 50.0, f"p95 latency {p95}ms exceeds 50ms target"
```

## Integration Testing

### End-to-End Scenarios

```python
def test_full_decision_flow(self):
    """Test complete decision making pipeline."""
    # Setup: alpha signals, portfolio, regime
    # Execute: evaluate_opportunity
    # Verify: event emission, logging, QoS state updates
    # Assert: correct intent structure and why chains
```

### Component Integration

- **AlphaModelRegistry**: Signal aggregation verification
- **AlertManager**: Risk alert triggering
- **OrderLoggerV1**: Structured logging validation
- **DeferredScheduler**: Intent deferral logic

## Test Maintenance

### Test Categories

1. **Unit Tests**: Individual method testing
2. **Integration Tests**: Component interaction
3. **Performance Tests**: Latency and throughput
4. **Regression Tests**: Bug fix validation

### Continuous Integration

- **Pre-commit**: Lint and format checks
- **CI Pipeline**: Full test suite execution
- **Coverage Reports**: Coverage target enforcement
- **Performance Benchmarks**: Latency regression detection

## Debugging Support

### Test Failure Analysis

```python
def analyze_test_failure(self, test_result):
    """Extract detailed failure information."""
    return {
        "failure_reason": test_result.longrepr,
        "test_duration": test_result.duration,
        "captured_output": test_result.capstdout,
        "error_traceback": test_result.capstderr
    }
```

### Logging Verification

```python
def verify_logging_output(self, caplog, expected_messages):
    """Verify structured logging contains expected information."""
    logs = [record.message for record in caplog.records]
    for expected in expected_messages:
        assert any(expected in log for log in logs)
```

## Future Test Enhancements

### Planned Improvements

- **Property-based Testing**: Generate edge case scenarios
- **Fuzz Testing**: Random input validation
- **Load Testing**: Concurrent decision evaluation
- **Chaos Testing**: Component failure simulation
- **A/B Testing**: Configuration optimization</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\apps\reference\domains\decision_making\TESTING.md
