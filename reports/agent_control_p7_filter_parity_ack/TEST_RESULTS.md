# Test results

## Aurora

- Changed-module `py_compile`: PASS.
- Focused Agent Bridge suite: 41 passed.
- Acknowledgement lifecycle and exact-state ownership: PASS.
- Match/conservative/risky/stale/missing classification: PASS.
- History append/idempotency/transitions: PASS.
- Packet projection/token budget: PASS.
- GET-only/no-order startup suites: PASS.
- Sample/model validation: PASS.
- Static secret/signing/mutation/execution surface scans: zero P7 matches.

## Cockpit

- `npm run lint`: PASS.
- `npm run build`: PASS, 2,186 modules transformed.
- Focused AgentFeed tests: PASS, 3/3.
- Broader trading-agent suite: 38/39; the same unrelated EZE OPEN_INTENT direct-ingress assertion documented in P6 failed.

## Runtime

- Ten GET polls: PASS.
- SQLite delta +10: PASS.
- Compact parity state present: PASS.
- Actions disabled: PASS.
- No consequential command or signed/authenticated endpoint evidence: PASS.
