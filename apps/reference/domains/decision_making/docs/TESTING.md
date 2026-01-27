# Decision Making Testing

> **Last Updated**: 2025-11-29  
> **Version**: 1.2.0

## Test Coverage Overview

| Category | Tests | Status |
|----------|-------|--------|
| QoS Controls | 8 | ✅ All passing |
| Rejection Reasons | 7 | ✅ All passing |
| Performance | 3 | ✅ All passing |
| Integration | 5+ | ✅ All passing |
| **Total** | **23+** | ✅ **Coverage Target: 90%** |

## Test Files

| File | Description |
|------|-------------|
| `tests/test_decision_making_qos.py` | QoS control testing |
| `tests/test_normalized_reject_reasons.py` | NRR normalization testing |
| `tests/test_phase7_performance.py` | Latency and throughput testing |
| `tests/bugfixes/test_p1_004_failclosed_price.py` | Fail-closed behavior testing |
| `tests/test_why_chain_message_preservation.py` | WHY chain integrity |
| `tests/audit_remediation/test_red_flags.py` | **Audit Red Flags Verification** (New) |

## Running Tests

```bash
# All decision_making tests
pytest tests/test_decision_making_qos.py tests/test_normalized_reject_reasons.py -v

# With coverage
pytest tests/test_decision_making*.py --cov=apps/reference/domains/decision_making --cov-report=term-missing

# Performance tests only
pytest tests/test_phase7_performance.py::TestPhase7Performance::test_decision_making_latency_p95 -v

# Specific test
pytest tests/test_normalized_reject_reasons.py::TestNormalizedRejectReasons::test_normalize_insufficient_balance -v
```

---

## QoS Testing Strategy

### Symbol Cooldown Testing

```python
def test_symbol_cooldown_qos(self, decision_making):
    """Test symbol-specific cooldown prevents rapid trading."""
    # First intent allowed
    result = decision_making.evaluate_opportunity(
        symbol="BTCUSDT",
        features_data=features,
        portfolio=portfolio,
        regime=regime,
        rid="rid-1"
    )
    assert result is None  # Intent processed

    # Immediate second intent blocked by cooldown
    result = decision_making.evaluate_opportunity(
        symbol="BTCUSDT",
        features_data=features,
        portfolio=portfolio,
        regime=regime,
        rid="rid-2"
    )
    assert result is not None  # Intent rejected
    assert "SYMBOL_COOLDOWN" in result or "RATE_LIMIT" in result
```

**Test Cases:**
- ✅ Initial state allows trading
- ✅ Cooldown period blocks subsequent trades
- ✅ Cooldown expiration allows new trades
- ✅ Multiple symbols operate independently
- ✅ Cooldown reset after window elapsed

### Rate Limiting Testing

```python
def test_rate_limit_qos(self, decision_making):
    """Test global rate limiting across symbols."""
    # Fill rate limit window (default: 6 intents/minute/symbol)
    for i in range(6):
        decision_making.evaluate_opportunity(f"BTCUSDT", ...)

    # Next intent blocked by rate limit
    result = decision_making.evaluate_opportunity("BTCUSDT", ...)
    assert "RATE_LIMIT_EXCEEDED" in str(result)
```

**Test Cases:**
- ✅ Rate limit enforcement at threshold
- ✅ Window reset after 60 seconds
- ✅ Per-symbol rate tracking
- ✅ Rate limit bypass in shadow mode

### Exposure Blocking Testing

```python
def test_exposure_block_cooldown(self, decision_making):
    """Test exposure limits prevent over-concentration."""
    # Simulate exposure block
    decision_making._handle_exposure_block("BTCUSDT")
    
    # Subsequent decisions blocked during cooldown
    qos_result = decision_making._qos_allow("BTCUSDT", is_exposure_block=True)
    assert qos_result[0] is False
    assert "EXPOSURE_LIMIT" in qos_result[1]
```

**Test Cases:**
- ✅ Exposure threshold enforcement
- ✅ Exposure block cooldown (10s default)
- ✅ Cooldown expiration allows trading
- ✅ Independent from symbol cooldown

---

## Rejection Reason Testing

### NRR Normalization

```python
def test_normalize_insufficient_balance(self):
    """Test balance-related rejection normalization."""
    test_cases = [
        "insufficient balance",
        "Account balance insufficient for order",
        "not enough funds available",
    ]
    
    for reason in test_cases:
        nrr = NormalizedRejectReasons.normalize(reason)
        assert nrr == "NRR-001"  # INSUFFICIENT_BALANCE
        
        description = NormalizedRejectReasons.get_description(nrr)
        assert "balance" in description.lower()
```

### Comprehensive Rejection Scenarios

```python
def test_comprehensive_rejection_scenarios(self):
    """Test all major rejection paths."""
    scenarios = [
        ("insufficient balance for order", "NRR-001"),
        ("invalid order parameters", "NRR-002"),
        ("market closed for trading", "NRR-003"),
        ("symbol not available", "NRR-004"),
        ("price out of range", "NRR-005"),
        ("quantity too small", "NRR-006"),
        ("rate limit exceeded", "NRR-014"),
        ("symbol cooldown active", "NRR-017"),
        ("exchange rejected order -2010", "NRR-018"),
    ]

    for reason, expected_nrr in scenarios:
        with self.subTest(reason=reason):
            result = NormalizedRejectReasons.normalize(reason)
            assert result == expected_nrr
```

---

## Audit Red Flags Validation (2026-01-26)

### 1. Hardcoded Anchor Test
```python
def test_anchor_is_configurable(self):
    """Verify anchor symbol is not hardcoded to BTCUSDT."""
    handler = AuroraHandler(config={"anchor_symbol": "ETHUSDT"})
    assert handler.anchor_symbol == "ETHUSDT"
    # Logic should NOT default to BTCUSDT if config provided
```

### 2. Anti-Pyramiding Fail-Open Check
```python
def test_anti_pyramiding_fail_closed(self):
    """Verify position check raises exception instead of False on error."""
    with patch("portfolio_manager.get_position", side_effect=Exception("DB Error")):
        with pytest.raises(Exception):
            _has_active_position_same_side(...)
        # Should NOT return False (allow trade)
```

---

## Performance Testing

### Latency Targets

| Metric | Target | Test Method |
|--------|--------|-------------|
| p95 Latency | < 50ms | 1000 iterations, sorted[950] |
| Overall p95 | < 100ms | End-to-end flow |
| Throughput | 100-200 decisions/sec | Rate measurement |

### Latency Test Implementation

```python
def test_decision_making_latency_p95(self):
    """Verify decision latency meets performance requirements."""
    latencies = []
    num_iterations = 1000

    for _ in range(num_iterations):
        start = time.perf_counter()
        
        # Simulate decision evaluation
        self.decision_making.evaluate_opportunity(
            symbol="BTCUSDT",
            features_data=features,
            portfolio=portfolio,
            regime=regime,
            rid=str(uuid.uuid4())
        )
        
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

    p95 = sorted(latencies)[int(num_iterations * 0.95)]
    p99 = sorted(latencies)[int(num_iterations * 0.99)]
    avg = sum(latencies) / len(latencies)

    print(f"\n✅ DecisionMaking Latency ({num_iterations} iterations):")
    print(f"   Average: {avg:.4f}ms")
    print(f"   p95: {p95:.4f}ms")
    print(f"   p99: {p99:.4f}ms")

    assert p95 < 50.0, f"p95 latency {p95:.4f}ms exceeds 50ms target"
```

---

## Integration Testing

### End-to-End Decision Flow

```python
def test_full_decision_flow(self):
    """Test complete decision making pipeline."""
    # Setup: Create DecisionMaking with real config
    dm = DecisionMaking(fsm=mock_fsm, config=config)
    
    # Simulate event sequence
    dm.on_portfolio(portfolio_event)
    dm.on_regime(regime_event)
    dm.on_risk(risk_event)
    dm.on_features(features_event)
    
    # Verify: Intent was emitted
    assert mock_fsm.emit.called
    call_args = mock_fsm.emit.call_args
    assert call_args[0][0] == "EVT:TRADE_INTENT_PROPOSED"
    
    # Verify: Payload structure
    payload = call_args[1]["payload"]
    assert "instrument" in payload
    assert "side" in payload
    assert "order" in payload
    assert "why" in payload
```

### Fail-Closed Behavior

```python
def test_fail_closed_no_price_reference(self):
    """Verify decision_making REJECTS when price reference is missing."""
    features_without_price = {
        "symbol": "BTCUSDT",
        "ts": int(time.time() * 1000),
        "features": {}  # No price
    }
    
    dm = DecisionMaking(fsm=mock_fsm, config=config)
    dm.on_features(Message(pld=features_without_price))
    
    # Should NOT emit trade intent
    assert not any(
        call[0][0] == "EVT:TRADE_INTENT_PROPOSED" 
        for call in mock_fsm.emit.call_args_list
    )
```

---

## Test Architecture

### Fixtures

```python
@pytest.fixture
def mock_fsm():
    """Mock FSM for event verification."""
    fsm = MagicMock()
    fsm.emit = MagicMock()
    fsm.listen = MagicMock()
    return fsm

@pytest.fixture
def qos_config():
    """Configuration with QoS settings."""
    return {
        "trading": {
            "decision": {
                "position_sizing": {
                    "min_position_size_usd": 10,
                    "liquidity_based_cap_usd": 1000
                },
                "qos": {
                    "exposure_block_cooldown_sec": 10,
                    "symbol_cooldown_sec": 3,
                    "max_intents_per_minute_per_symbol": 6,
                    "mode": "defer"
                }
            },
            "tca_prefs": {},
            "risk_budgets": {}
        }
    }

@pytest.fixture
def decision_making(mock_fsm, qos_config):
    """DecisionMaking instance with QoS configuration."""
    dm = DecisionMaking(fsm=mock_fsm, config=qos_config)
    yield dm
```

### Mock Strategy

| Component | Mock Method | Purpose |
|-----------|-------------|---------|
| FSM | `MagicMock()` | Event emission verification |
| Config | Dict fixture | Controlled configuration |
| Portfolio | Dict fixture | Balance/position state |
| Alpha Registry | `MagicMock()` | Signal injection |
| WAL | `patch('vfoundation.dr.wal')` | Isolate persistence |

### Test Data Generators

```python
def generate_test_portfolio(equity="100000.0", positions=None):
    """Generate consistent portfolio test data."""
    return {
        "equity": equity,
        "equity_free_usdt": equity,
        "equity_cross_usdt": equity,
        "positions": positions or [],
        "margin_used": "0.0"
    }

def generate_test_features(symbol="BTCUSDT", price="50000.0"):
    """Generate consistent feature test data."""
    return {
        "symbol": symbol,
        "ts": int(time.time() * 1000),
        "features": {
            "price": price,
            "volume_24h": "1000000000",
            "volatility": "0.02"
        }
    }

def generate_test_regime(symbol="BTCUSDT", regime="TREND_UP"):
    """Generate consistent regime test data."""
    return {
        "symbol": symbol,
        "regime": regime,
        "confidence": 0.85
    }
```

---

## Debugging Support

### Test Failure Analysis

```python
def analyze_test_failure(caplog, expected_behavior):
    """Extract detailed failure information."""
    logs = [record.message for record in caplog.records]
    
    print("\n=== Test Failure Analysis ===")
    print(f"Expected: {expected_behavior}")
    print(f"Log entries ({len(logs)}):")
    for log in logs[-10:]:  # Last 10 entries
        print(f"  - {log}")
    
    return {
        "log_count": len(logs),
        "last_logs": logs[-10:],
        "error_logs": [l for l in logs if "ERROR" in l or "WARNING" in l]
    }
```

### Logging Verification

```python
def verify_logging_output(caplog, expected_messages):
    """Verify structured logging contains expected information."""
    logs = [record.message for record in caplog.records]
    
    for expected in expected_messages:
        found = any(expected in log for log in logs)
        assert found, f"Expected log message not found: {expected}"
```

---

## Continuous Integration

### Pre-commit Checks

```bash
# Lint and format
ruff check apps/reference/domains/decision_making/
black --check apps/reference/domains/decision_making/
mypy apps/reference/domains/decision_making/
```

### CI Pipeline

```yaml
# .github/workflows/test.yml
- name: Run Decision Making Tests
  run: |
    pytest tests/test_decision_making*.py tests/test_normalized_reject_reasons.py \
      --cov=apps/reference/domains/decision_making \
      --cov-fail-under=90 \
      -v
```

### Coverage Requirements

- **Target**: 90% FSM coverage
- **Enforced**: CI pipeline fails below threshold
- **Reports**: Generated on every PR

---

## Future Test Enhancements

| Enhancement | Priority | Status |
|-------------|----------|--------|
| Property-based testing (Hypothesis) | Medium | Planned |
| Fuzz testing (random inputs) | Low | Backlog |
| Load testing (concurrent decisions) | Medium | Planned |
| Chaos testing (component failures) | Low | Backlog |
| A/B testing framework | Low | Backlog |
