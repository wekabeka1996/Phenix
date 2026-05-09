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
- C:\Users\user\Music\Phenix\logs\frozen\nrr062_fresh_capture_20260507_103909\logs\order_log_v1.jsonl
- C:\Users\user\Music\Phenix\logs\frozen\nrr062_fresh_capture_20260507_103909\data\recorder

- log lines read: 1462
- order_log: 1462

## Accepted Reducer Results
- accepted close events found: 41
- accepted contracts completed: 41

## Rejected Evaluator Results
- rejected events found: 239
- rejected contracts evaluated: 112

## MFE/MAE Reconstruction Results
- MFE/MAE computed count: 37
- MFE/MAE missing count: 4

## SemaAtom Encoding Results
- atoms created: 153
- atoms discarded: 0
- encoding errors: 0

## Memory Verdicts by Context
- symbol: BNBUSDT
  side=BUY strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.00..0.25
  atom_count=2 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"ACCEPTED_WIN": 1, "BAD_EXIT": 1}
  avg_reward=18.312857 avg_threat=23.267319 net_score=-4.954462
  avg_surprise=17.379862 avg_importance=41.580177
- symbol: BNBUSDT
  side=BUY strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.25..0.50
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"ACCEPTED_WIN": 1}
  avg_reward=43.031891 avg_threat=27.204607 net_score=15.827284
  avg_surprise=4.094504 avg_importance=70.236499
- symbol: BNBUSDT
  side=BUY strategy_id=aurora regime=TREND_UP confidence_bucket=0.00..0.25
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"ACCEPTED_LOSS": 1}
  avg_reward=0.0 avg_threat=0.0 net_score=0.0
  avg_surprise=0.0 avg_importance=0.0
- symbol: BNBUSDT
  side=BUY strategy_id=aurora regime=TREND_UP confidence_bucket=0.25..0.50
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"ACCEPTED_WIN": 1}
  avg_reward=86.556535 avg_threat=27.038907 net_score=59.517628
  avg_surprise=0.625009 avg_importance=113.595443
- symbol: BNBUSDT
  side=SELL strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.00..0.25
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"ACCEPTED_WIN": 1}
  avg_reward=0.0 avg_threat=1.541283 net_score=-1.541283
  avg_surprise=4.469721 avg_importance=1.541283
- symbol: BNBUSDT
  side=SELL strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.25..0.50
  atom_count=3 verdict=TOXIC_CONTEXT recommendation=avoid_or_review
  outcome_stats={"ACCEPTED_LOSS": 1, "ACCEPTED_WIN": 1, "BAD_EXIT": 1}
  avg_reward=5.088482 avg_threat=37.575313 net_score=-32.486831
  avg_surprise=15.729511 avg_importance=42.663795
- symbol: BNBUSDT
  side=SELL strategy_id=aurora regime=TREND_DOWN confidence_bucket=0.00..0.25
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"ACCEPTED_LOSS": 1}
  avg_reward=0.0 avg_threat=0.0 net_score=0.0
  avg_surprise=32.86679 avg_importance=0.031006
- symbol: BNBUSDT
  side=SELL strategy_id=aurora regime=TREND_DOWN confidence_bucket=0.25..0.50
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"BAD_EXIT": 1}
  avg_reward=0.0 avg_threat=3.797213 net_score=-3.797213
  avg_surprise=40.52944 avg_importance=3.797213
- symbol: BTCUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.00..0.25
  atom_count=3 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 2, "REJECT_MISSED_POSITIVE": 1}
  avg_reward=17.725454 avg_threat=16.167138 net_score=1.558316
  avg_surprise=33.892592 avg_importance=33.892592
- symbol: BTCUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.25..0.50
  atom_count=21 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 5, "REJECT_MISSED_POSITIVE": 16}
  avg_reward=2.915779 avg_threat=16.958836 net_score=-14.043057
  avg_surprise=19.874615 avg_importance=19.874615
- symbol: BTCUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.50..0.75
  atom_count=9 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 7, "REJECT_MISSED_POSITIVE": 2}
  avg_reward=12.658462 avg_threat=6.150529 net_score=6.507933
  avg_surprise=18.808992 avg_importance=18.808992
- symbol: BTCUSDT
  side=BUY strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.00..0.25
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"BAD_EXIT": 1}
  avg_reward=0.0 avg_threat=18.670379 net_score=-18.670379
  avg_surprise=12.098208 avg_importance=18.670379
- symbol: BTCUSDT
  side=BUY strategy_id=aurora regime=TREND_UP confidence_bucket=0.00..0.25
  atom_count=2 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"ACCEPTED_WIN": 2}
  avg_reward=19.898888 avg_threat=6.311906 net_score=13.586982
  avg_surprise=27.072669 avg_importance=26.210794
- symbol: BTCUSDT
  side=BUY strategy_id=aurora regime=TREND_UP confidence_bucket=0.25..0.50
  atom_count=2 verdict=TOXIC_CONTEXT recommendation=avoid_or_review
  outcome_stats={"ACCEPTED_WIN": 2}
  avg_reward=0.0 avg_threat=28.499484 net_score=-28.499484
  avg_surprise=5.411067 avg_importance=28.499484
- symbol: BTCUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.25..0.50
  atom_count=16 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 9, "REJECT_MISSED_POSITIVE": 7}
  avg_reward=8.743457 avg_threat=7.570995 net_score=1.172462
  avg_surprise=16.314452 avg_importance=16.314452
- symbol: BTCUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.50..0.75
  atom_count=3 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 2, "REJECT_MISSED_POSITIVE": 1}
  avg_reward=18.120916 avg_threat=0.906774 net_score=17.214142
  avg_surprise=19.027691 avg_importance=19.027691
- symbol: BTCUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.75..1.00
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"REJECT_CORRECT_BLOCK": 1}
  avg_reward=7.806895 avg_threat=0.0 net_score=7.806895
  avg_surprise=7.806895 avg_importance=7.806895
- symbol: BTCUSDT
  side=SELL strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.00..0.25
  atom_count=3 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"ACCEPTED_WIN": 2, "BAD_EXIT": 1}
  avg_reward=22.145513 avg_threat=17.257309 net_score=4.888205
  avg_surprise=10.459989 avg_importance=39.402823
- symbol: BTCUSDT
  side=SELL strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.25..0.50
  atom_count=5 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"ACCEPTED_WIN": 5}
  avg_reward=15.218492 avg_threat=18.896291 net_score=-3.677799
  avg_surprise=7.157615 avg_importance=34.114783
- symbol: BTCUSDT
  side=SELL strategy_id=aurora regime=TREND_DOWN confidence_bucket=0.25..0.50
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"BAD_EXIT": 1}
  avg_reward=0.0 avg_threat=22.219186 net_score=-22.219186
  avg_surprise=34.972137 avg_importance=22.219186
- symbol: ETHUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.00..0.25
  atom_count=2 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 1, "REJECT_MISSED_POSITIVE": 1}
  avg_reward=6.858316 avg_threat=15.589662 net_score=-8.731345
  avg_surprise=22.447979 avg_importance=22.447979
- symbol: ETHUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.25..0.50
  atom_count=6 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  outcome_stats={"REJECT_CORRECT_BLOCK": 5, "REJECT_MISSED_POSITIVE": 1}
  avg_reward=32.681109 avg_threat=0.082078 net_score=32.599031
  avg_surprise=32.763187 avg_importance=32.763187
- symbol: ETHUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.50..0.75
  atom_count=3 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 1, "REJECT_MISSED_POSITIVE": 2}
  avg_reward=8.109713 avg_threat=24.308285 net_score=-16.198572
  avg_surprise=32.417998 avg_importance=32.417998
- symbol: ETHUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.75..1.00
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"REJECT_MISSED_POSITIVE": 1}
  avg_reward=0.0 avg_threat=72.065533 net_score=-72.065533
  avg_surprise=72.065533 avg_importance=72.065533
- symbol: ETHUSDT
  side=BUY strategy_id=aurora regime=TREND_UP confidence_bucket=0.00..0.25
  atom_count=2 verdict=TOXIC_CONTEXT recommendation=avoid_or_review
  outcome_stats={"ACCEPTED_LOSS": 2}
  avg_reward=0.0 avg_threat=26.279158 net_score=-26.279158
  avg_surprise=28.969729 avg_importance=26.279158
- symbol: ETHUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.00..0.25
  atom_count=7 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 2, "REJECT_MISSED_POSITIVE": 5}
  avg_reward=0.556361 avg_threat=12.712866 net_score=-12.156505
  avg_surprise=13.269227 avg_importance=13.269227
- symbol: ETHUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.25..0.50
  atom_count=19 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 11, "REJECT_MISSED_POSITIVE": 8}
  avg_reward=9.250102 avg_threat=9.642553 net_score=-0.392451
  avg_surprise=18.892655 avg_importance=18.892655
- symbol: ETHUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.50..0.75
  atom_count=10 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 6, "REJECT_MISSED_POSITIVE": 4}
  avg_reward=11.025395 avg_threat=1.432724 net_score=9.592671
  avg_surprise=12.458119 avg_importance=12.458119
- symbol: ETHUSDT
  side=SELL strategy_id=aurora regime=TREND_DOWN confidence_bucket=0.00..0.25
  atom_count=6 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"ACCEPTED_LOSS": 5, "ACCEPTED_WIN": 1}
  avg_reward=6.346629 avg_threat=18.882311 net_score=-12.535683
  avg_surprise=9.167333 avg_importance=25.22894
- symbol: XRPUSDT
  side=BUY strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.25..0.50
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"REJECT_MISSED_POSITIVE": 1}
  avg_reward=0.0 avg_threat=13.564463 net_score=-13.564463
  avg_surprise=13.564463 avg_importance=13.564463
- symbol: XRPUSDT
  side=BUY strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.25..0.50
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"BAD_EXIT": 1}
  avg_reward=0.0 avg_threat=34.244157 net_score=-34.244157
  avg_surprise=10.237944 avg_importance=34.244157
- symbol: XRPUSDT
  side=BUY strategy_id=aurora regime=TREND_UP confidence_bucket=0.25..0.50
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"ACCEPTED_WIN": 1}
  avg_reward=74.655314 avg_threat=25.761199 net_score=48.894114
  avg_surprise=13.693161 avg_importance=100.416513
- symbol: XRPUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.00..0.25
  atom_count=2 verdict=FAVORABLE_CONTEXT recommendation=retain_or_promote
  outcome_stats={"REJECT_CORRECT_BLOCK": 2}
  avg_reward=38.112156 avg_threat=0.0 net_score=38.112156
  avg_surprise=38.112156 avg_importance=38.112156
- symbol: XRPUSDT
  side=SELL strategy_id=aurora regime=LOW_VOLATILITY confidence_bucket=0.25..0.50
  atom_count=8 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"REJECT_CORRECT_BLOCK": 6, "REJECT_MISSED_POSITIVE": 2}
  avg_reward=8.211948 avg_threat=3.705812 net_score=4.506136
  avg_surprise=11.917759 avg_importance=11.917759
- symbol: XRPUSDT
  side=SELL strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.00..0.25
  atom_count=1 verdict=LOW_SUPPORT recommendation=collect_more_atoms
  outcome_stats={"ACCEPTED_WIN": 1}
  avg_reward=43.593156 avg_threat=6.478022 net_score=37.115134
  avg_surprise=18.335924 avg_importance=50.071178
- symbol: XRPUSDT
  side=SELL strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.25..0.50
  atom_count=3 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"ACCEPTED_WIN": 2, "BAD_EXIT": 1}
  avg_reward=12.070091 avg_threat=19.869993 net_score=-7.799902
  avg_surprise=7.188631 avg_importance=31.940083
- symbol: XRPUSDT
  side=SELL strategy_id=aurora regime=MEAN_REVERSION confidence_bucket=0.50..0.75
  atom_count=2 verdict=MIXED_CONTEXT recommendation=monitor
  outcome_stats={"ACCEPTED_WIN": 2}
  avg_reward=40.111639 avg_threat=21.836634 net_score=18.275005
  avg_surprise=2.101841 avg_importance=61.948273

## Incomplete Buckets
- incomplete accepted buckets: {}
- incomplete rejected buckets: {"incomplete_rejected_missing_reference_price": 127}

## Missing Field Histogram
- {}

## Error Samples
- none

## Residual Risks
- Accepted MFE/MAE is replayed from recorder bars and depends on recorder coverage for the chosen symbol/time window.
- Rejected reference price extraction is strongest for low-vol rejects with nested economics metadata; other reject families can fall into incomplete buckets by design.
- Memory verdicts are heuristic aggregations over encoded atoms and do not claim forward predictive validity.

## Next Recommended Step
- SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION

