# REPORT_PACK_4: MR V2 Contracts & Config

## Package: PACK-4-MR-V2-CONTRACTS-CONFIG
## Date: 2026-03-30
## Status: DONE

---

## Objective
Add strict typed config for `MRDirectionalBiasConfig` — Vector 2 Directional Bias Injection.

## FACTS
1. `MRDirectionalBiasConfig` is strict `BaseModel` with `extra='forbid'`
2. 8 typed fields: `enabled`, `base_long_threshold`, `base_short_threshold`, `funding_shift_magnitude`, `funding_normalization_scale`, `funding_deadband`, `threshold_clamp_min`, `threshold_clamp_max`
3. Model validator: `clamp_min < clamp_max`, both base thresholds within clamp bounds
4. Wired as `Optional` on both `MeanReversion1mStrategyConfig` (global) and `MRStrategyOverrideConfig` (per-asset)
5. YAML block added to mean_reversion.yaml with `enabled: false`
6. 16 tests pass (0 new failures)

## Math Contract

```
normalized_funding = clamp(funding_rate / funding_normalization_scale, -1, 1)
if |normalized_funding| < funding_deadband: normalized_funding = 0

effective_long  = clamp(base_long  - norm_funding * shift_magnitude, clamp_min, clamp_max)
effective_short = clamp(base_short + norm_funding * shift_magnitude, clamp_min, clamp_max)
```

| Funding | Effect |
|---|---|
| positive (longs pay) | LONG threshold decreases (easier), SHORT threshold increases (stricter) |
| negative (shorts pay) | LONG threshold increases (stricter), SHORT threshold decreases (easier) |
| missing | static split thresholds (graceful degradation) |

## Field Table

| Field | Type | Default | Range | Description |
|---|---|---|---|---|
| `enabled` | bool | — | — | Master enable |
| `base_long_threshold` | float | — | (0, 0.5] | Static %B for LONG |
| `base_short_threshold` | float | — | (0, 0.5] | Static %B for SHORT |
| `funding_shift_magnitude` | float | 0.02 | [0, 0.2] | Max shift per normalized funding unit |
| `funding_normalization_scale` | float | 0.0003 | >0 | Funding / this → normalized |
| `funding_deadband` | float | 0.1 | [0, 1] | Noise suppression band |
| `threshold_clamp_min` | float | 0.01 | [0, 0.5] | Floor |
| `threshold_clamp_max` | float | 0.3 | [0, 0.5] | Ceiling |

## Files Changed

| File | Change |
|---|---|
| `apps/reference/config_models.py` | Added `MRDirectionalBiasConfig` class |
| `apps/reference/config_models.py` | Added `directional_bias` to `MRStrategyOverrideConfig` and `MeanReversion1mStrategyConfig` |
| `config/aurora/strategies/mean_reversion.yaml` | Added `directional_bias:` YAML block |
| `tests/config/test_mr_directional_bias_config.py` | 16 contract tests |

## Test Evidence
```
16 passed in 1.32s
```

## Remaining Risks
1. Runtime integration (consuming thresholds in strategy) deferred to PACK-5
