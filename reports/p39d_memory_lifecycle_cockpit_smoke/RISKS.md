# Risks

FACTS:
- No exchange execution path was added.
- No mainnet/live code path was added.
- Memory writes are append-only at model level and duplicate reflection IDs are rejected.

INFERENCES:
- Operational risk is low for exchange safety and medium for future lifecycle integration because the 4-hour runner is still absent.

ASSUMPTIONS:
- Persisting under the existing session root is acceptable for Cockpit runtime memory.

UNKNOWNS:
- Future retention/compaction policy for large memory files is not implemented.
- Browser UI smoke was not run; API smoke was run.
