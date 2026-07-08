# Cockpit display report

The existing Execution Body card renders one read-only line per parity summary, including mismatch type, acknowledgement state, and review requirement. Warning/critical states receive existing amber/red text styling.

The parser validates allowed parity, severity, acknowledgement and compatibility enums, boolean review state, and non-empty refs. There is no acknowledgement button or write API. `AGENT_FEED_ACTIONS_ENABLED=false` remains unchanged.

Validation: TypeScript lint PASS; production build PASS (2,186 modules); focused AgentFeed tests PASS (3/3). Reserved-port rejection for 7102/8443 remains tested.
