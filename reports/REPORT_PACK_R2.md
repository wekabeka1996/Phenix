# REPORT_PACK_R2: V2 SHORT Semantics Forensic Fix

## Package: PACK-R2-MR-V2-SHORT-SEMANTICS-FORENSIC-FIX
## Date: 2026-03-30
## Status: DONE

---

## Problem Addressed
Documentation, handler comments, and test docstrings claimed positive funding makes "LONG easier, SHORT stricter". This is semantically inverted relative to the actual trigger topology.

## Root Cause: Threshold Value vs Trigger Boundary Confusion

The word "stricter" was applied to the **threshold value** changing direction, but not to the **trigger boundary** that determines whether a signal fires. These are not the same thing for SHORT signals.

## Formal Derivation

### Trigger Topology (from `_evaluate_signal`)
```
LONG  fires when:  pct_b < long_threshold
SHORT fires when:  pct_b > (1 - short_threshold)
```

### Formula (from `_apply_directional_bias`)
```
eff_long  = base_long  - norm_funding × magnitude
eff_short = base_short + norm_funding × magnitude
```

### Truth Table

| Scenario | norm_funding | eff_long | LONG boundary (pct_b <) | LONG effect | eff_short | SHORT boundary (pct_b >) | SHORT effect |
|---|---|---|---|---|---|---|---|
| Baseline | 0 | 0.10 | 0.10 | — | 0.10 | 0.90 | — |
| Positive funding | +1.0 | 0.08 | 0.08 | HARDER (↓) | 0.12 | 0.88 | EASIER (↓) |
| Negative funding | -1.0 | 0.12 | 0.12 | EASIER (↑) | 0.08 | 0.92 | HARDER (↑) |

### Key Insight
- For LONG: threshold IS the boundary → lower threshold = harder [PROVEN]
- For SHORT: boundary = `1 - threshold` → higher threshold = LOWER boundary = EASIER [PROVEN]
- The `eff_short` value increases with positive funding, but the trigger boundary `(1 - eff_short)` decreases → SHORT becomes easier, not stricter [PROVEN]

### Economic Correctness
- Positive funding = longs crowded/paying → fade → SHORT easier, LONG harder ✓ [PROVEN]
- Negative funding = shorts crowded/paying → fade → LONG easier, SHORT harder ✓ [PROVEN]

**The formula in code was always economically correct. Only the prose labels were inverted.** [PROVEN]

## FACTS

### Code Changes (formula unchanged, only comments fixed)
1. `mean_reversion_handler.py:843-846` — Comment corrected: "LONG harder, SHORT easier" replaces "LONG easier, SHORT stricter"
2. No formula, conditional, or numeric code was changed

### Test Changes
3. `test_positive_funding_shifts` — Docstring corrected + trigger geometry explanation added
4. `test_negative_funding_shifts` — Same
5. Assertion comments on lines 105-108 and 131-134 corrected to reference trigger boundaries
6. Two new tests added: `test_trigger_boundary_positive_funding`, `test_trigger_boundary_negative_funding`
   - These assert exact trigger boundaries (not just threshold values)
   - They prove LONG_boundary vs baseline and SHORT_boundary vs baseline directionally

### Doc Changes
7. `mean_reversion_state_machine_passport.md` Section 14 — Interpretation text corrected

## Files Changed

| File | Change |
|---|---|
| `apps/reference/domains/decision_making/mean_reversion_handler.py` | Comment fix (line 843-846) |
| `tests/domains/decision_making/test_mr_directional_bias.py` | Fixed 2 docstrings, 4 assertion comments, added 2 trigger-boundary tests |
| `config/docs/mean_reversion_state_machine_passport.md` | Section 14 interpretation corrected |

## Tests

15/15 pass:

| Test | What It Proves |
|---|---|
| `test_trigger_boundary_positive_funding` | pos funding → LONG boundary 0.08 < baseline 0.10 (harder), SHORT boundary 0.88 < baseline 0.90 (easier) |
| `test_trigger_boundary_negative_funding` | neg funding → LONG boundary 0.12 > baseline 0.10 (easier), SHORT boundary 0.92 > baseline 0.90 (harder) |
| `test_positive_funding_shifts` | Numeric: eff_long=0.08, eff_short=0.12 |
| `test_negative_funding_shifts` | Numeric: eff_long=0.12, eff_short=0.08 |
| `test_zero_funding_no_shift` | No funding → no shift from base |

## INFERENCES
1. The original formula sign was correct from the start — only the English labels were wrong [PROVEN by trigger-boundary tests]

## ASSUMPTIONS
None.

## UNKNOWNS
None.

## Remaining Risks
None for this package. Trigger math is now formally proven with boundary tests.
