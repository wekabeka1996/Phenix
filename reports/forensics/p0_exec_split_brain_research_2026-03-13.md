# P0 Execution Split-Brain Research: DOGEUSDT `mean_reversion`

**Date**: 2026-03-13
**Author**: Principal Forensic Systems Engineer
**Status**: Research Package Complete

## 1. Incident Overview
A split-brain scenario occurred on DOGEUSDT within the `mean_reversion` strategy execution. The system exhibited a desynchronization between the actual exchange state (via polling/OrderGuardian) and the internal `ManageFlowFSM` tracking the position.

## 2. Phase 1: Codebase Traversal (Static Forensics)
Analysis of the `execution_position` domain revealed:
- **`ExecPosFSM.handle()` routing**: Delegates `CMD:OPEN` to `OpenFlowFSM` and `EVT:TRADE_EXECUTED` to `ManageFlowFSM`.
- **`DecisionMaking` SSOT Mismatch**: `DecisionMaking` uses a portfolio-centric view via `check_symbol_is_flat()`. If the exchange API reports `FLAT`, DM emits a new `CMD:OPEN`.
- **`OpenFlowFSM` Guards**: The "one-open-order" guard in `OpenFlowFSM` only checks for *pending* entry orders. It DOES NOT verify if `ManageFlowFSM` is currently in a `TRACKING` state for an active position.
- **`ManageFlowFSM` Logic**: `ManageFlowFSM` places SL/TP brackets immediately after the first `ENTRY` fill. If it misses a bracket fill (WebSocket drop), it remains stuck in `TRACKING` state.

## 3. Phase 2: Log-to-Code Reconstruction
A search of the logging directory retrieved multiple `MR_SIGNAL` emissions for `DOGEUSDT` (`SELL`) in `domain_mean_reversion.log` with high confidence (>0.85). 
- **Missing Link**: Execution logs for the exact timeframe were rotated/rolled out or missing `DOGEUSDT`-specific traces (due to standard INFO/DEBUG log culling).
- **Inferred Sequence**: The high frequency of MR signals coupled with the code review strongly implies a scenario where FSM lost track of an exit fill while DM saw the position as FLAT.

## 4. Phase 3: Deterministic Hypotheses (Simulation)
Created `tests/domains/execution_position/test_split_brain_repro.py` to deterministically simulate the core bugs.

### Scenario B: The "DM-Override" Split Brain
1.  **Context**: A position is open. Bracket placed.
2.  **Trigger**: SL fills on the exchange. FSM misses the WS update (Order Loss).
3.  **Divergence**: 
    - FSM `ManageFlow` remains `TRACKING`.
    - FSM `Watchdog` / `OrderGuardian` might poll it eventually, but meanwhile, DM triggers a REST portfolio sync.
    - DM sees `FLAT` on exchange. Emits `CMD:OPEN`.
4.  **Failure**: FSM `OpenFlow` approves `CMD:OPEN` (no pending entries). New position opens. `TRADE_EXECUTED` routes to `ManageFlowFSM`. `ManageFlowFSM` already has `self.sl_order_id`, so it ignores bracket placement, leaving the new position **unprotected**.

### Scenario D: Watchdog Polling Race
A secondary fix was observed in `fsm.py` where Watchdog polling emits `EVT:TRADE_EXECUTED` to unblock `OrderIndex`. If this races with the actual WS `TRADE_EXECUTED`, multiple `CMD:CLOSE` paths could be triggered erroneously, breaking idempotency.

## 5. Summary & Remediation (No Fixes Applied Yet)
The split-brain is primarily caused by **un-synchronized state management** between the DM's Portfolio Cache and execution's internal FSM.
- **DM**: Relies purely on remote portfolio state.
- **FSM Manage**: Relies purely on local event state machines.
If an event drops, DM sends orders the FSM Manage flow does not expect.
