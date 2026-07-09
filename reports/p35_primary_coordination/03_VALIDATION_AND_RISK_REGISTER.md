# Validation And Risk Register

## Reported Validations

| Source | Validation reported | Result |
| --- | --- | --- |
| P35A | `python -m pytest tests/test_attachments_api.py tests/test_context_builder.py tests/test_dashboard_chat_app.py tests/test_attachment_ui_panel.py` | `20 passed` |
| P35A | `python -m pytest tests/domains/agent_bridge/test_session_context_contract.py` | `6 passed` |
| P35A | report note | P34E was skipped at that time because the branch was not merged yet |
| P35B | Health/session/attachments/prompt-context/P33 checks, cadence governance tests, static frontend parsing | Pass, but browser-subagent execution was unavailable on Windows |
| P35C | `python -m pytest tests/test_agent_proposals.py tests/test_agent_proposal_api.py` | `14 passed` |
| P35C | `python -m pytest tests/test_dashboard_chat_app.py` | `9 passed` |
| P35 secondary | Combined coordination and timer-runner contract validation | Pass, report says ready for primary coordinator integration |

## Missing Proof

- P35B browser-run transcript, screenshot, or manual UI proof.
- No report files are missing anymore.

## Root-Cause Claims And Evidence Level

| Claim | Evidence level | Basis |
| --- | --- | --- |
| P35A closes the integrated close path | High | Passing pytest results in the P35A report |
| P35C is a non-executable proposal ledger | High | Passing proposal API/store tests and explicit non-execution boundary in the report |
| Secondary coordination is synchronized and ready | High | Combined coordination report says the secondary work is fully validated |
| P35B browser validation is incomplete on this machine | High | Report explicitly says browser-subagent execution was restricted on Windows |

## Risks

| Severity | Risk | Why it matters |
| --- | --- | --- |
| P0 | None observed | No live trading, raw exchange orders, or runtime-control surfaces were exercised in this refresh |
| P1 | P35B browser proof gap | Operator should not overstate full UI parity until a manual browser trace exists |
| P1 | Branch divergence from origin | `agent-hub-integrated-2026-07-09` is currently ahead 1 and behind 2, so the next baseline move needs a fresh decision |
| P2 | `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/app.py` is a likely future conflict surface | P35C already touches this file and P35B smoke depends on it |
| P2 | Coordination-document confusion | The secondary report is sourced from `origin/p35-secondary-combined-report-20260709`, while its own text names `p35e-cli-timer-runner-secondary-20260709` |

## Surface Checks

- Allowed file surfaces: respected.
- YAML/business config touch: none.
- Runtime/trading touch: none.
- Direct order authority risk: low. P35C keeps `execution_authority=false` and blocks order-like fields such as `order`, `sizing`, `leverage`, `quantity`, and `notional`.
