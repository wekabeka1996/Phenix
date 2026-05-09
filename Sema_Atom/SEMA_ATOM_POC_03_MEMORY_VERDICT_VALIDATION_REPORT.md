# SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT

## Verdict
VALIDATION_PASSED

## Scope
- Read-only validation of POC_02 memory verdicts using only `aurora_real_logs_v02.saf.jsonl` and the POC_02 report.
- No live logic, policy, gating, or enforcement changes.

## Inputs Read
- C:\Users\user\Music\Phenix\aurora_real_logs_v02.saf.jsonl
- C:\Users\user\Music\Phenix\SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md

## Summary
- total atoms: 153
- contexts tested: 10
- contexts skipped due to low support: 27
- verdict confirmation rate: 0.7000
- false positive verdicts: 2
- false negative verdicts: 1

## Context Evaluation Details
- context: BNBUSDT BUY aurora MEAN_REVERSION 0.00..0.25
  train_count=1 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=29.225054 validation_net_score=-39.133978
  train_outcomes={"GOOD_DECISION": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BNBUSDT BUY aurora MEAN_REVERSION 0.25..0.50
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=15.827284
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BNBUSDT BUY aurora TREND_UP 0.00..0.25
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=0.000000
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BNBUSDT BUY aurora TREND_UP 0.25..0.50
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=59.517628
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BNBUSDT SELL aurora MEAN_REVERSION 0.00..0.25
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=-1.541283
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BNBUSDT SELL aurora MEAN_REVERSION 0.25..0.50
  train_count=1 validation_count=2 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=-41.073298 validation_net_score=-28.193598
  train_outcomes={"CLEAN_LOSS": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BNBUSDT SELL aurora TREND_DOWN 0.00..0.25
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=0.000000
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BNBUSDT SELL aurora TREND_DOWN 0.25..0.50
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=-3.797213
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BTCUSDT BUY aurora LOW_VOLATILITY 0.00..0.25
  train_count=1 validation_count=2 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=37.282120 validation_net_score=-16.303586
  train_outcomes={"POLICY_PROTECTED": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BTCUSDT BUY aurora LOW_VOLATILITY 0.25..0.50
  train_count=10 validation_count=11 verdict=POLICY_TOO_STRICT_CANDIDATE recommendation=review_policy_thresholds
  train_net_score=-16.461044 validation_net_score=-11.844887
  train_outcomes={"POLICY_PROTECTED": 2, "POLICY_TOO_STRICT": 8} validation_outcomes={"POLICY_PROTECTED": 3, "POLICY_TOO_STRICT": 8}
  validation_result=CONFIRMED reason=validation_high_missed_positive_rate
- context: BTCUSDT BUY aurora LOW_VOLATILITY 0.50..0.75
  train_count=4 validation_count=5 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  train_net_score=15.522118 validation_net_score=-0.703415
  train_outcomes={"POLICY_PROTECTED": 4} validation_outcomes={"POLICY_PROTECTED": 3, "POLICY_TOO_STRICT": 2}
  validation_result=CONFIRMED reason=validation_positive_profile
- context: BTCUSDT BUY aurora MEAN_REVERSION 0.00..0.25
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=-18.670379
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BTCUSDT BUY aurora TREND_UP 0.00..0.25
  train_count=1 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=27.173964
  train_outcomes={"GOOD_DECISION": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BTCUSDT BUY aurora TREND_UP 0.25..0.50
  train_count=1 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=-5.315347 validation_net_score=-51.683620
  train_outcomes={"GOOD_DECISION": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BTCUSDT SELL aurora LOW_VOLATILITY 0.25..0.50
  train_count=8 validation_count=8 verdict=POLICY_TOO_STRICT_CANDIDATE recommendation=review_policy_thresholds
  train_net_score=-8.130135 validation_net_score=10.475059
  train_outcomes={"POLICY_PROTECTED": 3, "POLICY_TOO_STRICT": 5} validation_outcomes={"POLICY_PROTECTED": 6, "POLICY_TOO_STRICT": 2}
  validation_result=CONTRADICTED reason=validation_missing_missed_positive_pattern
- context: BTCUSDT SELL aurora LOW_VOLATILITY 0.50..0.75
  train_count=1 validation_count=2 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=-2.720323 validation_net_score=27.181375
  train_outcomes={"POLICY_TOO_STRICT": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BTCUSDT SELL aurora LOW_VOLATILITY 0.75..1.00
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=7.806895
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BTCUSDT SELL aurora MEAN_REVERSION 0.00..0.25
  train_count=1 validation_count=2 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=20.131715 validation_net_score=-2.733550
  train_outcomes={"GOOD_DECISION": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BTCUSDT SELL aurora MEAN_REVERSION 0.25..0.50
  train_count=2 validation_count=3 verdict=MIXED_CONTEXT recommendation=monitor
  train_net_score=-11.375384 validation_net_score=1.453925
  train_outcomes={"GOOD_DECISION": 2} validation_outcomes={"GOOD_DECISION": 3}
  validation_result=CONTRADICTED reason=validation_became_directional
- context: BTCUSDT SELL aurora TREND_DOWN 0.25..0.50
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=-22.219186
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: ETHUSDT BUY aurora LOW_VOLATILITY 0.00..0.25
  train_count=1 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=13.716633 validation_net_score=-31.179324
  train_outcomes={"POLICY_PROTECTED": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: ETHUSDT BUY aurora LOW_VOLATILITY 0.25..0.50
  train_count=3 validation_count=3 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  train_net_score=17.533576 validation_net_score=47.664485
  train_outcomes={"POLICY_PROTECTED": 2, "POLICY_TOO_STRICT": 1} validation_outcomes={"POLICY_PROTECTED": 3}
  validation_result=CONFIRMED reason=validation_positive_profile
- context: ETHUSDT BUY aurora LOW_VOLATILITY 0.50..0.75
  train_count=1 validation_count=2 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=24.329139 validation_net_score=-36.462428
  train_outcomes={"POLICY_PROTECTED": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: ETHUSDT BUY aurora LOW_VOLATILITY 0.75..1.00
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=-72.065533
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: ETHUSDT BUY aurora TREND_UP 0.00..0.25
  train_count=1 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=-29.469712 validation_net_score=-23.088604
  train_outcomes={"CLEAN_LOSS": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: ETHUSDT SELL aurora LOW_VOLATILITY 0.00..0.25
  train_count=3 validation_count=4 verdict=POLICY_TOO_STRICT_CANDIDATE recommendation=review_policy_thresholds
  train_net_score=-0.358196 validation_net_score=-21.005237
  train_outcomes={"POLICY_PROTECTED": 1, "POLICY_TOO_STRICT": 2} validation_outcomes={"POLICY_PROTECTED": 1, "POLICY_TOO_STRICT": 3}
  validation_result=CONFIRMED reason=validation_high_missed_positive_rate
- context: ETHUSDT SELL aurora LOW_VOLATILITY 0.25..0.50
  train_count=9 validation_count=10 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  train_net_score=0.365491 validation_net_score=-1.074598
  train_outcomes={"POLICY_PROTECTED": 5, "POLICY_TOO_STRICT": 4} validation_outcomes={"POLICY_PROTECTED": 6, "POLICY_TOO_STRICT": 4}
  validation_result=CONFIRMED reason=validation_positive_profile
- context: ETHUSDT SELL aurora LOW_VOLATILITY 0.50..0.75
  train_count=5 validation_count=5 verdict=POLICY_TOO_STRICT_CANDIDATE recommendation=review_policy_thresholds
  train_net_score=6.828617 validation_net_score=12.356725
  train_outcomes={"POLICY_PROTECTED": 2, "POLICY_TOO_STRICT": 3} validation_outcomes={"POLICY_PROTECTED": 4, "POLICY_TOO_STRICT": 1}
  validation_result=CONTRADICTED reason=validation_missing_missed_positive_pattern
- context: ETHUSDT SELL aurora TREND_DOWN 0.00..0.25
  train_count=3 validation_count=3 verdict=TOXIC_CONTEXT recommendation=avoid_or_review
  train_net_score=-22.481593 validation_net_score=-2.589772
  train_outcomes={"CLEAN_LOSS": 3} validation_outcomes={"CLEAN_LOSS": 2, "GOOD_DECISION": 1}
  validation_result=CONFIRMED reason=validation_negative_profile
- context: XRPUSDT BUY aurora LOW_VOLATILITY 0.25..0.50
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=-13.564463
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: XRPUSDT BUY aurora MEAN_REVERSION 0.25..0.50
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=-34.244157
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: XRPUSDT BUY aurora TREND_UP 0.25..0.50
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=48.894114
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: XRPUSDT SELL aurora LOW_VOLATILITY 0.00..0.25
  train_count=1 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=37.437080 validation_net_score=38.787232
  train_outcomes={"POLICY_PROTECTED": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: XRPUSDT SELL aurora LOW_VOLATILITY 0.25..0.50
  train_count=4 validation_count=4 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  train_net_score=13.040321 validation_net_score=-4.028049
  train_outcomes={"POLICY_PROTECTED": 4} validation_outcomes={"POLICY_PROTECTED": 2, "POLICY_TOO_STRICT": 2}
  validation_result=CONFIRMED reason=validation_positive_profile
- context: XRPUSDT SELL aurora MEAN_REVERSION 0.00..0.25
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=37.115134
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: XRPUSDT SELL aurora MEAN_REVERSION 0.25..0.50
  train_count=1 validation_count=2 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=30.665903 validation_net_score=-27.032805
  train_outcomes={"GOOD_DECISION": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: XRPUSDT SELL aurora MEAN_REVERSION 0.50..0.75
  train_count=1 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=27.393798 validation_net_score=9.156211
  train_outcomes={"GOOD_DECISION": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold

## Top Toxic Candidates
- ETHUSDT SELL TREND_DOWN 0.00..0.25 train_count=3 validation_count=3 train_score=-22.481593 validation_result=CONFIRMED

## Top Favorable Candidates
- ETHUSDT BUY LOW_VOLATILITY 0.25..0.50 train_count=3 validation_count=3 train_score=17.533576 validation_result=CONFIRMED
- BTCUSDT BUY LOW_VOLATILITY 0.50..0.75 train_count=4 validation_count=5 train_score=15.522118 validation_result=CONFIRMED
- XRPUSDT SELL LOW_VOLATILITY 0.25..0.50 train_count=4 validation_count=4 train_score=13.040321 validation_result=CONFIRMED
- ETHUSDT SELL LOW_VOLATILITY 0.25..0.50 train_count=9 validation_count=10 train_score=0.365491 validation_result=CONFIRMED

## Top Policy-Too-Strict Candidates
- BTCUSDT BUY LOW_VOLATILITY 0.25..0.50 train_count=10 validation_count=11 train_score=0.800000 validation_result=CONFIRMED
- ETHUSDT SELL LOW_VOLATILITY 0.00..0.25 train_count=3 validation_count=4 train_score=0.666667 validation_result=CONFIRMED
- BTCUSDT SELL LOW_VOLATILITY 0.25..0.50 train_count=8 validation_count=8 train_score=0.625000 validation_result=CONTRADICTED
- ETHUSDT SELL LOW_VOLATILITY 0.50..0.75 train_count=5 validation_count=5 train_score=0.600000 validation_result=CONTRADICTED

## False Positive Verdicts
- BTCUSDT SELL LOW_VOLATILITY 0.25..0.50 verdict=POLICY_TOO_STRICT_CANDIDATE validation_result=CONTRADICTED reason=validation_missing_missed_positive_pattern
- ETHUSDT SELL LOW_VOLATILITY 0.50..0.75 verdict=POLICY_TOO_STRICT_CANDIDATE validation_result=CONTRADICTED reason=validation_missing_missed_positive_pattern

## False Negative Verdicts
- BTCUSDT SELL MEAN_REVERSION 0.25..0.50 verdict=MIXED_CONTEXT validation_result=CONTRADICTED reason=validation_became_directional

## Residual Uncertainty
- The SAF file is a single frozen slice, so chronological validation is within-slice only and not a fresh forward period.
- Context support is sparse for many symbol/side/regime buckets, so skipped contexts materially limit confidence.
- `POLICY_TOO_STRICT` evidence is strongest where the adapter already reconstructed rejected offline outcomes; missing-reference rejects remain out of scope.
- `NEUTRAL_SIGNAL` rows are retained for chronology and support accounting but do not directly prove favorable or toxic predictive value.

