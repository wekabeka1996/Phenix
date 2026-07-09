# Memory Runtime Contract

FACTS:
- `POST /chat/sessions/{session_id}/agent-memory/identity` creates or loads memory for one session/agent identity.
- `POST /chat/sessions/{session_id}/agent-memory/instruction-ack` appends an instruction event ref and manifest context ref.
- `POST /chat/sessions/{session_id}/agent-events/rationale` records the normal arena event and appends an `opening_assumptions` reflection.
- `POST /chat/sessions/{session_id}/agent-memory/fsm-decision` appends a `decision_review` reflection for accepted/rejected FSM handoff decisions.
- `POST /chat/sessions/{session_id}/agent-memory/end` writes compact summary JSON and carryover markdown.
- `GET /chat/sessions/{session_id}/agent-memory` reads the memory document and compact summary.

INFERENCES:
- The memory lifecycle is now connected to Cockpit runtime events that are already session-scoped and attributable.

ASSUMPTIONS:
- Runtime callers will pass stable `agent_id`, `agent_number`, `session_id`, `command_id`, `event_id`, `created_at`, and rationale from the surrounding event envelope.

UNKNOWNS:
- The full P39 4-hour trading loop has not consumed this lifecycle yet.
