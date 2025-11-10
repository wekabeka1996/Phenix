# 🧪 Phase 3 TODO 3: Full Integration Test Suite

**Status**: READY TO START 🚀
**Previous Phase**: Phase 3 TODO 1-2 COMPLETE ✅ (52/52 tests passing)
**Estimated Duration**: 40-50 minutes
**Test Target**: 60+ tests with >90% code coverage

---

## 📋 Overview

Phase 3 TODO 3 is the **final validation step** for bracket order error recovery. It creates comprehensive integration tests that mock realistic Binance API response sequences to verify:

1. ✅ All 5 error codes trigger correct recovery strategies
2. ✅ Recovery strategies are executed in correct order
3. ✅ Successful recovery after errors
4. ✅ Graceful failure when retries exhausted
5. ✅ Proper logging of recovery attempts
6. ✅ No side effects or state corruption

---

## 🎯 Test Scenarios

### Scenario 1: Error -2021 (Order Would Immediately Trigger)
**Sequence**:
1. Place bracket order
2. Binance returns `-2021` error
3. FSM detects error, calls `_handle_bracket_error()`
4. Handler: wait 0.2s, retry same order
5. Binance returns success with `orderId: 123456`
6. FSM logs recovery and continues

**Validation Points**:
- ✅ Error detected and logged
- ✅ Retry sleep executed (0.2s)
- ✅ Order retried without modification
- ✅ Success response captured
- ✅ No qty/price changes

**Mock Responses**:
```python
# First call: error
mock_post.side_effect = [
    Mock(status_code=400, json=lambda: {"code": -2021, "msg": "Order would immediately trigger"}),
    Mock(status_code=200, json=lambda: {"orderId": 123456, "clientOrderId": "test-id-1"}),
]
```

---

### Scenario 2: Error -4116 (Duplicate ClientOrderId)
**Sequence**:
1. Place bracket order with `clientOrderId: "test-id-1"`
2. Binance returns `-4116` error (duplicate ID detected)
3. FSM detects error, calls `_handle_bracket_error()`
4. Handler: generate new deterministic `clientOrderId`
5. Retry order with new ID: `clientOrderId: "test-id-1-retry-1"`
6. Binance returns success with new ID

**Validation Points**:
- ✅ Error detected
- ✅ New clientOrderId generated (deterministic)
- ✅ Retry uses new ID
- ✅ Success response captured
- ✅ Old ID not reused

**Mock Responses**:
```python
mock_post.side_effect = [
    Mock(status_code=400, json=lambda: {"code": -4116, "msg": "Duplicate clientOrderId"}),
    Mock(status_code=200, json=lambda: {"orderId": 123457, "clientOrderId": "test-id-1-retry-1"}),
]
```

---

### Scenario 3: Error -4137 (Quantity Not Allowed)
**Sequence**:
1. Place bracket order with `quantity: 100`
2. Binance returns `-4137` error (quantity violates rules)
3. FSM detects error, calls `_handle_bracket_error()`
4. Handler: reduce qty by 10%: `quantity: 90`
5. Retry order with reduced qty
6. Binance returns success

**Validation Points**:
- ✅ Error detected
- ✅ Qty reduced by exactly 10%
- ✅ Retry uses new qty
- ✅ Success response captured
- ✅ Price not changed

**Mock Responses**:
```python
mock_post.side_effect = [
    Mock(status_code=400, json=lambda: {"code": -4137, "msg": "Quantity not allowed"}),
    Mock(status_code=200, json=lambda: {"orderId": 123458, "quantity": "90"}),
]
```

---

### Scenario 4: Error -4164 (MIN_NOTIONAL Not Satisfied)
**Sequence**:
1. Place bracket order with `quantity: 10` (notional too low)
2. Binance returns `-4164` error (minimum notional not met)
3. FSM detects error, calls `_handle_bracket_error()`
4. Handler: increase qty by 10%: `quantity: 11`
5. Retry order with increased qty
6. Binance returns success

**Validation Points**:
- ✅ Error detected
- ✅ Qty increased by exactly 10%
- ✅ Retry uses new qty
- ✅ Success response captured
- ✅ Price not changed

**Mock Responses**:
```python
mock_post.side_effect = [
    Mock(status_code=400, json=lambda: {"code": -4164, "msg": "MIN_NOTIONAL not satisfied"}),
    Mock(status_code=200, json=lambda: {"orderId": 123459, "quantity": "11"}),
]
```

---

### Scenario 5: Error -429 (Rate Limit Exceeded) - SUCCESS AFTER RETRIES
**Sequence**:
1. Place bracket order
2. Binance returns `-429` error (rate limit)
3. FSM detects error, calls `_handle_bracket_error()`
4. Handler: wait with exponential backoff + jitter (attempt 0)
5. Retry order (still rate limited)
6. Handler: wait with backoff (attempt 1)
7. Retry order (still rate limited)
8. Handler: wait with backoff (attempt 2)
9. Retry order → SUCCESS

**Validation Points**:
- ✅ Error detected 3 times
- ✅ Each retry has exponential backoff
- ✅ Jitter applied to backoff time
- ✅ Final retry succeeds
- ✅ Success response captured
- ✅ All 3 attempts logged

**Mock Responses**:
```python
mock_post.side_effect = [
    # Attempt 1
    Mock(status_code=429, json=lambda: {"code": -429, "msg": "Too many requests"}),
    # Attempt 2
    Mock(status_code=429, json=lambda: {"code": -429, "msg": "Too many requests"}),
    # Attempt 3 (Success)
    Mock(status_code=200, json=lambda: {"orderId": 123460, "clientOrderId": "test-id-5"}),
]
```

---

### Scenario 6: Error -429 (Rate Limit Exceeded) - ALL RETRIES FAIL
**Sequence**:
1. Place bracket order
2. Binance returns `-429` error (rate limit)
3. FSM detects error, retries with backoff (attempt 1)
4. Still `-429` (attempt 2)
5. Still `-429` (attempt 3)
6. Max retries reached → RuntimeError raised

**Validation Points**:
- ✅ Error detected 3 times
- ✅ Each retry has exponential backoff
- ✅ RuntimeError raised after max attempts
- ✅ Error message contains attempt count
- ✅ Failed order logged with all retry info

**Mock Responses**:
```python
mock_post.side_effect = [
    Mock(status_code=429, json=lambda: {"code": -429, "msg": "Too many requests"}),
    Mock(status_code=429, json=lambda: {"code": -429, "msg": "Too many requests"}),
    Mock(status_code=429, json=lambda: {"code": -429, "msg": "Too many requests"}),
]
```

---

## 📝 Test File Structure

### File: `test_phase3_todo3_integration.py` (NEW)

```python
# Imports
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from decimal import Decimal

# Fixtures
@pytest.fixture
def mock_binance_adapter():
    """Create mocked BinanceExecutionAdapter"""
    # Mock implementation details

@pytest.fixture
def mock_config():
    """Create mocked config with test symbols"""
    # Mock config

@pytest.fixture
async def fsm_instance(mock_config):
    """Create FSM instance with mocked dependencies"""
    # Setup FSM

# Test Classes
class TestErrorCode2021IntegrationSequence:
    """Error -2021: Order would immediately trigger"""
    async def test_single_retry_succeeds()
    async def test_error_and_success_logged()

class TestErrorCode4116IntegrationSequence:
    """Error -4116: Duplicate ClientOrderId"""
    async def test_new_client_order_id_generated()
    async def test_retry_with_new_id_succeeds()

class TestErrorCode4137IntegrationSequence:
    """Error -4137: Quantity not allowed"""
    async def test_quantity_reduced_by_10_percent()
    async def test_retry_with_reduced_qty_succeeds()

class TestErrorCode4164IntegrationSequence:
    """Error -4164: MIN_NOTIONAL not satisfied"""
    async def test_quantity_increased_by_10_percent()
    async def test_retry_with_increased_qty_succeeds()

class TestErrorCode429IntegrationSequence:
    """Error -429: Rate limit (success after retries)"""
    async def test_backoff_increases_per_attempt()
    async def test_three_attempts_then_success()

class TestErrorCode429ExhaustedSequence:
    """Error -429: Rate limit (all retries fail)"""
    async def test_runtime_error_after_max_attempts()
    async def test_all_retry_attempts_logged()

class TestIntegrationMetricsLogging:
    """Verify logging of recovery metrics"""
    async def test_recovery_attempt_logged()
    async def test_success_after_recovery_logged()

class TestIntegrationStateConsistency:
    """Verify no state corruption during recovery"""
    async def test_order_state_consistent_after_error()
    async def test_brackets_not_duplicated_on_retry()

class TestIntegrationEdgeCases:
    """Edge cases and corner scenarios"""
    async def test_rapid_error_sequences()
    async def test_mixed_error_types_in_bracket_order()
```

---

## ✅ Validation Checklist

- [ ] All 6 test scenarios pass
- [ ] 60+ cumulative tests pass (52 previous + 8-10 new)
- [ ] Code coverage > 90% for:
  - `_handle_bracket_error()` method
  - `_emit_place_order()` method
  - Error detection logic in binance_execution_adapter.py
- [ ] No regressions in previous phases
- [ ] All mocks properly configured
- [ ] All logging assertions pass

---

## 🏃 Implementation Order

1. **Create test file skeleton** (5 min)
2. **Implement fixtures** (10 min)
   - Mock BinanceExecutionAdapter
   - Mock config with test symbols
   - Create FSM instance
3. **Implement test scenarios** (25 min)
   - Error -2021 (2 tests)
   - Error -4116 (2 tests)
   - Error -4137 (2 tests)
   - Error -4164 (2 tests)
   - Error -429 success (2 tests)
   - Error -429 exhausted (2 tests)
4. **Add edge case tests** (8 min)
   - Metrics & logging
   - State consistency
   - Rapid sequences
5. **Run full test suite** (5 min)
   - Verify 60+ tests pass
   - Check coverage > 90%
   - Review any failures

---

## 📊 Expected Results

```
test_phase3_todo3_integration.py::TestErrorCode2021IntegrationSequence::test_single_retry_succeeds PASSED
test_phase3_todo3_integration.py::TestErrorCode2021IntegrationSequence::test_error_and_success_logged PASSED
test_phase3_todo3_integration.py::TestErrorCode4116IntegrationSequence::test_new_client_order_id_generated PASSED
test_phase3_todo3_integration.py::TestErrorCode4116IntegrationSequence::test_retry_with_new_id_succeeds PASSED
test_phase3_todo3_integration.py::TestErrorCode4137IntegrationSequence::test_quantity_reduced_by_10_percent PASSED
test_phase3_todo3_integration.py::TestErrorCode4137IntegrationSequence::test_retry_with_reduced_qty_succeeds PASSED
test_phase3_todo3_integration.py::TestErrorCode4164IntegrationSequence::test_quantity_increased_by_10_percent PASSED
test_phase3_todo3_integration.py::TestErrorCode4164IntegrationSequence::test_retry_with_increased_qty_succeeds PASSED
test_phase3_todo3_integration.py::TestErrorCode429IntegrationSequence::test_backoff_increases_per_attempt PASSED
test_phase3_todo3_integration.py::TestErrorCode429IntegrationSequence::test_three_attempts_then_success PASSED
test_phase3_todo3_integration.py::TestErrorCode429ExhaustedSequence::test_runtime_error_after_max_attempts PASSED
test_phase3_todo3_integration.py::TestErrorCode429ExhaustedSequence::test_all_retry_attempts_logged PASSED
test_phase3_todo3_integration.py::TestIntegrationMetricsLogging::test_recovery_attempt_logged PASSED
test_phase3_todo3_integration.py::TestIntegrationStateConsistency::test_order_state_consistent_after_error PASSED
...

=============== 62/62 PASSED in 1.23s ===============
Coverage: execution_position/binance_execution_adapter.py 92%
Coverage: execution_position/fsm_manage.py 88%
```

---

## 🔗 Related Files

- `apps/reference/domains/execution_position/binance_execution_adapter.py` - Implementation (to be tested)
- `apps/reference/domains/execution_position/fsm_manage.py` - Implementation (to be tested)
- `test_phase3_retry_logic.py` - Previous tests (41 tests baseline)
- `test_phase3_todo2_fsm_params.py` - Previous tests (11 tests)
- `TODO_PHASE3_TP_SL_FIX.md` - Overall progress tracker

---

## 📌 Notes

- **Key Focus**: Mock realistic Binance response sequences, not just unit test individual methods
- **Backoff Validation**: Verify exponential formula and jitter range (0.8x to 1.2x)
- **Logging Assertions**: Check that recovery attempts are logged with proper context
- **State Safety**: Ensure retries don't leave FSM in inconsistent state

---

**Ready to Start**: Phase 3 TODO 3 Implementation 🚀
**Next Command**: `pytest test_phase3_todo3_integration.py -v` (after file created)

