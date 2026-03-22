# Aurora Threshold Calibration Report

## Scope
- Objective: calibrate only live per-symbol Aurora threshold surface for signal_threshold.value and regime_thresholds.
- Non-goals: no weights, no neutral_threshold, no cooldown, no holding period, no business-logic mutation.
- Symbols: ETHUSDT, SOLUSDT
- Date window: 2026-03-20 through 2026-03-20 inclusive

## Data Source
- Input source: aurora_core QUADRATIC_DECISION_TRACE log parsing
- Log files matched: 6
- logs/aurora_core.log
- logs/aurora_core.log.1
- logs/aurora_core.log.2
- logs/aurora_core.log.3
- logs/aurora_core.log.4
- logs/aurora_core.log.5

## Runtime Truth Anchors
- FACT: per-symbol signal_threshold.value is read in Aurora decision path before kernel invocation when assets.<SYMBOL>.signal_threshold.enabled=true.
- FACT: per-symbol assets.<SYMBOL>.regime_thresholds override the global regime threshold map in live runtime.
- FACT: v1 calibrator intentionally excludes neutral_threshold and hold/exit hysteresis surfaces.
- FACT: this tool does not write back into aurora.yaml; it emits artifact-only overlay and report files.

## Symbol Summaries

### ETHUSDT
- Sample counts: total=65, non_deferred=65, deferred=0, neutral=65, side_bearing=0
- Regime counts: {'MEAN_REVERSION': 32, 'TREND_DOWN': 25, 'UNCERTAIN': 8}
- Observed |score| percentiles: p50=0.000000, p75=0.023921, p80=0.024928, p90=0.032748
- Current signal_threshold.value: 0.090000
- Current regime_thresholds: {'HIGH_VOLATILITY': 1.3, 'LOW_VOLATILITY': 0.85, 'MEAN_REVERSION': 1.05, 'DEFAULT': 1.0}
- Proposed signal_threshold.value: 0.024928
- Proposed regime_thresholds: {'DEFAULT': 1.0, 'MEAN_REVERSION': 0.9589457637997434, 'TREND_DOWN': 1.3226091142490373}
- Estimated activation rate: current=0.00%, proposed=21.54%

#### Regime Breakdown
| regime | samples | neutral | side | p50_abs | p75_abs | p80_abs | p90_abs | current_factor | current_effective | proposed_factor | proposed_effective |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MEAN_REVERSION | 32 | 32 | 0 | 0.000000 | 0.023517 | 0.023905 | 0.024347 | 1.050000 | 0.094500 | 0.958946 | 0.023905 |
| TREND_DOWN | 25 | 25 | 0 | 0.000000 | 0.032970 | 0.032970 | 0.033043 | 1.000000 | 0.090000 | 1.322609 | 0.032970 |
| UNCERTAIN | 8 | 8 | 0 | 0.000000 | 0.000000 | 0.000000 | 0.005367 | 1.000000 | 0.090000 | - | - |

#### Warnings
- No side-bearing non-deferred samples observed; v1 proposal is score-distribution based only.
- Regime UNCERTAIN for ETHUSDT has only 8 non-deferred samples; no regime-specific factor emitted.

### SOLUSDT
- Sample counts: total=65, non_deferred=65, deferred=0, neutral=65, side_bearing=0
- Regime counts: {'LOW_VOLATILITY': 5, 'MEAN_REVERSION': 34, 'TREND_DOWN': 16, 'UNCERTAIN': 10}
- Observed |score| percentiles: p50=0.021702, p75=0.029524, p80=0.029709, p90=0.039556
- Current signal_threshold.value: 0.090000
- Current regime_thresholds: {'HIGH_VOLATILITY': 1.15, 'LOW_VOLATILITY': 0.75, 'MEAN_REVERSION': 1.0, 'DEFAULT': 1.0}
- Proposed signal_threshold.value: 0.029709
- Proposed regime_thresholds: {'DEFAULT': 1.0, 'MEAN_REVERSION': 0.9843818371537245, 'TREND_DOWN': 1.3456528324750077, 'UNCERTAIN': 0.7401393517116025}
- Estimated activation rate: current=0.00%, proposed=24.62%

#### Regime Breakdown
| regime | samples | neutral | side | p50_abs | p75_abs | p80_abs | p90_abs | current_factor | current_effective | proposed_factor | proposed_effective |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| LOW_VOLATILITY | 5 | 5 | 0 | 0.000000 | 0.032873 | 0.033078 | 0.033487 | 0.750000 | 0.067500 | - | - |
| MEAN_REVERSION | 34 | 34 | 0 | 0.000000 | 0.028825 | 0.029245 | 0.029621 | 1.000000 | 0.090000 | 0.984382 | 0.029245 |
| TREND_DOWN | 16 | 16 | 0 | 0.039276 | 0.039732 | 0.039978 | 0.040427 | 1.000000 | 0.090000 | 1.345653 | 0.039978 |
| UNCERTAIN | 10 | 10 | 0 | 0.021730 | 0.021908 | 0.021989 | 0.022112 | 1.000000 | 0.090000 | 0.740139 | 0.021989 |

#### Warnings
- No side-bearing non-deferred samples observed; v1 proposal is score-distribution based only.
- Regime LOW_VOLATILITY for SOLUSDT has only 5 non-deferred samples; no regime-specific factor emitted.

## Candidate Overlay
```yaml
assets:
  ETHUSDT:
    signal_threshold:
      value: 0.024928
    regime_thresholds:
      DEFAULT: 1.0
      MEAN_REVERSION: 0.958946
      TREND_DOWN: 1.322609
  SOLUSDT:
    signal_threshold:
      value: 0.029709
    regime_thresholds:
      DEFAULT: 1.0
      MEAN_REVERSION: 0.984382
      TREND_DOWN: 1.345653
      UNCERTAIN: 0.740139
```

## Facts
- FACT: the calibrator reads only aurora.assets.<SYMBOL>.signal_threshold.value and aurora.assets.<SYMBOL>.regime_thresholds from aurora.yaml.
- FACT: the calibrator does not read or tune neutral_threshold, weights, cooldown, or holding_period.
- FACT: the v1 dataset is log-derived from QUADRATIC_DECISION_TRACE entries in aurora_core logs.

## Inferences
- INFERENCE: lowering per-symbol effective thresholds toward observed upper score quantiles should increase side activation rate relative to current config surface.
- INFERENCE: regime-specific factors are only emitted where regime sample coverage clears the configured minimum.

## Assumptions
- ASSUMPTION: QUADRATIC_DECISION_TRACE score distribution is an acceptable v1 proxy for threshold crossing calibration without replaying full decision state.
- ASSUMPTION: deep-merge application of the emitted overlay preserves the existing signal_threshold.enabled=true flag in base config.

## Unknowns
- UNKNOWN: whether the proposed threshold surface improves realized trading quality downstream after execution, objective gating, and risk controls.
- UNKNOWN: whether other time windows would suggest different regime factors for ETHUSDT and SOLUSDT.

## What Remains Unproven
- This v1 tool does not prove that the proposed thresholds are optimal, only that they are aligned to observed runtime score distributions and emitted via the correct live config surface.
