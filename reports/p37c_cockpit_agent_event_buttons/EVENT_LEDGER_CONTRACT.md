# Event Ledger Contract

Registry SSOT:
- YAML: tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_event_registry.yaml
- Pydantic: AgentArenaEventRegistry and AgentArenaEventRegistration
- Missing/invalid registry fails closed before route persistence.

Storage:
- Existing session event ledger: .agent_memory/sessions/<session_id>/events.dsctx.jsonl

Event type prefix:
- agent_arena.*

Registered actions:
- rationale -> agent_arena.rationale_recorded
- sos -> agent_arena.sos_requested
- testnet_order_request -> agent_arena.testnet_order_requested
- testnet_cancel_request -> agent_arena.testnet_cancel_requested
- testnet_close_request -> agent_arena.testnet_close_requested

Ledger metadata:
- metadata.arena_command carries the full registered command record:
  - event_id
  - command_id
  - session_id
  - agent_id
  - agent_number
  - action
  - event_type
  - created_at
  - rationale
  - status
  - environment
  - payload
  - fsm_registered
  - exchange_submitted

List API:
- GET /chat/sessions/{session_id}/agent-events returns only agent_arena.* events projected from the session ledger.

Execution boundary:
- This package records registered commands only.
- FSM handoff/execution wiring remains pending.
