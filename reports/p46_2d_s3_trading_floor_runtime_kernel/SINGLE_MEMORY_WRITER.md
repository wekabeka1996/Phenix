# Single Memory Writer

## FACTS

- P46-1C verdict: `P46_1C_SINGLE_MEMORY_WRITER_CUTOVER_VALIDATED`.
- Dashboard mutation calls use `CanonicalMemoryRuntime`, whose sole durable mutation is `CanonicalMemoryStore.append`.
- Active dashboard calls include rationale, instruction ACK, and FSM decision appends.
- `CanonicalMemoryStore.append` checks record identity and sequence but has no cross-process ownership lock.
- P46-1C residuals explicitly state multiprocess writer locking was not added or claimed.

## INFERENCES

Constructing the same store in main is not a safe migration. It creates concurrent-writer risk even if both classes have the same name and config.

## ASSUMPTIONS

Historical ledgers must stay untouched during a future migration.

## UNKNOWNS

Whether deployment currently exercises dashboard mutation routes continuously.

## Blocker

An atomic main-owner cutover requires an exclusive writer lease and a bounded dashboard mutation client. Neither exists in the approved baseline.
