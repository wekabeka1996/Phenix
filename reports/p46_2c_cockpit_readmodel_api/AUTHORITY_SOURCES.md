# Authority Sources

## FACTS
- Session, participant, and lease records come from `TradingSessionAuthorityStore` deep-copy readers.
- Context and lifecycle are explicit injected readers returning typed source snapshots.
- The service does not scan reports/logs, mutate authority, create adapters, or emit commands.
- If the service is not composed, routes return `READ_MODEL_AUTHORITY_UNAVAILABLE` with 503.

## INFERENCES
- Injection keeps production authority ownership explicit and prevents fixture fallback.

## ASSUMPTIONS
- Runtime composition selects canonical memory and lifecycle projections.

## UNKNOWNS
- Cross-domain atomic locking is unavailable; per-component timestamps/references expose this boundary.
