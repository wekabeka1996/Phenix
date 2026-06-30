# Files changed

## Aurora / Phenix

- `.gitignore` — tracks the required P2 evidence directory.
- `apps/reference/domains/agent_bridge/contracts.py` — readiness evidence and snapshot contract.
- `apps/reference/domains/agent_bridge/execution_readiness.py` — allowlisted, read-only runtime inspector.
- `apps/reference/domains/agent_bridge/reducer.py` — consumes the readiness snapshot in `ExecutionBodyCard`.
- `apps/reference/domains/agent_bridge/routes.py` — GET-only readiness endpoint.
- `tests/domains/agent_bridge/test_agent_feed_reducer.py` — updated GET-only route set.
- `tests/domains/agent_bridge/test_execution_readiness.py` — missing/runtime evidence and no-secret/no-submit tests.
- `reports/agent_control_p2_runtime_observation/` — required evidence and ten packet samples.

## Cockpit

- `src/shared/contracts/agentFeed.ts` — typed optional readiness snapshot validation.
- `scripts/p2-agent-feed-observation-host.ts` — reproducible approved-port host start.
- `scripts/p2-observe-agent-feed.ts` — bounded GET polling and persistence evidence collector.

No strategy, gate, credential, dispatch, action control, execution adapter, or order-routing file was modified.
