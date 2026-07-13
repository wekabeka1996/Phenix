# P46-1G-S1 Async FSM Dispatch Repair

## FACTS

- Task: `P46_1G_S1_CANONICAL_ASYNC_FSM_DISPATCH_REPAIR`.
- Starting SHA and remote SHA: `fb4a1720813598de5e4d8dda6830b7b6ecf883d5`; branch divergence was `0/0`.
- Runtime repair commit: `605d66c8`.
- Harness/report implementation tip: `a68d8749`; no source or test changes follow this SHA.
- Both commits were pushed successfully to `origin/p46-1b-canonical-integration-primary-20260711`.
- The tracked worktree was clean. The pre-existing forensic script `scripts/p46_1g_r_canonical_venue_proof.py` was untracked, had SHA256 `6b5a05ec066cfd1cef3f68ba731ae8c131250fff4b82b65267f05541d5499771`, and was not modified.
- Production constructs one `AsyncLoopRuntime`, starts it, and registers its loop on the canonical `ExecPosFSM`.
- The repair waits for loop readiness, rejects stopped/closed loops, dispatches cross-thread coroutines with `run_coroutine_threadsafe`, and waits for guardian shutdown.
- Deterministic HTTP/TCP tests prove one command emission, one FSM ingress, one recording-adapter call, and no second action for duplicate HTTP/TCP delivery.
- A real Binance Futures Testnet read preflight selected `DOGEUSDT`. One V2 request was accepted by HTTP and internally sized to `138`; the existing exposure guard rejected it with `SOFT_LIMIT_BELOW_CLIP_MIN` before adapter submission.
- Opening adapter submits: `0`. Venue order identities: `0`. Independent venue reads showed position `0` and open orders `0` for the proof symbol.
- No second V2 opening intent was sent. No direct adapter fallback was used.

## INFERENCES

- DEF-E11 is repaired at the canonical sync/async dispatch seam for a live registered loop.
- The remaining blocker is sizing-to-exposure-guard compatibility at the exact `10.0` USDT target, not async dispatch.

## ASSUMPTIONS

- The existing `apps/reference/main.py` construction remains the production runtime owner.

## UNKNOWNS

- Real adapter submit, venue acknowledgement, canonical cancel/close, and lifecycle reconciliation remain unproven through the repaired path.

## Verdict

`P46_1G_ASYNC_DISPATCH_REPAIRED_TESTNET_NOT_RUN`
