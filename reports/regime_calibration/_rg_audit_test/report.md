# Regime Parameter Calibration Report

## Context
- Symbols: ['BTCUSDT']
- Dates: 2026-02-08 to 2026-03-03
- TF: 300s
- Horizon: 12 bars
- Train Split: 0.7
- Seed: 42
- Trials: 30 (0 valid)

## Baseline Train Summary
- Score: -0.1137
- Macro F1: 0.0992
- Trend F1: 0.0000
- Uncertain Ratio: 0.2341
- Churn per 1000: 51.2568
- Avg Regime Duration: 19.4 bars

## Best Candidate Train Summary
- Score: -0.1137 (Δ +0.0000)
- Macro F1: 0.0992 (Δ +0.0000)
- Trend F1: 0.0000
- Uncertain Ratio: 0.2341
- Churn per 1000: 51.2568
- Avg Regime Duration: 19.4 bars

## Baseline Test Summary
- Macro F1: 0.1113
- Uncertain Ratio: 0.3776
- Churn per 1000: 62.0690

## Best Candidate Test Summary
- Macro F1: 0.1113 (Δ +0.0000)
- Trend F1: 0.0000
- Uncertain Ratio: 0.3776
- Churn per 1000: 62.0690

## Confusion Matrix (Train)
```text
True \ Pred | HIGH_VOL | LOW_VOLA | MEAN_REV | TREND_DO | TREND_UP | UNCERTAI
HIGH_VOLAT |        6 |        0 |       24 |        0 |        0 |       17
LOW_VOLATI |      193 |      971 |     1584 |        0 |        0 |      712
MEAN_REVER |        6 |        6 |       26 |        0 |        0 |       33
TREND_DOWN |        4 |        1 |        4 |        0 |        0 |        6
TREND_UP   |        1 |        2 |        0 |        0 |        0 |        3
UNCERTAIN  |       71 |       62 |      147 |        0 |        0 |      179
```

## Recommended YAML Overlay
```yaml
{}

```
