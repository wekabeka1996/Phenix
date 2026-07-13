# Production Composition

## FACTS

Current `apps/reference/main.py` creates:

- one FSM/execution runtime;
- one unseeded `TradingSessionAuthorityStore`;
- V2 processor and ingress bridge.

It does not create canonical memory, context/lifecycle projections, or `RuntimeAuthorityQueryService`. No application composition edits were made.

## INFERENCES

Registering the query service with only session authority and mutable caches would falsely report compatibility.

## ASSUMPTIONS

Production readiness must remain false until all mandatory dependencies share one runtime generation.

## UNKNOWNS

The future shutdown ordering for a main-owned memory mutation service.
