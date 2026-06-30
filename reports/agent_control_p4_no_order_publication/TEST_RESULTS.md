# Test results

## Aurora

- Changed-module compile: PASS.
- Final profile/publication/API/adapter/startup suite: PASS, 34/34.
- Schema validation: market 1, readiness 1, packets 10; PASS.
- Runtime no-order observation: PASS.
- Ten Cockpit polls: PASS, 10/10.
- Concurrent atomic reads: PASS, 40/40.

## Cockpit

- `npm run lint`: PASS.
- `npm run build`: PASS, 2,186 modules transformed.
- `AgentFeedBridge.test.ts`: PASS, 3/3.
- Forbidden ports and GET-only client: PASS through focused tests.
- Persistence delta: PASS, +10 rows.
- Action controls disabled: PASS by source contract and focused persistence test.

## Safety

- Exchange order/cancel/modify commands observed: 0.
- Consequential Cockpit routes called: 0.
- Final runtime HTTP methods: 394 GET, 0 non-GET.
- Live/prod credentials changed: 0.
- Secret values inspected by publisher/readiness probe: 0.
- Main restarts: 3 controlled launches; WAL JSON pre-clean performed before each, 0 matching files deleted.
- Ports 7102/8443 used by this bridge: 0.

## UI

- API/build/component evidence: PASS.
- Rendered DOM: BLOCKED by unavailable in-app browser; not claimed.
