# Signal Weights Calibration Report — BTCUSDT

## Parameters
- Symbol: BTCUSDT
- Dates: 2026-02-08 to 2026-03-03
- TF: 300s  |  horizon_bars: 1  |  train_frac: 0.70
- Ridge alpha: default  |  cost_bps_rt: 4

## Data
- days_train=16  rows_train=3,928
- days_test=7    rows_test=1,687
- eval_threshold=0.162

## Results
|         | Trades | total_pnl_bps | avg_pnl_bps | sharpe~  |
|---------|--------|---------------|-------------|---------|
| TRAIN baseline | 2603 | -5215.21 | -1.3277 | -29.41 |
| TRAIN calibr.  | 2552 | -2685.46 | -0.6837 | -15.42 |
| TEST  baseline | 1184 | -1957.99 | -1.1606 | -20.96 |
| TEST  calibr.  | 1147 |  -861.70 | -0.5108 |  -9.17 |

Train improvement: avg_pnl_bps -1.3277 -> -0.6837 (+48.5%)
Test  improvement: avg_pnl_bps -1.1606 -> -0.5108 (+56.0%)
Sharpe(test): -20.96 -> -9.17

## Best weights


## Notes
- ema_bias: positive (prev 0.20) -> NEGATIVE (-0.12). Ridge reversed sign.
- macro_resid: positive (prev 0.15) -> NEGATIVE (-0.07). Ridge reversed sign.
- volume_spike and delta_price are dominant.
- Applied to: config/aurora/strategies/aurora.yaml:aurora.assets.BTCUSDT.weights
