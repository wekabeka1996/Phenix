# Surface Visibility Audit

This document audits the presence of expected integrated surfaces on the synchronized `agent-hub-integrated-2026-07-09` branch.

## Audit Table

| Expected Integrated Surface | Local Filepath | Found | Notes |
| :--- | :--- | :---: | :--- |
| **Cockpit Dashboard** | `tools/deepseek-terminal-agent` | **YES** | Entire package is present. |
| **Attachments API Backend** | `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/attachments.py` | **YES** | Session attachment intake backend exists. |
| **Attachments API Tests** | `tools/deepseek-terminal-agent/tests/test_attachments_api.py` | **YES** | Unit tests for attachment routes and store exist. |
| **P33 Session Memory Contract** | `apps/reference/domains/agent_bridge/session_context_contract.py` | **YES** | Repaired contract with validators and safety comments. |
| **P33 Read Model and Routes** | `apps/reference/domains/agent_bridge/session_context_read_model.py` and `routes.py` | **YES** | Correctly pointed to tools directory memory root. |
| **Combined Reports** | `reports/p34_secondary_combined_coordination` | **YES** | P34 combined coordination report is tracked. |
| **P34E Agent Cadence Backend** | `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_cadence.py` | **NO** | Waiting for primary coordinator to merge. |
| **P34E Agent Cadence Tests** | `tools/deepseek-terminal-agent/tests/test_agent_cadence.py` | **NO** | Waiting for primary coordinator to merge. |

## Audit Summary
The secondary machine is synchronized with the primary-integrated baseline. All primary merges from P31, P32, and P33 are visible. The P34E cadence contract is not yet integrated into the baseline, placing the node in `P35D_P34E_PUBLISHED_WAITING_PRIMARY` status.
