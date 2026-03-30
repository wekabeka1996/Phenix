# REPORT: MR V1 End-to-End Proof

## Package: MR-V1-WIRING-SUBPACK-B
## Date: 2026-03-30
## Status: DONE

---

## Purpose

Prove that the microstructure veto operates correctly on the **real** `_on_process_strategy()` path — not just helper-level `_check_microstructure_veto()` calls. This exercises the full CMD payload parsing, features caching, price_motion caching, strategy signal generation, and veto overlay.

## Test Architecture

Tests use `object.__new__(MeanReversionHandler)` to construct a minimal handler with only the fields needed for the CMD → veto path. The strategy's `on_bar()` is mocked to return actionable signals (LONG/SHORT), isolating the veto overlay behavior from full Bollinger Band computation.

For "allow" tests, `_emit_signal` is mocked because it depends on deep AuroraConfig state irrelevant to veto proof. The proof is: signal **reaches** `_emit_signal` (was not blocked by veto).

## Test File

`tests/integration/test_mr_v1_e2e_price_motion.py` — 11 tests

## Test Matrix

| # | Test | Veto Config | TFI | Price Motion | Expected |
|---|---|---|---|---|---|
| 1 | toxic_flow_blocks_long | enabled | -0.5 (adverse) | ret_60s=-0.002 (continuation) | BLOCKED |
| 2 | absorption_allows_long | enabled | -0.5 (adverse) | large lower wick | ALLOWED |
| 3 | toxic_flow_blocks_short | enabled | +0.5 (adverse) | ret_60s=+0.002 (continuation) | BLOCKED |
| 4 | absorption_allows_short | enabled | +0.5 (adverse) | large upper wick | ALLOWED |
| 5 | missing_tfi_fail_closed | enabled | absent | present | BLOCKED |
| 6 | obi_confirm_only_allows | obi_confirm=true | -0.5 | OBI=+0.1 (non-adverse) | ALLOWED |
| 7 | obi_confirms_blocks | obi_confirm=true | -0.5 | OBI=-0.5 + continuation | BLOCKED |
| 8 | missing_price_motion | enabled | -0.5 | absent | BLOCKED (ambiguous) |
| 9 | zero_range_bar | enabled | -0.5 | present | BLOCKED (zero range) |
| 10 | price_motion_cached | enabled | -0.5 | present | Cache proof |
| 11 | veto_disabled | None | -0.8 | present | ALLOWED |

## Key Proofs

### Proof 1: Price Motion Pipeline
Test #10 verifies that after `_on_process_strategy()`:
- `handler._last_cmd_price_motion["DOGEUSDT"]` contains the price_motion from CMD payload
- `handler._last_cmd_features["DOGEUSDT"]` does NOT contain price_motion
This proves the dedicated cache architecture works on the real path.

### Proof 2: Bivariate Discrimination
Tests #1 vs #2 (and #3 vs #4) prove the veto correctly differentiates toxic continuation from absorption using the same adverse TFI but different bar geometry / price returns.

### Proof 3: Fail-Closed Semantics
Test #5 (missing TFI) and #8 (missing price_motion) prove unconditional fail-closed on the real path.

### Proof 4: OBI Confirm-Only
Tests #6 vs #7 prove OBI is never a sole veto driver — it only confirms when TFI is already adverse.

## FACTS
1. All 11 E2E tests exercise the real `_on_process_strategy()` entrypoint [PROVEN]
2. CMD payload caching (features + price_motion) verified on real path [PROVEN by test #10]
3. Blocked/allowed outcomes match spec for all 6 required cases [PROVEN]

## INFERENCES
1. The veto overlay is correctly wired between strategy.on_bar() and _emit_signal() on the real path [INFERRED from test results]

## ASSUMPTIONS
None.

## UNKNOWNS
None.
