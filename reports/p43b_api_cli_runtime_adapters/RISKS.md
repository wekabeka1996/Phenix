# Risks

## P0

- None introduced. The adapter module has no exchange/FSM/order authority.

## P1

- Real provider behavior is unproven without credentials; do not treat injected fake-client results as external API evidence.
- The restricted CLI protocol validates command/path inputs but cannot sandbox a malicious executable at OS level; production use requires a trusted installed binary and approved working directory.
- P42 `DualAgentRuntimeRunner` still needs an explicit caller integration to instantiate these adapters. No silent mock fallback was added.

## P2

- Provider-specific tool-call/JSON quirks may require a contract update after a credentialed smoke.
- CLI heartbeat is adapter-observed at protocol response boundaries; a separate child heartbeat frame is not implemented.
- `cli_command: null` and empty approved paths intentionally block production CLI startup until operator configuration exists.

No YAML business strategy, collective-memory internals, exchange adapter, order placement, or mainnet surface was changed.

