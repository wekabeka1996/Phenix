# Duplication Check

## Decision

`EXISTING_SIZING_AUTHORITY_REQUIRES_NARROW_ADAPTER`

## FACTS

- No pre-existing `AgentTradeIntentV2` was found.
- V1 request, dry-run/proposal contracts, and deprecated DeepSeek compiler exist but accept or derive executable quantity and are not V2 equivalents.
- `PositionQueries` already owns margin-first sizing and calls existing pure sizing helpers.
- Execution-position already owns quantity normalization, instrument guards, lifecycle FSM, and adapter boundary.
- The patch creates no second FSM ingress, exchange adapter, risk engine, or quantity normalizer.
- V2 approved output reuses registered `CMD:EXTERNAL_OPEN_REQUEST_V1`.

## INFERENCES

- A narrow adapter is appropriate; another sizing framework would duplicate active logic.

## ASSUMPTIONS

- A future authority provider can expose session/lease/context and authoritative DM snapshots without moving ownership.

## UNKNOWNS

- Existing `fee_buffer=0.001` default in margin-first helpers is not currently represented in instrument YAML and blocks production compliance.

