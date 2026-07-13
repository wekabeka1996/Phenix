# Validation

| Command | Result |
|---|---|
| S1 local/remote/ancestry/status checks | clean, `0/0`, required ancestors present |
| `rg` production construction inventory | no main `CanonicalMemoryStore` or `RuntimeAuthorityQueryService` construction |
| `rg` production authority publishers | no session/participant/lease seeding |
| `rg latest_portfolio_ref apps/reference` | read only; no publisher |
| `python -m pytest tests/domains/shadow_telemetry -q` | 139 passed |
| `python -m pytest tools/deepseek-terminal-agent/tests -q` | 578 passed, 13 skipped |
| Cockpit `npm run test:trading-agent` | 44 passed, 1 allowed known legacy EZE failure |
| Cockpit `npm run lint` | passed |
| Cockpit `npm run build` | passed |
| `git diff --check` before reports | passed |

Skipped tests are not counted as proof. No runtime venue or provider validation was attempted.
