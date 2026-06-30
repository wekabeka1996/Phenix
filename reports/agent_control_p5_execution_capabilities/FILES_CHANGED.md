# Files changed

- `.gitignore`: tracks the narrow P5 report directory.
- `apps/reference/domains/agent_bridge/contracts.py`: capability, constraint, summary, and P5 publication contracts.
- `apps/reference/domains/agent_bridge/capabilities.py`: allowlisted builder and requested-symbol projection.
- `apps/reference/domains/agent_bridge/execution_readiness.py`: invariant classification from descriptor evidence.
- `apps/reference/domains/agent_bridge/reducer.py`: compact card integration without duplicate readiness snapshot.
- `apps/reference/main.py`: direct publisher version `p5.v0`.
- `tests/domains/agent_bridge/test_execution_capabilities.py`: descriptor, classification, no-call, no-secret, projection, and budget tests.
- `tests/domains/agent_bridge/test_execution_readiness.py`: truthful partial-cache expectation.

Cockpit source did not change. Existing GET-only, forbidden-port, persistence, and disabled-action behavior was revalidated.
