# Files changed

## Aurora

- `.gitignore`: tracks the narrow P4 report directory.
- `apps/reference/runtime_profile.py`: typed fail-closed launch profile.
- `apps/reference/bootstrap/domain_builder.py`: no-order execution composition.
- `apps/reference/main.py`: profile telemetry, safe startup skips, and P4 publisher activation.
- `apps/reference/domains/execution_position/fsm.py`: no-order state, listener omission, and action guards.
- `apps/reference/domains/execution_position/adapters/adapter_init.py`: adapter initialization guard.
- `apps/reference/domains/agent_bridge/contracts.py`: direct/relay ownership and P4 publication metadata.
- `apps/reference/domains/agent_bridge/publication.py`: P4 owner/index metadata and canonical timeframe priority.
- `apps/reference/domains/agent_bridge/execution_readiness.py`: runtime-owned no-order isolation invariant.
- `apps/reference/domains/agent_bridge/reducer.py`: direct ownership mapping and narrow decision-tail optimization.
- `tests/domains/agent_bridge/test_no_order_runtime_profile.py`: profile/composition/action/readiness tests.
- `tests/domains/agent_bridge/test_runtime_publication.py`: P4 ownership and timeframe-retention tests.

## Cockpit

No P4 source changes. Existing GET-only client, persistence, six-card UI, forbidden-port checks, and disabled action control were reused and revalidated.
