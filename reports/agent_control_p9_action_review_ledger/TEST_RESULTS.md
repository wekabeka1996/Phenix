# Test results

## Aurora

- Changed-module compile: PASS.
- Focused Agent Bridge suite: 59 passed.
- ActionReview model, taxonomy, no-model/no-execution statuses: PASS.
- Forbidden order/fill/model/secret cases: PASS.
- Append/idempotency/concurrency/revision/supersession: PASS.
- Outcome consistency and no-PnL guard: PASS.
- Packet linkage/projection/token budget: PASS.
- Existing parity, readiness, publication, no-order, GET-only tests: PASS.
- Runtime ledger CLI lint: PASS.
- Two sample rows and ten runtime packets: PASS.

## Cockpit

- TypeScript lint: PASS.
- Production build: PASS, 2,186 modules.
- Focused AgentFeed/ActionReview tests: PASS, 3/3.
- Actions disabled and reserved ports rejected: PASS.

## Runtime safety

- Ten measured GET polls and SQLite +10: PASS.
- Packet-linked pre/outcome review: PASS.
- Consequential/model-provider requests: zero observed.
