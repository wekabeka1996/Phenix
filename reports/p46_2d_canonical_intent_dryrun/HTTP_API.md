# HTTP API

## FACTS
- Authenticated POST: `/proposal-dry-run/v1/sessions/{session_id}`.
- Authenticated GET: `/proposal-dry-run/v1/results/{proposal_id}`.
- Strict YAML/Pydantic policy declares schema/result versions, endpoint, enabled state, and 32 KiB body cap.
- Session identity mismatch, schema/forbidden fields, missing result, and unavailable authority are typed.
- Namespace exposes no generic command, FSM, or adapter operation.
