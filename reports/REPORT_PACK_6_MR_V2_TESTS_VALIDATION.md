# REPORT_PACK_6: MR V2 Tests & Validation

## Package: PACK-6-MR-V2-TESTS-VALIDATION
## Date: 2026-03-30
## Status: DONE

---

## Objective
Validate all Vector 2 (Directional Bias Injection) behaviors with dedicated behavioral tests.

## FACTS
1. Test file: `tests/domains/decision_making/test_mr_directional_bias.py`
2. 13 test functions covering all required spec behaviors
3. All 13 tests PASS on first run (0 failures, 0 skipped)
4. 58 total Vector 1 + Vector 2 tests pass together (0 regressions)
5. Pre-existing failures (5) in `tests/domains/decision_making/` are unrelated to our changes (`trend_run_length` mock gap, `write_trade_intent_rejected` attribute path)

## Test Coverage Matrix

| # | Spec Requirement | Test Function | Status |
|---|---|---|---|
| 1 | Static split thresholds work without funding | `test_static_split_without_funding` | PASS |
| 2 | Positive funding shifts long/short correctly | `test_positive_funding_shifts` | PASS |
| 3 | Negative funding shifts long/short correctly | `test_negative_funding_shifts` | PASS |
| 4a | Clamp prevents threshold below clamp_min | `test_clamp_prevents_too_low` | PASS |
| 4b | Clamp prevents threshold above clamp_max | `test_clamp_prevents_too_high` | PASS |
| 5 | Deadband suppresses small funding noise | `test_deadband_suppresses_noise` | PASS |
| 6a | Missing funding falls back to static split | `test_missing_funding_returns_static` | PASS |
| 6b | Missing funding does NOT block strategy | `test_missing_funding_does_not_block_strategy` | PASS |
| 7 | No bias config clears overrides (legacy compat) | `test_no_bias_config_clears_overrides` | PASS |
| 8 | Split thresholds affect LONG signal path | `test_split_thresholds_affect_long_signal` | PASS |
| 9 | Split thresholds affect SHORT signal path | `test_split_thresholds_affect_short_signal` | PASS |
| 10 | Invalid (non-numeric) funding degrades to static | `test_invalid_funding_degrades_to_static` | PASS |
| 11 | Zero funding produces no shift | `test_zero_funding_no_shift` | PASS |

## Formula Verified by Tests

```
norm_funding = clamp(funding_rate / funding_normalization_scale, -1, 1)
if |norm_funding| < funding_deadband: norm_funding = 0

eff_long  = clamp(base_long  - norm_funding * shift_magnitude, clamp_min, clamp_max)
eff_short = clamp(base_short + norm_funding * shift_magnitude, clamp_min, clamp_max)
```

Verified scenarios:
- `norm = +1.0`: eff_long = 0.10 - 0.02 = 0.08 (easier), eff_short = 0.10 + 0.02 = 0.12 (stricter)
- `norm = -1.0`: eff_long = 0.10 + 0.02 = 0.12 (stricter), eff_short = 0.10 - 0.02 = 0.08 (easier)
- `norm = 0.0`: no shift, thresholds stay at base values
- Extreme shift: clamped to `[clamp_min, clamp_max]`
- Below deadband: treated as zero

## Test Architecture

Tests use the same `object.__new__(MeanReversionHandler)` pattern as PACK-3 (Vector 1 tests) to isolate `_apply_directional_bias()` from full handler initialization. Strategy-level integration tests use real `MeanReversion1mStrategy` with `MRStrategyConfig` dataclass.

## INFERENCES
1. The handler → strategy config injection pattern (transient overrides) is correct and testable in isolation
2. Backward compatibility is preserved: `None` thresholds fall back to legacy `entry_threshold`

## ASSUMPTIONS
1. `funding_rate` feature will eventually be populated by FE pipeline (currently absent → graceful degradation)

## UNKNOWNS
1. Optimal `funding_normalization_scale` for live markets (requires calibration)
2. Whether deadband of 0.1 is appropriate for typical funding rate noise

---

## Regression Check

| Suite | Tests | Passed | Failed | Skipped |
|---|---|---|---|---|
| Vector 1 + Vector 2 combined | 58 | 58 | 0 | 0 |
| All decision_making domain | 38 | 29 | 5* | 4 |

*5 failures are pre-existing (unrelated to Vector 1/Vector 2):
- 4x `test_arbitration_atomic_commit.py`: MockSG missing `trend_run_length`
- 1x `test_aurora_handler.py`: `write_trade_intent_rejected` attribute path refactored

## Files

| File | Role |
|---|---|
| `tests/domains/decision_making/test_mr_directional_bias.py` | 13 behavioral tests |
| `reports/REPORT_PACK_6_MR_V2_TESTS_VALIDATION.md` | This report |
