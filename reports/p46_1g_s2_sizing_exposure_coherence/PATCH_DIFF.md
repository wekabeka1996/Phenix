# Patch Diff

## FACTS

- Config/Pydantic: required fee buffer and snapshot freshness policy.
- Sizing: explicit fee passed through PositionQueries; hidden active default removed.
- V2/authority: timestamp freshness, config/sizing lineage.
- Execution contracts: additive registry and `CMD:OPEN` lineage fields; exposure decision identity.
- Proof harness: 11 USDT post-buffer target projection, full risk-aware symbol preflight, canonical LeverageService, separate opening/cleanup counters.
- Tests: focused S2 boundary, stale-data, units, config, and zero-adapter rejection coverage plus updated fixtures.
- Reports: compact S2 forensic/runtime evidence package.
- Production soft limits, operator cap, exchange adapter implementation, FSM authority, and caller no-quantity contract were not weakened.

## INFERENCES

- Changes are limited to the proven sizing/guard/freshness/trace seams.

## ASSUMPTIONS

- Runtime logs remain ignored and are not commit artifacts.

## UNKNOWNS

- Commit SHAs are recorded after narrow commits are created.
