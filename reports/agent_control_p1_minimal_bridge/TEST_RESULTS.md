# Test results

## Aurora

- `python -m compileall -q apps/reference/domains/agent_bridge apps/reference/api/main.py` — PASS.
- `python -m pytest tests/domains/agent_bridge/test_agent_feed_reducer.py tests/api/test_api_main.py -q` — PASS, 8 tests (4 bridge and 4 API initialization).
- Tests cover bounded EOF reads, partial lines, explicit missingness, budget metadata/cap, no execution call, and GET-only routes.
- Offline real-source packet generation — PASS; BTCUSDT/ETHUSDT packet produced under budget with explicit stale/missing evidence.

## Cockpit

- Initial `npm run lint` / `npm run test:trading-agent` — BLOCKED because dependencies were absent (`tsc` and `tsx` not found).
- `npm ci` — PASS; 313 packages installed from lockfile. NPM reported 9 dependency audit findings (4 low, 2 moderate, 3 high); no automatic dependency mutation was performed.
- `npm run lint` — PASS.
- `npm run build` — PASS; Vite transformed 2,186 modules and produced the production bundle.
- `node --import tsx --test tests/trading-agent/AgentFeedBridge.test.ts` — PASS, 3 tests.
- `npm run test:trading-agent` — 38 PASS, 1 FAIL. All 3 new AgentFeedBridge tests pass. The failing existing EZE direct-execution test expected one call and observed zero at `PhenixTradingAgentService.test.ts:525`; this package does not modify that execution path.

## Artifact validation

- Sanitized sample parses as JSON and validates against the Python AgentFeedPacket model — PASS.
- Compact sample budget metadata: 4,420 bytes / 1,105 estimated tokens — PASS.
- Required report files exist and are non-empty — PASS, 11 artifacts.
- Secret-pattern scan and route-method scan — PASS.
- FastAPI TestClient smoke: health 200, sources 200, packet 200; packet schema `agent-feed/v0` and 7,863 response bytes — PASS.
- Orders placed — NONE. No consequential endpoint was called.
