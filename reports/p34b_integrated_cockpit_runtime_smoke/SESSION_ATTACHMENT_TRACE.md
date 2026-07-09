AGENT_IDENTITY:
  agent_number: 2
  agent_name: primary-integrated-cockpit-smoke
  machine: primary
  task_id: P34B_INTEGRATED_COCKPIT_RUNTIME_SMOKE
  branch: agent-hub-integrated-2026-07-09
  worktree: C:\Users\wekab\Music\Phenix-integrated-smoke
  commit: 5837ae4fa1ca35cb8d59c5023e9f8161a28ca76f
  started_at: 2026-07-09T10:39:16+03:00
  finished_at: 2026-07-09T10:47:00+03:00

# Session & Attachment API Trace Log

This document records the HTTP transaction traces for the chat session and attachment metadata APIs.

---

## 1. Chat Session Creation (`POST /chat/sessions`)

### Request
```http
POST /chat/sessions HTTP/1.1
Host: 127.0.0.1:<PORT>
Content-Type: application/json

{
  "title": "P34B Integrated Smoke Session"
}
```

### Response
```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "session": {
    "session_id": "a458ffef9ecf46238f1c5b90ee7ec008",
    "title": "P34B Integrated Smoke Session",
    "active_profile": { ... },
    "pinned_memory_atom_ids": [],
    "status": "idle",
    "metadata": {},
    "created_at": "2026-07-09T07:46:12Z",
    "updated_at": "2026-07-09T07:46:12Z"
  },
  "turns": [],
  "events": [],
  "memory_atoms": [],
  "artifacts": [],
  "subagents": []
}
```

---

## 2. Attachment Addition (`POST /chat/sessions/{session_id}/attachments`)

### Request
```http
POST /chat/sessions/a458ffef9ecf46238f1c5b90ee7ec008/attachments HTTP/1.1
Host: 127.0.0.1:<PORT>
Content-Type: application/json

{
  "kind": "market_screenshot",
  "raw_ref": "file://screenshots/btc-vwap.png",
  "summary": "BTC compression range near 95k VWAP",
  "source_refs": ["operator-upload://btc-vwap"],
  "include_in_prompt": true
}
```

### Response
```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "schema_version": 1,
  "attachment_id": "attachment-565f57fb98314ee28de8cd856cd58826",
  "session_id": "a458ffef9ecf46238f1c5b90ee7ec008",
  "kind": "market_screenshot",
  "raw_ref": "file://screenshots/btc-vwap.png",
  "summary": "BTC compression range near 95k VWAP",
  "source_refs": ["operator-upload://btc-vwap"],
  "created_at": "2026-07-09T07:46:13Z",
  "created_by": "operator",
  "include_in_prompt": true,
  "token_estimate": 8
}
```

---

## 3. Attachment Rejection (Raw Bytes Guard)

### Request
```http
POST /chat/sessions/a458ffef9ecf46238f1c5b90ee7ec008/attachments HTTP/1.1
Host: 127.0.0.1:<PORT>
Content-Type: application/json

{
  "kind": "market_screenshot",
  "summary": "Forbidden raw bytes",
  "raw_bytes": "base64_data_here..."
}
```

### Response
```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "Raw attachment bytes are not accepted by this metadata route: raw_bytes."
}
```

---

## 4. Attachment Listing (`GET /chat/sessions/{session_id}/attachments`)

### Request
```http
GET /chat/sessions/a458ffef9ecf46238f1c5b90ee7ec008/attachments HTTP/1.1
Host: 127.0.0.1:<PORT>
```

### Response
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "attachments": [
    {
      "schema_version": 1,
      "attachment_id": "attachment-565f57fb98314ee28de8cd856cd58826",
      "session_id": "a458ffef9ecf46238f1c5b90ee7ec008",
      "kind": "market_screenshot",
      "raw_ref": "file://screenshots/btc-vwap.png",
      "summary": "BTC compression range near 95k VWAP",
      "source_refs": ["operator-upload://btc-vwap"],
      "created_at": "2026-07-09T07:46:13Z",
      "created_by": "operator",
      "include_in_prompt": true,
      "token_estimate": 8
    }
  ]
}
```

---

## 5. Attachment Detail (`GET /chat/attachments/{attachment_id}`)

### Request
```http
GET /chat/attachments/attachment-565f57fb98314ee28de8cd856cd58826 HTTP/1.1
Host: 127.0.0.1:<PORT>
```

### Response
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "schema_version": 1,
  "attachment_id": "attachment-565f57fb98314ee28de8cd856cd58826",
  "session_id": "a458ffef9ecf46238f1c5b90ee7ec008",
  "kind": "market_screenshot",
  "raw_ref": "file://screenshots/btc-vwap.png",
  "summary": "BTC compression range near 95k VWAP",
  "source_refs": ["operator-upload://btc-vwap"],
  "created_at": "2026-07-09T07:46:13Z",
  "created_by": "operator",
  "include_in_prompt": true,
  "token_estimate": 8
}
```
