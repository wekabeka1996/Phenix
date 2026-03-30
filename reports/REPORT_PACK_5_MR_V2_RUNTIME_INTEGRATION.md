# REPORT_PACK_5: MR V2 Runtime Integration

## Package: PACK-5-MR-V2-RUNTIME-INTEGRATION
## Date: 2026-03-30
## Status: DONE

---

## Objective
Implement dynamic directional threshold modulation via handler-side preprocessing.

## FACTS
1. `MRStrategyConfig` (dataclass) extended with `entry_threshold_long` and `entry_threshold_short` optional fields
2. `_evaluate_signal` in `MeanReversion1mStrategy` uses directional thresholds when set, falls back to legacy symmetric `entry_threshold`
3. `_apply_directional_bias()` added to `MeanReversionHandler` — computes effective thresholds from funding_rate
4. Method sets transient overrides on `strategy.config` before each `on_bar()` call
5. No mutation of static YAML values — transient values are recomputed every bar
6. Missing funding → static split thresholds (graceful degradation, NO fail-closed)
7. 23 existing strategy tests pass (0 regressions)
8. Per-symbol config resolution: per-asset override > global default

## Formula (as implemented)

```python
norm_funding = clamp(funding_rate / funding_normalization_scale, -1, 1)
if |norm_funding| < funding_deadband: norm_funding = 0

eff_long  = clamp(base_long  - norm_funding * shift_magnitude, clamp_min, clamp_max)
eff_short = clamp(base_short + norm_funding * shift_magnitude, clamp_min, clamp_max)
```

## Code Mapping

| Formula Component | Code Location |
|---|---|
| Normalize funding | `mean_reversion_handler.py:_apply_directional_bias` line ~837 |
| Deadband | `_apply_directional_bias` line ~841 |
| Compute effective thresholds | `_apply_directional_bias` lines ~845-848 |
| Clamp | `_apply_directional_bias` lines ~851-852 |
| Set on strategy config | `_apply_directional_bias` lines ~854-855 |
| Consume long_threshold | `mean_reversion_strategy.py:_evaluate_signal` lines ~500, 517, 563 |
| Consume short_threshold | `mean_reversion_strategy.py:_evaluate_signal` lines ~500, 519, 574 |

## INFERENCES
1. Funding rate expected in `features.funding_rate` from FE payload (not yet populated by FE)
2. Before FE provides funding, the feature will be missing → graceful degradation works

## ASSUMPTIONS
1. `funding_rate` will be added to FE features pipeline (out of scope for this package)
2. Typical crypto perpetual funding rates are ~0.0001 to 0.001 per period

## UNKNOWNS
1. Whether FE currently populates `funding_rate` in features (likely not yet)
2. Optimal `funding_normalization_scale` requires live calibration

---

## Files Changed

| File | Change |
|---|---|
| `apps/reference/domains/feature_engineering/mean_reversion_strategy.py` | Added `entry_threshold_long/short` to `MRStrategyConfig`, updated `_evaluate_signal` to use split thresholds |
| `apps/reference/domains/decision_making/mean_reversion_handler.py` | Added `_apply_directional_bias()` method, added bias config resolution and funding rate state in `__init__` |

## Validation Evidence
- Module imports cleanly
- 23 existing MR strategy tests pass (0 regressions, 8 skipped)
- When `entry_threshold_long/short` are None → falls back to legacy `entry_threshold` (backwards compatible)

## Remaining Risks
1. Behavioral tests for threshold modulation deferred to PACK-6
2. `funding_rate` not yet available in FE pipeline — will degrade to static thresholds at runtime
