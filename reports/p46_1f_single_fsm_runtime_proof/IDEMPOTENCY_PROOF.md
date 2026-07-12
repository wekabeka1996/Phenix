# Idempotency Proof

## FACTS

- Duplicate identical HTTP request returned the original `202` response and emitted no second TCP envelope.
- Conflicting HTTP payload with the same `client_intent_id` returned `409 IDEMPOTENCY_CONFLICT`.
- Duplicate raw TCP delivery reached the bridge but `DUPLICATE_INTENT` suppression emitted no second command, FSM action, or adapter action.
- Ownership: HTTP keeps payload-hash response identity; bridge owns command-emission suppression; OpenFlow retains downstream idempotency as defense in depth.

## INFERENCES

- The ledgers have consistent intent identity during one process lifetime.

## ASSUMPTIONS

- IPC delivery retries preserve `client_intent_id`.

## UNKNOWNS

- HTTP/bridge idempotency reconstruction after process restart is not durable and remains a follow-up requirement.
