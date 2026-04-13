# REPORT — POSITION POLICY SIDECAR PACKAGE 5.2 POST-RESTART 24H+ RUNTIME REVIEW 2026-04-10

## Executive Verdict

- Operational verdict: PACKAGE52_RUNTIME_FIX_CONFIRMED.
- Defect-class verdict: FIXED.
- Frozen review slice: start ts_ms 1775728324358 at logs/trade_lifecycle.jsonl:1, frozen end ts_ms 1775827331073, runtime span 27.5019h.
- The previously proven noisy emitted-stream defect is no longer present in runtime truth: RECOMMENDED fell from 167 to 8, recommendation_duplicate_same_state suppressions appeared with count 292, and the frozen emitted recommendation stream shows 0 consecutive same-state and 0 consecutive same-fill recommendation pairs.

## Active Runtime Boundary Proof

Artifacts used for this review:

- logs/trade_lifecycle.jsonl
- logs/order_log_v1.jsonl
- config/aurora/domains.yaml
- artifacts/position_policy_sidecar/package52_post_restart_runtime_review_20260410.json
- artifacts/position_policy_sidecar/package52_post_restart_runtime_analysis_20260410.json
- artifacts/position_policy_sidecar/package5_post_change_runtime_cadence_20260408.json
- artifacts/position_policy_sidecar/package5_post_change_runtime_overlap_corrected_20260408.json

Active runtime boundary proof:

- Exact MODE_ACTIVE boundary: logs/trade_lifecycle.jsonl:1 contains POSITION_POLICY_SIDECAR_MODE_ACTIVE with ts_ms 1775728324358.
- Frozen current slice boundary: artifacts/position_policy_sidecar/package52_post_restart_runtime_analysis_20260410.json records slice_start_ts_ms 1775728324358, slice_end_ts_ms 1775827331073, duration_hours 27.501865277777778, artifact_sufficient_for_24h_review = true.
- MODE_ACTIVE count in the frozen slice is 1, so the reviewed runtime is one post-restart slice, not a mixed multi-restart sample.
- Proof that Package 5.2 dedup logic was active in runtime output is present directly in logs/trade_lifecycle.jsonl:44897 and logs/trade_lifecycle.jsonl:44906. Both rows carry suppression_reason = recommendation_duplicate_same_state and dedup_detail.suppressed_count = 1 then 2.

Freeze rule used for this review:

- logs/trade_lifecycle.jsonl was still append-active during capture, so this report intentionally freezes all current-run counts to the explicit analysis artifact end ts_ms 1775827331073.
- Overlap and threshold-crossing context were taken from the synchronized validator artifact written during the same review window.

## FACTS

- Frozen pre-dedup baseline truth from artifacts/position_policy_sidecar/package5_post_change_runtime_cadence_20260408.json:
  - runtime span = 23.914493611111112h
  - RECOMMENDED = 167
  - BTCUSDT = 93
  - ETHUSDT = 74
  - both recommending symbols had 100% consecutive same-state duplication
  - both recommending symbols had 100% consecutive same-fill duplication
- Frozen corrected pre-dedup overlap truth from artifacts/position_policy_sidecar/package5_post_change_runtime_overlap_corrected_20260408.json:
  - overlap_count = 19
  - overlap was BTCUSDT-only
- Frozen post-fix current slice from artifacts/position_policy_sidecar/package52_post_restart_runtime_analysis_20260410.json:
  - MODE_ACTIVE = 1
  - SUPPRESSED = 131104
  - SCORES = 1140
  - EVALUATED = 1140
  - RECOMMENDED = 8
  - ACTION_SKIPPED = 0
  - execution_fill_ingress count = 218
- Current recommendation count by symbol:
  - SOLUSDT = 4
  - BTCUSDT = 3
  - ETHUSDT = 1
  - DOGEUSDT = 0
- Current recommendation_duplicate_same_state suppression count by symbol:
  - BTCUSDT = 121
  - SOLUSDT = 102
  - ETHUSDT = 69
  - DOGEUSDT = 0
- Current suppressor counts by reason:

| Reason | Count |
| --- | ---: |
| no_manage_flow_for_symbol | 61957 |
| features_snapshot_missing_or_stale | 33080 |
| manage_flow_has_no_active_lifecycle | 28444 |
| regime_snapshot_missing_or_stale | 4453 |
| portfolio_snapshot_missing_or_stale | 1733 |
| startup_grace_active | 778 |
| post_fill_grace_active | 367 |
| recommendation_duplicate_same_state | 292 |

- Current dedup-specific quality checks from artifacts/position_policy_sidecar/package52_post_restart_runtime_analysis_20260410.json:
  - recommended_soft_close_pressure_values = [0.3]
  - all_recommendations_exactly_on_threshold_boundary = true
  - monotonic_duplicate_suppression_windows = true
  - monotonic_violations = []
  - false_suppression_candidate_count = 0
- Current threshold-crossing context from artifacts/position_policy_sidecar/package52_post_restart_runtime_review_20260410.json:
  - threshold_crossing_evaluated_count = 300
  - BTCUSDT threshold-crossing evaluated count = 124
  - SOLUSDT threshold-crossing evaluated count = 106
  - ETHUSDT threshold-crossing evaluated count = 70
  - DOGEUSDT threshold-crossing evaluated count = 0
- Arithmetic identity in the current slice:
  - 300 threshold-crossing evaluated rows - 8 emitted recommendations = 292
  - 292 exactly matches suppression_count_by_reason.recommendation_duplicate_same_state
- Frozen emitted recommendation stream audit bounded to slice_end_ts_ms 1775827331073 found:
  - BTCUSDT consecutive same-state recommendation pairs = 0 / 2
  - BTCUSDT consecutive same-fill recommendation pairs = 0 / 2
  - ETHUSDT consecutive same-state recommendation pairs = 0 / 0
  - ETHUSDT consecutive same-fill recommendation pairs = 0 / 0
  - SOLUSDT consecutive same-state recommendation pairs = 0 / 3
  - SOLUSDT consecutive same-fill recommendation pairs = 0 / 3
- Current overlap from artifacts/position_policy_sidecar/package52_post_restart_runtime_review_20260410.json:
  - matched_recommendations = 8
  - overlap sample by symbol = SOLUSDT 4, BTCUSDT 3, ETHUSDT 1

## INFERENCES

- The old emitted-stream defect class is now absorbed by dedup rather than emitted to runtime consumers. The strongest evidence is that the full threshold-crossing gap 300 - 8 is explained exactly by 292 recommendation_duplicate_same_state suppressions.
- Recommendation quality materially improved. The emitted stream went from a bursty 167 recommendations in 23.9145h to 8 recommendations in 27.5019h, and the emitted recommendations no longer repeat same-state or same-fill signatures consecutively.
- Residual duplicate attempts still exist inside the evaluator cadence, but they are no longer a live emitted-stream defect because they are converted into explicit suppressions with monotonic dedup_detail.suppressed_count.
- The validator field recommendation_truth_classification = recommendation_emission_gap is not evidence of a new failure by itself in this run. In this specific post-fix slice, that generic gap is fully accounted for by deliberate duplicate suppression.
- Recommendation quality is now acceptable for Package 5 closure review. The stream is sparse enough to inspect manually, and the corrected overlap sample is materially more interpretable than the pre-dedup burst.

## ASSUMPTIONS

- The frozen pre-dedup baseline counts supplied in the task prompt remain authoritative and are represented by the 2026-04-08 baseline artifacts above.
- No external action mode or threshold/config drift changed runtime semantics during the frozen current slice beyond the already-shipped Package 5.2 dedup behavior.

## UNKNOWNS

- This review does not prove how the same dedup behavior will look over a longer multi-day capture beyond 27.5019h.
- All emitted recommendations still sit exactly at soft_close_pressure = 0.3, so any future question about threshold geometry or actionability remains outside the scope of this dedup-only runtime review.

## Fresh Post-Fix Slice Summary

Current frozen slice summary:

| Metric | Pre-dedup baseline | Post-fix frozen slice |
| --- | ---: | ---: |
| Runtime hours | 23.9145 | 27.5019 |
| MODE_ACTIVE | 1 | 1 |
| SUPPRESSED | 113722 | 131104 |
| SCORES | 885 | 1140 |
| EVALUATED | 885 | 1140 |
| RECOMMENDED | 167 | 8 |
| ACTION_SKIPPED | 0 | 0 |
| execution_fill_ingress | 53 | 218 |
| recommendation_duplicate_same_state suppressions | absent | 292 |

Per-symbol recommendation comparison:

| Symbol | Pre-dedup RECOMMENDED | Post-fix RECOMMENDED | Post-fix duplicate suppressions |
| --- | ---: | ---: | ---: |
| BTCUSDT | 93 | 3 | 121 |
| ETHUSDT | 74 | 1 | 69 |
| SOLUSDT | 0 | 4 | 102 |
| DOGEUSDT | 0 | 0 | 0 |

## Recommendation Behavior Review

- Total RECOMMENDED fell materially: 167 -> 8.
- The emitted recommendation rate also fell materially: the pre-dedup stream emitted frequent same-state bursts, while the current 27.5019h slice emitted only 8 recommendations total.
- BTCUSDT and ETHUSDT no longer dominate the stream. Combined they emitted 4 recommendations, while SOLUSDT emitted 4 on its own.
- SOLUSDT is no longer silent. DOGEUSDT remains silent and also has 0 threshold-crossing evaluated rows in the current validator summary.
- All emitted recommendations still sit exactly on the threshold boundary 0.3. That was true in the noisy pre-dedup run and remains true here.
- Recommendation emergence remains explainable from runtime truth. Every emitted recommendation is accompanied by a threshold-met row, fill context, and a later dedup or re-emission chain that can be reconstructed directly from logs.

## Dedup Effectiveness Review

- recommendation_duplicate_same_state is present in runtime and materially active with count 292.
- dedup_detail.suppressed_count grows monotonically inside reviewed windows; the frozen analysis artifact reported zero monotonic violations.
- The old duplicate stream was absorbed rather than re-emitted:
  - pre-dedup baseline consecutive same-state RECOMMENDED duplication = 100% for BTCUSDT and ETHUSDT
  - frozen post-fix emitted stream consecutive same-state RECOMMENDED duplication = 0% for BTCUSDT, ETHUSDT, and SOLUSDT
  - frozen post-fix emitted stream consecutive same-fill RECOMMENDED duplication = 0% for BTCUSDT, ETHUSDT, and SOLUSDT
- The strongest aggregate proof is exact replacement arithmetic: 300 threshold-crossing evaluated rows, 8 emitted recommendations, 292 duplicate suppressions.
- Dedup defect-class determination: FIXED.

## Re-Emission Correctness Review

Concrete symbol-level chain A — SOLUSDT meaningful-state re-emission within one lifecycle:

- First recommendation: logs/trade_lifecycle.jsonl:44879, trace_id pps:SOLUSDT:1775760604575:44442, portfolio_position_amt = -31.4, canonical_fill_trace_id = exec-fill:SOLUSDT:trade_executed:aurora_SOLUSDT_1775760304347:1775760334824.
- Duplicate attempts suppressed instead of emitted: logs/trade_lifecycle.jsonl:44897 and logs/trade_lifecycle.jsonl:44906 with suppressed_count 1 then 2 and identical signature_fields.
- Later re-emission: logs/trade_lifecycle.jsonl:45356, trace_id pps:SOLUSDT:1775760912887:44899.
- Proven changed fields before re-emission:
  - portfolio_position_amt changed from -31.4 to -76
  - canonical_fill_trace_id changed from exec-fill:SOLUSDT:trade_executed:aurora_SOLUSDT_1775760304347:1775760334824 to exec-fill:SOLUSDT:trade_executed:aurora_SOLUSDT_1775760304347:1775760896036
- Conclusion: duplicate same-state attempts were suppressed, and re-emission resumed only after meaningful state change.

Concrete symbol-level chain B — SOLUSDT new lifecycle boundary re-emission:

- First recommendation in the window: logs/trade_lifecycle.jsonl:45356, trace_id pps:SOLUSDT:1775760912887:44899.
- Subsequent duplicate attempts in that window were suppressed with monotonic suppressed_count, beginning at logs/trade_lifecycle.jsonl:45365 and continuing through a 24-suppression window in the frozen analysis artifact.
- Later re-emission on a new lifecycle: logs/trade_lifecycle.jsonl:54674, trace_id pps:SOLUSDT:1775767501351:53852.
- Proven changed fields before re-emission:
  - position_qty changed from 15.7 to 1.74
  - canonical_fill_trace_id changed from exec-fill:SOLUSDT:trade_executed:aurora_SOLUSDT_1775760304347:1775760896036 to exec-fill:SOLUSDT:trade_executed:aurora_SOLUSDT_1775767201046:1775767344171
  - position_open_ts changed from 1775760305.885061 to 1775767328.2409382
- Conclusion: dedup reset did not block legitimate re-emission after a new lifecycle boundary.

Concrete symbol-level chain C — BTCUSDT re-emission after changed position/fill context:

- First recommendation: logs/trade_lifecycle.jsonl:51447, trace_id pps:BTCUSDT:1775765104093:50764.
- Later recommendations: logs/trade_lifecycle.jsonl:57216 and logs/trade_lifecycle.jsonl:63413.
- The emitted BTCUSDT stream has 3 recommendations and 0 consecutive same-state or same-fill recommendation pairs in the frozen review.
- Conclusion: BTCUSDT also shows re-emission only after changed emitted-state signature, not by same-state repetition.

## False Suppression Review

- No evidence of false suppression was found in the frozen slice.
- frozen analysis artifact false_suppression_candidate_count = 0.
- No recommendation_duplicate_same_state suppression row was found with signature_fields differing from the immediately preceding emitted recommendation signature.
- Therefore the reviewed runtime provides no evidence that meaningful new recommendations were suppressed incorrectly.

## Overlap / Quality Review

- Corrected pre-dedup overlap sample count = 19, all BTCUSDT, from artifacts/position_policy_sidecar/package5_post_change_runtime_overlap_corrected_20260408.json.
- Current overlap sample count = 8, distributed as SOLUSDT 4, BTCUSDT 3, ETHUSDT 1.
- This post-fix overlap view is more interpretable than the pre-dedup run because the sample is small, symbol-diverse, and no longer dominated by same-state repeat bursts.
- The recommendation stream is now sparse enough to review meaningfully in an operational shadow audit.
- Residual caveat: recommendations remain threshold-boundary events at 0.3. That is a geometry/explainability concern, not evidence that the Package 5.2 dedup fix failed.

## Final Verdict

PACKAGE52_RUNTIME_FIX_CONFIRMED

Justification:

- The previously proven noisy emitted-stream defect was materially removed in fresh post-restart runtime truth.
- RECOMMENDED dropped from 167 to 8.
- recommendation_duplicate_same_state appeared with count 292 and exactly absorbed the threshold-crossing gap.
- Re-emission after suppression was proven on concrete symbol chains only after meaningful state change or new lifecycle boundary.
- No evidence of false suppression was found.

## Next Exact Step

prepare Package 5 closure review
