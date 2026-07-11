# Rejected Duplicates

## FACTS

- `AgentMemoryLifecycle` is rejected as future canonical authority because it rewrites a mutable aggregate and emits additional persisted summary/carryover files.
- `MemoryAtomStore` is rejected as canonical authority because updates append superseding atom versions and agent identity is optional.
- `DecisionLedger` is rejected because records are mutable per-file workflow state without complete agent/session identity.
- `SessionStore` is rejected as trading-memory authority; it remains the chat/session presentation store.
- Aurora scenario memory is rejected as Cockpit trading-memory authority; it is a bridge read model.
- Whole P41X/P41Y store imports are rejected because they combine memory with leases, commands, FSM dispatch, dashboard state, and reconciliation.
- P43A broad exception-to-default projection is rejected as a memory recovery rule.

## INFERENCES

- Aliasing any rejected writer behind `CanonicalMemoryStore` would hide dual authority rather than remove it.

## ASSUMPTIONS

- Legacy readers can be isolated without writes during migration.

## UNKNOWNS

- No runtime cutover test yet proves all old write call sites are disabled.

