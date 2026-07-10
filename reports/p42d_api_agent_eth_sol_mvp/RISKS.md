# Risks

## 1. Mismatched Codebases
- **Risk**: Continuing the runner task without the integration branch would result in inconsistent FSM adapters or incorrect contract references.
- **Mitigation**: Fail-closed by blocking execution.

## 2. Inability to Validate
- **Risk**: Lack of `RUN_READY_GATE.md` prevents confirming whether simulated or live fills are permitted.
- **Mitigation**: Rigid adherence to run-ready gate instructions ensures zero unauthorized real execution.
