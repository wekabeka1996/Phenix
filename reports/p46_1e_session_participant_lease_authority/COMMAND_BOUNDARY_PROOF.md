# Command Boundary Proof

## FACTS

- Test input: active session, enabled `MAIN_AGENT`, owned ETHUSDT lease, authoritative fixture portfolio/price, V2 intent without qty.
- Result: one `CMD:EXTERNAL_OPEN_REQUEST_V1`, derived `qty=0.07`, linked session/participant/agent/intent/sizing IDs.
- Missing session, inactive session, subagent, missing/released lease, expired lease, owner mismatch, and sizing rejection each emitted zero execution commands.
- Repeating the same intent emitted no second command.

## INFERENCES

- Phenix, not the caller, owns quantity derivation at the proven boundary.

## ASSUMPTIONS

- Unit boundary fakes are valid only through command emission.

## UNKNOWNS

- FSM acceptance, adapter submission, exchange ACK, and lifecycle completion were not tested or claimed.
