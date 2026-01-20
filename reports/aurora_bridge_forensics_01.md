# AuroraBridge Forensics Report (TASK: AURORA-BRIDGE-FORENSICS-01)

## 1. Inventory & Architecture

**Definition**: `AuroraBridge` is defined in `apps/reference/main.py` (lines 92-630) and instantiated in the main startup sequence.
**Role**: Middleware to bridge `v1` Intents (`EVT:TRADE_INTENT_PROPOSED`) to `v2` Execution (`CMD:OPEN/CLOSE`), enforcing QoS and Portfolio Freshness.

### Event-Command Map
| Input Event | Internal Gates | Output | Target |
|---|---|---|---|
| `EVT:TRADE_INTENT_PROPOSED` | 1. QoS Gate (Rate Limit)<br>2. Portfolio State Gate (TTL)<br>3. Capacity Gate (Notional Check) | `CMD:OPEN` (or `CMD:CLOSE`) | `ExecPosFSM` (Direct Call) + `fsm` Bus (Emit) |
| `EVT:PORTFOLIO_STATE_UPDATED` | Updates `_last_portfolio` & `ts` | N/A | Internal State |
| `EVT:INTENT_DEFERRED` | Retry Scheduler | Re-emits `EVT:TRADE_INTENT_PROPOSED` | Self (Loopback) |

### Synchronization Model
*   **Dual Dispatch**: The bridge both *emits* `CMD:OPEN` to the bus (Fire-and-forget) AND *calls* `execution_position.handle()` directly (Synchronous execution).
*   **Global Variable Dependency**: Relies on `global execution_position` in `main.py` for direct calls, bypassing the event bus for the critical path.

## 2. Runtime Analysis ("Alive or Dead")

**Runtime Status**: `ALIVE` but `STARVED`.
*   **WAL Analysis (`ops/wal/2026-01-13.jsonl`)**:
    *   `EVT:ACCOUNT_UPDATE_RECEIVED`: **Present**. The system receives data from Binance.
    *   `EVT:PORTFOLIO_STATE_UPDATED`: **Absent from WAL**. *Note: This event is transient (emitted by PositionTracking but not persisted). Its absence in WAL is expected, but lack of downstream bridge logs suggests flow issues.*
    *   `EVT:TRADE_INTENT_PROPOSED`: **Absent from WAL**. *Critical: No trade intents were persisted in the analyzed session, suggesting `DecisionMaking` did not trigger or failed to persist.*
    *   **Bridge Logs**: No `BRIDGE:` entries found in the analyzed tail, consistent with zero input intents.

**Conclusion**: The Bridge logic is active in code, but no traffic passed through it in the reviewed session, likely due to upstream silence (`DecisionMaking`).

## 3. Policy Analysis (Toxic Behaviors)

1.  **Stale Portfolio Blocking ("The Black Hole")**:
    *   **Policy**: Blocks ANY trade if `PORTFOLIO_STATE_UPDATED` hasn't been received within TTL (config usually 30-60s).
    *   **Risk**: If `AccountConnector` is flaky or `PositionTracking` fails to emit updates (e.g., during "Hybrid" mode or network timeouts), the Bridge silently defers trades indefinitely.
    *   **Loop**: `Defer` -> `Wait` -> `Retry` -> `Defer`. Logs `BRIDGE: Deferred ... (portfolio stale)`.

2.  **No REJECT Emission**:
    *   **Behavior**: When gates fail (QoS, Stale), it emits `EVT:INTENT_DEFERRED` or `EVT:INTENT_DROPPED`.
    *   **Violation**: It **NEVER** emits `EVT:TRADE_INTENT_REJECTED`. Strategy/DecisionMaking never learns that the order failed, potentially leading to state desynchronization.

3.  **Global Variable Coupling**:
    *   The direct call `execution_position.handle()` couples the Bridge to the specific `main.py` instance structure, making it hard to test in isolation without heavy mocking (as seen in `test_e2e_...`).

## 4. Test Coverage

**Coverage Map**: mixed/green.
*   `tests/e2e/test_e2e_bridge_intent_to_execpos_dec_open.py`: **High**. Validates the full flow. *Crucially, it mocks `execution_position` to verify the direct call path.*
*   `tests/integration/test_bridge_capacity_gate.py`: **High**. Tests logic for max notional blocking.
*   `tests/domains/position_tracking/test_task47_disable_stale_gate.py`: **High**. Verifies debug overrides.
*   **Missing**: Tests for `REJECT` mapping (because the feature is missing).

## 5. Decision & Recommendation

**Verdict**: The `AuroraBridge` is an over-engineered relic that duplicates `ExecPosFSM` guards (Exposure) and introduces fragility (Stale Gate) without providing proper feedback (REJECT events). My recent hotfix (Direct Listener in ExecPosFSM) proved that bypassing the Bridge restores functionality immediately.

**Recommendation A: Kill Bridge (Adopted Strategy)**

**Rationale**:
1.  **Simplicity**: `ExecPosFSM` now owns the `PROPOSED` -> `EXECUTED` flow directly.
2.  **Reliability**: Bypasses the flaky "Stale Portfolio" gate (relying instead on `ExecPosFSM`'s internal ExposureGuard which is robust).
3.  **SSOT**: Removes the split-brain where Bridge decides "Can we trade?" (Gate) and FSM decides "Can we trade?" (Guard).

**Required Actions (Delta Plan)**:
1.  **Refactor `_on_trade_intent_proposed`**: Update the handler in `ExecPosFSM` to route `reduce_only: true` intents to `CMD:CLOSE` flow (currently routes all to `CMD:OPEN`).
2.  **Deprecate Bridge**: Remove `AuroraBridge` instantiation from `main.py` to prevent duplicate processing (once FSM handles everything).
3.  **Implement REJECT in FSM**: Ensure `ExecPosFSM` emits `TRADE_INTENT_REJECTED` if execution fails (already started in recent cleanup).
