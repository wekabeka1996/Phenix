# Files changed

## Phenix

- `.gitignore`: allowlist the P8 evidence directory.
- `apps/reference/domains/agent_bridge/contracts.py`: compact identity, expiry, provenance and validation fields; P8 publisher version.
- `apps/reference/domains/agent_bridge/parity_governance.py`: strict authored/validated models, canonical SHA-256 provenance, expiry and invalidation logic.
- `apps/reference/domains/agent_bridge/reducer.py`: compact P8 packet projection.
- `apps/reference/main.py`: P8 publisher version.
- `tests/domains/agent_bridge/test_operator_parity_acknowledgement.py`: P8 validation matrix.
- `tests/domains/agent_bridge/test_filter_parity_governance.py`: identity/provenance packet projection coverage.
- `reports/agent_control_p8_operator_ack_identity/`: evidence and samples.

## Adjacent Cockpit workspace

- `src/shared/contracts/agentFeed.ts`: P8 validation and fields.
- `src/components/agentFeed/AgentFeedPanel.tsx`: read-only identity/expiry display.
- `tests/trading-agent/AgentFeedBridge.test.ts`: validation-state parser coverage.

P7 Cockpit/server changes remain part of the uncommitted adjacent workspace. Unrelated Phenix worktree changes were not modified.
