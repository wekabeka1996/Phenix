# Post-Sunset Sanity Report (TASK: POST-SUNSET-SANITY-01)

## 1. Static Analysis: Single Consumer Verified
We confirmed that `ExecPosFSM` is the **sole** runtime consumer of `EVT:TRADE_INTENT_PROPOSED`.

*   **Runtime Listeners**:
    *   `apps/reference/domains/execution_position/fsm.py:282`: `self.bus.listen("EVT:TRADE_INTENT_PROPOSED", self._on_trade_intent_proposed)`
    *   No other runtime listeners found (grep returned only docs/mocks).
*   **AuroraBridge Code**: Removed. No instance specific references in `main.py` or domain code.
*   **Direct Calls**: No `execution_position.handle()` calls found in `main.py` or other domains.

## 2. Invariant Verification (Tests)
New regression tests (`tests/e2e/test_e2e_intent_single_attempt_by_rid.py`) verified the following invariants:

| Invariant | Test Scenario | Result |
|---|---|---|
| **Deduplication** | Submit same RID twice | **PASSED**. 2nd attempt rejected with `IDEMPOTENCY_FAIL`. |
| **No Black Holes** | Submit failed intent | **PASSED**. `ExecPosFSM` emitted `EVT:TRADE_INTENT_REJECTED` instead of silence. |
| **Routing** | Submit `reduce_only=True` | **PASSED**. Routed to `CLOSE` flow (DEC:CLOSE). |

## 3. Forensics Analysis (WAL)
Ran `tools/forensics/rid_duplicates_report.py` on existing WAL logs:
*   **Duplicates**: Found 1 synthetic test RID (`RID-E2E-INTENT-1`) with multiple CMD:OPENs (expected due to iterative testing). No organic duplicates.
*   **Black Holes**: Found 8 legacy RIDs (e.g. `9b920...`) that stalled after `PROPOSED`. This confirms the "Black Hole" issue existed prior to this fix. The new logic (Invariant 2) ensures this will not happen going forward.

## 4. Market-Era Hygiene
*   **Hardcodes**: Verified that `MARKET` order type usage is a "Fail-Open Default" (defaults to MARKET if missing), not a prohibition of LIMIT.
*   **Silent Fallbacks**: Identified and accepted default behavior. Future improvements could enforce strict `order_type`.

## 5. Conclusion
 The system is **Sanity Checked**. 
*   **Bridge**: GONE.
*   **Safety**: REINFORCED (Explicit Rejects).
*   **Logic**: SSOT in `ExecPosFSM`.

Ready for deployment.
