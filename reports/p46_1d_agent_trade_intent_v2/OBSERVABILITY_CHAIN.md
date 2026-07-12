# Observability Chain

## FACTS

Preserved references include `session_id`, `participant_id`, `agent_id`, `client_intent_id`, `sizing_decision_id`, request ID, symbol, snapshot refs, config version, and rejection reason.

Typed rejection reasons implemented:

`SCHEMA_INVALID`, `IDEMPOTENCY_CONFLICT`, `IPC_UNAVAILABLE`, `IPC_QUEUE_FULL`, `SIZING_AUTHORITY_UNAVAILABLE`, `SESSION_UNKNOWN`, `SESSION_INACTIVE`, `PARTICIPANT_UNKNOWN`, `SUBAGENT_FORBIDDEN`, `AGENT_MISMATCH`, `SYMBOL_NOT_IN_SESSION`, `LEASE_MISSING`, `LEASE_INVALID`, `CONTEXT_STALE`, `HORIZON_EXCEEDED`, `INTENT_EXPIRED`, `LIFECYCLE_STATE_REJECTED`, `EXECUTION_POLICY_MISSING`, `ACCOUNT_TRUTH_MISSING`, `MARKET_PRICE_MISSING`, `SIZING_CONFIG_MISSING`, `RISK_REJECTED`, plus existing PositionQueries reason codes.

No prompts, secrets, credentials, raw exchange parameters, or provider payloads are logged.

## INFERENCES

- The chain is sufficient for contract/queue/main-bridge forensic correlation without claiming FSM or exchange outcome.

## ASSUMPTIONS

- Existing WAL/event listeners persist registered bridge events as configured.

## UNKNOWNS

- Runtime WAL persistence for V2 events was not started or observed.

