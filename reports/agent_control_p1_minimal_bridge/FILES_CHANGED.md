# Files changed

## Aurora / Phenix

- `apps/reference/api/main.py` — registers the isolated GET-only bridge.
- `apps/reference/domains/agent_bridge/__init__.py`
- `apps/reference/domains/agent_bridge/contracts.py`
- `apps/reference/domains/agent_bridge/reducer.py`
- `apps/reference/domains/agent_bridge/routes.py`
- `tests/domains/agent_bridge/test_agent_feed_reducer.py`
- `reports/agent_control_p1_minimal_bridge/*` — contract, evidence, sample, and verdict.

## Cockpit workspace

- `server.ts` — two read-only proxy routes and validated persistence.
- `src/shared/contracts/agentFeed.ts`
- `src/shared/contracts/index.ts`
- `src/server/agentFeed/AuroraAgentFeedClient.ts`
- `src/server/agentFeed/AgentFeedStore.ts`
- `src/client/api/agentOsClient.ts`
- `src/components/agentFeed/AgentFeedPanel.tsx`
- `src/App.tsx`
- `tests/trading-agent/AgentFeedBridge.test.ts`

`npm ci` populated ignored `node_modules` from the existing lockfile. No environment/config value, credential, strategy behavior, gate, dispatch, or execution route was changed. Pre-existing dirty files in Phenix were preserved.
