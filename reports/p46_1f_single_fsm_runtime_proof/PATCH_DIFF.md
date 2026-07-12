# Patch Diff

## FACTS

- Aligned the existing registered external-open schema with additive V2 trace fields and snapshot form.
- Added strict unknown-command and duplicate-registry rejection to the canonical registry path.
- Added explicit legacy execution route policy and isolated HTTP/TCP legacy bypasses.
- Added bridge envelope/handler observability counters.
- Added deterministic production-component runtime harness and focused tests.
- No FSM guard, execution flow, exchange adapter, Cockpit, provider, or sizing algorithm was rewritten.

## INFERENCES

- Changes close only contract and path ambiguity proven by the harness.

## ASSUMPTIONS

- V1 compatibility source remains useful for offline migration tests.

## UNKNOWNS

- None affecting the reported single-FSM proof.
