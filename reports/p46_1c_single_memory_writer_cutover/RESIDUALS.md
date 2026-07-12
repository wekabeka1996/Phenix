# Residuals

## FACTS

- Historical `agent_trading_memory.json` artifacts are not migrated or deleted.
- Legacy compatibility is read-only and requires explicit absolute root.
- Multiprocess writer locking is not added or claimed.
- React Cockpit, AgentTradeIntentV2, sizing, FSM, exchange, and Testnet are unchanged.
- Context compressor, memory atoms, and decision ledger retain their distinct existing roles and paths.

## INFERENCES

- A future historical migration should be an explicit idempotent import package with source hashes, not dual-write.
- Multiprocess activation should wait for a dedicated contention/fault package.

## ASSUMPTIONS

- Operators preserve existing `.agent_memory` artifacts.

## UNKNOWNS

- Historical records with missing identity/version fields may require quarantine policy during migration.

