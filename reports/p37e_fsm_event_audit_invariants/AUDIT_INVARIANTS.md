# FSM Event Audit Invariants

## Specifications
- **Complete Command Attribution**: Every single agent action command must specify: `event_id`, `command_id`, `session_id`, `agent_id`, `agent_number`, `created_at`, `command_kind`.
- **Strict Sandbox / Testnet Only**: Executable intent commands must have `testnet_only = true`. Mainnet operations are strictly blocked.
- **Credential Protection**: Commands are recursively scanned, and any sensitive fields (like private keys, secrets, or API tokens) are rejected.
- **FSM-Visible Lifecycles**: Command states transit through a defined set of statuses: `recorded` -> `pending_fsm` / `accepted_by_fsm` / `rejected_by_fsm` -> `submitted_testnet` -> `exchange_ack` / `exchange_reject` -> `lifecycle_closed`.
- **Fail-Closed on Missing FSM Registration**: Unregistered command kinds transition status to `pending_fsm` and fail closed.

## Core Code Structures
- [AgentActionCommand](file:///C:/Users/user/Phenix/p37e-fsm-event-audit-invariants-secondary-20260709/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_action_audit.py#L29): Data schema.
- [FSMAuditRegistry](file:///C:/Users/user/Phenix/p37e-fsm-event-audit-invariants-secondary-20260709/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_action_audit.py#L76): FSM validation.
- [CommandAuditJournal](file:///C:/Users/user/Phenix/p37e-fsm-event-audit-invariants-secondary-20260709/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_action_audit.py#L90): History tracking.
