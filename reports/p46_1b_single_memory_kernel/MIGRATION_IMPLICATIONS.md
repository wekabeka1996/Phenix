# Migration Implications

## FACTS

- Current dashboard and lifecycle harness still instantiate `AgentMemoryLifecycle`; this task does not modify those unrelated runtime surfaces.
- P46 kernel performs no compatibility dual-write and does not scan legacy locations implicitly.
- Legacy artifacts can only be migrated by an explicit future reader/import command with provenance and idempotency.

## INFERENCES

Recommended later sequence:

1. stop new legacy writes at a declared session boundary;
2. inventory legacy documents read-only;
3. map each reflection/ACK/FSM reference to a canonical record with stable migration ID;
4. verify count, order, identity, and source references;
5. enable canonical writes at runtime;
6. retain legacy files immutable for audit.

## ASSUMPTIONS

- Active sessions can be cut over at an operator-approved boundary.

## UNKNOWNS

- The coordinator has not assigned the dashboard/harness migration patch or rollback window.

