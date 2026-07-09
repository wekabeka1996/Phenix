# Patch Diff

git diff --name-only:
- tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/app.py
- tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_proposals.py
- tools/deepseek-terminal-agent/tests/test_agent_proposal_api.py
- tools/deepseek-terminal-agent/tests/test_agent_proposals.py
- reports/p35c_cli_agent_proposal_ledger/API_CONTRACT.md
- reports/p35c_cli_agent_proposal_ledger/PATCH_DIFF.md
- reports/p35c_cli_agent_proposal_ledger/REPORT.md
- reports/p35c_cli_agent_proposal_ledger/RISKS.md
- reports/p35c_cli_agent_proposal_ledger/VALIDATION.md

Functional diff:
- Added AgentProposalRecord, AgentProposalStore, and forbidden-field validator.
- Added dashboard store singleton, session detail field, create/list/get routes, and session event logging.
- Added focused model/store and API tests.

Non-changes:
- No backend execution path.
- No Aurora runtime.
- No exchange/order runtime.
- No YAML/config edits.
