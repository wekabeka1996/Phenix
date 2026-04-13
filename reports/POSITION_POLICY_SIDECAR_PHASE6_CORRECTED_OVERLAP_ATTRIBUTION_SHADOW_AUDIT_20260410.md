# REPORT - POSITION POLICY SIDECAR PHASE 6 CORRECTED OVERLAP-ATTRIBUTION SHADOW AUDIT 2026-04-10

## Executive Verdict

- This task re-audits only the Phase 6 overlap blocker on the already frozen post-restart slice.
- Audit verdict: corrected overlap attribution does not materially reduce the current Phase 6 blocker to admission-grade confidence.
- Phase posture remains `still_shadow_only`.
- This task does not promote the sidecar, does not reopen Package 5, and does not change the current Phase 6 admission outcome.
- Current blocker reassessment: `overlap ambiguity` remains the correct single blocking reason cluster, but it is now narrower and better specified:
  - the published overlap method is over-inclusive,
  - the corrected close-only audit finds `0/8` emitted recommendations with proven same-lifecycle overlap against a real incumbent close mechanism,
  - `1/8` recommendations remains timing-ambiguous,
  - `7/8` recommendations have `no_overlap_proven`.

## Current Overlap Method Audit

### Files inspected

- [tools/forensics/position_policy_sidecar_validation.py](../tools/forensics/position_policy_sidecar_validation.py)
- [artifacts/position_policy_sidecar/package52_post_restart_runtime_review_20260410.json](../artifacts/position_policy_sidecar/package52_post_restart_runtime_review_20260410.json)
- [artifacts/position_policy_sidecar/package52_post_restart_runtime_analysis_20260410.json](../artifacts/position_policy_sidecar/package52_post_restart_runtime_analysis_20260410.json)
- [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl)
- [logs/order_log_v1.jsonl](../logs/order_log_v1.jsonl)

### Where the current method selects overlap candidates

- `_close_rows()` in [tools/forensics/position_policy_sidecar_validation.py](../tools/forensics/position_policy_sidecar_validation.py) currently loads order-log candidates by admitting any order-log row with:
  - `ORDER_FILLED`,
  - `ORDER_REJECTED`,
  - `ORDER_STATE_CHANGED`.
- The same function also appends trade-lifecycle rows without a close-only event filter:
  - it iterates all `iter_trade_lifecycle_records(...)`,
  - maps each row to `event_type = record.get("status") or record.get("event_type")`,
  - and uses `close_ts_ms` or `updated_ts_ms` as candidate timestamps.
- `_recommendation_overlaps()` then matches each recommendation to the nearest candidate on the same symbol inside the 15-minute window.

### Why the current candidate set is over-inclusive

- The current order-log admission rule is semantic-blind:
  - it does not require `order_kind` to be close-bearing,
  - it does not require `close_reason`,
  - it does not exclude `ENTRY` fills.
- The current trade-lifecycle admission rule is also semantic-blind:
  - it does not restrict candidates to terminal close, reconcile, disappearance, or cleanup events,
  - it admits any trade-lifecycle row surfaced by the iterator as long as a candidate timestamp exists.
- Repo-backed proof from the frozen slice:
  - the currently published overlap artifact reports `matched_recommendations = 8`,
  - the published `8/8` post-fix matched overlaps resolve to `ORDER_FILLED` rows in [logs/order_log_v1.jsonl](../logs/order_log_v1.jsonl),
  - every one of those matched order rows is `order_kind = ENTRY`,
  - every one of those matched order rows has `close_reason = NONE`.
- Additional nearby-window proof from the same frozen slice:
  - current method sees `40` nearby `ORDER_FILLED|ENTRY|None` order-log matches across the 8 recommendations,
  - only `5` nearby order-log rows are truly close-bearing `ORDER_FILLED|SL|SL`,
  - therefore the current method is dominated by entry-fill overmatch rather than incumbent close attribution.

### Why entry fills must be excluded

- Entry fills are not incumbent close mechanisms.
- Counting entry fills as overlap candidates can only prove temporal proximity to position opening, not interaction with:
  - `ExitManager`,
  - regime-flip close,
  - max-hold close,
  - bracket terminal exits,
  - orphan cleanup,
  - reconcile close.
- In the frozen slice, the current published overlap picture is materially distorted because the nearest admitted candidates are entry fills rather than close-bearing events.
- Therefore current published overlap outputs are not reliable enough for Phase 6 promotion analysis.

## FACTS

- [reports/POSITION_POLICY_SIDECAR_PACKAGE5_CLOSURE_REVIEW_20260410.md](POSITION_POLICY_SIDECAR_PACKAGE5_CLOSURE_REVIEW_20260410.md) formally closed Package 5 and stated the next exact step was Phase 6 review.
- [reports/POSITION_POLICY_SIDECAR_PHASE6_ACTION_READINESS_GATE_REVIEW_20260410.md](POSITION_POLICY_SIDECAR_PHASE6_ACTION_READINESS_GATE_REVIEW_20260410.md) recorded:
  - current Phase 6 decision `OUTCOME_B_STAY_IN_SHADOW`,
  - single blocking reason cluster `overlap ambiguity`.
- The frozen slice boundary comes from [artifacts/position_policy_sidecar/package52_post_restart_runtime_analysis_20260410.json](../artifacts/position_policy_sidecar/package52_post_restart_runtime_analysis_20260410.json):
  - `mode_active_ts_ms = 1775728324358`,
  - `slice_start_ts_ms = 1775728324358`,
  - `slice_end_ts_ms = 1775827331073`,
  - `duration_hours = 27.501865277777778`,
  - one `MODE_ACTIVE` boundary only.
- The frozen slice summary from [artifacts/position_policy_sidecar/package52_post_restart_runtime_review_20260410.json](../artifacts/position_policy_sidecar/package52_post_restart_runtime_review_20260410.json) records:
  - `RECOMMENDED = 8`,
  - current published weak-overlap `matched_recommendations = 8`,
  - sidecar remained in shadow,
  - `action_skipped_count = 0`.
- Current close truth remains frozen by [position_policy_sidecar_roadmap_v_1.md](../position_policy_sidecar_roadmap_v_1.md):
  - symbol-scoped,
  - reduce-only,
  - based on current live net symbol position,
  - not lifecycle-targeted,
  - not order-id-targeted,
  - not position-id-targeted.
- [apps/reference/domains/execution_position/close_executor.py](../apps/reference/domains/execution_position/close_executor.py) confirms live close execution resolves against current `positionAmt` and routes via `place_market_reduce_only`.
- Corrected close-only audit on the frozen slice explicitly excluded entry fills.
- Under the corrected rules, order-log close-like candidates were limited to `ORDER_FILLED` rows that were close-bearing by semantics:
  - `order_kind in {TP, SL, CLOSE}`,
  - or non-null `close_reason`.
- Under the corrected rules, generic `ORDER_FILLED` entry rows were excluded.
- Under the corrected rules, generic `ORDER_REJECTED` and `ORDER_STATE_CHANGED` rows were excluded as overlap candidates and used only as surrounding context if needed.
- Under the corrected rules, lifecycle close-like candidates were limited to:
  - `POSITION_DISAPPEARANCE_ATTRIBUTED`,
  - `EXECUTION_WS_TERMINAL_CORRELATED`,
  - `EXECUTION_CLOSE_RECONCILED`,
  - `ORPHANED_TTL`.
- Corrected audit output on the frozen 8 recommendations found:
  - `0/8` proven same-lifecycle overlap with a real incumbent close,
  - `1/8` timing-ambiguous recommendation,
  - `7/8` `no_overlap_proven`.
- Corrected order-log proof that entry fills were excluded:
  - for the first 6 recommendations, `nearby_order_log_close_candidates = []`,
  - the only surviving order-log close candidates in the full 8-recommendation set were `5` `SL` fill rows on `BTCUSDT`,
  - all current-method entry-fill overlaps disappeared once entry semantics were excluded.
- Recommendation-specific frozen facts:
  - `pps:SOLUSDT:1775760306203:44044` has nearby lifecycle close-like context `ORPHANED_TTL` at `1775760304568` with delta `-1635 ms`; its `fill_correlation.manage_state_after = FLAT`.
  - `pps:SOLUSDT:1775760604575:44442` has nearby lifecycle close-like context only the same prior-lifecycle `ORPHANED_TTL` with delta `-300007 ms`; its fill correlation points to current entry lifecycle `aurora_SOLUSDT_1775760304347`.
  - `pps:SOLUSDT:1775760912887:44899` has nearby lifecycle close-like context only the same prior-lifecycle `ORPHANED_TTL` with delta `-608319 ms`; its fill correlation points to current entry lifecycle `aurora_SOLUSDT_1775760304347`.
  - `pps:ETHUSDT:1775763903359:48740` has no corrected close-like candidates in the 15-minute window; its `fill_correlation.manage_state_after = FLAT`.
  - `pps:BTCUSDT:1775765104093:50764` has no corrected close-like candidates in the 15-minute window; its `fill_correlation.manage_state_after = FLAT`.
  - `pps:SOLUSDT:1775767501351:53852` has no corrected close-like candidates in the 15-minute window; its fill correlation points to current entry lifecycle `aurora_SOLUSDT_1775767201046`.
  - `pps:BTCUSDT:1775769303362:56248` has corrected close-like candidates from the prior lifecycle:
    - `SL` order-log fills around `1775768666155..1775768666287`,
    - `EXECUTION_WS_TERMINAL_CORRELATED` at `1775768666274`,
    - `POSITION_DISAPPEARANCE_ATTRIBUTED` at `1775768666864` with `attribution = proven_exchange_bracket_close`,
    - current position open timestamp is later: `1775769023.864692`.
  - `pps:BTCUSDT:1775773808468:62150` has corrected close-like candidates from the prior lifecycle:
    - `SL` order-log fills around `1775773029132..1775773029218`,
    - `EXECUTION_WS_TERMINAL_CORRELATED` at `1775773029207`,
    - `POSITION_DISAPPEARANCE_ATTRIBUTED` at `1775773032869` with `attribution = proven_exchange_bracket_close`,
    - current position open timestamp is later: `1775773808.4153225`,
    - its `fill_correlation.manage_state_after = FLAT`.

## INFERENCES

- The current published overlap sample is unsuitable for promotion because it overmatches entry fills and therefore does not prove interaction with incumbent close behavior.
- Once entry fills are excluded, the frozen slice no longer shows a broad overlap surface. It shows mostly absence of proven overlap.
- The corrected audit materially improves understanding of the blocker:
  - the blocker is not "too many proven overlaps",
  - the blocker is "too little admission-grade overlap attribution".
- Nearby real close-like events exist for some recommendations, but in the corrected audit they belong to prior lifecycles rather than the currently recommended lifecycle.
- The first SOL recommendation remains timing-ambiguous because it occurs 1.6 seconds after a prior-lifecycle `ORPHANED_TTL` while still carrying stale prior-lifecycle fill correlation.
- The remaining 7 recommendations do not have proven same-lifecycle incumbent overlap in the corrected slice.

## ASSUMPTIONS

- The 15-minute overlap window remains the comparison window for this corrected audit because the frozen weak-overlap artifact used that same window and this task is an attribution correction, not a parameter redesign.
- A recommendation is counted as overlapping only when the corrected close-like candidate survives semantic filtering and is not disproven by lifecycle timing evidence.
- Prior-lifecycle close events inside the raw 15-minute window are not sufficient by themselves to prove overlap with the newly recommended lifecycle.

## UNKNOWNS

- Whether a narrower time window than 15 minutes would remove the single remaining ambiguous SOL timing case.
- Whether future action-grade linkage work will eliminate stale prior-lifecycle `fill_correlation` on recommendation rows entirely.
- Whether a future corrected audit over a longer frozen sample would surface any true same-lifecycle overlaps with `ExitManager`, regime-flip close, or max-hold close.

## Corrected Close-Candidate Rules

### Inclusion rules

- Include order-log rows only if they are explicitly close-bearing:
  - `event_type = ORDER_FILLED`,
  - and `order_kind in {TP, SL, CLOSE}` or `close_reason` is non-null.
- Include lifecycle rows only if they are explicitly close-like:
  - `POSITION_DISAPPEARANCE_ATTRIBUTED`,
  - `EXECUTION_WS_TERMINAL_CORRELATED`,
  - `EXECUTION_CLOSE_RECONCILED`,
  - `ORPHANED_TTL`.
- Use same-symbol matching only.
- Use the frozen slice only.
- Use the same 15-minute timing window for comparability with the published weak artifact.

### Exclusion rules

- Exclude `ORDER_FILLED` rows where the matched order is `order_kind = ENTRY` and `close_reason = NONE`.
- Exclude generic `ORDER_REJECTED` rows as overlap candidates.
- Exclude generic `ORDER_STATE_CHANGED` rows as overlap candidates.
- Exclude generic order-state noise and entry-related rows from overlap attribution.
- Do not infer named ownership unless the row itself or surrounding lifecycle proof supports it.

### Proof that entry fills were excluded

- Under current weak matching, nearby order-log matches across the 8 recommendations were dominated by `ORDER_FILLED|ENTRY|None = 40`.
- Under corrected close-only matching, those entry-fill candidates were removed entirely.
- In the corrected evidence set, the only surviving order-log close-bearing candidates were `5` `SL` fill rows, all attached to two BTC recommendations and both tied to prior lifecycles.

## Per-Recommendation Overlap Classification

### Final bucket counts

| Final bucket | Count |
| --- | ---: |
| `matched_real_incumbent_close` | 0 |
| `matched_bracket_terminal_path` | 0 |
| `matched_orphan_or_cleanup_path` | 0 |
| `no_overlap_proven` | 7 |
| `ambiguous_timing_window` | 1 |

### Full classification table

| # | Trace ID | Symbol | Recommendation ts_ms | Surviving corrected close-like candidates | Final bucket | Supporting evidence | Alternative buckets rejected | Confidence |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- |
| 1 | `pps:SOLUSDT:1775760306203:44044` | SOLUSDT | 1775760306203 | Prior-lifecycle `ORPHANED_TTL` at 1775760304568 (`rid = aurora_SOLUSDT_1775747102440`, delta `-1635 ms`) | `ambiguous_timing_window` | Recommendation occurs 1.635s after a real cleanup-like close path, while `fill_correlation.manage_state_after = FLAT` still points at the prior lifecycle. Current `position_open_ts` indicates a new open has already started, so same-lifecycle overlap is not proven, but the timing adjacency is too tight to call fully clean. | `matched_orphan_or_cleanup_path` rejected because the cleanup row belongs to the prior lifecycle, not the current recommended one. `no_overlap_proven` rejected because stale prior-lifecycle fill correlation plus 1.6s adjacency leaves a real ambiguity. | Medium |
| 2 | `pps:SOLUSDT:1775760604575:44442` | SOLUSDT | 1775760604575 | Same prior-lifecycle `ORPHANED_TTL` at 1775760304568 (delta `-300007 ms`) | `no_overlap_proven` | Only surviving candidate is a cleanup row from the earlier lifecycle. Current fill correlation points to current entry lifecycle `aurora_SOLUSDT_1775760304347`, and the current position is already open and managed. | `matched_orphan_or_cleanup_path` rejected because the candidate is clearly prior-lifecycle. `ambiguous_timing_window` rejected because the 5-minute gap plus current-lifecycle fill correlation is strong enough to reject overlap. | Medium |
| 3 | `pps:SOLUSDT:1775760912887:44899` | SOLUSDT | 1775760912887 | Same prior-lifecycle `ORPHANED_TTL` at 1775760304568 (delta `-608319 ms`) | `no_overlap_proven` | The only corrected candidate is still the earlier cleanup path. Current fill correlation and position state both point to the current lifecycle, not the old cleanup event. | `matched_orphan_or_cleanup_path` rejected because there is no same-lifecycle cleanup evidence. `ambiguous_timing_window` rejected because the time gap is wider and lifecycle separation is clearer. | Medium |
| 4 | `pps:ETHUSDT:1775763903359:48740` | ETHUSDT | 1775763903359 | None | `no_overlap_proven` | No corrected order-log or lifecycle close-like candidate survives inside the 15-minute window. | `matched_*` buckets rejected because no real close-like candidate exists in-window. `ambiguous_timing_window` rejected because there is no timing candidate, even though `fill_correlation.manage_state_after = FLAT` is stale. | Medium |
| 5 | `pps:BTCUSDT:1775765104093:50764` | BTCUSDT | 1775765104093 | None | `no_overlap_proven` | No corrected close-like candidate survives inside the 15-minute window. | `matched_*` buckets rejected because there is no candidate. `ambiguous_timing_window` rejected because there is no in-window close-like event despite stale prior-lifecycle fill correlation. | Medium |
| 6 | `pps:SOLUSDT:1775767501351:53852` | SOLUSDT | 1775767501351 | None | `no_overlap_proven` | No corrected close-like candidate survives inside the 15-minute window. Current fill correlation points to the current lifecycle `aurora_SOLUSDT_1775767201046`. | All matched buckets rejected because no candidate exists. `ambiguous_timing_window` rejected because neither timing nor stale-link evidence suggests overlap. | High |
| 7 | `pps:BTCUSDT:1775769303362:56248` | BTCUSDT | 1775769303362 | Prior-lifecycle `SL` fill rows, `EXECUTION_WS_TERMINAL_CORRELATED`, and `POSITION_DISAPPEARANCE_ATTRIBUTED` with `attribution = proven_exchange_bracket_close` around 1775768666xxx | `no_overlap_proven` | Real bracket-terminal evidence exists, but it belongs to prior lifecycle `aurora_BTCUSDT_1775764804783:SL`. Current `position_open_ts = 1775769023.864692` is later than the terminal-close proof, so the recommendation belongs to a new lifecycle. | `matched_bracket_terminal_path` rejected because the bracket terminal path is real but not same-lifecycle overlap. `ambiguous_timing_window` rejected because lifecycle timing is strong enough to reject overlap even though the event is inside the 15-minute window. | High |
| 8 | `pps:BTCUSDT:1775773808468:62150` | BTCUSDT | 1775773808468 | Prior-lifecycle `SL` fill rows, `EXECUTION_WS_TERMINAL_CORRELATED`, and `POSITION_DISAPPEARANCE_ATTRIBUTED` with `attribution = proven_exchange_bracket_close` around 1775773029xxx | `no_overlap_proven` | Real bracket-terminal evidence exists, but it belongs to prior lifecycle `aurora_BTCUSDT_1775769002761:SL`. Current `position_open_ts = 1775773808.4153225` is later than the close proof. | `matched_bracket_terminal_path` rejected because the bracket close belongs to the prior lifecycle. `ambiguous_timing_window` rejected because the lifecycle-open timestamp cleanly separates the recommendation from the earlier close path, despite stale `fill_correlation.manage_state_after = FLAT`. | Medium |

## Named Incumbent Attribution Review

### Attempted incumbent attribution categories

- `ExitManager`
- regime-flip close
- max-hold close
- bracket terminal exit
- orphan cleanup / `ORPHANED_TTL`
- other close-like path if truly evidenced

### Findings

- `ExitManager`: no emitted recommendation has evidence strong enough to attribute overlap to `ExitManager`.
- Regime-flip close: no emitted recommendation has evidence strong enough to attribute overlap to regime-flip close.
- Max-hold close: no emitted recommendation has evidence strong enough to attribute overlap to max-hold close.
- Bracket terminal exit:
  - nearby real bracket-terminal evidence exists for recommendation 7 and recommendation 8,
  - but both are prior-lifecycle events,
  - therefore there is no proven same-lifecycle bracket-terminal overlap to attribute.
- Orphan cleanup / `ORPHANED_TTL`:
  - nearby real cleanup-path evidence exists for recommendations 1, 2, and 3,
  - but those rows belong to the prior lifecycle,
  - therefore no proven same-lifecycle orphan-cleanup overlap is attributable.
- Other close-like path: none proven.

### Attribution conclusion

- Named incumbent attribution was attempted honestly.
- No emitted recommendation in the frozen slice can be honestly attributed to:
  - `ExitManager`,
  - regime-flip close,
  - max-hold close,
  - or another same-lifecycle incumbent close owner.
- The only named close-like paths evidenced near recommendations are:
  - prior-lifecycle orphan cleanup / `ORPHANED_TTL`,
  - prior-lifecycle bracket terminal exit proven by `EXECUTION_WS_TERMINAL_CORRELATED` plus `POSITION_DISAPPEARANCE_ATTRIBUTED`.

## Admission Impact Analysis

- Corrected overlap attribution materially improves the honesty of the overlap picture.
- It does not materially improve the overlap picture to admission-grade confidence.
- Before correction, the frozen slice appeared to have `8/8` matched overlaps.
- After correction:
  - `0/8` recommendations have proven same-lifecycle incumbent overlap,
  - `1/8` remains timing-ambiguous,
  - `7/8` have `no_overlap_proven`.
- This reduces the original false appearance of pervasive overlap, but it does not solve the Phase 6 blocker because action admission still requires stronger understanding of whether recommendations do or do not conflict with incumbent close behavior.
- Therefore this corrected audit moves the system toward:
  - `still_shadow_only`,
  - not promotion reconsideration.

## Blocking Reason Reassessment

- `overlap ambiguity` remains the correct single blocking cluster.
- The blocker is now more precise than before:
  - the old overlap picture overstated overlap because it counted entry fills,
  - the corrected audit now shows the real issue is not proven conflict but insufficient admission-grade attribution,
  - current evidence still cannot prove either a clean no-overlap story or a named same-lifecycle incumbent-overlap story across the frozen sample.
- The blocker does not change to recommendation quality instability:
  - recommendation noise and duplicate emission were already addressed in Package 5 and Package 5.2.
- The blocker does not change to suppression unreliability:
  - this task did not surface new suppression failure evidence.
- The blocker does not change to business-fit mismatch:
  - the current symbol-scoped close contract remains acceptable for the narrow future action model.

## Next Exact Step

- Remain in `shadow` and run one further targeted forensic audit that reconstructs recommendation-to-lifecycle identity linkage for the single remaining ambiguous recommendation `pps:SOLUSDT:1775760306203:44044`, so Phase 6 can determine whether that case is true overlap or only stale prior-lifecycle trace contamination.
