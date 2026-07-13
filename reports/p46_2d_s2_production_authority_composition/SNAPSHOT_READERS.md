# Snapshot Readers

## Account

`DecisionMaking.latest_portfolio` receives runtime portfolio data. `CanonicalV2AuthorityProvider` attempts to read `latest_portfolio_ref`, but repository search finds no publisher/assignment for that attribute. Therefore account identity cannot survive into a production dry-run result.

## Market

`DecisionMaking.symbol_states[symbol]` can carry current price, timestamp, and optional `snapshot_ref`. Availability depends on upstream events and is fail-closed when missing/stale. No composition currently packages it with the required context/lifecycle versions.

## Decision

No network fetch or FastAPI fixture was introduced. Account identity publication and a stable market snapshot reader must be established in the main runtime before query-service readiness.
