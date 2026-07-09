# API Contract

## Proposal Kinds

- analysis_note
- memory_refresh
- sos_market_change
- operator_question
- trade_intent_draft

## Required Fields

- proposal_id: generated local safe id
- session_id: existing Cockpit chat session
- agent_id: CLI/API agent identity
- agent_number: numeric batch agent id
- kind: one proposal kind
- created_at: UTC ISO timestamp
- confidence: optional 0..1
- rationale: required bounded text
- source_refs: bounded source refs
- status: pending | reviewed | rejected | accepted_for_review
- payload: dict
- execution_authority: false

## Routes

POST /chat/sessions/{session_id}/agent-proposals
- Validates session exists first.
- Rejects missing session with 404.
- Rejects invalid model, missing agent_number, invalid confidence/status/kind, and forbidden fields with 400.
- Persists proposal and appends session event agent_proposal_submitted.

GET /chat/sessions/{session_id}/agent-proposals
- Validates session exists first.
- Returns {"agent_proposals": [...]}.

GET /chat/agent-proposals/{proposal_id}
- Loads proposal by id and validates owning session still exists.

## Forbidden Fields

Rejected at top-level request and recursively inside payload:
- order
- sizing
- leverage
- quantity
- notional
- exchange_order_id
- client_order_id
