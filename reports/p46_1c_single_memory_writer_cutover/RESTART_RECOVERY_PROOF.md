# Restart And Recovery Proof

## FACTS

Focused tests prove:

1. explicit temporary absolute root and validated config;
2. multiple canonical records appended;
3. store/runtime object discarded and reconstructed;
4. identical ordered history recovered;
5. deterministic summary/finalize/carryover across repeated calls;
6. append after restart continues sequence without loss;
7. invalid truncated final JSONL record causes strict read failure;
8. explicit `recover()` preserves the valid prefix, atomically removes only the invalid tail, and returns `CanonicalMemoryRecovery` evidence;
9. append succeeds after bounded repair;
10. corrupt middle record fails visibly and is never skipped;
11. identical retry is suppressed; conflicting duplicate identity raises;
12. separate sessions and agents return isolated views.

## INFERENCES

- Reopen/replay and single-process crash-tail recovery satisfy this bounded package; they do not prove multiprocess locking.

## ASSUMPTIONS

- Filesystem atomic replacement semantics match those already used by project persistence helpers.

## UNKNOWNS

- Power-loss behavior on every supported filesystem was not externally fault-injected.

