# NRR062_COUNTERFACTUAL_REPLAY_ECONOMICS

| Metric | Value | Notes |
| --- | --- | --- |
| Total Replay Rows | 227 | all results including ambiguous and invalid |
| Valid Replay Rows | 226 | TP, SL, timeout only |
| Estimated Gross PnL Quote | 114.063207 | quote-unit proxy using quantity when present |
| Estimated Net PnL Quote | -742.567497 | gross minus fee and slippage proxies |
| Estimated Fees Quote | 685.304563 | round-trip fee proxy |
| Estimated Win Rate | 38.053097 | valid rows only |
| Profit Factor | 0.65132 | valid rows only |

## by_symbol
| Segment | Rows | TP | SL | Timeout | Net PnL | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| BTCUSDT | 76 | 12 | 8 | 56 | -57.189128 | segment summary |
| ETHUSDT | 108 | 15 | 12 | 80 | -425.157888 | segment summary |
| XRPUSDT | 43 | 6 | 14 | 23 | -260.220481 | segment summary |

## by_side
| Segment | Rows | TP | SL | Timeout | Net PnL | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| BUY | 66 | 0 | 23 | 43 | -1030.743726 | segment summary |
| SELL | 161 | 33 | 11 | 116 | 288.176228 | segment summary |

## by_direction_confidence_bucket
| Segment | Rows | TP | SL | Timeout | Net PnL | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 0.01-0.05 | 31 | 0 | 9 | 22 | -366.81354 | segment summary |
| <0.01 | 196 | 33 | 25 | 137 | -375.753957 | segment summary |

## by_regime_confidence_bucket
| Segment | Rows | TP | SL | Timeout | Net PnL | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 0.15-0.25 | 18 | 2 | 4 | 12 | -131.235491 | segment summary |
| 0.25-0.35 | 50 | 6 | 11 | 33 | -421.536483 | segment summary |
| 0.35-0.39 | 13 | 0 | 1 | 12 | -98.791507 | segment summary |
| >=0.39 | 146 | 25 | 18 | 102 | -91.004016 | segment summary |

## by_violation_pattern
| Segment | Rows | TP | SL | Timeout | Net PnL | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| direction_confidence_below_threshold | 143 | 25 | 17 | 100 | -85.842423 | segment summary |
| regime_confidence_below_threshold+direction_confidence_below_threshold | 84 | 8 | 17 | 59 | -656.725074 | segment summary |
