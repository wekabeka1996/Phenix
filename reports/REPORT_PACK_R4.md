# REPORT_PACK_R4: V2 Contract Alignment & Doc Sync

## Package: PACK-R4-MR-V2-CONTRACT-ALIGNMENT-AND-DOC-SYNC
## Date: 2026-03-30
## Status: DONE

---

## Problem Addressed
Drift between a richer approved Vector 2 design (per-side/per-direction sensitivities, per-side clamp controls) and the implemented symmetric simplified model. Must explicitly ratify one canonical contract.

## Decision: Option B — Ratify Simplified Model as Canonical

### Why Not Option A (richer contract)?
1. No live calibration data exists to justify per-side/per-direction differentiation [FACT]
2. Adding `funding_shift_magnitude_long`/`funding_shift_magnitude_short`/`positive_sensitivity`/`negative_sensitivity` without data creates unjustified configurability [INFERRED]
3. The simplified model correctly implements "fade the crowd" economic logic [PROVEN by R2 trigger-boundary tests]
4. The model can be extended additively when calibration data is available [INFERRED]

### What the Simplified (Canonical) Contract Contains
| Parameter | Scope | Description |
|---|---|---|
| `funding_shift_magnitude` | Symmetric (same for LONG and SHORT) | Max threshold shift per unit normalized funding |
| `funding_normalization_scale` | Global | Normalizer: funding / scale = [-1, 1] |
| `funding_deadband` | Global | Noise suppression threshold |
| `threshold_clamp_min` | Symmetric | Floor for both sides |
| `threshold_clamp_max` | Symmetric | Ceiling for both sides |
| `base_long_threshold` | Per-side (static) | Base %B threshold for LONG |
| `base_short_threshold` | Per-side (static) | Base %B threshold for SHORT |

### What the Richer (Deferred) Contract Would Add
| Parameter | Status | Rationale for Deferral |
|---|---|---|
| `funding_shift_magnitude_long` / `_short` | Deferred | No calibration data |
| `positive_funding_sensitivity` / `negative_funding_sensitivity` | Deferred | No calibration data |
| `clamp_min_long` / `clamp_max_long` / `clamp_min_short` / `clamp_max_short` | Deferred | No asymmetric clamp need demonstrated |

## FACTS

### Parity Check: Code ↔ Config ↔ Docs ↔ Tests

| Surface | Status | Notes |
|---|---|---|
| `config_models.py::MRDirectionalBiasConfig` | 8 fields, `extra='forbid'` | Matches YAML exactly |
| `mean_reversion.yaml::directional_bias` | 8 fields | Matches Pydantic exactly |
| `mean_reversion_state_machine_passport.md` Section 14 | 8 fields in table, formulas match | Updated with R2 semantics fix, R3 isolation, R4 ratification |
| `test_mr_directional_bias.py` | 19 tests covering all behaviors | Includes trigger-boundary + cross-symbol proofs |
| `test_mr_directional_bias_config.py` | 16 tests covering all validators | All passing |

**Parity is complete. One canonical contract exists.** [PROVEN]

### Documents Updated
1. `mean_reversion_state_machine_passport.md`:
   - Section 13: Added R1 hardening note, removed "skip" from missing_policy options
   - Section 14: Added R2/R3 hardening notes, corrected trigger semantics, updated test counts, added Contract Ratification subsection
2. `REPORT_IMPLEMENTED_MR_VECTORS_V1_V2.md`: Will be updated with R-pack references

## Files Changed

| File | Change |
|---|---|
| `config/docs/mean_reversion_state_machine_passport.md` | Updated Sections 13+14 with R1-R4 hardening, added Contract Ratification |
| `reports/REPORT_PACK_R4.md` | This report |

## Tests

66/66 total across all V1+V2 suites:
- 16 V1 behavioral tests
- 15 V1 config tests
- 19 V2 behavioral tests (including 2 trigger-boundary + 4 cross-symbol)
- 16 V2 config tests

## INFERENCES
1. The simplified symmetric model is the correct starting point for a system with no live calibration data [INFERRED]
2. Per-side differentiation becomes valuable only after observing asymmetric funding response in live trading [INFERRED]

## ASSUMPTIONS
None.

## UNKNOWNS
1. Whether the richer contract will be needed after live calibration (depends on market behavior)

## Remaining Risks
None for this package.
