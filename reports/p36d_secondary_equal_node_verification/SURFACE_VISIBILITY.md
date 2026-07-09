# Surface Visibility Audit

This document verifies the visibility and integrity of all integrated codebase surfaces on the secondary node.

## Audit Table

| Codebase Surface | Filepath | Status | Notes |
| :--- | :--- | :---: | :--- |
| **Proposal Ledger** | `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_proposals.py` | **VISIBLE** | Implements the CLI proposal ledger contract. |
| **Proposal Tests** | `tools/deepseek-terminal-agent/tests/test_agent_proposals.py` | **VISIBLE** | Unit tests for proposal state transitions. |
| **Proposal API Tests** | `tools/deepseek-terminal-agent/tests/test_agent_proposal_api.py` | **VISIBLE** | HTTP API tests for proposal routes. |
| **Attachment UI Javascript** | `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/static/chat.js` | **VISIBLE** | Frontend attachment wiring. |
| **Attachment UI HTML** | `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/templates/chat.html` | **VISIBLE** | Cockpit interface integrations. |
| **Attachment Backend** | `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/attachments.py` | **VISIBLE** | Attachment intakes and metadata store. |
| **Attachment Tests** | `tools/deepseek-terminal-agent/tests/test_attachments_api.py` | **VISIBLE** | Backend tests for attachments. |
| **Attachment UI Panel Tests** | `tools/deepseek-terminal-agent/tests/test_attachment_ui_panel.py` | **VISIBLE** | Frontend integration checks. |
| **Agent Cadence Checks** | `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_cadence.py` | **VISIBLE** | Stagger interval governance backend. |
| **Agent Cadence Tests** | `tools/deepseek-terminal-agent/tests/test_agent_cadence.py` | **VISIBLE** | Cadence governance validations. |
| **Agent Timer Runner** | `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_timer_runner.py` | **VISIBLE** | CLI timer runner scheduler. |
| **Agent Timer Runner Tests** | `tools/deepseek-terminal-agent/tests/test_agent_timer_runner.py` | **VISIBLE** | Timer state, TTL, and heartbeat validations. |
| **P33 Session Context** | `apps/reference/domains/agent_bridge/session_context_contract.py` | **VISIBLE** | Repaired schema validation and safety comments. |
| **P33 Read Model and Routes** | `apps/reference/domains/agent_bridge/session_context_read_model.py` and `routes.py` | **VISIBLE** | Repointed to correct Cockpit root. |

## Workspace Parity Verdict
**PASSED**. The secondary workstation workspace contains 100% of the files matching the integrated primary codebase baseline. No files are dirty, missing, or conflicted.
