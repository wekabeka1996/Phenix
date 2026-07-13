# Ownership Decision

## Decision

`OWNERSHIP_CONFLICT_UNRESOLVED`

## FACTS

- Main already owns FSM and execution lifecycle.
- P46-1C selected terminal-agent runtime consumers for canonical-memory mutation.
- Dashboard production code constructs the store lazily and performs active appends.
- The store does not reject a second process opening the same root.
- No production main-to-dashboard or dashboard-to-main canonical memory mutation protocol exists.

## INFERENCES

`MAIN_PROCESS_CANONICAL_OWNER` is the preferred end state but is not presently proven. Selecting it now would contradict the validated P46-1C construction and violate the one-writer law.

## ASSUMPTIONS

Disabling dashboard writes is behavior loss unless replaced by an approved client path.

## UNKNOWNS

The operator-approved migration boundary and deployment cutover order.

## Required Next Decision

Approve a bounded memory ownership migration: main-process writer lease, mutation protocol, dashboard client conversion, and rollback/version handshake as one atomic package.
