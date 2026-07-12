# Positive Path Proof

## FACTS

1. Active `session-runtime-1`, enabled `participant-api-1`, ETHUSDT universe, active `lease-runtime-1`.
2. HTTP returned `202 queued` for V2 OPEN without qty.
3. Authority recorded one `ACCEPTED` decision.
4. PositionQueries produced `qty=0.2` from explicit equity, price, instrument config.
5. One TCP envelope reached one V2 bridge handler.
6. Registry accepted one `CMD:EXTERNAL_OPEN_REQUEST_V1` against its YAML schema.
7. One listener converted it to one `CMD:OPEN`; one real ExecPosFSM returned `DEC:OPEN`, `OPEN_OK`.
8. Recording adapter calls: submit `0`, cancel `0`, amend `0`; network disabled.

## INFERENCES

- The FSM accepted the command contract and guards before the venue boundary.

## ASSUMPTIONS

- Shadow mode intentionally prevents adapter scheduling after accepted DEC.

## UNKNOWNS

- A non-shadow recording-adapter run is deferred because this package forbids execution side effects beyond the boundary.
