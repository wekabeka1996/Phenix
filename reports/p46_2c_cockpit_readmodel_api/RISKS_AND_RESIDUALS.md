# Risks And Residuals

## FACTS
- Production app construction without an injected read service fails typed/unavailable; it never falls back to fixtures.
- Context and lifecycle source composition remains a canonical runtime wiring responsibility.
- Historical forensic script `scripts/p46_1g_r_canonical_venue_proof.py` in the canonical worktree was not modified or deleted.

## INFERENCES
- The principal residual is deployment composition, not contract ambiguity.

## ASSUMPTIONS
- Runtime owners can provide deterministic bounded context/lifecycle readers.

## UNKNOWNS
- Long-duration load, multiprocess contention, and cross-domain snapshot skew are unproven.
