# Canonical Path

## FACTS

- Intended path remains V2 -> authority -> PositionQueries -> HTTP/TCP -> registered command -> one ExecPosFSM -> `ExecPosFSM.adapter`.
- Adapter construction reads testnet credentials and URL from loaded YAML/environment.
- P42 standalone lifecycle harness was not invoked.
- Preflight stopped before adapter construction.

## INFERENCES

- No duplicate execution authority was introduced by this package.

## ASSUMPTIONS

- P46-1F's disabled V1/EZE policy remains active.

## UNKNOWNS

- Real adapter behavior through this path remains unproven.
