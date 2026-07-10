# Control Surface Matrix

| UI control | Registered event | Initial status | Exchange authority |
|---|---|---|---|
| Pause agent | `agent_arena.pause_agent_requested` | `recorded` | none |
| Resume agent | `agent_arena.resume_agent_requested` | `recorded` | none |
| Stop agent | `agent_arena.stop_agent_requested` | `recorded` | none |
| Stop session | `agent_arena.stop_session_requested` | `pending_fsm` | none |
| Trigger analysis | `agent_arena.analysis_requested` | `recorded` | none |
| Instruction refresh | `agent_arena.instruction_refresh_requested` | `recorded` | none |
| Emergency stop | `agent_arena.emergency_stop_requested` | `pending_fsm` | none |

All POSTs use `/arena/commands/{registered_action}` and require `agent_id`, `agent_number`, `session_id`, `command_id`, `event_id`, `symbol`, `created_at`, `rationale`, `instruction_version`, and optional `collective_state_version`.

Controls are disabled in the UI without an active session and instruction ACK. No `/arena/buy`, `/arena/sell`, raw exchange, cancel-order, or close-position route exists.

