# Test results

## Aurora

- Publication/bridge/main/relay compile: PASS.
- Final Python validation: PASS, 15/15 (`tests/domains/agent_bridge` and `tests/api/test_api_main.py`).
- Tests cover publication schemas, same-directory atomic write/read, invalid publication rejection, no temp residue, runtime-publication priority, explicit disk fallback, event-bus registration, missing readiness, secret-safe inspection, GET-only routes, no submit call, and packet budget.
- Live publication files: 3/3 valid.
- Live Cockpit→Aurora polls: 10/10 HTTP 200.

## Cockpit

- P3 changes: none.
- Lint: PASS.
- Production build: PASS (Vite, 2186 modules transformed).
- Focused AgentFeed tests: PASS, 3/3.
- Live persistence: 10 rows inserted; latest id matched the tenth packet.
- State remained disarmed/stopped.

## Safety

- Consequential requests: 0.
- Orders placed by P3: 0.
- Secrets read/changed: 0.
- Main runtime restarts by P3: 0.
- WAL files deleted by P3: 0.
- Ports 7102/8443 used by Cockpit/read bridge: 0.

## Artifact validation

- Required P3 files: PASS, 16/16 present and non-empty.
- Recorded packet samples: PASS, 10/10 GET/200 and schema-valid.
- Secret scan: PASS.
- Final verdict marker: PASS.
- `git diff --check`: PASS (line-ending warnings only).
