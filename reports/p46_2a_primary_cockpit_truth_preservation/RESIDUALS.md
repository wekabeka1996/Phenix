# Residuals

## FACTS

- Cockpit still contains V1 quantity-bearing trading code and local memory/session/token stores.
- The active historical Node observation host was not stopped.
- The snapshot, its `.env`, runtime database, logs, caches, and build output remain untouched in place.
- `npm audit` reports 4 low, 2 moderate, and 3 high dependency vulnerabilities; no automatic upgrade was applied.
- No React runtime smoke was performed.
- The legacy EZE direct-ingress regression test fails (`44/45` broad trading-agent tests pass); this is outside the preservation diff and aligns with the P0 authority conflict slated for isolation.

## INFERENCES

P46-2B must treat execution isolation and store naming/ownership as blocking review items.

## ASSUMPTIONS

Preserving the original snapshot is preferable to cleanup during forensic capture.

## UNKNOWNS

Operational ownership of PID 21984 and its retirement date are unknown.
