# API Contract

Base:
- Cockpit FastAPI dashboard.

Required identity fields:
- agent_id
- agent_number
- rationale or reason

Generated if absent:
- event_id
- command_id
- created_at

Routes:
- POST /chat/sessions/{session_id}/agent-events/rationale
- POST /chat/sessions/{session_id}/agent-events/sos
- POST /chat/sessions/{session_id}/agent-events/testnet-order-request
- POST /chat/sessions/{session_id}/agent-events/testnet-cancel-request
- POST /chat/sessions/{session_id}/agent-events/testnet-close-request
- GET /chat/sessions/{session_id}/agent-events

Status:
- rationale -> recorded
- sos -> pending_fsm
- testnet_order_request -> pending_fsm
- testnet_cancel_request -> pending_fsm
- testnet_close_request -> pending_fsm

Rejects:
- missing session -> 404
- missing/invalid agent identity -> 400
- registry unavailable -> 503
- mainnet/live flags -> 400
- raw exchange payload/credentials/signature/raw_order -> 400

No direct execution:
- exchange_submitted is always false.
- environment is always testnet.
