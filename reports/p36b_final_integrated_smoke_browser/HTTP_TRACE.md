AGENT_IDENTITY:
  agent_number: 2
  agent_name: primary-final-smoke-browser-validator
  machine: primary
  task_id: P36B_FINAL_INTEGRATED_SMOKE_AND_BROWSER_PROOF
  branch: agent-hub-integrated-2026-07-09
  worktree: C:\Users\wekab\Music\Phenix-integrated-smoke
  commit: a194cb739658483c2d62e21484c89ae398cd0670
  started_at: 2026-07-09T17:05:49+03:00
  finished_at: 2026-07-09T17:38:00+03:00

# Final Integrated Cockpit HTTP Trace Log

This document records the HTTP transactions of the Cockpit dashboard APIs.

---

## 1. Liveness & App Pages
- `GET /health` -> `200 OK`
  ```json
  {"ok": true, "service": "deepseek-terminal-agent-dashboard"}
  ```
- `GET /chat` -> `200 OK` (Jinja2 template compilation passes successfully).

---

## 2. Session API
- `POST /chat/sessions` -> `201 Created`
  ```json
  {"session": {"session_id": "a737f42f901a406499e368ce3f6312b9", "title": "P34B Integrated Smoke Session", ...}}
  ```
- `GET /chat/sessions` -> `200 OK` (successfully lists active sessions).

---

## 3. Attachments API
- `POST /chat/sessions/{session_id}/attachments` -> `201 Created`
  ```json
  {
    "schema_version": 1,
    "attachment_id": "attachment-4af7024c3fe74360b045ddf479b6c886",
    "kind": "market_screenshot",
    "summary": "BTC compression range near 95k VWAP",
    "include_in_prompt": true
  }
  ```
- `POST /chat/sessions/{session_id}/attachments` with raw byte keys -> `400 Bad Request`
  ```json
  {"error": "Raw attachment bytes are not accepted by this metadata route: raw_bytes."}
  ```
- `GET /chat/sessions/{session_id}/attachments` -> `200 OK` (returns list of metadata objects).
- `GET /chat/attachments/{attachment_id}` -> `200 OK` (returns details for specific attachment).

---

## 4. Proposal Ledger API
- `POST /chat/sessions/{session_id}/agent-proposals` -> `201 Created`
  ```json
  {
    "schema_version": 1,
    "proposal_id": "proposal-4abbc04654a14ad6905f093ee735ff70",
    "session_id": "a737f42f901a406499e368ce3f6312b9",
    "kind": "analysis_note",
    "rationale": "Strong order book imbalance support.",
    "status": "pending",
    "payload": {"ratio": 1.45}
  }
  ```
- `POST /chat/sessions/{session_id}/agent-proposals` with forbidden keys -> `400 Bad Request`
  ```json
  {"detail": "Forbidden proposal field: request.payload.sizing"}
  ```
- `GET /chat/sessions/{session_id}/agent-proposals` -> `200 OK` (lists active proposals).
- `GET /chat/agent-proposals/{proposal_id}` -> `200 OK` (returns specific proposal details).

---

## 5. Prompt Context Integration
- `POST /chat/sessions/{session_id}/context` -> `200 OK`
  ```json
  {
    "context_report": {
      "included_sections": ["attachments", "current_message", ...],
      "approximate_chars": 2045
    },
    "context_pack": "... Operator Attachments ... BTC compression range near 95k VWAP ..."
  }
  ```

---

## 6. P33 GET-only Verification
- `GET /chat/sessions/{session_id}/session-context` -> `404 Not Found` (endpoint is not exposed or mapped).
