# Transport Path

## FACTS

Implemented path:

```text
POST /intents/llm/v2
  -> AgentTradeIntentV2 validation
  -> existing authenticated/idempotent JsonlTcpQueueClient
  -> existing IPC endpoint
  -> LLMIntentIngressBridge._on_command
  -> authority processor (when injected)
  -> PositionQueries sizing adapter
  -> registered EVT:AGENT_TRADE_INTENT_V2_{RECEIVED|REJECTED|SIZED}
  -> existing CMD:EXTERNAL_OPEN_REQUEST_V1
  -> existing execution-position guard/FSM boundary
```

- HTTP source contains no `fsm_ref` and does not derive quantity.
- Rejected intents emit zero execution commands.
- Approved unit path emits exactly one existing registered downstream command.
- Production composition injects no processor and therefore rejects before command emission.

## INFERENCES

- The existing process-safe transport is reused additively; no HTTP-to-FSM bypass was created.

## ASSUMPTIONS

- Existing IPC queue/server lifecycle remains the supported process boundary.

## UNKNOWNS

- No live process or socket proof was run in this package.

