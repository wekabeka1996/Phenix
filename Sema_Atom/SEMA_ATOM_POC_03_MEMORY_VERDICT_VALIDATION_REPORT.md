# SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT

## Verdict
VALIDATION_PASSED

## Scope
- Read-only validation of POC_02 memory verdicts using only `aurora_real_logs_v02.saf.jsonl` and the POC_02 report.
- No live logic, policy, gating, or enforcement changes.

## Inputs Read
- Sema_Atom\aurora_real_logs_v02.saf.jsonl
- C:\Users\user\Music\Phenix\Sema_Atom\SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md

## Summary
- total atoms: 337
- contexts tested: 20
- contexts skipped due to low support: 20
- total context evaluations: 40
- verdict confirmation rate: 0.6000
- false positive verdicts: 5
- false negative verdicts: 3

## Context Evaluation Details
- context: BNBUSDT BUY aurora MEAN_REVERSION 0.25..0.50
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=32.909634
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BNBUSDT BUY aurora TREND_UP 0.25..0.50
  train_count=1 validation_count=2 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=59.948960 validation_net_score=-28.026722
  train_outcomes={"GOOD_DECISION": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BNBUSDT SELL aurora MEAN_REVERSION 0.25..0.50
  train_count=1 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=-2.260943 validation_net_score=-26.324304
  train_outcomes={"CLEAN_LOSS": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BNBUSDT SELL aurora MEAN_REVERSION 0.50..0.75
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=13.188436
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BNBUSDT SELL aurora TREND_DOWN 0.00..0.25
  train_count=1 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=-17.353488 validation_net_score=-35.459945
  train_outcomes={"CLEAN_LOSS": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BTCUSDT BUY aurora LOW_VOLATILITY 0.00..0.25
  train_count=1 validation_count=2 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=31.194600 validation_net_score=6.398809
  train_outcomes={"POLICY_PROTECTED": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BTCUSDT BUY aurora LOW_VOLATILITY 0.25..0.50
  train_count=6 validation_count=6 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  train_net_score=5.773558 validation_net_score=3.948269
  train_outcomes={"POLICY_PROTECTED": 5, "POLICY_TOO_STRICT": 1} validation_outcomes={"POLICY_PROTECTED": 4, "POLICY_TOO_STRICT": 2}
  validation_result=CONFIRMED reason=validation_positive_profile
- context: BTCUSDT BUY aurora LOW_VOLATILITY 0.50..0.75
  train_count=2 validation_count=3 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  train_net_score=11.367413 validation_net_score=28.611986
  train_outcomes={"POLICY_PROTECTED": 2} validation_outcomes={"POLICY_PROTECTED": 3}
  validation_result=CONFIRMED reason=validation_positive_profile
- context: BTCUSDT BUY aurora MEAN_REVERSION 0.50..0.75
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=1.811250
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BTCUSDT BUY aurora TREND_UP 0.00..0.25
  train_count=1 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=40.676595 validation_net_score=30.837680
  train_outcomes={"GOOD_DECISION": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BTCUSDT SELL aurora LOW_VOLATILITY 0.00..0.25
  train_count=9 validation_count=9 verdict=POLICY_TOO_STRICT_CANDIDATE recommendation=review_policy_thresholds
  train_net_score=-0.816258 validation_net_score=1.616235
  train_outcomes={"POLICY_PROTECTED": 3, "POLICY_TOO_STRICT": 6} validation_outcomes={"POLICY_PROTECTED": 5, "POLICY_TOO_STRICT": 4}
  validation_result=CONTRADICTED reason=validation_missing_missed_positive_pattern
- context: BTCUSDT SELL aurora LOW_VOLATILITY 0.25..0.50
  train_count=17 validation_count=18 verdict=POLICY_TOO_STRICT_CANDIDATE recommendation=review_policy_thresholds
  train_net_score=-9.274239 validation_net_score=7.277411
  train_outcomes={"POLICY_PROTECTED": 5, "POLICY_TOO_STRICT": 12} validation_outcomes={"GOOD_DECISION": 2, "POLICY_PROTECTED": 7, "POLICY_TOO_STRICT": 9}
  validation_result=CONFIRMED reason=validation_high_missed_positive_rate
- context: BTCUSDT SELL aurora LOW_VOLATILITY 0.50..0.75
  train_count=9 validation_count=10 verdict=POLICY_TOO_STRICT_CANDIDATE recommendation=review_policy_thresholds
  train_net_score=-0.249928 validation_net_score=-6.135459
  train_outcomes={"POLICY_PROTECTED": 3, "POLICY_TOO_STRICT": 6} validation_outcomes={"POLICY_PROTECTED": 4, "POLICY_TOO_STRICT": 6}
  validation_result=CONFIRMED reason=validation_high_missed_positive_rate
- context: BTCUSDT SELL aurora LOW_VOLATILITY 0.75..1.00
  train_count=5 validation_count=5 verdict=POLICY_TOO_STRICT_CANDIDATE recommendation=review_policy_thresholds
  train_net_score=-33.904731 validation_net_score=10.848701
  train_outcomes={"POLICY_TOO_STRICT": 5} validation_outcomes={"POLICY_PROTECTED": 5}
  validation_result=CONTRADICTED reason=validation_missing_missed_positive_pattern
- context: BTCUSDT SELL aurora MEAN_REVERSION 0.00..0.25
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=20.421620
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: BTCUSDT SELL aurora MEAN_REVERSION 0.25..0.50
  train_count=2 validation_count=3 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  train_net_score=31.105787 validation_net_score=16.100746
  train_outcomes={"GOOD_DECISION": 2} validation_outcomes={"CLEAN_LOSS": 1, "GOOD_DECISION": 2}
  validation_result=CONFIRMED reason=validation_positive_profile
- context: BTCUSDT SELL aurora TREND_DOWN 0.00..0.25
  train_count=1 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=52.507045 validation_net_score=0.000000
  train_outcomes={"GOOD_DECISION": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: DOGEUSDT SELL aurora TREND_DOWN 0.00..0.25
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=97.266036
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: ETHUSDT BUY aurora LOW_VOLATILITY 0.00..0.25
  train_count=2 validation_count=2 verdict=POLICY_TOO_STRICT_CANDIDATE recommendation=review_policy_thresholds
  train_net_score=-5.306854 validation_net_score=25.242908
  train_outcomes={"POLICY_TOO_STRICT": 2} validation_outcomes={"POLICY_PROTECTED": 2}
  validation_result=CONTRADICTED reason=validation_missing_missed_positive_pattern
- context: ETHUSDT BUY aurora LOW_VOLATILITY 0.25..0.50
  train_count=10 validation_count=11 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  train_net_score=0.493415 validation_net_score=12.991174
  train_outcomes={"POLICY_PROTECTED": 7, "POLICY_TOO_STRICT": 3} validation_outcomes={"POLICY_PROTECTED": 9, "POLICY_TOO_STRICT": 2}
  validation_result=CONFIRMED reason=validation_positive_profile
- context: ETHUSDT BUY aurora LOW_VOLATILITY 0.50..0.75
  train_count=8 validation_count=8 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  train_net_score=6.110600 validation_net_score=5.113279
  train_outcomes={"POLICY_PROTECTED": 5, "POLICY_TOO_STRICT": 3} validation_outcomes={"POLICY_PROTECTED": 7, "POLICY_TOO_STRICT": 1}
  validation_result=CONFIRMED reason=validation_positive_profile
- context: ETHUSDT BUY aurora LOW_VOLATILITY 0.75..1.00
  train_count=4 validation_count=4 verdict=MIXED_CONTEXT recommendation=monitor
  train_net_score=-0.672024 validation_net_score=30.725480
  train_outcomes={"POLICY_PROTECTED": 2, "POLICY_TOO_STRICT": 2} validation_outcomes={"POLICY_PROTECTED": 4}
  validation_result=CONTRADICTED reason=validation_became_directional
- context: ETHUSDT BUY aurora TREND_UP 0.00..0.25
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=39.718993
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: ETHUSDT SELL aurora LOW_VOLATILITY 0.00..0.25
  train_count=3 validation_count=3 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  train_net_score=18.898485 validation_net_score=11.185508
  train_outcomes={"POLICY_PROTECTED": 2, "POLICY_TOO_STRICT": 1} validation_outcomes={"POLICY_PROTECTED": 1, "POLICY_TOO_STRICT": 2}
  validation_result=CONFIRMED reason=validation_positive_profile
- context: ETHUSDT SELL aurora LOW_VOLATILITY 0.25..0.50
  train_count=26 validation_count=27 verdict=POLICY_TOO_STRICT_CANDIDATE recommendation=review_policy_thresholds
  train_net_score=-6.998836 validation_net_score=-4.383504
  train_outcomes={"POLICY_PROTECTED": 8, "POLICY_TOO_STRICT": 18} validation_outcomes={"POLICY_PROTECTED": 8, "POLICY_TOO_STRICT": 19}
  validation_result=CONFIRMED reason=validation_high_missed_positive_rate
- context: ETHUSDT SELL aurora LOW_VOLATILITY 0.50..0.75
  train_count=14 validation_count=15 verdict=POLICY_TOO_STRICT_CANDIDATE recommendation=review_policy_thresholds
  train_net_score=-20.332150 validation_net_score=6.544638
  train_outcomes={"POLICY_PROTECTED": 5, "POLICY_TOO_STRICT": 9} validation_outcomes={"POLICY_PROTECTED": 9, "POLICY_TOO_STRICT": 6}
  validation_result=CONTRADICTED reason=validation_missing_missed_positive_pattern
- context: ETHUSDT SELL aurora LOW_VOLATILITY 0.75..1.00
  train_count=7 validation_count=8 verdict=MIXED_CONTEXT recommendation=monitor
  train_net_score=-4.815017 validation_net_score=0.304782
  train_outcomes={"POLICY_PROTECTED": 3, "POLICY_TOO_STRICT": 4} validation_outcomes={"GOOD_DECISION": 1, "POLICY_PROTECTED": 3, "POLICY_TOO_STRICT": 4}
  validation_result=CONFIRMED reason=validation_remained_inconclusive
- context: ETHUSDT SELL aurora TREND_DOWN 0.00..0.25
  train_count=1 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=27.628725 validation_net_score=23.565515
  train_outcomes={"GOOD_DECISION": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: ETHUSDT SELL aurora TREND_DOWN 0.25..0.50
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=28.071938
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: XRPUSDT BUY aurora LOW_VOLATILITY 0.00..0.25
  train_count=1 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=-29.060029 validation_net_score=35.256365
  train_outcomes={"POLICY_TOO_STRICT": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: XRPUSDT BUY aurora LOW_VOLATILITY 0.25..0.50
  train_count=3 validation_count=4 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  train_net_score=11.758590 validation_net_score=8.163019
  train_outcomes={"POLICY_PROTECTED": 2, "POLICY_TOO_STRICT": 1} validation_outcomes={"POLICY_PROTECTED": 3, "POLICY_TOO_STRICT": 1}
  validation_result=CONFIRMED reason=validation_positive_profile
- context: XRPUSDT BUY aurora LOW_VOLATILITY 0.50..0.75
  train_count=2 validation_count=3 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  train_net_score=6.000884 validation_net_score=44.733583
  train_outcomes={"POLICY_PROTECTED": 2} validation_outcomes={"POLICY_PROTECTED": 3}
  validation_result=CONFIRMED reason=validation_positive_profile
- context: XRPUSDT BUY aurora TREND_UP 0.25..0.50
  train_count=1 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=-38.299892 validation_net_score=-28.991510
  train_outcomes={"CLEAN_LOSS": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: XRPUSDT SELL aurora LOW_VOLATILITY 0.00..0.25
  train_count=1 validation_count=2 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=-26.611581 validation_net_score=-70.512512
  train_outcomes={"POLICY_TOO_STRICT": 1} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: XRPUSDT SELL aurora LOW_VOLATILITY 0.25..0.50
  train_count=9 validation_count=9 verdict=POLICY_TOO_STRICT_CANDIDATE recommendation=review_policy_thresholds
  train_net_score=-10.194900 validation_net_score=-3.059604
  train_outcomes={"POLICY_PROTECTED": 3, "POLICY_TOO_STRICT": 6} validation_outcomes={"POLICY_PROTECTED": 6, "POLICY_TOO_STRICT": 3}
  validation_result=CONTRADICTED reason=validation_missing_missed_positive_pattern
- context: XRPUSDT SELL aurora LOW_VOLATILITY 0.50..0.75
  train_count=7 validation_count=7 verdict=MIXED_CONTEXT recommendation=monitor
  train_net_score=-6.918364 validation_net_score=12.610443
  train_outcomes={"POLICY_PROTECTED": 4, "POLICY_TOO_STRICT": 3} validation_outcomes={"POLICY_PROTECTED": 6, "POLICY_TOO_STRICT": 1}
  validation_result=CONTRADICTED reason=validation_became_directional
- context: XRPUSDT SELL aurora LOW_VOLATILITY 0.75..1.00
  train_count=2 validation_count=2 verdict=MIXED_CONTEXT recommendation=monitor
  train_net_score=-3.843237 validation_net_score=8.536337
  train_outcomes={"POLICY_PROTECTED": 1, "POLICY_TOO_STRICT": 1} validation_outcomes={"GOOD_DECISION": 1, "POLICY_PROTECTED": 1}
  validation_result=CONTRADICTED reason=validation_became_directional
- context: XRPUSDT SELL aurora MEAN_REVERSION 0.00..0.25
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=30.225685
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: XRPUSDT SELL aurora MEAN_REVERSION 0.25..0.50
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=10.768610
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold
- context: XRPUSDT SELL aurora TREND_DOWN 0.25..0.50
  train_count=0 validation_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  train_net_score=0.000000 validation_net_score=70.770922
  train_outcomes={} validation_outcomes={}
  validation_result=SKIPPED_LOW_SUPPORT reason=train_or_validation_support_below_threshold

## Top Toxic Candidates
- none

## Top Favorable Candidates
- BTCUSDT SELL MEAN_REVERSION 0.25..0.50 train_count=2 validation_count=3 train_score=31.105787 validation_result=CONFIRMED
- ETHUSDT SELL LOW_VOLATILITY 0.00..0.25 train_count=3 validation_count=3 train_score=18.898485 validation_result=CONFIRMED
- XRPUSDT BUY LOW_VOLATILITY 0.25..0.50 train_count=3 validation_count=4 train_score=11.758590 validation_result=CONFIRMED
- BTCUSDT BUY LOW_VOLATILITY 0.50..0.75 train_count=2 validation_count=3 train_score=11.367413 validation_result=CONFIRMED
- ETHUSDT BUY LOW_VOLATILITY 0.50..0.75 train_count=8 validation_count=8 train_score=6.110600 validation_result=CONFIRMED

## Top Policy-Too-Strict Candidates
- BTCUSDT SELL LOW_VOLATILITY 0.75..1.00 train_count=5 validation_count=5 train_score=1.000000 validation_result=CONTRADICTED
- ETHUSDT BUY LOW_VOLATILITY 0.00..0.25 train_count=2 validation_count=2 train_score=1.000000 validation_result=CONTRADICTED
- BTCUSDT SELL LOW_VOLATILITY 0.25..0.50 train_count=17 validation_count=18 train_score=0.705882 validation_result=CONFIRMED
- ETHUSDT SELL LOW_VOLATILITY 0.25..0.50 train_count=26 validation_count=27 train_score=0.692308 validation_result=CONFIRMED
- BTCUSDT SELL LOW_VOLATILITY 0.00..0.25 train_count=9 validation_count=9 train_score=0.666667 validation_result=CONTRADICTED

## False Positive Verdicts
- BTCUSDT SELL LOW_VOLATILITY 0.00..0.25 verdict=POLICY_TOO_STRICT_CANDIDATE validation_result=CONTRADICTED reason=validation_missing_missed_positive_pattern
- BTCUSDT SELL LOW_VOLATILITY 0.75..1.00 verdict=POLICY_TOO_STRICT_CANDIDATE validation_result=CONTRADICTED reason=validation_missing_missed_positive_pattern
- ETHUSDT BUY LOW_VOLATILITY 0.00..0.25 verdict=POLICY_TOO_STRICT_CANDIDATE validation_result=CONTRADICTED reason=validation_missing_missed_positive_pattern
- ETHUSDT SELL LOW_VOLATILITY 0.50..0.75 verdict=POLICY_TOO_STRICT_CANDIDATE validation_result=CONTRADICTED reason=validation_missing_missed_positive_pattern
- XRPUSDT SELL LOW_VOLATILITY 0.25..0.50 verdict=POLICY_TOO_STRICT_CANDIDATE validation_result=CONTRADICTED reason=validation_missing_missed_positive_pattern

## False Negative Verdicts
- ETHUSDT BUY LOW_VOLATILITY 0.75..1.00 verdict=MIXED_CONTEXT validation_result=CONTRADICTED reason=validation_became_directional
- XRPUSDT SELL LOW_VOLATILITY 0.50..0.75 verdict=MIXED_CONTEXT validation_result=CONTRADICTED reason=validation_became_directional
- XRPUSDT SELL LOW_VOLATILITY 0.75..1.00 verdict=MIXED_CONTEXT validation_result=CONTRADICTED reason=validation_became_directional

## Residual Uncertainty
- The SAF file is a single frozen slice, so chronological validation is within-slice only and not a fresh forward period.
- Context support is sparse for many symbol/side/regime buckets, so skipped contexts materially limit confidence.
- `POLICY_TOO_STRICT` evidence is strongest where the adapter already reconstructed rejected offline outcomes; missing-reference rejects remain out of scope.
- `NEUTRAL_SIGNAL` rows are retained for chronology and support accounting but do not directly prove favorable or toxic predictive value.

