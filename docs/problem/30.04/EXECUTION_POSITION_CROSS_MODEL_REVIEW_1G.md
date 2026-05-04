# Cross-model review — Model 1G findings on `execution_position`

Scope: read-only verification against `/mnt/data/execution_position.zip`.

Status legend:
- CONFIRMED: directly visible in source and materially relevant.
- PARTIAL: source pattern exists, but 1G wording overclaims or severity needs narrowing.
- REJECT / NOT PROVEN: not supported by the inspected code, or needs runtime/full-repo proof.

## Executive verdict

Model 1G is useful. It catches several real surfaces that my master audit either already had or should explicitly add. However, it also uses inflated wording in a few places: some patterns are intentional bounded seams, not automatically defects.

The most important new additions to carry forward are:

1. `adapter_init.py` defaults unresolved mode to `testnet` and falls into `shadow_mode` on missing credentials.
2. `close_submission_adapter.py` turns `requested_qty >= live_position_qty` into full close without explicit mismatch telemetry.
3. `exposure_manager.py` detects flip by direction only, while `exposure_guard.py` subtracts full current symbol exposure for `is_flip`.
4. `event_handlers.py` pops `_pending_entry_meta` before checking `PARTIALLY_FILLED`.
5. `event_handlers.py` dedupes fill events without `tradeId` as `fill_{orderId}_{symbol}`, which can suppress multiple valid partial fills from the same order if the adapter omits trade id.
6. `authoritative_restore_apply.py` intentionally mutates FSM state directly during authoritative restore; acceptable only if treated as restore-apply seam, not normal FSM transition.

## Finding matrix

| 1G group | Claim | Review verdict | Severity | Notes |
|---|---|---:|---:|---|
| G1 | `async_scheduling.py` fire-and-forget scheduling can hide task failure / lacks shutdown result ownership | CONFIRMED | P2 | `_submit_async()` creates task/future without retaining handle/done callback. This matches my Phase 2 P2. |
| G1 | unstable event loop capture can silently lose `OrderGuardian` | PARTIAL | P2 | No-loop guardian start is deferred and logged at debug, not marked as failed. It may be retried only if startup path calls scheduler again. Needs runtime test. |
| G1 | `adapter_init.py` hardcoded fallback `mode="testnet"` | CONFIRMED | P1/P2 | Source has `mode = "testnet"` default and fallback to testnet on resolver/global mode errors. This violates strict config philosophy unless startup validation guarantees earlier failure. |
| G1 | missing credentials convert execution to `shadow_mode` instead of fail-fast | CONFIRMED | P1/P2 | Source sets `self.shadow_mode = True` and returns. This may be intentional safe simulation, but live-like execution should not silently degrade. |
| G1 | WS failure switches to REST fallback without proof | PARTIAL | P2 | Source logs `REST polling fallback active` when WS client fails. Need verify watchdog/rest polling is actually active in that mode. |
| G2 | `CancelSubmissionRawPayload` validates context fields then drops them before adapter call | CONFIRMED_BUT_NOT_DEFECT_BY_ITSELF | P3 | This is a bounded raw-intake -> minimal adapter contract seam. It is only a bug if the dropped context is needed for downstream truth/forensics. |
| G2 | `close_submission_adapter.py` silently clips close qty to live position qty | PARTIAL_CONFIRMED | P2 | Code uses live `position_amt`; if requested qty >= live qty, final close uses full live qty. Safer than over-closing, but it hides requested-vs-live mismatch unless logged. |
| G2 | `close_executor.py` overuses `Any` | CONFIRMED | P3 | Many `Any` annotations exist. It weakens static contracts, but not a direct runtime defect. |
| G3 | Flip detection uses direction only, not size | CONFIRMED | P1/P2 | `ExposureManager` marks `is_flip=True` when intent side differs from current side. It does not check whether qty/notional is enough to actually flip or fully offset. |
| G3 | micro order can subtract full current exposure in `ExposureGuard` | CONFIRMED_CANDIDATE | P1/P2 | When `is_flip`, guard subtracts current symbol notional/margin and omits current symbol margin from concentration estimate. Needs targeted test with tiny opposite-side order vs large existing position. |
| G3 | soft clipping mutates payload | CONFIRMED | P2/P3 | `ExposureManager` mutates `pld["qty"]` and adds `pld["exposure_clip"]`. This is action-impacting mutation. It may be intended, but should be explicit in contract/tests. |
| G3 | float/Decimal mix in shadow notional can create precision noise | CONFIRMED | P3 | `check_shadow_notional()` compares adapter `shadow_notional` with `float(portfolio_notional)`. Low severity unless thresholds are tight. |
| G4 | `bracket_health.py` hardcodes strategy names | CONFIRMED | P2 | Recovery supports `md_amr`, `aurora`, explicitly rejects `mean_reversion`, and rejects unknown strategy IDs. This is contract limitation, not silent bug, but it blocks extension. |
| G4 | `bracket_manager.py` parallel placement fallback can duplicate bracket side after partial success | CONFIRMED | P1 | Same as my Phase 2 P1. `gather(... return_exceptions=False)` then sequential retry can resubmit a side that already succeeded/in-flight. |
| G4 | `bracket_math.py` casts float -> str -> Decimal | CONFIRMED_LOW | P3 | `_to_decimal(value)` uses `Decimal(str(value))`. This is better than `Decimal(float)`, but still accepts float inputs. Stronger contract should prefer Decimal/string only. |
| G5 | `authoritative_restore_apply.py` directly mutates FSM state | CONFIRMED_WITH_CONTEXT | P2 | It intentionally mutates `manage_flow.state`, `close_flow.state`, bracket snapshots. Acceptable only as authoritative restore seam; should never be generalized as normal transition path. |
| G5 | `event_handlers.py` removes pending entry metadata before partial-fill handling | CONFIRMED | P1/P2 | `_pending_entry_meta.pop(order_id)` happens before `_fill_status` check. This can break advanced stale-cancel/reprice metadata for a still-live partially-filled LIMIT entry. |
| G5 | dedupe suppresses real fills if `tradeId` absent | CONFIRMED | P1/P2 | Event key falls back to `fill_{orderId}_{symbol}`. Multiple partial fills without tradeId will be treated as duplicates. |
| G5 | telemetry written before core FSM successful processing | PARTIAL | P2/P3 | `ORDER_FILLED` is logged before later state updates/OrderIndex marking/bracket processing. This can create forensic “logged but downstream failed” ambiguity. Needs classification, not blanket rejection. |

## Recommended added packages after 1G review

Add these to the previously proposed package queue:

### Package E — Adapter mode fail-closed audit
- Prove whether live/hybrid can enter `testnet` fallback or `shadow_mode` after config errors.
- Expected behavior: live-like misconfiguration must fail startup or emit explicit fatal config event.

### Package F — Exposure flip semantics hardening
- Test tiny opposite-side order against large current position.
- `is_flip` must account for requested order size relative to current net position.
- Do not subtract full current exposure unless the submitted order can actually neutralize/flip it.

### Package G — Fill identity and partial-fill metadata hardening
- Do not remove `_pending_entry_meta` on `PARTIALLY_FILLED`.
- If `tradeId` is missing, dedupe must include enough differentiators: fill qty, cumulative qty, event time, update id, or a canonical adapter-provided fill sequence.

### Package H — Close requested-vs-live mismatch telemetry
- If requested close qty >= live qty, full close may be safe, but it should emit explicit mismatch/normalization telemetry.
- If requested close qty is far larger than live qty, classify as policy/state mismatch, not silent normal behavior.

