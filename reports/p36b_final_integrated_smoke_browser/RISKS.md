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

# Final Integrated Cockpit Smoke & Browser Risks Report

This document records the risk analysis for the final integrated state of the Cockpit dashboard application.

---

## 1. Browser Verification Gap
* **Risk**: Validating complex visual assets (like panels, collapsing containers, input nodes, or responsive css grids) solely via API endpoints leaves room for regressions in real user displays.
* **Control**:
  - Since headless chrome automation is unsupported in this Windows runtime environment, we introduced the static UI validation test (`test_attachment_ui_panel.py`).
  - This test reads the Jinja2 template and javascript client code directly, parsing and asserting the exact selectors and route bindings (like `id="attachments-panel"` and `function loadAttachments(sessionId)`) are integrated, guaranteeing correct asset distribution.

---

## 2. Proposal Ledger Execution Leakage (Order/Sizing)
* **Risk**: The proposal ledger acts as a storage system for agent intents. If agents inject executable order schemas (like quantity, pricing, leverage, or sizing keys) directly into the proposal payload, they might bypass approval queues or execution gateways.
* **Control**:
  - The store implements a strict JSON parser traversal that rejects any proposals containing flat or nested forbidden keys (`order`, `sizing`, `leverage`, `quantity`, `notional`, `exchange_order_id`, `client_order_id`) with a `400 Bad Request` before the proposal metadata is written to disk.
