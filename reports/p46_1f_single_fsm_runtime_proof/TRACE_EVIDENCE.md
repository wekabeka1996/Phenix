# Trace Evidence

## FACTS

```yaml
session_id: session-runtime-1
participant_id: participant-api-1
agent_id: api_agent_01
lease_id: lease-runtime-1
client_intent_id: intent-runtime-0001
sizing_decision_id: sizing:intent-runtime-0001
ipc_message_id: ipc-runtime-1
registered_command: CMD:EXTERNAL_OPEN_REQUEST_V1
fsm_instance_id: single process-local ExecPosFSM
fsm_result: DEC:OPEN / OPEN_OK
derived_quantity: "0.2"
adapter_call_id: null
```

## INFERENCES

- Shared IDs reconstruct intent through FSM acceptance without secrets or account detail.

## ASSUMPTIONS

- `request_id` is the canonical IPC message correlation field.

## UNKNOWNS

- No venue-side call ID exists because no adapter call occurred.
