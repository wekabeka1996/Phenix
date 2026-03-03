# Regime Parameter Calibration Report

## Context
- Symbols: ['SOLUSDT']
- Dates: 2026-02-08 to 2026-03-03
- TF: 300s
- Horizon: 12 bars
- Train Split: 0.7
- Seed: 42
- Trials: 300 (1 valid)

## Baseline Train Summary
- Score: -0.2338
- Macro F1: 0.1260
- Trend F1: 0.0000
- Uncertain Ratio: 0.4170
- Churn per 1000: 52.4889
- Avg Regime Duration: 19.0 bars

## Best Candidate Train Summary
- Score: 0.0363 (Δ +0.2701)
- Macro F1: 0.0861 (Δ -0.0399)
- Trend F1: 0.0140
- Uncertain Ratio: 0.0375
- Churn per 1000: 39.6747
- Avg Regime Duration: 25.0 bars

## Baseline Test Summary
- Macro F1: 0.1216
- Uncertain Ratio: 0.5259
- Churn per 1000: 49.4253

## Best Candidate Test Summary
- Macro F1: 0.0769 (Δ -0.0447)
- Trend F1: 0.0172
- Uncertain Ratio: 0.0730
- Churn per 1000: 58.0460

## Confusion Matrix (Train)
```text
True \ Pred | HIGH_VOL | LOW_VOLA | MEAN_REV | TREND_DO | TREND_UP | UNCERTAI
HIGH_VOLAT |       29 |        0 |       40 |        6 |        6 |        8
LOW_VOLATI |       81 |      175 |     2201 |       96 |       66 |       41
MEAN_REVER |       30 |        9 |      171 |       24 |       17 |       19
TREND_DOWN |        1 |        0 |       22 |        2 |        0 |        1
TREND_UP   |        3 |        3 |       21 |        0 |        1 |        2
UNCERTAIN  |       90 |       48 |      622 |       95 |       47 |       81
```

## Recommended YAML Overlay
```yaml
hysteresis_bars: 3
models.mean_reversion.confidence_multiplier: 35.1
models.mean_reversion.threshold: 0.0102
models.sma_trend.confidence_multiplier: 27.6
models.sma_trend.sma_long_period: 37
models.sma_trend.sma_short_period: 18
models.volatility.low_vol_multiplier: 0.79
models.volatility.threshold_multiplier: 1.28
uncertain_cutoff: 0.42

```
