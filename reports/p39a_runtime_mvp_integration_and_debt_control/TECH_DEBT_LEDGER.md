# Tech Debt Ledger

We classified the technical debt addressed or deferred during the P39 merges.

## 1. Action Audit Guard Integration
- **Classification**: `RETIRED`
- **Details**: Accidental execution risk via direct agent commands is retired by enforcing `no_order_observation_mode = True` on all incoming actions.

## 2. Hot-Reload Preflight Check
- **Classification**: `MITIGATED`
- **Details**: Instruction drift on manifest reload is mitigated by calculating hashes and running manifest validation checks before applying new files.

## 3. Session Memory Cockpit Bindings
- **Classification**: `CONVERTED_TO_RUNTIME_CHECK`
- **Details**: Memory carryover and state transitions are bound directly to HTTP lifecycle hooks, enforcing validation checks on incoming payload fields.
