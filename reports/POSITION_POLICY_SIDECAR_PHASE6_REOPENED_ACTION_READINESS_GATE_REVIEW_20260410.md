# REPORT - POSITION POLICY SIDECAR PHASE 6 REOPENED ACTION-READINESS GATE REVIEW 2026-04-10

## Executive Verdict

- Reopened admission decision: `OUTCOME_A_PROMOTE_TO_PHASE2`.
- Old blocker reclassification: `BLOCKER_COLLAPSED`.
- Immediate guarded 24h testnet pilot posture: `NOT_ADMISSIBLE_NOW`.
- Guarded 24h testnet pilot posture after the next narrow package: `ADMISSIBLE_ONLY_AFTER_NARROW_PHASE2_IMPLEMENTATION_PACKAGE`.
- Package 5 remains closed. This review does not reopen calibration, does not enable action, and does not implement Package 7.
- Why promotion is now correct:
  - the old overlap blocker is no longer supported by the frozen slice,
  - recommendation behavior is controlled and explainable enough to justify the next guarded package,
  - suppression behavior is shadow-proven enough for package admission,
  - business-fit of the narrow symbol-scoped reduce-only close model remains acceptable,
  - the remaining gaps are Phase-2 implementation/activation gaps, not Phase-1 defects.
- Why immediate pilot is not admissible now:
  - the current `enable` path still records `POSITION_POLICY_SIDECAR_ACTION_SKIPPED`,
  - no real sidecar request-to-close runtime path exists now,
  - request-to-outcome linkage does not exist now,
  - action-grade forensics are therefore not yet present.

## Reopened Phase 6 Gate Contract

### What Phase 6 is allowed to decide

- The roadmap defines Phase 6 as `Action-Readiness Gate Review` and states the goal is to decide whether Phase 2 action mode is admissible at all.
- Phase 6 may decide whether the project is admitted to the conditional next package:
  - `Outcome A - Promote to Phase 2`
  - `Outcome B - Stay in shadow`
  - `Outcome C - Rework Phase 1`
- Phase 6 may also define whether a future guarded testnet pilot is conceptually admissible only after the required Phase-2 contracts are implemented.

### What Phase 6 is not allowed to assume

- Phase 6 may not assume Package 5 closure means action is already safe.
- Phase 6 may not assume `enable` already means action-capable behavior.
- Phase 6 may not invent lifecycle-targeted, order-id-targeted, or position-id-targeted close semantics.
- Phase 6 may not claim a request-to-close runtime path exists if the current code still stops at `ACTION_SKIPPED`.

### What evidence was previously blocking promotion

- The original Phase 6 review in [reports/POSITION_POLICY_SIDECAR_PHASE6_ACTION_READINESS_GATE_REVIEW_20260410.md](POSITION_POLICY_SIDECAR_PHASE6_ACTION_READINESS_GATE_REVIEW_20260410.md) held the system in `OUTCOME_B_STAY_IN_SHADOW`.
- Its single blocking reason cluster was `overlap ambiguity`.

### What evidence has now changed

- The corrected overlap audit in [reports/POSITION_POLICY_SIDECAR_PHASE6_CORRECTED_OVERLAP_ATTRIBUTION_SHADOW_AUDIT_20260410.md](POSITION_POLICY_SIDECAR_PHASE6_CORRECTED_OVERLAP_ATTRIBUTION_SHADOW_AUDIT_20260410.md) proved:
  - the published overlap sample was over-inclusive because it counted entry fills,
  - corrected close-only attribution found `0/8` proven same-lifecycle incumbent overlaps,
  - `7/8` recommendations were `no_overlap_proven`,
  - `1/8` remained timing-ambiguous.
- The single-case forensic audit in [reports/POSITION_POLICY_SIDECAR_PHASE6_SINGLE_CASE_FORENSIC_AUDIT_SOLUSDT_1775760306203_44044_20260410.md](POSITION_POLICY_SIDECAR_PHASE6_SINGLE_CASE_FORENSIC_AUDIT_SOLUSDT_1775760306203_44044_20260410.md) then resolved the last ambiguous case as:
  - `STALE_PRIOR_LIFECYCLE_TRACE_CONTAMINATION`,
  - strong enough to reject `TRUE_SAME_LIFECYCLE_OVERLAP`,
  - therefore the old overlap blocker collapses on the frozen `27.5019h` slice.

### What must still be true before a guarded 24h pilot could be admissible

- The roadmap Phase 7 section requires, before activation:
  - EP-internal request path only,
  - symbol-scoped soft-close only,
  - explicit policy source attribution,
  - request-to-outcome linkage,
  - suppression reason linkage,
  - outcome trace from request through reconcile.
- The current code does not yet satisfy those activation requirements:
  - [apps/reference/domains/execution_position/position_policy_sidecar.py](../apps/reference/domains/execution_position/position_policy_sidecar.py) lines `493`-`508` show `enable` still emits `POSITION_POLICY_SIDECAR_ACTION_SKIPPED`,
  - repo search found only a deferred `PositionPolicyCloseRequest` type and type assignment, not an active emitted request-to-close flow,
  - therefore a guarded 24h pilot cannot start now.

## FACTS

- The roadmap in [position_policy_sidecar_roadmap_v_1.md](../position_policy_sidecar_roadmap_v_1.md) fixes the package order:
  - `Shadow Validation`
  - `Policy Calibration`
  - `Action-Readiness Gate Review`
  - `Phase-2 Action Package (only if admitted)`
- The same roadmap freezes the architectural laws:
  - `ManageFlowFSM` remains local SSOT,
  - `CloseExecutor` remains close executor,
  - recommendation-first,
  - fail closed under ambiguity,
  - no fake exact-targeted close semantics in early rollout.
- The roadmap Phase 6 section at lines `574`-`606` defines the review questions and outcomes.
- The roadmap Phase 7 section at lines `610`-`640` defines:
  - allowed Phase-2 scope is EP-internal request path only,
  - symbol-scoped soft-close only,
  - still no close-by-id,
  - still no bracket mutation,
  - still no partial reduce unless separately admitted,
  - required new contracts before activation include policy-source attribution and request-to-outcome linkage.
- [reports/POSITION_POLICY_SIDECAR_PACKAGE5_CLOSURE_REVIEW_20260410.md](POSITION_POLICY_SIDECAR_PACKAGE5_CLOSURE_REVIEW_20260410.md) formally closed Package 5 and moved the project to Phase 6.
- Package 5 closure evidence records:
  - pre-calibration baseline `EVALUATED = 934`, `RECOMMENDED = 0`, max observed `soft_close_pressure = 0.3`, threshold `0.70`,
  - threshold calibration `0.70 -> 0.30`,
  - noisy post-change runtime `RECOMMENDED = 167`,
  - post-fix frozen slice `RECOMMENDED = 8`,
  - `recommendation_duplicate_same_state = 292`,
  - `false_suppression_candidate_count = 0`,
  - `explainability_completeness = 1.0`.
- [reports/POSITION_POLICY_SIDECAR_PHASE6_ACTION_READINESS_GATE_REVIEW_20260410.md](POSITION_POLICY_SIDECAR_PHASE6_ACTION_READINESS_GATE_REVIEW_20260410.md) recorded:
  - decision `OUTCOME_B_STAY_IN_SHADOW`,
  - blocker `overlap ambiguity`,
  - recommendation quality `BORDERLINE_STILL_SHADOW_ONLY`,
  - suppression reliability `SHADOW_READY_ONLY`,
  - race forensics `SUFFICIENT_FOR_SHADOW_ONLY_BUT_NOT_ACTION`,
  - false-positive risk `UNKNOWN_INSUFFICIENT_EVIDENCE`.
- [reports/POSITION_POLICY_SIDECAR_PHASE6_CORRECTED_OVERLAP_ATTRIBUTION_SHADOW_AUDIT_20260410.md](POSITION_POLICY_SIDECAR_PHASE6_CORRECTED_OVERLAP_ATTRIBUTION_SHADOW_AUDIT_20260410.md) proved:
  - the old overlap method overmatched entry fills,
  - corrected close-only overlap produced `0/8` proven same-lifecycle incumbent overlaps,
  - `7/8` `no_overlap_proven`,
  - `1/8` `ambiguous_timing_window`.
- [reports/POSITION_POLICY_SIDECAR_PHASE6_SINGLE_CASE_FORENSIC_AUDIT_SOLUSDT_1775760306203_44044_20260410.md](POSITION_POLICY_SIDECAR_PHASE6_SINGLE_CASE_FORENSIC_AUDIT_SOLUSDT_1775760306203_44044_20260410.md) proved the last ambiguous case is `STALE_PRIOR_LIFECYCLE_TRACE_CONTAMINATION` and states the overlap blocker collapses on the frozen slice.
- [artifacts/position_policy_sidecar/package52_post_restart_runtime_analysis_20260410.json](../artifacts/position_policy_sidecar/package52_post_restart_runtime_analysis_20260410.json) records the frozen slice:
  - one `MODE_ACTIVE` boundary,
  - duration `27.501865277777778h`,
  - `RECOMMENDED = 8`,
  - `recommended_soft_close_pressure_values = [0.3]`,
  - `all_recommendations_exactly_on_threshold_boundary = true`,
  - `false_suppression_candidate_count = 0`.
- [reports/POSITION_POLICY_SIDECAR_PACKAGE52_POST_RESTART_24H_RUNTIME_REVIEW_20260410.md](POSITION_POLICY_SIDECAR_PACKAGE52_POST_RESTART_24H_RUNTIME_REVIEW_20260410.md) records:
  - recommendation stream no longer has emitted same-state or same-fill duplicates,
  - emitted recommendation sample is sparse enough for manual inspection,
  - `ACTION_SKIPPED = 0` in the frozen slice because the sidecar stayed in `shadow`.
- Current live config in [config/aurora/domains.yaml](../config/aurora/domains.yaml) lines `585`-`631` keeps:
  - `mode: shadow`,
  - `recommend_soft_close_at: 0.30`,
  - `allowed_actions.soft_close_symbol_current_net_only: true`,
  - `partial_reduce: false`,
  - `bracket_mutation: false`,
  - `exact_targeting: false`.
- Current typed contract in [apps/reference/config_models.py](../apps/reference/config_models.py) lines `4034`-`4215` defines:
  - mode enum `disable | shadow | enable`,
  - allowed action fields,
  - Phase-1 validation that forbids `partial_reduce`, `bracket_mutation`, and `exact_targeting`.
- Current enable-mode runtime semantics in [apps/reference/domains/execution_position/position_policy_sidecar.py](../apps/reference/domains/execution_position/position_policy_sidecar.py) lines `493`-`508` are:
  - emit `POSITION_POLICY_SIDECAR_ACTION_SKIPPED`,
  - `why = "phase1_enable_mode_does_not_request_close"`,
  - no close request is issued there.
- Repo search over `apps/reference/` found:
  - `PositionPolicyCloseRequest` defined in [apps/reference/domains/execution_position/position_policy_sidecar.py](../apps/reference/domains/execution_position/position_policy_sidecar.py),
  - `position_policy_close_request_type = PositionPolicyCloseRequest` assigned in [apps/reference/domains/execution_position/fsm.py](../apps/reference/domains/execution_position/fsm.py) lines `546` and `776`,
  - no active sidecar emission/consumer path beyond that deferred type placeholder.
- Current close execution truth remains as frozen in the roadmap and implemented in [apps/reference/domains/execution_position/close_executor.py](../apps/reference/domains/execution_position/close_executor.py):
  - symbol-scoped,
  - reduce-only,
  - based on current live `positionAmt`,
  - not lifecycle-targeted,
  - not order-id-targeted,
  - not position-id-targeted.

## INFERENCES

- The old Phase 6 blocker is no longer supported by the updated frozen evidence base.
- Recommendation behavior remains narrow and exact-threshold, but it is now controlled, explainable, and non-noisy.
- The remaining gaps are not Package 5 calibration failures and not Phase-1 contract dishonesty.
- The biggest remaining weakness is not overlap; it is that the current runtime still cannot produce or validate action-bearing behavior because the action path is intentionally not implemented yet.
- That missing action path blocks immediate pilot activation now, but it does not logically block admission to the next guarded package, because the roadmap defines Phase 7 precisely to add that request path and attribution layer before activation.
- Business-fit remains good enough for a first guarded testnet experiment because the roadmap’s allowed Phase-2 scope matches the current narrow contract truth.

## ASSUMPTIONS

- The updated overlap evidence chain in the two newer reports is authoritative for the reopened Phase 6 decision and supersedes the old overlap blocker from the earlier report.
- No hidden unreviewed runtime drift changed the meaning of the live `enable` path after the cited code search.
- A guarded 24h pilot means testnet-only, narrow scope, explicit rollback, and action-bearing observability, not production activation.

## UNKNOWNS

- The real false-positive action rate remains unknown because no action-bearing runtime path exists yet.
- Recommendation geometry remains one-pattern and exact-threshold on the frozen slice; it is still unknown how that geometry behaves once an action path exists.
- Current traces are strong for shadow explanation, but still unproven for full action-grade request-to-outcome forensics because no such request chain exists yet.
- The roadmap does not define a numeric false-positive tolerance or action-abort threshold; it only requires acceptability and rollback.

## Old Blocker Reclassification

### Classification

`BLOCKER_COLLAPSED`

### Why

- The corrected overlap audit removed entry-fill overmatch and showed `0/8` proven same-lifecycle incumbent overlaps.
- The only remaining ambiguous case was then reconstructed as stale prior-lifecycle trace carryover, not true same-lifecycle overlap.
- Therefore `overlap ambiguity` is no longer a live blocker on the frozen `27.5h` slice.
- It is no longer correct to keep the reopened Phase 6 decision in `shadow` using the old blocker.

## Recommendation Quality and Geometry Review

### Evidence

- Package 5.2 reduced emitted recommendations from `167` to `8` while converting the threshold-crossing gap into explicit duplicate suppressions.
- `false_suppression_candidate_count = 0`.
- `explainability_completeness = 1.0`.
- The emitted stream is sparse and symbol-distributed:
  - `SOLUSDT = 4`
  - `BTCUSDT = 3`
  - `ETHUSDT = 1`
- The surviving geometry remains narrow:
  - `8/8` emitted recommendations share one identical score shape,
  - `300/300` threshold crossings share the same exact geometry,
  - all emitted recommendations sit exactly on `soft_close_pressure = 0.3`.

### Assessment

- The stream is controlled and explainable.
- The stream is not noisy in the Package 5 defect class anymore.
- The stream is still geometry-fragile for immediate pilot activation because it is one-pattern and exact-threshold.
- That geometry concern is now a guarded-pilot design and monitoring concern, not a reason to reopen Package 5 or to deny the next narrow package.

### Classification

`STILL_BORDERLINE`

### Admission meaning

- `STILL_BORDERLINE` here means:
  - not ready for immediate pilot now,
  - but no longer blocking admission to the narrow Phase-2 package.

## Suppression Reliability and Forensics Review

### Suppression evidence

- Frozen post-fix suppressor counts remain explicit and operator-readable:
  - `no_manage_flow_for_symbol = 61957`
  - `manage_flow_has_no_active_lifecycle = 28444`
  - `features_snapshot_missing_or_stale = 33080`
  - `regime_snapshot_missing_or_stale = 4453`
  - `portfolio_snapshot_missing_or_stale = 1733`
  - `startup_grace_active = 778`
  - `post_fill_grace_active = 367`
  - `recommendation_duplicate_same_state = 292`
- Duplicate suppression is monotonic in the frozen analysis artifact and no false suppression evidence was found.
- The suppression payloads remain contract-honest and operator-readable in `trade_lifecycle.jsonl`.

### Forensic evidence

- `trade_lifecycle.jsonl` remains the authoritative shadow forensic surface per roadmap Phase 3.
- The newer overlap and single-case audits could reconstruct:
  - recommendation rows,
  - nearby lifecycle context,
  - order-log context,
  - stale-trace carryover versus new-open evidence.
- But action-grade request-to-outcome linkage still does not exist because no action request is emitted now.

### Classifications

- Suppression reliability: `READY_FOR_PHASE2_PACKAGE_ADMISSION`
- Forensic sufficiency: `SUFFICIENT_FOR_PHASE2_PACKAGE_ADMISSION_NOT_IMMEDIATE_PILOT`

### Why

- Suppressions are strong enough to support a guarded package.
- Forensics are strong enough to understand shadow behavior and to justify the next implementation step.
- Forensics are not yet strong enough for immediate action-bearing pilot validation because the request chain the roadmap requires is still absent.

## Action-Path Readiness Review

### Current runtime truth

- A real sidecar request-to-close path does not exist now.
- Request-to-outcome linkage does not exist now.
- Current `enable` semantics are still no-op/skipped for close initiation:
  - [apps/reference/domains/execution_position/position_policy_sidecar.py](../apps/reference/domains/execution_position/position_policy_sidecar.py) lines `493`-`508`
  - `why = "phase1_enable_mode_does_not_request_close"`
- The repo contains only a deferred request object and type handle:
  - `PositionPolicyCloseRequest` exists as a placeholder type,
  - `fsm.py` stores the type,
  - no active emitted request path or downstream consumer path was found.

### Assessment

- Immediate action-bearing validation cannot start now.
- Immediate guarded 24h pilot cannot start now.
- Missing action-path contracts are a live blocker for pilot-now, but not for admission to the narrow Phase-2 package, because the roadmap Phase 7 section explicitly defines that package as the place where:
  - EP-internal request path is added,
  - source attribution is added,
  - request-to-outcome linkage is added,
  - action events become attributable.

### Action-path verdict

- Phase-2 package admission: `YES`
- Immediate pilot-now readiness: `NO`

## False-Positive Risk Reassessment

### Evidence

- The old overlap blocker materially collapsed.
- That removes a major source of false-positive uncertainty on the frozen shadow slice.
- But no action-bearing runtime exists now:
  - no real close request is emitted,
  - no request-to-outcome chain exists,
  - no action-grade false-positive sample exists.
- Recommendation geometry remains exact-threshold and one-pattern.

### Assessment

- The blocker collapse materially reduced false-positive uncertainty from overlap.
- False-positive risk is still not proven for action-bearing behavior because the required action path does not exist yet.

### Classification

`UNKNOWN_DUE_TO_MISSING_ACTION_PATH_PROOF`

### Admission meaning

- This classification blocks immediate pilot now.
- It does not block admission to the next guarded package whose purpose is to create the missing proof layer under bounded conditions.

## Business-Fit Review for Guarded 24h Testnet

### Current narrow contract

- symbol-scoped soft-close only
- reduce-only
- no partial reduce
- no bracket mutation
- no exact targeting

### Assessment

- This narrow posture is still business-fit for a first guarded testnet experiment.
- It is not misleading because it matches the roadmap’s allowed Phase-2 scope exactly:
  - EP-internal request path only,
  - symbol-scoped soft-close only,
  - no partial reduce unless separately admitted,
  - no bracket mutation,
  - no close-by-id.
- Therefore business-fit is not the blocker.

### Business-fit verdict

`ACCEPTABLE_FOR_FIRST_GUARDED_TESTNET_EXPERIMENT`

### Important limit

- This verdict applies only after the narrow Phase-2 package exists.
- It does not make a 24h pilot admissible now.

## Final Reopened Phase 6 Decision

### Decision

`OUTCOME_A_PROMOTE_TO_PHASE2`

### Why this is the correct reopened decision

- The old blocker `overlap ambiguity` has collapsed on the frozen evidence slice.
- Package 5 remains closed and does not need rework.
- Recommendation behavior is controlled, sparse, and explainable enough to justify the next guarded package, even though it remains geometry-borderline for immediate pilot.
- Suppression behavior is shadow-proven enough for guarded package admission.
- The current narrow close contract is honest and business-fit enough for a first guarded testnet experiment.
- The remaining gaps are exactly the Phase-2 package gaps the roadmap already anticipates:
  - EP-internal request path,
  - policy source attribution,
  - request-to-outcome linkage,
  - outcome trace through reconcile.

### Explicit admissibility statement

- Admit now:
  - the next narrow `Phase-2 Action Package`
- Do not admit now:
  - immediate action enablement
  - immediate 24h action-bearing pilot

## Admitted Posture or New Blocking Cluster

### Admitted posture

- Immediate 24h testnet pilot admissibility:
  - `ONLY_AFTER_NARROW_PHASE2_IMPLEMENTATION_PACKAGE`
- Default runtime posture until that package exists:
  - `shadow` remains default
- Allowed next-step scope:
  - testnet only
  - EP-internal request path only
  - soft-close `symbol_current_net_only` only
  - no partial reduce
  - no bracket mutation
  - no exact targeting
  - sidecar remains non-owner

### Mandatory safeguards

- Action remains behind explicit mode / feature-gated activation.
- The existing fail-closed suppressions remain mandatory:
  - freshness
  - inactive lifecycle / no-manage-flow
  - post-fill grace
  - duplicate recommendation suppression
  - incumbent / ambiguity suppression
- No fake lifecycle identity may be introduced.
- Shadow remains the safe rollback posture.

### Mandatory observability

- The next package must add the roadmap-required action contracts before any pilot:
  - explicit policy source attribution
  - request-to-outcome linkage
  - suppression reason linkage
  - outcome trace from request through reconcile
- `trade_lifecycle.jsonl` must remain the authoritative forensic surface.

### Rollback triggers that would invalidate pilot admission

- Any action request without attributable request-to-outcome linkage.
- Any unexplained duplicate close.
- Any same-lifecycle incumbent overlap that reappears in action-bearing testnet evidence.
- Any action emitted under stale, missing, or ambiguous state that should have suppressed.
- Any action behavior that exceeds the admitted narrow scope.

## Next Exact Step

- Implement the narrow Phase-2 action package on testnet only, adding the EP-internal request path plus request-to-outcome attribution and keeping `shadow` as the default posture until that package is complete and explicitly re-reviewed for pilot cutover.
