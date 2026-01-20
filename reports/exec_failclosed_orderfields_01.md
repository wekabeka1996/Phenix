# Fail-Closed Order Field Hygiene Report (TASK: EXEC-FAILCLOSED-ORDERFIELDS-01)

## 1. Executive Summary
**Status**: Implemented Strict Validation in `ExecPosFSM`. The system no longer assumes "MARKET" if `order_type` is missing. Any intent with missing critical fields is now **Rejected** explicitly.

## 2. Changes Implemented
### ExecPosFSM (`_on_trade_intent_proposed`)
*   **Removed Default**: `get("order_type", "MARKET")` -> `get("order_type")`.
*   **Added Validation Gates**:
    *   **Gate 1**: `order_type` existence check.
    *   **Gate 2**: `LIMIT` Constraints (Must have `price` AND `tif`).
    *   **Gate 3**: `MARKET` Constraints (Must NOT have `tif`).
*   **Enhanced Error Handling**:
    *   Exceptions during processing now emit `EVT:TRADE_INTENT_REJECTED` with the exception message as the reason, plugging a potential "Black Hole".

## 3. Rejection Reasons (NRR)
New Negative Risk Response (NRR) codes introduced:
*   `NRR-INTENT-MISSING-ORDER_TYPE`
*   `NRR-INTENT-MISSING-PRICE`
*   `NRR-INTENT-MISSING-TIF`
*   `NRR-INTENT-INVALID-TIF`

## 4. Verification (Tests)
New test suite `tests/domains/execution_position/test_failclosed_validation.py` passed (6/6 scenarios):
1.  **Missing Type**: REJECTED (Correct Reason).
2.  **LIMIT No Price**: REJECTED.
3.  **LIMIT No TIF**: REJECTED.
4.  **MARKET With TIF**: REJECTED.
5.  **Valid MARKET**: PASSED (DEC:OPEN).
6.  **Valid LIMIT**: PASSED (DEC:OPEN).

## 5. Conclusion
The system is now fully **Fail-Closed** regarding order field composition. No more "Fail-Open Defaults". It is governed by explicit configuration/logic, not assumption.
