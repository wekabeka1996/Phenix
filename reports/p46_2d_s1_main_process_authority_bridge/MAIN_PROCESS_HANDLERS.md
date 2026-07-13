# Main-Process Handlers

## FACTS

- `RuntimeAuthorityQueryService` accepts explicit `PhenixReadModelService` and `ProposalDryRunService` instances.
- It rejects composition when those services do not share the exact same `TradingSessionAuthorityStore` object.
- Request IDs are idempotent; conflicting payload reuse returns `QUERY_ID_CONFLICT`.
- Pure dry-run delegates to the existing P46-2D service and preserves its zero-side-effect result.
- `LLMIntentIngressBridge` routes `QUERY:*` before command counters or FSM emissions.

## UNKNOWNS

Production `apps/reference/main.py` currently constructs authority and V2 sizing but does not expose a canonical runtime context/lifecycle reader or pure exposure preview. The query service is therefore not attached there; absent handler returns `QUERY_HANDLER_UNAVAILABLE`. This is deliberate fail-closed behavior, not a fixture substitution.
