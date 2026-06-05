# SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT

## Verdict
SEMA_ATOM_POC_02_STATUS:
READ_ONLY_REAL_LOG_RUN_COMPLETED

## Scope
- Read-only real-log adapter run from Aurora log surfaces to SemaAtom memory artifacts.
- No live trading logic, gates, or runtime behavior modified.

## Files Created/Changed
- aurora_real_logs_v02.saf.jsonl
- SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md

## Inputs Read
- logs\frozen\nrr062_fresh_capture_20260516_101448\logs\order_log_v1.jsonl
- logs\frozen\nrr062_fresh_capture_20260516_101448\data\recorder

- log lines read: 1927
- order_log: 1927

## Accepted Reducer Results
- accepted close events found: 65
- accepted contracts completed: 34

## Rejected Evaluator Results
- rejected events found: 468
- rejected contracts evaluated: 303
- reference_price_source_level_histogram: {"0_explicit_low_vol_cost_floor": 303, "5_missing": 165}

## MFE/MAE Reconstruction Results
- MFE/MAE computed count: 58
- MFE/MAE missing count: 7

## SemaAtom Encoding Results
- atoms created: 337
- atoms discarded: 31
- encoding errors: 0

## Memory Verdicts by Context
- symbol: BNBUSDT
  side=BUY strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.25..0.50
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"ACCEPTED_WIN": 1}
  avg_reward=40.155792 avg_threat=7.246158 net_score=32.909634
  avg_surprise=0.301923 avg_importance=47.40195
- symbol: BNBUSDT
  side=BUY strategy_id=aurora regime=TREND_UP confidence_bucket=0.25..0.50
  atom_count=3 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"ACCEPTED_LOSS": 2, "ACCEPTED_WIN": 1}
  avg_reward=32.013047 avg_threat=30.714542 net_score=1.298505
  avg_surprise=47.483475 avg_importance=87.695097
- symbol: BNBUSDT
  side=SELL strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.25..0.50
  atom_count=2 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"ACCEPTED_LOSS": 1, "ACCEPTED_WIN": 1}
  avg_reward=14.853378 avg_threat=29.146001 net_score=-14.292624
  avg_surprise=0.220594 avg_importance=45.129851
- symbol: BNBUSDT
  side=SELL strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.50..0.75
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"ACCEPTED_WIN": 1}
  avg_reward=28.185573 avg_threat=14.997136 net_score=13.188436
  avg_surprise=0.979712 avg_importance=43.182709
- symbol: BNBUSDT
  side=SELL strategy_id=aurora regime=TREND_DOWN confidence_bucket=0.00..0.25
  atom_count=2 verdict=TOXIC_CONTEXT recommendation=avoid_or_review
  outcome_stats={"ACCEPTED_LOSS": 2}
  avg_reward=0.0 avg_threat=26.406716 net_score=-26.406716
  avg_surprise=36.7132 avg_importance=57.397983
- symbol: BTCUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.00..0.25
  atom_count=3 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 2, "REJECT_MISSED_POSITIVE": 1}
  avg_reward=16.732227 avg_threat=2.068155 net_score=14.664072
  avg_surprise=18.800382 avg_importance=18.800382
- symbol: BTCUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.25..0.50
  atom_count=12 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 9, "REJECT_MISSED_POSITIVE": 3}
  avg_reward=8.35686 avg_threat=3.495947 net_score=4.860914
  avg_surprise=11.852807 avg_importance=11.852807
- symbol: BTCUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.50..0.75
  atom_count=5 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  outcome_stats={"REJECT_CORRECT_BLOCK": 5}
  avg_reward=21.714157 avg_threat=0.0 net_score=21.714157
  avg_surprise=21.714157 avg_importance=21.714157
- symbol: BTCUSDT
  side=BUY strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.50..0.75
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"ACCEPTED_WIN": 1}
  avg_reward=28.248062 avg_threat=26.436812 net_score=1.81125
  avg_surprise=9.515267 avg_importance=54.684873
- symbol: BTCUSDT
  side=BUY strategy_id=aurora regime=TREND_UP confidence_bucket=0.00..0.25
  atom_count=2 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  outcome_stats={"ACCEPTED_WIN": 2}
  avg_reward=51.943134 avg_threat=16.185996 net_score=35.757137
  avg_surprise=42.343643 avg_importance=68.12913
- symbol: BTCUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.00..0.25
  atom_count=18 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 8, "REJECT_MISSED_POSITIVE": 10}
  avg_reward=6.669209 avg_threat=6.26922 net_score=0.399988
  avg_surprise=12.938429 avg_importance=12.938429
- symbol: BTCUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.25..0.50
  atom_count=35 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"ACCEPTED_WIN": 2, "REJECT_CORRECT_BLOCK": 12, "REJECT_MISSED_POSITIVE": 21}
  avg_reward=8.13588 avg_threat=8.897842 net_score=-0.761962
  avg_surprise=13.2988 avg_importance=17.033723
- symbol: BTCUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.50..0.75
  atom_count=19 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 7, "REJECT_MISSED_POSITIVE": 12}
  avg_reward=5.48209 avg_threat=8.829666 net_score=-3.347576
  avg_surprise=14.311755 avg_importance=14.311755
- symbol: BTCUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.75..1.00
  atom_count=10 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 5, "REJECT_MISSED_POSITIVE": 5}
  avg_reward=5.42435 avg_threat=16.952366 net_score=-11.528015
  avg_surprise=22.376716 avg_importance=22.376716
- symbol: BTCUSDT
  side=SELL strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.00..0.25
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"ACCEPTED_WIN": 1}
  avg_reward=20.483131 avg_threat=0.061511 net_score=20.42162
  avg_surprise=0.135324 avg_importance=20.544642
- symbol: BTCUSDT
  side=SELL strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.25..0.50
  atom_count=5 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  outcome_stats={"ACCEPTED_LOSS": 1, "ACCEPTED_WIN": 4}
  avg_reward=27.431127 avg_threat=5.328364 net_score=22.102763
  avg_surprise=2.665432 avg_importance=33.094477
- symbol: BTCUSDT
  side=SELL strategy_id=aurora regime=TREND_DOWN confidence_bucket=0.00..0.25
  atom_count=2 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  outcome_stats={"ACCEPTED_LOSS": 1, "ACCEPTED_WIN": 1}
  avg_reward=38.716116 avg_threat=12.462594 net_score=26.253522
  avg_surprise=13.53713 avg_importance=52.053999
- symbol: DOGEUSDT
  side=SELL strategy_id=aurora regime=TREND_DOWN confidence_bucket=0.00..0.25
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"ACCEPTED_WIN": 1}
  avg_reward=99.894848 avg_threat=2.628812 net_score=97.266036
  avg_surprise=53.452506 avg_importance=102.523659
- symbol: ETHUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.00..0.25
  atom_count=4 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 2, "REJECT_MISSED_POSITIVE": 2}
  avg_reward=12.621454 avg_threat=2.653427 net_score=9.968027
  avg_surprise=15.274881 avg_importance=15.274881
- symbol: ETHUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.25..0.50
  atom_count=21 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 16, "REJECT_MISSED_POSITIVE": 5}
  avg_reward=11.762348 avg_threat=4.722488 net_score=7.03986
  avg_surprise=16.484836 avg_importance=16.484836
- symbol: ETHUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.50..0.75
  atom_count=16 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 12, "REJECT_MISSED_POSITIVE": 4}
  avg_reward=9.127004 avg_threat=3.515065 net_score=5.611939
  avg_surprise=12.642068 avg_importance=12.642068
- symbol: ETHUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.75..1.00
  atom_count=8 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 6, "REJECT_MISSED_POSITIVE": 2}
  avg_reward=16.241845 avg_threat=1.215117 net_score=15.026728
  avg_surprise=17.456962 avg_importance=17.456962
- symbol: ETHUSDT
  side=BUY strategy_id=aurora regime=TREND_UP confidence_bucket=0.00..0.25
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"ACCEPTED_WIN": 1}
  avg_reward=57.610036 avg_threat=17.891044 net_score=39.718993
  avg_surprise=3.586957 avg_importance=75.50108
- symbol: ETHUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.00..0.25
  atom_count=6 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 3, "REJECT_MISSED_POSITIVE": 3}
  avg_reward=18.842859 avg_threat=3.800863 net_score=15.041996
  avg_surprise=22.643721 avg_importance=22.643721
- symbol: ETHUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.25..0.50
  atom_count=53 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 16, "REJECT_MISSED_POSITIVE": 37}
  avg_reward=6.990958 avg_threat=12.657455 net_score=-5.666497
  avg_surprise=19.648413 avg_importance=19.648413
- symbol: ETHUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.50..0.75
  atom_count=29 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 14, "REJECT_MISSED_POSITIVE": 15}
  avg_reward=7.552412 avg_threat=13.982774 net_score=-6.430363
  avg_surprise=21.535186 avg_importance=21.535186
- symbol: ETHUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.75..1.00
  atom_count=15 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"ACCEPTED_WIN": 1, "REJECT_CORRECT_BLOCK": 6, "REJECT_MISSED_POSITIVE": 8}
  avg_reward=10.472745 avg_threat=12.557203 net_score=-2.084458
  avg_surprise=17.153548 avg_importance=23.029948
- symbol: ETHUSDT
  side=SELL strategy_id=aurora regime=TREND_DOWN confidence_bucket=0.00..0.25
  atom_count=2 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  outcome_stats={"ACCEPTED_WIN": 2}
  avg_reward=31.418653 avg_threat=5.821532 net_score=25.59712
  avg_surprise=3.13186 avg_importance=37.240185
- symbol: ETHUSDT
  side=SELL strategy_id=aurora regime=TREND_DOWN confidence_bucket=0.25..0.50
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"ACCEPTED_WIN": 1}
  avg_reward=29.261801 avg_threat=1.189862 net_score=28.071938
  avg_surprise=0.176276 avg_importance=30.451663
- symbol: XRPUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.00..0.25
  atom_count=2 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 1, "REJECT_MISSED_POSITIVE": 1}
  avg_reward=17.628183 avg_threat=14.530015 net_score=3.098168
  avg_surprise=32.158197 avg_importance=32.158197
- symbol: XRPUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.25..0.50
  atom_count=7 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 5, "REJECT_MISSED_POSITIVE": 2}
  avg_reward=12.555289 avg_threat=2.851311 net_score=9.703978
  avg_surprise=15.4066 avg_importance=15.4066
- symbol: XRPUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.50..0.75
  atom_count=5 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  outcome_stats={"REJECT_CORRECT_BLOCK": 5}
  avg_reward=29.240503 avg_threat=0.0 net_score=29.240503
  avg_surprise=29.240503 avg_importance=29.240503
- symbol: XRPUSDT
  side=BUY strategy_id=aurora regime=TREND_UP confidence_bucket=0.25..0.50
  atom_count=2 verdict=TOXIC_CONTEXT recommendation=avoid_or_review
  outcome_stats={"ACCEPTED_LOSS": 2}
  avg_reward=0.0 avg_threat=33.645701 net_score=-33.645701
  avg_surprise=84.207245 avg_importance=76.391032
- symbol: XRPUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.00..0.25
  atom_count=3 verdict=TOXIC_CONTEXT recommendation=avoid_or_review
  outcome_stats={"REJECT_MISSED_POSITIVE": 3}
  avg_reward=0.0 avg_threat=55.878868 net_score=-55.878868
  avg_surprise=55.878868 avg_importance=55.878868
- symbol: XRPUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.25..0.50
  atom_count=18 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 9, "REJECT_MISSED_POSITIVE": 9}
  avg_reward=12.310889 avg_threat=18.938142 net_score=-6.627252
  avg_surprise=31.249031 avg_importance=31.249031
- symbol: XRPUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.50..0.75
  atom_count=14 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 10, "REJECT_MISSED_POSITIVE": 4}
  avg_reward=14.588412 avg_threat=11.742373 net_score=2.846039
  avg_surprise=26.330786 avg_importance=26.330786
- symbol: XRPUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.75..1.00
  atom_count=4 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"ACCEPTED_WIN": 1, "REJECT_CORRECT_BLOCK": 2, "REJECT_MISSED_POSITIVE": 1}
  avg_reward=12.063163 avg_threat=9.716613 net_score=2.34655
  avg_surprise=7.313797 avg_importance=21.779776
- symbol: XRPUSDT
  side=SELL strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.00..0.25
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"ACCEPTED_WIN": 1}
  avg_reward=32.912413 avg_threat=2.686728 net_score=30.225685
  avg_surprise=3.358409 avg_importance=35.59914
- symbol: XRPUSDT
  side=SELL strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.25..0.50
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"ACCEPTED_WIN": 1}
  avg_reward=34.324943 avg_threat=23.556333 net_score=10.76861
  avg_surprise=0.0 avg_importance=57.881276
- symbol: XRPUSDT
  side=SELL strategy_id=aurora regime=TREND_DOWN confidence_bucket=0.25..0.50
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"ACCEPTED_WIN": 1}
  avg_reward=91.383812 avg_threat=20.61289 net_score=70.770922
  avg_surprise=4.809674 avg_importance=111.996702

## Incomplete Buckets
- incomplete accepted buckets: {"accepted_missing_entry_price": 5, "accepted_missing_regime": 31}
- incomplete rejected buckets: {"incomplete_rejected_missing_reference_price": 165}

## Missing Field Histogram
- {"entry_price": 5, "entry_ts_ms": 5, "regime": 31, "regime_confidence": 31}

## Error Samples
- none

## Residual Risks
- Accepted MFE/MAE is replayed from recorder bars and depends on recorder coverage for the chosen symbol/time window.
- Rejected reference price extraction is strongest for low-vol rejects with nested economics metadata; other reject families can fall into incomplete buckets by design.
- Memory verdicts are heuristic aggregations over encoded atoms and do not claim forward predictive validity.

## Next Recommended Step
- SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION

