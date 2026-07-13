# P46-2D-S2 Production Authority Composition

AGENT_IDENTITY:
  agent_name: Codex primary runtime integration
  task_id: P46_2D_S2_PRODUCTION_AUTHORITY_COMPOSITION_AND_FULL_REPROOF
  branch: p46-2d-s2-production-authority-composition-primary-20260713
  worktree: C:\Users\wekab\Music\Phenix-p46-2d-s1-bridge
  started_at: 2026-07-13
  finished_at: 2026-07-13

## Verdict

`P46_2D_S2_CANONICAL_READER_UNAVAILABLE`

## FACTS

- S1 is preserved and pushed at `40aa8feca55f9f94d281e3618eae9162f6a3f38a`, divergence `0/0` before S2 branching.
- Production `apps/reference/main.py` constructs one in-memory `TradingSessionAuthorityStore`, but does not seed a session, participant, or lease.
- Production main does not construct `CanonicalMemoryStore`, a context publisher, `PhenixReadModelService`, `ProposalDryRunService`, or `RuntimeAuthorityQueryService`.
- The only non-test `CanonicalMemoryStore` construction is in the separate terminal-agent dashboard process.
- `DecisionMaking.latest_portfolio` and `symbol_states` are live caches, but canonical account snapshot identity `latest_portfolio_ref` is read and never published.
- No bounded production lifecycle/reconciliation projection provides all required rows and source identities.
- `ExposureGuard.can_open()` is the reusable non-reserving calculation seam; `reserve()` is separate. It cannot complete dry-run composition without the missing canonical readers and snapshot identities.
- No source/config code was changed because adding a new context store or fixture-backed reader would create competing truth prohibited by the task.

## INFERENCES

- S1 transport is not the blocker. Production truth ownership and publication are.
- Wiring partial readers would make the compatibility handshake falsely healthy and weaken fail-closed behavior.

## ASSUMPTIONS

- The terminal-agent canonical memory writer remains authoritative for its own session runtime, but no approved cross-process read contract currently makes it main-process runtime context truth.

## UNKNOWNS

- Which process is intended to own the Trading Floor context manifest after consolidation.
- Which legitimate runtime API will seed production TradingSession/participant/lease state.
- Whether account and market snapshot identity publication belongs in DecisionMaking or a dedicated existing snapshot projection.

## Closure Boundary

No three-process proof was attempted because process A cannot truthfully advertise mandatory readers. Execution effects, Testnet, provider, adapter, FSM, and exchange calls remained zero.
