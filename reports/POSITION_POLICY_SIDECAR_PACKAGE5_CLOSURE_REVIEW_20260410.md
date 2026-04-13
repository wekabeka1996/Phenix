# REPORT — POSITION POLICY SIDECAR PACKAGE 5 CLOSURE REVIEW 2026-04-10

## Scope

- Decide whether Package 5 can be formally closed from roadmap plus the frozen Package 5 evidence chain.
- No code changes, no config changes, no new calibration, no action enablement.
- Required output is one governance decision only:
  - CLOSE_PACKAGE5
  - PACKAGE5_NEEDS_ONE_LAST_NARROW_ITERATION
  - HOLD_PACKAGE5_PENDING_MORE_RUNTIME_EVIDENCE

## SSOT Boundary Note

### FACT

- Copilot_Master_Roadmap.md in the current workspace does not enumerate Position Policy Sidecar phases or Package 5 / Package 6 boundaries. The file currently contains only vFoundation-oriented headings and therefore is too coarse to resolve this subsystem closure question directly.
- position_policy_sidecar_roadmap_v_1.md does define the sidecar package boundary explicitly:
  - Phase 5 is Policy Calibration Package.
  - Phase 6 is Action-Readiness Gate Review.
- The sidecar roadmap states for Phase 5:
  - Goal: tune thresholds and composite logic after shadow evidence exists.
  - Implementation scope includes thresholds, score weighting and caps, suppression rules, freshness windows, startup grace, and profitability guard.
  - Must NOT do: action enablement yet.
  - DoD requires evidence-driven calibration, before/after validation comparison, premature close rate reduced or controlled, explainability remaining complete, and a REPORT stating exact changes and why.
- The sidecar roadmap states for Phase 6:
  - Goal: decide whether Phase 2 action mode is admissible at all.
  - Review questions include recommendation quality stability, overlap understanding, suppression reliability, race-forensics trace sufficiency, business-fit of symbol-scoped close, and false-positive risk.

### INFERENCE

- For this subsystem, the operative Package 5 vs Package 6 boundary is available only in position_policy_sidecar_roadmap_v_1.md. This is a documentation granularity gap in Copilot_Master_Roadmap.md, not evidence that Package 5 lacks a boundary.

## Frozen Evidence Chain

### FACT

- Pre-calibration baseline from Package 4 / early Package 5 evidence showed:
  - EVALUATED = 934,
  - RECOMMENDED = 0,
  - max observed soft_close_pressure = 0.3,
  - recommend_soft_close_at was 0.70.
- First Package 5 move was narrow and evidence-driven:
  - config/aurora/domains.yaml threshold recommend_soft_close_at changed 0.70 -> 0.30.
- Post-change Package 5 shadow review from artifacts/position_policy_sidecar/package5_post_change_runtime_review_20260408.json and artifacts/position_policy_sidecar/package5_post_change_runtime_cadence_20260408.json showed:
  - runtime span = 23.9145h,
  - EVALUATED = 885,
  - RECOMMENDED = 167,
  - BTCUSDT recommendations = 93,
  - ETHUSDT recommendations = 74,
  - explainability_completeness = 1.0,
  - BTCUSDT consecutive same-state duplication ratio = 1.0,
  - BTCUSDT consecutive same-fill duplication ratio = 1.0,
  - ETHUSDT consecutive same-state duplication ratio = 1.0,
  - ETHUSDT consecutive same-fill duplication ratio = 1.0.
- Corrected overlap evidence from artifacts/position_policy_sidecar/package5_post_change_runtime_overlap_corrected_20260408.json showed:
  - overlap_count = 19,
  - all overlap cases were BTCUSDT,
  - overlap remained materially possible but still narrow.
- Package 5.2 post-restart runtime review from reports/POSITION_POLICY_SIDECAR_PACKAGE52_POST_RESTART_24H_RUNTIME_REVIEW_20260410.md, artifacts/position_policy_sidecar/package52_post_restart_runtime_review_20260410.json, and artifacts/position_policy_sidecar/package52_post_restart_runtime_analysis_20260410.json showed:
  - one frozen post-restart slice only,
  - slice duration = 27.5019h,
  - artifact_sufficient_for_24h_review = true,
  - EVALUATED = 1140,
  - RECOMMENDED = 8,
  - recommendation_duplicate_same_state suppressions = 292,
  - threshold_crossing_evaluated_count = 300,
  - 300 threshold crossings - 8 emitted recommendations = 292 duplicate suppressions,
  - emitted stream consecutive same-state duplication = 0,
  - emitted stream consecutive same-fill duplication = 0,
  - false_suppression_candidate_count = 0,
  - explainability_completeness = 1.0.
- The current live config still keeps the sidecar in shadow mode:
  - config/aurora/domains.yaml sets position_policy_sidecar.mode = shadow,
  - config/aurora/domains.yaml keeps recommend_soft_close_at = 0.30.

### INFERENCE

- Package 5 already executed two bounded calibration iterations inside its allowed scope:
  - Package 5.1 corrected the zero-yield threshold blocker.
  - Package 5.2 corrected the emitted-stream duplication/noise that the first post-change runtime exposed.
- The evidence chain is now sequential and closed enough for governance review:
  - zero-yield failure identified,
  - threshold calibrated,
  - noisy recommendation behavior discovered,
  - suppression rule refined,
  - fresh post-restart runtime confirmed the refinement.

## Package 5 DoD Assessment

### 1. Calibration changes are evidence-driven

### FACT

- Threshold 0.70 -> 0.30 was justified by observed max soft_close_pressure = 0.3 under the prior zero-recommendation slice.
- Suppression refinement in Package 5.2 was justified by the post-change 24h runtime showing 100 percent consecutive same-state and same-fill emitted duplication for the recommending symbols.

### VERDICT

- PASS.

### 2. Before/after validation comparison exists

### FACT

- Before threshold calibration: RECOMMENDED = 0.
- After threshold calibration but before dedup refinement: RECOMMENDED = 167 with unacceptable emitted duplication.
- After Package 5.2 refinement: RECOMMENDED = 8 with 292 duplicate suppressions and zero emitted duplicate pairs.

### VERDICT

- PASS.

### 3. Premature close rate is reduced or controlled

### FACT

- Phase 5 explicitly forbids action enablement.
- Current config remains shadow mode, so Package 5 cannot directly prove live premature closes.
- The only in-scope shadow proxy for premature close behavior is emitted recommendation pressure quality.
- That proxy moved from uncontrolled repeated same-state emission to controlled single-emission-plus-suppression behavior.

### INFERENCE

- Under the Package 5 shadow-only contract, recommendation pressure is now controlled enough to satisfy the DoD proxy that Phase 5 can legitimately measure.

### VERDICT

- PASS within shadow scope.

### 4. Explainability remains complete

### FACT

- explainability_completeness remained 1.0 in the post-change review and in the Package 5.2 post-restart review.

### VERDICT

- PASS.

### 5. REPORT states exact changes and why

### FACT

- The evidence chain already records exact Package 5 changes and rationale:
  - threshold calibration 0.70 -> 0.30 to remove the zero-yield blocker,
  - duplicate same-state suppression to remove repeated same-state emitted recommendations.
- The current closure review consolidates those changes against the roadmap boundary and frozen runtime evidence.

### VERDICT

- PASS.

## What Is Complete Inside Package 5

### FACT

- Shadow validation existed before calibration work.
- Threshold geometry no longer blocks recommendation emergence completely.
- The emitted recommendation stream is no longer noisy in the previously proven same-state / same-fill defect pattern.
- Re-emission after meaningful state change or new lifecycle boundary was proven in the Package 5.2 runtime analysis.
- No false suppression evidence was found in the frozen 27.5h post-restart slice.
- Package 5 remained inside its allowed scope:
  - no action enablement,
  - no new contract semantics,
  - no bracket mutation,
  - no partial reduce.

## What Remains Open But Is Outside Package 5

### FACT

- The Phase 6 roadmap questions are explicitly separate from Package 5 and include:
  - whether recommendation quality is stable enough,
  - whether overlap with ExitManager is sufficiently understood,
  - whether suppression rules are reliable enough for admission,
  - whether traces are sufficient for race forensics,
  - whether symbol-scoped close fits the business need,
  - whether false-positive risk is acceptable.
- Current evidence still shows all emitted recommendations exactly on the 0.30 threshold boundary.
- Current evidence is still shadow-only; no action-mode admission has been granted.

### INFERENCE

- Exact-threshold recommendation geometry is still an admission-risk question, but the roadmap places that question in Phase 6 action-readiness review, not in Phase 5 calibration closure.
- Keeping Package 5 open would require inventing a new Phase 5 acceptance condition beyond the documented roadmap DoD.

## Not Proven

### FACT

- This closure review does not prove that action mode is safe.
- This closure review does not prove acceptable real false-positive risk for live soft-close requests.
- This closure review does not prove that overlap with incumbent close mechanisms is fully understood.
- This closure review does not prove multi-day stability beyond the frozen 27.5h post-restart runtime slice.

### INFERENCE

- Those gaps are legitimate reasons to hold or reject Phase 6 admission later, but they are not evidence that Package 5 itself is still incomplete.

## Final Decision

### DECISION

CLOSE_PACKAGE5

### Why this is the correct decision

### FACT

- Package 5 roadmap scope is calibration only, not action admission.
- Package 5 DoD items are satisfied by the frozen evidence chain available in the repo.
- A fresh post-restart runtime slice longer than 24h already exists and is explicitly marked sufficient for review.
- No currently evidenced Package 5 DoD failure remains open after the Package 5.2 refinement.

### INFERENCE

- PACKAGE5_NEEDS_ONE_LAST_NARROW_ITERATION is not supported by current evidence because the only remaining concerns are Phase 6 admission questions, not missed Package 5 calibration deliverables.
- HOLD_PACKAGE5_PENDING_MORE_RUNTIME_EVIDENCE is not supported because Package 5 already has a fresh 27.5h post-restart slice that closes the specific noisy-emission defect opened by the earlier 24h run.

## Next Exact Step

- Begin Phase 6 Action-Readiness Gate Review in shadow mode only.
- Use the Phase 6 review questions from position_policy_sidecar_roadmap_v_1.md as the admission checklist.
- Do not enable action mode from this report.
