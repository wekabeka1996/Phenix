# Validation And Risk Register

## Reported Validations

| Source | Validation reported | Result |
| --- | --- | --- |
| P36B | `powershell -ExecutionPolicy Bypass -File tools/deepseek-terminal-agent/scripts/run_final_integrated_smoke.ps1` | Smoke passed; P33 GET-only endpoint returned 404; proposal ledger routes validated; browser automation unavailable on Windows |
| P36B | `tests/test_attachments_api.py`, `tests/test_attachment_ui_panel.py`, `tests/test_proposals_api.py`, `tests/test_integrated_smoke.py` | 4 passed, 2 passed, 2 passed, 1 passed |
| P36C | `python -m pytest tests/test_agent_proposal_client.py` | `11 passed` |
| P36C | `python -m pytest tests/test_agent_proposal_api.py tests/test_agent_proposals.py` | `14 passed` |
| P36C | CLI dry-run | Sanitized POST target/payload printed without contacting a server |
| P36A | `python -m pytest tests/test_agent_proposals.py tests/test_agent_proposal_api.py tests/test_dashboard_chat_app.py tests/test_attachments_api.py tests/test_context_builder.py tests/test_attachment_ui_panel.py tests/test_agent_cadence.py tests/test_agent_timer_runner.py` | Passed |
| P36A | `python -m pytest tests/domains/agent_bridge/test_session_context_contract.py` | Passed |
| Secondary | Node synchronization and remote head tracking verification | Pass |
| Secondary | Session-contract validation unit tests | Executed and validated |

## Missing Proof

- Live browser execution on Windows for P36B.

## Root-Cause Claims And Evidence Level

| Claim | Evidence level | Basis |
| --- | --- | --- |
| P36B smoke passed | High | Reported smoke validation and HTTP trace outputs |
| Browser proof is unavailable on Windows | High | P36B browser proof states local Chrome mode is only supported on Linux |
| Proposal forbidden fields are rejected | High | P36B HTTP trace and P36C client/report both show `400 Bad Request` for forbidden keys |
| No live/mainnet or raw-order activity occurred | High | P36C report states no live/mainnet and no order fields; P36B/P36A are validation-only |
| P36C proposal client is non-executable | High | Reported dry-run and offline test coverage |
| Secondary coordination is ready | High | Secondary report marks the package ready for primary close operations |

## Risks

| Severity | Risk | Why it matters |
| --- | --- | --- |
| P0 | None observed | No live trading, raw orders, or runtime execution surfaces were touched |
| P1 | Browser automation proof gap on Windows | The batch is ready, but the browser proof is static-only on this machine |
| P1 | Remote tracking ref lags the local baseline until published | Origin is still one commit behind the local baseline commit |
| P2 | Future dashboard/app conflict surface | `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/app.py` is a shared integration point for UI and API work |
| P2 | Missing visible `p36-secondary-equal-node-verification` ref | Not a blocker, but it means the coordination proof relies on the visible secondary combined-report ref instead |

## Surface Checks

- Allowed file surfaces: respected.
- YAML/business config touch: none.
- Runtime/trading touch: none.
- Direct order authority risk: low. Proposal flows reject forbidden order-like fields and the client stays non-executable.
