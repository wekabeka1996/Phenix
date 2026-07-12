# Sizing Authority

## FACTS

- `PositionQueriesSizingAdapterV2` delegates to existing `PositionQueries.calculate_position_size`.
- Inputs are an internal `AgentIntentAuthoritySnapshotV2`: portfolio/account ref, reference price/market ref, config version, session/participant/lease/context/lifecycle state, and execution policy.
- Output is `AgentIntentSizingDecisionV2`: intent/sizing IDs, approval, derived quantity, price, account/market/config refs, risk checks, rejection reasons, timestamp.
- Missing account, price, or config produces `ACCOUNT_TRUTH_MISSING`, `MARKET_PRICE_MISSING`, or `SIZING_CONFIG_MISSING`; no quantity fallback exists.
- Instrument step/min constraints and per-symbol margin/leverage come through existing PositionQueries/config paths.
- Identical fixtures produce identical sizing output; risk rejection emits no downstream command.

## INFERENCES

- Quantity is Phenix-derived in the tested adapter, not caller-controlled.

## ASSUMPTIONS

- Future production provider will use authoritative DecisionMaking snapshots rather than IPC caller data.

## UNKNOWNS

- Production provider is absent. Existing helper fee buffer remains an implicit money-impacting default, so production processor is not wired.

