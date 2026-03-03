# Regime Parameter Calibration Report

## Context
- Symbols: ['BTCUSDT']
- Dates: 2026-02-08 to 2026-03-03
- TF: 300s
- Horizon: 12 bars
- Train Split: 0.7
- Seed: 42
- Trials: 300 (45 valid)

## Baseline Train Summary
- Score: -0.1137
- Macro F1: 0.0992
- Trend F1: 0.0000
- Uncertain Ratio: 0.2341
- Churn per 1000: 51.2568
- Avg Regime Duration: 19.4 bars

## Best Candidate Train Summary
- Score: 0.1430 (Δ +0.2567)
- Macro F1: 0.1614 (Δ +0.0622)
- Trend F1: 0.0000
- Uncertain Ratio: 0.0086
- Churn per 1000: 22.9177
- Avg Regime Duration: 43.2 bars

## Baseline Test Summary
- Macro F1: 0.1113
- Uncertain Ratio: 0.3776
- Churn per 1000: 62.0690

## Best Candidate Test Summary
- Macro F1: 0.1561 (Δ +0.0448)
- Trend F1: 0.0000
- Uncertain Ratio: 0.0310
- Churn per 1000: 28.1609

## Confusion Matrix (Train)
```text
True \ Pred | HIGH_VOL | LOW_VOLA | MEAN_REV | TREND_DO | TREND_UP | UNCERTAI
HIGH_VOLAT |        0 |       22 |       25 |        0 |        0 |        0
LOW_VOLATI |       21 |     2229 |     1073 |       63 |       39 |       35
MEAN_REVER |        0 |       27 |       41 |        3 |        0 |        0
TREND_DOWN |        0 |        5 |        8 |        0 |        2 |        0
TREND_UP   |        0 |        3 |        3 |        0 |        0 |        0
UNCERTAIN  |        3 |      196 |      226 |       18 |       16 |        0
```

## Recommended YAML Overlay
```yaml
hysteresis_bars: 8
models.mean_reversion.confidence_multiplier: 134.1
models.mean_reversion.threshold: 0.0074
models.sma_trend.confidence_multiplier: 39.4
models.sma_trend.sma_long_period: 29
models.sma_trend.sma_short_period: 9
models.volatility.low_vol_multiplier: 0.99
models.volatility.threshold_multiplier: 1.84
uncertain_cutoff: 0.41

```
