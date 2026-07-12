# Negative Path Proof

## FACTS

- Zero FSM/adapter activity was asserted for unknown session, inactive session, unknown participant, disabled participant, subagent, missing lease, expired lease, owner mismatch, symbol outside universe, caller qty, missing account truth, missing market price, and sizing rejection.
- Schema-invalid V2 HTTP returned `422`; conflicting identity returned `409`.
- Malformed V2 TCP envelope produced schema rejection before command emission.
- Legacy V1/EZE HTTP routes returned `404`; legacy TCP kind was rejected before FSM.
- Registry-enabled unknown command raised `InvalidMessagePayloadError`; duplicate YAML verb registration raised `ValueError`.

## INFERENCES

- Negative failures are localized before the single FSM ingress unless the command is fully valid.

## ASSUMPTIONS

- Existing P46-1E tests remain authoritative for each exact rejection code.

## UNKNOWNS

- No network-failure behavior was exercised because network calls were forbidden.
