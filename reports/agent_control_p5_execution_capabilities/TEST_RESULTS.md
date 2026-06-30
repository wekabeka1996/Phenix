# Test results

## Aurora

- Changed-module compile: PASS.
- Final focused descriptor/publication/API/startup/adapter suite: PASS, 41/41.
- Descriptor model/config-only/exchange-confirmed/stale/unknown tests: PASS.
- Precision/minimum and reduce-only owner tests: PASS.
- No-secret/no-action static scan: PASS.
- No-order startup, direct publication, GET-only routes, and packet budget: PASS.
- Runtime schemas: readiness 1, descriptors 7, packet samples 10; PASS.
- Cockpit polls: 10/10 HTTP 200; persistence +10.

## Cockpit

- TypeScript lint: PASS.
- Production build: PASS, 2,186 modules transformed.
- Focused AgentFeed tests: PASS, 3/3.
- Forbidden ports 7102/8443: PASS.
- Actions disabled: PASS.

## Safety

- Orders/create/place/cancel/modify/amend observed: 0.
- Consequential routes: 0.
- Runtime HTTP methods in bounded scan: GET only.
- Secret values inspected by descriptor builder: 0.
- Live/prod credentials changed: 0.
- WAL JSON files deleted before launch: 0 because none matched.
