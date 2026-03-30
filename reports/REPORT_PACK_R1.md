# REPORT_PACK_R1: V1 Strict Fail-Closed Hardening

## Package: PACK-R1-MR-V1-STRICT-FAIL-CLOSED-HARDENING
## Date: 2026-03-30
## Status: DONE

---

## Problem Addressed
The `missing_policy` field on `MRMicrostructureVetoConfig` accepted `Literal["block", "skip"]`. When set to `"skip"`, the handler returned `(True, "")` on missing/invalid TFI — a fail-open path. This violates the approved safety contract: when microstructure veto is enabled, missing required inputs MUST block.

## FACTS

### Before (permissive)
1. `config_models.py:562` — `missing_policy: Literal["block", "skip"]` with default `"block"`
2. `mean_reversion_handler.py:668-678` — Two conditional branches: `if veto_cfg.missing_policy == "block": return False` else `return True`
3. `test_mr_microstructure_veto.py:193` — `test_missing_tfi_allows_when_policy_skip` explicitly tested and asserted the fail-open path
4. `mean_reversion.yaml:278` — Configured value was `"block"`, so live runtime was safe, but the code path existed

### After (hardened)
1. `config_models.py:562` — `missing_policy: Literal["block"]` — only `"block"` accepted; `"skip"` raises `ValidationError`
2. `mean_reversion_handler.py:667-673` — Unconditional fail-closed: `return False, "MICROSTRUCTURE_VETO:TFI_MISSING"` and `return False, "MICROSTRUCTURE_VETO:TFI_INVALID"` — no policy branch
3. `test_mr_microstructure_veto.py:193` — Replaced `test_missing_tfi_allows_when_policy_skip` with `test_skip_policy_rejected_at_config_level` (proves Pydantic rejects `"skip"`)
4. Added `test_invalid_tfi_blocks_unconditionally` (proves non-numeric TFI always blocks)
5. Added `test_missing_policy_skip_rejected` in config tests (proves `"skip"` is a ValidationError)

## Code Paths Audited

| Path | Before | After |
|---|---|---|
| TFI is None | Block if policy="block", else allow | Always block |
| TFI non-numeric | Block if policy="block", else allow | Always block |
| OBI missing + confirm enabled | Always block | Always block (no change) |
| Warmup not ready | Always block | Always block (no change) |
| Zero-range bar | Always block | Always block (no change) |

**Proven**: No permissive path remains in the active runtime contract. [PROVEN]

## Files Changed

| File | Change |
|---|---|
| `apps/reference/config_models.py` | `Literal["block", "skip"]` → `Literal["block"]`; updated description |
| `apps/reference/domains/decision_making/mean_reversion_handler.py` | Removed `missing_policy` conditional branches; unconditional fail-closed |
| `config/aurora/strategies/mean_reversion.yaml` | Updated comment to note "skip" removal |
| `tests/domains/decision_making/test_mr_microstructure_veto.py` | Replaced skip-allows test; added invalid-TFI-blocks test |
| `tests/config/test_mr_microstructure_veto_config.py` | Added `test_missing_policy_skip_rejected` |

## Tests

| Test | Assertion |
|---|---|
| `test_missing_tfi_blocks_when_policy_block` | Missing TFI → `allowed=False`, `TFI_MISSING` |
| `test_skip_policy_rejected_at_config_level` | `missing_policy="skip"` → `ValidationError` |
| `test_invalid_tfi_blocks_unconditionally` | Non-numeric TFI → `allowed=False`, `TFI_INVALID` |
| `test_missing_policy_skip_rejected` | Config-level: `"skip"` → `ValidationError` |
| `test_no_features_cached_blocks` | No features at all → `TFI_MISSING` |
| `test_warmup_not_ready_blocks` | Insufficient bars → block |
| `test_missing_obi_blocks_when_confirm_enabled` | OBI missing + confirm → block |

**31/31 tests pass** (16 behavioral + 15 config)

## INFERENCES
1. The `"skip"` value was never used in the live YAML (always `"block"`) — so live runtime was already safe [PROVEN by YAML inspection]
2. Removing the `Literal` option at Pydantic level makes it impossible to construct a permissive config, even via per-asset overrides [PROVEN by `extra='forbid'` + `Literal["block"]`]

## ASSUMPTIONS
None.

## UNKNOWNS
None.

## Remaining Risks
None for this package. Strict fail-closed is fully enforced at config + handler + test levels.
