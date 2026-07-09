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

# Integrated Cockpit Runtime Smoke Risks Report

This document records the risk analysis for the integration validation testing phase of the Cockpit dashboard.

---

## 1. Remote Branch Synchronization Risks
* **Risk**: Merging batch branches dynamically in multi-agent schedules can result in validating outdated commits or checking out dirty directories.
* **Control**:
  - The harness uses a pre-validation PowerShell script (`wait_for_branch.ps1`) to poll remote branches and verify the integration branch `origin/agent-hub-integrated-2026-07-09` is fully pushed before check out.
  - The git checkout uses a dedicated isolated git worktree `Phenix-integrated-smoke` to prevent pollution or race conditions with other ongoing tasks in the main workspace directory.

---

## 2. Payload Bloat and Base64 Injection Risks
* **Risk**: Unconstrained attachments (such as base64 images or massive pasted texts) uploaded to the session can degrade prompt context quality and increase token usage.
* **Control**:
  - The backend route handler `/chat/sessions/{session_id}/attachments` implements a validation guard: it parses payloads and rejects any entries containing forbidden binary keys (`raw_bytes`, `image_bytes`, `content_base64`, etc.) with a `400 Bad Request` code.
  - The context builder strips raw reference payloads and packages only the high-level summary and source URLs into the prompt context pack.

---

## 3. P33 Endpoint Absence & Security Check
* **Risk**: The missing `session-context` endpoint could fail-open or leak unauthorized session details if query parameters are parsed weakly.
* **Control**:
  - The integration branch fails closed. A HTTP query to `/chat/sessions/{session_id}/session-context` returns `404 Not Found` cleanly without raising server exceptions or revealing backend parameters.
