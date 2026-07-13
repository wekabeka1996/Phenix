# Residuals

## FACTS

- Exposure decision ID was attached inside FSM processing, but the harness's copied external-command snapshot was taken earlier; final evidence reconstructs the deterministic ID and labels that fact.
- Runtime emitted existing deprecation warnings for V2 received/sized and some lifecycle events lacking JSON schemas.
- The original untracked forensic script still contains direct adapter paths and remains excluded from success evidence.
- Snapshot-age configuration is now enforced; real production publishers that omit compatible timestamps will fail closed and need explicit producer wiring.
- The proof covered an unfilled cancel branch, not fill/close.

## INFERENCES

- A future observability-only change should persist exposure approval evidence before command payload snapshots are copied.

## ASSUMPTIONS

- No broad registry cleanup belongs in S2.

## UNKNOWNS

- Filled lifecycle behavior and production-long-session freshness remain unproven.
