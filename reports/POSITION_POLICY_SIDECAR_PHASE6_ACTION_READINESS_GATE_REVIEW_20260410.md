# REPORT - POSITION POLICY SIDECAR PHASE 6 ACTION-READINESS GATE REVIEW 2026-04-10

## 1. Executive Verdict

- Admission decision: `OUTCOME_B_STAY_IN_SHADOW`.
- Single blocking reason cluster: `overlap ambiguity`.
- Recommendation quality classification: `BORDERLINE_STILL_SHADOW_ONLY`.
- Suppression reliability classification: `SHADOW_READY_ONLY`.
- Race forensics / trace sufficiency classification: `SUFFICIENT_FOR_SHADOW_ONLY_BUT_NOT_ACTION`.
- Business-fit classification: current symbol-scoped close truth is acceptable for the narrow future action model and is not the blocker.
- False-positive risk classification: `UNKNOWN_INSUFFICIENT_EVIDENCE`.
- Package 5 remains formally closed. This review does not reopen calibration, does not change thresholds, and does not admit action.

## 2. Phase 6 Gate Contract

### Governing boundary

- SSOT for this review is [position_policy_sidecar_roadmap_v_1.md](../position_policy_sidecar_roadmap_v_1.md).
- The roadmap defines Phase 6 as `Action-Readiness Gate Review` and states the goal is to decide whether Phase 2 action mode is admissible at all.
- The roadmap lists the Phase 6 review questions explicitly:
  - recommendation quality stability,
  - overlap with `ExitManager`,
  - suppression reliability,
  - race-forensics trace sufficiency,
  - business-fit of symbol-scoped close,
  - acceptable false-positive risk.
- The roadmap defines only three admissible outcomes:
  - `Outcome A - Promote to Phase 2`,
  - `Outcome B - Stay in shadow`,
  - `Outcome C - Rework Phase 1`.

### What Phase 6 is allowed to decide

- Phase 6 may decide admission only.
- Phase 6 may record whether the current Phase-1 sidecar evidence is sufficient to admit the project toward the conditional Phase-2 action package.
- Phase 6 may hold the sidecar in shadow if action readiness is not proven.
- Phase 6 may require Phase-1 rework only if the evidence shows a Phase-1 contract or quality failure, not merely incomplete action proof.

### What Phase 6 is not allowed to assume

- Phase 6 may not assume that Package 5 closure implies action safety.
- Phase 6 may not assume exact targeting, lifecycle targeting, order-id targeting, or position-id targeting.
- Phase 6 may not assume new executor ownership or sidecar lifecycle ownership.
- Phase 6 may not assume a sidecar action request path already exists merely because the typed mode surface includes `enable`.
- Phase 6 may not invent Package 7 semantics that are not already frozen in the roadmap.

### Current live contract posture

- [config/aurora/domains.yaml](../config/aurora/domains.yaml) keeps:
  - `domains.execution_position.position_policy_sidecar.mode = shadow`,
  - `allowed_actions.soft_close_symbol_current_net_only = true`,
  - `allowed_actions.partial_reduce = false`,
  - `allowed_actions.bracket_mutation = false`,
  - `allowed_actions.exact_targeting = false`.
- [apps/reference/config_models.py](../apps/reference/config_models.py) enforces that Phase 1 forbids `partial_reduce`, `bracket_mutation`, and `exact_targeting`.
- [apps/reference/domains/execution_position/position_policy_sidecar.py](../apps/reference/domains/execution_position/position_policy_sidecar.py) shows that `enable` still emits `POSITION_POLICY_SIDECAR_ACTION_SKIPPED` with `why = "phase1_enable_mode_does_not_request_close"`.
- No public API, interface, or type changes are introduced by this review. This task records an admission decision only.

### Current execution truth

- The roadmap section `3.1 What the current close contract really is` states current close execution is:
  - symbol-scoped,
  - reduce-only,
  - based on current live net symbol position,
  - not lifecycle-targeted,
  - not order-id-targeted,
  - not position-id-targeted.
- [apps/reference/domains/execution_position/close_executor.py](../apps/reference/domains/execution_position/close_executor.py) confirms `CloseExecutor.execute_close()` resolves by `symbol`, reads current `positionAmt` from live open positions, and routes reduce-only close placement through `place_market_reduce_only`.

### What Package 5 already proved and should not be retried here

- [reports/POSITION_POLICY_SIDECAR_PACKAGE5_CLOSURE_REVIEW_20260410.md](POSITION_POLICY_SIDECAR_PACKAGE5_CLOSURE_REVIEW_20260410.md) already closed Package 5.
- Package 5 proved:
  - the zero-yield threshold blocker was real,
  - threshold calibration `0.70 -> 0.30` produced recommendation emergence,
  - the first post-change runtime exposed noisy repeated same-state emission,
  - Package 5.2 dedup/cadence hardening converted that defect into explicit suppressions,
  - the frozen post-restart slice was sufficient to confirm the fix.
- Therefore this report does not retry threshold calibration, emitted duplicate suppression, or Package 5 closure criteria.

### Outcome thresholds for this review

- `Promote` requires strong evidence across all Phase 6 questions, including action-grade overlap attribution and action-grade forensics.
- `Stay in shadow` is the correct outcome when Phase 1 remains contract-honest and operationally useful, but action admission is not yet proven.
- `Rework Phase 1` requires evidence of a Phase-1 defect class such as uncontrolled recommendation noise, suppression unreliability, or dishonest contract semantics. Current evidence does not show that.

## 3. FACTS

- [position_policy_sidecar_roadmap_v_1.md](../position_policy_sidecar_roadmap_v_1.md) defines the fixed package order `Shadow Validation -> Policy Calibration -> Action-Readiness Gate Review -> Phase-2 Action Package (only if admitted)`.
- The roadmap states Phase 7 is conditional and requires new contracts before activation:
  - explicit policy source attribution,
  - request-to-outcome linkage,
  - suppression reason linkage,
  - outcome trace from request through reconcile.
- [reports/POSITION_POLICY_SIDECAR_PACKAGE5_CLOSURE_REVIEW_20260410.md](POSITION_POLICY_SIDECAR_PACKAGE5_CLOSURE_REVIEW_20260410.md) records:
  - pre-calibration baseline `EVALUATED = 934`,
  - `RECOMMENDED = 0`,
  - max observed `soft_close_pressure = 0.3`,
  - `recommend_soft_close_at = 0.70`,
  - threshold calibration `0.70 -> 0.30`,
  - noisy post-change runtime `RECOMMENDED = 167`,
  - Package 5.2 post-restart confirmation `RECOMMENDED = 8`,
  - `recommendation_duplicate_same_state = 292`,
  - `false_suppression_candidate_count = 0`,
  - `explainability_completeness = 1.0`.
- [artifacts/position_policy_sidecar/package5_post_change_runtime_review_20260408.json](../artifacts/position_policy_sidecar/package5_post_change_runtime_review_20260408.json) records the noisy pre-dedup slice:
  - runtime span `23.9145h`,
  - `EVALUATED = 885`,
  - `RECOMMENDED = 167`,
  - `threshold_crossing_evaluated_count = 167`,
  - `max_evaluated_soft_close_pressure = 0.3`,
  - `action_skipped_count = 0`,
  - `explainability_completeness = 1.0`.
- [artifacts/position_policy_sidecar/package5_post_change_runtime_overlap_corrected_20260408.json](../artifacts/position_policy_sidecar/package5_post_change_runtime_overlap_corrected_20260408.json) records:
  - `overlap_count = 19`,
  - all overlap cases were `BTCUSDT`.
- [reports/POSITION_POLICY_SIDECAR_PACKAGE52_POST_RESTART_24H_RUNTIME_REVIEW_20260410.md](POSITION_POLICY_SIDECAR_PACKAGE52_POST_RESTART_24H_RUNTIME_REVIEW_20260410.md) and [artifacts/position_policy_sidecar/package52_post_restart_runtime_review_20260410.json](../artifacts/position_policy_sidecar/package52_post_restart_runtime_review_20260410.json) record the frozen post-restart slice:
  - one `MODE_ACTIVE` boundary,
  - duration `27.5019h`,
  - `artifact_sufficient_for_24h_review = true`,
  - `EVALUATED = 1140`,
  - `RECOMMENDED = 8`,
  - `threshold_crossing_evaluated_count = 300`,
  - `matched_recommendations = 8`,
  - `action_skipped_count = 0`,
  - `explainability_completeness = 1.0`.
- [artifacts/position_policy_sidecar/package52_post_restart_runtime_analysis_20260410.json](../artifacts/position_policy_sidecar/package52_post_restart_runtime_analysis_20260410.json) records:
  - `recommended_soft_close_pressure_values = [0.3]`,
  - `all_recommendations_exactly_on_threshold_boundary = true`,
  - `false_suppression_candidate_count = 0`,
  - `monotonic_duplicate_suppression_windows = true`.
- [tests/domains/execution_position/test_position_policy_sidecar_recommendation_dedup.py](../tests/domains/execution_position/test_position_policy_sidecar_recommendation_dedup.py) and [apps/reference/domains/execution_position/position_policy_sidecar.py](../apps/reference/domains/execution_position/position_policy_sidecar.py) provide Package 5.2 implementation evidence:
  - first recommendation emitted once,
  - repeated same-state recommendation is suppressed,
  - meaningful state change or new lifecycle boundary re-emits,
  - dedup payload carries explicit `dedup_detail`.
- Repo review of the frozen slice in [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) shows:
  - `8/8` emitted `POSITION_POLICY_SIDECAR_RECOMMENDED` rows share one identical score snapshot,
  - the shared score geometry is `soft_close_pressure = 0.3`, `regime_exhaustion_hint = 1.0`, `microstructure_adverse_pressure = 0.0`, `conviction_decay = 0.0`, `unrealized_loss_pressure = 0.0`,
  - the `300` threshold-crossing evaluated rows in the frozen slice share the same score geometry.
- Repo review of the frozen slice in [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) shows `4/8` emitted recommendations carry `fill_correlation.manage_state_after = FLAT`.
- Repo review of the frozen slice in [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) shows all `131104` suppression rows have no `incumbent_owner` populated.
- [tools/forensics/position_policy_sidecar_validation.py](../tools/forensics/position_policy_sidecar_validation.py) defines `_close_rows()` by loading all `ORDER_FILLED`, `ORDER_REJECTED`, and `ORDER_STATE_CHANGED` rows from `logs/order_log_v1.jsonl` as generic close candidates.
- Repo review of the published `8` post-fix matched overlap samples shows `8/8` resolve to `ORDER_FILLED` rows in [logs/order_log_v1.jsonl](../logs/order_log_v1.jsonl) whose matched order rows have:
  - `order_kind = ENTRY`,
  - `close_reason = NONE`.
- Repo search in the current workspace found only a deferred `PositionPolicyCloseRequest` type and `position_policy_close_request_type` assignment; no sidecar runtime request-to-close path was found. The current implemented `enable` path still records `POSITION_POLICY_SIDECAR_ACTION_SKIPPED`.

## 4. INFERENCES

- Package 5 closure proves calibration success inside Package 5 scope, not action safety.
- Recommendation emission is now controlled and explainable enough for shadow governance review, but the surviving recommendation geometry is still single-pattern and threshold-boundary only.
- The currently published overlap artifacts are not strong evidence of sidecar interaction with incumbent close mechanisms because the validator overmatches entry fills as close candidates.
- Because current overlap attribution is weak, unresolved overlap ambiguity remains a legitimate admission blocker.
- Suppression behavior is operationally readable and contract-honest in shadow, but incumbent-close suppression is not yet runtime-proven for action admission.
- `trade_lifecycle.jsonl` is sufficient to audit shadow behavior, but stale prior-lifecycle fill correlation on half of the emitted recommendation sample weakens action-grade race reconstruction.
- The current symbol-scoped reduce-only close contract is still compatible with the narrow future action model frozen in the roadmap, so business-fit mismatch is not the correct blocker here.
- Current evidence supports `Stay in shadow`, not `Rework Phase 1`, because no reviewed evidence shows a Phase-1 contract failure severe enough to require rollback of completed work.

## 5. ASSUMPTIONS

- The frozen 27.5019h post-restart slice used in Package 5.2 remains the authoritative Phase 6 runtime sample unless contradicted by stronger repo evidence.
- Action admission in this review refers only to the roadmap's narrow future Phase-2 posture: EP-internal request path and symbol-scoped soft-close through existing EP ownership.
- No hidden config or runtime drift outside the cited artifacts changed the meaning of the reviewed Phase 6 evidence during this task.

## 6. UNKNOWNS

- Whether recommendation behavior remains stable over multi-day captures beyond the frozen 27.5019h slice.
- Whether a corrected overlap method that excludes entry fills will show true overlap with `ExitManager`, regime-flip close, max-hold close, bracket terminal exits, duplicate-close suppression windows, or no overlap at all.
- Whether stale prior-lifecycle `fill_correlation` is only a forensic-surface issue or also a deeper state-linkage issue for future action interpretation.
- What real action-mode false-positive rate would be, because the sidecar has not been admitted to action and therefore has no action-bearing runtime evidence.
- What numeric false-positive tolerance would be acceptable to operators, because the roadmap requires acceptability but does not define a numeric risk budget.

## 7. Recommendation Quality Stability Review

### Evidence

- Pre-calibration baseline produced no recommendations because `recommend_soft_close_at = 0.70` exceeded the observed maximum `soft_close_pressure = 0.3`.
- Threshold calibration `0.70 -> 0.30` produced recommendation emergence but also noisy emitted duplication:
  - `RECOMMENDED = 167` in `23.9145h`,
  - same-state and same-fill emitted duplication ratios were `1.0` on the recommending symbols.
- Package 5.2 hardening then reduced the emitted stream to:
  - `RECOMMENDED = 8` in `27.5019h`,
  - duplicate suppressions `= 292`,
  - zero consecutive same-state emitted duplicate pairs,
  - zero consecutive same-fill emitted duplicate pairs,
  - `false_suppression_candidate_count = 0`.
- Symbol distribution in the frozen post-fix slice is narrow but no longer two-symbol burst noise:
  - `SOLUSDT = 4`,
  - `BTCUSDT = 3`,
  - `ETHUSDT = 1`.
- Explainability remains structurally complete in the published artifact with `explainability_completeness = 1.0`.
- Repo review of the frozen slice shows the emitted stream is still one invariant recommendation shape:
  - `8/8` recommendations share one identical score snapshot,
  - `300/300` threshold-crossing evaluated rows share the same score geometry,
  - every recommendation sits exactly on the threshold boundary `soft_close_pressure = 0.3`.

### Assessment

- The stream is sparse and manually inspectable after Package 5.2.
- The stream is no longer noisy in the defect class that blocked Package 5 closure.
- The stream is still fragile for action admission because it is entirely threshold-boundary and entirely one-pattern.
- The current behavior looks conservative rather than chaotic, but it is not yet diverse or stress-proven enough to support action admission.

### Classification

`BORDERLINE_STILL_SHADOW_ONLY`

## 8. Overlap Understanding Review

### Evidence

- The roadmap requires Phase 6 to determine whether overlap with `ExitManager` is sufficiently understood.
- The pre-dedup corrected overlap artifact records `19` matched overlaps, all on `BTCUSDT`.
- The post-fix artifact records `matched_recommendations = 8`.
- [tools/forensics/position_policy_sidecar_validation.py](../tools/forensics/position_policy_sidecar_validation.py) currently treats any `ORDER_FILLED`, `ORDER_REJECTED`, or `ORDER_STATE_CHANGED` row in `logs/order_log_v1.jsonl` as a close candidate.
- Repo review of the frozen `8` matched overlap samples shows `8/8` resolve to `ORDER_FILLED` rows whose matched order rows are:
  - `order_kind = ENTRY`,
  - `close_reason = NONE`.
- Therefore the published post-fix overlap sample does not prove interaction with:
  - `ExitManager`,
  - regime-flip close,
  - max-hold close,
  - bracket terminal exits,
  - duplicate-close suppression windows.
- A corrected close-only review of the same frozen sample does not rescue admission:
  - `3/8` recommendations had no true close-like match within 15 minutes,
  - `3/8` aligned only to prior-lifecycle `ORPHANED_TTL` rows,
  - `2/8` aligned to prior bracket-close disappearance rows.

### Assessment

- Current overlap samples are not sufficient for promotion.
- Symbol-level overlap behavior is not action-admission interpretable because the published overlap method is over-inclusive.
- Overlap attribution is weak, not strong.
- Unresolved overlap ambiguity is not acceptable for promotion because action admission depends on knowing whether the sidecar would duplicate or race incumbent close behavior.

### Classification

- Overlap attribution strength: weak.
- Promotion suitability: not acceptable.

## 9. Suppression Reliability Review

### Evidence

- The frozen post-fix slice records explicit suppressions by reason:
  - `no_manage_flow_for_symbol = 61957`,
  - `manage_flow_has_no_active_lifecycle = 28444`,
  - `features_snapshot_missing_or_stale = 33080`,
  - `regime_snapshot_missing_or_stale = 4453`,
  - `portfolio_snapshot_missing_or_stale = 1733`,
  - `startup_grace_active = 778`,
  - `post_fill_grace_active = 367`,
  - `recommendation_duplicate_same_state = 292`.
- Package 5.2 implementation evidence proves duplicate recommendation suppression is explicit and monotonic, with runtime `dedup_detail.suppressed_count` and `false_suppression_candidate_count = 0`.
- Suppression payloads in [logs/trade_lifecycle.jsonl](../logs/trade_lifecycle.jsonl) are operator-readable:
  - `suppression_reason` is explicit,
  - `reason_codes` are explicit,
  - freshness snapshots are explicit.
- The roadmap requires suppression under incumbent close-in-progress or terminal lifecycle conditions.
- Repo review of the frozen slice shows all `131104` suppression rows have `incumbent_owner = NONE`.

### Assessment

- Freshness, startup grace, post-fill grace, no-manage-flow, and dedup suppression all appear reliable enough for shadow operation.
- The dedup defect class from Package 5.1 is fixed in runtime.
- However incumbent-close and terminal-owner suppression is contract-defined rather than runtime-proven in this admission sample because no frozen suppression row carries an incumbent owner.

### Classification

`SHADOW_READY_ONLY`

## 10. Race Forensics / Trace Sufficiency Review

### Evidence

- The roadmap Phase 3 required `trade_lifecycle.jsonl` to become the authoritative forensic surface for this feature.
- [apps/reference/domains/execution_position/position_policy_sidecar.py](../apps/reference/domains/execution_position/position_policy_sidecar.py) writes policy rows into `trade_lifecycle.jsonl` with:
  - `trace_id`,
  - `reason_codes`,
  - `position_snapshot`,
  - `feature_ref`,
  - `regime_ref`,
  - `score_snapshot`,
  - `freshness_snapshot`,
  - `suppression_reason`,
  - `dedup_detail` when applicable.
- The frozen post-fix artifact records `explainability_completeness = 1.0`.
- Trace continuity is present across `POSITION_POLICY_SIDECAR_SCORES`, `POSITION_POLICY_SIDECAR_EVALUATED`, `POSITION_POLICY_SIDECAR_RECOMMENDED`, and `POSITION_POLICY_SIDECAR_SUPPRESSED` rows for the same evaluation cycle.
- Repo review of the frozen slice shows `4/8` emitted recommendations carry `fill_correlation.manage_state_after = FLAT`, which points to prior-lifecycle fill context rather than current-lifecycle action context.
- The current validator cannot reliably reconstruct recommendation -> overlap -> incumbent action timing because its close candidate set includes entry fills.
- The roadmap Phase 7 explicitly says action activation later requires `request-to-outcome linkage` and `outcome trace from request through reconcile`.
- Repo search found no implemented sidecar request-to-close runtime path in the current codebase; current `enable` still emits `POSITION_POLICY_SIDECAR_ACTION_SKIPPED`.

### Assessment

- The current trace surface is sufficient to explain shadow evaluation, suppression, and dedup behavior.
- The current trace surface is not sufficient for action-bearing forensics because:
  - stale prior-lifecycle fill correlation is still present in the emitted sample,
  - request-to-outcome linkage does not exist yet,
  - current overlap timing attribution is not action-grade.

### Classification

`SUFFICIENT_FOR_SHADOW_ONLY_BUT_NOT_ACTION`

## 11. Business-Fit Review for Current Close Contract

### Evidence

- The roadmap explicitly frames the long-term goal as influencing symbol-scoped close behavior through existing execution contracts.
- The roadmap Phase 7 allowed scope is:
  - EP-internal request path only,
  - symbol-scoped soft-close action only,
  - still no close-by-id,
  - still no bracket mutation,
  - still no partial reduce unless separately admitted.
- Current config and model contracts keep:
  - `soft_close_symbol_current_net_only = true`,
  - `partial_reduce = false`,
  - `bracket_mutation = false`,
  - `exact_targeting = false`.
- Current close execution truth is symbol-scoped and based on current live `positionAmt`.

### Assessment

- For the narrow future action model frozen in the roadmap, symbol-net reduce-only close is contract-honest.
- The absence of exact targeting is tolerable for that narrow future posture because the roadmap explicitly defers exact targeting and forbids fake close-by-id semantics.
- This does not prove action admission; it only means business-fit mismatch is not the primary blocker in the current evidence set.

### Conclusion

- Current business-fit is acceptable for the narrow future action model.
- Business-fit mismatch is not the blocking reason cluster for this review.

## 12. False-Positive Risk Review

### Evidence

- Positive evidence:
  - noisy duplicate emission is fixed,
  - emitted recommendations are sparse,
  - `false_suppression_candidate_count = 0`,
  - explainability is complete in the published artifact.
- Limiting evidence:
  - all emitted recommendations are exact-threshold single-pattern events,
  - overlap attribution is weak because the published overlap sample overmatches entry fills,
  - current forensics are shadow-grade rather than action-grade,
  - no action-bearing runtime evidence exists,
  - incumbent interaction remains unresolved.

### Assessment

- Current evidence does not justify `ACCEPTABLE_FOR_GUARDED_PHASE2`.
- Current evidence also does not justify `TOO_HIGH_REWORK_PHASE1`, because the reviewed defects are not Phase-1 contract failures and Package 5 remains properly closed.
- The correct classification is that action false-positive risk is still unproven due to insufficient admission-grade overlap and forensic evidence.

### Classification

`UNKNOWN_INSUFFICIENT_EVIDENCE`

## 13. Final Admission Decision

### Decision

`OUTCOME_B_STAY_IN_SHADOW`

### Rationale

- Package 5 is closed and does not need to be reopened.
- Recommendation behavior is now controlled enough for shadow governance review.
- Suppression behavior is shadow-reliable and contract-honest.
- Business-fit of the narrow symbol-scoped future action model is acceptable.
- Promotion still fails because overlap understanding is not admission-grade, and the remaining false-positive risk cannot be proven acceptable from the current shadow evidence.

## 14. Admitted Posture or Blocking Reason Cluster

### Blocking Reason Cluster

`overlap ambiguity`

### Why this is the blocking cluster

- The current published overlap evidence is methodologically insufficient for promotion because the validator treats entry fills as close candidates.
- In the frozen post-fix slice, the reported matched overlap sample is `8/8` entry fills with `order_kind = ENTRY` and `close_reason = NONE`.
- Because overlap attribution is weak, Phase 6 cannot prove precedence understanding against incumbent close mechanisms.
- This blocker is concrete and evidence-based. It is narrower than "general uncertainty" and more accurate than "recommendation instability" or "business-fit mismatch".

## 15. Next Exact Step

- Perform one corrected overlap-attribution shadow audit on the frozen 27.5h post-restart slice that excludes entry fills and links each recommendation to either:
  - a real incumbent close mechanism,
  - or an explicit `no_overlap_proven` verdict,
  while the sidecar remains in `shadow`.
