# Patch Diff

git diff --name-only:
- tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/app.py
- tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_event_registry.yaml
- tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_events.py
- tools/deepseek-terminal-agent/tests/test_agent_event_api.py
- tools/deepseek-terminal-agent/tests/test_agent_events.py
- reports/p37c_cockpit_agent_event_buttons/API_CONTRACT.md
- reports/p37c_cockpit_agent_event_buttons/EVENT_LEDGER_CONTRACT.md
- reports/p37c_cockpit_agent_event_buttons/PATCH_DIFF.md
- reports/p37c_cockpit_agent_event_buttons/REPORT.md
- reports/p37c_cockpit_agent_event_buttons/RISKS.md
- reports/p37c_cockpit_agent_event_buttons/VALIDATION.md

Functional diff:
- Added YAML + Pydantic registered agent arena event contract.
- Added validation for testnet-only/no raw exchange payloads.
- Added six Cockpit API endpoints.
- Added unit/API tests.

Non-changes:
- No YAML/config edits.
- No Aurora runtime edits.
- No exchange adapter/order execution code.
- No UI wiring.
