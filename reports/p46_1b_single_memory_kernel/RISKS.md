# Risks

## FACTS

- Existing runtime write call sites still use `AgentMemoryLifecycle`.
- The canonical append operation checks duplicates before append but this focused implementation has not been multiprocess fault-tested.
- Malformed ledger rows fail closed and require operator-led recovery; they are not silently skipped.
- No exchange/FSM/runtime wiring exists in this kernel.

## INFERENCES

- Concurrent process writers require a later proven lock/transaction layer before runtime activation.
- Migrating active sessions without a write freeze could lose ordering or create duplicate migration records.

## ASSUMPTIONS

- Runtime activation remains blocked until migration and concurrency work pass review.

## UNKNOWNS

- Real historical data may expose legacy identity gaps requiring explicit quarantine rules.

