# Tech Debt Delta

## FACTS

- RETIRED: P38C callable-only gap where preflight/ACK existed but nothing persisted them into a session cycle.
- CONVERTED_TO_RUNTIME_CHECK: Missing required instruction files now appear in persisted refresh/ACK event metadata as `missing_required_files`.
- MITIGATED: Duplicate refresh noise is avoided on unchanged cycles while ACK heartbeat remains attributable.
- DEFERRED_WITH_REASON: Live scheduler integration is deferred because Agent 5 owns runtime cycle invocation.
- DEFERRED_WITH_REASON: Dashboard/API endpoint is deferred because Python callable is sufficient and lower risk for MVP integration.

## INFERENCES

- Event-ledger persistence is enough for first runtime truth without adding a new table or daemon.

## ASSUMPTIONS

- Agent runtime can read `recommended_cadence_seconds` and schedule accordingly.

## UNKNOWNS

- Whether the coordinator wants a later dashboard route for manual operator-triggered refresh.
