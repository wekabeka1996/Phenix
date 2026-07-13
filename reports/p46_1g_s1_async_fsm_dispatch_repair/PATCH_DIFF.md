# Patch Diff

## FACTS

| File | Change |
|---|---|
| `apps/reference/bootstrap/async_runtime.py` | Add loop readiness handshake and fail-closed startup. |
| `apps/reference/domains/execution_position/adapters/async_scheduling.py` | Add typed loop rejection and safe same/cross-thread scheduling. |
| `apps/reference/domains/execution_position/fsm.py` | Await bounded guardian shutdown. |
| `tests/domains/execution_position/test_p46_1g_s1_async_dispatch.py` | Add deterministic DEF-E11, thread, duplicate, and adapter-boundary proof. |
| `scripts/p46_1g_s1_canonical_venue_proof.py` | Add canonical-loop Testnet proof harness with emergency-only direct containment. |
| `reports/p46_1g_s1_async_fsm_dispatch_repair/*` | Add compact forensic and validation reports. |

- The pre-existing `scripts/p46_1g_r_canonical_venue_proof.py` is intentionally not part of the patch.

## INFERENCES

- The patch is bounded to event-loop dispatch, its tests, proof harness, and reports.

## ASSUMPTIONS

- No generated runtime logs will be committed.

## UNKNOWNS

- Final commit SHAs are populated by Git history rather than predicted here.
