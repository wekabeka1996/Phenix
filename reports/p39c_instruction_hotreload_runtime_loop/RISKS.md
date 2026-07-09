# Risks

## FACTS

- No live trading runtime was started.
- No mainnet/live paths were touched.
- No YAML/business config was edited.
- No raw exchange client calls were added.

## INFERENCES

- ACK events can grow over long sessions because every cycle records one heartbeat.
- Missing-file status is explicit, but callers must decide whether to block trading decisions.

## ASSUMPTIONS

- Session event ledger volume is acceptable for a 4h MVP at 5-minute cadence.

## UNKNOWNS

- Runtime behavior under concurrent agents has not been load-tested.
- No external filesystem watcher integration exists.
- No UI staleness indicator exists for unacknowledged manifest versions.
