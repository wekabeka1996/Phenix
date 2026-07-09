# Validation

Preflight:
- pwd
- git rev-parse --show-toplevel
- git status --short --branch
- git branch --show-current

Preflight result:
- worktree: C:\Users\wekab\Music\Phenix-p37c-cockpit-agent-event-buttons
- branch: p37c-cockpit-agent-event-buttons-primary-20260709
- baseline: bc25105175bd6e41d677f8d74f72979cd7155b1e

Tests:
- python -m pytest tests/test_agent_events.py tests/test_agent_event_api.py
  - result: 12 passed
- python -m pytest tests/test_agent_proposal_api.py tests/test_dashboard_chat_app.py
  - result: 13 passed

Static safety scan:
- rg for binance/exchange.create/create_order/cancel_order/api_secret/api_key/mainnet/live on changed files.
- Result: no exchange/order client calls; matches are forbidden-key validators and tests only, plus existing dashboard config-status api_key_present text.

Covered:
- create/list event buttons
- YAML + Pydantic registry load
- missing session rejects
- missing agent identity rejects
- mainnet flag rejects
- raw exchange payload rejects
- every accepted action has event_id, command_id, timestamp
- registry unavailable fails closed with 503
