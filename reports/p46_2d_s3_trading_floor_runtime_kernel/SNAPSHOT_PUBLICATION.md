# Snapshot Publication

## FACTS

- `CanonicalV2AuthorityProvider` reads `decision_making.latest_portfolio`, `latest_portfolio_ref`, and symbol-state `snapshot_ref`.
- No assignment to `latest_portfolio_ref` was found in `apps/reference`.
- Market snapshot references are optional cache content rather than a guaranteed publication contract.
- Queries/dry-runs must not call the exchange to repair missing identity.

## INFERENCES

Current anonymous mutable caches cannot be promoted to immutable account/market truth by an adapter alone.

## ASSUMPTIONS

Publication belongs on the existing portfolio/features update paths once ownership and schema are approved.

## UNKNOWNS

The canonical source kind and version identity for account snapshots.
