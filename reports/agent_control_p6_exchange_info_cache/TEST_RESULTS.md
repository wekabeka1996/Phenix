# Test results

## Aurora

- Changed-module compile: PASS.
- Final focused Agent Bridge/adapter/filter/no-order/portfolio suite: 60 passed, 4 skipped.
- Live public fetch/cache model validation: PASS.
- Ten runtime packet, readiness and cache samples validate with Pydantic: PASS.
- Static public-client scan: no key/secret/signature or write-method client surface.

## Cockpit

- TypeScript lint: PASS.
- Production build: PASS, 2,186 modules transformed.
- Focused AgentFeed tests: PASS, 3/3.
- Broader trading-agent suite: 38/39; unrelated EZE OPEN_INTENT assertion failed and Cockpit source was not changed by P6.

## Runtime safety

- Final signed/authenticated HTTP matches: 0.
- Order/create/place/cancel/modify/amend matches: 0.
- Consequential AgentFeed routes: 0.
- Cockpit actions: disabled.
