# Test results

## Aurora

- Python compile for agent bridge and API main: PASS.
- Final combined pytest (`tests/domains/agent_bridge` plus `tests/api/test_api_main.py`): PASS, 10/10.
- Coverage includes bounded seek/tail, partial lines, explicit missingness, budgets, GET-only routes, runtime readiness evidence, secret-attribute exclusion, and an execution method that raises if called.
- Actual health GET: PASS, HTTP 200.
- Actual packet GET through Cockpit: PASS, 10/10.
- Actual readiness GET: PASS, HTTP 200.

## Cockpit

- `npm run lint`: PASS.
- `npm run build`: PASS; Vite transformed 2,186 modules.
- Focused AgentFeed tests: PASS, 3/3 in the final combined run.
- Forbidden ports 7102/8443 remain rejected by tests.
- `AGENT_FEED_ACTIONS_ENABLED=false` remains tested.
- Persistence live check: PASS, 0 to 10 rows; failed poll remained 10.

## Runtime safety

- Cockpit state: `armed=false`, `status=stopped`.
- Aurora access log bridge methods: GET only.
- Failed fetch visible as HTTP 502: PASS.
- Write/consequential requests invoked: 0.
- Orders placed by this package: 0.
- Secrets read or changed: 0.

## Known limitations

- In-app browser unavailable, so rendered DOM refresh is not proven.
- Full trading-agent suite retains the unrelated P1-observed EZE direct-execution test failure; P2 does not touch that path.
- NPM dependency audit findings reported in P1 were not automatically mutated in this package.

## Artifact validation

- Required files: PASS, 14/14 non-empty artifacts.
- Runtime samples: PASS, 10/10 JSONL observations validate as `AgentFeedPacket` with GET/200/read-only/budget invariants.
- Secret-pattern scan: PASS.
- `git diff --check` on P2 scope: PASS (line-ending warning only).
