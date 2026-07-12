# V2 Authority Integration

## FACTS

- Validation order is contract, session, active state, participant, session membership, enabled main role, universe, lease identity/owner/expiry, horizon, sizing, command.
- `CanonicalV2AuthorityProvider` adapts the store and existing DecisionMaking portfolio/market surfaces to the existing V2 snapshot.
- `apps/reference/main.py` constructs one store and injects one V2 processor into the existing `LLMIntentIngressBridge`.
- Duplicate identical processor calls return deterministic results; the bridge suppresses a second command with `DUPLICATE_INTENT`. Conflicting IDs reject as `INTENT_ID_CONFLICT`.

## INFERENCES

- The process-safe V1 transport was extended; no second HTTP/TCP/FSM route was created.

## ASSUMPTIONS

- Session lifecycle callers will populate the explicitly exposed store operations before a production V2 intent can authorize.

## UNKNOWNS

- Production freshness references for portfolio and market snapshots remain unproven.
