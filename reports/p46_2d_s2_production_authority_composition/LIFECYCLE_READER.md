# Lifecycle Reader

## FACTS

`ExecPosFSM` owns live position/order/exposure internals and startup reconciliation. Inflight reconciliation and lifecycle logging exist as separate surfaces. No single read-only API emits positions, open orders, pending intents, pending commands, recent FSM decisions, reconciliation state/divergence/timestamp, and stable source references.

Historical WAL/log parsing is explicitly forbidden as current truth. Direct reads of private mutable FSM dictionaries would not provide a stable, thread-safe projection contract.

## Decision

No lifecycle adapter was fabricated. A bounded snapshot method must first be added to the canonical FSM/reconciliation owner with explicit synchronization and source identity semantics.
