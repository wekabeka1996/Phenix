# Validation

Preflight commands:
- pwd
- git rev-parse --show-toplevel
- git status --short --branch
- git branch --show-current

Preflight result:
- worktree: C:\Users\wekab\Music\Phenix-p35c-cli-proposal-ledger
- branch: p35c-cli-proposal-ledger-primary-20260709
- base: agent-hub-integrated-2026-07-09 at 87b73b7b

Tests:
- python -m pytest tests/test_agent_proposals.py tests/test_agent_proposal_api.py
  - result: 14 passed
- python -m pytest tests/test_dashboard_chat_app.py
  - result: 9 passed

Covered:
- Valid non-executable trade_intent_draft payload.
- Model top-level extra field rejection.
- execution_authority cannot be true.
- Recursive forbidden payload fields rejected.
- Store create/list/get persists under session directory.
- API create/list/get.
- Missing session fail-closed 404.
- Forbidden top-level and nested fields return 400.
- Session event logs proposal id, agent id, agent number, kind, status, and execution_authority=false.
