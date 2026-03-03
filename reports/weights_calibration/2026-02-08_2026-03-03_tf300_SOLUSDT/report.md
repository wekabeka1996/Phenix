# Signal Weights Calibration Report - SOLUSDT

## Parameters
- Symbol: SOLUSDT
- Dates: 2026-02-08 to 2026-03-03
- TF: 300s  |  horizon_bars: 1  |  train_frac: 0.70
- Ridge alpha: default  |  cost_bps_rt: 4

## Data
- days_train=16  rows_train=4,008
- days_test=7    rows_test=1,681
- eval_threshold=0.09

## Results
|         | Trades | total_pnl_bps | avg_pnl_bps | sharpe~  |
|---------|--------|---------------|-------------|---------|
| TRAIN baseline | 2449 | -6222.89 | -1.5526 | -22.31 |
| TRAIN calibr.  | 2644 | -1270.29 | -0.3169 |  -5.42 |
| TEST  baseline | 1008 | -1384.08 | -0.8234 |  -9.63 |
| TEST  calibr.  | 1101 | -1047.27 | -0.6230 |  -8.35 |

Train improvement: avg_pnl_bps -1.5526 -> -0.3169 (+79.6%)
Test  improvement: avg_pnl_bps -0.8234 -> -0.6230 (+24.3%)
Sharpe(test): -9.63 -> -8.35

## Best weights
absorption: 0.0562502, delta_price: 0.294059, depth_imbalance: 0.0148722
ema_bias: -0.176429, macro_resid: -0.0492056, obi: 0.135947
tfi: 0.263238, volatility_state: 0.0119935, volume_spike: 0.238007

## Notes
- ema_bias: positive (prev 0.20) -> NEGATIVE (-0.18). Ridge reversed sign.
- macro_resid: positive (prev 0.25) -> NEGATIVE (-0.05). Ridge reversed sign.
- depth_imbalance: negative (prev -0.20) -> POSITIVE (+0.015). Sign reversal.
- delta_price and tfi are dominant (0.294, 0.263).
- Applied to: config/aurora/strategies/aurora.yaml:aurora.assets.SOLUSDT.weights
