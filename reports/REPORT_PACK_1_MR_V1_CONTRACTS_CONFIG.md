# REPORT_PACK_1: MR V1 Contracts & Config

## Package: PACK-1-MR-V1-CONTRACTS-CONFIG
## Date: 2026-03-30
## Status: DONE

---

## Objective
Add strict typed config for `MRMicrostructureVetoConfig` — Vector 1 Microstructure Veto overlay.

## FACTS
1. `MRMicrostructureVetoConfig` is a strict `BaseModel` with `extra='forbid'`
2. 12 typed fields with range constraints and defaults
3. One model_validator enforcing `absorption_rebound_threshold < price_continuation_threshold`
4. Wired as `Optional` field on both `MeanReversion1mStrategyConfig` (global) and `MRStrategyOverrideConfig` (per-asset)
5. YAML block added to `config/aurora/strategies/mean_reversion.yaml` with `enabled: false`
6. 14 tests pass (0 new failures introduced)
7. The codebase uses `tfi` (Trade Flow Imbalance) not "TSI" — Vector 1 maps to `tfi`
8. The codebase uses `obi` (Order Book Imbalance) — already available in FE payload
9. `absorption` field in FE is always `"0.0"` — absorption detection uses wick ratio + price rebound instead

## INFERENCES
1. Per-asset override pattern follows existing `squeeze_expansion_veto` / `momentum_separation_veto` precedent
2. `missing_policy: "block"` default is correct fail-closed behavior per spec

## ASSUMPTIONS
1. TFI EMA smoothing span of 5 is reasonable for 5m bars (tunable via config)
2. Default thresholds (tfi: 0.3, obi: 0.3, continuation: 0.1%, rebound: 0.05%) are sensible starting points
3. Price reaction can be measured from FE `ret_60s` / bar wick geometry (available in CMD:PROCESS_STRATEGY payload)

## UNKNOWNS
1. Optimal threshold values require live calibration — starting disabled
2. Whether TFI EMA should be computed in handler (new state) or pre-computed in FE pipeline

---

## Field Table

| Field | Type | Default | Range | Description |
|---|---|---|---|---|
| `enabled` | `bool` | — | — | Master enable for veto |
| `tfi_ema_span` | `int` | 5 | [2, 50] | EMA smoothing for raw TFI |
| `tfi_adverse_threshold` | `float` | 0.3 | (0, 1] | Adverse flow threshold |
| `obi_confirm_enabled` | `bool` | False | — | Require OBI confirmation |
| `obi_adverse_threshold` | `float` | 0.3 | (0, 1] | Adverse book threshold |
| `price_reaction_lookback_sec` | `int` | 60 | [10, 600] | Price continuation window |
| `price_continuation_threshold` | `float` | 0.001 | (0, 0.05] | Min adverse move for toxic |
| `absorption_wick_ratio_min` | `float` | 0.4 | [0, 1] | Min wick ratio for absorption |
| `absorption_rebound_threshold` | `float` | 0.0005 | [0, 0.05] | Min favorable move for rebound |
| `readiness_min_bars` | `int` | 5 | [1, 100] | Min bars before veto engages |
| `missing_policy` | `Literal["block","skip"]` | "block" | — | Fail-closed policy for missing data |

## Invariants
1. `absorption_rebound_threshold < price_continuation_threshold` (model_validator)
2. `extra='forbid'` — no unknown fields allowed
3. All numeric fields have explicit bounds via `Field(ge=, le=, gt=, lt=)`

---

## Files Changed

| File | Change |
|---|---|
| `apps/reference/config_models.py` | Added `MRMicrostructureVetoConfig` class (12 fields, 1 validator) |
| `apps/reference/config_models.py` | Added `microstructure_veto` field to `MRStrategyOverrideConfig` |
| `apps/reference/config_models.py` | Added `microstructure_veto` field to `MeanReversion1mStrategyConfig` |
| `config/aurora/strategies/mean_reversion.yaml` | Added `microstructure_veto:` YAML block (disabled) |
| `tests/config/test_mr_microstructure_veto_config.py` | 14 contract tests (all passing) |

## Test Evidence

```
14 passed in 0.73s
```

| Test | Claim |
|---|---|
| `test_valid_config_loads` | Valid config creates instance correctly |
| `test_extra_field_rejected` | `extra='forbid'` rejects unknown fields |
| `test_tfi_threshold_zero_rejected` | tfi_adverse_threshold > 0 enforced |
| `test_tfi_threshold_above_one_rejected` | tfi_adverse_threshold <= 1.0 enforced |
| `test_obi_threshold_zero_rejected` | obi_adverse_threshold > 0 enforced |
| `test_obi_threshold_above_one_rejected` | obi_adverse_threshold <= 1.0 enforced |
| `test_absorption_rebound_equals_continuation_rejected` | rebound < continuation invariant |
| `test_absorption_rebound_exceeds_continuation_rejected` | rebound < continuation invariant |
| `test_missing_policy_invalid_value_rejected` | Only "block"/"skip" accepted |
| `test_readiness_min_bars_zero_rejected` | readiness_min_bars >= 1 |
| `test_tfi_ema_span_below_minimum_rejected` | tfi_ema_span >= 2 |
| `test_yaml_load_wires_microstructure_veto` | Full YAML → Pydantic path works |
| `test_yaml_load_without_microstructure_veto` | Optional field (None when absent) |
| `test_per_asset_microstructure_veto_override` | Per-asset override wires correctly |

## Remaining Risks
1. TFI EMA state management needs to be decided in PACK-2 (handler-side vs FE)
2. Threshold calibration deferred to live testing phase
