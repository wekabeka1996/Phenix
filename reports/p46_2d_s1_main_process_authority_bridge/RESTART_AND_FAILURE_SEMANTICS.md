# Restart and Failure Semantics

## Proven

- Disconnect: typed unavailable or bounded connect timeout on Windows.
- Request timeout: `IPC_QUERY_TIMEOUT`.
- Oversized request/reply and malformed reply: fail closed.
- Runtime generation change: current request rejected; cached generation cleared.
- Identical duplicate request: same reply without second handler execution.
- Conflicting duplicate: `CONFLICT`.
- Server shutdown closes active connections and joins owned threads within configured timeout.

## Not Proven

- Full production main restart while Cockpit holds an operator review.
- Interrupted production dry-run persistence behavior across all three processes.
