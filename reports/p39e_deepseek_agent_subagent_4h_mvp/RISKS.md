# Risks

## 1. Out-of-sync Branches
- **Risk**: Continuing the runner task without the integration branch would result in outdated FSM configurations, missing validation gates, or incorrect contract references.
- **Mitigation**: Fail-closed by blocking execution with the verdict `BLOCKED_RUN_READY_GATE`.

## 2. Inability to Validate
- **Risk**: Lack of `RUN_READY_GATE.md` prevents confirming whether simulated or tiny testnet fills are permitted.
- **Mitigation**: Rigid adherence to run-ready gate instructions ensures zero unauthorized real execution.
