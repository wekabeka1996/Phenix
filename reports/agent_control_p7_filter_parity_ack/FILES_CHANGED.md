# Files changed

## Phenix

- `.gitignore`: allowlist this P7 evidence directory.
- `apps/reference/domains/agent_bridge/contracts.py`: full/compact parity acknowledgement contracts and P7 publisher version.
- `apps/reference/domains/agent_bridge/parity_governance.py`: exact-state acknowledgement loader, classification, and append-safe history owner.
- `apps/reference/domains/agent_bridge/{capabilities,execution_readiness,publication,reducer}.py`: readiness and compact packet integration.
- `apps/reference/main.py`: P7 publisher version and parity-history directory wiring.
- `tests/domains/agent_bridge/test_filter_parity_governance.py`: lifecycle, severity, acknowledgement, history, packet, and budget tests.
- `reports/agent_control_p7_filter_parity_ack/`: this evidence package.

## Adjacent Cockpit workspace

- `src/shared/contracts/agentFeed.ts`: typed P7 compact state and validation.
- `src/components/agentFeed/AgentFeedPanel.tsx`: read-only parity status rendering.
- `tests/trading-agent/AgentFeedBridge.test.ts`: valid and invalid acknowledgement-state coverage.
- `server.ts`: environment-selectable `PORT` used for approved 18081 runtime validation.

Pre-existing Neocortex/config and `tools/runtime_forensics_tmp` changes were left untouched.
