# Test results

## Aurora

- Changed-module compile: PASS.
- Focused Agent Bridge suite: 49 passed.
- Required identity/model validation: PASS.
- Exact-state/wrong-state/wrong-symbol/wrong-environment: PASS.
- Mandatory expiry/review and 30-day cap: PASS.
- Conservative/risky/stale/missing/match semantics: PASS.
- Normalized file hash/provenance: PASS.
- Packet identity/expiry projection and token budget: PASS.
- No-order and GET-only route tests: PASS.
- Runtime packet model validation: 10/10 PASS.
- Static safety scan: no secret read, signing implementation, write route, or execution call.

## Cockpit

- TypeScript lint: PASS.
- Production build: PASS, 2,186 modules.
- Focused AgentFeed tests: PASS, 3/3.
- Reserved 7102/8443 rejection and disabled actions: PASS.

## Runtime

- Ten GET polls and SQLite +10: PASS.
- P8 compact state present: PASS.
- No consequential command/signed endpoint evidence: PASS.
