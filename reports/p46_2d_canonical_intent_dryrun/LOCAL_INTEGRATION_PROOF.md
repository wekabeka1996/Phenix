# Local Integration Proof

## FACTS
- Real loopback chain: Cockpit Express -> SQLite proposal -> server-side client -> uvicorn/FastAPI -> authority/V2 mapper/PositionQueries/exposure preview -> immutable result -> review -> context invalidation.
- Evidence: proposals `1`; dry-run POSTs `1`; decision `ACCEPTED`; derived quantity present; caller quantity absent; execution authorized false; command/FSM/adapter/exchange/provider `0`.

## ASSUMPTIONS
- Test server uses deterministic explicit runtime authorities and recording no-network boundaries; this is not production composition evidence.
