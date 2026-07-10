# OPERATIONAL RISKS & ATTRIBUTES

This document reviews operational risks and validation safeguards for release attestation.

---

## 1. Operational Risks & Mitigation

- **Source Code Mutations**: An operator might edit source files locally after release validation, introducing untested bugs.
  - *Mitigation*: The path-diff check monitors code directories and fails closed on startup if any files outside of `reports/` or `PRE_SUBMIT_GATE.json` are modified relative to the code-complete SHA.
- **Git Binary Dependency**: The git check requires the `git` binary to run.
  - *Mitigation*: If the git client is unavailable or in a non-git temporary directory, the runner falls back to `P42_MOCK_CHECKOUT_SHA` in unit tests, but requires strict command execution in the live trading arena.
- **Self-Referential Deadlock**: Mandating that `HEAD == Integration SHA` causes a deadlock when committing reports changes the HEAD hash.
  - *Mitigation*: The ancestry check replaces the exact equality check, permitting report commits while keeping code verification intact.
