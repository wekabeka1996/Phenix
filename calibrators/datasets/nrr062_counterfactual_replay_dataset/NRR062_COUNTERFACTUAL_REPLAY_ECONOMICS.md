# NRR062_COUNTERFACTUAL_REPLAY_ECONOMICS

| Metric | Value | Notes |
| --- | --- | --- |
| Total Replay Rows | 153 | all results including ambiguous and invalid |
| Valid Replay Rows | 153 | TP, SL, timeout only |
| Estimated Gross PnL Quote | 966.964678 | quote-unit proxy using quantity when present |
| Estimated Net PnL Quote | 391.047687 | gross minus fee and slippage proxies |
| Estimated Fees Quote | 460.733593 | round-trip fee proxy |
| Estimated Win Rate | 51.633987 | valid rows only |
| Profit Factor | 1.412076 | valid rows only |

## by_symbol
| Segment | Rows | TP | SL | Timeout | Net PnL | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| BTCUSDT | 47 | 12 | 1 | 34 | 341.796535 | segment summary |
| ETHUSDT | 76 | 15 | 7 | 54 | 44.542274 | segment summary |
| XRPUSDT | 30 | 6 | 5 | 19 | 4.708877 | segment summary |

## by_side
| Segment | Rows | TP | SL | Timeout | Net PnL | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| BUY | 39 | 0 | 7 | 32 | -452.718237 | segment summary |
| SELL | 114 | 33 | 6 | 75 | 843.765924 | segment summary |

## by_direction_confidence_bucket
| Segment | Rows | TP | SL | Timeout | Net PnL | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 0.01-0.05 | 23 | 0 | 2 | 21 | -161.00002 | segment summary |
| <0.01 | 130 | 33 | 11 | 86 | 552.047707 | segment summary |

## by_regime_confidence_bucket
| Segment | Rows | TP | SL | Timeout | Net PnL | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 0.15-0.25 | 12 | 2 | 2 | 8 | -26.035105 | segment summary |
| 0.25-0.35 | 31 | 6 | 7 | 18 | -161.274377 | segment summary |
| 0.35-0.39 | 7 | 0 | 0 | 7 | -25.323704 | segment summary |
| >=0.39 | 103 | 25 | 4 | 74 | 603.680872 | segment summary |

## by_violation_pattern
| Segment | Rows | TP | SL | Timeout | Net PnL | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| direction_confidence_below_threshold | 101 | 25 | 4 | 72 | 585.82653 | segment summary |
| regime_confidence_below_threshold+direction_confidence_below_threshold | 52 | 8 | 9 | 35 | -194.778843 | segment summary |
