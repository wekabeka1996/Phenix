# Duplication Audit

## FACTS

- Production search finds one `TradingSessionAuthorityStore` class and one construction in `apps/reference/main.py`.
- No `default_session` or `default_participant` occurrence exists in scoped runtime source.
- P41 collective-memory leases remain evidence/read-model data and are not instantiated as Aurora execution authority.
- `CMD:EXTERNAL_OPEN_REQUEST_V1` has two ingress producers: the retained V1 compatibility mapper and the V2 branch. Only V2 uses canonical session/lease authority.

## INFERENCES

- There is one session/participant/lease authority, but V1 remains an execution-contract compatibility residual.

## ASSUMPTIONS

- V1 removal requires a separate migration package.

## UNKNOWNS

- Runtime policy for disabling V1 after V2 rollout is undecided.
