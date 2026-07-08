# Cockpit display report

The read-only Execution Body card displays parity, ack status, validation result, operator id or `none`, ISO expiry or `n/a`, and review requirement.

The parser validates the P8 status enum, exact state ref, optional identity/timestamps/reason/provenance, and all P7 parity fields. No mutation button, acknowledgement endpoint, dispatch wiring, or action enablement was added. `AGENT_FEED_ACTIONS_ENABLED=false` remains enforced.

Cockpit lint PASS; production build PASS (2,186 modules); focused AgentFeed tests PASS (3/3); forbidden 7102/8443 client tests remain passing.
