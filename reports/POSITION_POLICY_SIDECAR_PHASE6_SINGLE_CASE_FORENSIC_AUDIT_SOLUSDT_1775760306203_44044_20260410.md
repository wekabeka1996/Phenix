# REPORT - POSITION POLICY SIDECAR PHASE 6 SINGLE-CASE FORENSIC AUDIT 2026-04-10

## Executive Verdict

- Scope: one-case causal reconstruction for `pps:SOLUSDT:1775760306203:44044` only.
- Final classification: `STALE_PRIOR_LIFECYCLE_TRACE_CONTAMINATION`.
- Evidence strength: strong enough to reject `TRUE_SAME_LIFECYCLE_OVERLAP`; residual ambiguity is not zero, but it is not the dominant explanation after reconstructing the frozen chain.
- Phase 6 blocker impact: the single surviving overlap-ambiguity case collapses as an overlap explanation on the frozen slice.
- This task does not promote the system, does not reopen Package 5, and does not admit action by itself.

## Ambiguous-Case Timeline Reconstruction

### Files used

- [position_policy_sidecar_roadmap_v_1.md](../position_policy_sidecar_roadmap_v_1.md)
- [reports/POSITION_POLICY_SIDECAR_PHASE6_ACTION_READINESS_GATE_REVIEW_20260410.md](POSITION_POLICY_SIDECAR_PHASE6_ACTION_READINESS_GATE_REVIEW_20260410.md)
- [reports/POSITION_POLICY_SIDECAR_PHASE6_CORRECTED_OVERLAP_ATTRIBUTION_SHADOW_AUDIT_20260410.md](POSITION_POLICY_SIDECAR_PHASE6_CORRECTED_OVERLAP_ATTRIBUTION_SHADOW_AUDIT_20260410.md)
- [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl)
- [logs/order_log_v1.jsonl](../logs/order_log_v1.jsonl)

### Ordered event chain

| Order | ts_ms | Evidence | Meaning |
| --- | ---: | --- | --- |
| 1 | `1775760303015` | [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) line `44438` | Sidecar still sees `SOLUSDT` as `FLAT` with `suppression_reason = manage_flow_has_no_active_lifecycle` and stale prior fill correlation `aurora_SOLUSDT_1775747102440:SL`. |
| 2 | `1775760304204` | [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) line `44443` | Same stale prior-lifecycle correlation persists on another SOL sidecar suppression. |
| 3 | `1775760304325` | [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) line `44444` | Same stale prior-lifecycle correlation persists again immediately before the new entry sequence. |
| 4 | `1775760304568` | [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) line `44447` | Prior SOL lifecycle `aurora_SOLUSDT_1775747102440` is marked `status = ORPHANED_TTL` with `close_reason = TTL_EXPIRED_3600s`. |
| 5 | `1775760304579` | [logs/order_log_v1.jsonl](../logs/order_log_v1.jsonl) line `226` | New SOL intent starts on `rid = aurora_SOLUSDT_1775760304347`. |
| 6 | `1775760305656` | [logs/order_log_v1.jsonl](../logs/order_log_v1.jsonl) line `228` | New SOL entry is placed: `ORDER_PLACED`, `order_id = 1838184176`, `client_order_id = ENTRY-6ff0b5884e9d`. |
| 7 | `1775760305878` | [logs/order_log_v1.jsonl](../logs/order_log_v1.jsonl) line `229` | New lifecycle receives an `ENTRY` fill for `15.7` contracts at `83.74`. |
| 8 | `1775760305885.061` | [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) lines `44472`-`44474` | Recommendation row's `position_snapshot.position_open_ts` shows the current position episode is already open before the recommendation is emitted. |
| 9 | `1775760306203` | [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) lines `44472`-`44474` | Recommendation `pps:SOLUSDT:1775760306203:44044` is emitted with `manage_state = BRACKETS_PENDING`, `position_qty = 15.7`, but `fill_correlation` still points to prior lifecycle `aurora_SOLUSDT_1775747102440:SL` and `manage_state_after = FLAT`. |
| 10 | `1775760306534` | [logs/order_log_v1.jsonl](../logs/order_log_v1.jsonl) line `230` | Another `ENTRY` fill row appears for the same current lifecycle and same client order id. |
| 11 | `1775760308503` | [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) line `44501` | `EXECUTION_BRACKET_DEFERRED_PLACED` resolves ownership for the new lifecycle with `lifecycle_active = true` on `rid = aurora_SOLUSDT_1775760304347`. |
| 12 | `1775760308881` | [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) line `44505` | Sidecar now suppresses on `post_fill_grace_active` and the `fill_correlation` has flipped to current lifecycle `aurora_SOLUSDT_1775760304347` with `manage_state_after = BRACKETS_PENDING`. |
| 13 | `1775760334824` | [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) line `44537` | Lifecycle snapshot records the current SOL lifecycle as `FILLED`. |
| 14 | `1775760334831` | [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) line `44538` | `EXECUTION_FILL_INGRESS` lands for current lifecycle `aurora_SOLUSDT_1775760304347`. |
| 15 | `1775760334833` | [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) line `44539` | Sidecar on `TRADE_EXECUTED` keeps `post_fill_grace_active` and carries current-lifecycle fill correlation with `manage_state_after = BRACKETS_PENDING`. |

### Key timing deltas

- Prior close-like row `ORPHANED_TTL` to recommendation: `1775760306203 - 1775760304568 = 1635 ms`.
- New entry placement to recommendation: `1775760306203 - 1775760305656 = 547 ms`.
- New entry fill to recommendation: `1775760306203 - 1775760305878 = 325 ms`.
- Prior close-like row to current position open timestamp: `1775760305885.061 - 1775760304568 = 1317.061 ms`.

## FACTS

- [reports/POSITION_POLICY_SIDECAR_PHASE6_ACTION_READINESS_GATE_REVIEW_20260410.md](POSITION_POLICY_SIDECAR_PHASE6_ACTION_READINESS_GATE_REVIEW_20260410.md) holds the current Phase 6 decision at `OUTCOME_B_STAY_IN_SHADOW`.
- [reports/POSITION_POLICY_SIDECAR_PHASE6_CORRECTED_OVERLAP_ATTRIBUTION_SHADOW_AUDIT_20260410.md](POSITION_POLICY_SIDECAR_PHASE6_CORRECTED_OVERLAP_ATTRIBUTION_SHADOW_AUDIT_20260410.md) reduced the frozen 27.5h slice to `7/8 no_overlap_proven` and `1/8 ambiguous_timing_window`, with the sole survivor `pps:SOLUSDT:1775760306203:44044`.
- The recommendation row itself is in [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) lines `44472`-`44474`:
  - `trace_id = pps:SOLUSDT:1775760306203:44044`
  - `event_type = POSITION_POLICY_SIDECAR_RECOMMENDED`
  - `symbol = SOLUSDT`
  - `position_snapshot.manage_state = BRACKETS_PENDING`
  - `position_snapshot.position_qty = "15.7"`
  - `position_snapshot.portfolio_position_amt = "-15.7"`
  - `position_snapshot.position_open_ts = 1775760305.885061`
  - `fill_correlation.rid = aurora_SOLUSDT_1775747102440:SL`
  - `fill_correlation.manage_state_after = FLAT`
- The recommendation score snapshot is fixed at:
  - `position_health_score = 0.7`
  - `exit_pressure_score = 0.3`
  - `hold_confidence = 0.7`
  - `soft_close_pressure = 0.3`
  - `microstructure_adverse_pressure = 0.0`
  - `regime_exhaustion_hint = 1.0`
  - `conviction_decay = 0.0`
  - `unrealized_loss_pressure = 0.0`
- The nearest surviving close-like incumbent evidence for the same symbol is [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) line `44447`:
  - `rid = aurora_SOLUSDT_1775747102440`
  - `status = ORPHANED_TTL`
  - `close_reason = TTL_EXPIRED_3600s`
  - `close_ts_ms = 1775760304568`
- Immediately before the recommendation, the same stale prior-lifecycle fill correlation appears on SOL sidecar suppressions at [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) lines `44438`, `44443`, and `44444`, all with:
  - `manage_state = FLAT`
  - `position_open_ts = 0.0`
  - `suppression_reason = manage_flow_has_no_active_lifecycle`
  - stale `fill_correlation.rid = aurora_SOLUSDT_1775747102440:SL`
- New-open evidence exists before the recommendation in [logs/order_log_v1.jsonl](../logs/order_log_v1.jsonl):
  - line `228`: `ORDER_PLACED` at `1775760305656` for `order_id = 1838184176`, `client_order_id = ENTRY-6ff0b5884e9d`
  - line `229`: `ORDER_FILLED` at `1775760305878`, `order_kind = ENTRY`, `quantity = 15.7`
  - line `230`: another `ORDER_FILLED` at `1775760306534`, still `order_kind = ENTRY`
- Current-lifecycle ownership becomes explicit after the recommendation:
  - [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) line `44501`: `EXECUTION_BRACKET_DEFERRED_PLACED` at `1775760308503`, `rid = aurora_SOLUSDT_1775760304347`, `lifecycle_active = true`
  - [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) line `44505`: sidecar suppression now references `fill_correlation.rid = aurora_SOLUSDT_1775760304347`
  - [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) lines `44537`-`44539`: current-lifecycle `TRADE_LIFECYCLE_FILLED`, `EXECUTION_FILL_INGRESS`, and sidecar `post_fill_grace_active` rows all reference `aurora_SOLUSDT_1775760304347`
- Current close truth remains frozen by [position_policy_sidecar_roadmap_v_1.md](../position_policy_sidecar_roadmap_v_1.md):
  - symbol-scoped
  - reduce-only
  - based on live net symbol position
  - not lifecycle-targeted
  - not order-id-targeted
  - not position-id-targeted

## INFERENCES

- The recommendation belongs to a newly opened SOL position episode, not to the prior lifecycle that ended by `ORPHANED_TTL`.
- The `fill_correlation` on the recommendation row is lagging stale context from the prior SOL lifecycle.
- Time proximity alone created the earlier ambiguity:
  - the stale prior `ORPHANED_TTL` is only `1635 ms` earlier,
  - but the recommendation already carries a new active position snapshot and a new `position_open_ts`.
- The evidence set is strong enough to reject a same-lifecycle incumbent-close interpretation for this one case.

## ASSUMPTIONS

- `position_snapshot.position_open_ts` is a stronger indicator of the active position episode than the stale `fill_correlation` payload when those two surfaces disagree.
- The `ENTRY` order-log rows in [logs/order_log_v1.jsonl](../logs/order_log_v1.jsonl) belong to the current position episode represented by `position_snapshot.position_qty = 15.7`.
- `ORPHANED_TTL` on [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) line `44447` represents cleanup of the prior SOL lifecycle because its `rid` is the same prior lifecycle family referenced by the stale `fill_correlation`.

## UNKNOWNS

- The exact internal handoff point when sidecar should have switched from prior-lifecycle fill correlation to current-lifecycle fill correlation before `1775760306203`.
- Whether a tighter request-to-outcome trace surface would have removed this transient stale-correlation state entirely.
- Whether other frozen slices outside this 27.5h window contain similarly short stale-correlation transitions.

## Lifecycle Separation Analysis

### Strong evidence

- New lifecycle open is already visible before the recommendation:
  - [logs/order_log_v1.jsonl](../logs/order_log_v1.jsonl) line `229` shows `ENTRY` fill at `1775760305878`
  - [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) lines `44472`-`44474` show `position_open_ts = 1775760305.885061`
  - recommendation row shows `manage_state = BRACKETS_PENDING` and `position_qty = 15.7`
- Prior lifecycle close-like evidence is independently named and older:
  - [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) line `44447` is `aurora_SOLUSDT_1775747102440`
  - recommendation `fill_correlation.rid` still points to `aurora_SOLUSDT_1775747102440:SL`
  - the stale sidecar suppressions just before the recommendation remain `FLAT`, which matches a prior lifecycle being carried forward in trace context rather than the current active one

### Weak evidence

- The close-like row and the recommendation are only `1635 ms` apart.
- The recommendation row itself still carries prior-lifecycle `fill_correlation.manage_state_after = FLAT`.
- Because current close truth is not lifecycle-targeted, trace payload disagreement cannot be resolved from executor semantics alone.

### Separation conclusion

- The stronger evidence favors two distinct position episodes:
  - prior episode cleanup ending at `1775760304568`
  - new episode already open by `1775760305878` / `1775760305885.061`
- Lifecycle separation is therefore proven strongly enough for this one case to reject same-lifecycle overlap.

## Stale-Trace Hypothesis Review

### Hypothesis

- The recommendation inherited stale prior-lifecycle trace context, making it look close-adjacent even though it belongs to a new lifecycle.

### Supporting evidence

- Before the recommendation, sidecar repeatedly emits SOL suppressions with:
  - `manage_state = FLAT`
  - `position_open_ts = 0.0`
  - stale `fill_correlation.rid = aurora_SOLUSDT_1775747102440:SL`
  - [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) lines `44438`, `44443`, `44444`
- The recommendation row then flips the position truth without flipping the fill correlation:
  - active position appears with `BRACKETS_PENDING`, `15.7`, and `position_open_ts = 1775760305.885061`
  - stale fill correlation remains on the old `:SL` trace
- After the recommendation, the system converges onto the new lifecycle:
  - [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) line `44501` resolves new lifecycle bracket ownership
  - [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) line `44505` flips sidecar `fill_correlation.rid` to `aurora_SOLUSDT_1775760304347`
  - [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) lines `44537`-`44539` continue with current-lifecycle fill linkage and `manage_state_after = BRACKETS_PENDING`

### Assessment

- The stale-trace hypothesis fits the full sequence without contradiction.
- It explains why the row looked close-adjacent in the corrected overlap audit:
  - the recommendation was temporally near a real prior cleanup event,
  - and the row still carried stale prior fill context.

## True-Overlap Hypothesis Review

### Hypothesis

- The recommendation overlaps with a real same-lifecycle incumbent close-like path.

### Burden of proof check

- Same symbol only: satisfied, but insufficient.
- Close timing only: satisfied, but insufficient.
- Same position episode: not proven.
- Reconciliation against new-open evidence: fails for the true-overlap hypothesis.

### Why the hypothesis fails

- The only nearby close-like row is prior lifecycle `aurora_SOLUSDT_1775747102440` at [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) line `44447`.
- The recommendation's active position episode is already open later:
  - new `ENTRY` fill at [logs/order_log_v1.jsonl](../logs/order_log_v1.jsonl) line `229`
  - `position_open_ts = 1775760305.885061` on recommendation row
- No row in the frozen evidence ties a same-lifecycle incumbent close mechanism to the new position episode before `1775760306203`.
- The later lifecycle evidence is all current-open / post-fill / bracket-placement evidence, not close evidence.

### Assessment

- `TRUE_SAME_LIFECYCLE_OVERLAP` is not supported by the frozen evidence.

## Final Classification

- Classification: `STALE_PRIOR_LIFECYCLE_TRACE_CONTAMINATION`

### Justification

- Prior close-like context is real but belongs to the prior lifecycle `aurora_SOLUSDT_1775747102440`.
- New-open evidence is also real and predates the recommendation:
  - entry placed at `1775760305656`
  - entry filled at `1775760305878`
  - active `position_open_ts = 1775760305.885061`
- The recommendation row is the transition artifact:
  - current position truth already reflects the new lifecycle,
  - `fill_correlation` still lags on the old lifecycle with `manage_state_after = FLAT`.

## Phase 6 Blocker Impact

- For this one surviving case, the previous overlap blocker does not survive forensic reconstruction as a genuine overlap.
- Broadly stated:
  - the corrected overlap audit left one ambiguous case,
  - this single-case audit resolves that case toward stale trace contamination rather than same-lifecycle incumbent overlap.
- Therefore the overlap-ambiguity blocker collapses on the frozen 27.5h slice.
- This report still does not promote the system directly; it only removes this one blocker explanation from the frozen evidence record.

## Next Exact Step

- Reopen the formal Phase 6 admission decision using the corrected overlap audit plus this single-case forensic result, while keeping the sidecar in `shadow` until that governance decision is explicitly reissued.
