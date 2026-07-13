# Local Integration Proof

## FACTS
- Real uvicorn served the production FastAPI route functions over loopback.
- Cockpit's real semantic client authenticated and fetched the aggregate; browser-like traffic reached only Cockpit Express.
- Result: GET 3; writes 0; execution commands 0; FSM mutations 0; adapter/exchange/provider calls 0; identities, context version, and references preserved; stale admission blocked.

## INFERENCES
- The HTTP trust boundary is operational without an execution side effect.

## ASSUMPTIONS
- Deterministic test authority represents contract behavior, not live venue state.

## UNKNOWNS
- Production process supervision was not exercised.
