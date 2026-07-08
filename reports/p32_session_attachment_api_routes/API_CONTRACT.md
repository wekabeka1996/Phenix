# P32B Attachment API Contract

base: Cockpit dashboard FastAPI app

## AttachmentRecord

Fields:
- attachment_id: generated safe local id
- session_id: existing chat session id
- kind: operator_note | pasted_text | news_summary | image_ref | chart_snapshot | market_screenshot | file_ref
- raw_ref: bounded reference/path only; data: inline payloads are rejected
- summary: required bounded summary
- source_refs: bounded source references
- created_at: UTC ISO timestamp
- created_by: bounded actor label, default operator
- include_in_prompt: bool, default true
- token_estimate: non-negative estimate, computed when omitted

## Routes

POST /chat/sessions/{session_id}/attachments
- Validates session exists.
- Rejects raw_bytes, image_bytes, file_bytes, content_base64, blob, bytes fields.
- Stores metadata/ref/summary only.
- Returns AttachmentRecord with HTTP 201.
- Returns 404 if session is missing.
- Returns 400 for invalid kind, invalid refs, inline data URI refs, or invalid token estimate.

GET /chat/sessions/{session_id}/attachments
- Validates session exists.
- Returns {"attachments": [AttachmentRecord...]}.
- Returns 404 if session is missing.

GET /chat/attachments/{attachment_id}
- Loads the attachment and validates its session still exists.
- Returns AttachmentRecord.
- Returns 404 if attachment or owning session is missing.

## Prompt Context

ContextBuilder reads AttachmentStore separately from memory compression and adds an attachments section only when prompt-eligible records exist.

Prompt text includes:
- attachment id
- kind
- bounded summary
- bounded raw_ref
- up to five source_refs

Prompt text excludes:
- include_in_prompt=false records
- raw byte fields
- inline data URI payloads
