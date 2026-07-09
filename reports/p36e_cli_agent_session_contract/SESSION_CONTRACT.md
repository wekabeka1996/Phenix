# CLI Agent Session Contract

## Specifications
- **Bounded Session State**: `CLIAgentSessionState` governs maximum run time and iteration limits.
- **Strict Non-Executability**: `CLIAgentActionEnvelope` enforces that no leverage, quantity, sizing, or order-like fields are present in any action payload.
- **Heartbeat & Event Triggers**: Supports heartbeat signals, manual/scheduled memory refreshes, and SOS alerts.

## Data Schemas
- State model: `CLIAgentSessionState`
- Action model: `CLIAgentActionEnvelope`

## Core Helper Functions
- [build_memory_refresh_action(...)](file:///C:/Users/user/Phenix/p36e-cli-agent-session-contract-secondary-20260709/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_session_contract.py#L38)
- [build_sos_emit_action(...)](file:///C:/Users/user/Phenix/p36e-cli-agent-session-contract-secondary-20260709/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_session_contract.py#L47)
- [build_proposal_submit_action(...)](file:///C:/Users/user/Phenix/p36e-cli-agent-session-contract-secondary-20260709/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_session_contract.py#L56)
- [should_agent_session_continue(...)](file:///C:/Users/user/Phenix/p36e-cli-agent-session-contract-secondary-20260709/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_session_contract.py#L68)
- [apply_timer_tick_to_session_state(...)](file:///C:/Users/user/Phenix/p36e-cli-agent-session-contract-secondary-20260709/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_session_contract.py#L82)
