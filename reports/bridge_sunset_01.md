# Bridge Sunset Report (TASK: BRIDGE-SUNSET-01)

## 1. Executive Summary
**Status**: `AuroraBridge` has been permanently removed from the runtime (`main.py`). The system is now operating with a **Single Source of Truth (SSOT)** for trade intent processing: `ExecPosFSM`.

### Key Changes
*   **Removed**: `class AuroraBridge`, global instance `_bridge_instance`, and all associated global handlers (`on_trade_intent_proposed`, `on_portfolio_state_updated`, `on_intent_deferred`).
*   **Enhanced**: `ExecPosFSM` now listens directly to `EVT:TRADE_INTENT_PROPOSED`.
*   **Routed**: `ExecPosFSM` now intelligently routes logic based on `reduce_only` flag (OPEN vs CLOSE flows).
*   **Feedback**: `ExecPosFSM` now emits `EVT:TRADE_INTENT_REJECTED` on failure and `DEC:OPEN/CLOSE` on success to the bus.

## 2. New Architecture Flow
| Step | Action | Owner |
|---|---|---|
| 1. Input | `EVT:TRADE_INTENT_PROPOSED` | `DecisionMaking` |
| 2. Consumer | `_on_trade_intent_proposed` (Listener) | `ExecPosFSM` (Single Consumer) |
| 3. Routing | Check `reduce_only` flag | `ExecPosFSM` |
| 4. Execution | `handle(CMD:OPEN)` or `handle(CMD:CLOSE)` | `ExecPosFSM` (Guards + Flow) |
| 5. Output | `DEC:OPEN` / `DEC:CLOSE` (Success) or `EVT:TRADE_INTENT_REJECTED` (Failure) | `ExecPosFSM` (Bus Emission) |

## 3. Test Verification
The E2E test `tests/e2e/test_e2e_bridge_intent_to_execpos_dec_open.py` was updated to reflect the new architecture (removing Bridge dependency) and verified:

*   **Test 1 (OPEN)**: `TRADE_INTENT_PROPOSED` (Buy) -> `ExecPosFSM` -> `DEC:OPEN` (Bus). **PASSED**.
*   **Test 2 (CLOSE)**: `TRADE_INTENT_PROPOSED` (Sell, reduce_only=True) -> `ExecPosFSM` -> `DEC:CLOSE` (Bus). **PASSED**.

## 4. Operational Notes
*   **No Stale Portfolio Gate**: The "Black Hole" gate is gone. `ExecPosFSM` relies on its own `ExposureGuard` which uses internal portfolio state but fails gracefully or explicitly rejects, rather than silently deferring.
*   **Logs**: Look for `[ExecPosFSM] ... Processing TRADE_INTENT -> CMD:OPEN` in logs. Failures will show `Execution Rejected`.

## 5. Next Steps
*   **Monitor**: Watch for `EVT:TRADE_INTENT_REJECTED` in production logs to catch any configuration issues (e.g. leverage missing) that were previously hidden by Bridge deferrals.
*   **Cleanup**: Verify `main.py` diffs to ensure no other legacy bindings exist (Completed).
