# Executive Summary: DOGEUSDT Split-Brain

**Issue**: `mean_reversion` strategy triggered an execution split-brain on DOGEUSDT, leaving positions unprotected or improperly tracked.

## Status Update (2026-03-13 repair package)

- The split-brain invariants are now repaired in code.
- Local reopen guard now lives in `apps/reference/domains/execution_position/fsm.py`, not in `fsm_open.py`.
- `ManageFlowFSM` now fail-closes entry-like fills that arrive over an already-active local lifecycle instead of silently swallowing them.
- TP/SL close matching now accepts the runtime `SL-<hash>`, `TP1-<hash>`, `TP2-<hash>` client-id forms and `client_order_id` payloads.
- `WS/order update loss` remains only `LIKELY`; the repair does not depend on proving that hypothesis.

## Observability Update (2026-03-13 P1 hardening)

- `EVT:EXECUTION_GUARD_BLOCKED` now carries structured guard context: `rid`, local state, portfolio truth, divergence flag, and explicit `block_reason`.
- `EVT:EXECUTION_DIVERGENCE_DETECTED` now separates split-brain telemetry from generic guard blocks.
- Exit matcher telemetry is now explicit through `EVT:EXIT_MATCH_ATTEMPTED` and `EVT:EXIT_MATCH_FAILED`, including raw ids, normalized ids, inferred role, and match reason.
- Cleanup/tidy is now explicitly non-business-close through `EVT:EXECUTION_TIDY_PERFORMED` plus enriched `EVT:SYMBOL_TIDY` payloads (`business_close_reconciled=false`).
- Business-valid reconcile is surfaced separately through `EVT:EXECUTION_CLOSE_RECONCILED`; tidy is no longer the only visible signal around cleanup/reconcile.
- These were additive telemetry changes only. Entry/exit/risk/strategy semantics were not changed in the P1 package.

## Root Causes Identified
1. **Architectural Desync (DM vs FSM)**:
    - `DecisionMaking` views the position via Exchange REST Portfolio syncs (`FLAT`).
    - `ExecutionPosition` (`ManageFlowFSM`) tracks state via WebSocket events (`TRACKING`).
    - **Result**: When WS drops an exit event (e.g., SL hit), DM sends a new `CMD:OPEN` while execution FSM still thinks it's managing the old position.
2. **Missing Local FSM Guards**:
    - `OpenFlowFSM.handle()` does not verify if `ManageFlowFSM.state != FLAT` before allowing a new entry.
    - When the new entry fill arrives over stale `TRACKING`, `ManageFlowFSM` can stay on the old local lifecycle route and suppress safe new-lifecycle bracket handling before bracket placement is even reached.

## Repair Outcome

- `ExecPosFSM.handle()` now blocks `CMD:OPEN` whenever the local execution lifecycle for the symbol is still active, including the `REST=FLAT` / `FSM=TRACKING` divergence window.
- `ManageFlowFSM.handle()` now emits an explicit guard failure for entry-like fills that would otherwise continue over stale local state.
- `ManageFlowFSM._handle_bracket_fill()` now reconciles valid TP/SL fills even when local tracking still holds the pre-ACK client order id instead of the exchange order id.
- `OrderGuardian.cleanup_orphans()` remains a tidy-only path; it was intentionally not turned into a business-close substitute.
- The old `_has_brackets()` suppressor theory is retired. The reproduced suppress-path was stale local `TRACKING` routing, not `_has_brackets()`.

## Remaining Unknowns

- No raw incident event sequence was recovered to upgrade `H1` (`WS/order update loss`) above `LIKELY`.
- The repair package is still safe without that proof because it now enforces the local execution invariants directly.
- Testnet/live incident chronology is still not reconstructible from raw WS payload evidence alone; the new observability surface reduces that blind spot for future incidents but does not retroactively prove the DOGEUSDT trigger chain.
